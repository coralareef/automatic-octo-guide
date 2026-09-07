from __future__ import annotations

import time
import urllib.error
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from pokequant.clients.showdown import BASE_REPLAY, get_replay, iter_replays
from pokequant.clients.smogon import get_chaos
from pokequant.config import MetaTarget
from pokequant.history import month_range
from pokequant.parsers.replay import parse_replay
from pokequant.storage import connect, store_meta_snapshot, store_replay


def ingest_meta_history(
    db_path: str | Path,
    *,
    start: str,
    end: str,
    format: str = "gen9ou",
    rating: int = 1825,
    fetcher: Callable[[MetaTarget], dict[str, Any]] = get_chaos,
) -> dict[str, int]:
    conn = connect(db_path)
    stored = 0
    missing = 0
    failed = 0
    try:
        for month in month_range(start, end):
            target = MetaTarget(month=month, format=format, rating=rating)
            try:
                payload = fetcher(target)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    missing += 1
                    continue
                failed += 1
                continue
            except Exception:
                failed += 1
                continue
            store_meta_snapshot(conn, target, payload)
            stored += 1
    finally:
        conn.close()
    return {"stored": stored, "missing": missing, "failed": failed}


def ingest_replay_corpus(
    db_path: str | Path,
    *,
    user: str | None = None,
    user2: str | None = None,
    format: str | None = "gen9ou",
    limit: int | None = None,
    sleep_seconds: float = 0.0,
    search_iter: Callable[..., Iterator[dict[str, Any]]] = iter_replays,
    replay_fetcher: Callable[[str], dict[str, Any]] = get_replay,
) -> dict[str, int]:
    conn = connect(db_path)
    discovered = 0
    inserted = 0
    duplicates = 0
    failed = 0
    try:
        for stub in search_iter(
            user=user,
            user2=user2,
            format=format,
            limit=limit,
            sleep_seconds=sleep_seconds,
        ):
            discovered += 1
            replay_id = str(stub.get("id", ""))
            if not replay_id:
                failed += 1
                continue
            if conn.execute(
                "SELECT 1 FROM replays WHERE battle_id=?", (replay_id,)
            ).fetchone():
                duplicates += 1
                continue
            try:
                summary = parse_replay(replay_fetcher(replay_id))
            except Exception:
                failed += 1
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                continue
            raw_rating = stub.get("rating")
            try:
                rating = int(raw_rating) if raw_rating is not None else None
            except (TypeError, ValueError):
                rating = None
            if store_replay(
                conn,
                summary,
                f"{BASE_REPLAY}/{replay_id}.json",
                rating=rating,
            ):
                inserted += 1
            else:
                duplicates += 1
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    finally:
        conn.close()
    return {
        "discovered": discovered,
        "inserted": inserted,
        "duplicates": duplicates,
        "failed": failed,
    }
