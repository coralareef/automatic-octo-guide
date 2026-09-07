import re
from typing import Any

from pokequant.models import ReplaySummary


_SLOT_RE = re.compile(r"^(p[12])[a-c]?:\s*(.+)$")


def _species_from_details(details: str) -> str:
    return details.split(",", 1)[0].strip()


def parse_replay(payload: dict[str, Any]) -> ReplaySummary:
    battle_id = str(payload.get("id", "unknown"))
    log = str(payload.get("log", ""))
    summary = ReplaySummary(
        battle_id=battle_id,
        format=payload.get("format"),
        upload_time=payload.get("uploadtime"),
        teams={"p1": set(), "p2": set()},
    )
    players: dict[str, str] = {}

    for line in log.splitlines():
        if not line.startswith("|"):
            continue
        parts = line.split("|")
        event = parts[1] if len(parts) > 1 else ""

        if event == "player" and len(parts) >= 4:
            players[parts[2]] = parts[3]
        elif event in {"switch", "drag", "replace"} and len(parts) >= 4:
            match = _SLOT_RE.match(parts[2])
            if match:
                side = match.group(1)
                summary.teams.setdefault(side, set()).add(_species_from_details(parts[3]))
        elif event == "poke" and len(parts) >= 4:
            side = parts[2]
            if side in {"p1", "p2"}:
                summary.teams.setdefault(side, set()).add(_species_from_details(parts[3]))
        elif event == "turn" and len(parts) >= 3:
            try:
                summary.turns = max(summary.turns, int(parts[2]))
            except ValueError:
                pass
        elif event == "win" and len(parts) >= 3:
            summary.winner = parts[2]
        elif event == "tie":
            summary.winner = None

    summary.players = tuple(players[key] for key in ("p1", "p2") if key in players)
    return summary
