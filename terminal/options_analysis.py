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
    _iv_str = f"{avg_iv:.0f}%" if avg_iv is not None else "N/A"
    if iv_regime == "low":
        if pcr and pcr >= 1.0:
            recommendations.append({
                "rank": 2,
                "strategy": "long_call",
                "rationale": f"Low IV ({_iv_str}) → cheap to buy calls; bullish PCR {pcr:.2f}",
            })
        else:
            recommendations.append({
                "rank": 2,
                "strategy": "long_put",
                "rationale": f"Low IV ({_iv_str}) → cheap to buy puts; bearish PCR {pcr:.2f}" if pcr else "Low IV → buying puts is cost-effective",
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
            "rationale": f"IV at {_iv_str} — OTM strangle is affordable; captures moves beyond ±1 strike",
        })
    else:
        recommendations.append({
            "rank": 3,
            "strategy": "iron_condor",
            "rationale": f"High IV ({_iv_str}) — selling iron condor collects rich premium in range-bound market",
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


# ─────────────────────────────────────────────────────────────────────────────
# ██████████  OPTIONS BUYING ENGINE  ██████████
# ─────────────────────────────────────────────────────────────────────────────
# This section focuses exclusively on debit (buying) strategies:
#   Long Call / Long Put / Bull Call Spread / Bear Put Spread /
#   Long Straddle / Long Strangle / Calendar Spread
#
# Key framework:
#   1. IV regime  — buy when IV is cheap relative to expected realised vol
#   2. IV rank    — estimate cheapness vs recent history
#   3. Expected Move — what the market is pricing in
#   4. Strike selection — ATM (high delta, high cost) vs OTM (leverage)
#   5. DTE selection — at least 2× the time you expect the move to take
#   6. Theta profile — how fast the premium erodes
#   7. Discipline — 50% premium stop, 100-200% profit target
# ─────────────────────────────────────────────────────────────────────────────

# IV regime thresholds for Indian markets (empirical)
_IV_REGIMES = [
    (0,   10, "Very Low",  "Extremely cheap — ideal buying conditions"),
    (10,  15, "Low",       "Cheap to buy — favours debit strategies"),
    (15,  20, "Moderate",  "Fair value — select buying with strong directional view"),
    (20,  28, "Elevated",  "Expensive — prefer spreads over naked buys to reduce cost"),
    (28,  40, "High",      "Costly — use tight spreads or avoid naked long options"),
    (40, 999, "Extreme",   "Very expensive — selling strategies preferred; avoid naked buys"),
]


def _iv_regime_label(iv_pct: float) -> tuple[str, str]:
    """Return (regime_label, advice) for a given IV%."""
    for lo, hi, label, advice in _IV_REGIMES:
        if lo <= iv_pct < hi:
            return label, advice
    return "Unknown", "Insufficient data"


# ─────────────────────────────────────────────────────────────────────────────
# IV Calculation from Option Prices (chain-wide)
# ─────────────────────────────────────────────────────────────────────────────

def calc_chain_ivs(chain_data: dict) -> dict:
    """
    Calculate implied volatility for every strike in the chain from LTP.
    Returns chain_data enriched with 'ce_iv_calc' and 'pe_iv_calc' for each row.
    Also returns summary: atm_iv, atm_ce_iv, atm_pe_iv, avg_iv, iv_skew.
    """
    rows  = chain_data.get("data", [])
    spot  = chain_data.get("underlying") or 0.0
    exp   = chain_data.get("expiry", "")
    dte   = days_to_expiry(exp) if exp else 0

    if not rows or spot <= 0 or dte <= 0:
        return {**chain_data, "iv_summary": {"error": "Insufficient data for IV calculation"}}

    enriched = []
    ce_ivs, pe_ivs = [], []

    for row in rows:
        r = dict(row)
        k = float(r.get("strike", 0))
        if k <= 0:
            enriched.append(r)
            continue

        for opt_type, ltp_key, iv_key in [("CE", "ce_ltp", "ce_iv_calc"),
                                            ("PE", "pe_ltp", "pe_iv_calc")]:
            ltp = float(r.get(ltp_key) or 0)
            # Only compute IV if LTP is meaningful (> intrinsic + small margin)
            intrinsic = max(0, spot - k if opt_type == "CE" else k - spot)
            if ltp > 0 and ltp >= intrinsic and ltp < spot * 0.5:
                iv = calc_iv(ltp, spot, k, dte, opt_type)
                r[iv_key] = round(iv * 100, 2) if iv else None
                if iv and 3 < iv * 100 < 150:   # sanity bounds
                    if opt_type == "CE":
                        ce_ivs.append((abs(k - spot), iv * 100))
                    else:
                        pe_ivs.append((abs(k - spot), iv * 100))
            else:
                r[iv_key] = None
        enriched.append(r)

    # ATM IV = IV of the strike closest to spot for each side
    atm_ce_iv = min(ce_ivs, key=lambda x: x[0])[1] if ce_ivs else None
    atm_pe_iv = min(pe_ivs, key=lambda x: x[0])[1] if pe_ivs else None
    atm_iv    = round((atm_ce_iv + atm_pe_iv) / 2, 2) if atm_ce_iv and atm_pe_iv else (atm_ce_iv or atm_pe_iv)

    # Average IV (all liquid strikes, weighted by proximity to ATM)
    all_ivs = [iv for _, iv in ce_ivs + pe_ivs]
    avg_iv  = round(float(np.mean(all_ivs)), 2) if all_ivs else None

    # IV skew: put IV (below spot) vs call IV (above spot)
    near_pe = [iv for dist, iv in pe_ivs if dist <= spot * 0.05]
    near_ce = [iv for dist, iv in ce_ivs if dist <= spot * 0.05]
    skew    = round(float(np.mean(near_pe)) - float(np.mean(near_ce)), 2) if near_pe and near_ce else None

    regime, advice = _iv_regime_label(atm_iv or avg_iv or 0)

    iv_summary = {
        "atm_iv":           atm_iv,
        "atm_ce_iv":        round(atm_ce_iv, 2) if atm_ce_iv else None,
        "atm_pe_iv":        round(atm_pe_iv, 2) if atm_pe_iv else None,
        "avg_iv":           avg_iv,
        "iv_skew":          skew,
        "iv_skew_label":    ("Puts expensive (bearish skew)" if skew and skew > 2
                             else ("Calls expensive (bullish skew)" if skew and skew < -2
                                   else "Balanced")),
        "iv_regime":        regime,
        "iv_regime_advice": advice,
        "dte":              dte,
        "expiry":           exp,
    }

    return {**chain_data, "data": enriched, "iv_summary": iv_summary}


# ─────────────────────────────────────────────────────────────────────────────
# Expected Move
# ─────────────────────────────────────────────────────────────────────────────

def calc_expected_move(spot: float, atm_iv: float, dte: int) -> dict:
    """
    Calculate expected move using IV:
      1SD move = spot × IV × √(DTE/365)
    Returns ±1σ, ±2σ price levels and % moves.
    """
    if spot <= 0 or atm_iv <= 0 or dte <= 0:
        return {"error": "Insufficient data"}

    sigma_daily = atm_iv / 100 / math.sqrt(365)
    move_1sd    = spot * (atm_iv / 100) * math.sqrt(dte / 365)
    move_2sd    = move_1sd * 2

    # Straddle-based expected move (market price method):
    # EM ≈ 0.85 × ATM_straddle (rough approximation)

    return {
        "spot":              spot,
        "dte":               dte,
        "atm_iv_pct":        atm_iv,
        "sigma_daily_pct":   round(sigma_daily * 100, 3),
        "expected_move_1sd": round(move_1sd, 2),
        "expected_move_1sd_pct": round(move_1sd / spot * 100, 2),
        "upper_1sd":         round(spot + move_1sd, 2),
        "lower_1sd":         round(spot - move_1sd, 2),
        "upper_2sd":         round(spot + move_2sd, 2),
        "lower_2sd":         round(spot - move_2sd, 2),
        "interpretation":    (
            f"Market expects ±{round(move_1sd,0):.0f} pts ({round(move_1sd/spot*100,1)}%) "
            f"move in {dte} trading days (1σ = 68% probability). "
            f"Range: {round(spot-move_1sd,0):.0f} – {round(spot+move_1sd,0):.0f}"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Strike Selection Guide
# ─────────────────────────────────────────────────────────────────────────────

def strike_selection_guide(spot: float, atm_iv: float, dte: int,
                            direction: str, budget_per_lot: float | None = None,
                            chain_rows: list | None = None) -> dict:
    """
    Recommend optimal strike(s) for a directional options buy.
    direction: 'bullish' | 'bearish' | 'volatile'
    Returns ATM, slight-OTM, and deep-OTM with cost/delta/breakeven tradeoffs.
    """
    direction = direction.lower()
    em = calc_expected_move(spot, atm_iv, dte)

    # Strike offsets relative to expected move
    strike_profiles = []
    opt_type = "CE" if direction == "bullish" else ("PE" if direction == "bearish" else "CE")

    # Build strike options
    profiles_config = [
        ("ITM",         -0.10 if direction == "bullish" else +0.10,
         "High delta (0.6–0.8), expensive, forgiving, lower leverage",
         "Conservative — high probability of being ITM at expiry"),
        ("ATM",          0.0,
         "Delta ~0.5, moderate cost, balanced risk/reward",
         "Balanced — best for capturing directional moves"),
        ("Slight OTM",  +0.03 if direction == "bullish" else -0.03,
         "Delta 0.35–0.45, cheaper, needs bigger move to break even",
         "Moderate leverage — good if move > 1σ expected"),
        ("OTM",         +0.05 if direction == "bullish" else -0.05,
         "Delta 0.2–0.35, cheap, needs large move",
         "High leverage — use only with strong conviction"),
        ("Far OTM",     +0.08 if direction == "bullish" else -0.08,
         "Delta < 0.2, lottery ticket, mostly theta decay",
         "Avoid unless targeting multi-sigma event move"),
    ]

    for label, pct_offset, cost_note, recommendation in profiles_config:
        k = round(spot * (1 + pct_offset) / 50) * 50   # round to nearest 50
        greeks = calc_greeks(spot, k, dte, atm_iv / 100, opt_type) if atm_iv > 0 else {}
        ltp = greeks.get("theoretical_price", 0)

        # Find nearest actual strike from chain
        actual_ltp = None
        if chain_rows:
            ltp_key = "ce_ltp" if opt_type == "CE" else "pe_ltp"
            nearest = min(chain_rows, key=lambda r: abs(float(r.get("strike", 0)) - k), default=None)
            if nearest:
                k = float(nearest["strike"])
                actual_ltp = float(nearest.get(ltp_key) or 0)
                greeks = calc_greeks(spot, k, dte, atm_iv / 100, opt_type) if atm_iv > 0 else {}

        delta = abs(greeks.get("delta", 0))
        theta = greeks.get("theta", 0)
        price = actual_ltp if actual_ltp else greeks.get("theoretical_price", ltp)

        be = round(k + price, 2) if direction == "bullish" else round(k - price, 2)
        pct_to_be = round((be / spot - 1) * 100, 2) if direction == "bullish" else round((1 - be / spot) * 100, 2)
        em_move  = em.get("expected_move_1sd_pct", 0)

        strike_profiles.append({
            "label":          label,
            "strike":         k,
            "option_type":    opt_type,
            "ltp":            round(price, 2),
            "delta":          round(delta, 3),
            "theta_per_day":  round(theta, 2),
            "breakeven":      be,
            "pct_to_breakeven": pct_to_be,
            "vs_expected_move": (
                f"Breakeven needs {pct_to_be:.1f}% move vs expected {em_move:.1f}% (1σ)"
                if em_move else ""
            ),
            "cost_profile":   cost_note,
            "recommendation": recommendation,
            "is_recommended": label in ("ATM", "Slight OTM"),
        })

    # DTE recommendation
    dte_advice = _dte_recommendation(dte, atm_iv)

    return {
        "symbol_spot":     spot,
        "direction":       direction,
        "option_type":     opt_type,
        "atm_iv":          atm_iv,
        "dte":             dte,
        "expected_move":   em,
        "strike_profiles": strike_profiles,
        "dte_advice":      dte_advice,
        "buying_rules":    _BUYING_DISCIPLINE,
    }


def _dte_recommendation(dte: int, iv: float) -> dict:
    """Recommend DTE range based on IV and current DTE."""
    if dte <= 3:
        return {
            "label": "Expiry Day / Last Days",
            "advice": "Extreme time decay. Only for experienced traders. Gamma play only.",
            "ideal_dte_range": "0–3 DTE",
            "risk": "VERY HIGH theta decay — position can go to zero overnight",
        }
    elif dte <= 7:
        return {
            "label": "Expiry Week",
            "advice": "High gamma, high risk. Need quick move. Avoid if unsure.",
            "ideal_dte_range": "4–7 DTE",
            "risk": "HIGH theta decay — suitable only for strong conviction moves",
        }
    elif dte <= 15:
        return {
            "label": "Near-Term",
            "advice": "Sweet spot for options buyers with 5-10 day view.",
            "ideal_dte_range": "8–15 DTE",
            "risk": "MODERATE theta — positions manageable if move happens within a week",
        }
    elif dte <= 30:
        return {
            "label": "Monthly Expiry",
            "advice": "Good balance of theta and time. Suitable for 2-3 week thesis.",
            "ideal_dte_range": "15–30 DTE",
            "risk": "LOW-MODERATE theta decay in first half, accelerates in second half",
        }
    else:
        return {
            "label": "Far-Term (LEAPS equivalent)",
            "advice": "Low theta burn, high cost. Best for big structural moves.",
            "ideal_dte_range": "30+ DTE",
            "risk": "LOW theta — most forgiving but expensive in absolute premium",
        }


_BUYING_DISCIPLINE = {
    "stop_loss":       "Exit when premium falls 50% from entry (lose max half the premium paid)",
    "profit_target":   "Book partial at 50-80% gain; trail remainder",
    "exit_by_time":    "Exit at 50% of DTE if position is flat (theta decay accelerates)",
    "avoid_over_hold": "Never hold naked options to expiry hoping for recovery",
    "position_sizing": "Risk max 2-3% of capital per trade (premium paid = max risk)",
    "iv_entry":        "Prefer IV < 20% for index, < 30% for stocks before buying",
    "best_entry":      "Buy at IV contraction (after event) not IV expansion (before event)",
}


# ─────────────────────────────────────────────────────────────────────────────
# Theta Decay Profile
# ─────────────────────────────────────────────────────────────────────────────

def theta_decay_profile(spot: float, strike: float, total_dte: int,
                         sigma: float, option_type: str = "CE") -> dict:
    """
    Show how an option's value erodes over time (theta decay curve).
    Returns a day-by-day table for key DTE checkpoints.
    """
    if total_dte <= 0 or sigma <= 0:
        return {"error": "Insufficient data"}

    entry_price = bs_price(spot, strike, total_dte / 365, RISK_FREE_RATE, sigma, option_type)
    checkpoints = []

    # Key DTE points to show
    dtes = [total_dte, int(total_dte * 0.75), int(total_dte * 0.5),
            int(total_dte * 0.25), 7, 3, 1, 0]
    dtes = sorted(set(d for d in dtes if 0 <= d <= total_dte), reverse=True)

    for dte in dtes:
        T = dte / 365
        price = bs_price(spot, strike, T, RISK_FREE_RATE, sigma, option_type) if dte > 0 else max(0, spot - strike if option_type == "CE" else strike - spot)
        pct_remaining = round(price / entry_price * 100, 1) if entry_price > 0 else 0
        days_elapsed = total_dte - dte
        checkpoints.append({
            "dte":               dte,
            "days_elapsed":      days_elapsed,
            "option_price":      round(price, 2),
            "value_remaining_pct": pct_remaining,
            "value_lost_pct":    round(100 - pct_remaining, 1),
        })

    # 50% value DTE (when option loses half its value to time decay alone)
    half_val_dte = None
    for i in range(total_dte, -1, -1):
        p = bs_price(spot, strike, i / 365, RISK_FREE_RATE, sigma, option_type) if i > 0 else 0
        if p <= entry_price * 0.5:
            half_val_dte = i
            break

    return {
        "entry_dte":       total_dte,
        "entry_price":     round(entry_price, 2),
        "strike":          strike,
        "option_type":     option_type,
        "sigma_pct":       round(sigma * 100, 2),
        "checkpoints":     checkpoints,
        "half_value_at_dte": half_val_dte,
        "half_value_warning": (
            f"Option loses 50% value by DTE {half_val_dte} — exit by then if no move"
            if half_val_dte else None
        ),
        "key_insight": (
            "Last 30% of DTE accounts for ~50% of theta decay — exit early if position is flat"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Probability of Profit (Delta-based)
# ─────────────────────────────────────────────────────────────────────────────

def probability_itm(spot: float, strike: float, dte: int,
                     sigma: float, option_type: str = "CE") -> dict:
    """
    Estimate probability of finishing ITM using BS delta.
    Also compute probability of reaching 100% profit (breakeven × 2).
    """
    greeks = calc_greeks(spot, strike, dte, sigma, option_type)
    delta  = abs(greeks.get("delta", 0))
    ltp    = greeks.get("theoretical_price", 0)

    # Probability of reaching target (2× premium = breakeven + premium)
    target_spot = strike + 2 * ltp if option_type == "CE" else strike - 2 * ltp
    target_greeks = calc_greeks(spot, target_spot, dte, sigma, option_type) if target_spot > 0 else {}
    prob_target = abs(target_greeks.get("delta", 0)) if target_greeks else 0

    return {
        "strike":                 strike,
        "option_type":            option_type,
        "prob_itm_at_expiry_pct": round(delta * 100, 1),
        "prob_2x_return_pct":     round(prob_target * 100, 1),
        "delta":                  round(delta, 3),
        "ltp":                    round(ltp, 2),
        "breakeven":              round(strike + ltp if option_type == "CE" else strike - ltp, 2),
        "interpretation":         (
            f"{round(delta*100,0):.0f}% chance of finishing ITM; "
            f"{round(prob_target*100,0):.0f}% chance of reaching 2× return target"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Deep Options Buying Analysis — Single Symbol
# ─────────────────────────────────────────────────────────────────────────────

def analyze_buying_opportunity(symbol: str, direction: str = "bullish",
                                 expiry: str | None = None,
                                 use_live: bool = True) -> dict:
    """
    Comprehensive options buying analysis for a symbol:
      • ATM IV and regime (cheap/expensive)
      • Expected move (what market is pricing in)
      • Strike selection guide (ITM / ATM / OTM with cost, delta, breakeven)
      • Top 2 recommended strikes with full greeks
      • Theta decay profile for recommended strike
      • OI structure (support/resistance for the view)
      • Buying discipline checklist
    """
    direction = direction.lower()
    if direction not in ("bullish", "bearish", "volatile"):
        direction = "bullish"

    # ── Fetch and enrich chain ────────────────────────────────────────────────
    chain_raw = (
        fetch_live_option_chain(symbol, expiry)
        if use_live else
        _eod_chain_to_live_format(symbol, expiry)
    )
    if "error" in chain_raw:
        return chain_raw

    chain = calc_chain_ivs(chain_raw)
    iv_summary = chain.get("iv_summary", {})
    atm_iv = iv_summary.get("atm_iv") or iv_summary.get("avg_iv") or 18.0  # fallback
    spot   = chain.get("underlying") or 0.0
    exp    = chain.get("expiry", "")
    dte    = days_to_expiry(exp) if exp else 0

    if spot <= 0:
        return {"error": f"Could not determine spot price for {symbol}", "symbol": symbol}

    # ── Expected move ─────────────────────────────────────────────────────────
    em = calc_expected_move(spot, atm_iv, dte)

    # ── Strike selection ──────────────────────────────────────────────────────
    strike_guide = strike_selection_guide(
        spot, atm_iv, dte, direction,
        chain_rows=chain.get("data", [])
    )

    # ── Pick top 2 recommended strikes ───────────────────────────────────────
    recommended = [s for s in strike_guide["strike_profiles"] if s["is_recommended"]][:2]

    # ── Theta decay for ATM strike ────────────────────────────────────────────
    atm_strike_info = next(
        (s for s in strike_guide["strike_profiles"] if s["label"] == "ATM"), None
    )
    theta_profile = None
    if atm_strike_info and dte > 0:
        theta_profile = theta_decay_profile(
            spot, atm_strike_info["strike"], dte,
            atm_iv / 100,
            "CE" if direction == "bullish" else "PE"
        )

    # ── OI context for the directional view ──────────────────────────────────
    oi_context = {}
    rows = chain.get("data", [])
    if rows:
        df = pd.DataFrame(rows)
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
        df = df.dropna(subset=["strike"])

        if direction == "bullish":
            # Nearest CE resistance wall above spot
            above = df[df["strike"] > spot].nlargest(3, "ce_oi")
            oi_context["resistance_walls"] = above[["strike", "ce_oi", "ce_ltp"]].to_dict("records")
            oi_context["note"] = "Call OI above spot = resistance. Break above these for target."
        elif direction == "bearish":
            below = df[df["strike"] < spot].nlargest(3, "pe_oi")
            oi_context["support_walls"] = below[["strike", "pe_oi", "pe_ltp"]].to_dict("records")
            oi_context["note"] = "Put OI below spot = support. Break below for target."
        else:
            top_ce = df.nlargest(2, "ce_oi")[["strike", "ce_oi"]].to_dict("records")
            top_pe = df.nlargest(2, "pe_oi")[["strike", "pe_oi"]].to_dict("records")
            oi_context = {"top_ce_walls": top_ce, "top_pe_walls": top_pe,
                          "note": "Straddle/strangle must break beyond both walls for profit."}

    # ── PCR and max pain context ──────────────────────────────────────────────
    chain_analysis = analyze_option_chain(symbol, expiry, use_live)
    pcr        = chain_analysis.get("pcr", {}) if "error" not in chain_analysis else {}
    max_pain   = chain_analysis.get("max_pain")

    # ── IV rank proxy (estimated from ATM IV vs typical NIFTY/stock ranges) ──
    iv_rank_proxy = _estimate_iv_rank(symbol, atm_iv)

    # ── Overall buying verdict ────────────────────────────────────────────────
    verdict = _buying_verdict(atm_iv, iv_rank_proxy, dte, direction, pcr)

    return {
        "symbol":          symbol,
        "underlying":      spot,
        "expiry":          exp,
        "dte":             dte,
        "direction":       direction,
        "source":          chain.get("source", "unknown"),
        "iv_summary":      iv_summary,
        "iv_rank_proxy":   iv_rank_proxy,
        "expected_move":   em,
        "strike_guide":    strike_guide,
        "recommended_strikes": recommended,
        "theta_decay":     theta_profile,
        "oi_context":      oi_context,
        "pcr":             pcr,
        "max_pain":        max_pain,
        "verdict":         verdict,
        "buying_discipline": _BUYING_DISCIPLINE,
    }


def _estimate_iv_rank(symbol: str, current_iv: float) -> dict:
    """
    Estimate IV rank without full history.
    Uses empirical typical-IV ranges for NSE indices and stocks.
    """
    # Typical annualised IV ranges for NSE instruments (empirical)
    _typical_ranges: dict[str, tuple[float, float]] = {
        "NIFTY":      (10, 28),
        "BANKNIFTY":  (12, 35),
        "FINNIFTY":   (12, 32),
        "MIDCPNIFTY": (14, 38),
    }
    sym = symbol.upper()
    lo, hi = _typical_ranges.get(sym, (15, 60))   # stocks have wider range

    rank = round((current_iv - lo) / (hi - lo) * 100, 1) if hi > lo else 50.0
    rank = max(0.0, min(100.0, rank))

    return {
        "current_iv":     round(current_iv, 2),
        "typical_range":  f"{lo}%–{hi}%",
        "iv_rank_pct":    rank,
        "label":          (
            "Very Low (Top buying zone)"    if rank < 20 else
            "Low (Good buying zone)"        if rank < 35 else
            "Medium (Selective buying)"     if rank < 60 else
            "High (Spreads preferred)"      if rank < 80 else
            "Extreme (Avoid buying naked)"
        ),
        "note": (
            "IV rank is estimated from typical historical ranges. "
            "Download more EOD bhavcopy history for precise rank."
        ),
    }


def _buying_verdict(iv: float, iv_rank: dict, dte: int,
                     direction: str, pcr: dict) -> dict:
    """Produce a clear BUY / SPREAD / AVOID verdict for options buying."""
    rank   = iv_rank.get("iv_rank_pct", 50)
    pcr_oi = pcr.get("oi") if pcr else None

    score = 0
    reasons = []

    # IV score
    if iv < 15:
        score += 3
        reasons.append(f"✅ IV {iv:.1f}% is very low — cheap to buy options")
    elif iv < 20:
        score += 2
        reasons.append(f"✅ IV {iv:.1f}% is low — reasonable cost for buyers")
    elif iv < 28:
        score += 1
        reasons.append(f"⚠️  IV {iv:.1f}% is moderate — prefer spreads to reduce cost")
    else:
        score -= 1
        reasons.append(f"❌ IV {iv:.1f}% is high — options are expensive to buy")

    # IV rank score
    if rank < 30:
        score += 2
        reasons.append(f"✅ IV rank {rank:.0f}% — historically cheap")
    elif rank < 60:
        score += 1
        reasons.append(f"⚠️  IV rank {rank:.0f}% — moderate; not the cheapest")
    else:
        score -= 1
        reasons.append(f"❌ IV rank {rank:.0f}% — expensive relative to history")

    # DTE score
    if 8 <= dte <= 20:
        score += 2
        reasons.append(f"✅ DTE {dte} is ideal for options buyers (sweet spot)")
    elif 21 <= dte <= 35:
        score += 1
        reasons.append(f"✅ DTE {dte} — good time for monthly expiry play")
    elif dte < 5:
        score -= 2
        reasons.append(f"❌ DTE {dte} — extreme theta decay risk")
    elif dte < 8:
        score -= 1
        reasons.append(f"⚠️  DTE {dte} — be very selective; theta accelerating")

    # PCR alignment
    if pcr_oi:
        if direction == "bullish" and pcr_oi > 1.0:
            score += 1
            reasons.append(f"✅ PCR {pcr_oi:.2f} — put writing = bullish sentiment aligns")
        elif direction == "bearish" and pcr_oi < 0.8:
            score += 1
            reasons.append(f"✅ PCR {pcr_oi:.2f} — call writing = bearish sentiment aligns")
        elif direction == "bullish" and pcr_oi < 0.7:
            score -= 1
            reasons.append(f"⚠️  PCR {pcr_oi:.2f} — bearish OI; cautious on bullish play")

    # Verdict
    if score >= 6:
        verdict_label = "STRONG BUY SETUP"
        verdict_color = "green"
    elif score >= 4:
        verdict_label = "GOOD BUYING OPPORTUNITY"
        verdict_color = "green"
    elif score >= 2:
        verdict_label = "USE SPREAD (not naked long)"
        verdict_color = "yellow"
    elif score >= 0:
        verdict_label = "SELECTIVE — SMALL POSITION ONLY"
        verdict_color = "yellow"
    else:
        verdict_label = "AVOID BUYING — IV TOO HIGH"
        verdict_color = "red"

    return {
        "label":       verdict_label,
        "score":       score,
        "color":       verdict_color,
        "reasons":     reasons,
        "action":      (
            "Preferred strategy: ATM or slight-OTM buy" if score >= 4 else
            "Preferred strategy: debit spread (reduce IV cost)" if score >= 2 else
            "Consider waiting for IV contraction or use credit spread"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Options Buying Scanner — Cross-Stock
# ─────────────────────────────────────────────────────────────────────────────

def scan_options_buying_opportunities(direction: str = "bullish",
                                       min_oi: int = 500_000,
                                       max_iv: float = 35.0,
                                       top_n: int = 10) -> dict:
    """
    Scan all symbols with options data in the F&O DB.
    Rank by: low IV + strong technical momentum + adequate OI liquidity.

    direction: 'bullish' | 'bearish' | 'volatile'
    min_oi: minimum ATM strike OI for liquidity filter
    max_iv: IV ceiling for buying filter
    """
    import sqlite3
    from terminal.fno_data import FNO_DB, get_available_dates

    if not FNO_DB.exists():
        return {"error": "F&O DB not found. Run refresh_fno_eod_data() first."}

    dates = get_available_dates()
    if not dates:
        return {"error": "No F&O EOD data available."}

    trade_date = dates[0]
    conn = sqlite3.connect(FNO_DB)

    # Get all symbols with adequate options liquidity
    rows = conn.execute("""
        SELECT symbol, option_type, strike, last_price, oi, underlying, expiry_date
        FROM fno_eod
        WHERE trade_date=? AND option_type IS NOT NULL AND oi >= ?
        ORDER BY symbol, expiry_date, strike
    """, (trade_date, min_oi // 10)).fetchall()
    conn.close()

    if not rows:
        return {"error": f"No options data for {trade_date} with OI >= {min_oi//10}"}

    # Group by symbol
    from collections import defaultdict
    by_symbol: dict[str, list] = defaultdict(list)
    for r in rows:
        by_symbol[r[0]].append(r)

    results = []
    for symbol, sym_rows in by_symbol.items():
        try:
            # Get the nearest expiry
            expiries = sorted(set(r[6] for r in sym_rows))
            near_exp = expiries[0]
            near_rows = [r for r in sym_rows if r[6] == near_exp]

            # Find spot and ATM
            spot_vals = [r[5] for r in near_rows if r[5]]
            if not spot_vals:
                continue
            spot = float(spot_vals[0])
            dte  = days_to_expiry(near_exp)

            if dte < 2:  # skip if expiry too close
                near_exp = expiries[1] if len(expiries) > 1 else near_exp
                near_rows = [r for r in sym_rows if r[6] == near_exp]
                dte = days_to_expiry(near_exp)
                if dte < 2:
                    continue

            # ATM strike
            atm_row = min(near_rows, key=lambda r: abs(float(r[2]) - spot))
            atm_k = float(atm_row[2])

            # Find CE and PE ATM rows
            ce_atm = next((r for r in near_rows if abs(float(r[2]) - atm_k) < 1 and r[1] == "CE"), None)
            pe_atm = next((r for r in near_rows if abs(float(r[2]) - atm_k) < 1 and r[1] == "PE"), None)

            if not ce_atm or not pe_atm:
                continue

            ce_ltp = float(ce_atm[3] or 0)
            pe_ltp = float(pe_atm[3] or 0)
            ce_oi  = int(ce_atm[4] or 0)
            pe_oi  = int(pe_atm[4] or 0)

            # Skip low liquidity
            if ce_oi < min_oi and pe_oi < min_oi:
                continue

            # Calculate ATM CE and PE IV
            ce_iv = calc_iv(ce_ltp, spot, atm_k, dte, "CE")
            pe_iv = calc_iv(pe_ltp, spot, atm_k, dte, "PE")
            atm_iv = round(((ce_iv or 0) + (pe_iv or 0)) / 2 * 100, 2)
            if atm_iv <= 0 or atm_iv > max_iv * 1.5:
                continue

            # IV regime
            regime, _ = _iv_regime_label(atm_iv)

            # Expected move
            em_pct = round((atm_iv / 100) * math.sqrt(dte / 365) * 100, 2) if dte > 0 else 0

            # ATM straddle cost
            straddle_cost = round(ce_ltp + pe_ltp, 2)
            straddle_pct  = round(straddle_cost / spot * 100, 2) if spot > 0 else 0

            # Score for ranking
            iv_score   = max(0, 10 - atm_iv / 3)         # lower IV = higher score
            liq_score  = min(5, math.log10(max(ce_oi, pe_oi)) - 4)
            dte_score  = 3 if 8 <= dte <= 25 else (2 if dte <= 35 else 1)
            total_score = round(iv_score + liq_score + dte_score, 2)

            # Direction filter
            if direction == "bullish" and atm_iv > max_iv:
                continue
            if direction == "bearish" and atm_iv > max_iv:
                continue

            results.append({
                "symbol":         symbol,
                "spot":           round(spot, 2),
                "expiry":         near_exp,
                "dte":            dte,
                "atm_strike":     atm_k,
                "ce_ltp":         ce_ltp,
                "pe_ltp":         pe_ltp,
                "atm_iv_pct":     atm_iv,
                "iv_regime":      regime,
                "straddle_cost":  straddle_cost,
                "straddle_pct":   straddle_pct,
                "expected_move_pct": em_pct,
                "ce_oi":          ce_oi,
                "pe_oi":          pe_oi,
                "buying_score":   total_score,
            })
        except Exception:
            continue

    # Sort by score (best buying opportunity first)
    results.sort(key=lambda x: x["buying_score"], reverse=True)

    return {
        "direction":   direction,
        "trade_date":  trade_date,
        "max_iv_filter": max_iv,
        "min_oi_filter": min_oi,
        "total_scanned": len(by_symbol),
        "qualified":   len(results),
        "top_picks":   results[:top_n],
        "methodology": (
            f"Ranked by: low ATM IV (cheaper to buy) + OI liquidity + ideal DTE (8–25). "
            f"Filter: IV < {max_iv}%, ATM OI > {min_oi:,}. "
            f"ATM straddle cost = CE LTP + PE LTP (use for straddle/strangle sizing)."
        ),
    }
