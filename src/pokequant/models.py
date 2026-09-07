from dataclasses import dataclass, field


@dataclass(slots=True)
class ReplaySummary:
    battle_id: str
    format: str | None = None
    upload_time: int | None = None
    players: tuple[str, ...] = ()
    player_ratings: tuple[int | None, ...] = ()
    rating: int | None = None
    winner: str | None = None
    turns: int = 0
    teams: dict[str, set[str]] = field(default_factory=dict)


@dataclass(slots=True)
class PokemonMeta:
    name: str
    usage: float
    raw_count: float = 0.0
    moves: dict[str, float] = field(default_factory=dict)
    items: dict[str, float] = field(default_factory=dict)
    abilities: dict[str, float] = field(default_factory=dict)
    tera_types: dict[str, float] = field(default_factory=dict)
    teammates: dict[str, float] = field(default_factory=dict)
    checks_counters: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class RankedPokemon:
    name: str
    score: float
    usage: float
    versatility: float
    synergy_mass: float


@dataclass(slots=True)
class TeamCandidate:
    members: tuple[str, ...]
    score: float
    usage_score: float
    synergy_score: float
    diversity_score: float
