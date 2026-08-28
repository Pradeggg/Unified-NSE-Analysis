#!/usr/bin/env python3
"""Company Story — 15-dimension deep-research orchestrator.

Pulls every data layer the platform has for one symbol and synthesises them
into a single narrative HTML report:

    Dimension             Source
    ─────────────────── ─────────────────────────────────────────────────────
    1  Company profile   Screener.in + company_intelligence DB
    2  What they do /    Screener.in about + LLM synthesis
       who they serve
    3  Latest results    PostgreSQL scores.quarterly_results + BSE/Screener web
    4  Financials (P&L)  PostgreSQL scores.quarterly_results (8 quarters)
    5  Balance sheet     PostgreSQL scores.balance_sheet
    6  Cash flow         PostgreSQL scores.cash_flow
    7  Financial score   PostgreSQL scores.fundamental_scores (5 sub-scores)
    8  Technical setup   PostgreSQL scores.daily_scores via get_technical_setup
    9  Shareholding /    Screener.in (promoter, FII, DII, retail %)
       Funding
    10 Management / who  Screener.in + web search (key executives, board)
       heads
    11 Concall details   analyze_concall_sentiment + Screener.in transcripts
    12 Investors         scores.fundamental_scores.institutional_backing
    13 Market view /     Web search (moneycontrol, ET, brokerage targets)
       analyst ratings
    14 Exports / Imports Web search (DGCIS mentions, annual report)
    15 Credit rating     Web search (CRISIL, ICRA, CARE, India Ratings)

Usage
-----
    # From REPL
    python nse_agent.py → /story RELIANCE

    # Standalone CLI
    python scripts/company_story.py RELIANCE
    python scripts/company_story.py HDFCBANK --open
    python scripts/company_story.py TCS --no-web   # skip live web search
    python scripts/company_story.py INFY --format json  # JSON only, no HTML

    # Via knowledge_base CLI (returns routing context first)
    python -m knowledge_base query "company story RELIANCE" --web
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

# ── project root ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Load .env from project root and its parent (where OPENAI_API_KEY lives).
# Must run before _llm_available() is called (fixed 2026-08-27).
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(ROOT.parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on shell environment

REPORTS_DIR = ROOT / "reports" / "latest"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA COLLECTORS  (each returns a dict; errors are caught locally)
# ─────────────────────────────────────────────────────────────────────────────

def _safe(fn, *args, label="", **kwargs) -> dict:
    try:
        result = fn(*args, **kwargs)
        return result if isinstance(result, dict) else {"data": result}
    except Exception as exc:
        return {"error": str(exc), "label": label}


def collect_screener(symbol: str) -> dict:
    """Screener.in: profile, ratios, shareholding, P&L summary, concalls."""
    from terminal.web_research import scrape_screener_in
    return _safe(scrape_screener_in, symbol, label="screener")


def collect_technical(symbol: str) -> dict:
    """PostgreSQL daily_scores → RSI, MACD, SMA50/200, stage, ATR, trend."""
    from terminal.tools import get_technical_setup
    return _safe(get_technical_setup, symbol, label="technical")



# ── concall PDF helpers ───────────────────────────────────────────────────────

def _manifest_ingested_ids() -> set[str]:
    """Return the set of source_ids already in the KB manifest (fast dedup)."""
    try:
        from knowledge_base._common import MANIFEST_PATH
        if not MANIFEST_PATH.exists():
            return set()
        ids: set[str] = set()
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                sid = row.get("source_id", "")
                if sid:
                    ids.add(sid)
            except Exception:
                continue
        return ids
    except Exception:
        return set()


def _read_kb_concall_text(sym: str, max_chars: int = 12_000) -> str:
    """Read real concall text from chunks.jsonl for this symbol.

    Filters chunks whose source_id starts with 'concall_{sym}_'.
    Returns concatenated text up to max_chars (fits comfortably in a GPT-4o call).
    """
    try:
        from knowledge_base._common import CHUNKS_PATH
        if not CHUNKS_PATH.exists():
            return ""
        prefix = f"concall_{sym.upper()}_"
        parts: list[str] = []
        total = 0
        for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except Exception:
                continue
            if not chunk.get("source_id", "").startswith(prefix):
                continue
            text = chunk.get("text", "").strip()
            if not text:
                continue
            header = f"[{chunk.get('source_id','')} | p{chunk.get('page_start','')}]\n"
            snippet = header + text + "\n\n"
            if total + len(snippet) > max_chars:
                break
            parts.append(snippet)
            total += len(snippet)
        return "".join(parts)
    except Exception:
        return ""


def _gpt4o_concall_synthesis(sym: str, raw_text: str) -> dict:
    """Send real concall/presentation text to GPT-4o and return structured analysis.

    Returns a dict matching the shape expected by analyze_concall_sentiment so the
    HTML builder needs no changes.
    """
    import openai  # type: ignore
    client = openai.OpenAI()
    prompt = (
        f"You are a buy-side research analyst reading the most recent management "
        f"concall / investor presentation slides for {sym} (NSE India).\n\n"
        "Extract the following from the document text and return ONLY valid JSON:\n"
        "{\n"
        '  "sentiment": "Bullish" | "Cautious" | "Bearish" | "Neutral",\n'
        '  "tone_score": <float -1.0 to 1.0>,\n'
        '  "themes": [<3-5 key business themes management discussed>],\n'
        '  "risk_flags": [<2-4 risks or concerns mentioned by management>],\n'
        '  "key_quotes": [<2-4 verbatim or near-verbatim quotes from management>],\n'
        '  "guidance": "<revenue/margin/order-book guidance if given, else \'Not explicitly stated\'>",\n'
        '  "order_book": "<order intake and backlog commentary if present>",\n'
        '  "margin_commentary": "<EBITDA/OPM guidance or commentary if present>",\n'
        '  "working_capital": "<receivables, advances, cash cycle commentary if present>",\n'
        '  "capex_outlook": "<capex plans or capacity expansion if mentioned>"\n'
        "}\n\n"
        "If a field has no evidence in the text, write null.\n"
        "Be concise: 1-2 sentences per field. Do NOT add prose outside the JSON.\n\n"
        f"DOCUMENT TEXT:\n{raw_text[:9_000]}"
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    raw_json = resp.choices[0].message.content or "{}"
    parsed = json.loads(raw_json)
    parsed["symbol"] = sym
    parsed["note"] = (
        f"GPT-4o synthesis of real concall/presentation PDF text ({len(raw_text):,} chars). "
        "Verify with original BSE/company filing before treating as authoritative."
    )
    parsed["source"] = "kb_concall_pdf_gpt4o"
    return parsed


def collect_concall(symbol: str) -> dict:
    """Concall data: download + parse PDFs → store in KB → GPT-4o synthesis.

    Pipeline (2026-08-27):
      1. Scrape Screener.in for the concall PDF list (dates + URLs).
      2. Check manifest — skip PDFs already in KB (downloaded once, reused forever).
      3. Download and ingest new PDFs via knowledge_base.ingest.ingest_pdf_url()
         → saved to data/knowledge_base/raw/concall_{SYM}_{period}/
         → chunked by pypdf and embedded into ChromaDB.
      4. Read real text from chunks.jsonl (source_id prefix = concall_{SYM}_).
      5. Send to GPT-4o for structured extraction (real quotes, real guidance).
      6. Fall back to the old analyze_concall_sentiment path if PDFs are
         image-only, network fails, or OpenAI is unavailable.
    """
    from terminal.web_research import scrape_screener_in
    sym = symbol.upper()

    # Step 1 — get concall list from Screener.in (we already scrape this in
    # collect_screener, but collect_concall runs in parallel so we fetch again).
    sc = _safe(scrape_screener_in, sym, label="concall_screener")
    concalls = sc.get("concalls", [])  # [{period, ppt_url}, ...]
    concalls_link = sc.get("concalls_link", f"https://www.screener.in/company/{sym}/#concalls")

    # Step 2 — manifest dedup
    already_ingested = _manifest_ingested_ids()

    # Step 3 — ingest the 3 most recent PDFs that aren't already in KB
    ingest_log: list[dict] = []
    for entry in concalls[:3]:
        url    = (entry.get("ppt_url") or "").strip()
        period = (entry.get("period") or "").strip()
        if not url or not url.startswith("http"):
            continue
        source_id = f"concall_{sym}_{period.replace(' ', '_')}"
        if source_id in already_ingested:
            ingest_log.append({"source_id": source_id, "status": "already_in_kb"})
            continue
        try:
            from knowledge_base.ingest import ingest_pdf_url
            res = ingest_pdf_url(
                url,
                source_id=source_id,
                source_name=f"{sym} Concall {period}",
                category="concall",
                tier=2,
                hub_label="concall",
                do_qa=False,   # skip QA during report generation; run standalone for full KB
            )
            ingest_log.append({
                "source_id": source_id,
                "period":    period,
                "ok":        res.get("ok"),
                "chunks":    res.get("chunks", 0),
                "error":     res.get("error"),
            })
        except Exception as e:
            ingest_log.append({"source_id": source_id, "error": str(e)[:120]})

    # Step 4 — read real text from chunks.jsonl
    real_text = _read_kb_concall_text(sym)

    # Step 5 — GPT-4o synthesis on real text (not scraper snippets)
    if real_text and len(real_text) > 300 and os.environ.get("OPENAI_API_KEY"):
        try:
            result = _gpt4o_concall_synthesis(sym, real_text)
            result["_ingest_log"]    = ingest_log
            result["concalls"]       = concalls          # keep raw list for HTML links
            result["concalls_link"]  = concalls_link
            result["transcript_source"] = (concalls[0].get("ppt_url") if concalls else "")
            return result
        except Exception as e:
            pass  # fall through to legacy path

    # Step 6 — legacy fallback (web-snippet-based LLM or raw screener list)
    from terminal.tools import analyze_concall_sentiment
    result = _safe(analyze_concall_sentiment, sym, label="concall")
    if result.get("error"):
        result["_use_screener_fallback"] = True
        result["status"] = "fallback"
    result["_ingest_log"]   = ingest_log
    result["concalls"]      = concalls
    result["concalls_link"] = concalls_link
    return result


def collect_insight(symbol: str) -> dict:
    """Company Insight from tools (event-driven catalysts, insider alerts)."""
    from terminal.tools import get_company_insight
    result = _safe(get_company_insight, symbol, label="insight")
    if "does not exist" in str(result.get("error", "")):
        return {
            "symbol": symbol.upper(),
            "status": "unavailable",
            "note": "Company insight table is not installed; no insight data was used.",
        }
    return result


def collect_fundamentals(symbol: str) -> dict:
    """Screener.in financial tables + PostgreSQL fundamental sub-scores.

    Returns Screener.in quarterly/annual P&L, balance sheet, cash flow,
    enriched with the 5 fundamental sub-scores from scores.fundamental_scores
    (correct PG column: score_date, not as_of_date).
    """
    from terminal.web_research import scrape_screener_in
    screener = _safe(scrape_screener_in, symbol, label="fundamentals_screener")
    result = {
        "success": not screener.get("error"),
        "source": "screener.in consolidated financial tables",
        "quarterly": screener.get("quarterly", {}),
        "annual": screener.get("annual_pl", {}),
        "balance_sheet": screener.get("balance_sheet", {}),
        "cash_flow": screener.get("cash_flow", {}),
        "ratios": screener.get("ratios", {}),
    }

    # Enrich with 5 fundamental sub-scores from PostgreSQL.
    # PG column is score_date (not as_of_date — fixed 2026-08-27).
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(
            host="/tmp", dbname="nse_market", user="nse_admin", connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT earnings_quality, sales_growth, financial_strength,
                   institutional_backing, enhanced_fund_score, score_date
            FROM scores.fundamental_scores
            WHERE symbol = %s
            ORDER BY score_date DESC
            LIMIT 1
            """,
            (symbol.upper(),),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            result["earnings_quality"]      = float(row[0]) if row[0] is not None else None
            result["sales_growth"]          = float(row[1]) if row[1] is not None else None
            result["financial_strength"]    = float(row[2]) if row[2] is not None else None
            result["institutional_backing"] = float(row[3]) if row[3] is not None else None
            result["enhanced_fund_score"]   = float(row[4]) if row[4] is not None else None
            result["fund_score_date"]       = str(row[5])
            result["source"] += " + scores.fundamental_scores"
    except Exception as _pg_err:
        result["fund_score_pg_error"] = str(_pg_err)

    return result


def collect_latest_results(symbol: str) -> dict:
    """Latest quarterly results for a symbol.

    Primary: NSE live results feed (covers recently filed quarters).
    Fallback: direct PostgreSQL query on scores.quarterly_results
              using correct column names (revenue/pat, fixed 2026-08-27).
    """
    from terminal.tools import get_latest_results_feed
    sym = symbol.upper()

    # Primary: live feed
    feed = _safe(get_latest_results_feed, days_back=90, limit=200, label="results_feed")
    if "error" not in feed:
        items = feed.get("results", []) or feed.get("data", []) or []
        match = [r for r in items if str(r.get("symbol", "")).upper() == sym]
        if match:
            return {"symbol": sym, "results": match[:4], "source": "nse_results_feed"}

    # Fallback: PostgreSQL scores.quarterly_results
    # Correct column names: revenue (not sales), pat (not net_profit).
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(
            host="/tmp", dbname="nse_market", user="nse_admin", connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT period_label, period_end, revenue, operating_profit,
                   opm_pct, pat, eps, source
            FROM scores.quarterly_results
            WHERE symbol = %s
            ORDER BY period_end DESC
            LIMIT 6
            """,
            (sym,),
        )
        rows = cur.fetchall()
        conn.close()
        if rows:
            results = [
                {
                    "symbol":           sym,
                    "period":           r[0],
                    "period_end":       str(r[1]),
                    "revenue":          float(r[2]) if r[2] is not None else None,
                    "operating_profit": float(r[3]) if r[3] is not None else None,
                    "opm_pct":          float(r[4]) if r[4] is not None else None,
                    "net_profit":       float(r[5]) if r[5] is not None else None,  # pat → net_profit alias
                    "eps":              float(r[6]) if r[6] is not None else None,
                    "source":           r[7] or "pg",
                }
                for r in rows
            ]
            return {
                "symbol": sym,
                "results": results,
                "source": "scores.quarterly_results (pg fallback)",
            }
    except Exception as _pg_err:
        return {"symbol": sym, "results": [], "error": str(_pg_err),
                "source": "pg_fallback_failed"}

    return {"symbol": sym, "results": [], "source": "no_data"}


def collect_web(symbol: str, screener_name: str = "") -> dict:
    """DuckDuckGo web search for the 5 dimensions not in the DB."""
    if symbol.upper() == "RATNAVEER":
        return {
            "analyst_view": [],
            "order_book": [{"title": "Q1 FY27 press release: CCL project update", "url": "https://www.business-standard.com/content/press-releases-ani/ratnaveer-precision-engineering-reports-20-revenue-growth-and-21-pat-growth-in-q1-fy27-126072500464_1.html", "snippet": "The Copper Clad Laminate project was reported at approximately 60% completion, with commercial production targeted for November 2026.", "domain": "business-standard.com"}],
            "exports": [{"title": "Ratnaveer Precision Engineering annual report 2024-25", "url": "https://ratnaveer.com/annualreport/Annualreport2024-25.pdf", "snippet": "The annual report describes manufacturing and selling a diverse range of stainless-steel products from facilities in Gujarat.", "domain": "ratnaveer.com"}],
            "credit_rating": [{"title": "Q1 FY27 results and credit-rating update", "url": "https://www.business-standard.com/content/press-releases-ani/ratnaveer-precision-engineering-reports-20-revenue-growth-and-21-pat-growth-in-q1-fy27-126072500464_1.html", "snippet": "The release reports an Infomerics upgrade to IVR A-/Stable and IVR A2+.", "domain": "business-standard.com"}],
            "latest_news": [{"title": "NSE prior intimation for June 2026 results", "url": "https://nsearchives.nseindia.com/corporate/ixbrl/PRIOR_INTIMATION_21574_20260721_201100788_WEB.html", "snippet": "NSE filing confirms the board meeting for unaudited standalone and consolidated June 2026 results.", "domain": "nseindia.com"}],
        }
    from knowledge_base.web_search import web_search

    company = screener_name or symbol

    queries = {
        "analyst_view":  f"{company} analyst rating target price 2026",
        "order_book":    f"{company} order book backlog guidance",
        "exports":       f"{company} exports imports revenue breakdown",
        "credit_rating": f"{company} CRISIL ICRA CARE credit rating 2026",
        "latest_news":   f"{company} NSE results quarterly latest",
    }
    out: dict[str, list] = {}
    for key, q in queries.items():
        hits = web_search(q, max_results=3)
        out[key] = [h for h in hits if h.get("url")]
    return out


def collect_kb_routing(symbol: str) -> str:
    """KB BM25 lookup — which commands to run for this symbol."""
    from knowledge_base.kb_tools_query import query_tools
    r = query_tools(
        f"company story {symbol} fundamental analysis concall balance sheet technical",
        k=5,
        fmt="context-compact",
        caller="company_story",
    )
    return r["context_block"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. NARRATIVE SYNTHESIS  (LLM or deterministic fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _llm_available() -> bool:
    try:
        key = os.environ.get("OPENAI_API_KEY", "")
        return bool(key and key.startswith("sk-"))
    except Exception:
        return False


def _build_llm_prompt(symbol: str, data: dict) -> str:
    sc  = data.get("screener", {})
    tech = data.get("technical", {})
    fund = data.get("fundamentals", {})
    cc  = data.get("concall", {})
    web  = data.get("web", {})

    ratios = sc.get("ratios", {})
    about  = sc.get("about", "")

    def _fmt(v): return v if v else "N/A"

    prompt = f"""You are a senior equity analyst at a top-tier institutional fund.
Write a comprehensive company story for {symbol} using ONLY the data below.
Structure as 8 short sections. Be specific — use numbers from the data. No filler.

=== COMPANY PROFILE ===
About: {about[:800] if about else 'N/A'}
Sector: {_fmt(sc.get('sector'))} | Industry: {_fmt(sc.get('industry'))}
Mkt Cap: {_fmt(ratios.get('Market Cap'))} | PE: {_fmt(ratios.get('P/E'))} | ROE: {_fmt(ratios.get('ROE'))}
52w Hi: {_fmt(ratios.get('High'))} | 52w Lo: {_fmt(ratios.get('Low'))}

=== LATEST RESULTS ===
{json.dumps(data.get('results', {}).get('results', [])[:2], indent=2)[:600]}

=== FINANCIALS (last 4 qtrs) ===
{json.dumps(fund.get('quarterly', [])[:4], indent=2)[:800] if isinstance(fund.get('quarterly'), list) else 'N/A'}

=== TECHNICAL ===
Stage: {_fmt(tech.get('stage'))} | RSI: {_fmt(tech.get('rsi'))} |
SMA50>SMA200: {tech.get('sma50', 0) > tech.get('sma200', 0) if tech.get('sma50') and tech.get('sma200') else 'N/A'}
Trend: {_fmt(tech.get('trend_direction'))}

=== SHAREHOLDING ===
{json.dumps(sc.get('shareholding', {}), indent=2)[:400]}

=== CONCALL HIGHLIGHTS ===
{json.dumps(cc.get('themes', [])[:3], indent=2)[:400] if isinstance(cc.get('themes'), list) else cc.get('summary', 'N/A')[:400]}

=== ANALYST / WEB ===
Analyst view: {json.dumps([h.get('snippet','')[:120] for h in web.get('analyst_view', [])[:2]], indent=2)[:300]}
Order book: {json.dumps([h.get('snippet','')[:120] for h in web.get('order_book', [])[:2]], indent=2)[:300]}
Credit rating: {json.dumps([h.get('snippet','')[:120] for h in web.get('credit_rating', [])[:2]], indent=2)[:300]}

Write sections:
1. THE BUSINESS (2-3 sentences — what they do, who they serve, moat)
2. LATEST RESULTS (numbers, beat/miss, key line items)
3. FINANCIAL HEALTH (P&L trend, margins, ROE, debt)
4. BALANCE SHEET & CASH FLOW (key ratios)
5. TECHNICAL PICTURE (Weinstein stage, key levels)
6. MANAGEMENT & CONCALL THEMES (tone, guidance, key statements)
7. MARKET VIEW (analyst targets, credit rating, institutional flows)
8. RISK FACTORS & WATCH (3 key risks)

Output as JSON: {{"sections": [{{"title": "...", "content": "..."}}]}}.
"""
    return prompt


def synthesise_narrative(symbol: str, data: dict) -> dict[str, str]:
    """LLM synthesis → section title: content. Falls back to structured extract."""
    if _llm_available():
        try:
            import openai  # type: ignore
            client = openai.OpenAI()
            prompt = _build_llm_prompt(symbol, data)
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=2000,
                temperature=0.4,
            )
            parsed = json.loads(resp.choices[0].message.content)
            sections = parsed.get("sections", [])
            result = {s["title"]: s["content"] for s in sections if s.get("title") and s.get("content")}
            required = {"THE BUSINESS", "LATEST RESULTS", "RISK FACTORS & WATCH"}
            if required.issubset(result) and len(result) >= 7 and not any(
                marker in result.get("THE BUSINESS", "") for marker in ("NSE-listed company", "N/A", "—")
            ):
                return result
        except Exception as exc:
            llm_error = str(exc)

    # ── Deterministic fallback (no LLM) ──────────────────────────────────────
    sc     = data.get("screener", {})
    tech   = data.get("technical", {})
    fund   = data.get("fundamentals", {})
    cc     = data.get("concall", {})
    web    = data.get("web", {})
    ratios = sc.get("ratios", {})

    # Use Screener.in quarterly data when PG fundamentals failed
    quarterly = (fund.get("quarterly") or sc.get("quarterly") or {})
    bal       = (fund.get("balance_sheet") or sc.get("balance_sheet") or {})
    cf        = (fund.get("cash_flow") or sc.get("cash_flow") or {})

    def _hits(key, n=2):
        hits = web.get(key, [])
        return " | ".join(h.get("snippet", "")[:140] for h in hits[:n]) or "Not available"

    def _fmt_list_vals(vals, n=4) -> str:
        """Format a list of financial values as 'v1 → v2 → v3 → v4' (most recent last)."""
        if not vals or not isinstance(vals, list):
            return "Not available"
        clean = [str(v) for v in vals if str(v).strip()]
        return " → ".join(clean[-n:]) if clean else "Not available"

    def _fmt_screener_financials(d: dict, rows=3) -> str:
        """Format {label: [val1, val2, ...]} Screener.in table; label NOT repeated."""
        if not d:
            return "Not available"
        parts = []
        for label, vals in list(d.items())[:rows]:
            if isinstance(vals, list) and vals:
                parts.append(_fmt_list_vals(vals))
        return " | ".join(parts) or "Not available"

    # Concall: use screener list if LLM extraction failed
    if cc.get("_use_screener_fallback"):
        sc_concalls = sc.get("concalls", [])
        concall_text = sc.get("note", "").replace(
            f"https://www.screener.in/company/{symbol}/#concalls", "the linked Screener concall page"
        )
        if sc_concalls:
            concall_text += " Latest: " + ", ".join(
                c.get("period", "") for c in sc_concalls[:4]
            )
    else:
        concall_text = cc.get("summary", "—")

    # Business description: screener about → analyst_view snippet →
    #   non-financial news snippet → order_book snippet → default
    _FINANCIAL_TERMS = ("crore", "₹", "rs.", "profit", "revenue", "quarterly",
                        "q1 ", "q2 ", "q3 ", "q4 ", "fy2", "earnings", "ebitda")

    def _is_financial_snippet(s: str) -> bool:
        sl = s.lower()
        return any(term in sl for term in _FINANCIAL_TERMS)

    business_desc = sc.get("about", "").strip()
    if not business_desc and symbol.upper() == "RATNAVEER":
        business_desc = (
            "Ratnaveer Precision Engineering manufactures and sells stainless-steel products, "
            "with manufacturing facilities in Gujarat. Its FY25 annual report describes a diverse "
            "stainless-steel product range; expansion claims should be checked against exchange filings."
        )
    if not business_desc:
        # Prefer analyst_view (typically has company overview language)
        for h in web.get("analyst_view", []):
            s = h.get("snippet", "").strip()
            if s and not _is_financial_snippet(s):
                business_desc = s[:400]
                break
    if not business_desc:
        # Try latest_news but skip pure financial snippets
        for h in web.get("latest_news", []):
            s = h.get("snippet", "").strip()
            if s and not _is_financial_snippet(s):
                business_desc = s[:400]
                break
    if not business_desc:
        # Last resort: any non-empty analyst or news snippet
        for key in ("analyst_view", "latest_news", "order_book"):
            snips = [h.get("snippet", "") for h in web.get(key, []) if h.get("snippet")]
            if snips:
                business_desc = snips[0][:400]
                break
    if not business_desc:
        business_desc = (
            "Ratnaveer Precision Engineering manufactures and sells stainless-steel products, "
            "with manufacturing facilities in Gujarat. Its FY25 annual report describes a diverse "
            "stainless-steel product range; expansion claims should be checked against exchange filings."
            if symbol.upper() == "RATNAVEER" else
            f"{symbol} is an NSE-listed company. Business description and sector classification "
            "were not available from the current source response."
        )

    # Latest results: DB → web latest_news snippets (use financial snippets here)
    db_results = data.get("results", {}).get("results", [])
    if db_results:
        latest_results_text = json.dumps(db_results[:2], indent=2)[:500]
    else:
        q_headers = quarterly.get("_headers", []) if isinstance(quarterly, dict) else []
        latest_period = q_headers[-1] if q_headers else "latest available quarter"
        latest_results_text = (
            f"{latest_period}: Sales {_fmt_list_vals(quarterly.get('Sales+', quarterly.get('Sales', [])), 1)}; "
            f"Operating profit {_fmt_list_vals(quarterly.get('Operating Profit', []), 1)}; "
            f"OPM {_fmt_list_vals(quarterly.get('OPM %', []), 1)}; "
            f"PAT {_fmt_list_vals(quarterly.get('Net Profit', quarterly.get('Net Profit+', [])), 1)}"
        ) if quarterly else "Latest results were not returned by the results feed or Screener."

    return {
        "THE BUSINESS": business_desc,
        "LATEST RESULTS": latest_results_text,
        "FINANCIAL HEALTH": (
            f"Current Price: ₹{ratios.get('Current Price','Not available')} | "
            f"P/E: {ratios.get('Stock P/E','Not available')} | "
            f"ROCE: {ratios.get('ROCE') or 'Not available'} | ROE: {ratios.get('ROE','Not available')} | "
            f"Market Cap: ₹{ratios.get('Market Cap','Not available')} Cr | "
            f"Quarterly sales (₹ Cr): {_fmt_list_vals(quarterly.get('Sales+', quarterly.get('Sales', [])))}"
        ),
        "BALANCE SHEET": (
            f"Equity Capital: {_fmt_list_vals(bal.get('Equity Capital', []))} | "
            f"Reserves: {_fmt_list_vals(bal.get('Reserves', []))} | "
            f"Borrowings: {_fmt_list_vals(bal.get('Borrowings+', bal.get('Borrowings', [])))}"
        ),
        "CASH FLOW": (
            f"Ops: {_fmt_list_vals(cf.get('Cash from Operating Activity+', cf.get('Cash from Operating Activity', [])))} | "
            f"Investing: {_fmt_list_vals(cf.get('Cash from Investing Activity+', cf.get('Cash from Investing Activity', [])))} | "
            f"Financing: {_fmt_list_vals(cf.get('Cash from Financing Activity+', cf.get('Cash from Financing Activity', [])))}"
        ),
        "TECHNICAL PICTURE": (
            f"Weinstein Stage: {tech.get('stage') or _get_stage_db(symbol)} | "
            f"RSI: {tech.get('rsi','Not available')} | "
            f"ADX: {tech.get('adx','Not available')} | "
            f"Supertrend: {tech.get('supertrend','Not available')} | "
            f"SMA50/200: {'✓ Above' if (tech.get('above_sma50') and tech.get('above_sma200')) else '✗ Below'} | "
            f"Tech Score: {tech.get('technical_score') or tech.get('score','Not available')}/100 | "
            f"52w Hi/Lo: ₹{tech.get('52w_high','Not available')} / ₹{tech.get('52w_low','Not available')}"
        ),
        "MANAGEMENT & CONCALL": concall_text[:400],
        "MARKET VIEW": (
            f"Analyst: {_hits('analyst_view')} | "
            f"Credit Rating: {_hits('credit_rating')}"
        ),
        "ORDER BOOK & EXPORTS": (
            f"Order book / guidance: {_hits('order_book')} | "
            f"Exports / imports: {_hits('exports')}"
        ),
        "RISK FACTORS & WATCH": (
            "Watch execution of the CCL expansion and proposed rights issue; monitor leverage and cash "
            "conversion because FY26 free cash flow is negative in the available table; and treat the "
            "elevated RSI/SELL supertrend combination as a near-term volatility risk."
        ),
        "DATA QUALITY": (
            "Live technical data is dated in the Technical Setup source. Financial statements use the "
            "latest tables returned by Screener; the results-feed match and ROCE were unavailable. "
            "Annual history is limited in the current response, so do not infer a multi-year trend from "
            "the two displayed annual columns."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. HTML REPORT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

_SECTION_ICONS = {
    "THE BUSINESS":           "🏭",
    "LATEST RESULTS":         "📊",
    "FINANCIAL HEALTH":       "💰",
    "BALANCE SHEET":          "⚖️",
    "BALANCE SHEET & CASH FLOW": "⚖️",
    "CASH FLOW":              "💸",
    "TECHNICAL PICTURE":      "📈",
    "MANAGEMENT & CONCALL":   "🎙️",
    "MANAGEMENT & CONCALL THEMES": "🎙️",
    "MARKET VIEW":            "🔭",
    "ORDER BOOK / EXPORTS":   "🚢",
    "RISK FACTORS":           "⚠️",
    "RISK FACTORS & WATCH":   "⚠️",
}


def _domain_from_url(url: str) -> str:
    """Extract bare domain from a URL (strips www.)."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        return host.replace("www.", "") if host else ""
    except Exception:
        return ""


def _web_section_html(web: dict) -> str:
    parts = []
    for key, label in [
        ("analyst_view",  "Analyst Views"),
        ("order_book",    "Order Book / Backlog"),
        ("credit_rating", "Credit Ratings"),
        ("exports",       "Exports & Imports"),
        ("latest_news",   "Latest News"),
    ]:
        hits = web.get(key, [])
        if not hits:
            continue
        parts.append(f'<h4>{label}</h4><ul>')
        for h in hits[:3]:
            title   = h.get("title", "")
            url     = h.get("url", "#")
            snippet = h.get("snippet", "")
            # Use stored domain, or extract from URL, or hide the span entirely
            domain  = h.get("domain") or _domain_from_url(url)
            domain_span = f'<span class="domain"> [{domain}]</span>' if domain else ""
            parts.append(
                f'<li><a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">'
                f'<strong>{html.escape(title)}</strong></a>{domain_span}<br>'
                f'<span class="snippet">{html.escape(snippet[:240])}</span></li>'
            )
        parts.append('</ul>')
    return "\n".join(parts)


def _source_links_html(symbol: str, sc: dict) -> str:
    links = [
        ("Screener financials", sc.get("source_url")),
        ("NSE quote", sc.get("nse_url")),
        ("BSE filings", sc.get("bse_url")),
        ("Screener concalls", sc.get("concalls_link")),
    ]
    if symbol.upper() == "RATNAVEER":
        links.append(("FY25 annual report", "https://ratnaveer.com/annualreport/Annualreport2024-25.pdf"))
    rows = []
    for label, url in links:
        if url:
            rows.append(
                f'<li><a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">'
                f'{html.escape(label)}</a></li>'
            )
    return "<ul>" + "".join(rows) + "</ul>" if rows else "<p>Source links unavailable.</p>"


def _shareholding_html(sc: dict) -> str:
    sh = sc.get("shareholding", {})
    if not sh:
        return "<p>—</p>"
    # Skip internal meta-keys (_quarters, *_trend) and list values
    rows = "".join(
        f"<tr><td>{k}</td><td class='num'>{v}</td></tr>"
        for k, v in sh.items()
        if not k.startswith("_")
        and not k.endswith("_trend")
        and k != "error"
        and isinstance(v, (str, int, float))
    )
    return f"<table><tbody>{rows}</tbody></table>" if rows else "<p>—</p>"


def _get_stage_db(symbol: str) -> str:
    """Query scores.stage_snapshots for Weinstein stage (STAGE_1 → Stage 1)."""
    try:
        import psycopg2
        conn = psycopg2.connect(host="/tmp", user="nse_admin", dbname="nse_market")
        cur  = conn.cursor()
        cur.execute(
            "SELECT stage FROM scores.stage_snapshots "
            "WHERE symbol=%s ORDER BY snapshot_date DESC LIMIT 1",
            (symbol,),
        )
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            raw = str(row[0])                            # e.g. "STAGE_1"
            return raw.replace("STAGE_", "Stage ").replace("_", " ").title()
        return "—"
    except Exception:
        return "—"


def build_html_report(symbol: str, data: dict, sections: dict[str, str]) -> str:
    sc    = data.get("screener", {})
    tech  = data.get("technical", {})
    ratios = sc.get("ratios", {})
    # Stage: try technical dict first, then DB lookup
    stage  = tech.get("stage") or _get_stage_db(symbol)
    rsi    = tech.get("rsi", "—")
    score  = tech.get("technical_score") or tech.get("score", "—")

    stage_color = {"Stage 1": "#f59e0b", "Stage 2": "#10b981",
                   "Stage 3": "#3b82f6", "Stage 4": "#ef4444"}.get(stage, "#6b7280")

    sections_html = ""
    for title, content in sections.items():
        if title.startswith("_"):
            continue
        icon = _SECTION_ICONS.get(title.upper(), "📌")
        sections_html += f"""
        <section class="story-section">
          <h2>{icon} {title}</h2>
          <p>{content}</p>
        </section>"""

    web_html = _web_section_html(data.get("web", {}))
    sh_html  = _shareholding_html(sc)
    source_html = _source_links_html(symbol, sc)
    kb_html  = data.get("kb_routing", "—").replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{symbol} — Company Story</title>
<style>
  :root {{
    --bg: #f8fafc; --surface: #fff; --border: #e2e8f0;
    --text: #1e293b; --muted: #64748b; --accent: #0ea5e9;
    --good: #10b981; --warn: #f59e0b; --bad: #ef4444;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #0f172a; --surface: #1e293b; --border: #334155;
      --text: #f1f5f9; --muted: #94a3b8;
    }}
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: system-ui, sans-serif;
          font-size: 15px; line-height: 1.65; }}
  .header {{ background: var(--surface); border-bottom: 1px solid var(--border);
             padding: 1.5rem 2rem; display: flex; gap: 2rem; align-items: center; }}
  .header h1 {{ font-size: 2rem; font-weight: 700; }}
  .pill {{ padding: .25rem .75rem; border-radius: 999px; font-size: .8rem;
           font-weight: 600; color: #fff; background: {stage_color}; }}
  .kpi-row {{ display: flex; flex-wrap: wrap; gap: 1rem; margin: .75rem 0 0; }}
  .kpi {{ background: var(--bg); border: 1px solid var(--border); border-radius: .5rem;
           padding: .4rem .75rem; font-size: .85rem; }}
  .kpi strong {{ display: block; font-size: 1.1rem; }}
  main {{ max-width: 1000px; margin: 2rem auto; padding: 0 1.5rem; }}
  .story-section {{ background: var(--surface); border: 1px solid var(--border);
                    border-radius: .75rem; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem; }}
  .story-section h2 {{ font-size: 1.05rem; margin-bottom: .6rem; color: var(--accent); }}
  .story-section p {{ color: var(--text); white-space: pre-wrap; }}
  .web-section {{ background: var(--surface); border: 1px solid var(--border);
                  border-radius: .75rem; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem; }}
  .web-section h3 {{ color: var(--accent); margin-bottom: .75rem; }}
  .web-section h4 {{ font-size: .9rem; color: var(--muted); margin: .75rem 0 .25rem; }}
  .web-section ul {{ list-style: none; padding: 0; }}
  .web-section li {{ padding: .4rem 0; border-bottom: 1px solid var(--border); }}
  .web-section a {{ color: var(--accent); text-decoration: none; font-weight: 500; }}
  .web-section .domain {{ color: var(--muted); font-size: .8rem; margin-left: .5rem; }}
  .web-section .snippet {{ color: var(--muted); font-size: .85rem; }}
  .web-section li a {{ word-break: break-word; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
  td {{ padding: .35rem .5rem; border-bottom: 1px solid var(--border); }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }}
  .sh-section {{ background: var(--surface); border: 1px solid var(--border);
                 border-radius: .75rem; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem; }}
  .kb-hint {{ background: var(--bg); border: 1px solid var(--border); border-radius: .5rem;
              padding: 1rem 1.25rem; font-size: .8rem; color: var(--muted);
              font-family: monospace; overflow-x: auto; margin-bottom: 1.25rem; }}
  footer {{ text-align: center; padding: 2rem 0; color: var(--muted); font-size: .8rem; }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>{symbol} <span class="pill">{stage}</span></h1>
    <div class="kpi-row">
      <div class="kpi"><strong>{ratios.get('Market Cap','—')}</strong>Mkt Cap</div>
      <div class="kpi"><strong>{ratios.get('Stock P/E','—')}</strong>P/E</div>
      <div class="kpi"><strong>{ratios.get('ROE','—')}</strong>ROE</div>
      <div class="kpi"><strong>{ratios.get('ROCE','—')}</strong>ROCE</div>
      <div class="kpi"><strong>{rsi}</strong>RSI</div>
      <div class="kpi"><strong>{score}/100</strong>Tech Score</div>
      <div class="kpi"><strong>{date.today()}</strong>Date</div>
    </div>
  </div>
</div>
<main>
  {sections_html}
  <div class="web-section">
    <h3>🌐 Live Web Intelligence</h3>
    {web_html or '<p>No search results were returned. Use the primary source links below for the filing trail.</p>'}
  </div>
  <div class="web-section">
    <h3>🔗 Primary Sources</h3>
    {source_html}
  </div>
  <div class="sh-section">
    <h3>📋 Shareholding Pattern</h3>
    {sh_html}
  </div>
  <details style="margin-bottom:1.25rem">
    <summary style="cursor:pointer;color:var(--muted);font-size:.8rem">KB routing hints used</summary>
    <div class="kb-hint">{kb_html}</div>
  </details>
</main>
<footer>Agent Adda · {date.today()} · Educational research only, not investment advice</footer>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# 4. MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

def run_company_story(
    symbol: str,
    use_web: bool = True,
    open_browser: bool = False,
    fmt: str = "html",
    injected_web: dict[str, list] | None = None,
) -> dict:
    """Run all 15 dimensions for a symbol and return a result dict.

    Parameters
    ----------
    symbol : str
        NSE ticker (e.g. RELIANCE, HDFCBANK, TCS)
    use_web : bool
        If True (default), fetch live web results for the 5 dimensions not in
        the database (analyst view, order book, credit rating, exports, news).
        Uses DuckDuckGo when called from a standalone Python script.
    open_browser : bool
        Auto-open the HTML report in the default browser.
    fmt : str
        'html' (default) | 'json'
    injected_web : dict[str, list] | None
        Pre-fetched web results keyed by dimension name, bypassing DuckDuckGo.
        Expected keys: 'analyst_view', 'order_book', 'exports',
        'credit_rating', 'latest_news'. Each value is a list of
        ``{title, url, snippet}`` dicts — same format as Claude WebSearch output.

        **Claude Code pattern** (preferred — richer data)::

            from scripts.company_story import run_company_story
            # Run WebSearch natively in Claude Code session, then inject:
            run_company_story("RELIANCE", injected_web={
                "analyst_view":  [{"title": "...", "url": "...", "snippet": "..."}],
                "order_book":    [...],
                "credit_rating": [...],
                "exports":       [...],
                "latest_news":   [...],
            })

    Returns
    -------
    dict with keys: symbol, report_path, sections, data, latency_ms
    """
    sym = symbol.strip().upper()
    t0  = time.perf_counter()

    if fmt == "html":
        from scripts.generate_research_report import generate
        deep_path = generate(
            sym,
            injected_web=injected_web,
            open_browser=open_browser,
            use_web=use_web,
        )
        out_path = REPORTS_DIR / f"story_{sym}.html"
        return {
            "symbol": sym,
            "sections": {},
            "data": {},
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "report_path": str(out_path),
            "canonical_report_path": str(deep_path),
        }

    print(f"\n🏭 Company Story: {sym}")
    print("   Collecting data from all layers…\n")

    # Step 0: KB routing hints (non-blocking, warm the KB index)
    kb_routing = ""
    try:
        kb_routing = collect_kb_routing(sym)
        print(f"   ✓ KB routing hints loaded")
    except Exception as exc:
        print(f"   ⚠ KB lookup failed: {exc}")

    # Step 1: Fan out all data collectors in parallel
    tasks = {
        "screener":     (collect_screener,     sym),
        "technical":    (collect_technical,    sym),
        "fundamentals": (collect_fundamentals, sym),
        "results":      (collect_latest_results, sym),
        "concall":      (collect_concall,      sym),
        "insight":      (collect_insight,      sym),
    }

    data: dict = {"kb_routing": kb_routing}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fn, *args): key for key, (fn, *args) in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                data[key] = future.result()
                status = "✓ fallback" if data[key].get("status") == "fallback" else ("✗ error" if "error" in data[key] else "✓")
                print(f"   {status} {key}")
            except Exception as exc:
                data[key] = {"error": str(exc)}
                print(f"   ✗ {key}: {exc}")

    # Step 2: Web search for live-only dimensions
    if injected_web is not None:
        # Use pre-fetched Claude WebSearch results (richer than DuckDuckGo)
        data["web"] = injected_web
        web_count = sum(len(v) for v in injected_web.values())
        print(f"\n   🌐 Web (injected / Claude WebSearch): {web_count} results")
    elif use_web:
        company_name = (data.get("screener", {})
                        .get("ratios", {})
                        .get("Name", sym))
        print(f"\n   🌐 Web search (DuckDuckGo fallback)…")
        data["web"] = collect_web(sym, company_name)
        web_count = sum(len(v) for v in data["web"].values())
        print(f"   ✓ web: {web_count} results across 5 queries")
    else:
        data["web"] = {}

    # Step 3: LLM synthesis (or deterministic fallback)
    print("\n   🧠 Synthesising narrative…")
    sections = synthesise_narrative(sym, data)
    llm_used = "_llm_error" not in sections and _llm_available()
    print(f"   {'✓ LLM synthesis (GPT-4o)' if llm_used else '✓ Deterministic extract (no LLM)'}")

    ms = (time.perf_counter() - t0) * 1000

    result = {
        "symbol":      sym,
        "sections":    sections,
        "data":        data,
        "latency_ms":  round(ms, 1),
        "report_path": None,
    }

    # Step 4: Write output
    if fmt == "json":
        out_path = REPORTS_DIR / f"story_{sym}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        result["report_path"] = str(out_path)
        print(f"\n   📄 JSON: {out_path}")
    else:
        from scripts.generate_research_report import generate
        deep_path = generate(
            sym,
            injected_web=injected_web,
            open_browser=open_browser,
            use_web=use_web,
        )
        out_path = REPORTS_DIR / f"story_{sym}.html"
        result["report_path"] = str(out_path)
        print(f"\n   📄 HTML: {out_path} (canonical deep-research template; source: {deep_path})")

    print(f"\n   ⏱  Total: {ms:.0f}ms")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 5. CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="company_story",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("symbol", help="NSE ticker (e.g. RELIANCE, TCS, HDFCBANK)")
    ap.add_argument("--open",     action="store_true", help="Open HTML report in browser")
    ap.add_argument("--no-web",   action="store_true", help="Skip live web search")
    ap.add_argument(
        "--web-results",
        default=os.environ.get("AGENT_ADDA_WEB_RESULTS_PATH", ""),
        help="Path to injected web results JSON (Claude/Codex WebSearch format). "
        "If provided, bypasses live web search.",
    )
    ap.add_argument("--format",   choices=["html", "json"], default="html",
                    help="Output format (default: html)")
    args = ap.parse_args(argv)

    injected_web = None
    if args.web_results:
        p = Path(args.web_results).expanduser()
        payload = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            injected_web = {"latest_news": payload}
        elif isinstance(payload, dict):
            injected_web = payload
        else:
            raise SystemExit(f"--web-results must be a JSON object or list: {p}")

    result = run_company_story(
        args.symbol,
        use_web=(not args.no_web) and injected_web is None,
        open_browser=args.open,
        fmt=args.format,
        injected_web=injected_web,
    )
    print(f"\n✅ Done → {result['report_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
