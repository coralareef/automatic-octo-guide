import json
import urllib.parse
import urllib.request
from typing import Any, Iterator


BASE_REPLAY = "https://replay.pokemonshowdown.com"
BASE_SITE = "https://pokemonshowdown.com"
BASE_PLAY = "https://play.pokemonshowdown.com"
USER_AGENT = "pokequant/0.1 (+https://github.com/coralareef/automatic-octo-guide)"


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
    format: str | None = None,
    limit: int = 100,
) -> Iterator[dict[str, Any]]:
    """Paginate replay search using the documented `before` cursor.

    Showdown returns up to 51 records; if record 51 exists, the first 50
    belong to the current page and another page can be requested.
    """
    yielded = 0
    before: int | None = None
    seen_ids: set[str] = set()
    while yielded < limit:
        page = search_replays(user=user, format=format, before=before)
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
            if yielded >= limit:
                return
        if len(page) <= 50 or not usable:
            break
        last_time = usable[-1].get("uploadtime")
        if last_time is None:
            break
        before = int(last_time)


def get_user(username: str) -> dict[str, Any]:
    userid = "".join(ch for ch in username.lower() if ch.isalnum())
    return _get_json(f"{BASE_SITE}/users/{userid}.json")


def get_ladder(format: str) -> Any:
    return _get_json(f"{BASE_SITE}/ladder/{urllib.parse.quote(format)}.json")


def get_pokedex() -> dict[str, Any]:
    return _get_json(f"{BASE_PLAY}/data/pokedex.json")


def get_moves() -> dict[str, Any]:
    return _get_json(f"{BASE_PLAY}/data/moves.json")
