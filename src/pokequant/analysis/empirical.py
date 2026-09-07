from __future__ import annotations

import itertools
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PokemonOutcome:
    name: str
    appearances: int
    wins: int
    losses: int
    posterior_win_rate: float
    ci_low: float
    ci_high: float


@dataclass(frozen=True, slots=True)
class PairSynergy:
    a: str
    b: str
    team_appearances: int
    a_appearances: int
    b_appearances: int
    team_observations: int
    raw_lift: float
    pmi: float
    shrunk_pmi: float
    pair_decisive_games: int
    pair_wins: int
    pair_posterior_win_rate: float
    pair_ci_low: float
    pair_ci_high: float


@dataclass(frozen=True, slots=True)
class MatchupEstimate:
    attacker: str
    defender: str
    observations: int
    wins: int
    losses: int
    posterior_win_rate: float
    ci_low: float
    ci_high: float


def wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 1.0)
    p = wins / total
    z2 = z * z
    denom = 1.0 + z2 / total
    centre = (p + z2 / (2.0 * total)) / denom
    half = z * math.sqrt(
        (p * (1.0 - p) / total) + z2 / (4.0 * total * total)
    ) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _battle_rows(
    conn: sqlite3.Connection,
    *,
    format: str,
    min_rating: int | None = None,
) -> list[sqlite3.Row]:
    if min_rating is None:
        return conn.execute(
            """
            SELECT battle_id, rating, winner_side
            FROM replays
            WHERE format=?
            """,
            (format,),
        ).fetchall()
    return conn.execute(
        """
        SELECT battle_id, rating, winner_side
        FROM replays
        WHERE format=? AND rating>=?
        """,
        (format, min_rating),
    ).fetchall()


def _teams_for_battles(
    conn: sqlite3.Connection,
    battle_ids: list[str],
) -> dict[str, dict[str, set[str]]]:
    teams: dict[str, dict[str, set[str]]] = {
        battle_id: {"p1": set(), "p2": set()} for battle_id in battle_ids
    }
    if not battle_ids:
        return teams
    # SQLite commonly defaults to 999 variables; batch below that limit.
    for start in range(0, len(battle_ids), 800):
        batch = battle_ids[start : start + 800]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"""
            SELECT battle_id, side, pokemon
            FROM team_members
            WHERE battle_id IN ({placeholders})
            """,
            batch,
        ).fetchall()
        for row in rows:
            teams[row["battle_id"]].setdefault(row["side"], set()).add(
                row["pokemon"]
            )
    return teams


def pokemon_outcomes(
    conn: sqlite3.Connection,
    *,
    format: str,
    min_rating: int | None = None,
    prior_strength: float = 12.0,
    prior_mean: float = 0.5,
) -> list[PokemonOutcome]:
    battles = _battle_rows(conn, format=format, min_rating=min_rating)
    teams = _teams_for_battles(conn, [row["battle_id"] for row in battles])
    appearances: dict[str, int] = defaultdict(int)
    wins: dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)

    for battle in battles:
        winner_side = battle["winner_side"]
        if winner_side not in {"p1", "p2"}:
            continue
        for side in ("p1", "p2"):
            for pokemon in teams[battle["battle_id"]][side]:
                appearances[pokemon] += 1
                if side == winner_side:
                    wins[pokemon] += 1
                else:
                    losses[pokemon] += 1

    result = []
    for pokemon, n in appearances.items():
        posterior = (wins[pokemon] + prior_strength * prior_mean) / (
            n + prior_strength
        )
        ci_low, ci_high = wilson_interval(wins[pokemon], n)
        result.append(
            PokemonOutcome(
                name=pokemon,
                appearances=n,
                wins=wins[pokemon],
                losses=losses[pokemon],
                posterior_win_rate=posterior,
                ci_low=ci_low,
                ci_high=ci_high,
            )
        )
    return sorted(
        result,
        key=lambda row: (row.posterior_win_rate, row.appearances),
        reverse=True,
    )


def pair_synergies(
    conn: sqlite3.Connection,
    *,
    format: str,
    min_rating: int | None = None,
    min_pair_appearances: int = 2,
    pmi_shrinkage: float = 8.0,
    win_prior_strength: float = 12.0,
) -> list[PairSynergy]:
    battles = _battle_rows(conn, format=format, min_rating=min_rating)
    teams = _teams_for_battles(conn, [row["battle_id"] for row in battles])

    mon_counts: dict[str, int] = defaultdict(int)
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    pair_decisive: dict[tuple[str, str], int] = defaultdict(int)
    pair_wins: dict[tuple[str, str], int] = defaultdict(int)
    team_observations = 0

    for battle in battles:
        winner_side = battle["winner_side"]
        for side in ("p1", "p2"):
            team = sorted(teams[battle["battle_id"]][side])
            if not team:
                continue
            team_observations += 1
            for pokemon in team:
                mon_counts[pokemon] += 1
            for a, b in itertools.combinations(team, 2):
                pair_counts[(a, b)] += 1
                if winner_side in {"p1", "p2"}:
                    pair_decisive[(a, b)] += 1
                    if winner_side == side:
                        pair_wins[(a, b)] += 1

    result = []
    for (a, b), n_ab in pair_counts.items():
        if n_ab < min_pair_appearances:
            continue
        n_a = mon_counts[a]
        n_b = mon_counts[b]
        if not team_observations or not n_a or not n_b:
            continue
        raw_lift = (n_ab * team_observations) / (n_a * n_b)
        pmi = math.log(max(raw_lift, 1e-12))
        shrink = (
            n_ab / (n_ab + pmi_shrinkage)
            if pmi_shrinkage > 0
            else 1.0
        )
        shrunk_pmi = pmi * shrink
        decisive = pair_decisive[(a, b)]
        wins = pair_wins[(a, b)]
        posterior_win = (
            (wins + 0.5 * win_prior_strength)
            / (decisive + win_prior_strength)
            if decisive + win_prior_strength > 0
            else 0.5
        )
        ci_low, ci_high = wilson_interval(wins, decisive)
        result.append(
            PairSynergy(
                a=a,
                b=b,
                team_appearances=n_ab,
                a_appearances=n_a,
                b_appearances=n_b,
                team_observations=team_observations,
                raw_lift=raw_lift,
                pmi=pmi,
                shrunk_pmi=shrunk_pmi,
                pair_decisive_games=decisive,
                pair_wins=wins,
                pair_posterior_win_rate=posterior_win,
                pair_ci_low=ci_low,
                pair_ci_high=ci_high,
            )
        )
    return sorted(
        result,
        key=lambda row: (row.shrunk_pmi, row.team_appearances),
        reverse=True,
    )


def matchup_matrix(
    conn: sqlite3.Connection,
    *,
    format: str,
    min_rating: int | None = None,
    min_observations: int = 2,
    prior_strength: float = 6.0,
) -> list[MatchupEstimate]:
    battles = _battle_rows(conn, format=format, min_rating=min_rating)
    teams = _teams_for_battles(conn, [row["battle_id"] for row in battles])
    wins: dict[tuple[str, str], int] = defaultdict(int)
    losses: dict[tuple[str, str], int] = defaultdict(int)

    for battle in battles:
        winner_side = battle["winner_side"]
        if winner_side not in {"p1", "p2"}:
            continue
        loser_side = "p2" if winner_side == "p1" else "p1"
        winner_team = teams[battle["battle_id"]][winner_side]
        loser_team = teams[battle["battle_id"]][loser_side]
        for winner in winner_team:
            for loser in loser_team:
                if winner == loser:
                    continue
                wins[(winner, loser)] += 1
                losses[(loser, winner)] += 1

    keys = set(wins) | set(losses)
    result = []
    for attacker, defender in keys:
        w = wins[(attacker, defender)]
        l = losses[(attacker, defender)]
        n = w + l
        if n < min_observations:
            continue
        posterior = (w + 0.5 * prior_strength) / (n + prior_strength)
        ci_low, ci_high = wilson_interval(w, n)
        result.append(
            MatchupEstimate(
                attacker=attacker,
                defender=defender,
                observations=n,
                wins=w,
                losses=l,
                posterior_win_rate=posterior,
                ci_low=ci_low,
                ci_high=ci_high,
            )
        )
    return sorted(
        result,
        key=lambda row: (row.posterior_win_rate, row.observations),
        reverse=True,
    )
