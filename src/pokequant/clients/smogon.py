import gzip
import json
import urllib.request
from typing import Any

from pokequant.config import MetaTarget


USER_AGENT = "pokequant/0.1 (+https://github.com/coralareef/automatic-octo-guide)"


def get_chaos(target: MetaTarget, timeout: float = 60.0) -> dict[str, Any]:
    req = urllib.request.Request(target.chaos_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = response.read()
    try:
        raw = gzip.decompress(payload)
    except gzip.BadGzipFile:
        raw = payload
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or "data" not in data:
        raise ValueError("Unexpected Smogon chaos payload")
    return data
