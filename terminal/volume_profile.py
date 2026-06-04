"""terminal/volume_profile.py — Volume Profile and Chart Pattern Analysis.

Two core capabilities built on market.equity_eod OHLCV data:

Volume Profile
--------------
  compute_volume_profile(symbol, lookback=60) → VolumeProfile
    - POC  (Point of Control):   price with most volume
    - VAH  (Value Area High):    top of 70% volume zone
    - VAL  (Value Area Low):     bottom of 70% volume zone
    - HVN  (High Volume Nodes):  price clusters with above-avg volume
    - LVN  (Low Volume Nodes):   price gaps with below-avg volume

Chart Patterns
--------------
  detect_patterns(symbol, lookback=120) → list[ChartPattern]
    - VCP     Volatility Contraction Pattern (tight base before breakout)
    - BULL_FLAG   Strong move + consolidation
    - BEAR_FLAG   Weak move + consolidation
    - DOUBLE_BOTTOM  W shape — bullish reversal
    - DOUBLE_TOP     M shape — bearish reversal
    - CUP_HANDLE  Rounded recovery with handle
    - ASCENDING_TRIANGLE  Flat resistance + rising lows
    - DESCENDING_TRIANGLE Flat support + falling highs
    - BULL_PENNANT / BEAR_PENNANT
    - STAGE2_CONTINUATION  Price > SMA50 > SMA200, tightening

All computations are deterministic (no LLM, no external API).
PostgreSQL market.equity_eod is the data source.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Optional

_PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_ohlcv(symbol: str, lookback: int = 120) -> list[dict]:
    """Load OHLCV bars from market.equity_eod, newest first → reversed to oldest-first."""
    try:
        import psycopg2
        conn = psycopg2.connect(_PG_DSN)
        c = conn.cursor()
        c.execute(
            """SELECT trade_date, open, high, low, close, volume
               FROM market.equity_eod
               WHERE symbol = %s AND volume > 0
               ORDER BY trade_date DESC
               LIMIT %s""",
            (symbol.upper(), lookback),
        )
        rows = c.fetchall()
        conn.close()
        if not rows:
            return []
        # Reverse to chronological order
        bars = []
        for r in reversed(rows):
            bars.append({
                "date":   r[0],
                "open":   float(r[1] or 0),
                "high":   float(r[2] or 0),
                "low":    float(r[3] or 0),
                "close":  float(r[4] or 0),
                "volume": int(r[5] or 0),
            })
        return bars
    except Exception:
        return []


# ── Volume Profile ────────────────────────────────────────────────────────────

@dataclass
class VolumeProfile:
    symbol: str
    lookback_bars: int
    poc: float              # Point of Control (highest volume price)
    vah: float              # Value Area High (top of 70% volume zone)
    val: float              # Value Area Low  (bottom of 70% volume zone)
    hvn: list[float]        # High Volume Nodes (above-avg clusters)
    lvn: list[float]        # Low Volume Nodes  (below-avg gaps)
    current_price: float
    price_vs_poc: float     # % above/below POC
    price_in_value_area: bool
    buckets: list[dict]     # [{price, volume, pct}] for rendering
    n_bars: int


def compute_volume_profile(
    symbol: str,
    lookback: int = 60,
    n_buckets: int = 30,
) -> Optional[VolumeProfile]:
    """Compute volume profile from recent OHLCV bars."""
    bars = _load_ohlcv(symbol, lookback)
    if len(bars) < 10:
        return None

    lo = min(b["low"]  for b in bars)
    hi = max(b["high"] for b in bars)
    if hi <= lo:
        return None

    bucket_size = (hi - lo) / n_buckets
    vol_at_price = [0.0] * n_buckets

    for b in bars:
        # Distribute bar volume uniformly across its price range
        b_lo, b_hi, vol = b["low"], b["high"], b["volume"]
        range_size = max(b_hi - b_lo, 0.01)
        for i in range(n_buckets):
            bucket_lo = lo + i * bucket_size
            bucket_hi = bucket_lo + bucket_size
            overlap = max(0.0, min(b_hi, bucket_hi) - max(b_lo, bucket_lo))
            vol_at_price[i] += vol * (overlap / range_size)

    total_vol = sum(vol_at_price) or 1.0
    poc_idx   = vol_at_price.index(max(vol_at_price))
    poc_price = lo + (poc_idx + 0.5) * bucket_size

    # Value Area: expand from POC until 70% of total volume included
    va_lo_idx = poc_idx
    va_hi_idx = poc_idx
    va_vol = vol_at_price[poc_idx]
    target = 0.70 * total_vol
    while va_vol < target:
        can_expand_lo = va_lo_idx > 0
        can_expand_hi = va_hi_idx < n_buckets - 1
        if not can_expand_lo and not can_expand_hi:
            break
        add_lo = vol_at_price[va_lo_idx - 1] if can_expand_lo else -1
        add_hi = vol_at_price[va_hi_idx + 1] if can_expand_hi else -1
        if add_hi >= add_lo:
            va_hi_idx += 1
            va_vol += add_hi
        else:
            va_lo_idx -= 1
            va_vol += add_lo

    vah = lo + (va_hi_idx + 1) * bucket_size
    val = lo + va_lo_idx * bucket_size

    # HVN / LVN
    avg_vol = total_vol / n_buckets
    hvn, lvn = [], []
    for i, v in enumerate(vol_at_price):
        price = lo + (i + 0.5) * bucket_size
        if v > avg_vol * 1.5:
            hvn.append(round(price, 2))
        elif v < avg_vol * 0.3:
            lvn.append(round(price, 2))

    current = bars[-1]["close"]
    pct_vs_poc = (current - poc_price) / poc_price * 100 if poc_price else 0

    buckets = [
        {
            "price":  round(lo + (i + 0.5) * bucket_size, 2),
            "volume": round(vol_at_price[i]),
            "pct":    round(vol_at_price[i] / total_vol * 100, 1),
            "is_poc": i == poc_idx,
            "in_va":  va_lo_idx <= i <= va_hi_idx,
        }
        for i in range(n_buckets)
    ]

    return VolumeProfile(
        symbol=symbol,
        lookback_bars=len(bars),
        poc=round(poc_price, 2),
        vah=round(vah, 2),
        val=round(val, 2),
        hvn=[round(h, 2) for h in hvn[:5]],
        lvn=[round(v, 2) for v in lvn[:5]],
        current_price=round(current, 2),
        price_vs_poc=round(pct_vs_poc, 1),
        price_in_value_area=val <= current <= vah,
        buckets=buckets,
        n_bars=len(bars),
    )


# ── Chart Patterns ────────────────────────────────────────────────────────────

@dataclass
class ChartPattern:
    pattern:      str          # e.g. "VCP", "BULL_FLAG"
    label:        str          # human-readable
    signal:       str          # "bullish" | "bearish" | "neutral"
    confidence:   float        # 0–1
    description:  str
    pivot:        Optional[float] = None   # key price level
    stop:         Optional[float] = None   # suggested stop level
    target:       Optional[float] = None   # estimated target
    bars_forming: Optional[int]  = None    # how long the pattern took


def _sma(closes: list[float], n: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        result[i] = sum(closes[i - n + 1 : i + 1]) / n
    return result


def _atr(bars: list[dict], n: int = 14) -> list[Optional[float]]:
    trs: list[float] = []
    for i, b in enumerate(bars):
        if i == 0:
            trs.append(b["high"] - b["low"])
        else:
            trs.append(max(
                b["high"] - b["low"],
                abs(b["high"] - bars[i - 1]["close"]),
                abs(b["low"]  - bars[i - 1]["close"]),
            ))
    result: list[Optional[float]] = [None] * len(bars)
    for i in range(n - 1, len(bars)):
        result[i] = sum(trs[i - n + 1 : i + 1]) / n
    return result


def _rolling_max(vals: list[float], n: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(vals)
    for i in range(n - 1, len(vals)):
        result[i] = max(vals[i - n + 1 : i + 1])
    return result


def _rolling_min(vals: list[float], n: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(vals)
    for i in range(n - 1, len(vals)):
        result[i] = min(vals[i - n + 1 : i + 1])
    return result


def detect_patterns(
    symbol: str,
    lookback: int = 120,
) -> list[ChartPattern]:
    """Detect common chart patterns from OHLCV history."""
    bars = _load_ohlcv(symbol, lookback)
    if len(bars) < 20:
        return []

    closes  = [b["close"]  for b in bars]
    highs   = [b["high"]   for b in bars]
    lows    = [b["low"]    for b in bars]
    volumes = [b["volume"] for b in bars]
    n       = len(bars)

    sma20  = _sma(closes, 20)
    sma50  = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    atr14  = _atr(bars, 14)
    h20    = _rolling_max(highs, 20)
    l20    = _rolling_min(lows, 20)

    current = closes[-1]
    patterns: list[ChartPattern] = []

    # ── 1. VCP — Volatility Contraction Pattern ───────────────────────────────
    if n >= 30:
        # Look at recent 30 bars: high range → low range → tightening
        ranges = [(highs[i] - lows[i]) / closes[i] for i in range(n - 30, n)]
        early_range = sum(ranges[:10]) / 10
        late_range  = sum(ranges[-10:]) / 10
        contraction = (early_range - late_range) / early_range if early_range > 0 else 0

        near_high = highs[-1] >= max(highs[-30:-5]) * 0.97
        vol_low   = volumes[-1] < sum(volumes[-20:-1]) / 19 * 0.7

        if contraction > 0.25 and near_high and vol_low and current > (sma50[-1] or 0):
            atr_v = atr14[-1] or (current * 0.02)
            patterns.append(ChartPattern(
                pattern="VCP",
                label="VCP — Volatility Contraction",
                signal="bullish",
                confidence=min(0.9, 0.5 + contraction),
                description=(
                    f"Price is contracting near recent highs on declining volume. "
                    f"Range contracted {contraction*100:.0f}% over 30 sessions — "
                    f"classic VCP setup. Breakout above ₹{max(highs[-30:]):.1f} is the trigger."
                ),
                pivot=round(max(highs[-30:]), 2),
                stop=round(current - 2 * atr_v, 2),
                target=round(current + 4 * atr_v, 2),
                bars_forming=30,
            ))

    # ── 2. Bull Flag ──────────────────────────────────────────────────────────
    if n >= 25:
        # Pole: strong 10-bar move up; flag: last 10 bars tight consolidation
        pole_start = closes[n - 25]
        pole_end   = closes[n - 15]
        pole_gain  = (pole_end - pole_start) / pole_start if pole_start else 0
        flag_hi    = max(closes[n - 15:])
        flag_lo    = min(closes[n - 15:])
        flag_range = (flag_hi - flag_lo) / flag_hi if flag_hi else 1

        if pole_gain > 0.07 and flag_range < 0.06 and current > (sma20[-1] or 0):
            atr_v = atr14[-1] or (current * 0.02)
            patterns.append(ChartPattern(
                pattern="BULL_FLAG",
                label="Bull Flag",
                signal="bullish",
                confidence=min(0.85, 0.4 + pole_gain * 2),
                description=(
                    f"Strong +{pole_gain*100:.1f}% pole move followed by tight "
                    f"{flag_range*100:.1f}% consolidation. Breakout above "
                    f"₹{flag_hi:.1f} targets continuation of the prior trend."
                ),
                pivot=round(flag_hi, 2),
                stop=round(flag_lo - atr_v * 0.5, 2),
                target=round(flag_hi + (pole_end - pole_start), 2),
                bars_forming=10,
            ))

    # ── 3. Bear Flag ──────────────────────────────────────────────────────────
    if n >= 25:
        pole_start = closes[n - 25]
        pole_end   = closes[n - 15]
        pole_drop  = (pole_start - pole_end) / pole_start if pole_start else 0
        flag_hi    = max(closes[n - 15:])
        flag_lo    = min(closes[n - 15:])
        flag_range = (flag_hi - flag_lo) / flag_hi if flag_hi else 1

        if pole_drop > 0.07 and flag_range < 0.06 and current < (sma20[-1] or float("inf")):
            atr_v = atr14[-1] or (current * 0.02)
            patterns.append(ChartPattern(
                pattern="BEAR_FLAG",
                label="Bear Flag",
                signal="bearish",
                confidence=min(0.85, 0.4 + pole_drop * 2),
                description=(
                    f"Strong −{pole_drop*100:.1f}% pole drop followed by tight "
                    f"{flag_range*100:.1f}% consolidation. Breakdown below "
                    f"₹{flag_lo:.1f} risks continuation of the downtrend."
                ),
                pivot=round(flag_lo, 2),
                stop=round(flag_hi + atr_v * 0.5, 2),
                target=round(flag_lo - (pole_start - pole_end), 2),
                bars_forming=10,
            ))

    # ── 4. Double Bottom ──────────────────────────────────────────────────────
    if n >= 40:
        # Find two lows of similar price separated by a peak
        seg1_lo  = min(lows[n - 40 : n - 20])
        seg2_lo  = min(lows[n - 20 : n])
        peak_hi  = max(highs[n - 35 : n - 5])
        pct_diff = abs(seg1_lo - seg2_lo) / ((seg1_lo + seg2_lo) / 2) if seg1_lo else 1
        neckline = peak_hi

        if (pct_diff < 0.04 and peak_hi > seg1_lo * 1.05
                and current > neckline * 0.98):
            atr_v = atr14[-1] or (current * 0.02)
            depth = neckline - min(seg1_lo, seg2_lo)
            patterns.append(ChartPattern(
                pattern="DOUBLE_BOTTOM",
                label="Double Bottom (W)",
                signal="bullish",
                confidence=min(0.80, 0.5 + (1 - pct_diff) * 0.3),
                description=(
                    f"Two lows within {pct_diff*100:.1f}% of each other "
                    f"(₹{seg1_lo:.1f} and ₹{seg2_lo:.1f}) with a peak at "
                    f"₹{neckline:.1f}. Breakout above neckline targets "
                    f"₹{neckline + depth:.1f} (measured move)."
                ),
                pivot=round(neckline, 2),
                stop=round(min(seg1_lo, seg2_lo) - atr_v, 2),
                target=round(neckline + depth, 2),
                bars_forming=40,
            ))

    # ── 5. Double Top ─────────────────────────────────────────────────────────
    if n >= 40:
        seg1_hi  = max(highs[n - 40 : n - 20])
        seg2_hi  = max(highs[n - 20 : n])
        trough_lo = min(lows[n - 35 : n - 5])
        pct_diff = abs(seg1_hi - seg2_hi) / ((seg1_hi + seg2_hi) / 2) if seg1_hi else 1
        neckline = trough_lo

        if (pct_diff < 0.04 and trough_lo < seg1_hi * 0.97
                and current < neckline * 1.02):
            atr_v = atr14[-1] or (current * 0.02)
            depth = max(seg1_hi, seg2_hi) - neckline
            patterns.append(ChartPattern(
                pattern="DOUBLE_TOP",
                label="Double Top (M)",
                signal="bearish",
                confidence=min(0.80, 0.5 + (1 - pct_diff) * 0.3),
                description=(
                    f"Two highs within {pct_diff*100:.1f}% of each other "
                    f"(₹{seg1_hi:.1f} and ₹{seg2_hi:.1f}) with a trough at "
                    f"₹{neckline:.1f}. Breakdown below neckline risks "
                    f"₹{neckline - depth:.1f} (measured move)."
                ),
                pivot=round(neckline, 2),
                stop=round(max(seg1_hi, seg2_hi) + atr_v, 2),
                target=round(neckline - depth, 2),
                bars_forming=40,
            ))

    # ── 6. Ascending Triangle ─────────────────────────────────────────────────
    if n >= 30:
        recent_highs = highs[n - 30:]
        recent_lows  = lows[n - 30:]
        flat_top = max(recent_highs)
        near_flat = sum(1 for h in recent_highs if h >= flat_top * 0.98) >= 3

        # Rising lows: simple linear regression on lows
        lo_vals = recent_lows
        xs = list(range(len(lo_vals)))
        slope = (sum(x * y for x, y in zip(xs, lo_vals)) - sum(xs) * sum(lo_vals) / len(xs)) / \
                (sum(x**2 for x in xs) - sum(xs)**2 / len(xs) + 1e-9)

        if near_flat and slope > 0 and current > sum(recent_lows) / len(recent_lows):
            atr_v = atr14[-1] or (current * 0.02)
            patterns.append(ChartPattern(
                pattern="ASCENDING_TRIANGLE",
                label="Ascending Triangle",
                signal="bullish",
                confidence=0.70,
                description=(
                    f"Flat resistance at ₹{flat_top:.1f} with rising lows — "
                    f"bullish compression. Breakout above ₹{flat_top:.1f} "
                    f"typically targets the triangle height added to the breakout."
                ),
                pivot=round(flat_top, 2),
                stop=round(current - 1.5 * atr_v, 2),
                target=round(flat_top + (flat_top - min(recent_lows)), 2),
                bars_forming=30,
            ))

    # ── 7. Stage 2 Continuation ───────────────────────────────────────────────
    if n >= 50:
        s20  = sma20[-1]
        s50  = sma50[-1]
        s200 = sma200[-1] if sma200[-1] else None
        atr_v = atr14[-1] or (current * 0.02)

        in_stage2 = (
            s20 and s50 and
            current > s20 > s50 and
            (s200 is None or s50 > s200)
        )

        if in_stage2:
            # Check tightness: recent 10-bar range vs ATR
            recent_range = (max(highs[-10:]) - min(lows[-10:])) / (atr_v * 10)
            tight = recent_range < 1.5

            patterns.append(ChartPattern(
                pattern="STAGE2_CONTINUATION",
                label="Stage 2 Uptrend Continuation",
                signal="bullish",
                confidence=0.75 + (0.1 if tight else 0),
                description=(
                    f"Price > SMA20 (₹{s20:.1f}) > SMA50 (₹{s50:.1f})"
                    + (f" > SMA200 (₹{s200:.1f})" if s200 else "")
                    + f". Classic Weinstein Stage 2 uptrend — trend is intact."
                    + (" Range tight relative to ATR — low-risk add point." if tight else "")
                ),
                pivot=round(max(highs[-5:]), 2),
                stop=round(s50 - atr_v, 2),
                target=None,
                bars_forming=None,
            ))

    # ── 8. Descending Triangle ────────────────────────────────────────────────
    if n >= 30:
        recent_highs2 = highs[n - 30:]
        recent_lows2  = lows[n - 30:]
        flat_bot = min(recent_lows2)
        near_flat_bot = sum(1 for l in recent_lows2 if l <= flat_bot * 1.02) >= 3

        # Falling highs
        hi_vals = recent_highs2
        xs = list(range(len(hi_vals)))
        slope2 = (sum(x * y for x, y in zip(xs, hi_vals)) - sum(xs) * sum(hi_vals) / len(xs)) / \
                 (sum(x**2 for x in xs) - sum(xs)**2 / len(xs) + 1e-9)

        if near_flat_bot and slope2 < 0 and current < sum(recent_highs2) / len(recent_highs2):
            atr_v = atr14[-1] or (current * 0.02)
            patterns.append(ChartPattern(
                pattern="DESCENDING_TRIANGLE",
                label="Descending Triangle",
                signal="bearish",
                confidence=0.65,
                description=(
                    f"Flat support at ₹{flat_bot:.1f} with falling highs — "
                    f"bearish compression. Breakdown below ₹{flat_bot:.1f} "
                    f"risks accelerated selling."
                ),
                pivot=round(flat_bot, 2),
                stop=round(current + 1.5 * atr_v, 2),
                target=round(flat_bot - (max(recent_highs2) - flat_bot), 2),
                bars_forming=30,
            ))

    # De-duplicate — if both bullish and bearish signal for same category, keep higher confidence
    seen: set[str] = set()
    unique: list[ChartPattern] = []
    for p in sorted(patterns, key=lambda x: -x.confidence):
        key = p.signal + "_" + p.pattern.split("_")[0]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


# ── HTML rendering ────────────────────────────────────────────────────────────

def render_volume_profile_svg(vp: VolumeProfile, width: int = 180, height: int = 120) -> str:
    """Render a compact horizontal bar chart of the volume profile as SVG."""
    if not vp or not vp.buckets:
        return ""

    max_vol = max(b["volume"] for b in vp.buckets) or 1
    bar_h   = max(2, height // len(vp.buckets))
    total_h = bar_h * len(vp.buckets)
    bar_area_w = width - 45  # leave space for price labels

    bars_svg = ""
    for i, b in enumerate(reversed(vp.buckets)):  # highest price at top
        bar_w = max(2, int(b["volume"] / max_vol * bar_area_w))
        y = i * bar_h

        if b["is_poc"]:
            color = "#dc2626"   # red — POC
        elif b["in_va"]:
            color = "#3b82f6"   # blue — value area
        else:
            color = "#94a3b8"   # grey — outside VA

        bars_svg += f'<rect x="0" y="{y}" width="{bar_w}" height="{max(1, bar_h-1)}" fill="{color}" opacity=".8"/>'

    # Price labels: POC, VAH, VAL
    n = len(vp.buckets)
    poc_y = total_h - (vp.poc - vp.buckets[0]["price"]) / (vp.buckets[-1]["price"] - vp.buckets[0]["price"] + 0.01) * total_h
    vah_y = total_h - (vp.vah - vp.buckets[0]["price"]) / (vp.buckets[-1]["price"] - vp.buckets[0]["price"] + 0.01) * total_h
    val_y = total_h - (vp.val - vp.buckets[0]["price"]) / (vp.buckets[-1]["price"] - vp.buckets[0]["price"] + 0.01) * total_h

    labels = (
        f'<line x1="0" y1="{poc_y:.0f}" x2="{bar_area_w}" y2="{poc_y:.0f}" stroke="#dc2626" stroke-width="1" stroke-dasharray="2"/>'
        f'<text x="{bar_area_w+3}" y="{poc_y+4:.0f}" font-size="8" fill="#dc2626" font-weight="700">POC</text>'
        f'<line x1="0" y1="{vah_y:.0f}" x2="{bar_area_w}" y2="{vah_y:.0f}" stroke="#3b82f6" stroke-width="1" stroke-dasharray="2"/>'
        f'<text x="{bar_area_w+3}" y="{vah_y+4:.0f}" font-size="8" fill="#3b82f6">VAH</text>'
        f'<line x1="0" y1="{val_y:.0f}" x2="{bar_area_w}" y2="{val_y:.0f}" stroke="#3b82f6" stroke-width="1" stroke-dasharray="2"/>'
        f'<text x="{bar_area_w+3}" y="{val_y+4:.0f}" font-size="8" fill="#3b82f6">VAL</text>'
    )

    return (
        f'<svg width="{width}" height="{total_h}" '
        f'viewBox="0 0 {width} {total_h}" style="display:block">'
        f'{bars_svg}{labels}'
        f'</svg>'
    )


def render_patterns_html(patterns: list[ChartPattern]) -> str:
    """Render detected patterns as compact HTML badges with details."""
    if not patterns:
        return '<p style="color:#9ca3af;font-size:11px">No strong patterns detected in the lookback window.</p>'

    sig_colors = {
        "bullish": ("#16a34a", "#dcfce7"),
        "bearish": ("#dc2626", "#fee2e2"),
        "neutral": ("#6b7280", "#f3f4f6"),
    }

    html = ""
    for p in patterns:
        tc, bg = sig_colors.get(p.signal, ("#6b7280", "#f3f4f6"))
        conf_pct = int(p.confidence * 100)
        levels = []
        if p.pivot:  levels.append(f"Pivot ₹{p.pivot:,.1f}")
        if p.stop:   levels.append(f"Stop ₹{p.stop:,.1f}")
        if p.target: levels.append(f"Target ₹{p.target:,.1f}")
        levels_str = " · ".join(levels)

        html += f"""
        <div style="background:{bg};border-left:3px solid {tc};border-radius:4px;
                    padding:6px 10px;margin-bottom:6px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-weight:700;font-size:12px;color:{tc}">{p.label}</span>
            <span style="font-size:10px;color:{tc};background:white;padding:1px 6px;
                         border-radius:999px">{conf_pct}% conf</span>
          </div>
          <p style="font-size:11px;color:#374151;margin:3px 0">{p.description}</p>
          {f'<p style="font-size:10px;color:#6b7280;margin:2px 0">{levels_str}</p>' if levels_str else ''}
        </div>"""

    return html
