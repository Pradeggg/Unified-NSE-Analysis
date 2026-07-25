#!/usr/bin/env python3
"""Portfolio-construction layer for Agent Adda NSE signal research.

This module sits downstream of signal generation. It re-simulates executable
next-session fills, converts delivery/slippage friction into R, recomputes net
edge, and builds a constrained daily book with factor-aware risk sizing.

The assumptions in :class:`Config` are intentionally explicit. Slippage and
factor correlation are defaults, not facts; calibrate them against fills before
using this for live allocation.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


log = logging.getLogger("portfolio_construction")

BOOK_COLUMNS = [
    "symbol",
    "sector",
    "setup",
    "net_expectancy_R",
    "risk_pct_of_capital",
    "close",
    "stop",
]


@dataclass
class Config:
    # Exit rules, aligned with the EOD signal-effectiveness research spec.
    target_r: float = 2.0
    timeout_bars: int = 10
    min_risk_floor_pct: float = 0.01

    # Fill model: "next_open" or "limit_at_signal_close".
    fill_model: str = "next_open"

    # Round-trip cost assumptions. Values are notional fractions.
    stt_per_side: float = 0.0010
    exch_sebi_stamp_gst: float = 0.0003
    brokerage_per_side: float = 0.0000
    slippage_base_per_side: float = 0.0010
    slippage_adr_coef: float = 0.020
    slippage_spike_coef: float = 0.0006
    slippage_spike_knee: float = 5.0

    # Daily selector constraints.
    min_turnover_inr: float = 5.0e7

    # Sizing assumptions.
    kelly_fraction: float = 0.25
    factor_rho: float = 0.55
    heat_cap: float = 0.06
    sector_heat_cap: float = 0.025
    per_name_risk_cap: float = 0.0075
    max_positions: int = 6

    ev_cols: dict[str, str] = field(
        default_factory=lambda: {
            "date": "date",
            "symbol": "symbol",
            "setup": "setup",
            "sector": "sector",
            "close": "close",
            "entry": "entry",
            "stop": "stop",
            "target": "target",
            "outcome": "outcome",
            "r_multiple": "r_multiple",
            "volume_ratio": "volume_ratio_20d",
            "adr_pct": "adr_pct_20",
        }
    )
    eod_cols: dict[str, str] = field(
        default_factory=lambda: {
            "date": "date",
            "symbol": "symbol",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "turnover": "turnover_cr",
        }
    )
    queue_cols: dict[str, str] = field(
        default_factory=lambda: {
            "date": "date",
            "symbol": "symbol",
            "sector": "sector",
            "setup": "setup",
            "close": "close",
            "stop": "estimated_stop",
            "volume_ratio": "volume_ratio_20d",
            "adr_pct": "adr_pct_20",
            "turnover": "turnover_cr_20d",
        }
    )

    @property
    def target_R(self) -> float:
        """Compatibility alias for the original design note."""
        return self.target_r


def get_engine(conn_str: str | None):
    if not conn_str:
        return None
    from sqlalchemy import create_engine

    return create_engine(conn_str)


def attach_eod_frame(eod_df: pd.DataFrame) -> None:
    """Attach an in-memory EOD frame for CSV/no-DB re-simulation."""
    load_forward_bars._eod = eod_df.copy()  # type: ignore[attr-defined]
    load_forward_bars._eod_group_cache = None  # type: ignore[attr-defined]


def load_forward_bars(engine: Any, symbol: str, start_date: Any, n_bars: int, cfg: Config) -> pd.DataFrame:
    """Return forward OHLC bars after ``start_date`` for one symbol."""
    c = cfg.eod_cols
    canonical = {v: k for k, v in c.items()}
    if engine is not None:
        query = f"""
            SELECT {c['date']}, {c['open']}, {c['high']}, {c['low']}, {c['close']}
            FROM market.equity_eod
            WHERE upper({c['symbol']}) = upper(%(symbol)s)
              AND {c['date']} > %(start_date)s
              AND series = 'EQ'
            ORDER BY {c['date']} ASC
            LIMIT %(n_bars)s
        """
        rows = pd.read_sql_query(
            query,
            engine,
            params={"symbol": symbol, "start_date": start_date, "n_bars": int(n_bars)},
        )
        return rows.rename(columns=canonical)

    eod = getattr(load_forward_bars, "_eod", None)
    if eod is None:
        raise RuntimeError("No DB engine and no EOD frame attached. Call attach_eod_frame().")
    start = pd.to_datetime(start_date)
    cache_key = tuple(sorted(c.items()))
    cached = getattr(load_forward_bars, "_eod_group_cache", None)
    if not cached or cached.get("key") != cache_key:
        work = eod.copy()
        work[c["date"]] = pd.to_datetime(work[c["date"]], errors="coerce")
        groups = {
            str(sym).upper(): frame.sort_values(c["date"]).rename(columns=canonical).reset_index(drop=True)
            for sym, frame in work.groupby(work[c["symbol"]].astype(str).str.upper(), dropna=False)
        }
        cached = {"key": cache_key, "groups": groups}
        load_forward_bars._eod_group_cache = cached  # type: ignore[attr-defined]
    frame = cached["groups"].get(str(symbol).upper(), pd.DataFrame())
    if frame.empty:
        return frame
    position = pd.to_datetime(frame["date"], errors="coerce").searchsorted(start, side="right")
    return frame.iloc[position : position + int(n_bars)].copy()


def resimulate_signal(signal: pd.Series, bars: pd.DataFrame, cfg: Config) -> dict[str, Any]:
    """Re-simulate one signal using an executable entry and fixed structural stop."""
    if bars is None or bars.empty:
        return {"valid": False, "reason": "no_forward_bars"}

    stop_level = _finite_float(signal.get("stop"))
    signal_close = _finite_float(signal.get("close"))
    if not np.isfinite(stop_level) or not np.isfinite(signal_close):
        return {"valid": False, "reason": "missing_signal_level"}

    bars = bars.reset_index(drop=True).copy()
    for column in ("open", "high", "low", "close"):
        if column not in bars.columns:
            return {"valid": False, "reason": f"missing_{column}"}

    if cfg.fill_model == "next_open":
        entry = _finite_float(bars.loc[0, "open"])
    elif cfg.fill_model == "limit_at_signal_close":
        first_low = _finite_float(bars.loc[0, "low"])
        first_high = _finite_float(bars.loc[0, "high"])
        entry = signal_close if first_low <= signal_close <= first_high else _finite_float(bars.loc[0, "open"])
    else:
        raise ValueError(f"unknown fill_model {cfg.fill_model!r}")

    if not np.isfinite(entry) or entry <= 0:
        return {"valid": False, "reason": "bad_entry"}
    if entry <= stop_level:
        return {"valid": False, "reason": "entry_below_stop"}

    risk = entry - stop_level
    floor = cfg.min_risk_floor_pct * entry
    if risk < floor:
        stop_level = entry - floor
        risk = floor
    if risk <= 0:
        return {"valid": False, "reason": "bad_risk"}

    target_price = entry + cfg.target_r * risk
    bars_to_check = min(len(bars), int(cfg.timeout_bars))
    r_gross: float | None = None
    outcome: str | None = None
    held = 0
    for idx in range(bars_to_check):
        held = idx + 1
        low = _finite_float(bars.loc[idx, "low"])
        high = _finite_float(bars.loc[idx, "high"])
        if low <= stop_level:
            r_gross = -1.0
            outcome = "loss"
            break
        if high >= target_price:
            r_gross = float(cfg.target_r)
            outcome = "target"
            break

    if r_gross is None:
        held = max(1, bars_to_check)
        last_close = _finite_float(bars.loc[held - 1, "close"])
        r_gross = (last_close - entry) / risk
        outcome = "timeout"

    return {
        "valid": True,
        "entry": entry,
        "stop": stop_level,
        "target": target_price,
        "risk_pct": risk / entry,
        "r_gross": r_gross,
        "outcome": outcome,
        "bars_held": held,
    }


def cost_pct(adr_pct: float, volume_ratio: float, cfg: Config) -> float:
    """Round-trip execution cost as notional fraction."""
    adr = _finite_float(adr_pct, default=0.0)
    volume = _finite_float(volume_ratio, default=1.0)
    spike_excess = max(0.0, volume - cfg.slippage_spike_knee)
    slippage_per_side = (
        cfg.slippage_base_per_side
        + cfg.slippage_adr_coef * (adr / 100.0)
        + cfg.slippage_spike_coef * spike_excess
        + cfg.brokerage_per_side
    )
    return cfg.stt_per_side * 2.0 + cfg.exch_sebi_stamp_gst + slippage_per_side * 2.0


def cost_in_r(adr_pct: float, volume_ratio: float, risk_pct: float, cfg: Config) -> float:
    """Round-trip cost expressed in R units."""
    risk = _finite_float(risk_pct)
    if not np.isfinite(risk) or risk <= 0:
        return float("inf")
    return cost_pct(adr_pct, volume_ratio, cfg) / risk


def recompute_net_edge(events: pd.DataFrame, engine: Any, cfg: Config) -> pd.DataFrame:
    """Re-simulate events, subtract execution cost, and return per-event net R."""
    c = cfg.ev_cols
    rows: list[dict[str, Any]] = []
    for _, event in events.iterrows():
        setup = event.get(c["setup"], "")
        symbol = event.get(c["symbol"], "")
        signal = pd.Series({"stop": event.get(c["stop"]), "close": event.get(c["close"])})
        bars = load_forward_bars(engine, symbol, event.get(c["date"]), cfg.timeout_bars, cfg)
        sim = resimulate_signal(signal, bars, cfg)
        base = {
            "date": event.get(c["date"]),
            "symbol": symbol,
            "setup": setup,
            "sector": event.get(c.get("sector", "sector"), ""),
            "valid": bool(sim.get("valid")),
        }
        if not sim.get("valid"):
            rows.append({**base, "r_net": np.nan, "reason": sim.get("reason")})
            continue
        cost_r = cost_in_r(event.get(c["adr_pct"], np.nan), event.get(c["volume_ratio"], np.nan), sim["risk_pct"], cfg)
        rows.append(
            {
                **base,
                "entry": sim["entry"],
                "stop": sim["stop"],
                "target": sim["target"],
                "risk_pct": sim["risk_pct"],
                "outcome": sim["outcome"],
                "bars_held": sim["bars_held"],
                "r_gross": sim["r_gross"],
                "cost_R": cost_r,
                "r_net": sim["r_gross"] - cost_r,
            }
        )
    return pd.DataFrame(rows)


def setup_net_leaderboard(net_events: pd.DataFrame) -> pd.DataFrame:
    """Aggregate valid per-event net R into the setup leaderboard used for allocation."""
    if net_events is None or net_events.empty:
        return pd.DataFrame(columns=["trades", "net_expectancy_R", "net_pos_rate_pct", "net_median_R", "r_net_std"])
    valid = net_events.loc[net_events["valid"].astype(bool)].copy()
    if valid.empty:
        return pd.DataFrame(columns=["trades", "net_expectancy_R", "net_pos_rate_pct", "net_median_R", "r_net_std"])
    valid["r_net"] = pd.to_numeric(valid["r_net"], errors="coerce")
    grouped = valid.groupby("setup", dropna=False)["r_net"]
    out = pd.DataFrame(
        {
            "trades": grouped.size(),
            "net_expectancy_R": grouped.mean(),
            "net_pos_rate_pct": valid.assign(_positive=valid["r_net"] > 0).groupby("setup", dropna=False)["_positive"].mean().mul(100),
            "net_median_R": grouped.median(),
            "r_net_std": grouped.std(),
        }
    )
    return out.sort_values("net_expectancy_R", ascending=False)


def kelly_phi(r_net: Iterable[float]) -> float:
    """General-return Kelly fraction per R: ``E[r] / E[r^2]``."""
    values = np.asarray([float(x) for x in r_net if np.isfinite(float(x))], dtype=float)
    if values.size == 0:
        return 0.0
    second_moment = float(np.mean(values**2))
    if second_moment <= 0:
        return 0.0
    return max(0.0, float(np.mean(values)) / second_moment)


def effective_concurrency(n_open: int, rho: float) -> float:
    """Independent-bet equivalent for ``n_open`` correlated positions."""
    if n_open <= 0:
        return 0.0
    return float(n_open) / (1.0 + (float(n_open) - 1.0) * float(rho))


def risk_per_trade(n_open_after_add: int, phi: float, cfg: Config) -> float:
    """Capital-at-risk cap for one new position."""
    kelly_risk = cfg.kelly_fraction * max(0.0, float(phi))
    n_eff = effective_concurrency(n_open_after_add, cfg.factor_rho)
    heat_share = cfg.heat_cap / max(n_eff, 1.0)
    return min(kelly_risk, heat_share, cfg.per_name_risk_cap)


def select_daily_book(
    queue: pd.DataFrame,
    net_lb: pd.DataFrame,
    phi_by_setup: dict[str, float],
    cfg: Config,
) -> pd.DataFrame:
    """Select one risk-constrained daily book from the current signal queue."""
    c = cfg.queue_cols
    if queue is None or queue.empty or net_lb is None or net_lb.empty:
        return _empty_book()

    q = queue.copy()
    net_map = _net_expectancy_map(net_lb)
    q["net_expectancy_R"] = q[c["setup"]].map(net_map)
    q = q[pd.to_numeric(q["net_expectancy_R"], errors="coerce") > 0].copy()
    if q.empty:
        return _empty_book()

    turnover_col = c.get("turnover")
    if turnover_col and turnover_col in q.columns:
        q = q[pd.to_numeric(q[turnover_col], errors="coerce").fillna(0.0) >= cfg.min_turnover_inr].copy()
    if q.empty:
        return _empty_book()

    q = q.sort_values("net_expectancy_R", ascending=False).drop_duplicates(subset=[c["symbol"]], keep="first")
    q = q.sort_values("net_expectancy_R", ascending=False).reset_index(drop=True)

    book: list[dict[str, Any]] = []
    total_heat = 0.0
    sector_heat: dict[str, float] = {}
    for _, row in q.iterrows():
        if len(book) >= cfg.max_positions:
            break
        setup = str(row[c["setup"]])
        risk = risk_per_trade(len(book) + 1, phi_by_setup.get(setup, 0.0), cfg)
        if risk <= 0:
            continue
        sector = str(row.get(c["sector"], "UNKNOWN") or "UNKNOWN")
        if total_heat + risk > cfg.heat_cap:
            continue
        if sector_heat.get(sector, 0.0) + risk > cfg.sector_heat_cap:
            continue
        book.append(
            {
                "symbol": row[c["symbol"]],
                "sector": sector,
                "setup": setup,
                "net_expectancy_R": round(float(row["net_expectancy_R"]), 4),
                "risk_pct_of_capital": round(float(risk), 5),
                "close": row.get(c.get("close", "close")),
                "stop": row.get(c.get("stop", "stop")),
            }
        )
        total_heat += risk
        sector_heat[sector] = sector_heat.get(sector, 0.0) + risk

    out = pd.DataFrame(book, columns=BOOK_COLUMNS)
    out.attrs["total_heat"] = round(float(total_heat), 5)
    return out


def run(
    events_csv: str | Path,
    queue_csv: str | Path,
    eod_csv: str | Path | None,
    conn_str: str | None,
    cfg: Config,
    *,
    output_dir: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run fill correction, net edge recompute, and current-book selection."""
    engine = get_engine(conn_str)
    events = pd.read_csv(events_csv, parse_dates=[cfg.ev_cols["date"]], low_memory=False)
    queue = pd.read_csv(queue_csv, parse_dates=[cfg.queue_cols["date"]], low_memory=False)

    if engine is None:
        if not eod_csv:
            raise SystemExit("Need either --conn or --eod to re-simulate fills.")
        eod = pd.read_csv(eod_csv, parse_dates=[cfg.eod_cols["date"]])
        attach_eod_frame(eod)

    log.info("Re-simulating %d signal events with fill_model=%s", len(events), cfg.fill_model)
    net_events = recompute_net_edge(events, engine, cfg)
    net_lb = setup_net_leaderboard(net_events)
    phi_by_setup = {
        str(setup): kelly_phi(net_events.loc[net_events["setup"] == setup, "r_net"])
        for setup in net_lb.index
    }
    book = select_daily_book(queue, net_lb, phi_by_setup, cfg)
    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        net_events.to_csv(out_dir / "portfolio_construction_net_events.csv", index=False)
        net_lb.to_csv(out_dir / "portfolio_construction_net_leaderboard.csv")
        book.to_csv(out_dir / "portfolio_construction_daily_book.csv", index=False)
    return net_events, net_lb, book


def _net_expectancy_map(net_lb: pd.DataFrame) -> dict[str, float]:
    if "setup" in net_lb.columns and "net_expectancy_R" in net_lb.columns:
        return dict(zip(net_lb["setup"].astype(str), pd.to_numeric(net_lb["net_expectancy_R"], errors="coerce")))
    if "net_expectancy_R" in net_lb.columns:
        return pd.to_numeric(net_lb["net_expectancy_R"], errors="coerce").to_dict()
    if "net_expectancy_r" in net_lb.columns:
        return pd.to_numeric(net_lb["net_expectancy_r"], errors="coerce").to_dict()
    return {}


def _empty_book() -> pd.DataFrame:
    out = pd.DataFrame(columns=BOOK_COLUMNS)
    out.attrs["total_heat"] = 0.0
    return out


def _finite_float(value: Any, default: float = float("nan")) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    return out if np.isfinite(out) else default


def _cli() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, help="signal_events_*.csv")
    parser.add_argument("--queue", required=True, help="current_decision_queue_*.csv")
    parser.add_argument("--eod", help="equity_eod CSV for no-DB mode")
    parser.add_argument("--conn", help="SQLAlchemy PostgreSQL URL")
    parser.add_argument("--output-dir", default="reports/latest", help="Directory for generated portfolio-construction CSVs.")
    parser.add_argument("--fill-model", choices=["next_open", "limit_at_signal_close"], default="next_open")
    args = parser.parse_args()
    cfg = Config(fill_model=args.fill_model)
    _, net_lb, book = run(args.events, args.queue, args.eod, args.conn, cfg, output_dir=args.output_dir)
    log.info("Net-of-cost setup leaderboard:\n%s", net_lb.round(4).to_string())
    log.info("Selected book, total heat %.4f:\n%s", book.attrs.get("total_heat", 0.0), book.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
