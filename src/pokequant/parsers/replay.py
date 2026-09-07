import re
from typing import Any

from pokequant.models import ReplaySummary


_SLOT_RE = re.compile(r"^(p[12])[a-c]?:\s*(.+)$")


def _species_from_details(details: str) -> str:
    return details.split(",", 1)[0].strip()


def _preview_species(details: str) -> str:
    species = _species_from_details(details)
    # Showdown can hide a battle-start form behind a wildcard at preview
    # (e.g. Zamazenta-* / Greninja-*). Treat it as the base species identity.
    if species.endswith("-*"):
        species = species[:-2]
    return species


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_replay(payload: dict[str, Any]) -> ReplaySummary:
    battle_id = str(payload.get("id", "unknown"))
    log = str(payload.get("log", ""))
    summary = ReplaySummary(
        battle_id=battle_id,
        format=payload.get("formatid") or payload.get("format"),
        upload_time=_int_or_none(payload.get("uploadtime")),
        rating=_int_or_none(payload.get("rating")),
        teams={"p1": set(), "p2": set()},
    )
    players: dict[str, str] = {}
    ratings: dict[str, int | None] = {}
    preview_teams: dict[str, set[str]] = {"p1": set(), "p2": set()}
    observed_teams: dict[str, set[str]] = {"p1": set(), "p2": set()}

    for line in log.splitlines():
        if not line.startswith("|"):
            continue
        parts = line.split("|")
        event = parts[1] if len(parts) > 1 else ""

        if event == "player" and len(parts) >= 4:
            side = parts[2]
            if side in {"p1", "p2"}:
                if parts[3]:
                    players[side] = parts[3]
                ratings[side] = _int_or_none(parts[5]) if len(parts) >= 6 else None
        elif event in {"switch", "drag", "replace"} and len(parts) >= 4:
            match = _SLOT_RE.match(parts[2])
            if match:
                side = match.group(1)
                observed_teams[side].add(_species_from_details(parts[3]))
        elif event == "poke" and len(parts) >= 4:
            side = parts[2]
            if side in {"p1", "p2"}:
                preview_teams[side].add(_preview_species(parts[3]))
        elif event == "turn" and len(parts) >= 3:
            try:
                summary.turns = max(summary.turns, int(parts[2]))
            except ValueError:
                pass
        elif event == "win" and len(parts) >= 3:
            summary.winner = parts[2]
        elif event == "tie":
            summary.winner = None

    for side in ("p1", "p2"):
        # Preview is the authoritative team identity. Switch events may contain
        # transformations/form changes and are fallback-only for partial logs.
        summary.teams[side] = preview_teams[side] or observed_teams[side]

    payload_players = payload.get("players")
    if isinstance(payload_players, list):
        for idx, side in enumerate(("p1", "p2")):
            if side not in players and idx < len(payload_players):
                value = payload_players[idx]
                if isinstance(value, str) and value:
                    players[side] = value

    summary.players = tuple(players.get(side, "") for side in ("p1", "p2"))
    summary.player_ratings = tuple(ratings.get(side) for side in ("p1", "p2"))

    if summary.rating is None:
        known = [rating for rating in summary.player_ratings if rating is not None]
        # Conservative ladder-quality proxy: both players must meet the threshold
        # when both ratings are present.
        if known:
            summary.rating = min(known)

    return summary
