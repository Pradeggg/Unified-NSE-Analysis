#!/usr/bin/env python3
"""Agent Adda Intelligence Loop (inner loop runner).

Goal: provide a single entrypoint that:
1) retrieves KB context + similar real episodes
2) proposes the next command/tool to run (BM25 baseline router)
3) optionally executes it (with safe defaults)
4) logs steps/validators/artifacts into EpisodeStore

This is intentionally minimal and offline-safe by default.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from knowledge_base.episode_store import EpisodeStore
from knowledge_base.kb_tools_query import query_tools
from knowledge_base.real_episodes import search_real_episodes, summarize_real_episodes
from knowledge_base.skills_registry import get_registry


ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"


def _prefer_venv_python(cmd: str) -> str:
    if not VENV_PYTHON.exists():
        return cmd
    if cmd.startswith("python "):
        return f"{VENV_PYTHON} " + cmd[len("python ") :]
    if cmd.startswith("python3 "):
        return f"{VENV_PYTHON} " + cmd[len("python3 ") :]
    return cmd


def _inject_web_results_args(cmd: str) -> str:
    """Attach injected web-results path to supported scripts when available."""
    web_path = (os.environ.get("AGENT_ADDA_WEB_RESULTS_PATH") or "").strip()
    if not web_path:
        return cmd
    if "--web-results" in cmd:
        return cmd
    if "scripts/company_story.py" in cmd:
        return cmd + f" --web-results {shlex.quote(web_path)}"
    return cmd


def _prompt_goal() -> str:
    try:
        return input("Goal: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _choose_action(goal: str, *, k: int = 8) -> dict[str, Any] | None:
    reg = get_registry()
    hits = reg.search(goal, k=k)
    for h in hits:
        e = h.get("entry") or {}
        cli = str(e.get("cli") or "").strip()
        if not cli or cli.lower().startswith("cd "):
            continue
        return {"score": h.get("score", 0.0), "entry": e}
    return hits[0] if hits else None


def _expand_placeholders(cli: str, *, symbol: str | None, date: str | None) -> str:
    out = cli
    if symbol:
        out = out.replace("SYMBOL", symbol.strip().upper())
        out = out.replace("{SYMBOL}", symbol.strip().upper())
        out = out.replace("{symbol}", symbol.strip().upper())
    if date:
        out = out.replace("{date}", date.strip())
    return out


def _detect_report_intent(goal: str) -> dict[str, str] | None:
    g = " ".join((goal or "").lower().split())
    if not g:
        return None

    # Detect known report families
    if "midday" in g and "market" in g:
        return {"variant": "midday", "checkpoint": "midday_market", "preset": "midday_market"}
    if "morning" in g and "market" in g:
        return {"variant": "morning", "checkpoint": "morning_market", "preset": "morning_market"}
    if "eod" in g and "market" in g:
        return {"variant": "eod", "checkpoint": "eod_market", "preset": "eod_market"}
    if "sector" in g and "rotation" in g:
        return {"variant": "sector_rotation", "checkpoint": "sector_rotation", "preset": "sector_rotation"}
    if "stage 2" in g or "stage2" in g:
        return {"variant": "stage2_tracker", "checkpoint": "stage2_tracker", "preset": "stage2_tracker"}
    if "top picks" in g or "top_picks" in g:
        return {"variant": "top_picks", "checkpoint": "top_picks", "preset": "top_picks"}
    if "swing" in g and "playbook" in g:
        return {"variant": "swing_playbook", "checkpoint": "swing_playbook", "preset": "swing_playbook"}

    return None


def _wants_validate(goal: str) -> bool:
    g = goal.lower()
    return any(w in g for w in ("validate", "verify", "qa", "check report"))


def _wants_publish(goal: str) -> bool:
    g = goal.lower()
    return any(w in g for w in ("publish", "post", "push to www", "push to website", "deploy report"))


def _detect_pg_or_dashboard_intent(goal: str) -> dict[str, str] | None:
    g = " ".join((goal or "").lower().split())
    if not g:
        return None
    if "postgres" in g or re.search(r"\bpg\b", g):
        if re.search(r"\brestart\b|\bre-start\b", g):
            return {"kind": "pg_restart"}
        if re.search(r"\bstart\b|\bboot\b|\brun\b", g):
            return {"kind": "pg_start"}
        if re.search(r"\bstop\b|\bshutdown\b", g):
            return {"kind": "pg_stop"}
        if re.search(r"\bstatus\b|\bstate\b", g) or "db status" in g or "pg status" in g:
            return {"kind": "pg_status"}
        return {"kind": "pg_status"}
    if "fund dashboard" in g or "refresh fund dashboard" in g:
        return {"kind": "fund_dashboard"}
    if "live prices" in g or "live dashboard" in g:
        return {"kind": "live_prices"}
    return None


_SLUG_PREFIX = {
    "midday_market": "midday-market",
    "morning_market": "morning-market",
    "eod_market": "eod-market-report",
    "sector_rotation": "sector-rotation",
    "stage2_tracker": "stage2-tracker",
    "top_picks": "top-picks",
    "swing_playbook": "swing-playbook",
}


def _http_status(url: str, *, timeout_s: int = 20) -> tuple[int | None, str]:
    """Return (status_code, error). status_code is None on transport failure."""
    try:
        proc = subprocess.run(
            [
                "curl",
                "-sS",
                "--max-time",
                str(timeout_s),
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                url,
            ],
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "").strip()[:400]
    code_s = (proc.stdout or "").strip()
    try:
        return int(code_s), ""
    except Exception:
        return None, f"unexpected curl output: {code_s!r}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent_adda_intelligence_loop")
    ap.add_argument("goal", nargs="*", help="What you want done (natural language)")
    ap.add_argument("--max-steps", type=int, default=6, help="Max attempts (default 6)")
    ap.add_argument("--router-top", type=int, default=8, help="Router candidate pool (default 8)")
    ap.add_argument("--symbol", default="", help="Optional SYMBOL placeholder value")
    ap.add_argument("--date", default="", help="Optional {date} placeholder value (YYYY-MM-DD)")
    ap.add_argument("--execute", action="store_true", help="Actually run the proposed command(s)")
    ap.add_argument("--www-commit", action="store_true", help="Allow committing publish outputs in agentadda/www")
    ap.add_argument("--www-push", action="store_true", help="Allow pushing agentadda/www to GitHub (implies --www-commit)")
    ap.add_argument("--notify", action="store_true", help="Allow push_to_www email notification when pushing (default off)")
    ap.add_argument("--verify-urls", action="store_true", help="Verify live URLs after publish (HTTP 200 checks)")
    ap.add_argument("--verify-base", default="https://www.agentadda.workers.dev", help="Base URL for verification (default workers.dev)")
    ap.add_argument("--verify-custom", default="", help="Optional custom domain base (e.g. https://agentadda.in)")
    ap.add_argument("--caller", default="intelligence_loop", help="Caller label for episode logging")
    args = ap.parse_args(argv)

    goal = " ".join(args.goal).strip() or _prompt_goal()
    if not goal:
        print("No goal provided.")
        return 2

    if args.www_push and not args.www_commit:
        args.www_commit = True

    store = EpisodeStore()
    handle = store.start_episode(
        goal=f"Agent Adda Intelligence Loop: {goal}",
        caller=args.caller,
        tags=["intelligence_loop"],
        metadata={
            "execute": bool(args.execute),
            "max_steps": args.max_steps,
            "router_top": args.router_top,
            "www_commit": bool(args.www_commit),
            "www_push": bool(args.www_push),
            "notify": bool(args.notify),
        },
    )
    os.environ["AGENT_ADDA_EPISODE_ID"] = handle.episode_id

    # 1) KB context
    kb = query_tools(goal, k=5, fmt="json", hybrid=False, web=False, max_tokens=1200, caller=args.caller)
    store.log_step(
        handle,
        step="kb_query",
        tool_name="knowledge_base.query",
        tool_args={"goal": goal},
        result={"hits": [{"id": (h.get("entry") or {}).get("id"), "score": h.get("score")} for h in (kb.get("hits") or [])]},
    )

    # 2) Similar real episodes (recent)
    eps = summarize_real_episodes(days=14)
    similar = search_real_episodes(eps, goal, k=5)
    store.log_step(
        handle,
        step="similar_episodes",
        tool_name="episodes_real.search",
        tool_args={"query": goal},
        result={"episode_ids": [e.episode_id for e in similar]},
    )

    # 3) Try to propose + (optionally) execute
    symbol = args.symbol.strip().upper() or None
    date = args.date.strip() or None

    quick = _detect_pg_or_dashboard_intent(goal)
    if quick:
        plan: list[tuple[str, str]] = []
        if quick["kind"] == "pg_start":
            plan = [("run", "./postgres/start_pg.sh start"), ("check", "./postgres/start_pg.sh status")]
        elif quick["kind"] == "pg_stop":
            plan = [("run", "./postgres/start_pg.sh stop"), ("check", "./postgres/start_pg.sh status")]
        elif quick["kind"] == "pg_restart":
            plan = [("run", "./postgres/start_pg.sh restart"), ("check", "./postgres/start_pg.sh status")]
        elif quick["kind"] == "pg_status":
            plan = [("check", "./postgres/start_pg.sh status")]
        elif quick["kind"] == "fund_dashboard":
            plan = [("run", _prefer_venv_python("python tools/fund_refresh.py --no-open"))]
        elif quick["kind"] == "live_prices":
            plan = [("run", _prefer_venv_python("python tools/live_prices.py --no-open"))]

        if not args.execute:
            print("Planned steps:")
            for i, (kind, cmd) in enumerate(plan, 1):
                print(f"  {i}. {kind}: {cmd}")
            store.end_episode(
                handle,
                status="SUCCESS",
                summary="proposed dashboard/pg action (dry-run)",
                metadata={"quick": quick, "planned_steps": [k for k, _ in plan]},
            )
            return 0

        for i, (kind, cmd) in enumerate(plan, 1):
            store.log_step(handle, step=f"plan[{i}]", tool_name="policy.quick", tool_args={"kind": kind, "cmd": cmd, "quick": quick})
            print(f"[{i}/{len(plan)}] {kind}: {cmd}")
            env = os.environ.copy()
            env["AGENT_ADDA_EPISODE_ID"] = handle.episode_id
            res = subprocess.run(cmd, shell=True, cwd=str(ROOT), env=env)
            store.log_step(
                handle,
                step=f"exec[{i}]",
                tool_name="subprocess.run",
                status="ok" if res.returncode == 0 else "error",
                result={"returncode": res.returncode, "kind": kind},
            )
            if res.returncode != 0:
                store.end_episode(
                    handle,
                    status="FAILED",
                    summary=f"failed at {kind}",
                    metadata={"failed_step": kind, "returncode": res.returncode, "quick": quick},
                )
                return res.returncode or 1

        store.end_episode(handle, status="SUCCESS", summary="quick policy completed", metadata={"quick": quick})
        return 0

    # Prefer an explicit report workflow if detected (build → validate → publish)
    report = _detect_report_intent(goal)
    if report:
        plan: list[tuple[str, str]] = []
        if report["variant"] in ("midday", "morning"):
            plan.append(("build", _prefer_venv_python(f"python scripts/build_morning_market_report.py --variant {report['variant']}")))
        elif report["variant"] == "eod":
            plan.append(("build", _prefer_venv_python("python scripts/build_eod_market_report.py --no-open")))
        elif report["variant"] == "sector_rotation":
            plan.append(("build", _prefer_venv_python("python sector_rotation_report.py")))
        elif report["variant"] == "stage2_tracker":
            plan.append(("build", _prefer_venv_python("python sector_rotation_tracker.py --report --html")))
        elif report["variant"] == "top_picks":
            plan.append(("build", _prefer_venv_python("python top_picks_report.py")))
        elif report["variant"] == "swing_playbook":
            plan.append(("build", _prefer_venv_python("python scripts/generate_swing_playbook_report.py --no-open")))

        if _wants_validate(goal) or _wants_publish(goal):
            plan.append(
                (
                    "validate",
                    _prefer_venv_python(
                        f"python report_validation.py --checkpoint {report['checkpoint']} --skip-llm --fail-on-high"
                    ),
                )
            )

        if _wants_publish(goal):
            # Safe default: dry-run publish unless explicitly allowed.
            base = _prefer_venv_python(f"python scripts/push_to_www.py --preset {report['preset']} --date {date or ''}".strip())
            if not date:
                # push_to_www defaults to today's date, but be explicit when we know it.
                base = _prefer_venv_python(f"python scripts/push_to_www.py --preset {report['preset']}")
            if args.www_commit:
                cmd = base
                if args.www_push:
                    cmd += " --push"
                    if not args.notify:
                        cmd += " --no-notify"
                else:
                    cmd += " --no-notify"
            else:
                cmd = base + " --dry-run"
            plan.append(("publish", cmd))

        # Optional URL verification (only meaningful when we actually push).
        will_publish_live = _wants_publish(goal) and args.execute and args.www_push
        if args.verify_urls and will_publish_live and date:
            slug_prefix = _SLUG_PREFIX.get(report["checkpoint"], report["preset"].replace("_", "-"))
            slug = f"{slug_prefix}-{date}"
            bases = [args.verify_base.strip().rstrip("/")]
            if args.verify_custom.strip():
                bases.append(args.verify_custom.strip().rstrip("/"))
            for base_url in bases:
                plan.append(("verify", f"{base_url}/stocks/reports/{slug}"))
                plan.append(("verify", f"{base_url}/reports/{slug}.html"))
                plan.append(("verify", f"{base_url}/stocks/reports/latest.json"))

        if not args.execute:
            print("Planned steps:")
            for i, (kind, cmd) in enumerate(plan, 1):
                print(f"  {i}. {kind}: {cmd}")
            store.end_episode(
                handle,
                status="SUCCESS",
                summary="proposed report workflow (dry-run)",
                metadata={"report": report, "planned_steps": [k for k, _ in plan]},
            )
            return 0

        for i, (kind, cmd) in enumerate(plan, 1):
            store.log_step(handle, step=f"plan[{i}]", tool_name="policy.report", tool_args={"kind": kind, "cmd": cmd, "report": report})
            print(f"[{i}/{len(plan)}] {kind}: {cmd}")
            env = os.environ.copy()
            env["AGENT_ADDA_EPISODE_ID"] = handle.episode_id
            if kind == "verify":
                code, err = _http_status(cmd)
                ok_http = (code == 200)
                store.log_validator(
                    handle,
                    name="url_200",
                    ok=ok_http,
                    details={"url": cmd, "http_code": code, "error": err},
                )
                store.log_artifact(handle, artifact_type="url", locator=cmd, meta={"http_code": code})
                if not ok_http:
                    store.end_episode(
                        handle,
                        status="FAILED",
                        summary="URL verification failed",
                        metadata={"url": cmd, "http_code": code, "error": err, "report": report},
                    )
                    return 1
                continue

            res = subprocess.run(cmd, shell=True, cwd=str(ROOT), env=env)
            store.log_step(
                handle,
                step=f"exec[{i}]",
                tool_name="subprocess.run",
                status="ok" if res.returncode == 0 else "error",
                result={"returncode": res.returncode, "kind": kind},
            )
            if res.returncode != 0:
                store.end_episode(
                    handle,
                    status="FAILED",
                    summary=f"failed at {kind}",
                    metadata={"failed_step": kind, "returncode": res.returncode, "report": report},
                )
                return res.returncode or 1

        store.end_episode(handle, status="SUCCESS", summary="report workflow completed", metadata={"report": report})
        return 0

    attempted: list[str] = []
    ok = False
    last_rc: int | None = None

    reg = get_registry()
    candidates = reg.search(goal, k=max(args.router_top, 8))
    for step_idx, cand in enumerate(candidates[: args.max_steps], start=1):
        e = cand.get("entry") or {}
        eid = str(e.get("id") or "").strip()
        cli = str(e.get("cli") or "").strip()
        attempted.append(eid or "?")
        if not cli:
            continue
        run_cli = _inject_web_results_args(_prefer_venv_python(_expand_placeholders(cli, symbol=symbol, date=date)))

        store.log_step(
            handle,
            step=f"propose[{step_idx}]",
            tool_name="router.bm25",
            tool_args={"id": eid, "cli": run_cli, "score": cand.get("score")},
        )

        if "→" in run_cli:
            # REPL shortcut: log and stop (cannot execute without REPL context).
            store.log_step(
                handle,
                step=f"blocked_repl_shortcut[{step_idx}]",
                tool_name="router.bm25",
                status="blocked",
                result={"cli": run_cli},
            )
            break

        if not args.execute:
            # Dry-run: show first proposal and stop.
            print(f"Proposed: {eid}\nCLI: {run_cli}")
            store.end_episode(
                handle,
                status="SUCCESS",
                summary="proposed next action (dry-run)",
                metadata={"proposed_id": eid, "cli": run_cli, "attempted": attempted},
            )
            return 0

        print(f"[step {step_idx}] Running: {run_cli}")
        env = os.environ.copy()
        env["AGENT_ADDA_EPISODE_ID"] = handle.episode_id
        res = subprocess.run(run_cli, shell=True, cwd=str(ROOT), env=env)
        last_rc = int(res.returncode)
        store.log_step(
            handle,
            step=f"exec[{step_idx}]",
            tool_name="subprocess.run",
            status="ok" if res.returncode == 0 else "error",
            result={"returncode": res.returncode, "id": eid},
        )

        if res.returncode == 0:
            ok = True
            break

    store.end_episode(
        handle,
        status="SUCCESS" if ok else "FAILED",
        summary="completed" if ok else "all candidates failed",
        metadata={"attempted": attempted, "last_returncode": last_rc},
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
