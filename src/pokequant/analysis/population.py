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


def team_swap_distance(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    """Number of roster slots that would need replacing to turn one team into another."""
    return max(len(a), len(b)) - len(set(a) & set(b))


def _select_diverse_prototypes(
    teams: list[tuple[str, ...]],
    probabilities: list[float],
    *,
    top: int,
    min_swaps: int,
    diversity_strength: float,
) -> list[int]:
    if not teams or top <= 0:
        return []
    selected = [0]
    remaining = set(range(1, len(teams)))
    while remaining and len(selected) < top:
        distances = {
            idx: min(team_swap_distance(teams[idx], teams[j]) for j in selected)
            for idx in remaining
        }
        threshold = max(min_swaps, 0)
        eligible = [idx for idx in remaining if distances[idx] >= threshold]
        while not eligible and threshold > 0:
            threshold -= 1
            eligible = [idx for idx in remaining if distances[idx] >= threshold]
        if not eligible:
            eligible = list(remaining)

        def merit(idx: int) -> float:
            distance_fraction = distances[idx] / max(len(teams[idx]), 1)
            return _safe_log(probabilities[idx]) + max(diversity_strength, 0.0) * distance_fraction

        chosen = max(eligible, key=merit)
        selected.append(chosen)
        remaining.remove(chosen)
    return selected


def _cluster_probability_mass(
    teams: list[tuple[str, ...]],
    probabilities: list[float],
    prototypes: list[int],
) -> dict[int, float]:
    masses = {idx: 0.0 for idx in prototypes}
    for team_idx, team in enumerate(teams):
        # Nearest roster prototype wins; ties go to the more probable prototype.
        chosen = min(
            prototypes,
            key=lambda idx: (
                team_swap_distance(team, teams[idx]),
                -probabilities[idx],
                idx,
            ),
        )
        masses[chosen] += probabilities[team_idx]
    return masses


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
    candidate_multiplier: int = 10,
    min_prototype_swaps: int = 2,
    diversity_strength: float = 1.25,
) -> list[OpponentArchetype]:
    """Create coherent, diverse opponent proposals from Smogon chaos.

    A broad high-probability beam is generated first. Instead of returning the
    top-N near-duplicates, we select diverse roster prototypes and assign the
    probability mass of every retained team to its nearest prototype. This keeps
    the proposal distribution concentrated on current usage/teammate evidence
    while preventing one common core from consuming the entire simulation suite.
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

    candidate_count = min(
        len(beam),
        max(top, top * max(candidate_multiplier, 1)),
    )
    finalists = beam[:candidate_count]
    scored = [score_cache[team] for team in finalists]
    max_score = max(score for score, _, _ in scored)
    temp = max(temperature, 1e-6)
    raw_weights = [math.exp((score - max_score) / temp) for score, _, _ in scored]
    total_weight = sum(raw_weights) or 1.0
    probabilities = [weight / total_weight for weight in raw_weights]

    prototype_indices = _select_diverse_prototypes(
        finalists,
        probabilities,
        top=min(top, len(finalists)),
        min_swaps=min_prototype_swaps,
        diversity_strength=diversity_strength,
    )
    cluster_mass = _cluster_probability_mass(finalists, probabilities, prototype_indices)

    rows = [
        OpponentArchetype(
            members=finalists[idx],
            score=scored[idx][0],
            proposal_probability=cluster_mass[idx],
            usage_component=scored[idx][1],
            association_component=scored[idx][2],
        )
        for idx in prototype_indices
    ]
    rows.sort(key=lambda row: row.proposal_probability, reverse=True)
    total = sum(row.proposal_probability for row in rows) or 1.0
    return [
        OpponentArchetype(
            members=row.members,
            score=row.score,
            proposal_probability=row.proposal_probability / total,
            usage_component=row.usage_component,
            association_component=row.association_component,
        )
        for row in rows
    ]
