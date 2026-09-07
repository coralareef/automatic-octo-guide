from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ValidationResult:
    format: str
    valid: bool
    problems: tuple[str, ...]
    packed: str
    export: str
    pokemon: tuple[str, ...]


def validate_team(
    team: str,
    *,
    format: str = "gen9ou",
    repo_root: str | Path | None = None,
    node: str = "node",
    timeout: float = 30.0,
) -> ValidationResult:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    bridge = root / "sim" / "showdown_bridge.cjs"
    if not bridge.exists():
        raise FileNotFoundError(f"Showdown bridge not found: {bridge}")

    proc = subprocess.run(
        [node, str(bridge), "validate"],
        input=json.dumps({"format": format, "team": team}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        cwd=root,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Showdown validator failed")
    payload = json.loads(proc.stdout)
    return ValidationResult(
        format=str(payload["format"]),
        valid=bool(payload["valid"]),
        problems=tuple(str(x) for x in payload.get("problems", [])),
        packed=str(payload.get("packed", "")),
        export=str(payload.get("export", "")),
        pokemon=tuple(str(x) for x in payload.get("pokemon", [])),
    )
