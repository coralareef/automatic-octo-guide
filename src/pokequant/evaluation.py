from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Callable, Iterable

from pokequant.simulator import SimulationResult


@dataclass(frozen=True, slots=True)
class OpponentTeam:
    name: str
    team: str
    weight: float
    members: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchupEstimate:
    opponent: str
    weight: float
    battles: int
    win_rate: float
    wins: float
    losses: float
    ties: float


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    expected_win: float
    ci_low: float
    ci_high: float
    effective_battles: float
    total_battles: int
    downside_cvar: float
    matchup_std: float
    risk: float
    objective: float
    protocol_errors: int
    matchups: tuple[MatchupEstimate, ...]


Simulator = Callable[..., SimulationResult]


def _normalize_opponents(opponents: Iterable[OpponentTeam]) -> list[OpponentTeam]:
    rows = [row for row in opponents if row.team and row.weight > 0]
    total = sum(row.weight for row in rows)
    if total <= 0:
        return []
    return [
        OpponentTeam(
            name=row.name,
            team=row.team,
            weight=row.weight / total,
            members=row.members,
        )
        for row in rows
    ]


def deterministic_seed(base_seed: int | str, opponent: str, replicate: int) -> str:
    digest = hashlib.sha256(
        f"{base_seed}|{opponent}|{replicate}".encode("utf-8")
    ).digest()
    values = [int.from_bytes(digest[i : i + 2], "big") or 1 for i in range(0, 8, 2)]
    return ",".join(str(value) for value in values)


def _candidate_outcome(result: SimulationResult, candidate_side: str) -> float:
    winner = result.winner.casefold()
    if winner == "tie":
        return 0.5
    if candidate_side == "p1":
        return 1.0 if winner == "p1" else 0.0
    return 1.0 if winner == "p2" else 0.0


def _lower_tail_cvar(
    values: list[float], weights: list[float], alpha: float = 0.20
) -> float:
    if not values:
        return 0.0
    alpha = max(min(alpha, 1.0), 1e-9)
    ranked = sorted(zip(values, weights), key=lambda row: row[0])
    remaining = alpha
    total = 0.0
    used = 0.0
    for value, weight in ranked:
        take = min(max(weight, 0.0), remaining)
        if take > 0:
            total += value * take
            used += take
            remaining -= take
        if remaining <= 1e-12:
            break
    return total / used if used > 0 else min(values)


def evaluate_candidate(
    candidate_team: str,
    opponents: Iterable[OpponentTeam],
    *,
    simulator: Simulator,
    format: str = "gen9ou",
    seeds_per_opponent: int = 4,
    base_seed: int | str = 202608,
    max_turns: int = 1000,
    risk_lambda: float = 0.20,
    cvar_alpha: float = 0.20,
    strict_protocol: bool = True,
) -> EvaluationResult:
    """Evaluate a candidate with paired side-swapped seeded battles.

    Every opponent/seed pair is simulated twice: candidate as P1 and candidate
    as P2. This cancels systematic side/order bias in the battle policy. The
    opponent weights define P(O); each opponent's weight is split evenly across
    its paired simulations. Ties count as half a win.
    """
    rows = _normalize_opponents(opponents)
    if not rows:
        raise ValueError("at least one positive-weight opponent team is required")
    if seeds_per_opponent <= 0:
        raise ValueError("seeds_per_opponent must be positive")

    battle_outcomes: list[float] = []
    battle_weights: list[float] = []
    matchup_rows: list[MatchupEstimate] = []
    protocol_errors = 0

    for opponent in rows:
        outcomes: list[float] = []
        ties = 0.0
        for replicate in range(seeds_per_opponent):
            seed = deterministic_seed(base_seed, opponent.name, replicate)
            for candidate_side in ("p1", "p2"):
                if candidate_side == "p1":
                    p1team, p2team = candidate_team, opponent.team
                else:
                    p1team, p2team = opponent.team, candidate_team
                result = simulator(
                    p1team,
                    p2team,
                    format=format,
                    seed=seed,
                    max_turns=max_turns,
                )
                protocol_errors += int(result.errors)
                if strict_protocol and result.errors:
                    raise RuntimeError(
                        f"simulation protocol error against {opponent.name}: "
                        f"errors={result.errors} seed={seed} side={candidate_side}"
                    )
                outcome = _candidate_outcome(result, candidate_side)
                outcomes.append(outcome)
                if math.isclose(outcome, 0.5):
                    ties += 1
                battle_outcomes.append(outcome)
                battle_weights.append(
                    opponent.weight / (2.0 * seeds_per_opponent)
                )

        games = len(outcomes)
        wins = sum(1.0 for value in outcomes if value > 0.5)
        losses = sum(1.0 for value in outcomes if value < 0.5)
        matchup_rows.append(
            MatchupEstimate(
                opponent=opponent.name,
                weight=opponent.weight,
                battles=games,
                win_rate=sum(outcomes) / games,
                wins=wins,
                losses=losses,
                ties=ties,
            )
        )

    expected = sum(w * x for w, x in zip(battle_weights, battle_outcomes))
    total_weight = sum(battle_weights)
    if not math.isclose(total_weight, 1.0, rel_tol=1e-8, abs_tol=1e-8):
        expected /= total_weight
        battle_weights = [weight / total_weight for weight in battle_weights]

    sum_sq = sum(weight * weight for weight in battle_weights)
    n_eff = 1.0 / sum_sq if sum_sq > 0 else 0.0
    variance = sum(
        weight * (outcome - expected) ** 2
        for weight, outcome in zip(battle_weights, battle_outcomes)
    )
    se = math.sqrt(max(variance, 0.0) / max(n_eff, 1.0))
    ci_low = max(0.0, expected - 1.96 * se)
    ci_high = min(1.0, expected + 1.96 * se)

    matchup_values = [row.win_rate for row in matchup_rows]
    matchup_weights = [row.weight for row in matchup_rows]
    cvar = _lower_tail_cvar(matchup_values, matchup_weights, cvar_alpha)
    matchup_var = sum(
        weight * (value - expected) ** 2
        for weight, value in zip(matchup_weights, matchup_values)
    )
    matchup_std = math.sqrt(max(matchup_var, 0.0))
    downside_gap = max(0.0, expected - cvar)
    risk = 0.60 * downside_gap + 0.40 * matchup_std
    objective = expected - max(risk_lambda, 0.0) * risk

    matchup_rows.sort(key=lambda row: row.win_rate)
    return EvaluationResult(
        expected_win=expected,
        ci_low=ci_low,
        ci_high=ci_high,
        effective_battles=n_eff,
        total_battles=len(battle_outcomes),
        downside_cvar=cvar,
        matchup_std=matchup_std,
        risk=risk,
        objective=objective,
        protocol_errors=protocol_errors,
        matchups=tuple(matchup_rows),
    )
