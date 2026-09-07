from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pokequant.analysis.meta import parse_chaos
from pokequant.config import MetaTarget
from pokequant.models import ReplaySummary

PARSER_VERSION = "0.2.0"

SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta_snapshots(
    id INTEGER PRIMARY KEY,
    month TEXT NOT NULL,
    format TEXT NOT NULL,
    rating INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    info_json TEXT NOT NULL,
    UNIQUE(month, format, rating)
);

CREATE TABLE IF NOT EXISTS pokemon_meta(
    snapshot_id INTEGER NOT NULL REFERENCES meta_snapshots(id) ON DELETE CASCADE,
    pokemon TEXT NOT NULL,
    usage REAL NOT NULL,
    raw_count REAL NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, pokemon)
);

CREATE TABLE IF NOT EXISTS replays(
    battle_id TEXT PRIMARY KEY,
    format TEXT,
    upload_time INTEGER,
    rating INTEGER,
    p1 TEXT,
    p2 TEXT,
    winner TEXT,
    winner_side TEXT,
    turns INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    parser_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_members(
    battle_id TEXT NOT NULL REFERENCES replays(battle_id) ON DELETE CASCADE,
    side TEXT NOT NULL,
    pokemon TEXT NOT NULL,
    PRIMARY KEY(battle_id, side, pokemon)
);

CREATE INDEX IF NOT EXISTS idx_replays_format_time
ON replays(format, upload_time);

CREATE INDEX IF NOT EXISTS idx_replays_rating
ON replays(format, rating);

CREATE INDEX IF NOT EXISTS idx_team_members_pokemon
ON team_members(pokemon);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def store_meta_snapshot(
    conn: sqlite3.Connection,
    target: MetaTarget,
    payload: dict[str, Any],
    retrieved_at: str | None = None,
) -> int:
    retrieved_at = retrieved_at or utcnow()
    records = parse_chaos(payload)
    conn.execute(
        """
        INSERT INTO meta_snapshots(
            month, format, rating, source_url, retrieved_at, parser_version, info_json
        ) VALUES(?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(month, format, rating) DO UPDATE SET
            source_url=excluded.source_url,
            retrieved_at=excluded.retrieved_at,
            parser_version=excluded.parser_version,
            info_json=excluded.info_json
        """,
        (
            target.month,
            target.format,
            target.rating,
            target.chaos_url,
            retrieved_at,
            PARSER_VERSION,
            json.dumps(payload.get("info", {}), sort_keys=True),
        ),
    )
    snapshot_id = int(
        conn.execute(
            "SELECT id FROM meta_snapshots WHERE month=? AND format=? AND rating=?",
            (target.month, target.format, target.rating),
        ).fetchone()["id"]
    )
    conn.execute("DELETE FROM pokemon_meta WHERE snapshot_id=?", (snapshot_id,))
    rows = []
    for mon in records.values():
        detail = {
            "moves": mon.moves,
            "items": mon.items,
            "abilities": mon.abilities,
            "tera_types": mon.tera_types,
            "teammates": mon.teammates,
            "checks_counters": mon.checks_counters,
        }
        rows.append(
            (
                snapshot_id,
                mon.name,
                mon.usage,
                mon.raw_count,
                json.dumps(detail, sort_keys=True),
            )
        )
    conn.executemany(
        "INSERT INTO pokemon_meta(snapshot_id, pokemon, usage, raw_count, data_json) VALUES(?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return snapshot_id


def store_replay(
    conn: sqlite3.Connection,
    summary: ReplaySummary,
    source_url: str,
    retrieved_at: str | None = None,
    rating: int | None = None,
) -> bool:
    if not summary.battle_id or summary.battle_id == "unknown":
        raise ValueError("replay requires battle id")
    retrieved_at = retrieved_at or utcnow()
    players = list(summary.players) + [None, None]
    p1, p2 = players[0], players[1]
    winner_side = (
        "p1"
        if summary.winner and summary.winner == p1
        else "p2"
        if summary.winner and summary.winner == p2
        else None
    )
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO replays(
            battle_id, format, upload_time, rating, p1, p2, winner, winner_side,
            turns, source_url, retrieved_at, parser_version
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            summary.battle_id,
            summary.format,
            summary.upload_time,
            rating,
            p1,
            p2,
            summary.winner,
            winner_side,
            summary.turns,
            source_url,
            retrieved_at,
            PARSER_VERSION,
        ),
    )
    inserted = cur.rowcount > 0
    if inserted:
        conn.executemany(
            "INSERT OR IGNORE INTO team_members(battle_id, side, pokemon) VALUES(?, ?, ?)",
            [
                (summary.battle_id, side, pokemon)
                for side, team in summary.teams.items()
                for pokemon in sorted(team)
            ],
        )
        conn.commit()
    return inserted


def corpus_stats(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "meta_snapshots": conn.execute("SELECT COUNT(*) FROM meta_snapshots").fetchone()[0],
        "pokemon_rows": conn.execute("SELECT COUNT(*) FROM pokemon_meta").fetchone()[0],
        "replays": conn.execute("SELECT COUNT(*) FROM replays").fetchone()[0],
        "team_members": conn.execute("SELECT COUNT(*) FROM team_members").fetchone()[0],
    }
