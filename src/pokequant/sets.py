from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from pokequant.models import PokemonMeta


_STAT_NAMES = ("HP", "Atk", "Def", "SpA", "SpD", "Spe")


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
    pool_size: int = 7,
    keep: int = 12,
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
    top_items: int = 4,
    top_abilities: int = 2,
    top_teras: int = 4,
    top_spreads: int = 4,
    move_pool: int = 7,
    move_sets: int = 12,
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
