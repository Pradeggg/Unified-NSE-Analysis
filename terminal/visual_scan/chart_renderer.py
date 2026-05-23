"""Annotated local chart rendering for visual scan reports."""

from __future__ import annotations

from html import escape
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

from .models import ChartAnnotation


def _safe_filename_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


def _prep(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])
    df = frame.copy()
    df.columns = [str(col).lower().strip() for col in df.columns]
    if "date" in df.columns and "trade_date" not in df.columns:
        df = df.rename(columns={"date": "trade_date"})
    if "trade_date" not in df.columns or "close" not in df.columns:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])

    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
    for column in ("open", "high", "low"):
        if column not in df.columns:
            df[column] = df["close"]
        else:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(df["close"])
    if "volume" not in df.columns:
        df["volume"] = 0
    else:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    return df


def _scale(value: float, minimum: float, maximum: float, size: float, invert: bool = False) -> float:
    if maximum == minimum:
        position = size / 2
    else:
        position = (float(value) - minimum) / (maximum - minimum) * size
    return size - position if invert else position


def _points(values: Iterable[float], minimum: float, maximum: float, width: int, height: int) -> str:
    vals = list(values)
    if not vals:
        return ""
    step = width / max(len(vals) - 1, 1)
    return " ".join(
        f"{idx * step:.2f},{_scale(value, minimum, maximum, height, invert=True):.2f}"
        for idx, value in enumerate(vals)
    )


def _sma_points(series: pd.Series, window: int, minimum: float, maximum: float, width: int, height: int) -> str:
    rolling = series.rolling(window).mean()
    step = width / max(len(series) - 1, 1)
    points = []
    for idx, value in enumerate(rolling):
        if pd.notna(value):
            points.append(f"{idx * step:.2f},{_scale(float(value), minimum, maximum, height, invert=True):.2f}")
    return " ".join(points)


def _render_svg(df: pd.DataFrame, annotations: list[ChartAnnotation]) -> str:
    if df.empty:
        return "<div class='empty-chart'>No usable OHLC data available.</div>"

    width = 1120
    price_height = 420
    volume_height = 110
    gap = 26
    total_height = price_height + volume_height + gap
    values = pd.concat([df["open"], df["high"], df["low"], df["close"]])
    min_price = float(values.min())
    max_price = float(values.max())
    prices = [annotation.price for annotation in annotations if annotation.price is not None]
    if prices:
        min_price = min(min_price, min(float(price) for price in prices))
        max_price = max(max_price, max(float(price) for price in prices))
    pad = max((max_price - min_price) * 0.08, max_price * 0.01, 1.0)
    min_price -= pad
    max_price += pad
    max_volume = float(df["volume"].max()) if float(df["volume"].max()) > 0 else 1.0
    step = width / max(len(df) - 1, 1)
    candle_width = max(3.0, min(10.0, step * 0.55))

    elements: list[str] = []
    for _, ratio in enumerate((0.0, 0.25, 0.5, 0.75, 1.0)):
        y = price_height * ratio
        price = max_price - (max_price - min_price) * ratio
        elements.append(f"<line class='grid' x1='0' x2='{width}' y1='{y:.2f}' y2='{y:.2f}' />")
        elements.append(f"<text class='axis' x='{width - 6}' y='{y + 14:.2f}'>{price:.2f}</text>")

    for idx, row in df.iterrows():
        x = idx * step
        open_y = _scale(row["open"], min_price, max_price, price_height, invert=True)
        high_y = _scale(row["high"], min_price, max_price, price_height, invert=True)
        low_y = _scale(row["low"], min_price, max_price, price_height, invert=True)
        close_y = _scale(row["close"], min_price, max_price, price_height, invert=True)
        color_class = "up" if row["close"] >= row["open"] else "down"
        body_top = min(open_y, close_y)
        body_height = max(abs(close_y - open_y), 1.0)
        elements.append(f"<line class='wick {color_class}' x1='{x:.2f}' x2='{x:.2f}' y1='{high_y:.2f}' y2='{low_y:.2f}' />")
        elements.append(
            f"<rect class='candle {color_class}' x='{x - candle_width / 2:.2f}' y='{body_top:.2f}' "
            f"width='{candle_width:.2f}' height='{body_height:.2f}' />"
        )
        vol_height = _scale(row["volume"], 0, max_volume, volume_height)
        elements.append(
            f"<rect class='volume' x='{x - candle_width / 2:.2f}' y='{price_height + gap + volume_height - vol_height:.2f}' "
            f"width='{candle_width:.2f}' height='{vol_height:.2f}' />"
        )

    close_points = _points(df["close"], min_price, max_price, width, price_height)
    elements.append(f"<polyline class='close-line' points='{close_points}' />")
    for window, class_name in ((20, "sma20"), (50, "sma50"), (200, "sma200")):
        if len(df) >= window:
            points = _sma_points(df["close"], window, min_price, max_price, width, price_height)
            elements.append(f"<polyline class='{class_name}' points='{points}' />")

    for annotation in annotations:
        if annotation.price is None:
            continue
        y = _scale(annotation.price, min_price, max_price, price_height, invert=True)
        label = escape(annotation.label)
        color = escape(annotation.color)
        elements.append(f"<line class='annotation' x1='0' x2='{width}' y1='{y:.2f}' y2='{y:.2f}' stroke='{color}' />")
        elements.append(f"<text class='annotation-label' x='10' y='{max(y - 8, 14):.2f}' fill='{color}'>{label}</text>")

    first_date = df["trade_date"].iloc[0].date().isoformat()
    last_date = df["trade_date"].iloc[-1].date().isoformat()
    elements.append(f"<text class='date-label' x='0' y='{total_height - 4}'>{first_date}</text>")
    elements.append(f"<text class='date-label end' x='{width}' y='{total_height - 4}'>{last_date}</text>")
    return f"<svg viewBox='0 0 {width} {total_height}' role='img'>{''.join(elements)}</svg>"


def _render_one(
    symbol: str,
    label: str,
    frame: pd.DataFrame,
    annotations: list[ChartAnnotation],
    path: Path,
) -> None:
    df = _prep(frame)
    latest = ""
    if not df.empty:
        latest = f"<p class='meta'>Latest close: {float(df['close'].iloc[-1]):.2f} | Bars: {len(df)}</p>"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(symbol)} Visual Scan - {escape(label)}</title>
  <style>
    body {{ margin: 0; background: #0f172a; color: #e2e8f0; font-family: Arial, sans-serif; }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; font-weight: 700; }}
    .meta {{ margin: 0 0 16px; color: #94a3b8; }}
    svg {{ width: 100%; height: auto; background: #111827; border: 1px solid #334155; }}
    .grid {{ stroke: #1f2937; stroke-width: 1; }}
    .axis, .date-label {{ fill: #94a3b8; font-size: 13px; }}
    .end {{ text-anchor: end; }}
    .wick {{ stroke-width: 1.4; }}
    .candle.up, .wick.up {{ fill: #14b8a6; stroke: #14b8a6; }}
    .candle.down, .wick.down {{ fill: #f43f5e; stroke: #f43f5e; }}
    .volume {{ fill: #475569; opacity: 0.65; }}
    .close-line, .sma20, .sma50, .sma200 {{ fill: none; stroke-width: 2; }}
    .close-line {{ stroke: #e2e8f0; opacity: 0.75; }}
    .sma20 {{ stroke: #38bdf8; }}
    .sma50 {{ stroke: #22c55e; }}
    .sma200 {{ stroke: #f97316; }}
    .annotation {{ stroke-width: 1.5; stroke-dasharray: 6 5; }}
    .annotation-label {{ font-size: 14px; font-weight: 700; }}
    .empty-chart {{ min-height: 360px; display: grid; place-items: center; background: #111827; border: 1px solid #334155; color: #94a3b8; }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(symbol)} Visual Scan - {escape(label)}</h1>
    {latest}
    {_render_svg(df, annotations)}
  </main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def render_visual_scan_charts(
    *,
    symbol: str,
    run_id: str,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    annotations: list[ChartAnnotation],
    output_dir: str | Path,
) -> dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    safe_symbol = _safe_filename_part(str(symbol).strip().upper(), "SYMBOL")
    safe_run_id = _safe_filename_part(run_id, "run")
    daily_path = target / f"{safe_symbol}_{safe_run_id}_daily.html"
    weekly_path = target / f"{safe_symbol}_{safe_run_id}_weekly.html"
    _render_one(safe_symbol, "Daily", daily, annotations, daily_path)
    _render_one(safe_symbol, "Weekly", weekly, annotations, weekly_path)
    return {"daily": str(daily_path), "weekly": str(weekly_path)}
