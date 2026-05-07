"""
terminal/options_analysis.py
─────────────────────────────
Options and F&O Analysis Engine for Agent Adda.

Provides:
  • Black-Scholes greeks and IV calculation
  • PCR (Put-Call Ratio) analysis
  • Max Pain calculation
  • OI heatmap and support/resistance detection
  • Options strategy payoff builder
  • Futures basis and cost-of-carry analysis
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from terminal.fno_data import (
    fetch_live_option_chain,
    fetch_live_futures,
    get_eod_option_chain,
    get_eod_futures,
    get_lot_size,
    days_to_expiry,
)


# ─────────────────────────────────────────────────────────────────────────────
# Black-Scholes Model
# ─────────────────────────────────────────────────────────────────────────────
RISK_FREE_RATE = 0.065   # ~RBI repo rate proxy


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    """Compute d1 and d2 for Black-Scholes."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0, 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str = "CE") -> float:
    """Black-Scholes theoretical price."""
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if option_type.upper() == "CE":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def calc_greeks(S: float, K: float, T_days: float, sigma: float,
                option_type: str = "CE",
                r: float = RISK_FREE_RATE) -> dict[str, float]:
    """
    Calculate option greeks.
    S: spot price, K: strike, T_days: days to expiry,
    sigma: IV as decimal (0.20 = 20%), r: risk-free rate.
    """
    T = T_days / 365.0
    if T <= 0 or sigma <= 0:
        return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "rho": 0,
                "theoretical_price": max(0, S - K if option_type == "CE" else K - S)}

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    nd1  = norm.cdf(d1)
    nd2  = norm.cdf(d2)
    nd1_ = norm.cdf(-d1)
    nd2_ = norm.cdf(-d2)
    phi  = norm.pdf(d1)

    if option_type.upper() == "CE":
        delta = nd1
        rho   = K * T * math.exp(-r * T) * nd2 / 100
        price = S * nd1 - K * math.exp(-r * T) * nd2
    else:
        delta = nd1 - 1
        rho   = -K * T * math.exp(-r * T) * nd2_ / 100
        price = K * math.exp(-r * T) * nd2_ - S * nd1_

    gamma = phi / (S * sigma * math.sqrt(T))
    vega  = S * phi * math.sqrt(T) / 100        # per 1% IV move
    theta = (
        -(S * phi * sigma) / (2 * math.sqrt(T))
        - r * K * math.exp(-r * T) * (nd2 if option_type.upper() == "CE" else nd2_)
    ) / 365                                       # per day

    return {
        "delta":             round(delta, 4),
        "gamma":             round(gamma, 6),
        "theta":             round(theta, 4),
        "vega":              round(vega, 4),
        "rho":               round(rho, 4),
        "theoretical_price": round(price, 2),
    }


def calc_iv(option_price: float, S: float, K: float, T_days: float,
            option_type: str = "CE", r: float = RISK_FREE_RATE,
            max_iter: int = 200, tol: float = 1e-6) -> float | None:
    """
    Implied Volatility via Newton-Raphson.
    Returns IV as decimal (0.20 = 20%) or None if no convergence.
    """
    T = T_days / 365.0
    if T <= 0 or option_price <= 0:
        return None

    intrinsic = max(0, S - K if option_type.upper() == "CE" else K - S)
    if option_price < intrinsic:
        return None

    sigma = 0.30   # initial guess
    for _ in range(max_iter):
        price = bs_price(S, K, T, r, sigma, option_type)
        d1, _ = _d1_d2(S, K, T, r, sigma)
        vega = S * norm.pdf(d1) * math.sqrt(T)
        if vega < 1e-10:
            break
        diff = price - option_price
        sigma -= diff / vega
        sigma = max(0.001, min(sigma, 20.0))
        if abs(diff) < tol:
            return round(sigma, 4)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Option Chain Analysis
# ─────────────────────────────────────────────────────────────────────────────
def analyze_option_chain(symbol: str, expiry: str | None = None,
                          use_live: bool = True) -> dict:
    """
    Full option chain analysis: PCR, max pain, OI heatmap, support/resistance,
    and greeks for ATM ± 5 strikes.
    """
    chain_data = (
        fetch_live_option_chain(symbol, expiry)
        if use_live else
        _eod_chain_to_live_format(symbol, expiry)
    )

    if "error" in chain_data:
        return chain_data

    rows  = chain_data.get("data", [])
    spot  = chain_data.get("underlying") or 0.0
    exp   = chain_data.get("expiry", "")
    dte   = days_to_expiry(exp) if exp else 0

    if not rows:
        return {"error": f"No option chain data for {symbol}", "symbol": symbol}

    df = pd.DataFrame(rows)
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df = df.dropna(subset=["strike"]).sort_values("strike")

    # ── PCR ──────────────────────────────────────────────────────────────────
    total_ce_oi = int(df["ce_oi"].sum())
    total_pe_oi = int(df["pe_oi"].sum())
    pcr_oi  = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi > 0 else None
    total_ce_vol = int(df["ce_vol"].sum())
    total_pe_vol = int(df["pe_vol"].sum())
    pcr_vol = round(total_pe_vol / total_ce_vol, 3) if total_ce_vol > 0 else None

    pcr_signal = "Neutral"
    if pcr_oi:
        if pcr_oi > 1.3:
            pcr_signal = "Bullish (high put writing = market comfortable with upside)"
        elif pcr_oi < 0.7:
            pcr_signal = "Bearish (high call writing = market expecting downside)"
        elif pcr_oi > 1.0:
            pcr_signal = "Mildly Bullish"
        else:
            pcr_signal = "Mildly Bearish"

    # ── Max Pain ─────────────────────────────────────────────────────────────
    strikes = df["strike"].tolist()
    max_pain_strike = _calc_max_pain(df, strikes)

    # ── OI Heatmap: top CE/PE OI strikes (resistance / support) ──────────────
    top_ce = df.nlargest(5, "ce_oi")[["strike", "ce_oi", "ce_oi_chg", "ce_ltp"]].to_dict("records")
    top_pe = df.nlargest(5, "pe_oi")[["strike", "pe_oi", "pe_oi_chg", "pe_ltp"]].to_dict("records")

    # ── ATM strikes greeks ───────────────────────────────────────────────────
    atm_greeks = []
    if spot > 0 and dte > 0:
        atm_idx = (df["strike"] - spot).abs().idxmin()
        atm_strike = float(df.loc[atm_idx, "strike"])
        atm_positions = [("ATM-2", -2), ("ATM-1", -1), ("ATM", 0),
                         ("ATM+1", 1), ("ATM+2", 2)]
        # Get sorted unique strikes
        sorted_strikes = sorted(strikes)
        atm_pos_in_list = sorted_strikes.index(atm_strike) if atm_strike in sorted_strikes else len(sorted_strikes) // 2

        for label, offset in atm_positions:
            idx = atm_pos_in_list + offset
            if 0 <= idx < len(sorted_strikes):
                k = sorted_strikes[idx]
                ce_ltp = float(df[df["strike"] == k]["ce_ltp"].values[0]) if k in df["strike"].values else 0
                pe_ltp = float(df[df["strike"] == k]["pe_ltp"].values[0]) if k in df["strike"].values else 0
                ce_iv  = df[df["strike"] == k]["ce_iv"].values[0] if "ce_iv" in df.columns and k in df["strike"].values else None
                sigma  = float(ce_iv) / 100 if ce_iv and ce_iv > 0 else 0.18  # fallback 18%
                entry = {
                    "label":    label,
                    "strike":   k,
                    "ce_ltp":   ce_ltp,
                    "pe_ltp":   pe_ltp,
                }
                if sigma > 0 and dte > 0:
                    entry["ce_greeks"] = calc_greeks(spot, k, dte, sigma, "CE")
                    entry["pe_greeks"] = calc_greeks(spot, k, dte, sigma, "PE")
                atm_greeks.append(entry)

    # ── OI Change (buildup/unwinding) ────────────────────────────────────────
    df["ce_oi_chg"] = pd.to_numeric(df.get("ce_oi_chg", 0), errors="coerce").fillna(0)
    df["pe_oi_chg"] = pd.to_numeric(df.get("pe_oi_chg", 0), errors="coerce").fillna(0)

    oi_buildup = {
        "ce_buildup": df.nlargest(3, "ce_oi_chg")[["strike", "ce_oi_chg", "ce_oi", "ce_ltp"]].to_dict("records"),
        "pe_buildup": df.nlargest(3, "pe_oi_chg")[["strike", "pe_oi_chg", "pe_oi", "pe_ltp"]].to_dict("records"),
        "ce_unwinding": df.nsmallest(3, "ce_oi_chg")[["strike", "ce_oi_chg", "ce_oi", "ce_ltp"]].to_dict("records"),
        "pe_unwinding": df.nsmallest(3, "pe_oi_chg")[["strike", "pe_oi_chg", "pe_oi", "pe_ltp"]].to_dict("records"),
    }

    # ── IV Skew ──────────────────────────────────────────────────────────────
    iv_skew = None
    if "ce_iv" in df.columns and df["ce_iv"].notna().sum() > 3:
        below_atm = df[df["strike"] <= spot]["pe_iv"].dropna()
        above_atm = df[df["strike"] >= spot]["ce_iv"].dropna()
        if len(below_atm) > 0 and len(above_atm) > 0:
            iv_skew = {
                "put_iv_avg":  round(float(below_atm.mean()), 2),
                "call_iv_avg": round(float(above_atm.mean()), 2),
                "skew":        round(float(below_atm.mean()) - float(above_atm.mean()), 2),
            }

    return {
        "symbol":         symbol,
        "underlying":     spot,
        "expiry":         exp,
        "dte":            dte,
        "source":         chain_data.get("source", "unknown"),
        "as_of":          chain_data.get("as_of"),
        "pcr": {
            "oi":     pcr_oi,
            "volume": pcr_vol,
            "signal": pcr_signal,
        },
        "max_pain":       max_pain_strike,
        "max_pain_vs_spot": round(max_pain_strike - spot, 2) if max_pain_strike and spot else None,
        "top_ce_oi_strikes": top_ce,
        "top_pe_oi_strikes": top_pe,
        "oi_buildup":     oi_buildup,
        "atm_greeks":     atm_greeks,
        "iv_skew":        iv_skew,
        "total_ce_oi":    total_ce_oi,
        "total_pe_oi":    total_pe_oi,
        "total_ce_vol":   total_ce_vol,
        "total_pe_vol":   total_pe_vol,
    }


def _calc_max_pain(df: pd.DataFrame, strikes: list[float]) -> float | None:
    """
    Max Pain = strike where total option writers' loss is minimised.
    Returns the max-pain strike price.
    """
    if not strikes:
        return None
    min_loss = float("inf")
    max_pain = None

    for s in strikes:
        # Total loss if expiry at s:
        # CE writers pay out max(0, spot_at_expiry - CE_strike) for all CE below s
        # PE writers pay out max(0, PE_strike - spot_at_expiry) for all PE above s
        ce_loss = float(((s - df["strike"]).clip(lower=0) * df["ce_oi"]).sum())
        pe_loss = float(((df["strike"] - s).clip(lower=0) * df["pe_oi"]).sum())
        total_loss = ce_loss + pe_loss
        if total_loss < min_loss:
            min_loss = total_loss
            max_pain = s

    return max_pain


def _eod_chain_to_live_format(symbol: str, expiry: str | None) -> dict:
    df = get_eod_option_chain(symbol, expiry_date=expiry)
    if df.empty:
        return {"error": f"No EOD chain data for {symbol}", "symbol": symbol}
    # use _live_chain_from_eod structure but rename fields
    from terminal.fno_data import _live_chain_from_eod
    return _live_chain_from_eod(symbol, expiry)


# ─────────────────────────────────────────────────────────────────────────────
# Futures Analysis
# ─────────────────────────────────────────────────────────────────────────────
def analyze_futures(symbol: str, use_live: bool = True) -> dict:
    """
    Futures basis, cost-of-carry, rollover analysis.
    """
    fut_data = fetch_live_futures(symbol) if use_live else _eod_futures_data(symbol)
    if "error" in fut_data:
        return fut_data

    spot = fut_data.get("underlying") or 0.0
    futures = fut_data.get("futures", [])
    if not futures:
        return {"error": f"No futures data for {symbol}", "symbol": symbol}

    enriched = []
    for f in futures:
        lp = f.get("last_price") or f.get("settle_price") or 0
        dte = days_to_expiry(f.get("expiry", "")) if f.get("expiry") else 0
        basis = round(lp - spot, 2) if spot and lp else None
        basis_pct = round((lp / spot - 1) * 100, 3) if spot and lp else None
        coc = None
        if basis_pct is not None and dte > 0:
            coc = round(basis_pct * 365 / dte, 2)   # annualised cost of carry

        enriched.append({
            **f,
            "basis":      basis,
            "basis_pct":  basis_pct,
            "cost_of_carry_annualised_pct": coc,
            "dte":        dte,
        })

    # Rollover: OI ratio between near and next month
    rollover_signal = None
    if len(enriched) >= 2:
        near_oi = enriched[0].get("oi", 0) or 0
        next_oi = enriched[1].get("oi", 0) or 0
        total   = near_oi + next_oi
        if total > 0:
            rollover_pct = round(next_oi / total * 100, 1)
            rollover_signal = {
                "near_month_oi": near_oi,
                "next_month_oi": next_oi,
                "rollover_pct":  rollover_pct,
                "interpretation": (
                    "High rollover — longs/shorts building in next month"
                    if rollover_pct > 40 else
                    "Low rollover — positions staying in near month"
                ),
            }

    return {
        "symbol":          symbol,
        "spot":            spot,
        "source":          fut_data.get("source"),
        "as_of":           fut_data.get("as_of"),
        "futures":         enriched,
        "rollover":        rollover_signal,
        "lot_size":        get_lot_size(symbol),
    }


def _eod_futures_data(symbol: str) -> dict:
    df = get_eod_futures(symbol)
    if df.empty:
        return {"error": f"No EOD futures data for {symbol}", "symbol": symbol}
    underlying = float(df["underlying"].iloc[0]) if "underlying" in df.columns else None
    futures = []
    for _, row in df.iterrows():
        futures.append({
            "expiry":       row.get("expiry_date"),
            "last_price":   row.get("last_price"),
            "settle_price": row.get("settle_price"),
            "oi":           int(row.get("oi", 0)),
            "oi_change":    int(row.get("oi_change", 0)),
            "volume":       int(row.get("volume", 0)),
            "underlying":   underlying,
        })
    return {"symbol": symbol, "underlying": underlying, "futures": futures, "source": "eod"}


# ─────────────────────────────────────────────────────────────────────────────
# Options Strategy Builder
# ─────────────────────────────────────────────────────────────────────────────
STRATEGY_CATALOG: dict[str, dict] = {
    "long_call": {
        "name": "Long Call",
        "view": "Bullish",
        "risk": "Limited (premium paid)",
        "reward": "Unlimited",
        "legs": [{"type": "CE", "action": "BUY", "strike_offset": 0}],
        "best_when": "Strong directional move expected upward; low IV environment",
    },
    "long_put": {
        "name": "Long Put",
        "view": "Bearish",
        "risk": "Limited (premium paid)",
        "reward": "Limited (strike - 0)",
        "legs": [{"type": "PE", "action": "BUY", "strike_offset": 0}],
        "best_when": "Strong directional move expected downward; low IV environment",
    },
    "bull_call_spread": {
        "name": "Bull Call Spread",
        "view": "Moderately Bullish",
        "risk": "Net premium paid",
        "reward": "Strike difference - net premium",
        "legs": [
            {"type": "CE", "action": "BUY",  "strike_offset": 0},
            {"type": "CE", "action": "SELL", "strike_offset": +1},
        ],
        "best_when": "Moderate upside expected; reduce cost vs plain long call",
    },
    "bear_put_spread": {
        "name": "Bear Put Spread",
        "view": "Moderately Bearish",
        "risk": "Net premium paid",
        "reward": "Strike difference - net premium",
        "legs": [
            {"type": "PE", "action": "BUY",  "strike_offset": 0},
            {"type": "PE", "action": "SELL", "strike_offset": -1},
        ],
        "best_when": "Moderate downside expected; reduce cost vs plain long put",
    },
    "long_straddle": {
        "name": "Long Straddle",
        "view": "Volatile (direction-neutral)",
        "risk": "Both premiums paid",
        "reward": "Unlimited",
        "legs": [
            {"type": "CE", "action": "BUY", "strike_offset": 0},
            {"type": "PE", "action": "BUY", "strike_offset": 0},
        ],
        "best_when": "Big move expected but direction uncertain; pre-event strategy",
    },
    "long_strangle": {
        "name": "Long Strangle",
        "view": "Volatile (direction-neutral)",
        "risk": "Both premiums paid (cheaper than straddle)",
        "reward": "Unlimited",
        "legs": [
            {"type": "CE", "action": "BUY", "strike_offset": +1},
            {"type": "PE", "action": "BUY", "strike_offset": -1},
        ],
        "best_when": "Big move expected; OTM strangle cheaper than ATM straddle",
    },
    "iron_condor": {
        "name": "Iron Condor",
        "view": "Range-bound (neutral)",
        "risk": "Strike width - net credit",
        "reward": "Net credit received",
        "legs": [
            {"type": "PE", "action": "BUY",  "strike_offset": -2},
            {"type": "PE", "action": "SELL", "strike_offset": -1},
            {"type": "CE", "action": "SELL", "strike_offset": +1},
            {"type": "CE", "action": "BUY",  "strike_offset": +2},
        ],
        "best_when": "Low volatility expected; index stays in a range till expiry",
    },
    "covered_call": {
        "name": "Covered Call",
        "view": "Neutral to mildly bullish (stock holding)",
        "risk": "Full stock downside less premium received",
        "reward": "Premium + limited upside to strike",
        "legs": [{"type": "CE", "action": "SELL", "strike_offset": +1}],
        "best_when": "Holding stock, want to earn income; capped upside acceptable",
    },
    "protective_put": {
        "name": "Protective Put",
        "view": "Hedging existing long stock",
        "risk": "Put premium paid",
        "reward": "Full upside participation with downside hedge",
        "legs": [{"type": "PE", "action": "BUY", "strike_offset": 0}],
        "best_when": "Holding stock, want insurance against sharp fall",
    },
    "calendar_spread": {
        "name": "Calendar Spread",
        "view": "Neutral short-term, mild move by far expiry",
        "risk": "Net debit paid",
        "reward": "Time decay difference between near and far expiry",
        "legs": [
            {"type": "CE", "action": "SELL", "strike_offset": 0, "expiry": "near"},
            {"type": "CE", "action": "BUY",  "strike_offset": 0, "expiry": "far"},
        ],
        "best_when": "IV expected to rise; sell near-term theta, own far-term gamma",
    },
}


def build_strategy(symbol: str, strategy_key: str,
                   expiry: str | None = None,
                   use_live: bool = True) -> dict:
    """
    Build a complete options strategy with live/EOD pricing.
    Returns legs with entry prices, max risk, reward, breakevens.
    """
    strategy_key = strategy_key.lower().replace(" ", "_")
    if strategy_key not in STRATEGY_CATALOG:
        return {
            "error": f"Unknown strategy '{strategy_key}'. Choose from: {', '.join(STRATEGY_CATALOG.keys())}",
            "available_strategies": list(STRATEGY_CATALOG.keys()),
        }

    strat = STRATEGY_CATALOG[strategy_key]
    chain = fetch_live_option_chain(symbol, expiry) if use_live else _eod_chain_to_live_format(symbol, expiry)

    if "error" in chain:
        return chain

    spot = chain.get("underlying") or 0.0
    exp  = chain.get("expiry", "")
    dte  = days_to_expiry(exp) if exp else 0
    rows = chain.get("data", [])
    if not rows:
        return {"error": f"No chain data for {symbol}", "symbol": symbol}

    df = pd.DataFrame(rows)
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    sorted_strikes = sorted(df["strike"].dropna().unique().tolist())

    # ATM index
    atm_idx = min(range(len(sorted_strikes)),
                  key=lambda i: abs(sorted_strikes[i] - spot))

    lot_size = get_lot_size(symbol) or 1
    legs_detail = []
    net_premium = 0.0

    for leg in strat["legs"]:
        strike_pos = atm_idx + leg["strike_offset"]
        strike_pos = max(0, min(strike_pos, len(sorted_strikes) - 1))
        k = sorted_strikes[strike_pos]

        opt_col = "ce_ltp" if leg["type"] == "CE" else "pe_ltp"
        row = df[df["strike"] == k]
        ltp = float(row[opt_col].iloc[0]) if not row.empty and opt_col in row.columns else 0.0

        iv_col = "ce_iv" if leg["type"] == "CE" else "pe_iv"
        iv = float(row[iv_col].iloc[0]) if not row.empty and iv_col in row.columns and row[iv_col].notna().any() else None

        greeks = {}
        if iv and iv > 0 and dte > 0:
            greeks = calc_greeks(spot, k, dte, iv / 100, leg["type"])

        sign = +1 if leg["action"] == "BUY" else -1
        net_premium += sign * ltp

        legs_detail.append({
            "action":   leg["action"],
            "type":     leg["type"],
            "strike":   k,
            "ltp":      round(ltp, 2),
            "iv":       round(iv, 2) if iv else None,
            "greeks":   greeks,
            "expiry":   exp,
            "lot_size": lot_size,
            "cost_per_lot": round(sign * ltp * lot_size, 2),
        })

    # ── Payoff metrics ────────────────────────────────────────────────────────
    net_premium = round(net_premium, 2)
    breakevens = _calc_breakevens(strategy_key, legs_detail, net_premium)
    max_risk, max_reward = _calc_risk_reward(strategy_key, legs_detail, net_premium, sorted_strikes)

    # ── Payoff at expiry (for chart data) ────────────────────────────────────
    step = max(1, round((sorted_strikes[-1] - sorted_strikes[0]) / 50))
    payoff_curve = _payoff_at_expiry(legs_detail, sorted_strikes[0], sorted_strikes[-1], step)

    return {
        "symbol":          symbol,
        "strategy":        strat["name"],
        "view":            strat["view"],
        "best_when":       strat["best_when"],
        "underlying":      spot,
        "expiry":          exp,
        "dte":             dte,
        "source":          chain.get("source", "unknown"),
        "legs":            legs_detail,
        "net_premium":     net_premium,
        "net_premium_per_lot": round(net_premium * lot_size, 2),
        "max_risk":        max_risk,
        "max_reward":      max_reward,
        "breakevens":      breakevens,
        "payoff_curve":    payoff_curve,
        "lot_size":        lot_size,
        "risk": {
            "label": strat["risk"],
            "reward_label": strat["reward"],
        }
    }


def _calc_breakevens(strategy_key: str, legs: list[dict],
                     net_premium: float) -> list[float]:
    """Compute breakeven points for common strategies."""
    if not legs:
        return []

    buy_legs  = [l for l in legs if l["action"] == "BUY"]
    sell_legs = [l for l in legs if l["action"] == "SELL"]

    if strategy_key == "long_call":
        return [round(buy_legs[0]["strike"] + abs(net_premium), 2)]
    if strategy_key == "long_put":
        return [round(buy_legs[0]["strike"] - abs(net_premium), 2)]
    if strategy_key == "bull_call_spread":
        return [round(buy_legs[0]["strike"] + abs(net_premium), 2)]
    if strategy_key == "bear_put_spread":
        return [round(buy_legs[0]["strike"] - abs(net_premium), 2)]
    if strategy_key in ("long_straddle", "long_strangle"):
        strikes = sorted(set(l["strike"] for l in buy_legs))
        atm = strikes[len(strikes) // 2]
        return [
            round(atm - abs(net_premium), 2),
            round(atm + abs(net_premium), 2),
        ]
    if strategy_key == "iron_condor":
        pe_sell  = min(l["strike"] for l in sell_legs if l["type"] == "PE")
        ce_sell  = max(l["strike"] for l in sell_legs if l["type"] == "CE")
        credit   = abs(net_premium)
        return [round(pe_sell - credit, 2), round(ce_sell + credit, 2)]
    return []


def _calc_risk_reward(strategy_key: str, legs: list[dict],
                      net_premium: float,
                      all_strikes: list[float]) -> tuple[str, str]:
    lot = legs[0]["lot_size"] if legs else 1

    if strategy_key in ("long_call", "long_put",
                         "bull_call_spread", "bear_put_spread",
                         "long_straddle", "long_strangle",
                         "protective_put", "calendar_spread"):
        risk = round(abs(net_premium) * lot, 2)
        return (f"₹{risk:,.0f} (net premium)", "Unlimited / spread width")
    if strategy_key == "iron_condor":
        sell_strikes  = sorted(l["strike"] for l in legs if l["action"] == "SELL")
        width = (sell_strikes[-1] - sell_strikes[0]) if len(sell_strikes) >= 2 else 0
        credit = abs(net_premium)
        reward = round(credit * lot, 2)
        risk_amt = round((width - credit) * lot, 2)
        return (f"₹{risk_amt:,.0f}", f"₹{reward:,.0f} net credit")
    if strategy_key == "covered_call":
        reward = round(abs(net_premium) * lot, 2)
        return ("Full stock downside less premium", f"₹{reward:,.0f} premium income")

    return ("See strategy description", "See strategy description")


def _payoff_at_expiry(legs: list[dict], low: float, high: float,
                      step: float) -> list[dict[str, float]]:
    """Return payoff curve data points [{spot, payoff}, ...]."""
    points = []
    spot = low
    while spot <= high + step:
        pnl = 0.0
        for leg in legs:
            k     = leg["strike"]
            ltp   = leg["ltp"]
            sign  = 1 if leg["action"] == "BUY" else -1
            if leg["type"] == "CE":
                intrinsic = max(0.0, spot - k)
            else:
                intrinsic = max(0.0, k - spot)
            pnl += sign * (intrinsic - ltp)
        points.append({"spot": round(spot, 1), "payoff": round(pnl, 2)})
        spot += step
    return points


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Recommender
# ─────────────────────────────────────────────────────────────────────────────
def recommend_strategies(symbol: str, expiry: str | None = None,
                          use_live: bool = True) -> dict:
    """
    Analyse current market conditions and recommend top 3 options strategies.
    Uses PCR, IV context, dte, and max pain.
    """
    chain_analysis = analyze_option_chain(symbol, expiry, use_live)
    if "error" in chain_analysis:
        return chain_analysis

    spot    = chain_analysis.get("underlying", 0)
    pcr     = chain_analysis.get("pcr", {}).get("oi")
    dte     = chain_analysis.get("dte", 0)
    iv_skew = chain_analysis.get("iv_skew")
    max_pain = chain_analysis.get("max_pain")
    avg_iv  = None
    if iv_skew:
        avg_iv = (iv_skew.get("put_iv_avg", 0) + iv_skew.get("call_iv_avg", 0)) / 2

    recommendations: list[dict] = []

    # ── Low IV → buying strategies preferred ─────────────────────────────────
    if avg_iv is None or avg_iv < 20:
        iv_regime = "low"
    elif avg_iv < 35:
        iv_regime = "medium"
    else:
        iv_regime = "high"

    # ── PCR-based directional view ────────────────────────────────────────────
    if pcr and pcr > 1.3 and dte > 7:
        recommendations.append({
            "rank": 1,
            "strategy": "bull_call_spread",
            "rationale": f"PCR {pcr:.2f} (bullish) + {dte} DTE — limited-risk upside play",
        })
    elif pcr and pcr < 0.7 and dte > 7:
        recommendations.append({
            "rank": 1,
            "strategy": "bear_put_spread",
            "rationale": f"PCR {pcr:.2f} (bearish) + {dte} DTE — limited-risk downside play",
        })

    # ── Low IV + directional → plain long call/put ───────────────────────────
    if iv_regime == "low":
        if pcr and pcr >= 1.0:
            recommendations.append({
                "rank": 2,
                "strategy": "long_call",
                "rationale": f"Low IV ({avg_iv:.0f}%) → cheap to buy calls; bullish PCR {pcr:.2f}",
            })
        else:
            recommendations.append({
                "rank": 2,
                "strategy": "long_put",
                "rationale": f"Low IV ({avg_iv:.0f}%) → cheap to buy puts; bearish PCR {pcr:.2f}" if pcr else "Low IV → buying puts is cost-effective",
            })

    # ── Pre-event (DTE ≤ 7) → straddle/strangle ─────────────────────────────
    if dte <= 7:
        recommendations.append({
            "rank": 3,
            "strategy": "long_straddle",
            "rationale": f"Only {dte} DTE — straddle captures expiry-week volatility in either direction",
        })
    elif iv_regime in ("low", "medium"):
        recommendations.append({
            "rank": 3,
            "strategy": "long_strangle",
            "rationale": f"IV at {avg_iv:.0f}% — OTM strangle is affordable; captures moves beyond ±1 strike",
        })
    else:
        recommendations.append({
            "rank": 3,
            "strategy": "iron_condor",
            "rationale": f"High IV ({avg_iv:.0f}%) — selling iron condor collects rich premium in range-bound market",
        })

    # Deduplicate
    seen, final = set(), []
    for r in recommendations:
        if r["strategy"] not in seen:
            seen.add(r["strategy"])
            final.append(r)

    return {
        "symbol":          symbol,
        "underlying":      spot,
        "expiry":          chain_analysis.get("expiry"),
        "dte":             dte,
        "iv_regime":       iv_regime,
        "pcr_oi":          pcr,
        "max_pain":        max_pain,
        "recommendations": final[:3],
        "chain_summary":   {
            k: chain_analysis[k]
            for k in ("pcr", "top_ce_oi_strikes", "top_pe_oi_strikes", "oi_buildup")
            if k in chain_analysis
        },
    }
