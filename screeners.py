"""
screeners.py  —  A1: William O'Neil Stage Analysis Screener
============================================================
Classifies every stock into one of four stages based on price/MA structure,
then builds a ranked Stage 2 (Markup) screener table for the HTML report.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------
STAGE_LABELS = {
    "STAGE_1": "Stage 1 — Base",
    "STAGE_2": "Stage 2 — Markup",
    "STAGE_3": "Stage 3 — Top",
    "STAGE_4": "Stage 4 — Decline",
    "UNKNOWN": "Unknown",
}

STAGE_BADGE_CSS = {
    "STAGE_2": ("s2-badge", "S2 ✅"),
    "STAGE_1": ("s1-badge", "S1"),
    "STAGE_3": ("s3-badge", "S3 ⚠"),
    "STAGE_4": ("s4-badge", "S4 ❌"),
    "UNKNOWN": ("su-badge", "—"),
}

# Score deltas applied to INVESTMENT_SCORE in rank_stock_candidates()
STAGE_SCORE_DELTA = {
    "STAGE_2": +4,
    "STAGE_1": 0,
    "STAGE_3": -5,
    "STAGE_4": -8,
    "UNKNOWN": 0,
}


# ---------------------------------------------------------------------------
# Per-symbol feature computation
# ---------------------------------------------------------------------------

def _compute_stage_features(hist: pd.DataFrame) -> dict:
    """
    Compute stage classification and supporting metrics for a single symbol.
    hist: sorted (ascending) OHLCV DataFrame for one symbol.
    Returns a dict of scalar values.
    """
    defaults = {
        "STAGE": "UNKNOWN",
        "SMA_50": None, "SMA_200": None,
        "SMA_50_SLOPE": None, "SMA_200_SLOPE": None,
        "DIST_FROM_52W_HIGH_PCT": None,
        "VOL_RATIO": None,
    }
    if len(hist) < 50:
        return defaults

    close = hist["CLOSE"].astype(float)
    hi = hist["HIGH"].astype(float) if "HIGH" in hist.columns else close
    lo = hist["LOW"].astype(float) if "LOW" in hist.columns else close
    vol = hist["TOTTRDQTY"].astype(float) if "TOTTRDQTY" in hist.columns else pd.Series(
        1.0, index=hist.index
    )

    sma50 = close.rolling(50, min_periods=40).mean()
    sma200 = close.rolling(200, min_periods=150).mean()
    sma50_slope = sma50.pct_change(10).fillna(0)
    sma200_slope = sma200.pct_change(10).fillna(0)

    hi_52w = close.rolling(252, min_periods=50).max()
    dist_52w_high = ((close / hi_52w.replace(0, np.nan)) - 1) * 100

    vol_20d = vol.rolling(20, min_periods=10).mean()
    vol_200d = vol.rolling(200, min_periods=60).mean()
    vol_ratio = (vol_20d / vol_200d.replace(0, np.nan)).fillna(1.0)

    atr = (hi - lo).rolling(14, min_periods=7).mean()
    atr_3m = (hi - lo).rolling(60, min_periods=30).mean()
    atr_expanding = (atr / atr_3m.replace(0, np.nan)).fillna(1.0)

    c = float(close.iloc[-1])
    s50 = float(sma50.iloc[-1]) if not math.isnan(float(sma50.iloc[-1])) else None
    s200 = float(sma200.iloc[-1]) if not math.isnan(float(sma200.iloc[-1])) else None
    s50_sl = float(sma50_slope.iloc[-1])
    s200_sl = float(sma200_slope.iloc[-1])
    d52 = float(dist_52w_high.iloc[-1]) if not math.isnan(float(dist_52w_high.iloc[-1])) else -99.0
    vr = float(vol_ratio.iloc[-1])
    atr_exp = float(atr_expanding.iloc[-1])

    if s200 is None:
        stage = "UNKNOWN"
    elif c > (s50 or 0) and (s50 or 0) > s200 and s50_sl > 0.001 and s200_sl > 0.0005 and d52 > -20:
        stage = "STAGE_2"
    elif c < (s50 or 0) and (s50 or 0) < s200 and s200_sl < -0.001:
        stage = "STAGE_4"
    elif c > s200 and s50_sl < 0.001 and atr_exp > 1.2:
        stage = "STAGE_3"
    else:
        stage = "STAGE_1"

    return {
        "STAGE": stage,
        "SMA_50": round(s50, 2) if s50 is not None else None,
        "SMA_200": round(s200, 2) if s200 is not None else None,
        "SMA_50_SLOPE": round(s50_sl * 100, 4),
        "SMA_200_SLOPE": round(s200_sl * 100, 4),
        "DIST_FROM_52W_HIGH_PCT": round(d52, 2),
        "VOL_RATIO": round(vr, 2),
    }


# ---------------------------------------------------------------------------
# Enrichment: add stage columns to candidates DataFrame
# ---------------------------------------------------------------------------

def enrich_with_stage(
    candidates: pd.DataFrame,
    history: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """
    Adds STAGE, SMA_50, SMA_200, SMA_50_SLOPE, SMA_200_SLOPE,
    DIST_FROM_52W_HIGH_PCT, VOL_RATIO to every row in candidates.
    history: long-form OHLCV DataFrame (SYMBOL, TIMESTAMP, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY).
    """
    df = candidates.copy()
    stage_cols = ["STAGE", "SMA_50", "SMA_200", "SMA_50_SLOPE",
                  "SMA_200_SLOPE", "DIST_FROM_52W_HIGH_PCT", "VOL_RATIO"]
    for col in stage_cols:
        df[col] = "UNKNOWN" if col == "STAGE" else None

    if history is None or history.empty:
        return df

    hist_all = history.copy()
    hist_all["TIMESTAMP"] = pd.to_datetime(hist_all["TIMESTAMP"])

    for sym in df["SYMBOL"].dropna().unique():
        sym_hist = hist_all[hist_all["SYMBOL"] == sym].sort_values("TIMESTAMP")
        features = _compute_stage_features(sym_hist)
        mask = df["SYMBOL"] == sym
        for k, v in features.items():
            df.loc[mask, k] = v

    return df


# ---------------------------------------------------------------------------
# Screener: ranked Stage 2 table
# ---------------------------------------------------------------------------

def run_stage_screener(
    candidates: pd.DataFrame,
    history: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Run the A1 stage screener. If candidates already has a STAGE column
    (from enrich_with_stage), it reuses it; otherwise computes it.
    Returns a full DataFrame with all stages, scored and sorted.
    """
    if "STAGE" not in candidates.columns or (candidates["STAGE"] == "UNKNOWN").all():
        df = enrich_with_stage(candidates, history)
    else:
        df = candidates.copy()

    # RS percentile rank
    if "RELATIVE_STRENGTH" in df.columns:
        rs = pd.to_numeric(df["RELATIVE_STRENGTH"], errors="coerce")
        df["RS_RANK_PCT"] = rs.rank(pct=True).fillna(0.5)
    else:
        df["RS_RANK_PCT"] = 0.5

    # Stage score (meaningful only for Stage 2, but computed for all)
    dist = pd.to_numeric(df.get("DIST_FROM_52W_HIGH_PCT", pd.Series([-30] * len(df))),
                         errors="coerce").fillna(-30)
    vr = pd.to_numeric(df.get("VOL_RATIO", pd.Series([1.0] * len(df))),
                       errors="coerce").fillna(1.0).clip(0.5, 3.0)

    stage2_mask = df["STAGE"] == "STAGE_2"
    df["STAGE_SCORE"] = 0.0
    if stage2_mask.any():
        df.loc[stage2_mask, "STAGE_SCORE"] = (
            df.loc[stage2_mask, "RS_RANK_PCT"] * 0.40
            + (1 - dist[stage2_mask].abs() / 20).clip(0, 1) * 0.30
            + (vr[stage2_mask] / 3.0) * 0.30
        )

    # Sort: Stage 2 first (by score desc), then 1, 3, 4, Unknown
    stage_order = {"STAGE_2": 0, "STAGE_1": 1, "STAGE_3": 2, "STAGE_4": 3, "UNKNOWN": 4}
    df["_stage_sort"] = df["STAGE"].map(stage_order).fillna(4)
    df = df.sort_values(["_stage_sort", "STAGE_SCORE"], ascending=[True, False])
    df = df.drop(columns=["_stage_sort"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# HTML rendering helpers
# ---------------------------------------------------------------------------

def stage_badge_html(stage: str) -> str:
    css_cls, label = STAGE_BADGE_CSS.get(stage, ("su-badge", stage))
    return f'<span class="stage-badge {css_cls}">{label}</span>'


STAGE_CSS = """
/* ---- A1 STAGE ANALYSIS BADGES ---- */
.stage-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;white-space:nowrap}
.s2-badge{background:#dcfce7;color:#166534;border:1px solid #86efac}
.s1-badge{background:#fef9c3;color:#854d0e;border:1px solid #fde047}
.s3-badge{background:#ffedd5;color:#c2410c;border:1px solid #fdba74}
.s4-badge{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.su-badge{background:#f1f5f9;color:#94a3b8}
/* Stage screener tab */
.stage-summary{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.stage-card{padding:12px 16px;border-radius:8px;min-width:110px;text-align:center}
.stage-card .sc-count{font-size:24px;font-weight:800}
.stage-card .sc-label{font-size:11px;font-weight:600;margin-top:2px}
.stage-card.s2{background:#dcfce7;color:#166534}.stage-card.s1{background:#fef9c3;color:#854d0e}
.stage-card.s3{background:#ffedd5;color:#c2410c}.stage-card.s4{background:#fee2e2;color:#991b1b}
.stage-card.su{background:#f1f5f9;color:#64748b}
"""


def build_stage_screener_tab_html(
    screener_df: pd.DataFrame,
    import_html: object = None,
) -> str:
    """Build the full Stage Screener tab HTML."""
    try:
        import html as html_mod
    except ImportError:
        import html as html_mod

    if screener_df is None or screener_df.empty:
        return '<div class="card"><p>No stage data available — run with stock history cache.</p></div>'

    counts = screener_df["STAGE"].value_counts()
    n2 = int(counts.get("STAGE_2", 0))
    n1 = int(counts.get("STAGE_1", 0))
    n3 = int(counts.get("STAGE_3", 0))
    n4 = int(counts.get("STAGE_4", 0))
    nu = int(counts.get("UNKNOWN", 0))

    summary_html = (
        f'<div class="stage-summary">'
        f'<div class="stage-card s2"><div class="sc-count">{n2}</div><div class="sc-label">Stage 2 — BUY ZONE</div></div>'
        f'<div class="stage-card s1"><div class="sc-count">{n1}</div><div class="sc-label">Stage 1 — Basing</div></div>'
        f'<div class="stage-card s3"><div class="sc-count">{n3}</div><div class="sc-label">Stage 3 — Distribution</div></div>'
        f'<div class="stage-card s4"><div class="sc-count">{n4}</div><div class="sc-label">Stage 4 — Decline</div></div>'
        f'<div class="stage-card su"><div class="sc-count">{nu}</div><div class="sc-label">Insufficient Data</div></div>'
        f'</div>'
    )

    # Filter chips
    chip_html = (
        '<div class="idx-filter-bar" style="margin-bottom:10px">'
        '<button class="idx-chip active" data-stagecat="All">All</button>'
        '<button class="idx-chip" data-stagecat="STAGE_2">Stage 2 ✅</button>'
        '<button class="idx-chip" data-stagecat="STAGE_1">Stage 1</button>'
        '<button class="idx-chip" data-stagecat="STAGE_3">Stage 3 ⚠</button>'
        '<button class="idx-chip" data-stagecat="STAGE_4">Stage 4 ❌</button>'
        '<input type="text" id="stageSearch" class="idx-search" placeholder="Search symbol…" autocomplete="off">'
        '<span id="stageCount" style="font-size:11px;color:#64748b;margin-left:4px">'
        f'{len(screener_df)} stocks'
        '</span>'
        '</div>'
    )

    def _rc(val):
        try:
            v = float(val)
        except (TypeError, ValueError):
            return '<span class="ret-neu">—</span>'
        if math.isnan(v):
            return '<span class="ret-neu">—</span>'
        cls = "ret-pos" if v > 0 else ("ret-neg" if v < 0 else "ret-neu")
        return f'<span class="{cls}">{v:+.1f}%</span>'

    def _fmt(val, digits=2, suffix=""):
        try:
            v = float(val)
            if math.isnan(v):
                return "—"
            return f"{v:.{digits}f}{suffix}"
        except (TypeError, ValueError):
            return "—"

    rows_html = ""
    for _, row in screener_df.iterrows():
        sym = str(row.get("SYMBOL", ""))
        stage = str(row.get("STAGE", "UNKNOWN"))
        badge = stage_badge_html(stage)
        co = html_mod.escape(str(row.get("COMPANY_NAME", sym))[:30])
        sec = html_mod.escape(str(row.get("SECTOR_NAME", "")))
        price = _fmt(row.get("CLOSE"), digits=2)
        sma50 = _fmt(row.get("SMA_50"), digits=2)
        sma200 = _fmt(row.get("SMA_200"), digits=2)
        sl50 = _rc(row.get("SMA_50_SLOPE"))
        sl200 = _rc(row.get("SMA_200_SLOPE"))
        d52 = _rc(row.get("DIST_FROM_52W_HIGH_PCT"))
        vr_raw = row.get("VOL_RATIO")
        try:
            vr_v = float(vr_raw)
            vr_cls = "ret-pos" if vr_v > 1.2 else ("ret-neg" if vr_v < 0.8 else "ret-neu")
            vr_html = f'<span class="{vr_cls}">{vr_v:.2f}×</span>'
        except (TypeError, ValueError):
            vr_html = '<span class="ret-neu">—</span>'
        rs_pct = _fmt(row.get("RS_RANK_PCT"), digits=0, suffix="%") if row.get("RS_RANK_PCT") not in (None, "") else "—"
        try:
            rs_v = float(row.get("RS_RANK_PCT", 0) or 0) * 100
            rs_cls = "ret-pos" if rs_v >= 70 else ("ret-neg" if rs_v < 30 else "ret-neu")
            rs_pct = f'<span class="{rs_cls}">{rs_v:.0f}th</span>'
        except (TypeError, ValueError):
            rs_pct = '<span class="ret-neu">—</span>'
        inv = _fmt(row.get("INVESTMENT_SCORE"), digits=1)
        stg_sc = _fmt(row.get("STAGE_SCORE"), digits=3) if stage == "STAGE_2" else "—"

        rows_html += (
            f'<tr data-stagecat="{html_mod.escape(stage)}" data-stagesym="{html_mod.escape(sym.lower())}">'
            f'<td><strong>{html_mod.escape(sym)}</strong></td>'
            f'<td style="font-size:10px;color:#64748b">{co}</td>'
            f'<td style="font-size:10px;color:#64748b">{sec}</td>'
            f'<td>{badge}</td>'
            f'<td class="num" data-val="{price}">₹{price}</td>'
            f'<td class="num" data-val="{sma50}">{sma50}</td>'
            f'<td class="num" data-val="{sma200}">{sma200}</td>'
            f'<td class="num">{sl50}</td>'
            f'<td class="num">{sl200}</td>'
            f'<td class="num">{d52}</td>'
            f'<td class="num">{vr_html}</td>'
            f'<td class="num">{rs_pct}</td>'
            f'<td class="num" data-val="{inv}">{inv}</td>'
            f'<td class="num" data-val="{stg_sc if stage == "STAGE_2" else -1}">{stg_sc}</td>'
            f'</tr>'
        )

    table_html = (
        f'<div class="tbl-wrap"><table>'
        f'<thead><tr>'
        f'<th>Symbol</th><th>Company</th><th>Sector</th><th>Stage</th>'
        f'<th class="num">Price</th><th class="num">SMA 50</th><th class="num">SMA 200</th>'
        f'<th class="num">50D Slope</th><th class="num">200D Slope</th>'
        f'<th class="num">Dist 52W Hi</th><th class="num">Vol Ratio</th>'
        f'<th class="num">RS Pctile</th><th class="num">Inv Score</th><th class="num">Stage Score</th>'
        f'</tr></thead>'
        f'<tbody id="stageTbody">{rows_html}</tbody>'
        f'</table></div>'
    )

    stage_js = """
<script>
(function(){
  var chips=document.querySelectorAll('[data-stagecat]');
  var si=document.getElementById('stageSearch');
  function filterStage(){
    var ac='';
    chips.forEach(function(c){if(c.classList&&c.classList.contains('active'))ac=c.dataset.stagecat;});
    var q=si?si.value.toLowerCase().trim():'';
    var vis=0;
    document.querySelectorAll('#stageTbody tr').forEach(function(r){
      var cm=(ac==='All'||r.dataset.stagecat===ac);
      var sm=(!q||r.dataset.stagesym.indexOf(q)>=0);
      r.style.display=(cm&&sm)?'':'none';
      if(cm&&sm)vis++;
    });
    var el=document.getElementById('stageCount');
    if(el)el.textContent=vis+' stocks';
  }
  chips.forEach(function(c){
    if(!c.dataset||!c.dataset.stagecat)return;
    c.addEventListener('click',function(){
      chips.forEach(function(x){if(x.classList)x.classList.remove('active');});
      c.classList.add('active');
      filterStage();
    });
  });
  if(si)si.addEventListener('input',filterStage);
})();
</script>"""

    methodology_note = (
        '<div class="card" style="margin-top:16px;font-size:12px;color:#475569">'
        '<strong>Stage Definitions (O\'Neil / Weinstein):</strong>'
        '<ul style="margin:6px 0 0 16px;line-height:1.7">'
        '<li><strong>Stage 2 — Markup (BUY ZONE):</strong> Price &gt; SMA50 &gt; SMA200, '
        'both MAs rising, within 20% of 52W high. Positive RS percentile.</li>'
        '<li><strong>Stage 1 — Base:</strong> Price near 200 DMA, MAs flat/declining. Accumulation phase.</li>'
        '<li><strong>Stage 3 — Distribution:</strong> Near highs but SMA50 flattening, '
        'ATR expanding. Avoid.</li>'
        '<li><strong>Stage 4 — Decline:</strong> Price &lt; SMA50 &lt; SMA200, MAs falling. '
        'Shorting territory.</li>'
        '</ul>'
        '<p style="margin:8px 0 0">Stage 2 stocks receive a <strong>+4</strong> investment score bonus; '
        'Stage 3 = −5, Stage 4 = −8. Only buy Stage 2.</p>'
        '</div>'
    )

    return (
        f'<div class="sec-title">Stage Analysis Screener</div>'
        f'<div class="sec-sub">William O\'Neil / Stan Weinstein 4-stage price cycle classification. '
        f'Only Stage 2 (Markup) stocks are in the buy zone.</div>'
        + summary_html
        + chip_html
        + table_html
        + stage_js
        + methodology_note
    )


# ---------------------------------------------------------------------------
# A3: 52-Week High Momentum Screener
# ---------------------------------------------------------------------------

def momentum_52w_high_screener(candidates: pd.DataFrame) -> pd.DataFrame:
    """A3: Select stocks within 5% of 52W high with strong RS, volume, and trend.

    Selection criteria:
    - Price within 0–5% below 52W high
    - SMA_50 slope positive (uptrend)
    - RS rank percentile ≥ 75th
    - Volume ratio ≥ 1.0 (volume not contracting)
    - RSI between 50 and 80

    Score: rs_pct×0.35 + proximity×0.30 + vol_ratio×0.20 + rsi_norm×0.15
    """
    df = candidates.copy()

    def _col(primary: str, fallback: str | None, default: float) -> pd.Series:
        if primary in df.columns:
            return pd.to_numeric(df[primary], errors="coerce").fillna(default)
        if fallback and fallback in df.columns:
            return pd.to_numeric(df[fallback], errors="coerce").fillna(default)
        return pd.Series(default, index=df.index, dtype=float)

    dist = _col("DIST_FROM_52W_HIGH_PCT", "DRAWDOWN_FROM_52W_HIGH_PCT", -100.0)
    vol  = _col("VOL_RATIO", "VOLUME_RATIO", 1.0)
    rs   = _col("RS_RANK_PCT", None, 0.5)
    sl50 = _col("SMA_50_SLOPE", None, 0.0)
    rsi  = _col("RSI", None, 50.0)

    mask = (
        dist.between(-5, 0.5)
        & (sl50 > 0)
        & (rs >= 0.75)
        & (vol >= 1.0)
        & rsi.between(50, 80)
    )
    out = df[mask].copy()
    if out.empty:
        return out

    out["MOMENTUM_SCORE"] = (
        rs[mask] * 0.35
        + (1 - dist[mask].abs() / 5).clip(0, 1) * 0.30
        + vol[mask].clip(0.8, 2.5) / 2.5 * 0.20
        + ((rsi[mask] - 50) / 30).clip(0, 1) * 0.15
    ).round(4)
    out["DIST_52W_HIGH_PCT"] = dist[mask].round(2)
    return out.sort_values("MOMENTUM_SCORE", ascending=False).reset_index(drop=True)


def build_momentum_screener_tab_html(screener_df: pd.DataFrame) -> str:
    """Build HTML section for A3 52W High Momentum screener."""
    import html as html_mod

    if screener_df is None or screener_df.empty:
        return (
            '<div class="card" style="margin-top:16px">'
            '<div class="sec-title">52W High Momentum</div>'
            '<p style="color:var(--muted)">No stocks matched the momentum criteria today '
            '(price within 5% of 52W high, RS top-25%, vol≥1×, RSI 50–80, SMA50 rising).</p></div>'
        )

    def _h(v: object) -> str:
        return html_mod.escape(str(v)) if v not in (None, "", float("nan")) else "—"

    def _pct(v: object, decimals: int = 1) -> str:
        try:
            return f"{float(v):+.{decimals}f}%"
        except (TypeError, ValueError):
            return "—"

    def _num(v: object, decimals: int = 2) -> str:
        try:
            return f"{float(v):.{decimals}f}"
        except (TypeError, ValueError):
            return "—"

    rows_html = ""
    for rank, (_, row) in enumerate(screener_df.iterrows(), start=1):
        dist = row.get("DIST_52W_HIGH_PCT", row.get("DIST_FROM_52W_HIGH_PCT", float("nan")))
        dist_cls = "pos-cell" if float(dist or -1) >= -1 else ""
        stage = str(row.get("STAGE", "UNKNOWN") or "UNKNOWN")
        stage_badge = stage_badge_html(stage)
        score = float(row.get("MOMENTUM_SCORE", 0) or 0)
        score_w = int(score * 100)
        score_html = (
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<span style="font-weight:700;min-width:32px">{score:.2f}</span>'
            f'<div style="flex:1;height:6px;background:#e2e8f0;border-radius:3px">'
            f'<div style="width:{score_w}%;height:100%;background:#3b82f6;border-radius:3px"></div></div>'
            f'</div>'
        )
        rows_html += (
            f'<tr>'
            f'<td class="num">{rank}</td>'
            f'<td><strong>{_h(row.get("SYMBOL"))}</strong></td>'
            f'<td>{_h(row.get("COMPANY_NAME", row.get("SYMBOL", "")))}</td>'
            f'<td>{_h(row.get("SECTOR_NAME", ""))}</td>'
            f'<td class="num">{_num(row.get("CURRENT_PRICE") or row.get("CLOSE"))}</td>'
            f'<td class="num {dist_cls}">{_pct(dist)}</td>'
            f'<td class="num">{_pct(row.get("RS_RANK_PCT", float("nan")) * 100 if row.get("RS_RANK_PCT") is not None else float("nan"), 0)}</td>'
            f'<td class="num">{_num(row.get("VOL_RATIO") or row.get("VOLUME_RATIO"), 2)}×</td>'
            f'<td class="num">{_num(row.get("RSI"), 1)}</td>'
            f'<td>{stage_badge}</td>'
            f'<td>{score_html}</td>'
            f'</tr>'
        )

    return (
        '<div class="card" style="margin-top:16px">'
        '<div class="sec-title">52W High Momentum — A3</div>'
        '<div class="sec-sub">Stocks within 5% of 52-week high with RS top-25%, rising SMA50, '
        'volume ≥ 1× average, and RSI 50–80. Ranked by composite momentum score.</div>'
        f'<div class="tbl-wrap"><table><thead><tr>'
        f'<th>#</th><th>Symbol</th><th>Company</th><th>Sector</th>'
        f'<th class="num">Price</th><th class="num">Dist 52W High</th>'
        f'<th class="num">RS Rank</th><th class="num">Vol Ratio</th>'
        f'<th class="num">RSI</th><th>Stage</th><th>Score</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
        f'<div style="margin-top:8px;font-size:11px;color:var(--muted)">'
        f'{len(screener_df)} candidates · Score = RS 35% + Proximity 30% + Volume 20% + RSI 15%</div>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# A6: Turnaround Detector
# ---------------------------------------------------------------------------

def compute_max_drawdown_column(
    candidates: pd.DataFrame,
    history: pd.DataFrame | None,
    lookback_days: int = 120,
) -> pd.DataFrame:
    """Enrich candidates with MAX_DRAWDOWN_PCT from price history.

    MAX_DRAWDOWN_PCT is the worst peak-to-trough drop experienced over the
    last ``lookback_days`` trading days.  Falls back to
    ``(FIFTY_TWO_WEEK_LOW / FIFTY_TWO_WEEK_HIGH − 1) × 100`` when history
    is unavailable.
    """
    df = candidates.copy()

    if history is not None and not history.empty:
        date_col = "TIMESTAMP" if "TIMESTAMP" in history.columns else "DATE"
        hist = history.copy()
        hist[date_col] = pd.to_datetime(hist[date_col], errors="coerce")
        hist["CLOSE"] = pd.to_numeric(hist["CLOSE"], errors="coerce")
        hist = hist.dropna(subset=[date_col, "SYMBOL", "CLOSE"]).sort_values([date_col])

        drawdowns: dict[str, float] = {}
        for sym, grp in hist.groupby("SYMBOL"):
            closes = grp.tail(lookback_days)["CLOSE"]
            if len(closes) < 20:
                continue
            rolling_max = closes.cummax()
            dd = float((closes / rolling_max - 1).min() * 100)
            drawdowns[sym] = round(dd, 1)

        df["MAX_DRAWDOWN_PCT"] = df["SYMBOL"].map(drawdowns)
    else:
        # Fallback: use 52W high/low spread as proxy
        high = pd.to_numeric(df.get("FIFTY_TWO_WEEK_HIGH", pd.Series(dtype=float)), errors="coerce")
        low = pd.to_numeric(df.get("FIFTY_TWO_WEEK_LOW", pd.Series(dtype=float)), errors="coerce")
        proxy = ((low / high) - 1) * 100
        df["MAX_DRAWDOWN_PCT"] = proxy.where(high > 0, other=float("nan")).round(1)

    return df


def turnaround_screener(candidates: pd.DataFrame) -> pd.DataFrame:
    """A6: Detect stocks in early recovery after a deep decline.

    Criteria (all must be met):
    1. MAX_DRAWDOWN_PCT < −30%  — experienced a significant downtrend
    2. Current price > SMA_50   — has crossed back above 50-day average
    3. 35 ≤ RSI ≤ 58            — recovering but not yet overbought
    4. SUPERTREND_STATE in {BULLISH, NEUTRAL}

    Ranked by RSI ascending (lower = earlier in recovery = higher opportunity).
    """
    df = candidates.copy()

    close = pd.to_numeric(df.get("CURRENT_PRICE", df.get("CLOSE", pd.Series(dtype=float))), errors="coerce")
    sma50 = pd.to_numeric(df.get("SMA_50", pd.Series(dtype=float)), errors="coerce")
    rsi = pd.to_numeric(df.get("RSI", pd.Series(dtype=float)), errors="coerce").fillna(50.0)
    dd = pd.to_numeric(df.get("MAX_DRAWDOWN_PCT", pd.Series(float("nan"), index=df.index)), errors="coerce")
    st = df.get("SUPERTREND_STATE", pd.Series("UNKNOWN", index=df.index)).fillna("UNKNOWN")

    mask = (
        (dd < -30)
        & (close > sma50)
        & rsi.between(35, 58)
        & st.isin(["BULLISH", "NEUTRAL"])
    )

    out = df[mask].copy()
    if out.empty:
        return out

    out = out.sort_values("RSI", ascending=True).reset_index(drop=True)
    out["TURNAROUND_SIGNAL"] = "EARLY_RECOVERY"
    return out


def build_turnaround_tab_html(screener_df: pd.DataFrame) -> str:
    """Build HTML section for A6 Turnaround Detector."""
    import html as html_mod

    if screener_df is None or screener_df.empty:
        return (
            '<div class="card" style="margin-top:16px">'
            '<div class="sec-title">Turnaround Detector — A6</div>'
            '<p style="color:var(--muted)">No turnaround candidates today '
            '(need: drawdown &lt;−30%, price above SMA50, RSI 35–58, Supertrend BULLISH/NEUTRAL).</p></div>'
        )

    def _h(v: object) -> str:
        return html_mod.escape(str(v)) if v not in (None, "", float("nan")) else "—"

    def _pct(v: object, decimals: int = 1, plus: bool = False) -> str:
        try:
            f = float(v)
            return f"{f:+.{decimals}f}%" if plus else f"{f:.{decimals}f}%"
        except (TypeError, ValueError):
            return "—"

    def _num(v: object, decimals: int = 2) -> str:
        try:
            return f"{float(v):.{decimals}f}"
        except (TypeError, ValueError):
            return "—"

    rows_html = ""
    for rank, (_, row) in enumerate(screener_df.iterrows(), start=1):
        dd_val = row.get("MAX_DRAWDOWN_PCT", float("nan"))
        try:
            dd_f = float(dd_val)
            dd_cls = "style=\"color:#dc2626;font-weight:700\""
            dd_str = f"{dd_f:.1f}%"
        except (TypeError, ValueError):
            dd_cls = ""
            dd_str = "—"

        rsi_val = float(row.get("RSI", 50) or 50)
        rsi_bar = int((rsi_val - 35) / (58 - 35) * 100)
        rsi_html = (
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<span style="min-width:32px">{rsi_val:.1f}</span>'
            f'<div style="flex:1;height:5px;background:#e2e8f0;border-radius:3px">'
            f'<div style="width:{rsi_bar}%;height:100%;background:#f59e0b;border-radius:3px"></div></div>'
            f'</div>'
        )

        st = str(row.get("SUPERTREND_STATE", "") or "")
        st_cls = "color:#16a34a;font-weight:600" if st == "BULLISH" else "color:#64748b"

        rows_html += (
            f'<tr>'
            f'<td class="num">{rank}</td>'
            f'<td><strong>{_h(row.get("SYMBOL"))}</strong></td>'
            f'<td>{_h(row.get("COMPANY_NAME", row.get("SYMBOL", "")))}</td>'
            f'<td>{_h(row.get("SECTOR_NAME", ""))}</td>'
            f'<td class="num">{_num(row.get("CURRENT_PRICE") or row.get("CLOSE"))}</td>'
            f'<td class="num" {dd_cls}>{dd_str}</td>'
            f'<td>{rsi_html}</td>'
            f'<td style="{st_cls}">{_h(st)}</td>'
            f'<td class="num">{_num(row.get("SMA_50"))}</td>'
            f'<td>{stage_badge_html(str(row.get("STAGE", "UNKNOWN") or "UNKNOWN"))}</td>'
            f'</tr>'
        )

    return (
        '<div class="card" style="margin-top:16px">'
        '<div class="sec-title">Turnaround Detector — A6</div>'
        '<div class="sec-sub">Stocks that experienced a deep decline (&gt;30% drawdown) and are now showing '
        'early recovery: price above SMA50, RSI 35–58, Supertrend turning bullish. '
        'Sorted by RSI ascending — lower RSI = earlier in recovery.</div>'
        f'<div class="tbl-wrap"><table><thead><tr>'
        f'<th>#</th><th>Symbol</th><th>Company</th><th>Sector</th>'
        f'<th class="num">Price</th><th class="num">Max Drawdown</th>'
        f'<th>RSI</th><th>Supertrend</th><th class="num">SMA50</th><th>Stage</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
        f'<div style="margin-top:8px;font-size:11px;color:var(--muted)">'
        f'{len(screener_df)} turnaround candidates · Earlier recovery = better risk/reward entry</div>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))

    import argparse
    ap = argparse.ArgumentParser(description="A1 Stage Analysis Screener")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    data_dir = Path(__file__).parent / "data"
    stock_csv = data_dir / "nse_sec_full_data.csv"
    if not stock_csv.exists():
        print(f"Stock data not found at {stock_csv}")
        sys.exit(1)

    print("Loading stock data…")
    history = pd.read_csv(stock_csv, usecols=["SYMBOL", "TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"])

    # Build a stub candidates frame from latest prices
    latest = history.sort_values("TIMESTAMP").groupby("SYMBOL").last().reset_index()
    latest = latest.rename(columns={"CLOSE": "CLOSE"})
    latest["COMPANY_NAME"] = latest["SYMBOL"]
    latest["SECTOR_NAME"] = ""
    latest["TECHNICAL_SCORE"] = 50.0
    latest["RELATIVE_STRENGTH"] = 0.0
    latest["ENHANCED_FUND_SCORE"] = 50.0

    print(f"Running stage screener on {len(latest)} symbols…")
    result = run_stage_screener(latest, history)
    counts = result["STAGE"].value_counts()
    print("\nStage distribution:")
    for stage, cnt in counts.items():
        print(f"  {stage:12s}: {cnt}")

    s2 = result[result["STAGE"] == "STAGE_2"]
    print(f"\nTop 20 Stage 2 stocks:")
    print(s2[["SYMBOL", "STAGE_SCORE", "DIST_FROM_52W_HIGH_PCT", "VOL_RATIO", "SMA_50_SLOPE"]].head(20).to_string(index=False))
