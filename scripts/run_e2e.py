#!/usr/bin/env python3
"""Run the Agent Adda end-to-end scenario matrix."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "tests" / "e2e" / "e2e_scenarios.json"
VALID_TIERS = {"smoke", "critical", "full"}


def _load_matrix(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError(f"{path} does not contain a non-empty scenarios list")
    return scenarios


def _expand_command(command: list[str]) -> list[str]:
    return [part.replace("{python}", sys.executable) for part in command]


def _scenario_matches(scenario: dict[str, Any], tiers: set[str], areas: set[str], ids: set[str]) -> bool:
    if ids and scenario["id"] not in ids:
        return False
    if tiers and scenario["tier"] not in tiers:
        return False
    if areas and scenario.get("area") not in areas:
        return False
    return True


def _blocked_requirements(scenario: dict[str, Any], allowed: set[str]) -> list[str]:
    required = set(scenario.get("requires") or [])
    return sorted(required - allowed)


def _format_scenario(scenario: dict[str, Any]) -> str:
    req = ",".join(scenario.get("requires") or []) or "-"
    return f"{scenario['id']:<32} {scenario['tier']:<8} {scenario.get('area', '-'):<16} requires={req}"


def _run_one(scenario: dict[str, Any], timeout: int, dry_run: bool) -> tuple[str, str, float]:
    command = _expand_command(scenario["command"])
    print(f"\n==> {scenario['id']} [{scenario['tier']}/{scenario.get('area', '-')}]")
    print("    " + " ".join(command))
    if dry_run:
        return scenario["id"], "DRY_RUN", 0.0

    start = time.time()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        text=True,
        timeout=timeout,
    )
    elapsed = time.time() - start
    return scenario["id"], ("PASS" if completed.returncode == 0 else f"FAIL({completed.returncode})"), elapsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Agent Adda E2E scenario matrix")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX, help="Path to e2e_scenarios.json")
    parser.add_argument("--tier", action="append", choices=sorted(VALID_TIERS), help="Tier to run; repeatable")
    parser.add_argument("--area", action="append", help="Functional area to run; repeatable")
    parser.add_argument("--id", action="append", dest="ids", help="Specific scenario id to run; repeatable")
    parser.add_argument("--allow-requires", action="append", default=[], help="Allow scenarios requiring this service, e.g. postgres")
    parser.add_argument("--include-requires", action="store_true", help="Run scenarios with external requirements")
    parser.add_argument("--timeout", type=int, default=300, help="Per-scenario timeout in seconds")
    parser.add_argument("--list", action="store_true", help="List selected scenarios without running")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenarios = _load_matrix(args.matrix)
    tiers = set(args.tier or ["smoke"])
    areas = set(args.area or [])
    ids = set(args.ids or [])
    allowed_requires = set(args.allow_requires or [])
    if args.include_requires:
        allowed_requires.update({req for s in scenarios for req in s.get("requires", [])})

    selected = [s for s in scenarios if _scenario_matches(s, tiers, areas, ids)]
    runnable: list[dict[str, Any]] = []
    skipped: list[tuple[dict[str, Any], list[str]]] = []
    for scenario in selected:
        blocked = _blocked_requirements(scenario, allowed_requires)
        if blocked:
            skipped.append((scenario, blocked))
        else:
            runnable.append(scenario)

    if args.list:
        for scenario in selected:
            blocked = _blocked_requirements(scenario, allowed_requires)
            suffix = f" SKIP missing={','.join(blocked)}" if blocked else ""
            print(_format_scenario(scenario) + suffix)
        return 0

    if not runnable:
        print("No runnable scenarios selected.")
        if skipped:
            print("Skipped scenarios require: " + ", ".join(sorted({b for _, blocked in skipped for b in blocked})))
        return 1

    results = []
    for scenario in runnable:
        results.append(_run_one(scenario, args.timeout, args.dry_run))

    if skipped:
        print("\nSkipped:")
        for scenario, blocked in skipped:
            print(f"  {scenario['id']}: missing {', '.join(blocked)}")

    print("\nSummary:")
    failed = 0
    for sid, status, elapsed in results:
        print(f"  {sid:<32} {status:<10} {elapsed:6.1f}s")
        failed += int(status.startswith("FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
