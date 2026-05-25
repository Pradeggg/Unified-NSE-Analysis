#!/usr/bin/env bash
# Smoke test for the four recurring user-visible regressions:
#   1. "top gainers"                          -> get_top_gainers_losers must succeed (no ERROR in SOURCE TRAIL)
#   2. morning briefing                       -> must NOT call resolve_symbol('Global')
#   3. "/scan NIFTY AUTO"                     -> index parser must accept multi-word index names
#   4. "Fundamental analysis for the above stocks" -> collective reference must resolve to prior symbols
#
# Run from the repo root (or anywhere — the script cd's itself):
#   bash scripts/smoke_user_flows.sh
#
# Exits non-zero on the first failure. Each step prints PASS/FAIL with the
# matched (or expected) substring so the failure is obvious from the screen.

set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
LOG_DIR="$(mktemp -d)"
trap 'rm -rf "$LOG_DIR"' EXIT

pass=0
fail=0

run_case() {
    local name="$1" query="$2" must_contain="$3" must_not_contain="$4"
    local log="$LOG_DIR/${name// /_}.log"
    printf "── %-55s " "$name"
    "$PY" nse_agent.py --no-briefing --skip-readiness -q "$query" \
        > "$log" 2>&1 || true

    if [[ -n "$must_not_contain" ]] && grep -qE "$must_not_contain" "$log"; then
        printf "FAIL  (forbidden pattern matched: %s)\n" "$must_not_contain"
        echo "    log: $log"
        fail=$((fail + 1))
        return
    fi
    if [[ -n "$must_contain" ]] && ! grep -qE "$must_contain" "$log"; then
        printf "FAIL  (expected pattern missing: %s)\n" "$must_contain"
        echo "    log: $log"
        fail=$((fail + 1))
        return
    fi
    printf "PASS\n"
    pass=$((pass + 1))
}

echo "Agent Adda — user-flow smoke ($(date '+%Y-%m-%d %H:%M:%S'))"
echo

# 1. "top gainers" must return a gainers list (live API path).
run_case "top gainers (intraday default)"          \
    "top gainers"                                   \
    "(GAINERS|Top gainers|Top Movers|MODISONLTD|HARIOMPIPE)" \
    "(get_top_gainers_losers: ERROR|scan_intraday_market: ERROR)"

# 1b. Explicit intraday must route to the live tool.
run_case "top gainers intraday"                     \
    "top gainers intraday"                          \
    "get_top_gainers_losers"                        \
    "get_eod_top_movers"

# 1c. Explicit EOD must route to the snapshot tool.
run_case "top gainers EOD"                          \
    "top gainers EOD"                               \
    "get_eod_top_movers"                            \
    "get_top_gainers_losers: ERROR"

# 2. Morning briefing must not try to resolve 'Global' as a ticker.
#    The bug previously produced: resolve_symbol(... 'Global' ...) followed by
#    get_live_quote 403 on /api/quote-equity?symbol=GLOBAL.
run_case "morning briefing — no GLOBAL misroute"    \
    "/briefing"                                     \
    ""                                              \
    "(symbol=GLOBAL|'Global' is a market concept)"

# 3. /scan must accept a multi-word index name.
run_case "/scan NIFTY AUTO accepts index"           \
    "/scan NIFTY AUTO"                              \
    ""                                              \
    "No stocks found for index"

# 4. Collective reference must resolve (no THE%20ABOVE%20STOCKS URL).
run_case "collective reference resolution"          \
    "top gainers ; fundamentals for the above"      \
    ""                                              \
    "THE%20ABOVE|company/THE ABOVE"

echo
echo "─────────────────────────────────────────────────────────────"
printf "Result: %d passed, %d failed\n" "$pass" "$fail"
[[ $fail -eq 0 ]]
