#!/usr/bin/env python3
"""Market breadth indicators derived from local NSE OHLCV history."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
STOCK_DATA_CSV = ROOT / "data" / "nse_sec_full_data.csv"
BREADTH_HISTORY_CSV = ROOT / "data" / "breadth_history.csv"
INDEX_MAPPING_CSV = ROOT / "data" / "index_stock_mapping.csv"
SECTOR_BREADTH_CSV = ROOT / "data" / "sector_breadth.csv"

# Sector indices to track in C3 — maps index symbol (uppercase) → display name
SECTOR_BREADTH_INDICES: dict[str, str] = {
    "NIFTY AUTO":       "Auto",
    "NIFTY BANK":       "Banking",
    "NIFTY FMCG":       "FMCG",
    "NIFTY IT":         "IT",
    "NIFTY METAL":      "Metal",
    "NIFTY PHARMA":     "Pharma",
    "NIFTY REALTY":     "Realty",
    "NIFTY ENERGY":     "Energy",
    "NIFTY INFRA":      "Infrastructure",
    "NIFTY MIDCAP 150": "Midcap",
}


def _date_column(df: pd.DataFrame) -> str:
    if "DATE" in df.columns:
        return "DATE"
    if "TIMESTAMP" in df.columns:
        return "TIMESTAMP"
    raise KeyError("Expected DATE or TIMESTAMP column for breadth calculation")


def get_advance_decline_series(universe_df: pd.DataFrame) -> pd.Series:
    """Compute daily net advance/decline from stock rows.

    A stock is an advancer when ``CLOSE > PREVCLOSE``. If ``PREVCLOSE`` is
    missing, the prior close per symbol is used.
    """
    required = {"SYMBOL", "CLOSE"}
    missing = required - set(universe_df.columns)
    if missing:
        raise KeyError(f"Missing required columns: {', '.join(sorted(missing))}")

    date_col = _date_column(universe_df)
    daily = universe_df.copy()
    daily["DATE"] = pd.to_datetime(daily[date_col], errors="coerce")
    daily["CLOSE"] = pd.to_numeric(daily["CLOSE"], errors="coerce")
    daily = daily.dropna(subset=["DATE", "SYMBOL", "CLOSE"]).sort_values(["SYMBOL", "DATE"])

    if "PREVCLOSE" in daily.columns:
        daily["PREV"] = pd.to_numeric(daily["PREVCLOSE"], errors="coerce")
    else:
        daily["PREV"] = pd.NA
    daily["PREV"] = daily["PREV"].fillna(daily.groupby("SYMBOL")["CLOSE"].shift(1))
    daily = daily.dropna(subset=["PREV"])

    daily["ADV"] = daily["CLOSE"] > daily["PREV"]
    grouped = daily.groupby("DATE")["ADV"].agg(
        advances="sum",
        total="count",
    )
    grouped["declines"] = grouped["total"] - grouped["advances"]
    net_ad = (grouped["advances"] - grouped["declines"]).astype(int).rename("net_ad")
    return net_ad.sort_index()


def compute_mcclellan(net_advance_decline: pd.Series) -> pd.DataFrame:
    """Compute McClellan Oscillator, Summation Index, and signal labels."""
    net_ad = pd.to_numeric(net_advance_decline, errors="coerce").dropna().sort_index()
    ema19 = net_ad.ewm(span=19, adjust=False).mean()
    ema39 = net_ad.ewm(span=39, adjust=False).mean()
    oscillator = ema19 - ema39
    summation = oscillator.cumsum()

    signal = pd.Series("NEUTRAL", index=oscillator.index, dtype="object")
    signal.loc[oscillator > 70] = "OVERBOUGHT"
    signal.loc[oscillator < -70] = "OVERSOLD"
    signal.loc[(oscillator > 0) & (oscillator.shift(1) <= 0)] = "BULLISH_CROSS"
    signal.loc[(oscillator < 0) & (oscillator.shift(1) >= 0)] = "BEARISH_CROSS"

    return pd.DataFrame(
        {
            "oscillator": oscillator.round(1),
            "summation": summation.round(0),
            "signal": signal,
        }
    )


def _prepared_daily_stock_frame(universe_df: pd.DataFrame) -> pd.DataFrame:
    required = {"SYMBOL", "CLOSE"}
    missing = required - set(universe_df.columns)
    if missing:
        raise KeyError(f"Missing required columns: {', '.join(sorted(missing))}")

    date_col = _date_column(universe_df)
    daily = universe_df.copy()
    daily["DATE"] = pd.to_datetime(daily[date_col], errors="coerce")
    daily["CLOSE"] = pd.to_numeric(daily["CLOSE"], errors="coerce")
    daily = daily.dropna(subset=["DATE", "SYMBOL", "CLOSE"]).sort_values(["SYMBOL", "DATE"])

    if "PREVCLOSE" in daily.columns:
        daily["PREV"] = pd.to_numeric(daily["PREVCLOSE"], errors="coerce")
    else:
        daily["PREV"] = pd.NA
    daily["PREV"] = daily["PREV"].fillna(daily.groupby("SYMBOL")["CLOSE"].shift(1))
    daily = daily.dropna(subset=["PREV"])
    daily["ADV"] = daily["CLOSE"] > daily["PREV"]
    return daily


def _trin_signal(value: float) -> str:
    if pd.isna(value):
        return "NO_DATA"
    if value < 0.5:
        return "VERY_BULLISH"
    if value < 0.8:
        return "BULLISH"
    if value < 1.2:
        return "NEUTRAL"
    if value < 2.0:
        return "BEARISH"
    return "PANIC"


def _trin_5d_signal(value: float) -> str:
    if pd.isna(value):
        return "NO_DATA"
    if value < 0.75:
        return "INTERNALLY_STRONG"
    if value > 1.40:
        return "INTERNALLY_WEAK"
    return "NEUTRAL"


def compute_trin(universe_df: pd.DataFrame) -> pd.DataFrame:
    """Compute TRIN / Arms Index from daily advance/decline volume breadth."""
    daily = _prepared_daily_stock_frame(universe_df)
    volume_col = "TOTTRDQTY" if "TOTTRDQTY" in daily.columns else "VOLUME" if "VOLUME" in daily.columns else None
    if volume_col is None:
        raise KeyError("Expected TOTTRDQTY or VOLUME column for TRIN calculation")
    daily["VOLUME"] = pd.to_numeric(daily[volume_col], errors="coerce").fillna(0)

    rows = []
    for date, group in daily.groupby("DATE"):
        advances = int(group["ADV"].sum())
        declines = int((~group["ADV"]).sum())
        adv_volume = float(group.loc[group["ADV"], "VOLUME"].sum())
        dec_volume = float(group.loc[~group["ADV"], "VOLUME"].sum())
        ad_ratio = advances / max(declines, 1)
        volume_ratio = adv_volume / max(dec_volume, 1.0)
        trin = ad_ratio / volume_ratio if volume_ratio else pd.NA
        rows.append(
            {
                "DATE": date,
                "advances": advances,
                "declines": declines,
                "adv_volume": round(adv_volume, 0),
                "dec_volume": round(dec_volume, 0),
                "trin": round(float(trin), 2) if not pd.isna(trin) else pd.NA,
            }
        )

    out = pd.DataFrame(rows).set_index("DATE").sort_index()
    out["trin_5d"] = out["trin"].rolling(5, min_periods=1).mean().round(2)
    out["trin_signal"] = out["trin"].apply(_trin_signal)
    out["trin_5d_signal"] = out["trin_5d"].apply(_trin_5d_signal)
    return out


def detect_mcclellan_divergence(price_series: pd.Series, oscillator: pd.Series, lookback: int = 60) -> str:
    """Detect simple price/oscillator divergence over a recent lookback window."""
    price = pd.to_numeric(price_series, errors="coerce").dropna().sort_index().tail(lookback)
    osc = pd.to_numeric(oscillator, errors="coerce").dropna().sort_index().tail(lookback)
    common_index = price.index.intersection(osc.index)
    price = price.loc[common_index]
    osc = osc.loc[common_index]
    if len(price) < 5:
        return "NONE"

    midpoint = max(2, len(price) // 2)
    first_price_low = price.iloc[:midpoint].min()
    second_price_low = price.iloc[midpoint:].min()
    first_osc_low = osc.iloc[:midpoint].min()
    second_osc_low = osc.iloc[midpoint:].min()
    if second_price_low < first_price_low and second_osc_low > first_osc_low:
        return "BULLISH_DIVERGENCE"

    first_price_high = price.iloc[:midpoint].max()
    second_price_high = price.iloc[midpoint:].max()
    first_osc_high = osc.iloc[:midpoint].max()
    second_osc_high = osc.iloc[midpoint:].max()
    if second_price_high > first_price_high and second_osc_high < first_osc_high:
        return "BEARISH_DIVERGENCE"

    return "NONE"


def _nifty500_close_series(index_data: pd.DataFrame) -> pd.Series:
    symbol = index_data["SYMBOL"].astype(str).str.upper()
    mask = symbol.isin(["NIFTY 500", "NIFTY500"])
    if not mask.any():
        return pd.Series(dtype=float, name="nifty500_close")
    part = index_data[mask].copy()
    part["DATE"] = pd.to_datetime(part["TIMESTAMP"], errors="coerce")
    part["CLOSE"] = pd.to_numeric(part["CLOSE"], errors="coerce")
    return part.dropna(subset=["DATE", "CLOSE"]).set_index("DATE")["CLOSE"].sort_index().rename("nifty500_close")


def build_breadth_history(stock_data: pd.DataFrame, index_data: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build daily breadth history with McClellan columns."""
    net_ad = get_advance_decline_series(stock_data)
    mcclellan = compute_mcclellan(net_ad)
    trin = compute_trin(stock_data)
    history = pd.DataFrame({"net_ad": net_ad}).join(mcclellan, how="inner").join(trin, how="left")
    history["divergence"] = "NONE"

    if index_data is not None and not index_data.empty:
        price = _nifty500_close_series(index_data)
        if not price.empty:
            history["nifty500_close"] = price.reindex(history.index).ffill()
            for idx_pos, idx in enumerate(history.index):
                start = max(0, idx_pos - 59)
                window = history.iloc[start : idx_pos + 1]
                history.at[idx, "divergence"] = detect_mcclellan_divergence(
                    window["nifty500_close"],
                    window["oscillator"],
                    lookback=60,
                )

    history = history.reset_index().rename(columns={"DATE": "date", "index": "date"})
    if "date" not in history.columns:
        history = history.rename(columns={history.columns[0]: "date"})
    history["date"] = pd.to_datetime(history["date"]).dt.strftime("%Y-%m-%d")
    history["generated_at"] = datetime.now().isoformat(timespec="seconds")
    return history


def generate_breadth_history(
    stock_csv: Path = STOCK_DATA_CSV,
    index_csv: Path = ROOT / "data" / "nse_index_data.csv",
    output_csv: Path = BREADTH_HISTORY_CSV,
    lookback_days: int = 420,
) -> pd.DataFrame:
    """Load local NSE data, compute breadth history, persist to CSV, and return it."""
    usecols = ["SYMBOL", "TIMESTAMP", "CLOSE", "PREVCLOSE", "TOTTRDQTY"]
    stock_data = pd.read_csv(stock_csv, usecols=lambda col: col in usecols)
    stock_data["TIMESTAMP"] = pd.to_datetime(stock_data["TIMESTAMP"], errors="coerce")
    max_date = stock_data["TIMESTAMP"].max()
    if pd.notna(max_date) and lookback_days:
        stock_data = stock_data[stock_data["TIMESTAMP"] >= max_date - pd.Timedelta(days=lookback_days)]

    index_data = pd.DataFrame()
    if index_csv.exists():
        index_data = pd.read_csv(index_csv, usecols=lambda col: col in {"SYMBOL", "TIMESTAMP", "CLOSE"})
        index_data["TIMESTAMP"] = pd.to_datetime(index_data["TIMESTAMP"], errors="coerce")
        if pd.notna(max_date) and lookback_days:
            index_data = index_data[index_data["TIMESTAMP"] >= max_date - pd.Timedelta(days=lookback_days)]

    history = build_breadth_history(stock_data, index_data)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(output_csv, index=False)
    return history


def load_breadth_history(path: Path = BREADTH_HISTORY_CSV) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def mcclellan_context_html(history: pd.DataFrame) -> str:
    """Compact McClellan strip for the sector rotation report header."""
    if history is None or history.empty:
        return ""
    latest = history.iloc[-1]
    try:
        oscillator = float(latest.get("oscillator", 0) or 0)
    except (TypeError, ValueError):
        oscillator = 0.0
    signal = str(latest.get("signal", "NEUTRAL") or "NEUTRAL")
    divergence = str(latest.get("divergence", "NONE") or "NONE")
    trin_signal = str(latest.get("trin_signal", "") or "")
    net_ad = latest.get("net_ad", "")
    date = str(latest.get("date", ""))
    try:
        trin = float(latest.get("trin", 0) or 0)
    except (TypeError, ValueError):
        trin = 0.0

    if signal in {"OVERBOUGHT", "BULLISH_CROSS"} or trin_signal in {"VERY_BULLISH", "BULLISH"}:
        tone = "positive"
    elif signal in {"OVERSOLD", "BEARISH_CROSS"} or trin_signal in {"BEARISH", "PANIC"}:
        tone = "caution"
    else:
        tone = "neutral"
    if divergence != "NONE":
        tone = "positive" if divergence == "BULLISH_DIVERGENCE" else "caution"

    bg, fg = {
        "positive": ("#ecfdf5", "#047857"),
        "caution": ("#fef2f2", "#b91c1c"),
        "neutral": ("#f8fafc", "#475569"),
    }[tone]

    div_html = "" if divergence == "NONE" else f'<span>{html.escape(divergence.replace("_", " "))}</span>'
    return (
        f'<div class="breadth-strip" style="background:{bg};color:{fg};border-color:rgba(0,0,0,.08)">'
        f'<span class="breadth-kicker" style="color:{fg}">McClellan</span>'
        f'<span class="breadth-context" style="color:{fg}">{html.escape(signal)}</span>'
        f'<span>Osc {oscillator:+.1f}</span>'
        f'<span>TRIN {trin:.2f} {html.escape(trin_signal.replace("_", " "))}</span>'
        f'<span>Net A/D {html.escape(str(net_ad))}</span>'
        f'{div_html}'
        f'<span>{html.escape(date)}</span>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# C3 — Sector Breadth Divergence
# ---------------------------------------------------------------------------

def _load_index_constituents(mapping_csv: Path = INDEX_MAPPING_CSV) -> dict[str, list[str]]:
    """Load symbol → index mapping CSV and return {INDEX_NAME_UPPER: [symbols]}."""
    if not mapping_csv.exists():
        return {}
    df = pd.read_csv(mapping_csv)
    df["INDEX_NAME"] = df["INDEX_NAME"].astype(str).str.strip().str.upper()
    df["STOCK_SYMBOL"] = df["STOCK_SYMBOL"].astype(str).str.strip().str.upper()
    result: dict[str, list[str]] = {}
    for index_name, grp in df.groupby("INDEX_NAME"):
        syms = [s for s in grp["STOCK_SYMBOL"].tolist() if s and s != "NAN"]
        if syms:
            result[index_name] = sorted(set(syms))
    return result


def compute_sector_breadth(
    stock_metrics: pd.DataFrame,
    constituents: dict[str, list[str]],
    sector_indices: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Compute pct_above_50dma and pct_above_200dma for each tracked sector index.

    Args:
        stock_metrics: per-symbol DataFrame with columns SYMBOL, CLOSE, SMA_50, SMA_200.
        constituents:  {INDEX_NAME_UPPER: [SYMBOL, ...]} from index_stock_mapping.csv.
        sector_indices: override for SECTOR_BREADTH_INDICES; defaults to module constant.

    Returns:
        DataFrame with one row per sector: sector, index_name, constituent_count,
        pct_above_50dma, pct_above_200dma, breadth_signal.
    """
    tracked = {k.upper(): v for k, v in (sector_indices or SECTOR_BREADTH_INDICES).items()}
    normed_consts = {k.upper(): v for k, v in constituents.items()}

    metrics = stock_metrics.copy()
    metrics["SYMBOL"] = metrics["SYMBOL"].astype(str).str.strip().str.upper()
    for col in ("CLOSE", "SMA_50", "SMA_200"):
        if col in metrics.columns:
            metrics[col] = pd.to_numeric(metrics[col], errors="coerce")
    metrics = metrics.drop_duplicates("SYMBOL").set_index("SYMBOL")

    rows = []
    for index_key, sector_name in tracked.items():
        symbols = normed_consts.get(index_key, [])
        # Try common capitalisation variants if exact key missing
        if not symbols:
            for k, v in normed_consts.items():
                if k.replace(" ", "").replace("-", "") == index_key.replace(" ", "").replace("-", ""):
                    symbols = v
                    break
        available = [s for s in symbols if s in metrics.index]
        if not available:
            rows.append({
                "sector": sector_name,
                "index_name": index_key,
                "constituent_count": 0,
                "pct_above_50dma": float("nan"),
                "pct_above_200dma": float("nan"),
                "breadth_signal": "NO_DATA",
            })
            continue
        sub = metrics.loc[available]
        n = len(sub)
        pct50 = float((sub["CLOSE"] > sub["SMA_50"]).mean() * 100) if "SMA_50" in sub.columns else float("nan")
        pct200 = float((sub["CLOSE"] > sub["SMA_200"]).mean() * 100) if "SMA_200" in sub.columns else float("nan")
        if pd.isna(pct50):
            sig = "NO_DATA"
        elif pct50 > 60:
            sig = "HEALTHY"
        elif pct50 >= 40:
            sig = "NEUTRAL"
        else:
            sig = "WEAK"
        rows.append({
            "sector": sector_name,
            "index_name": index_key,
            "constituent_count": n,
            "pct_above_50dma": round(pct50, 1) if not pd.isna(pct50) else float("nan"),
            "pct_above_200dma": round(pct200, 1) if not pd.isna(pct200) else float("nan"),
            "breadth_signal": sig,
        })
    return pd.DataFrame(rows)


def sector_breadth_divergence(
    stock_data: pd.DataFrame,
    index_data: pd.DataFrame | None = None,
    constituents: dict[str, list[str]] | None = None,
    lookback_days: int = 5,
    sector_indices: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Build a daily sector breadth snapshot and detect divergences.

    For each tracked sector index, computes pct_above_50dma and pct_above_200dma
    per trading date, then emits divergence alerts comparing current vs 5 days ago:

    - BULLISH_DIV : sector index price at new low BUT pct_above_50dma is higher
                    (few weak stocks, index dragged by a couple of large-caps)
    - BEARISH_DIV : sector index price at new high BUT pct_above_50dma is falling
                    (distribution — breadth deteriorating despite headline strength)
    - INT_WEAKNESS: pct_above_50dma fell > 10pp over lookback_days while index flat
                    (index held up by a handful of heavyweight constituents)
    - NONE        : no notable divergence

    Returns a DataFrame with the latest date's per-sector row enriched with
    divergence_alert and change_5d (pct_above_50dma change over lookback window).
    """
    tracked = sector_indices or SECTOR_BREADTH_INDICES
    if constituents is None:
        constituents = _load_index_constituents()

    # Build per-day stock metrics
    df = stock_data.copy()
    date_col = "TIMESTAMP" if "TIMESTAMP" in df.columns else "DATE"
    df["DATE"] = pd.to_datetime(df[date_col], errors="coerce")
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    df = df.dropna(subset=["DATE", "SYMBOL", "CLOSE"]).sort_values(["SYMBOL", "DATE"])
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip().str.upper()
    df["SMA_50"] = df.groupby("SYMBOL")["CLOSE"].transform(lambda x: x.rolling(50, min_periods=50).mean())
    df["SMA_200"] = df.groupby("SYMBOL")["CLOSE"].transform(lambda x: x.rolling(200, min_periods=200).mean())

    # Build sector index close series for divergence detection
    sector_index_closes: dict[str, pd.Series] = {}
    if index_data is not None and not index_data.empty:
        idx = index_data.copy()
        idx_date = "TIMESTAMP" if "TIMESTAMP" in idx.columns else "DATE"
        idx["DATE"] = pd.to_datetime(idx[idx_date], errors="coerce")
        idx["CLOSE"] = pd.to_numeric(idx["CLOSE"], errors="coerce")
        idx["SYMBOL"] = idx["SYMBOL"].astype(str).str.strip().str.upper()
        idx = idx.dropna(subset=["DATE", "SYMBOL", "CLOSE"])
        for ix_key in tracked:
            sub = idx[idx["SYMBOL"].str.upper() == ix_key.upper()]
            if not sub.empty:
                sector_index_closes[ix_key.upper()] = sub.set_index("DATE")["CLOSE"].sort_index()

    trading_dates = sorted(df["DATE"].unique())
    normed_consts = {k.upper(): v for k, v in constituents.items()}

    history_rows: list[dict] = []
    for date in trading_dates:
        day_df = df[df["DATE"] == date]
        day_df = day_df.drop_duplicates("SYMBOL").set_index("SYMBOL")
        for ix_key, sector_name in tracked.items():
            syms = normed_consts.get(ix_key.upper(), [])
            available = [s for s in syms if s in day_df.index]
            if not available:
                continue
            sub = day_df.loc[available]
            pct50 = float((sub["CLOSE"] > sub["SMA_50"]).mean() * 100) if "SMA_50" in sub.columns else float("nan")
            history_rows.append({
                "date": date,
                "sector": sector_name,
                "index_name": ix_key.upper(),
                "pct_above_50dma": round(pct50, 1) if not pd.isna(pct50) else float("nan"),
            })

    if not history_rows:
        return pd.DataFrame()

    hist = pd.DataFrame(history_rows)
    hist["date"] = pd.to_datetime(hist["date"])

    # For each sector, compute 5-day change and divergence alert on the latest date
    rows = []
    for ix_key, sector_name in tracked.items():
        sector_hist = hist[hist["index_name"] == ix_key.upper()].sort_values("date")
        if sector_hist.empty:
            continue
        latest = sector_hist.iloc[-1]
        prev_row = sector_hist.iloc[-lookback_days - 1] if len(sector_hist) > lookback_days else sector_hist.iloc[0]
        pct50_now = float(latest["pct_above_50dma"]) if not pd.isna(latest["pct_above_50dma"]) else float("nan")
        pct50_prev = float(prev_row["pct_above_50dma"]) if not pd.isna(prev_row["pct_above_50dma"]) else float("nan")
        change_5d = round(pct50_now - pct50_prev, 1) if not (pd.isna(pct50_now) or pd.isna(pct50_prev)) else float("nan")

        # Divergence: compare sector index price vs breadth
        divergence_alert = "NONE"
        ix_closes = sector_index_closes.get(ix_key.upper())
        if ix_closes is not None and not ix_closes.empty and not pd.isna(pct50_now) and not pd.isna(pct50_prev):
            price_window = ix_closes.tail(lookback_days + 1)
            if len(price_window) >= 2:
                price_now = float(price_window.iloc[-1])
                price_prev = float(price_window.iloc[0])
                price_change_pct = (price_now / price_prev - 1) * 100 if price_prev > 0 else 0.0
                if price_change_pct < -1.5 and change_5d > 3:
                    divergence_alert = "BULLISH_DIV"
                elif price_change_pct > 1.5 and change_5d < -5:
                    divergence_alert = "BEARISH_DIV"
                elif abs(price_change_pct) <= 1.5 and change_5d < -10:
                    divergence_alert = "INT_WEAKNESS"

        breadth_sig = (
            "HEALTHY" if not pd.isna(pct50_now) and pct50_now > 60
            else "NEUTRAL" if not pd.isna(pct50_now) and pct50_now >= 40
            else "WEAK" if not pd.isna(pct50_now)
            else "NO_DATA"
        )
        rows.append({
            "sector": sector_name,
            "index_name": ix_key.upper(),
            "pct_above_50dma": pct50_now,
            "change_5d": change_5d,
            "breadth_signal": breadth_sig,
            "divergence_alert": divergence_alert,
            "as_of_date": str(latest["date"].date()),
        })
    return pd.DataFrame(rows).sort_values("pct_above_50dma", ascending=False).reset_index(drop=True)


def generate_sector_breadth(
    stock_csv: Path = STOCK_DATA_CSV,
    index_csv: Path = ROOT / "data" / "nse_index_data.csv",
    mapping_csv: Path = INDEX_MAPPING_CSV,
    output_csv: Path = SECTOR_BREADTH_CSV,
    lookback_days: int = 5,
    history_window: int = 300,
) -> pd.DataFrame:
    """Load data, compute sector breadth divergence, persist to CSV, and return result."""
    usecols_stock = ["SYMBOL", "TIMESTAMP", "CLOSE", "PREVCLOSE"]
    stock_data = pd.read_csv(stock_csv, usecols=lambda c: c in usecols_stock)
    stock_data["TIMESTAMP"] = pd.to_datetime(stock_data["TIMESTAMP"], errors="coerce")
    max_date = stock_data["TIMESTAMP"].max()
    if pd.notna(max_date) and history_window:
        stock_data = stock_data[stock_data["TIMESTAMP"] >= max_date - pd.Timedelta(days=history_window)]

    index_data = pd.DataFrame()
    if index_csv.exists():
        index_data = pd.read_csv(index_csv, usecols=lambda c: c in {"SYMBOL", "TIMESTAMP", "CLOSE"})
        index_data["TIMESTAMP"] = pd.to_datetime(index_data["TIMESTAMP"], errors="coerce")
        if pd.notna(max_date) and history_window:
            index_data = index_data[index_data["TIMESTAMP"] >= max_date - pd.Timedelta(days=history_window)]

    constituents = _load_index_constituents(mapping_csv)
    result = sector_breadth_divergence(stock_data, index_data, constituents, lookback_days=lookback_days)
    if not result.empty:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_csv, index=False)
    return result


def load_sector_breadth(path: Path = SECTOR_BREADTH_CSV) -> pd.DataFrame:
    """Load the latest sector breadth snapshot from CSV."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


if __name__ == "__main__":
    result = generate_breadth_history()
    latest = result.iloc[-1].to_dict() if not result.empty else {}
    print(f"Wrote {len(result)} breadth rows to {BREADTH_HISTORY_CSV}")
    if latest:
        print(
            "Latest McClellan: "
            f"{latest.get('oscillator'):+.1f} {latest.get('signal')} "
            f"({latest.get('divergence')})"
        )
