from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pokequant.models import PokemonMeta


@dataclass(frozen=True, slots=True)
class CounterEvidence:
    threat: str
    answer: str
    threat_usage: float
    encounters: float
    probability: float
    deviation: float
    posterior_probability: float
    robust_probability: float


@dataclass(frozen=True, slots=True)
class ThreatCoverage:
    threat: str
    usage: float
    best_answer: str | None
    best_score: float
    second_answer: str | None
    second_score: float
    combined_score: float


@dataclass(frozen=True, slots=True)
class TeamThreatCoverage:
    members: tuple[str, ...]
    score: float
    uncovered_usage_mass: float
    threats: tuple[ThreatCoverage, ...]


@dataclass(frozen=True, slots=True)
class AnswerCoverage:
    answer: str
    score: float
    covered_usage_mass: float
    strong_matchups: int


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def counter_evidence(
    threat: PokemonMeta,
    answer: str,
    *,
    prior_strength: float = 20.0,
    z: float = 1.0,
) -> CounterEvidence | None:
    """Return confidence-adjusted Smogon check/counter evidence.

    Smogon chaos stores, for each listed answer, weighted encounter count ``n``,
    the fraction ``p`` where that answer KOed or forced out the subject, and
    standard deviation ``d`` for that fraction. V1 shrinks p toward 0.5 and
    subtracts a configurable uncertainty penalty. Missing evidence contributes
    zero coverage rather than being treated as a neutral matchup.
    """
    raw = threat.checks_counters.get(answer)
    if not isinstance(raw, dict):
        return None
    try:
        n = max(float(raw.get("n", 0.0)), 0.0)
        p = _clamp(float(raw.get("p", 0.0)))
        d = max(float(raw.get("d", 0.0)), 0.0)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None

    prior = max(prior_strength, 0.0)
    posterior = (n * p + prior * 0.5) / (n + prior) if n + prior else 0.5
    evidence_fraction = n / (n + prior) if n + prior else 0.0
    robust = _clamp(posterior - max(z, 0.0) * d * evidence_fraction)
    return CounterEvidence(
        threat=threat.name,
        answer=answer,
        threat_usage=max(threat.usage, 0.0),
        encounters=n,
        probability=p,
        deviation=d,
        posterior_probability=posterior,
        robust_probability=robust,
    )


def _threat_pool(
    records: dict[str, PokemonMeta],
    *,
    top_n: int = 30,
    min_usage: float = 0.0,
) -> list[PokemonMeta]:
    threats = [m for m in records.values() if m.usage >= min_usage]
    threats.sort(key=lambda m: m.usage, reverse=True)
    return threats[: max(top_n, 0)]


def team_threat_coverage(
    members: Iterable[str],
    records: dict[str, PokemonMeta],
    *,
    top_n: int = 30,
    min_usage: float = 0.0,
    prior_strength: float = 20.0,
    z: float = 1.0,
    redundancy_weight: float = 0.25,
    uncovered_threshold: float = 0.55,
) -> TeamThreatCoverage:
    team = tuple(dict.fromkeys(str(name) for name in members))
    threats = _threat_pool(records, top_n=top_n, min_usage=min_usage)
    total_usage = sum(max(mon.usage, 0.0) for mon in threats)
    if total_usage <= 0:
        return TeamThreatCoverage(team, 0.0, 0.0, ())

    rows: list[ThreatCoverage] = []
    weighted_score = 0.0
    uncovered_mass = 0.0
    redundancy = _clamp(redundancy_weight)

    for threat in threats:
        scored: list[tuple[str, float]] = []
        for answer in team:
            ev = counter_evidence(
                threat,
                answer,
                prior_strength=prior_strength,
                z=z,
            )
            if ev is not None:
                scored.append((answer, ev.robust_probability))
        scored.sort(key=lambda row: row[1], reverse=True)
        best_answer, best = scored[0] if scored else (None, 0.0)
        second_answer, second = scored[1] if len(scored) > 1 else (None, 0.0)
        # Redundancy only fills a fraction of the remaining gap to perfect coverage.
        combined = _clamp(best + redundancy * (1.0 - best) * second)
        weight = max(threat.usage, 0.0) / total_usage
        weighted_score += weight * combined
        if best < uncovered_threshold:
            uncovered_mass += weight
        rows.append(
            ThreatCoverage(
                threat=threat.name,
                usage=threat.usage,
                best_answer=best_answer,
                best_score=best,
                second_answer=second_answer,
                second_score=second,
                combined_score=combined,
            )
        )

    rows.sort(key=lambda row: row.usage, reverse=True)
    return TeamThreatCoverage(
        members=team,
        score=_clamp(weighted_score),
        uncovered_usage_mass=_clamp(uncovered_mass),
        threats=tuple(rows),
    )


def rank_counter_answers(
    records: dict[str, PokemonMeta],
    *,
    top_n_threats: int = 30,
    min_usage: float = 0.0,
    prior_strength: float = 20.0,
    z: float = 1.0,
    strong_threshold: float = 0.60,
) -> list[AnswerCoverage]:
    threats = _threat_pool(records, top_n=top_n_threats, min_usage=min_usage)
    total_usage = sum(max(mon.usage, 0.0) for mon in threats)
    if total_usage <= 0:
        return []

    rows: list[AnswerCoverage] = []
    for answer in records:
        score = 0.0
        covered = 0.0
        strong = 0
        for threat in threats:
            weight = max(threat.usage, 0.0) / total_usage
            ev = counter_evidence(
                threat,
                answer,
                prior_strength=prior_strength,
                z=z,
            )
            robust = ev.robust_probability if ev is not None else 0.0
            score += weight * robust
            if robust >= strong_threshold:
                covered += weight
                strong += 1
        rows.append(
            AnswerCoverage(
                answer=answer,
                score=_clamp(score),
                covered_usage_mass=_clamp(covered),
                strong_matchups=strong,
            )
        )
    return sorted(rows, key=lambda row: (row.score, row.covered_usage_mass), reverse=True)
