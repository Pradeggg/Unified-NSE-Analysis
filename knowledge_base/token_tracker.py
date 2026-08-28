"""Token usage tracking for the Agent Adda Knowledge Base.

Every KB query logs:
    - timestamp, query text, search method (bm25 / vector / hybrid)
    - tokens_in  (query tokens)
    - tokens_out (response/context block tokens)
    - entries_returned, latency_ms
    - estimated_savings_tokens (tokens caller saves vs. brute-force code search)
    - llm_tokens_used (non-zero only for vector searches that hit an embedding API)

Storage: SQLite at  data/knowledge_base/query_log.db  (auto-created).

Usage
-----
    from knowledge_base.token_tracker import TokenTracker
    t = TokenTracker()
    rec = t.log(
        query="run daily pipeline",
        tokens_in=8,
        tokens_out=320,
        entries_returned=3,
        source_file_tokens_saved=18000,
        latency_ms=12,
        search_method="bm25",
    )
    print(t.stats(days=7))
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ._common import KB_DIR

DB_PATH = KB_DIR / "query_log.db"

# ── token counting ─────────────────────────────────────────────────────────────

def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Count tokens using tiktoken; fall back to word-count estimate."""
    if not text:
        return 0
    try:
        import tiktoken  # noqa: WPS433
        enc = tiktoken.get_encoding(model)
        return len(enc.encode(text))
    except Exception:
        # Rough empirical estimate: 1 word ≈ 1.35 tokens
        return max(1, int(len(text.split()) * 1.35))


# ── schema ────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS query_log (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                      TEXT NOT NULL,           -- ISO-8601
    query                   TEXT NOT NULL,
    search_method           TEXT NOT NULL,           -- bm25 | vector | hybrid
    tokens_in               INTEGER NOT NULL DEFAULT 0,
    tokens_out              INTEGER NOT NULL DEFAULT 0,
    entries_returned        INTEGER NOT NULL DEFAULT 0,
    source_file_tokens      INTEGER NOT NULL DEFAULT 0,  -- tokens caller would need WITHOUT KB
    estimated_savings       INTEGER NOT NULL DEFAULT 0,  -- source_file_tokens - tokens_out - tokens_in
    llm_tokens_used         INTEGER NOT NULL DEFAULT 0,  -- embedding API tokens (0 for bm25)
    latency_ms              REAL    NOT NULL DEFAULT 0,
    caller                  TEXT    DEFAULT '',      -- optional: 'claude'|'codex'|'cli'|'mcp'
    session_id              TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS llm_call_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    call_type   TEXT NOT NULL,   -- embed | chat | qa_gen
    model       TEXT NOT NULL,
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL    NOT NULL DEFAULT 0,
    latency_ms  REAL    NOT NULL DEFAULT 0,
    query_log_id INTEGER REFERENCES query_log(id)
);

CREATE INDEX IF NOT EXISTS idx_query_log_ts    ON query_log(ts);
CREATE INDEX IF NOT EXISTS idx_llm_call_log_ts ON llm_call_log(ts);
"""


# ── pricing (USD per 1M tokens, 2026 rates) ───────────────────────────────────
_PRICE_PER_1M: dict[str, dict[str, float]] = {
    "gpt-4o":               {"in": 2.50,  "out": 10.00},
    "gpt-4o-mini":          {"in": 0.15,  "out": 0.60},
    "text-embedding-3-small": {"in": 0.02, "out": 0.0},
    "text-embedding-3-large": {"in": 0.13, "out": 0.0},
    "claude-sonnet-4-6":    {"in": 3.00,  "out": 15.00},
    "ollama":               {"in": 0.0,   "out": 0.0},   # local = free
    "sentence-transformers": {"in": 0.0,  "out": 0.0},   # local = free
}


def _cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    p = _PRICE_PER_1M.get(model, {"in": 0.0, "out": 0.0})
    return (tokens_in * p["in"] + tokens_out * p["out"]) / 1_000_000


# ── TokenTracker ──────────────────────────────────────────────────────────────

class TokenTracker:
    """SQLite-backed token usage logger for KB queries and LLM calls."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db = db_path or DB_PATH
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_DDL)

    # ── logging ───────────────────────────────────────────────────────────────

    def log(
        self,
        *,
        query: str,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        context_block: str = "",
        entries_returned: int = 0,
        source_file_tokens: int = 0,
        latency_ms: float = 0.0,
        search_method: str = "bm25",
        llm_tokens_used: int = 0,
        caller: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        """Record one KB query. Returns the logged row as a dict."""
        ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        tin  = tokens_in  if tokens_in  is not None else count_tokens(query)
        tout = tokens_out if tokens_out is not None else count_tokens(context_block)
        # savings = what the caller would have needed - what they actually got
        savings = max(0, source_file_tokens - tout - tin)

        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO query_log
                   (ts, query, search_method, tokens_in, tokens_out,
                    entries_returned, source_file_tokens, estimated_savings,
                    llm_tokens_used, latency_ms, caller, session_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   RETURNING id""",
                (ts, query[:500], search_method, tin, tout,
                 entries_returned, source_file_tokens, savings,
                 llm_tokens_used, round(latency_ms, 2), caller, session_id),
            )
            row_id = cur.fetchone()[0]

        return {
            "id": row_id, "ts": ts, "query": query,
            "tokens_in": tin, "tokens_out": tout,
            "entries_returned": entries_returned,
            "estimated_savings": savings,
            "search_method": search_method,
            "latency_ms": round(latency_ms, 2),
        }

    def log_llm_call(
        self,
        *,
        call_type: str,
        model: str,
        tokens_in: int,
        tokens_out: int = 0,
        latency_ms: float = 0.0,
        query_log_id: int | None = None,
    ) -> None:
        """Record an LLM/embedding API call (e.g. from vector_store)."""
        ts   = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        cost = _cost_usd(model, tokens_in, tokens_out)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO llm_call_log
                   (ts, call_type, model, tokens_in, tokens_out, cost_usd, latency_ms, query_log_id)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (ts, call_type, model, tokens_in, tokens_out,
                 cost, round(latency_ms, 2), query_log_id),
            )

    # ── analytics ─────────────────────────────────────────────────────────────

    def stats(self, days: int = 7) -> dict[str, Any]:
        """Return usage summary for the last N days."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds") + "Z"
        with self._conn() as conn:
            qs = conn.execute(
                """SELECT
                       COUNT(*)                      AS total_queries,
                       COALESCE(SUM(tokens_in),0)    AS total_tokens_in,
                       COALESCE(SUM(tokens_out),0)   AS total_tokens_out,
                       COALESCE(SUM(estimated_savings),0) AS total_savings,
                       COALESCE(AVG(latency_ms),0)   AS avg_latency_ms,
                       COALESCE(SUM(llm_tokens_used),0) AS llm_tokens_used,
                       COALESCE(AVG(entries_returned),0) AS avg_entries
                   FROM query_log WHERE ts >= ?""",
                (since,),
            ).fetchone()

            methods = conn.execute(
                "SELECT search_method, COUNT(*) AS n FROM query_log WHERE ts >= ? GROUP BY search_method",
                (since,),
            ).fetchall()

            llm = conn.execute(
                """SELECT model,
                          SUM(tokens_in) AS tin,
                          SUM(tokens_out) AS tout,
                          SUM(cost_usd) AS cost
                   FROM llm_call_log WHERE ts >= ? GROUP BY model""",
                (since,),
            ).fetchall()

            recent = conn.execute(
                """SELECT ts, query, tokens_in, tokens_out, estimated_savings, latency_ms, search_method
                   FROM query_log WHERE ts >= ? ORDER BY ts DESC LIMIT 10""",
                (since,),
            ).fetchall()

        row = dict(qs) if qs else {}
        savings_k  = round(row.get("total_savings", 0) / 1000, 1)
        total_in_k = round(row.get("total_tokens_in", 0) / 1000, 1)
        # Cost estimate for tokens saved (assumes gpt-4o caller)
        savings_cost = _cost_usd("gpt-4o", int(row.get("total_savings", 0)), 0)

        return {
            "period_days":         days,
            "total_queries":       row.get("total_queries", 0),
            "tokens_in_k":         total_in_k,
            "tokens_out_k":        round(row.get("total_tokens_out", 0) / 1000, 1),
            "estimated_savings_k": savings_k,
            "savings_cost_usd":    round(savings_cost, 4),
            "avg_latency_ms":      round(row.get("avg_latency_ms", 0), 1),
            "llm_tokens_used":     row.get("llm_tokens_used", 0),
            "avg_entries_returned": round(row.get("avg_entries", 0), 1),
            "by_search_method":    {r["search_method"]: r["n"] for r in methods},
            "llm_calls_by_model":  [
                {"model": r["model"],
                 "tokens_in": r["tin"],
                 "tokens_out": r["tout"],
                 "cost_usd": round(r["cost"], 6)}
                for r in llm
            ],
            "recent_queries":      [
                {"ts": r["ts"], "query": r["query"][:60],
                 "tin": r["tokens_in"], "tout": r["tokens_out"],
                 "savings": r["estimated_savings"], "ms": round(r["latency_ms"], 1),
                 "method": r["search_method"]}
                for r in recent
            ],
        }

    def format_stats_report(self, days: int = 7) -> str:
        """Pretty-printed stats report for the CLI."""
        s = self.stats(days)
        lines = [
            f"╔══ Agent Adda KB — Token Usage ({days}-day window) ══╗",
            f"  Queries:          {s['total_queries']}",
            f"  Tokens IN (query): {s['tokens_in_k']}K",
            f"  Tokens OUT (ctx):  {s['tokens_out_k']}K",
            f"  Est. savings:      {s['estimated_savings_k']}K tokens  (≈ ${s['savings_cost_usd']} if gpt-4o)",
            f"  Avg latency:       {s['avg_latency_ms']} ms",
            f"  Avg entries/query: {s['avg_entries_returned']}",
            f"  LLM tokens used:   {s['llm_tokens_used']}",
            "",
            "  Search methods:",
        ]
        for method, n in s["by_search_method"].items():
            lines.append(f"    {method:<12}  {n} queries")
        if s["llm_calls_by_model"]:
            lines.append("")
            lines.append("  LLM calls:")
            for lc in s["llm_calls_by_model"]:
                lines.append(
                    f"    {lc['model']:<30}  in={lc['tokens_in']:>6}  out={lc['tokens_out']:>6}  ${lc['cost_usd']}"
                )
        if s["recent_queries"]:
            lines.append("")
            lines.append("  Recent queries:")
            for r in s["recent_queries"][:5]:
                lines.append(
                    f"    [{r['ts'][11:19]}] {r['query']:<45} "
                    f"tin={r['tin']:>4} tout={r['tout']:>5} sav={r['savings']:>6} {r['ms']}ms"
                )
        lines.append("╚" + "═" * 54 + "╝")
        return "\n".join(lines)


# ── module-level singleton ─────────────────────────────────────────────────────
_tracker: TokenTracker | None = None


def get_tracker() -> TokenTracker:
    global _tracker
    if _tracker is None:
        _tracker = TokenTracker()
    return _tracker


# ── context manager for timing + auto-log ─────────────────────────────────────

class QueryTimer:
    """Context manager that times a KB query and auto-logs it."""

    def __init__(
        self,
        query: str,
        *,
        search_method: str = "bm25",
        caller: str = "",
        session_id: str = "",
        tracker: TokenTracker | None = None,
    ) -> None:
        self.query = query
        self.search_method = search_method
        self.caller = caller
        self.session_id = session_id
        self._tracker = tracker or get_tracker()
        self._t0: float = 0.0
        self.result: dict[str, Any] = {}

    def __enter__(self) -> "QueryTimer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *_: Any) -> None:
        pass  # logging happens via .finish()

    def finish(
        self,
        *,
        context_block: str = "",
        entries_returned: int = 0,
        source_file_tokens: int = 0,
        llm_tokens_used: int = 0,
    ) -> dict[str, Any]:
        latency_ms = (time.perf_counter() - self._t0) * 1000
        self.result = self._tracker.log(
            query=self.query,
            context_block=context_block,
            entries_returned=entries_returned,
            source_file_tokens=source_file_tokens,
            latency_ms=latency_ms,
            search_method=self.search_method,
            llm_tokens_used=llm_tokens_used,
            caller=self.caller,
            session_id=self.session_id,
        )
        return self.result
