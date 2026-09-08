from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass

from pokequant.models import PokemonMeta


_STAT_NAMES = ("HP", "Atk", "Def", "SpA", "SpD", "Spe")
_ID_RE = re.compile(r"[^a-z0-9]+")

_CHOICE_ITEMS = {"choiceband", "choicescarf", "choicespecs"}
_CHOICE_BAD_MOVES = {
    "agility",
    "bulkup",
    "calmmind",
    "dragondance",
    "irondefense",
    "nastyplot",
    "protect",
    "recover",
    "rest",
    "roost",
    "slackoff",
    "softboiled",
    "spikes",
    "stealthrock",
    "substitute",
    "swordsdance",
    "synthesis",
    "toxicspikes",
    "wish",
}
# Status moves that are unusable behind Assault Vest. This is intentionally
# conservative and can be expanded without changing the statistical model.
_KNOWN_STATUS_MOVES = _CHOICE_BAD_MOVES | {
    "defog",
    "encore",
    "healingwish",
    "haze",
    "leechseed",
    "partingshot",
    "reflect",
    "lightscreen",
    "auroraveil",
    "raindance",
    "sunnyday",
    "sandstorm",
    "snowscape",
    "electricterrain",
    "grassyterrain",
    "mistyterrain",
    "psychicterrain",
    "sleeptalk",
    "taunt",
    "thunderwave",
    "toxic",
    "trick",
    "switcheroo",
    "willowisp",
}

_ITEM_ROLE_REQUIREMENTS: dict[str, tuple[set[str], set[str]]] = {
    "lightclay": ({"reflect", "lightscreen", "auroraveil"}, set()),
    "damprock": ({"raindance"}, {"drizzle"}),
    "heatrock": ({"sunnyday"}, {"drought", "orichalcumpulse"}),
    "smoothrock": ({"sandstorm"}, {"sandstream"}),
    "icyrock": ({"snowscape", "hail"}, {"snowwarning"}),
    "terrainextender": (
        {"electricterrain", "grassyterrain", "mistyterrain", "psychicterrain"},
        {"electricsurge", "grassysurge", "mistysurge", "psychicsurge", "hadronengine"},
    ),
}


@dataclass(frozen=True, slots=True)
class Spread:
    nature: str
    evs: tuple[int, int, int, int, int, int]


@dataclass(frozen=True, slots=True)
class SetCandidate:
    species: str
    item: str | None
    ability: str | None
    tera_type: str | None
    spread: Spread
    moves: tuple[str, ...]
    marginal_score: float
    coherence_score: float = 1.0

    def export(self) -> str:
        head = self.species + (f" @ {self.item}" if self.item else "")
        lines = [head]
        if self.ability:
            lines.append(f"Ability: {self.ability}")
        if self.tera_type:
            lines.append(f"Tera Type: {self.tera_type.title()}")
        ev_parts = [
            f"{value} {stat}"
            for value, stat in zip(self.spread.evs, _STAT_NAMES)
            if value > 0
        ]
        if ev_parts:
            lines.append("EVs: " + " / ".join(ev_parts))
        if self.spread.nature:
            lines.append(f"{self.spread.nature} Nature")
        lines.extend(f"- {move}" for move in self.moves)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class TeamSetCandidate:
    sets: tuple[SetCandidate, ...]
    marginal_score: float

    @property
    def members(self) -> tuple[str, ...]:
        return tuple(candidate.species for candidate in self.sets)

    def export(self) -> str:
        return build_team_export(self.sets)


def _id(value: str | None) -> str:
    if not value:
        return ""
    return _ID_RE.sub("", value.casefold())


def parse_spread(label: str) -> Spread | None:
    nature, sep, raw_evs = str(label).partition(":")
    if not sep or not nature.strip():
        return None
    parts = raw_evs.split("/")
    if len(parts) != 6:
        return None
    try:
        evs = tuple(max(0, min(252, int(value))) for value in parts)
    except ValueError:
        return None
    if len(evs) != 6:
        return None
    return Spread(nature.strip(), evs)  # type: ignore[arg-type]


def set_coherence(
    *,
    item: str | None,
    moves: tuple[str, ...],
    spread: Spread,
    ability: str | None = None,
) -> float:
    """Heuristic proposal penalty for obviously self-conflicting legal sets.

    These rules do not claim to model battle value. They prevent independent
    Smogon marginals from promoting combinations such as Choice Scarf + Nasty
    Plot + Recover, Assault Vest + status moves, or role-extender items without
    the matching move/ability. Simulation remains the final arbiter.
    """
    item_id = _id(item)
    ability_id = _id(ability)
    move_ids = {_id(move) for move in moves}
    score = 1.0

    if item_id in _CHOICE_ITEMS and move_ids & _CHOICE_BAD_MOVES:
        score *= 0.03
    if item_id == "assaultvest" and move_ids & _KNOWN_STATUS_MOVES:
        score *= 0.01
    if item_id == "boosterenergy" and ability_id not in {"quarkdrive", "protosynthesis"}:
        score *= 0.02

    requirement = _ITEM_ROLE_REQUIREMENTS.get(item_id)
    if requirement is not None:
        required_moves, required_abilities = requirement
        if not (move_ids & required_moves) and ability_id not in required_abilities:
            score *= 0.02

    # Body Press is Defense-scaled. Iron Defense is usually selected to enable
    # Body Press; mixing Iron Defense into a conventional Attack set is a common
    # artifact of independent marginals rather than a coherent role.
    hp, atk, defense, spa, spd, spe = spread.evs
    del hp, spa, spd, spe
    if "bodypress" in move_ids:
        if defense >= 128:
            score *= 1.10
        elif defense < 64:
            score *= 0.45
    if {"irondefense", "bodypress"}.issubset(move_ids):
        if defense >= 128 and defense >= atk:
            score *= 1.20
        elif atk > defense:
            score *= 0.20
    if "irondefense" in move_ids and "bodypress" not in move_ids:
        score *= 0.18
    # Close Combat drops both defenses, directly working against an Iron Defense
    # win condition. Legal marginal mixing can otherwise rank this surprisingly high.
    if {"irondefense", "closecombat"}.issubset(move_ids):
        score *= 0.20

    return max(0.0, min(score, 1.25))


def _top(mapping: dict[str, float], n: int) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for key, raw in mapping.items():
        try:
            value = max(float(raw), 0.0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            rows.append((str(key), value))
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows[: max(n, 0)]


def _feature_log_score(value: float, mapping: dict[str, float]) -> float:
    total = 0.0
    for raw in mapping.values():
        try:
            total += max(float(raw), 0.0)
        except (TypeError, ValueError):
            continue
    if total <= 0 or value <= 0:
        return math.log(1e-12)
    return math.log(max(value / total, 1e-12))


def _move_sets(
    mon: PokemonMeta,
    *,
    pool_size: int = 9,
    keep: int = 20,
) -> list[tuple[tuple[str, ...], float]]:
    top_moves = _top(mon.moves, pool_size)
    if not top_moves:
        return [((), 0.0)]
    if len(top_moves) <= 4:
        names = tuple(name for name, _ in top_moves)
        score = sum(_feature_log_score(value, mon.moves) for _, value in top_moves)
        return [(names, score)]

    value_by_name = dict(top_moves)
    rows: list[tuple[tuple[str, ...], float]] = []
    for combo in itertools.combinations((name for name, _ in top_moves), 4):
        score = sum(
            _feature_log_score(value_by_name[name], mon.moves) for name in combo
        )
        rows.append((tuple(combo), score))
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows[: max(keep, 1)]


def generate_set_candidates(
    mon: PokemonMeta,
    *,
    top_items: int = 6,
    top_abilities: int = 2,
    top_teras: int = 5,
    top_spreads: int = 8,
    move_pool: int = 9,
    move_sets: int = 20,
    limit: int = 64,
) -> list[SetCandidate]:
    items = _top(mon.items, top_items) or [(None, 1.0)]
    abilities = _top(mon.abilities, top_abilities) or [(None, 1.0)]
    teras = _top(mon.tera_types, top_teras) or [(None, 1.0)]

    spreads: list[tuple[Spread, float]] = []
    for label, value in _top(mon.spreads, top_spreads):
        spread = parse_spread(label)
        if spread is not None:
            spreads.append((spread, value))
    if not spreads:
        # Non-zero EV sentinel prevents Showdown's "forgot to EV" validation warning.
        spreads = [(Spread("Serious", (4, 0, 0, 0, 0, 0)), 1.0)]

    move_options = _move_sets(mon, pool_size=move_pool, keep=move_sets)
    rows: list[SetCandidate] = []
    for (
        (item, item_v),
        (ability, ability_v),
        (tera, tera_v),
        (spread, spread_v),
        (moves, move_log),
    ) in itertools.product(items, abilities, teras, spreads, move_options):
        log_score = move_log
        if item is not None:
            log_score += _feature_log_score(item_v, mon.items)
        if ability is not None:
            log_score += 0.5 * _feature_log_score(ability_v, mon.abilities)
        if tera is not None:
            log_score += 0.6 * _feature_log_score(tera_v, mon.tera_types)
        if mon.spreads:
            log_score += _feature_log_score(spread_v, mon.spreads)
        coherence = set_coherence(
            item=item,
            ability=ability,
            moves=moves,
            spread=spread,
        )
        log_score += 1.5 * math.log(max(coherence, 1e-12))
        # Convert the log score to a monotonic, numerically stable display score.
        marginal = math.exp(
            max(log_score / max(len(moves) + 3.1, 1.0), -30.0)
        )
        rows.append(
            SetCandidate(
                species=mon.name,
                item=item,
                ability=ability,
                tera_type=tera,
                spread=spread,
                moves=moves,
                marginal_score=marginal,
                coherence_score=coherence,
            )
        )

    rows.sort(key=lambda row: row.marginal_score, reverse=True)
    # Deduplicate exact exports because empty/fallback feature dimensions can collide.
    seen: set[str] = set()
    out: list[SetCandidate] = []
    for row in rows:
        key = row.export()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= max(limit, 1):
            break
    return out


def generate_team_set_candidates(
    members: tuple[str, ...] | list[str],
    records: dict[str, PokemonMeta],
    *,
    per_species: int = 6,
    beam_width: int = 48,
    limit: int = 24,
) -> list[TeamSetCandidate]:
    """Beam-search likely exact-set combinations for a fixed species six.

    The set marginals are not treated as independent truth. They are only a
    proposal distribution that narrows the combinations passed to Showdown's
    legality gate and later to battle simulation.
    """
    species = tuple(members)
    if not species:
        return []
    missing = [name for name in species if name not in records]
    if missing:
        raise KeyError(f"unknown species: {', '.join(missing)}")

    beam: list[tuple[tuple[SetCandidate, ...], float]] = [((), 0.0)]
    for name in species:
        variants = generate_set_candidates(records[name], limit=per_species)
        if not variants:
            return []
        expanded: list[tuple[tuple[SetCandidate, ...], float]] = []
        for current, log_score in beam:
            for variant in variants:
                expanded.append(
                    (
                        current + (variant,),
                        log_score + math.log(max(variant.marginal_score, 1e-12)),
                    )
                )
        expanded.sort(key=lambda row: row[1], reverse=True)
        beam = expanded[: max(beam_width, 1)]

    rows = [
        TeamSetCandidate(
            sets=sets,
            marginal_score=math.exp(log_score / max(len(sets), 1)),
        )
        for sets, log_score in beam
    ]
    rows.sort(key=lambda row: row.marginal_score, reverse=True)
    return rows[: max(limit, 1)]


def build_team_export(sets: list[SetCandidate] | tuple[SetCandidate, ...]) -> str:
    return "\n\n".join(candidate.export() for candidate in sets)
