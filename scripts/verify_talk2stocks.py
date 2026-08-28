#!/usr/bin/env python3
"""Live verification for the Talk 2 Stocks FastAPI service.

This script is intentionally lightweight: it uses only the Python standard
library and checks the JSON contract returned by the running service.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Check:
    name: str
    method: str
    path: str
    payload: dict[str, Any] | None
    validate: Callable[[dict[str, Any]], list[str]]


def _request_json(base_url: str, method: str, path: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _expect_equal(body: dict[str, Any], key: str, expected: Any) -> list[str]:
    return [] if body.get(key) == expected else [f"{key}: expected {expected!r}, got {body.get(key)!r}"]


def _expect_contains(body: dict[str, Any], key: str, expected: str) -> list[str]:
    haystack = str(body.get(key) or "")
    return [] if expected in haystack else [f"{key}: missing {expected!r}"]


def _expect_no_placeholder(body: dict[str, Any]) -> list[str]:
    text = json.dumps(body, default=str)
    bad = ["<RESOLVED_NSE_SYMBOL>", "RESOLVED_NSE_SYMBOL", "%3CRESOLVED_NSE_SYMBOL%3E"]
    return [f"placeholder leaked: {token}" for token in bad if token in text]


def _validate_defaults(body: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_expect_equal(body, "brand", "Agent Adda"))
    errors.extend(_expect_equal(body, "product", "Talk 2 Stocks"))
    if not isinstance(body.get("watchlist"), list) or not body.get("watchlist"):
        errors.append("watchlist is empty or missing")
    return errors


def _validate_ltfoods(body: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_expect_equal(body, "intent", "financials_review"))
    if body.get("symbols") != ["LTFOODS"]:
        errors.append(f"symbols: expected ['LTFOODS'], got {body.get('symbols')!r}")
    errors.extend(_expect_equal(body, "response_template", "financial_results_table"))
    errors.extend(_expect_contains(body, "answer", "**LTFOODS Latest Financial Results**"))
    errors.extend(_expect_contains(body, "answer", "**Technical Analysis"))
    errors.extend(_expect_contains(body, "answer", "| Jun 2026 |"))
    errors.extend(_expect_no_placeholder(body))
    return errors


def _validate_compare(body: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_expect_equal(body, "intent", "compare"))
    symbols = set(body.get("symbols") or [])
    for symbol in ("TCS", "INFY"):
        if symbol not in symbols:
            errors.append(f"compare missing symbol {symbol}")
    if not body.get("comparison"):
        errors.append("comparison rows missing")
    errors.extend(_expect_no_placeholder(body))
    return errors


def _validate_index(body: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_expect_equal(body, "intent", "index_context"))
    if body.get("symbols"):
        errors.append(f"index prompt returned stock symbols: {body.get('symbols')!r}")
    if not body.get("market_context"):
        errors.append("market_context rows missing")
    errors.extend(_expect_no_placeholder(body))
    return errors


def _validate_screener(body: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_expect_equal(body, "intent", "screener"))
    if body.get("response_template") != "screener_table":
        errors.append(f"response_template should be screener_table, got {body.get('response_template')!r}")
    if not body.get("evidence"):
        errors.append("screener evidence missing")
    errors.extend(_expect_no_placeholder(body))
    return errors


def _validate_intraday_health(body: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_expect_equal(body, "intent", "intraday_health"))
    if body.get("response_template") != "source_health":
        errors.append(f"response_template should be source_health, got {body.get('response_template')!r}")
    if not isinstance(body.get("intraday_context"), dict) or not body.get("intraday_context"):
        errors.append("intraday_context missing")
    errors.extend(_expect_no_placeholder(body))
    return errors


def _validate_advice_boundary(body: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_expect_equal(body, "intent", "advice_boundary"))
    answer = str(body.get("answer") or "").lower()
    if "research" not in answer or "not personalised investment advice" not in answer:
        errors.append("answer should include research-only advice boundary language")
    errors.extend(_expect_no_placeholder(body))
    return errors


def _checks() -> list[Check]:
    return [
        Check("defaults", "GET", "/api/talk/defaults", None, _validate_defaults),
        Check(
            "ltfoods_financials_and_technicals",
            "POST",
            "/api/talk/chat",
            {"question": "Can you pull the latest financial results and technical analysis of LTFoods", "mode": "permissive"},
            _validate_ltfoods,
        ),
        Check(
            "compare_tcs_infy",
            "POST",
            "/api/talk/chat",
            {"question": "Compare TCS vs INFY", "mode": "permissive"},
            _validate_compare,
        ),
        Check(
            "banknifty_index_context",
            "POST",
            "/api/talk/chat",
            {"question": "Analyze BANKNIFTY", "mode": "permissive"},
            _validate_index,
        ),
        Check(
            "high_rs_screener",
            "POST",
            "/api/talk/chat",
            {"question": "Show high RS leaders", "mode": "permissive"},
            _validate_screener,
        ),
        Check(
            "intraday_health_gate",
            "POST",
            "/api/talk/chat",
            {"question": "Check intraday source health", "mode": "permissive"},
            _validate_intraday_health,
        ),
        Check(
            "advice_boundary",
            "POST",
            "/api/talk/chat",
            {"question": "Should I buy TCS?", "mode": "permissive"},
            _validate_advice_boundary,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a running Talk 2 Stocks API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="Base URL for the FastAPI service.")
    parser.add_argument("--timeout", type=float, default=75.0, help="Per-request timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary instead of human-readable lines.")
    args = parser.parse_args()

    started = time.time()
    results: list[dict[str, Any]] = []
    failures = 0
    for check in _checks():
        t0 = time.time()
        try:
            body = _request_json(args.base_url, check.method, check.path, check.payload, args.timeout)
            errors = check.validate(body)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            body = {}
            errors = [f"{type(exc).__name__}: {exc}"]
        elapsed_ms = round((time.time() - t0) * 1000)
        ok = not errors
        failures += 0 if ok else 1
        results.append(
            {
                "name": check.name,
                "ok": ok,
                "elapsed_ms": elapsed_ms,
                "errors": errors,
                "intent": body.get("intent"),
                "symbols": body.get("symbols"),
                "template": body.get("response_template"),
            }
        )

    summary = {
        "base_url": args.base_url,
        "ok": failures == 0,
        "checks": len(results),
        "failures": failures,
        "elapsed_ms": round((time.time() - started) * 1000),
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"Talk 2 Stocks verification: {args.base_url}")
        for result in results:
            mark = "PASS" if result["ok"] else "FAIL"
            print(f"{mark} {result['name']} ({result['elapsed_ms']} ms)")
            for error in result["errors"]:
                print(f"  - {error}")
        print(f"Summary: {summary['checks'] - failures}/{summary['checks']} passed in {summary['elapsed_ms']} ms")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
