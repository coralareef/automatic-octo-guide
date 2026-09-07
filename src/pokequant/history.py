from __future__ import annotations

from datetime import date
import math


def parse_month(value: str) -> date:
    year, month = map(int, value.split("-"))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid month: {value}")
    return date(year, month, 1)


def month_index(value: str) -> int:
    d = parse_month(value)
    return d.year * 12 + d.month - 1


def month_range(start: str, end: str) -> list[str]:
    a, b = month_index(start), month_index(end)
    if a > b:
        raise ValueError("start month must be <= end month")
    out: list[str] = []
    for idx in range(a, b + 1):
        year, month0 = divmod(idx, 12)
        out.append(f"{year:04d}-{month0 + 1:02d}")
    return out


def time_decay_weight(
    observation_month: str,
    reference_month: str,
    half_life_months: float = 3.0,
) -> float:
    if half_life_months <= 0:
        raise ValueError("half_life_months must be > 0")
    age = month_index(reference_month) - month_index(observation_month)
    if age < 0:
        raise ValueError("observation month cannot be after reference month")
    return math.pow(0.5, age / half_life_months)
