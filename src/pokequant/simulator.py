from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationResult:
    format: str
    valid: bool
    problems: tuple[str, ...]
    packed: str
    export: str
    pokemon: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SimulationResult:
    format: str
    winner: str
    turns: int
    requests: int
    seed: str
    policy: str = "default"
    errors: int = 0


def _run_bridge(
    command: str,
    payload: dict[str, Any],
    *,
    repo_root: str | Path | None = None,
    node: str = "node",
    timeout: float = 30.0,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    bridge = root / "sim" / "showdown_bridge.cjs"
    if not bridge.exists():
        raise FileNotFoundError(f"Showdown bridge not found: {bridge}")

    proc = subprocess.run(
        [node, str(bridge), command],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        cwd=root,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"Showdown {command} failed")
    return json.loads(proc.stdout)


def validate_team(
    team: str,
    *,
    format: str = "gen9ou",
    repo_root: str | Path | None = None,
    node: str = "node",
    timeout: float = 30.0,
) -> ValidationResult:
    payload = _run_bridge(
        "validate",
        {"format": format, "team": team},
        repo_root=repo_root,
        node=node,
        timeout=timeout,
    )
    return ValidationResult(
        format=str(payload["format"]),
        valid=bool(payload["valid"]),
        problems=tuple(str(x) for x in payload.get("problems", [])),
        packed=str(payload.get("packed", "")),
        export=str(payload.get("export", "")),
        pokemon=tuple(str(x) for x in payload.get("pokemon", [])),
    )


def _simulation_result(payload: dict[str, Any]) -> SimulationResult:
    return SimulationResult(
        format=str(payload["format"]),
        winner=str(payload["winner"]),
        turns=int(payload["turns"]),
        requests=int(payload["requests"]),
        seed=str(payload["seed"]),
        policy=str(payload.get("policy", "default")),
        errors=int(payload.get("errors", 0)),
    )


def simulate_default(
    p1team: str,
    p2team: str,
    *,
    format: str = "gen9ou",
    seed: str = "1,2,3,4",
    max_turns: int = 1000,
    repo_root: str | Path | None = None,
    node: str = "node",
    timeout: float = 60.0,
) -> SimulationResult:
    payload = _run_bridge(
        "simulate-default",
        {
            "format": format,
            "p1team": p1team,
            "p2team": p2team,
            "seed": seed,
            "maxTurns": max_turns,
        },
        repo_root=repo_root,
        node=node,
        timeout=timeout,
    )
    return _simulation_result(payload)


def simulate_heuristic(
    p1team: str,
    p2team: str,
    *,
    format: str = "gen9ou",
    seed: str = "1,2,3,4",
    max_turns: int = 1000,
    repo_root: str | Path | None = None,
    node: str = "node",
    timeout: float = 60.0,
) -> SimulationResult:
    """Run a seeded battle with the same state-aware heuristic on both sides."""
    payload = _run_bridge(
        "simulate-heuristic",
        {
            "format": format,
            "p1team": p1team,
            "p2team": p2team,
            "seed": seed,
            "maxTurns": max_turns,
        },
        repo_root=repo_root,
        node=node,
        timeout=timeout,
    )
    return _simulation_result(payload)
