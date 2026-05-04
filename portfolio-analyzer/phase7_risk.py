#!/usr/bin/env python3
"""
Phase 7: Risk modeling and projection scenarios.

Uses popular financial risk profiler metrics:
- Value at Risk (VaR) 95% / 99% (historical)
- Conditional VaR (Expected Shortfall)
- Sharpe ratio (annualized)
- Beta vs Nifty 50 / Nifty 500
- Max drawdown, volatility (annualized)
- Concentration (Herfindahl, top-N weight)

Projection scenarios: apply market situations (e.g. Nifty +10%, -15%, stress)
to current portfolio via beta/weights; LLM narrative for scenario implications.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from config import (
        OUTPUT_DIR,
        HOLDINGS_CSV_OUT,
        CLOSED_PNL_CSV,
        STOCK_CSV,
        INDEX_CSV,
        RISK_METRICS_CSV,
        RISK_METRICS_JSON,
        SCENARIO_PROJECTIONS_CSV,
        SCENARIO_NARRATIVE_MD,
        PROJECT_ROOT,
    )
except ImportError:
    PORTFOLIO_ANALYZER = Path(__file__).resolve().parent
    OUTPUT_DIR = PORTFOLIO_ANALYZER / "output"
    HOLDINGS_CSV_OUT = OUTPUT_DIR / "holdings.csv"
    CLOSED_PNL_CSV = OUTPUT_DIR / "closed_pnl.csv"
    PROJECT_ROOT = PORTFOLIO_ANALYZER.parent
    STOCK_CSV = PROJECT_ROOT / "data" / "nse_sec_full_data.csv"
    INDEX_CSV = PROJECT_ROOT / "data" / "nse_index_data.csv"
    RISK_METRICS_CSV = OUTPUT_DIR / "risk_metrics.csv"
    RISK_METRICS_JSON = OUTPUT_DIR / "risk_metrics.json"
    SCENARIO_PROJECTIONS_CSV = OUTPUT_DIR / "scenario_projections.csv"
    SCENARIO_NARRATIVE_MD = OUTPUT_DIR / "scenario_narrative.md"

# Risk-free rate (annualized, decimal). Override via config if needed.
RISK_FREE_RATE_ANNUAL = 0.065  # ~6.5% (e.g. 91-day T-bill proxy)
TRADING_DAYS_PER_YEAR = 252

# Scenario definitions: name, index return assumption (decimal), description
DEFAULT_SCENARIOS = [
    {"id": "nifty_up_10", "name": "Nifty +10%", "index_return": 0.10, "description": "Broad market rally"},
    {"id": "nifty_down_15", "name": "Nifty −15%", "index_return": -0.15, "description": "Market correction"},
    {"id": "nifty_sideways", "name": "Nifty sideways (±2%)", "index_return": 0.0, "description": "Range-bound market"},
    {"id": "stress_20", "name": "Stress (−20%)", "index_return": -0.20, "description": "Severe drawdown"},
    {"id": "rally_15", "name": "Rally +15%", "index_return": 0.15, "description": "Strong bull move"},
]


def load_holdings_weights() -> tuple[pd.DataFrame, dict]:
    """
    Load current holdings and compute weights (by value).
    Falls back to closed_pnl symbols with equal weight if no holdings file.
    Returns (holdings_df with weight column, portfolio_value_rs).
    """
    portfolio_value_rs = 0.0
    if HOLDINGS_CSV_OUT.exists():
        df = pd.read_csv(HOLDINGS_CSV_OUT)
        # Expect columns like symbol/Symbol, quantity/Qty, optional value/Value or price
        sym_col = "symbol" if "symbol" in df.columns else (df.columns[0] if len(df.columns) else None)
        qty_col = next((c for c in df.columns if str(c).lower() in ("qty", "quantity", "qty.")), None)
        val_col = next((c for c in df.columns if str(c).lower() in ("value", "market value", "amount")), None)
        if sym_col and (qty_col or val_col):
            df = df.rename(columns={sym_col: "symbol"})
            df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
            if val_col:
                df["value_rs"] = pd.to_numeric(df[val_col], errors="coerce").fillna(0)
            else:
                df["value_rs"] = 0  # need prices to fill
            portfolio_value_rs = df["value_rs"].sum()
            if portfolio_value_rs <= 0 and qty_col:
                # We'll get value from NSE prices in caller
                df["qty"] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0)
            else:
                df["weight"] = df["value_rs"] / portfolio_value_rs if portfolio_value_rs > 0 else 1.0 / len(df)
            return df, {"portfolio_value_rs": portfolio_value_rs, "source": "holdings.csv"}
    # Fallback: symbols from closed PnL (for risk we use equal weight as proxy)
    if CLOSED_PNL_CSV.exists():
        pnl = pd.read_csv(CLOSED_PNL_CSV)
        if "symbol" in pnl.columns:
            symbols = pnl["symbol"].unique().tolist()
            weights = 1.0 / len(symbols) if symbols else []
            df = pd.DataFrame({"symbol": symbols, "weight": weights})
            return df, {"portfolio_value_rs": None, "source": "closed_pnl_symbols_equal_weight"}
    return pd.DataFrame(), {"portfolio_value_rs": None, "source": None}


def load_returns(symbols: list[str], index_name: str = "Nifty 50", lookback_days: int = 504) -> tuple[pd.DataFrame, pd.Series]:
    """
    Load daily close returns for symbols and index from NSE data.
    Returns (stock_returns DataFrame, index_returns Series).
    """
    if not STOCK_CSV.exists():
        return pd.DataFrame(), pd.Series(dtype=float)
    symbols_upper = [s.strip().upper() for s in symbols]
    try:
        # Single read: filter by symbol then take last lookback_days per symbol
        df = pd.read_csv(
            STOCK_CSV,
            usecols=["SYMBOL", "TIMESTAMP", "CLOSE"],
            dtype={"SYMBOL": str, "CLOSE": float},
        )
        df["SYMBOL"] = df["SYMBOL"].str.strip().str.upper()
        df = df[df["SYMBOL"].isin(symbols_upper)]
        if df.empty:
            return pd.DataFrame(), pd.Series(dtype=float)
        df["date"] = pd.to_datetime(df["TIMESTAMP"])
        df = df.sort_values("date").groupby("SYMBOL").tail(lookback_days)
        df["ret"] = df.groupby("SYMBOL")["CLOSE"].pct_change()
        df = df[["date", "SYMBOL", "ret"]].dropna(subset=["ret"])
        stock_ret = df.pivot_table(index="date", columns="SYMBOL", values="ret").sort_index()
    except Exception:
        return pd.DataFrame(), pd.Series(dtype=float)

    index_ret = pd.Series(dtype=float)
    if INDEX_CSV.exists():
        try:
            idx = pd.read_csv(INDEX_CSV, usecols=["Index Name", "TIMESTAMP", "CLOSE"])
            idx = idx[idx["Index Name"].astype(str).str.strip() == index_name]
            idx = idx.sort_values("TIMESTAMP").tail(lookback_days)
            if not idx.empty:
                idx["date"] = pd.to_datetime(idx["TIMESTAMP"])
                idx["ret"] = idx["CLOSE"].pct_change()
                index_ret = idx.set_index("date")["ret"]
        except Exception:
            pass
    return stock_ret, index_ret


def portfolio_returns(weights: pd.DataFrame, stock_returns: pd.DataFrame) -> pd.Series:
    """Weights: columns symbol, weight. stock_returns: columns = symbols. Returns portfolio daily return series."""
    if weights.empty or stock_returns.empty:
        return pd.Series(dtype=float)
    w = weights.set_index("symbol")["weight"]
    common = [c for c in stock_returns.columns if c in w.index]
    if not common:
        return pd.Series(dtype=float)
    sub = stock_returns[common].copy()
    for c in common:
        sub[c] = sub[c].fillna(0) * w.get(c, 0)
    return sub.sum(axis=1)


def var_historical(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical VaR (negative of the (1-confidence) quantile of returns)."""
    if returns.dropna().empty:
        return np.nan
    return -float(np.percentile(returns.dropna(), (1 - confidence) * 100))


def cvar_historical(returns: pd.Series, confidence: float = 0.95) -> float:
    """Conditional VaR (average of returns worse than VaR)."""
    if returns.dropna().empty:
        return np.nan
    var = var_historical(returns, confidence)
    tail = returns[returns <= -abs(var)]
    return -float(tail.mean()) if len(tail) else np.nan


def max_drawdown(returns: pd.Series) -> float:
    """Peak-to-trough drawdown (positive = drawdown %)."""
    if returns.dropna().empty:
        return np.nan
    cum = (1 + returns).cumprod()
    return float((cum / cum.cummax() - 1).min() * 100)


def sharpe_annual(returns: pd.Series, risk_free_rate_annual: float = RISK_FREE_RATE_ANNUAL) -> float:
    """Annualized Sharpe. risk_free_rate_annual in decimal."""
    if returns.dropna().empty or returns.std() == 0:
        return np.nan
    rf_daily = risk_free_rate_annual / TRADING_DAYS_PER_YEAR
    excess = returns.mean() - rf_daily
    return float(excess / returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def beta_vs_index(port_returns: pd.Series, index_returns: pd.Series) -> float:
    """Portfolio beta vs index."""
    common = port_returns.align(index_returns, join="inner")[0].dropna()
    if common[0].empty or common[1].empty or common[1].var() == 0:
        return np.nan
    return float(common[0].cov(common[1]) / common[1].var())


def concentration_herfindahl(weights: pd.Series) -> float:
    """Herfindahl index (sum of squared weights). 1 = single stock, lower = more diversified."""
    if weights.empty:
        return np.nan
    return float((weights ** 2).sum())


def run_phase7(
    scenarios: list[dict] | None = None,
    risk_free_rate: float = RISK_FREE_RATE_ANNUAL,
    write_narrative: bool = True,
) -> dict:
    """
    Compute risk metrics and scenario projections; write CSV/JSON and optional LLM narrative.
    Returns summary dict with portfolio_volatility, var_95, sharpe, beta, max_drawdown, concentration.
    """
    scenarios = scenarios or DEFAULT_SCENARIOS
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

    holdings, meta = load_holdings_weights()
    if holdings.empty:
        out = {
            "portfolio_volatility_annual_pct": None,
            "var_95_1d_pct": None,
            "cvar_95_1d_pct": None,
            "sharpe_ratio": None,
            "beta_nifty": None,
            "max_drawdown_pct": None,
            "concentration_herfindahl": None,
            "scenarios": [],
            "note": "No holdings or closed_pnl; run Phase 0 first.",
        }
        RISK_METRICS_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(RISK_METRICS_JSON, "w") as f:
            json.dump(out, f, indent=2)
        return out

    symbols = holdings["symbol"].dropna().astype(str).str.strip().str.upper().unique().tolist()
    stock_ret, index_ret = load_returns(symbols, lookback_days=504)
    if "weight" not in holdings.columns:
        holdings["weight"] = 1.0 / len(holdings)
    port_ret = portfolio_returns(holdings[["symbol", "weight"]], stock_ret)

    # Portfolio-level risk metrics
    vol_annual = float(port_ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100) if not port_ret.empty else np.nan
    var_95 = float(var_historical(port_ret, 0.95) * 100)
    cvar_95 = float(cvar_historical(port_ret, 0.95) * 100)
    sharpe = sharpe_annual(port_ret, risk_free_rate)
    beta = beta_vs_index(port_ret, index_ret) if not index_ret.empty else np.nan
    mdd = max_drawdown(port_ret)
    w = holdings.set_index("symbol")["weight"]
    herf = concentration_herfindahl(w)

    risk_summary = {
        "portfolio_volatility_annual_pct": round(vol_annual, 2) if not np.isnan(vol_annual) else None,
        "var_95_1d_pct": round(var_95, 2) if not np.isnan(var_95) else None,
        "cvar_95_1d_pct": round(cvar_95, 2) if not np.isnan(cvar_95) else None,
        "sharpe_ratio": round(sharpe, 2) if not np.isnan(sharpe) else None,
        "beta_nifty": round(beta, 2) if not np.isnan(beta) else None,
        "max_drawdown_pct": round(mdd, 2) if not np.isnan(mdd) else None,
        "concentration_herfindahl": round(herf, 4) if not np.isnan(herf) else None,
        "risk_free_rate_annual": risk_free_rate,
        "holdings_source": meta.get("source"),
        "n_constituents": len(symbols),
    }

    # Per-stock contribution (simplified: weight * vol ratio)
    rows = []
    for sym in symbols:
        sret = stock_ret.get(sym)
        if sret is not None and sret.notna().any():
            vol_s = sret.std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100
            rows.append({"symbol": sym, "weight_pct": w.get(sym, 0) * 100, "volatility_annual_pct": round(vol_s, 2)})
    risk_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    risk_table = pd.DataFrame([risk_summary])
    if not risk_df.empty:
        risk_df.to_csv(RISK_METRICS_CSV, index=False)
    risk_table.to_csv(OUTPUT_DIR / "risk_metrics_portfolio.csv", index=False)
    with open(RISK_METRICS_JSON, "w") as f:
        json.dump({**risk_summary, "per_stock": risk_df.to_dict("records") if not risk_df.empty else []}, f, indent=2)

    # Scenario projections: portfolio return ≈ beta * index_return (simplified)
    beta_use = beta if not np.isnan(beta) else 1.0
    scenario_rows = []
    for s in scenarios:
        idx_ret = s.get("index_return", 0)
        port_proj = beta_use * idx_ret
        scenario_rows.append({
            "scenario_id": s.get("id", ""),
            "scenario_name": s.get("name", ""),
            "index_return_pct": round(idx_ret * 100, 1),
            "portfolio_projected_return_pct": round(port_proj * 100, 1),
            "description": s.get("description", ""),
        })
    scenario_df = pd.DataFrame(scenario_rows)
    scenario_df.to_csv(SCENARIO_PROJECTIONS_CSV, index=False)
    risk_summary["scenarios"] = scenario_rows

    if write_narrative:
        narrative = _write_scenario_narrative(risk_summary, scenario_rows)
        SCENARIO_NARRATIVE_MD.write_text(narrative, encoding="utf-8")

    return risk_summary


def _write_scenario_narrative(risk_summary: dict, scenario_rows: list) -> str:
    """Stub LLM or template narrative for risk and scenarios."""
    lines = [
        "# Portfolio risk and scenario narrative",
        "",
        "## Risk metrics (rule-based)",
        "",
        f"- **Volatility (annualised):** {risk_summary.get('portfolio_volatility_annual_pct')}%",
        f"- **VaR (95%, 1-day):** {risk_summary.get('var_95_1d_pct')}%",
        f"- **CVaR (95%, 1-day):** {risk_summary.get('cvar_95_1d_pct')}%",
        f"- **Sharpe ratio:** {risk_summary.get('sharpe_ratio')}",
        f"- **Beta vs Nifty:** {risk_summary.get('beta_nifty')}",
        f"- **Max drawdown:** {risk_summary.get('max_drawdown_pct')}%",
        f"- **Concentration (Herfindahl):** {risk_summary.get('concentration_herfindahl')}",
        "",
        "## Scenario projections",
        "",
        "Assumption: portfolio return ≈ beta × index return (simplified).",
        "",
        "| Scenario | Index return | Portfolio projected return |",
        "|----------|--------------|---------------------------|",
    ]
    for r in scenario_rows:
        lines.append(f"| {r.get('scenario_name', '')} | {r.get('index_return_pct')}% | {r.get('portfolio_projected_return_pct')}% |")
    lines += [
        "",
        "Use the scenario table above for stress-test assumptions. Consider professional advice for hedging and rebalancing decisions.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    summary = run_phase7()
    print("Phase 7 (risk + scenarios) done.")
    print("  Volatility (ann. %):", summary.get("portfolio_volatility_annual_pct"))
    print("  VaR 95% 1d (%):", summary.get("var_95_1d_pct"))
    print("  Sharpe:", summary.get("sharpe_ratio"))
    print("  Beta:", summary.get("beta_nifty"))
    print("  Max drawdown (%):", summary.get("max_drawdown_pct"))
    print("  Outputs:", RISK_METRICS_CSV, SCENARIO_PROJECTIONS_CSV, SCENARIO_NARRATIVE_MD)
