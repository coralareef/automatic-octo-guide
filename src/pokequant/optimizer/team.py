import itertools
import math
from collections import Counter

from pokequant.analysis.threats import team_threat_coverage
from pokequant.models import PokemonMeta, RankedPokemon, TeamCandidate


def _norm_pair_synergy(a: PokemonMeta, b: PokemonMeta) -> float:
    """Symmetric teammate evidence compressed to a bounded score.

    Chaos teammate values are rating-weighted counts rather than clean
    probabilities in every historical dataset, so V1 uses a monotonic bounded
    transform. Replay-derived lift and simulator results will later supersede
    this prior where sufficient evidence exists.
    """
    ab = max(a.teammates.get(b.name, 0.0), 0.0)
    ba = max(b.teammates.get(a.name, 0.0), 0.0)
    evidence = math.sqrt(ab * ba) if ab and ba else max(ab, ba)
    return 1.0 - math.exp(-evidence / max(a.raw_count + b.raw_count, 1.0))


def _diversity(team: tuple[str, ...], records: dict[str, PokemonMeta]) -> float:
    buckets = Counter()
    for name in team:
        mon = records[name]
        buckets["moves"] += min(len(mon.moves), 8)
        buckets["items"] += min(len(mon.items), 6)
        buckets["tera"] += min(len(mon.tera_types), 6)
    denom = max(len(team), 1)
    return min(
        1.0,
        (buckets["moves"] / (8 * denom)) * 0.5
        + (buckets["items"] / (6 * denom)) * 0.3
        + (buckets["tera"] / (6 * denom)) * 0.2,
    )


def score_team(
    team: tuple[str, ...],
    records: dict[str, PokemonMeta],
    rank_scores: dict[str, float],
    *,
    threat_top_n: int = 30,
) -> TeamCandidate:
    usage_score = sum(rank_scores[name] for name in team) / (100.0 * len(team))
    pairs = list(itertools.combinations(team, 2))
    synergy = (
        sum(_norm_pair_synergy(records[a], records[b]) for a, b in pairs) / len(pairs)
        if pairs
        else 0.0
    )
    diversity = _diversity(team, records)
    threat = team_threat_coverage(team, records, top_n=threat_top_n).score

    # Current metagame strength and observed counter coverage dominate the prior.
    # Synergy and set diversity remain useful tie-breakers until simulator-derived
    # expected win probability becomes the final objective.
    total = 100.0 * (
        0.34 * usage_score
        + 0.20 * synergy
        + 0.08 * diversity
        + 0.38 * threat
    )
    return TeamCandidate(team, total, usage_score, synergy, diversity, threat)


def beam_search(
    records: dict[str, PokemonMeta],
    ranked: list[RankedPokemon],
    *,
    pool_size: int = 40,
    beam_width: int = 250,
    team_size: int = 6,
    threat_top_n: int = 30,
) -> list[TeamCandidate]:
    pool = [r.name for r in ranked[:pool_size] if r.name in records]
    rank_scores = {r.name: r.score for r in ranked}
    beam: list[tuple[str, ...]] = [()]

    for _ in range(team_size):
        candidates: dict[tuple[str, ...], TeamCandidate] = {}
        for partial in beam:
            start = pool.index(partial[-1]) + 1 if partial else 0
            for name in pool[start:]:
                team = partial + (name,)
                scored = score_team(
                    team,
                    records,
                    rank_scores,
                    threat_top_n=threat_top_n,
                )
                candidates[team] = scored
        ordered = sorted(candidates.values(), key=lambda c: c.score, reverse=True)
        beam = [candidate.members for candidate in ordered[:beam_width]]
        if not beam:
            break

    return sorted(
        (
            score_team(
                team,
                records,
                rank_scores,
                threat_top_n=threat_top_n,
            )
            for team in beam
            if len(team) == team_size
        ),
        key=lambda c: c.score,
        reverse=True,
    )
