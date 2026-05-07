"""
terminal/forensics.py
D5 Forensic Accounting Suite — Agent Adda NSE Market Research Terminal.

Implements three quantitative red-flag models sourced from academic finance:

  1. Beneish M-score  — detects earnings manipulation probability
     • M > -1.78 → "Likely Manipulator"  (8-variable probit model)
     • Variables: DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA

  2. Piotroski F-score — measures financial health & momentum strength
     • 0-3 = Weak, 4-6 = Average, 7-9 = Strong
     • 9 binary signals across profitability, leverage, and efficiency

  3. Altman Z'-score  — bankruptcy / distress risk (EM version)
     • Z' > 2.6 = Safe Zone, 1.1–2.6 = Grey, < 1.1 = Distress Zone
     • Tailored for non-manufacturing / emerging market firms

Data source: screener.in consolidated/standalone pages (static HTML scraping).
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

# ── HTTP helpers ──────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.screener.in/",
}

_TIMEOUT = 15


def _get(url: str) -> requests.Response:
    return requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)


# ── Number parsing ────────────────────────────────────────────────────────────

def _parse_num(text: str) -> float | None:
    """Parse screener.in number strings like '1,23,456.78' or '-45.6' → float."""
    if not text:
        return None
    cleaned = re.sub(r"[,\s%₹]", "", text.strip())
    # Handle values like "1.23 Cr" — already in Crores on screener.in
    cleaned = re.sub(r"\s*(Cr|Lakh|K|M|B)?$", "", cleaned, flags=re.I)
    if cleaned in ("-", "--", "N.A.", "NA", ""):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


# ── Screener.in scraper for balance sheet + cash flow ────────────────────────

def _scrape_screener_financials(symbol: str) -> dict:
    """
    Scrape screener.in for multi-year financial statement data.

    Returns:
        {
          "annual_pl":      {row_label: [yr1, yr2, yr3, yr4, yr5], "_headers": [...]},
          "balance_sheet":  {row_label: [yr1, yr2, yr3, yr4, yr5], "_headers": [...]},
          "cash_flow":      {row_label: [yr1, yr2, yr3, yr4, yr5], "_headers": [...]},
          "ratios":         {"EPS": "...", "ROE": "...", ...},
          "source_url":     "...",
          "error":          None or str,
        }
    """
    sym = symbol.upper().strip()
    url = f"https://www.screener.in/company/{sym}/consolidated/"
    try:
        resp = _get(url)
        if resp.status_code == 404:
            url = f"https://www.screener.in/company/{sym}/"
            resp = _get(url)
        resp.raise_for_status()
    except Exception as e:
        return {"symbol": sym, "error": str(e), "source_url": url}

    soup = BeautifulSoup(resp.text, "lxml")

    def _parse_table(section_id: str) -> dict[str, Any]:
        """Parse a screener.in data table into {row_label: [values...]}."""
        result: dict[str, Any] = {}
        sec = soup.select_one(f"#{section_id}")
        if not sec:
            return result
        rows = sec.select("tr")
        if not rows:
            return result
        # Header row
        hdr_cells = [td.get_text(strip=True) for td in rows[0].select("td,th")]
        col_headers = hdr_cells[1:]  # skip first label col
        result["_headers"] = col_headers
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.select("td,th")]
            if not cells or not cells[0]:
                continue
            label = cells[0].strip()
            if label.startswith("+"):
                continue  # skip expansion rows
            values = cells[1:len(col_headers) + 1]
            result[label] = values
        return result

    def _parse_ratios() -> dict[str, str]:
        ratios: dict[str, str] = {}
        for li in soup.select("#top-ratios li"):
            name = li.select_one(".name")
            val = li.select_one(".number")
            if name and val:
                ratios[name.get_text(strip=True)] = val.get_text(strip=True)
        return ratios

    return {
        "symbol":       sym,
        "source_url":   url,
        "annual_pl":    _parse_table("profit-loss"),
        "balance_sheet": _parse_table("balance-sheet"),
        "cash_flow":    _parse_table("cash-flow"),
        "ratios":       _parse_ratios(),
        "error":        None,
    }


# ── Data extraction helpers ───────────────────────────────────────────────────

def _col_vals(data: dict, *labels: str) -> list[float | None]:
    """
    Return the last 5 annual column values for a row matching any of the labels.
    Returns a list of up to 5 floats (most-recent last), None where missing.
    """
    for label in labels:
        for key in data:
            if key.lower().strip().startswith(label.lower()):
                raw = data[key]
                if isinstance(raw, list):
                    return [_parse_num(v) for v in raw[:5]]
    return [None] * 5


def _yr(vals: list[float | None], idx: int) -> float | None:
    """Get value at column index, counting from the right (0=latest, 1=prev year)."""
    if not vals:
        return None
    # screener.in columns are oldest→newest; vals[-1] = latest
    rev = list(reversed(vals))
    if idx < len(rev):
        return rev[idx]
    return None


# ── Beneish M-score ───────────────────────────────────────────────────────────

def _compute_beneish(pl: dict, bs: dict) -> dict:
    """
    Beneish M-score: 8-variable probit model for earnings manipulation.

    Variables:
      DSRI  = Days Sales Receivables Index   → ↑ = aggressive revenue recognition
      GMI   = Gross Margin Index             → ↑ = deteriorating margins
      AQI   = Asset Quality Index            → ↑ = rising non-productive assets
      SGI   = Sales Growth Index             → ↑ = high-growth = manipulation risk
      DEPI  = Depreciation Index             → ↑ = understating depreciation
      SGAI  = SGA Expense Index              → ↑ = rising overhead
      LVGI  = Leverage Index                 → ↑ = rising debt burden
      TATA  = Total Accruals to Total Assets → ↑ = earnings driven by accruals

    M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
            + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

    Threshold: M > -1.78 → earnings manipulation likely.
    """
    # Income statement
    sales_v   = _col_vals(pl, "Sales", "Revenue from Operations", "Revenue")
    gp_v      = _col_vals(pl, "Gross Profit")
    # If no gross profit row, try to compute from OPM
    depr_v    = _col_vals(pl, "Depreciation", "Amortisation")
    sga_v     = _col_vals(pl, "Other Expenses", "Selling")
    opp_v     = _col_vals(pl, "Operating Profit", "EBIT", "Profit before tax")

    # Balance sheet
    ta_v      = _col_vals(bs, "Total Assets", "Balance Sheet Total")
    ca_v      = _col_vals(bs, "Other Assets", "Current Assets", "Total Current Assets")
    fa_v      = _col_vals(bs, "Fixed Assets", "Net Block", "Tangible Assets")
    borrow_v  = _col_vals(bs, "Borrowings", "Total Borrowings", "Long Term Borrowing")
    curr_liab = _col_vals(bs, "Other Liabilities", "Current Liabilities", "Total Current Liabilities")
    ar_v      = _col_vals(bs, "Trade Receivables", "Debtors", "Accounts Receivable")

    def _get(v: list, idx: int) -> float | None:
        return _yr(v, idx)

    # Current year (idx=0) and prior year (idx=1)
    s0, s1   = _get(sales_v, 0),  _get(sales_v, 1)
    ta0, ta1 = _get(ta_v, 0),     _get(ta_v, 1)
    ca0, ca1 = _get(ca_v, 0),     _get(ca_v, 1)
    fa0, fa1 = _get(fa_v, 0),     _get(fa_v, 1)
    d0, d1   = _get(depr_v, 0),   _get(depr_v, 1)
    sga0, sga1 = _get(sga_v, 0),  _get(sga_v, 1)
    bw0, bw1 = _get(borrow_v, 0), _get(borrow_v, 1)
    cl0, cl1 = _get(curr_liab, 0),_get(curr_liab, 1)
    ar0, ar1 = _get(ar_v, 0),     _get(ar_v, 1)
    op0, op1 = _get(opp_v, 0),    _get(opp_v, 1)

    # Gross profit proxy: use operating profit if no direct gross profit
    gp0, gp1 = _get(gp_v, 0), _get(gp_v, 1)
    if gp0 is None and s0 and op0:
        gp0 = op0  # use EBIT as gross margin proxy (understates)
    if gp1 is None and s1 and op1:
        gp1 = op1

    vars_: dict[str, float | None] = {}
    raw: dict[str, Any] = {
        "sales_curr": s0, "sales_prev": s1,
        "total_assets_curr": ta0, "total_assets_prev": ta1,
        "ar_curr": ar0, "ar_prev": ar1,
    }

    # DSRI = (AR/Sales)_t / (AR/Sales)_t-1
    vars_["DSRI"] = _safe_div(
        _safe_div(ar0, s0),
        _safe_div(ar1, s1),
    ) if ar0 and ar1 else None

    # GMI = Gross Margin_t-1 / Gross Margin_t
    gm0 = _safe_div(gp0, s0)
    gm1 = _safe_div(gp1, s1)
    vars_["GMI"] = _safe_div(gm1, gm0) if gm0 and gm1 else None

    # AQI = (1 - (CA+FA)/TA)_t / (1 - (CA+FA)/TA)_t-1
    def _aq(ca: float | None, fa: float | None, ta: float | None) -> float | None:
        if ca is None or fa is None or ta is None or ta == 0:
            return None
        return 1.0 - (ca + fa) / ta
    aq0 = _aq(ca0, fa0, ta0)
    aq1 = _aq(ca1, fa1, ta1)
    vars_["AQI"] = _safe_div(aq0, aq1) if aq0 is not None and aq1 else None

    # SGI = Sales_t / Sales_t-1
    vars_["SGI"] = _safe_div(s0, s1)

    # DEPI = (Depr/(Depr+FA))_t-1 / (Depr/(Depr+FA))_t
    def _dep_rate(d: float | None, fa: float | None) -> float | None:
        if d is None or fa is None or (d + fa) == 0:
            return None
        return d / (d + fa)
    dr0 = _dep_rate(d0, fa0)
    dr1 = _dep_rate(d1, fa1)
    vars_["DEPI"] = _safe_div(dr1, dr0) if dr0 and dr1 else None

    # SGAI = (SGA/Sales)_t / (SGA/Sales)_t-1
    vars_["SGAI"] = _safe_div(
        _safe_div(sga0, s0),
        _safe_div(sga1, s1),
    ) if sga0 and sga1 else None

    # LVGI = ((LTD + CL) / TA)_t / ((LTD + CL) / TA)_t-1
    lev0 = _safe_div((bw0 or 0) + (cl0 or 0), ta0) if ta0 else None
    lev1 = _safe_div((bw1 or 0) + (cl1 or 0), ta1) if ta1 else None
    vars_["LVGI"] = _safe_div(lev0, lev1) if lev0 and lev1 else None

    # TATA = (ΔCurrentAssets - ΔCash - ΔCurrentLiabilities - Depreciation) / TA
    # Simplified: ΔWorkingCapital - Depreciation) / TA
    if ca0 and ca1 and cl0 and cl1 and d0 and ta0:
        delta_wc = (ca0 - cl0) - (ca1 - cl1)
        vars_["TATA"] = (delta_wc - d0) / ta0
    else:
        vars_["TATA"] = None

    # M-score
    weights = {
        "DSRI": 0.920, "GMI": 0.528, "AQI": 0.404, "SGI": 0.892,
        "DEPI": 0.115, "SGAI": -0.172, "LVGI": -0.327, "TATA": 4.679,
    }
    intercept = -4.84

    available = {k: v for k, v in vars_.items() if v is not None}
    if len(available) < 4:
        return {
            "score": None,
            "interpretation": "Insufficient data",
            "variables": vars_,
            "note": f"Only {len(available)}/8 variables available",
        }

    m_score = intercept + sum(weights[k] * v for k, v in available.items())
    interpretation = (
        "⚠️  Likely Manipulator (M > -1.78)"
        if m_score > -1.78
        else "✅  Low Manipulation Risk (M ≤ -1.78)"
    )
    risk_flags = []
    if vars_.get("DSRI") and vars_["DSRI"] > 1.465:
        risk_flags.append("DSRI high — receivables growing faster than sales")
    if vars_.get("GMI") and vars_["GMI"] > 1.193:
        risk_flags.append("GMI high — gross margin deteriorating")
    if vars_.get("AQI") and vars_["AQI"] > 1.254:
        risk_flags.append("AQI high — rising non-productive assets")
    if vars_.get("TATA") and vars_["TATA"] > 0.031:
        risk_flags.append("TATA high — profits driven by accruals, not cash")
    if vars_.get("LVGI") and vars_["LVGI"] > 1.0:
        risk_flags.append("LVGI high — leverage increasing")

    return {
        "score":          round(m_score, 3),
        "threshold":      -1.78,
        "interpretation": interpretation,
        "variables":      {k: round(v, 4) if v else None for k, v in vars_.items()},
        "vars_available": len(available),
        "vars_total":     8,
        "risk_flags":     risk_flags,
        "raw":            raw,
    }


# ── Piotroski F-score ─────────────────────────────────────────────────────────

def _compute_piotroski(pl: dict, bs: dict, cf: dict) -> dict:
    """
    Piotroski F-score: 9-point system for financial health.

    Profitability (4):
      F1: ROA > 0 (Net Profit / Total Assets)
      F2: Operating Cash Flow > 0
      F3: ΔROA > 0 (ROA improved year-over-year)
      F4: Accrual quality: CFO/TA > ROA (cash earnings beat accrual earnings)

    Leverage & Liquidity (3):
      F5: ΔLong-term Debt < 0 (debt decreased)
      F6: ΔCurrent Ratio > 0 (liquidity improved)
      F7: No equity dilution (shares outstanding didn't increase >5%)

    Efficiency (2):
      F8: ΔGross Margin > 0
      F9: ΔAsset Turnover > 0 (Revenue / Total Assets improved)

    Score: 0-3 = Weak, 4-6 = Average, 7-9 = Strong.
    """
    np_v   = _col_vals(pl, "Net Profit", "Profit after tax", "PAT")
    sales_v = _col_vals(pl, "Sales", "Revenue from Operations", "Revenue")
    ta_v   = _col_vals(bs, "Total Assets", "Balance Sheet Total")
    bw_v   = _col_vals(bs, "Borrowings", "Total Borrowings", "Long Term Borrowing")
    ca_v   = _col_vals(bs, "Other Assets", "Current Assets", "Total Current Assets")
    cl_v   = _col_vals(bs, "Other Liabilities", "Current Liabilities", "Total Current Liabilities")
    cfo_v  = _col_vals(cf, "Cash from Operating Activity", "Net Cash from Operating", "Operating Cash Flow")
    eq_v   = _col_vals(bs, "Equity Capital", "Share Capital", "Paid-up Capital")
    gp_v   = _col_vals(pl, "Gross Profit")

    def _g(v: list, idx: int) -> float | None:
        return _yr(v, idx)

    np0, np1   = _g(np_v, 0), _g(np_v, 1)
    ta0, ta1   = _g(ta_v, 0), _g(ta_v, 1)
    bw0, bw1   = _g(bw_v, 0), _g(bw_v, 1)
    ca0, ca1   = _g(ca_v, 0), _g(ca_v, 1)
    cl0, cl1   = _g(cl_v, 0), _g(cl_v, 1)
    cfo0       = _g(cfo_v, 0)
    s0, s1     = _g(sales_v, 0), _g(sales_v, 1)
    eq0, eq1   = _g(eq_v, 0), _g(eq_v, 1)
    gp0, gp1   = _g(gp_v, 0), _g(gp_v, 1)

    signals: dict[str, int | None] = {}
    explanations: dict[str, str] = {}

    # F1: ROA > 0
    roa0 = _safe_div(np0, ta0)
    if roa0 is not None:
        signals["F1_roa_positive"] = 1 if roa0 > 0 else 0
        explanations["F1"] = f"ROA = {roa0:.2%} ({'✅' if roa0 > 0 else '❌'})"
    else:
        signals["F1_roa_positive"] = None

    # F2: CFO > 0
    if cfo0 is not None:
        signals["F2_cfo_positive"] = 1 if cfo0 > 0 else 0
        explanations["F2"] = f"CFO = {cfo0:,.0f} Cr ({'✅' if cfo0 > 0 else '❌'})"
    else:
        signals["F2_cfo_positive"] = None

    # F3: ΔROA > 0
    roa1 = _safe_div(np1, ta1)
    if roa0 is not None and roa1 is not None:
        signals["F3_roa_improving"] = 1 if roa0 > roa1 else 0
        explanations["F3"] = f"ΔROA = {(roa0 - roa1):.2%} ({'✅' if roa0 > roa1 else '❌'})"
    else:
        signals["F3_roa_improving"] = None

    # F4: Accrual quality (CFO/TA > ROA)
    if cfo0 is not None and ta0 and roa0 is not None:
        cfo_ratio = cfo0 / ta0
        signals["F4_accrual_quality"] = 1 if cfo_ratio > roa0 else 0
        explanations["F4"] = f"CFO/TA {cfo_ratio:.2%} vs ROA {roa0:.2%} ({'✅' if cfo_ratio > roa0 else '❌'})"
    else:
        signals["F4_accrual_quality"] = None

    # F5: ΔLeverage < 0 (debt ratio declined)
    lev0 = _safe_div(bw0, ta0)
    lev1 = _safe_div(bw1, ta1)
    if lev0 is not None and lev1 is not None:
        signals["F5_leverage_reduced"] = 1 if lev0 < lev1 else 0
        explanations["F5"] = f"Debt/TA {lev1:.2%}→{lev0:.2%} ({'✅' if lev0 < lev1 else '❌'})"
    else:
        signals["F5_leverage_reduced"] = None

    # F6: ΔCurrent Ratio > 0
    cr0 = _safe_div(ca0, cl0)
    cr1 = _safe_div(ca1, cl1)
    if cr0 is not None and cr1 is not None:
        signals["F6_liquidity_improved"] = 1 if cr0 > cr1 else 0
        explanations["F6"] = f"Current Ratio {cr1:.2f}→{cr0:.2f} ({'✅' if cr0 > cr1 else '❌'})"
    else:
        signals["F6_liquidity_improved"] = None

    # F7: No dilution (share capital unchanged or decreased)
    if eq0 is not None and eq1 is not None and eq1 > 0:
        dilution = (eq0 - eq1) / eq1
        signals["F7_no_dilution"] = 1 if dilution <= 0.05 else 0
        explanations["F7"] = f"Equity Capital change {dilution:.1%} ({'✅' if dilution <= 0.05 else '❌'})"
    else:
        signals["F7_no_dilution"] = None

    # F8: ΔGross Margin > 0
    gm0 = _safe_div(gp0, s0) if gp0 else _safe_div(np0, s0)  # net margin as fallback
    gm1 = _safe_div(gp1, s1) if gp1 else _safe_div(np1, s1)
    if gm0 is not None and gm1 is not None:
        signals["F8_margin_improved"] = 1 if gm0 > gm1 else 0
        explanations["F8"] = f"Margin {gm1:.2%}→{gm0:.2%} ({'✅' if gm0 > gm1 else '❌'})"
    else:
        signals["F8_margin_improved"] = None

    # F9: ΔAsset Turnover > 0
    at0 = _safe_div(s0, ta0)
    at1 = _safe_div(s1, ta1)
    if at0 is not None and at1 is not None:
        signals["F9_asset_turnover_improved"] = 1 if at0 > at1 else 0
        explanations["F9"] = f"Asset Turnover {at1:.2f}→{at0:.2f} ({'✅' if at0 > at1 else '❌'})"
    else:
        signals["F9_asset_turnover_improved"] = None

    available = {k: v for k, v in signals.items() if v is not None}
    f_score = sum(available.values())
    max_possible = len(available)

    if max_possible < 5:
        strength = "Insufficient Data"
        color = "grey"
    elif f_score >= 7:
        strength = "🟢 Strong (7-9) — High-quality financials"
        color = "green"
    elif f_score >= 4:
        strength = "🟡 Average (4-6) — Watch for improving trends"
        color = "yellow"
    else:
        strength = "🔴 Weak (0-3) — Financial deterioration signals"
        color = "red"

    return {
        "score":         f_score,
        "max_possible":  max_possible,
        "strength":      strength,
        "signals":       signals,
        "explanations":  explanations,
    }


# ── Altman Z'-score (Emerging Markets version) ────────────────────────────────

def _compute_altman(pl: dict, bs: dict) -> dict:
    """
    Altman Z'-score: modified model for non-manufacturing / emerging-market firms.

    Z' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4

    X1 = Working Capital / Total Assets         (liquidity)
    X2 = Retained Earnings / Total Assets       (cumulative profitability)
    X3 = EBIT / Total Assets                    (operating efficiency)
    X4 = Book Value of Equity / Total Liabilities (leverage buffer)

    Zones:
      Z' > 2.6  → Safe Zone  (low default risk)
      1.1 ≤ Z' ≤ 2.6 → Grey Zone (moderate risk)
      Z' < 1.1  → Distress Zone (high bankruptcy risk)
    """
    ta_v    = _col_vals(bs, "Total Assets", "Balance Sheet Total")
    ca_v    = _col_vals(bs, "Other Assets", "Current Assets", "Total Current Assets")
    cl_v    = _col_vals(bs, "Other Liabilities", "Current Liabilities", "Total Current Liabilities")
    bw_v    = _col_vals(bs, "Borrowings", "Total Borrowings")
    eq_cap  = _col_vals(bs, "Equity Capital", "Share Capital", "Paid-up Capital")
    res_v   = _col_vals(bs, "Reserves", "Retained Earnings", "Surplus")
    op_v    = _col_vals(pl, "Operating Profit", "EBIT", "Profit before interest")
    np_v    = _col_vals(pl, "Net Profit", "Profit after tax", "PAT")

    ta0  = _yr(ta_v, 0)
    ca0  = _yr(ca_v, 0)
    cl0  = _yr(cl_v, 0)
    bw0  = _yr(bw_v, 0)
    eq0  = _yr(eq_cap, 0)
    res0 = _yr(res_v, 0)
    op0  = _yr(op_v, 0)
    np0  = _yr(np_v, 0)

    if ta0 is None or ta0 == 0:
        return {"score": None, "interpretation": "Insufficient data — Total Assets missing"}

    # Total Liabilities = Total Assets - Equity - Reserves
    total_equity = (eq0 or 0) + (res0 or 0)
    total_liab = ta0 - total_equity
    if total_liab <= 0:
        total_liab = bw0 or ta0 * 0.3  # fallback estimate

    # Working capital
    wc = (ca0 or 0) - (cl0 or 0)

    # Retained earnings proxy = Reserves (most conservative)
    retained = res0 or 0

    # EBIT proxy = Operating Profit (before interest & tax)
    ebit = op0 or np0 or 0

    # Book value of equity
    bv_equity = total_equity

    x1 = wc / ta0
    x2 = retained / ta0
    x3 = ebit / ta0
    x4 = _safe_div(bv_equity, total_liab) or 0

    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4

    if z > 2.6:
        zone = "🟢 Safe Zone (Z' > 2.6) — Low default risk"
    elif z >= 1.1:
        zone = "🟡 Grey Zone (1.1–2.6) — Monitor closely"
    else:
        zone = "🔴 Distress Zone (Z' < 1.1) — High bankruptcy risk"

    return {
        "score":          round(z, 3),
        "zone":           zone,
        "thresholds":     {"safe": 2.6, "distress": 1.1},
        "components": {
            "X1_working_capital_ratio": round(x1, 4),
            "X2_retained_earnings_ratio": round(x2, 4),
            "X3_ebit_ratio": round(x3, 4),
            "X4_equity_to_liabilities": round(x4, 4),
        },
        "data_used": {
            "total_assets": ta0,
            "working_capital": round(wc, 0),
            "retained_earnings": round(retained, 0),
            "ebit": round(ebit, 0),
            "book_value_equity": round(bv_equity, 0),
            "total_liabilities": round(total_liab, 0),
        },
    }


# ── Main public API ───────────────────────────────────────────────────────────

def run_forensic_analysis(symbol: str) -> dict:
    """
    Run complete forensic accounting analysis for an NSE stock.

    Computes:
      1. Beneish M-score — earnings manipulation probability
      2. Piotroski F-score — financial health & strength
      3. Altman Z'-score — bankruptcy / distress risk (EM version)

    Returns a unified dict with all three scores, interpretations, and risk flags.
    Data sourced from screener.in consolidated financial statements.

    Args:
        symbol: NSE ticker (e.g. 'RELIANCE', 'TCS', 'HDFCBANK')

    Returns:
        {
          "symbol": str,
          "source_url": str,
          "beneish": {...},   # M-score with variables & risk flags
          "piotroski": {...}, # F-score with 9 signal breakdown
          "altman": {...},    # Z'-score with zone & components
          "summary": str,     # LLM-ready 3-line verdict
          "overall_risk": "low" | "moderate" | "high",
        }
    """
    sym = symbol.upper().strip()

    # Fetch financial data
    data = _scrape_screener_financials(sym)
    if data.get("error"):
        return {"symbol": sym, "error": data["error"], "source_url": data.get("source_url", "")}

    pl = data["annual_pl"]
    bs = data["balance_sheet"]
    cf = data["cash_flow"]

    if not pl and not bs:
        return {
            "symbol":   sym,
            "error":    "No financial statement data found on screener.in",
            "source_url": data["source_url"],
        }

    # Run all three models
    beneish  = _compute_beneish(pl, bs)
    piotroski = _compute_piotroski(pl, bs, cf)
    altman   = _compute_altman(pl, bs)

    # Overall risk assessment
    risk_score = 0
    if beneish.get("score") is not None and beneish["score"] > -1.78:
        risk_score += 2
    if piotroski.get("score") is not None and piotroski["score"] <= 3:
        risk_score += 2
    elif piotroski.get("score") is not None and piotroski["score"] <= 5:
        risk_score += 1
    if altman.get("score") is not None:
        if altman["score"] < 1.1:
            risk_score += 2
        elif altman["score"] < 2.6:
            risk_score += 1

    overall = "high" if risk_score >= 4 else "moderate" if risk_score >= 2 else "low"

    # Build LLM-ready summary
    b_str = f"M={beneish['score']}" if beneish.get("score") else "N/A"
    p_str = f"F={piotroski['score']}/{piotroski.get('max_possible', 9)}" if piotroski.get("score") is not None else "N/A"
    a_str = f"Z'={altman['score']}" if altman.get("score") else "N/A"

    summary_lines = [
        f"Beneish M-score ({b_str}): {beneish.get('interpretation', 'N/A')}",
        f"Piotroski F-score ({p_str}): {piotroski.get('strength', 'N/A')}",
        f"Altman Z'-score ({a_str}): {altman.get('zone', 'N/A')}",
    ]
    if beneish.get("risk_flags"):
        summary_lines.append("Red flags: " + "; ".join(beneish["risk_flags"][:3]))

    return {
        "symbol":       sym,
        "source_url":   data["source_url"],
        "beneish":      beneish,
        "piotroski":    piotroski,
        "altman":       altman,
        "summary":      "\n".join(summary_lines),
        "overall_risk": overall,
        "risk_score":   risk_score,
        "data_years":   pl.get("_headers", []),
    }


def screen_forensic_watchlist(symbols: list[str]) -> dict:
    """
    Run forensic screening across a list of symbols. Returns ranked results
    with overall risk rating for each stock. Useful for portfolio-level
    forensic checks or pre-buy due diligence.

    Args:
        symbols: List of NSE tickers (max 10 for speed).

    Returns:
        {
          "results": [{symbol, overall_risk, risk_score, beneish_score,
                       piotroski_score, altman_score, beneish_interp,
                       piotroski_strength, altman_zone}],
          "high_risk": [...],
          "low_risk":  [...],
          "count":     int,
        }
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not symbols:
        return {"error": "No symbols provided"}

    # Cap at 8 stocks to avoid hammering screener.in
    syms = [s.upper().strip() for s in symbols[:8]]
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(run_forensic_analysis, sym): sym for sym in syms}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                r = fut.result()
                if r.get("error"):
                    results.append({"symbol": sym, "error": r["error"], "overall_risk": "unknown"})
                else:
                    results.append({
                        "symbol":            sym,
                        "overall_risk":      r["overall_risk"],
                        "risk_score":        r["risk_score"],
                        "beneish_score":     r["beneish"].get("score"),
                        "beneish_interp":    r["beneish"].get("interpretation", "N/A"),
                        "beneish_flags":     r["beneish"].get("risk_flags", []),
                        "piotroski_score":   r["piotroski"].get("score"),
                        "piotroski_strength": r["piotroski"].get("strength", "N/A"),
                        "altman_score":      r["altman"].get("score"),
                        "altman_zone":       r["altman"].get("zone", "N/A"),
                        "source_url":        r["source_url"],
                    })
            except Exception as e:
                results.append({"symbol": sym, "error": str(e), "overall_risk": "unknown"})

    # Sort: high risk first
    risk_order = {"high": 0, "moderate": 1, "low": 2, "unknown": 3}
    results.sort(key=lambda x: risk_order.get(x.get("overall_risk", "unknown"), 3))

    return {
        "results":   results,
        "high_risk": [r["symbol"] for r in results if r.get("overall_risk") == "high"],
        "moderate_risk": [r["symbol"] for r in results if r.get("overall_risk") == "moderate"],
        "low_risk":  [r["symbol"] for r in results if r.get("overall_risk") == "low"],
        "count":     len(results),
    }
