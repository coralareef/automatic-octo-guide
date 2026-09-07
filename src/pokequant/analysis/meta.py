import math
from typing import Any

from pokequant.models import PokemonMeta, RankedPokemon


def _mapping(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, raw in value.items():
        try:
            out[str(key)] = float(raw)
        except (TypeError, ValueError):
            continue
    return out


def parse_chaos(payload: dict[str, Any]) -> dict[str, PokemonMeta]:
    records: dict[str, PokemonMeta] = {}
    for name, row in payload.get("data", {}).items():
        if not isinstance(row, dict):
            continue
        usage = float(row.get("usage", row.get("Usage", 0.0)) or 0.0)
        raw = float(row.get("Raw count", row.get("raw_count", 0.0)) or 0.0)
        records[str(name)] = PokemonMeta(
            name=str(name),
            usage=usage,
            raw_count=raw,
            moves=_mapping(row.get("Moves")),
            items=_mapping(row.get("Items")),
            abilities=_mapping(row.get("Abilities")),
            tera_types=_mapping(row.get("Tera Types")),
            spreads=_mapping(row.get("Spreads")),
            teammates=_mapping(row.get("Teammates")),
            checks_counters=row.get("Checks and Counters", {})
            if isinstance(row.get("Checks and Counters", {}), dict)
            else {},
        )
    return records


def _entropy(values: dict[str, float], top_n: int = 12) -> float:
    positive = sorted((v for v in values.values() if v > 0), reverse=True)[:top_n]
    total = sum(positive)
    if total <= 0 or len(positive) <= 1:
        return 0.0
    probs = [v / total for v in positive]
    entropy = -sum(p * math.log(p) for p in probs if p > 0)
    return entropy / math.log(len(probs))


def _robust_scale(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if math.isclose(lo, hi):
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def rank_pokemon(records: dict[str, PokemonMeta]) -> list[RankedPokemon]:
    mons = list(records.values())
    usage_scaled = _robust_scale([math.log1p(max(m.usage, 0.0)) for m in mons])
    synergy_raw = [sum(max(v, 0.0) for v in m.teammates.values()) for m in mons]
    synergy_scaled = _robust_scale([math.log1p(v) for v in synergy_raw])

    ranked: list[RankedPokemon] = []
    for idx, mon in enumerate(mons):
        versatility = (
            0.40 * _entropy(mon.moves)
            + 0.25 * _entropy(mon.items)
            + 0.15 * _entropy(mon.tera_types)
            + 0.10 * _entropy(mon.abilities)
            + 0.10 * _entropy(mon.spreads)
        )
        score = 100.0 * (
            0.68 * usage_scaled[idx]
            + 0.20 * synergy_scaled[idx]
            + 0.12 * versatility
        )
        ranked.append(
            RankedPokemon(
                name=mon.name,
                score=score,
                usage=mon.usage,
                versatility=versatility,
                synergy_mass=synergy_raw[idx],
            )
        )
    return sorted(ranked, key=lambda x: x.score, reverse=True)
