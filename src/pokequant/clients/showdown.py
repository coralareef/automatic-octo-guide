import json
import time
import urllib.parse
import urllib.request
from typing import Any, Iterator


BASE_REPLAY = "https://replay.pokemonshowdown.com"
BASE_SITE = "https://pokemonshowdown.com"
BASE_PLAY = "https://play.pokemonshowdown.com"
USER_AGENT = "pokequant/0.2 (+https://github.com/coralareef/automatic-octo-guide)"


def _get_json(url: str, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_replay(battle_id: str) -> dict[str, Any]:
    return _get_json(f"{BASE_REPLAY}/{urllib.parse.quote(battle_id)}.json")


def search_replays(
    *,
    user: str | None = None,
    user2: str | None = None,
    format: str | None = None,
    before: int | None = None,
) -> list[dict[str, Any]]:
    params: list[tuple[str, str]] = []
    if user:
        params.append(("user", user))
    if user2:
        params.append(("user2", user2))
    if format:
        params.append(("format", format))
    if before is not None:
        params.append(("before", str(before)))
    query = urllib.parse.urlencode(params)
    suffix = f"?{query}" if query else ""
    result = _get_json(f"{BASE_REPLAY}/search.json{suffix}")
    if not isinstance(result, list):
        raise ValueError("Unexpected replay search response")
    return result


def iter_replays(
    *,
    user: str | None = None,
    user2: str | None = None,
    format: str | None = None,
    limit: int | None = 100,
    sleep_seconds: float = 0.0,
) -> Iterator[dict[str, Any]]:
    """Paginate replay search using Showdown's documented `before` cursor.

    Showdown searches are limited to 51 results. The first 50 are the current
    page; the 51st establishes that another page exists. The API documentation
    says to use the uploadtime of the last result as the next cursor.
    """
    yielded = 0
    before: int | None = None
    seen_ids: set[str] = set()

    while limit is None or yielded < limit:
        page = search_replays(
            user=user,
            user2=user2,
            format=format,
            before=before,
        )
        if not page:
            break

        usable = page[:50]
        for replay in usable:
            replay_id = str(replay.get("id", ""))
            if not replay_id or replay_id in seen_ids:
                continue
            seen_ids.add(replay_id)
            yield replay
            yielded += 1
            if limit is not None and yielded >= limit:
                return

        if len(page) <= 50 or not usable:
            break

        cursor = page[-1].get("uploadtime")
        if cursor is None:
            break
        next_before = int(cursor)
        if before is not None and next_before >= before:
            next_before = before - 1
        before = next_before

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)


def get_user(username: str) -> dict[str, Any]:
    userid = "".join(ch for ch in username.lower() if ch.isalnum())
    return _get_json(f"{BASE_SITE}/users/{userid}.json")


def get_ladder(format: str) -> Any:
    return _get_json(f"{BASE_SITE}/ladder/{urllib.parse.quote(format)}.json")


def get_pokedex() -> dict[str, Any]:
    return _get_json(f"{BASE_PLAY}/data/pokedex.json")


def get_moves() -> dict[str, Any]:
    return _get_json(f"{BASE_PLAY}/data/moves.json")
