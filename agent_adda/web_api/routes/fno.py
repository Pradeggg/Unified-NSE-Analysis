"""F&O overview route — live NSE options + futures data for indices and stocks."""
from __future__ import annotations

import os
import sys
import logging
from fastapi import APIRouter, Query, HTTPException

router = APIRouter()
_HERE = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
log = logging.getLogger(__name__)

_FNO_INDICES = {"BANKNIFTY", "NIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}


def _tools():
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    import terminal.tools as t
    return t


@router.get("/overview")
def fno_overview(
    symbol: str = Query(..., description="Symbol e.g. BANKNIFTY, RELIANCE"),
    expiry_index: int = Query(0, description="0=nearest, 1=next, etc."),
):
    """
    Return live F&O snapshot:
      - PCR, max pain, ATM strike, OI concentration (support/resistance)
      - Futures basis, cost-of-carry, rollover
      - Top 5 CE and PE strikes by OI (key levels for options traders)
    Falls back to PG EOD data outside market hours.
    """
    sym = symbol.strip().upper()
    tools = _tools()

    result: dict = {"symbol": sym}
    errors: list[str] = []

    # ── Options chain ───────────────────────────────────────────────────────
    try:
        oi = tools.get_oi_analysis(sym)
        if "error" not in oi:
            result["options"] = {
                "expiry":           oi.get("expiry"),
                "expiry_dates":     oi.get("expiry_dates", [])[:4],
                "underlying":       oi.get("underlying"),
                "atm":              oi.get("atm"),
                "pcr":              oi.get("pcr"),
                "max_pain":         oi.get("max_pain"),
                "max_pain_vs_spot": oi.get("max_pain_vs_spot"),
                "total_ce_oi":      oi.get("total_ce_oi"),
                "total_pe_oi":      oi.get("total_pe_oi"),
                "top_ce_oi_strikes": oi.get("top_ce_oi_strikes", [])[:5],  # resistance
                "top_pe_oi_strikes": oi.get("top_pe_oi_strikes", [])[:5],  # support
                "oi_buildup":       oi.get("oi_buildup", {}),
                "source":           oi.get("source", "live"),
                "dte":              oi.get("dte"),
            }
        else:
            errors.append(f"OI: {oi['error']}")
    except Exception as exc:
        errors.append(f"OI fetch failed: {exc}")
        log.warning("fno_overview OI error for %s: %s", sym, exc)

    # ── Futures ─────────────────────────────────────────────────────────────
    try:
        fut = tools.get_futures_analysis(sym)
        if "error" not in fut:
            result["futures"] = {
                "futures_price":    fut.get("futures_price"),
                "spot_price":       fut.get("spot_price"),
                "basis":            fut.get("basis"),
                "basis_pct":        fut.get("basis_pct"),
                "cost_of_carry":    fut.get("cost_of_carry"),
                "rollover_pct":     fut.get("rollover_pct"),
                "open_interest":    fut.get("open_interest"),
                "oi_change_pct":    fut.get("oi_change_pct"),
                "signal":           fut.get("signal"),
                "expiry":           fut.get("expiry"),
                "source":           fut.get("source", "live"),
            }
        else:
            errors.append(f"Futures: {fut.get('error','unknown')}")
    except Exception as exc:
        errors.append(f"Futures fetch failed: {exc}")
        log.warning("fno_overview futures error for %s: %s", sym, exc)

    # ── PG signals (PCR / buildup historical) ───────────────────────────────
    try:
        pg_fno = tools._quick_analysis_fno(sym)
        if pg_fno.get("available"):
            result["pg_signals"] = pg_fno
    except Exception:
        pass  # PG signals are best-effort

    if not result.get("options") and not result.get("futures"):
        raise HTTPException(
            503,
            detail=f"F&O data unavailable for {sym}. "
                   "NSE API may be down or market is closed. "
                   f"Errors: {'; '.join(errors) or 'unknown'}"
        )

    result["errors"] = errors
    return result


def _fno_context_text(sym: str) -> str:
    """
    Return a compact F&O summary string to inject into the LLM prompt.
    Returns empty string on any failure (never throws).
    """
    try:
        tools = _tools()
        parts: list[str] = []

        oi = tools.get_oi_analysis(sym)
        if "error" not in oi and oi.get("underlying"):
            atm    = oi.get("atm", "?")
            pcr    = oi.get("pcr", 0)
            mp     = oi.get("max_pain", "?")
            mpdiff = oi.get("max_pain_vs_spot")
            ce_top = oi.get("top_ce_oi_strikes", [])[:3]
            pe_top = oi.get("top_pe_oi_strikes", [])[:3]
            expiry = oi.get("expiry", "?")
            dte    = oi.get("dte", "?")
            ce_str = ", ".join(str(s.get("strike","?")) for s in ce_top) if ce_top else "n/a"
            pe_str = ", ".join(str(s.get("strike","?")) for s in pe_top) if pe_top else "n/a"
            mp_str = f"₹{mp}" + (f" ({mpdiff:+.0f} from spot)" if mpdiff else "")
            parts.append(
                f"[LIVE F&O DATA — {sym} | Expiry: {expiry} (DTE {dte})]\n"
                f"  ATM Strike: {atm} | PCR: {pcr:.2f} | Max Pain: {mp_str}\n"
                f"  CE OI Resistance (top strikes): {ce_str}\n"
                f"  PE OI Support    (top strikes): {pe_str}"
            )

        fut = tools.get_futures_analysis(sym)
        if "error" not in fut and fut.get("futures_price"):
            fp      = fut.get("futures_price","?")
            sp      = fut.get("spot_price","?")
            basis   = fut.get("basis_pct","?")
            rollover = fut.get("rollover_pct","?")
            signal  = fut.get("signal","")
            oi_chg  = fut.get("oi_change_pct","?")
            parts.append(
                f"  Futures: ₹{fp} | Spot: ₹{sp} | Basis: {basis}% | "
                f"Rollover: {rollover}% | OI Δ: {oi_chg}%"
                + (f" | Signal: {signal}" if signal else "")
            )

        return "\n".join(parts) if parts else ""
    except Exception as exc:
        log.debug("_fno_context_text error for %s: %s", sym, exc)
        return ""
