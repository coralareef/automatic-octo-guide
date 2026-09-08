from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from pokequant.history import time_decay_weight
from pokequant.models import PokemonMeta


@dataclass(slots=True)
class HistoricalPokemon:
    name: str
    weighted_usage: float
    effective_weight: float
    snapshots: int


def weighted_usage(
    conn: sqlite3.Connection,
    *,
    format: str,
    rating: int,
    reference_month: str,
    half_life_months: float = 3.0,
) -> list[HistoricalPokemon]:
    rows = conn.execute(
        """
        SELECT s.month, p.pokemon, p.usage
        FROM pokemon_meta p
        JOIN meta_snapshots s ON p.snapshot_id = s.id
        WHERE s.format=? AND s.rating=? AND s.month<=?
        """,
        (format, rating, reference_month),
    ).fetchall()

    accumulated: dict[str, tuple[float, float, int]] = {}
    for row in rows:
        weight = time_decay_weight(
            row["month"], reference_month, half_life_months
        )
        total, total_weight, count = accumulated.get(
            row["pokemon"], (0.0, 0.0, 0)
        )
        accumulated[row["pokemon"]] = (
            total + weight * float(row["usage"]),
            total_weight + weight,
            count + 1,
        )

    result = [
        HistoricalPokemon(
            name=name,
            weighted_usage=total / total_weight if total_weight else 0.0,
            effective_weight=total_weight,
            snapshots=count,
        )
        for name, (total, total_weight, count) in accumulated.items()
    ]
    return sorted(result, key=lambda row: row.weighted_usage, reverse=True)


def _numeric_mapping(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, raw in value.items():
        try:
            result[str(key)] = float(raw)
        except (TypeError, ValueError):
            continue
    return result


def weighted_meta_records(
    conn: sqlite3.Connection,
    *,
    format: str,
    rating: int,
    reference_month: str,
    half_life_months: float = 3.0,
    min_snapshots: int = 1,
) -> dict[str, PokemonMeta]:
    """Aggregate historical Smogon chaos snapshots into time-decayed records.

    The inputs are battle-derived monthly Pokémon Showdown statistics stored in
    ``pokemon_meta``. Usage is averaged across months with exponential time
    decay. Moves, items, abilities, Tera types, spreads and teammate counts are
    accumulated as decayed evidence. Check/counter estimates are pooled by their
    decayed encounter counts, preserving both within-month uncertainty and
    between-month variation.

    This function is intentionally data-only: it does not add expert opinions,
    sample-team priors or hand-written species bonuses.
    """
    if min_snapshots <= 0:
        raise ValueError("min_snapshots must be > 0")

    rows = conn.execute(
        """
        SELECT s.month, p.pokemon, p.usage, p.raw_count, p.data_json
        FROM pokemon_meta p
        JOIN meta_snapshots s ON p.snapshot_id = s.id
        WHERE s.format=? AND s.rating=? AND s.month<=?
        ORDER BY s.month, p.pokemon
        """,
        (format, rating, reference_month),
    ).fetchall()

    usage_num: dict[str, float] = defaultdict(float)
    usage_den: dict[str, float] = defaultdict(float)
    raw_counts: dict[str, float] = defaultdict(float)
    snapshots: dict[str, int] = defaultdict(int)
    feature_names = (
        "moves",
        "items",
        "abilities",
        "tera_types",
        "spreads",
        "teammates",
    )
    features: dict[str, dict[str, dict[str, float]]] = {
        feature: defaultdict(lambda: defaultdict(float))
        for feature in feature_names
    }
    # pokemon -> answer -> [weighted_n, weighted_n*p, weighted_n*d^2,
    #                        weighted_n*p^2]
    counter_acc: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    )

    for row in rows:
        weight = time_decay_weight(
            row["month"], reference_month, half_life_months
        )
        pokemon = str(row["pokemon"])
        usage_num[pokemon] += weight * max(float(row["usage"]), 0.0)
        usage_den[pokemon] += weight
        raw_counts[pokemon] += weight * max(float(row["raw_count"]), 0.0)
        snapshots[pokemon] += 1

        try:
            detail = json.loads(row["data_json"])
        except (TypeError, json.JSONDecodeError):
            detail = {}
        if not isinstance(detail, dict):
            detail = {}

        for feature in feature_names:
            for key, value in _numeric_mapping(detail.get(feature)).items():
                features[feature][pokemon][key] += weight * max(value, 0.0)

        raw_counters = detail.get("checks_counters", {})
        if not isinstance(raw_counters, dict):
            continue
        for answer, raw in raw_counters.items():
            if not isinstance(raw, dict):
                continue
            try:
                n = max(float(raw.get("n", 0.0)), 0.0)
                p = max(0.0, min(1.0, float(raw.get("p", 0.0))))
                d = max(float(raw.get("d", 0.0)), 0.0)
            except (TypeError, ValueError):
                continue
            if n <= 0:
                continue
            wn = weight * n
            acc = counter_acc[pokemon][str(answer)]
            acc[0] += wn
            acc[1] += wn * p
            acc[2] += wn * d * d
            acc[3] += wn * p * p

    records: dict[str, PokemonMeta] = {}
    for pokemon, count in snapshots.items():
        if count < min_snapshots or usage_den[pokemon] <= 0:
            continue

        checks_counters: dict[str, dict[str, float]] = {}
        for answer, (n, np, nd2, np2) in counter_acc[pokemon].items():
            if n <= 0:
                continue
            p = np / n
            within_var = nd2 / n
            between_var = max(np2 / n - p * p, 0.0)
            checks_counters[answer] = {
                "n": n,
                "p": p,
                "d": math.sqrt(max(within_var + between_var, 0.0)),
            }

        records[pokemon] = PokemonMeta(
            name=pokemon,
            usage=usage_num[pokemon] / usage_den[pokemon],
            raw_count=raw_counts[pokemon],
            moves=dict(features["moves"][pokemon]),
            items=dict(features["items"][pokemon]),
            abilities=dict(features["abilities"][pokemon]),
            tera_types=dict(features["tera_types"][pokemon]),
            spreads=dict(features["spreads"][pokemon]),
            teammates=dict(features["teammates"][pokemon]),
            checks_counters=checks_counters,
        )

    return records
