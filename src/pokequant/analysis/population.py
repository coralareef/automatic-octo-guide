from __future__ import annotations

import math
from dataclasses import dataclass

from pokequant.models import PokemonMeta


@dataclass(frozen=True, slots=True)
class OpponentArchetype:
    members: tuple[str, ...]
    score: float
    proposal_probability: float
    usage_component: float
    association_component: float


def _safe_log(value: float, floor: float = 1e-9) -> float:
    return math.log(max(value, floor))


def _usage_probabilities(
    records: dict[str, PokemonMeta],
    pool: list[str],
) -> dict[str, float]:
    total = sum(max(records[name].usage, 0.0) for name in pool)
    if total <= 0:
        uniform = 1.0 / max(len(pool), 1)
        return {name: uniform for name in pool}
    return {name: max(records[name].usage, 0.0) / total for name in pool}


def pair_association(a: PokemonMeta, b: PokemonMeta) -> float:
    """Return a bounded teammate-association proposal score in [0, 1].

    Smogon teammate values are weighted counts, so they are not interpreted as
    literal conditional probabilities. Each direction is normalized against the
    strongest teammate signal for that Pokémon and combined geometrically when
    both directions exist. Missing evidence receives a small floor later rather
    than being interpreted as an anti-synergy observation.
    """
    ab = max(float(a.teammates.get(b.name, 0.0) or 0.0), 0.0)
    ba = max(float(b.teammates.get(a.name, 0.0) or 0.0), 0.0)
    max_a = max((max(float(v), 0.0) for v in a.teammates.values()), default=0.0)
    max_b = max((max(float(v), 0.0) for v in b.teammates.values()), default=0.0)
    norm_ab = ab / max_a if max_a > 0 else 0.0
    norm_ba = ba / max_b if max_b > 0 else 0.0
    if norm_ab > 0 and norm_ba > 0:
        return max(0.0, min(1.0, math.sqrt(norm_ab * norm_ba)))
    return max(0.0, min(1.0, max(norm_ab, norm_ba)))


def _components(
    team: tuple[str, ...],
    records: dict[str, PokemonMeta],
    usage_probs: dict[str, float],
    *,
    association_floor: float,
) -> tuple[float, float]:
    if not team:
        return 0.0, 0.0
    usage = sum(_safe_log(usage_probs[name]) for name in team) / len(team)
    if len(team) == 1:
        return usage, 0.0
    pair_logs: list[float] = []
    for idx, a in enumerate(team):
        for b in team[idx + 1 :]:
            pair_logs.append(
                _safe_log(max(pair_association(records[a], records[b]), association_floor))
            )
    association = sum(pair_logs) / len(pair_logs) if pair_logs else 0.0
    return usage, association


def generate_opponent_population(
    records: dict[str, PokemonMeta],
    *,
    pool_size: int = 50,
    beam_width: int = 600,
    team_size: int = 6,
    top: int = 40,
    usage_weight: float = 0.72,
    association_weight: float = 0.28,
    association_floor: float = 0.02,
    temperature: float = 0.18,
) -> list[OpponentArchetype]:
    """Create coherent high-probability opponent proposals from Smogon chaos.

    This is a proposal distribution for simulation coverage, not a claim that
    Smogon teammate marginals uniquely identify the true joint distribution.
    We blend current usage with normalized pairwise teammate association, keep a
    wide beam, then softmax the retained archetypes into reproducible weights.
    """
    if team_size <= 0 or top <= 0:
        return []
    pool = [
        mon.name
        for mon in sorted(records.values(), key=lambda m: m.usage, reverse=True)
        if mon.usage > 0
    ][: max(pool_size, team_size)]
    if len(pool) < team_size:
        return []

    usage_probs = _usage_probabilities(records, pool)
    uw = max(usage_weight, 0.0)
    aw = max(association_weight, 0.0)
    denom = uw + aw or 1.0
    uw /= denom
    aw /= denom

    beam: list[tuple[str, ...]] = [()]
    score_cache: dict[tuple[str, ...], tuple[float, float, float]] = {}
    pool_index = {name: idx for idx, name in enumerate(pool)}

    for _ in range(team_size):
        expanded: list[tuple[float, tuple[str, ...]]] = []
        for partial in beam:
            start = pool_index[partial[-1]] + 1 if partial else 0
            for name in pool[start:]:
                team = partial + (name,)
                usage, association = _components(
                    team,
                    records,
                    usage_probs,
                    association_floor=association_floor,
                )
                score = uw * usage + aw * association
                score_cache[team] = (score, usage, association)
                expanded.append((score, team))
        expanded.sort(key=lambda row: row[0], reverse=True)
        beam = [team for _, team in expanded[: max(beam_width, 1)]]
        if not beam:
            return []

    finalists = beam[: max(top, 1)]
    scored = [score_cache[team] for team in finalists]
    max_score = max(score for score, _, _ in scored)
    temp = max(temperature, 1e-6)
    weights = [math.exp((score - max_score) / temp) for score, _, _ in scored]
    total_weight = sum(weights) or 1.0

    rows = [
        OpponentArchetype(
            members=team,
            score=scored[idx][0],
            proposal_probability=weights[idx] / total_weight,
            usage_component=scored[idx][1],
            association_component=scored[idx][2],
        )
        for idx, team in enumerate(finalists)
    ]
    return rows
