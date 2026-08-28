#!/usr/bin/env python3
"""Refresh the standalone portfolio consolidation HTML from latest portfolio evidence."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = Path("/private/tmp/portfolio_consolidation_report.html")
DEFAULT_EVIDENCE = ROOT / "reports" / "portfolio" / "latest_portfolio_ric_sherlock.json"


def _num(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _series_last_growth(table: Any, key: str) -> float | None:
    if not isinstance(table, dict) or not isinstance(table.get(key), list):
        return None
    values = [_num(v) for v in table[key]]
    values = [v for v in values if v is not None]
    if len(values) < 2 or values[-2] == 0:
        return None
    return round((values[-1] / values[-2] - 1) * 100, 1)


def _quarter_rows(fund: dict[str, Any]) -> list[dict[str, Any]]:
    q = fund.get("quarterly") if isinstance(fund.get("quarterly"), dict) else {}
    periods = q.get("periods") or q.get("Period") or q.get("period") or []
    sales = q.get("Sales+") or q.get("Revenue") or []
    profit = q.get("Net Profit+") or q.get("Net Profit") or []
    result = []
    for idx, label in enumerate(periods[-8:]):
        src_idx = len(periods) - min(8, len(periods)) + idx
        result.append(
            {
                "label": str(label),
                "end": str(label),
                "pat": _num(profit[src_idx]) if src_idx < len(profit) else None,
                "rev": _num(sales[src_idx]) if src_idx < len(sales) else None,
            }
        )
    return result


def _shareholding_text(fund: dict[str, Any]) -> str:
    data = fund.get("shareholding")
    if not isinstance(data, dict):
        return "—"
    parts = []
    for key in ("Promoters", "FIIs", "DIIs", "Government", "Public"):
        values = data.get(key)
        value = values[-1] if isinstance(values, list) and values else values
        if value not in (None, "", "—"):
            parts.append(f"{key} {value}")
    return " | ".join(parts) or "—"


def _ratios_text(fund: dict[str, Any]) -> str:
    ratios = fund.get("ratios") if isinstance(fund.get("ratios"), dict) else {}
    wanted = ("Stock P/E", "ROCE", "ROE", "Dividend Yield", "Book Value", "Market Cap")
    return "; ".join(f"{key}: {ratios[key]}" for key in wanted if ratios.get(key) not in (None, "")) or "—"


def _chart_payload(item: dict[str, Any]) -> dict[str, Any]:
    snap = item.get("snapshot") or {}
    tech = item.get("technical") or {}
    bars = ((item.get("chart_history") or {}).get("bars") or [])
    candles, volume = [], []
    for bar in bars:
        date = str(bar.get("d") or "")[:10]
        close = _num(bar.get("c"))
        if not date or close is None:
            continue
        candles.append({"time": date, "open": _num(bar.get("o")) or close, "high": _num(bar.get("h")) or close, "low": _num(bar.get("l")) or close, "close": close})
        volume.append({"time": date, "value": _num(bar.get("v")) or 0, "color": "#14b8a680" if close >= (_num(bar.get("o")) or close) else "#f43f5e80"})
    def line(key: str) -> list[dict[str, Any]]:
        return [{"time": str(b.get("d"))[:10], "value": _num(b.get(key))} for b in bars if b.get("d") and _num(b.get(key)) is not None]
    return {
        "snapshot": {
            "price": _num(snap.get("price")), "sma20": _num(tech.get("sma20")), "sma50": _num(tech.get("sma50")),
            "sma200": _num(tech.get("sma200")), "rsi": _num(tech.get("rsi") or snap.get("rsi")),
            "macd": tech.get("macd"), "supertrend": tech.get("supertrend"), "adx": _num(tech.get("adx")),
            "vol_ratio": _num(tech.get("volume_ratio")), "technical_score": _num(snap.get("technical_score")),
            "stage": str(snap.get("stage") or "—").replace("STAGE_", "S"), "signal": snap.get("trading_signal") or "—",
            "as_of": snap.get("snapshot_date") or tech.get("as_of") or "—",
        },
        "candles": candles, "sma20": line("s20"), "sma50": line("s50"), "sma200": line("s200"), "volume": volume,
    }


def _replace_json_const(source: str, name: str, value: Any) -> str:
    match = re.search(rf"(?m)^const {re.escape(name)} = ", source)
    if not match:
        raise RuntimeError(f"Missing JavaScript constant: {name}")
    _, end = json.JSONDecoder().raw_decode(source, match.end())
    return source[: match.end()] + json.dumps(value, ensure_ascii=False, separators=(",", ":")) + source[end:]


def refresh(template: Path, evidence_path: Path, output: Path) -> dict[str, Any]:
    items = json.loads(evidence_path.read_text(encoding="utf-8"))
    protected = {"ICICIBANK", "HDFCBANK", "TATASTEEL", "COFORGE", "FEDERALBNK", "ATHERENERG", "ENDURANCE"}
    rows, charts = [], {}
    for item in items:
        portfolio = item.get("portfolio") or {}
        if str(portfolio.get("isin") or "").upper().startswith("INF"):
            continue
        snap = item.get("snapshot") or {}
        fund = item.get("fundamentals") or {}
        ratios = fund.get("ratios") if isinstance(fund.get("ratios"), dict) else {}
        score = _num(snap.get("investment_score")) or 0
        fund_score = _num(snap.get("enhanced_fund_score"))
        fq = "STRONG" if fund_score is not None and fund_score >= 60 else "DECENT" if fund_score is not None and fund_score >= 40 else "WEAK"
        stage = str(snap.get("stage") or "UNKNOWN").replace("STAGE_", "S")
        signal = str(snap.get("trading_signal") or "—")
        tech_score = _num(snap.get("technical_score")) or 0
        if stage == "S4" and signal == "SELL" and fq == "WEAK": tranche = "T1"
        elif stage == "S4" or signal == "SELL": tranche = "T2"
        elif score < 50 or tech_score < 40: tranche = "T3"
        else: tranche = "KEEP"
        qty = _num(portfolio.get("qty")) or 0
        avg = _num(portfolio.get("avg_cost")) or 0
        ltp = _num(portfolio.get("broker_price")) or _num(snap.get("price")) or 0
        pnl_pct = _num(portfolio.get("unrealized_pct"))
        annual = fund.get("annual_pl") if isinstance(fund.get("annual_pl"), dict) else {}
        row = {
            "rank": 0, "sym": item["symbol"], "company": portfolio.get("company_name") or snap.get("company_name") or item["symbol"],
            "score": round(score, 1), "fq": fq, "stage": stage, "signal": signal,
            "roe": _num(ratios.get("ROE")), "roce": _num(ratios.get("ROCE")), "rev": _series_last_growth(annual, "Sales+"),
            "pat_yoy": _series_last_growth(annual, "Net Profit+"), "eps": _series_last_growth(annual, "EPS in Rs"),
            "pnl": pnl_pct, "qty": qty, "avg": avg, "ltp": ltp, "val": _num(portfolio.get("market_value")) or qty * ltp,
            "rs": _num(snap.get("relative_strength")), "rs_hist": [_num(snap.get("relative_strength"))], "rs_trend": "flat",
            "sp": max(0, round(100 - score)), "anchor": item["symbol"] in protected, "tranche": tranche,
            "investor": _shareholding_text(fund), "ratios": _ratios_text(fund), "quarters": _quarter_rows(fund),
        }
        rows.append(row)
        charts[item["symbol"]] = _chart_payload(item)
    rows.sort(key=lambda r: (not r["anchor"], -r["score"], -(r["rs"] or -1)))
    for rank, row in enumerate(rows, 1): row["rank"] = rank
    total_val = sum(r["val"] or 0 for r in rows)
    total_cost = sum((r["qty"] or 0) * (r["avg"] or 0) for r in rows)
    tranches = {}
    for key, label in (("T1", "S4/SELL + WEAK"), ("T2", "S4/SELL"), ("T3", "Borderline")):
        group = [r for r in rows if r["tranche"] == key]
        capital = sum(r["val"] or 0 for r in group)
        cost = sum((r["qty"] or 0) * (r["avg"] or 0) for r in group)
        tranches[key] = {"count": len(group), "capital": round(capital / 100000, 1), "gain": round((capital - cost) / 100000, 1), "label": label}
    scenarios = {}
    for threshold in (50, 60, 70):
        group = [r for r in rows if r["score"] < threshold and not r["anchor"]]
        capital = sum(r["val"] or 0 for r in group); cost = sum((r["qty"] or 0) * (r["avg"] or 0) for r in group)
        scenarios[str(threshold)] = {"sell": len(group), "capital": round(capital / 100000, 1), "gain": round((capital - cost) / 100000, 1)}
    fq = Counter(r["fq"] for r in rows)
    stats = {"n": len(rows), "total_val": round(total_val / 100000, 1), "total_cost": round(total_cost / 100000, 1),
             "total_gain": round((total_val - total_cost) / 100000, 1), "total_pct": round((total_val / total_cost - 1) * 100, 1) if total_cost else 0,
             "strong": fq["STRONG"], "decent": fq["DECENT"], "weak": fq["WEAK"], "tranches": tranches, "scenarios": scenarios}
    source = template.read_text(encoding="utf-8")
    source = _replace_json_const(source, "ALL", rows)
    source = _replace_json_const(source, "STATS", stats)
    source = _replace_json_const(source, "CHART_DATA", charts)
    source = re.sub(r"<title>Portfolio Consolidation — .*?</title>", "<title>Portfolio Consolidation — 18 Aug 2026</title>", source)
    source = re.sub(r"Portfolio Consolidation Report · .*?<", "Portfolio Consolidation Report · refreshed 18 Aug 2026 · NSE data through 17 Aug 2026<", source)
    output.write_text(source, encoding="utf-8")
    return {"output": str(output), "holdings": len(rows), "market_value_lakh": stats["total_val"], "cost_lakh": stats["total_cost"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_TEMPLATE)
    args = parser.parse_args()
    print(json.dumps(refresh(args.template, args.evidence, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
