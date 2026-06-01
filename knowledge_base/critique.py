"""Critique a broker / research report against our internal DB facts.

PG 2026-05-27: Reconciles an external broker thesis (sitting in the KB or
provided as a path/URL) with our own stage_snapshots, daily_scores, and
equity_eod return profile, then asks gpt-4o-mini for a structured verdict.

Public API
----------
critique_report(symbol, *, source="kb", path=None, url=None, top_k=6,
                model=None, brand=None) -> dict

Returns a dict with keys:
  ok, symbol, db_snapshot, broker_passages, verdict (LLM JSON), model.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ._common import load_dotenv
from .vector_store import KBVectorStore

load_dotenv()

# PG: keep cheap + fast for verdict pass; user can override via env / arg.
CRITIQUE_MODEL = os.environ.get("KB_CRITIQUE_MODEL", "gpt-4o-mini")

_SYSTEM_PROMPT = (
    "You are a senior portfolio manager reconciling an external broker "
    "research note against our own internal market database snapshot. "
    "Be skeptical. Quote concrete numbers from BOTH sides. "
    "Output ONLY valid JSON with these keys:\n"
    "  agreement_score: int 0-100 (how much our data supports the broker thesis)\n"
    "  recommended_stance: one of [STRONG_BUY, BUY, ACCUMULATE, HOLD, REDUCE, AVOID]\n"
    "  bull_points: list of short strings (max 5)\n"
    "  bear_points: list of short strings (max 5)\n"
    "  target_sanity: short paragraph judging whether the broker target is reasonable vs CMP / fundamentals\n"
    "  tactical_trigger: a specific price / signal that would confirm the bull case\n"
    "  invalidation: a specific price / signal that would kill the thesis\n"
    "  one_line_verdict: ≤140 chars summary\n"
)


# ─────────────────────────────────────────────────────────────────────────────
# DB pulls
# ─────────────────────────────────────────────────────────────────────────────

def _pg_connect():
    # PG: defer terminal import so this module is usable without the terminal pkg
    from terminal.postgres_tools import _connect
    return _connect()


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "__float__") and not isinstance(value, (int, float, bool)):
        try:
            return float(value)
        except Exception:
            return str(value)
    return value


def _row_to_dict(cur, row) -> dict[str, Any]:
    cols = [d[0] for d in cur.description]
    return {c: _to_jsonable(v) for c, v in zip(cols, row)}


def fetch_db_snapshot(symbol: str) -> dict[str, Any]:
    """Pull the freshest stage snapshot + multi-horizon returns for `symbol`."""
    sym = symbol.upper().strip()
    snap: dict[str, Any] = {"symbol": sym}
    try:
        conn = _pg_connect()
    except Exception as exc:
        return {"symbol": sym, "error": f"pg connect failed: {exc}"}

    try:
        with conn, conn.cursor() as cur:
            # latest stage snapshot — richest single-row summary we have
            cur.execute(
                """
                SELECT *
                FROM scores.stage_snapshots
                WHERE upper(symbol) = %s
                ORDER BY snapshot_date DESC
                LIMIT 1
                """,
                (sym,),
            )
            row = cur.fetchone()
            if row:
                snap["stage_snapshot"] = _row_to_dict(cur, row)

            # latest daily_scores row (technical + fundamental composite)
            cur.execute(
                """
                SELECT *
                FROM scores.daily_scores
                WHERE upper(symbol) = %s
                ORDER BY score_date DESC
                LIMIT 1
                """,
                (sym,),
            )
            row = cur.fetchone()
            if row:
                snap["daily_score"] = _row_to_dict(cur, row)

            # multi-horizon returns
            cur.execute(
                """
                WITH series AS (
                    SELECT trade_date, close
                    FROM market.equity_eod
                    WHERE upper(symbol) = %s
                    ORDER BY trade_date DESC
                    LIMIT 300
                ),
                latest AS (SELECT close AS cmp, trade_date FROM series LIMIT 1)
                SELECT
                    (SELECT cmp FROM latest)                                    AS cmp,
                    (SELECT trade_date FROM latest)                             AS as_of,
                    (SELECT close FROM series OFFSET 5 LIMIT 1)                 AS close_5d,
                    (SELECT close FROM series OFFSET 21 LIMIT 1)                AS close_21d,
                    (SELECT close FROM series OFFSET 63 LIMIT 1)                AS close_63d,
                    (SELECT close FROM series OFFSET 252 LIMIT 1)               AS close_252d,
                    (SELECT MAX(close) FROM series)                             AS hi_300d,
                    (SELECT MIN(close) FROM series)                             AS lo_300d
                """,
                (sym,),
            )
            row = cur.fetchone()
            if row:
                d = _row_to_dict(cur, row)
                cmp_ = d.get("cmp")
                def _pct(prev):
                    if cmp_ and prev and prev != 0:
                        return round((cmp_ - prev) / prev * 100, 2)
                    return None
                snap["returns"] = {
                    "as_of": d.get("as_of"),
                    "cmp": cmp_,
                    "ret_5d_pct":   _pct(d.get("close_5d")),
                    "ret_21d_pct":  _pct(d.get("close_21d")),
                    "ret_63d_pct":  _pct(d.get("close_63d")),
                    "ret_252d_pct": _pct(d.get("close_252d")),
                    "hi_300d": d.get("hi_300d"),
                    "lo_300d": d.get("lo_300d"),
                    "dist_from_hi_pct": _pct(d.get("hi_300d")),
                }
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return snap


# ─────────────────────────────────────────────────────────────────────────────
# Broker content retrieval
# ─────────────────────────────────────────────────────────────────────────────

def _retrieve_kb_passages(symbol: str, *, top_k: int, brand: str | None) -> list[dict]:
    store = KBVectorStore()
    query = symbol
    if brand:
        query = f"{brand} {symbol} target rating buy sell recommendation"
    else:
        query = f"{symbol} target rating recommendation outlook"
    # PG: chunks collection gives full passages — better for verdict than QA snippets
    results = store.query(query, k=top_k, collection="chunks")
    return results


def _extract_pdf_passages(path: Path) -> list[dict]:
    """Cheap fallback: read a PDF directly into one passage per page."""
    try:
        from pypdf import PdfReader
    except Exception as exc:
        return [{"text": f"[pypdf import failed: {exc}]", "metadata": {}, "score": 0.0}]
    out: list[dict] = []
    try:
        reader = PdfReader(str(path))
        for i, p in enumerate(reader.pages, start=1):
            try:
                txt = (p.extract_text() or "").strip()
            except Exception:
                txt = ""
            if txt:
                out.append({
                    "text": txt,
                    "metadata": {"page": i, "path": str(path)},
                    "score": 1.0,
                })
    except Exception as exc:
        out.append({"text": f"[pypdf read failed: {exc}]", "metadata": {}, "score": 0.0})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# LLM verdict
# ─────────────────────────────────────────────────────────────────────────────

def _call_llm(prompt_user: str, *, model: str) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "OPENAI_API_KEY not set"}
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key)
    except Exception as exc:
        return {"ok": False, "error": f"openai import failed: {exc}"}

    try:
        resp = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt_user},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        raw = resp.choices[0].message.content or "{}"
        return {"ok": True, "verdict": json.loads(raw), "raw": raw}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _build_prompt(symbol: str, snapshot: dict, passages: list[dict]) -> str:
    # PG: cap each passage to ~1500 chars and total to ~8 KB so the call stays cheap.
    excerpts: list[str] = []
    budget = 8000
    for i, p in enumerate(passages, start=1):
        txt = (p.get("text") or "").strip()
        if not txt:
            continue
        if len(txt) > 1500:
            txt = txt[:1500] + " …"
        meta = p.get("metadata") or {}
        tag = meta.get("source_name") or meta.get("path") or "?"
        block = f"[Passage {i} | {tag}]\n{txt}\n"
        if budget - len(block) < 0:
            break
        excerpts.append(block)
        budget -= len(block)

    snap_json = json.dumps(snapshot, indent=2, default=str)

    return (
        f"SYMBOL: {symbol}\n\n"
        f"==== INTERNAL DB SNAPSHOT (ground truth) ====\n"
        f"{snap_json}\n\n"
        f"==== BROKER REPORT PASSAGES ====\n"
        + ("\n".join(excerpts) if excerpts else "[no passages found]")
        + "\n\n"
        "Now produce the JSON verdict per the schema in the system prompt. "
        "Cross-check broker targets / rationale against the DB returns, stage, "
        "and stance fields. Flag any drift."
    )


# ─────────────────────────────────────────────────────────────────────────────
# public entry point
# ─────────────────────────────────────────────────────────────────────────────

def critique_report(
    symbol: str,
    *,
    source: str = "kb",
    path: str | Path | None = None,
    url: str | None = None,
    top_k: int = 6,
    model: str | None = None,
    brand: str | None = None,
) -> dict[str, Any]:
    """Compose broker excerpts + DB snapshot, ask the LLM for a verdict.

    source=
        "kb"   → semantic search the KB for symbol passages.
        "path" → read the local PDF at `path` directly.
        "url"  → download + read the PDF at `url` (ad-hoc, no KB write).
    """
    sym = symbol.upper().strip()
    chosen_model = model or CRITIQUE_MODEL

    # 1. DB facts
    db_snapshot = fetch_db_snapshot(sym)

    # 2. Broker passages
    passages: list[dict] = []
    if source == "kb":
        passages = _retrieve_kb_passages(sym, top_k=top_k, brand=brand)
    elif source == "path":
        if not path:
            return {"ok": False, "error": "source=path requires --path"}
        passages = _extract_pdf_passages(Path(path).expanduser())
    elif source == "url":
        if not url:
            return {"ok": False, "error": "source=url requires --url"}
        # PG: route via the ingest helper so the doc lands in the KB AND we get passages
        from .ingest import ingest_pdf_url
        ing = ingest_pdf_url(url, source_id="ADHOC", category="broker_research", do_qa=False)
        if not ing.get("ok"):
            return {"ok": False, "error": f"ingest failed: {ing.get('error')}", "ingest": ing}
        passages = _retrieve_kb_passages(sym, top_k=top_k, brand=brand)
    else:
        return {"ok": False, "error": f"unknown source: {source}"}

    # 3. LLM verdict
    prompt = _build_prompt(sym, db_snapshot, passages)
    llm = _call_llm(prompt, model=chosen_model)

    return {
        "ok": llm.get("ok", False),
        "symbol": sym,
        "model": chosen_model,
        "source": source,
        "db_snapshot": db_snapshot,
        "broker_passages": [
            {
                "score": round(float(p.get("score", 0)), 3),
                "source": (p.get("metadata") or {}).get("source_name")
                          or (p.get("metadata") or {}).get("path"),
                "page_start": (p.get("metadata") or {}).get("page_start"),
                "page_end":   (p.get("metadata") or {}).get("page_end"),
                "preview": ((p.get("text") or "")[:240]),
            }
            for p in passages
        ],
        "verdict": llm.get("verdict"),
        "llm_error": llm.get("error"),
    }


__all__ = ["critique_report", "fetch_db_snapshot"]
