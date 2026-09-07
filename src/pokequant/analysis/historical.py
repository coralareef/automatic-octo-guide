from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pokequant.history import time_decay_weight


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
