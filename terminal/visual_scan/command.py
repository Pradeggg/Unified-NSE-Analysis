"""End-to-end visual scan command handler."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from .chart_renderer import render_visual_scan_charts
from .data_loader import VisualScanInput, load_visual_scan_input
from .detectors import (
    detect_breakout_retest,
    detect_cup_with_handle,
    detect_trend_structure,
    detect_vcp,
    detect_volume_quality,
    score_visual_scan,
)
from .models import ChartAnnotation, PatternEvidence, PatternStatus, VisualScanPack
from .report import save_visual_scan_outputs
from .tradingview import capture_tradingview_screenshot


def _daily_for_mtf(daily: pd.DataFrame) -> pd.DataFrame:
    if daily is None or daily.empty:
        return pd.DataFrame()
    df = daily.copy()
    rename = {
        "trade_date": "TIMESTAMP",
        "date": "TIMESTAMP",
        "open": "OPEN",
        "high": "HIGH",
        "low": "LOW",
        "close": "CLOSE",
        "volume": "TOTTRDQTY",
    }
    df = df.rename(columns={key: value for key, value in rename.items() if key in df.columns})
    required = {"TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    if "TOTTRDQTY" not in df.columns:
        df["TOTTRDQTY"] = 0
    return df[["TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]].copy()


def _derive_mtf_payload(symbol: str, daily: pd.DataFrame) -> dict[str, Any]:
    mtf_daily = _daily_for_mtf(daily)
    if mtf_daily.empty:
        return {}
    try:
        from terminal import mtf as mtf_engine

        result = mtf_engine.compute_mtf(
            symbol,
            timeframes=(mtf_engine.TF_MONTHLY, mtf_engine.TF_WEEKLY, mtf_engine.TF_DAILY),
            daily_loader=lambda *_args, **_kwargs: mtf_daily,
            intraday_loader=lambda *_args, **_kwargs: None,
        )
        return result.as_dict()
    except Exception:
        return {}


def _mtf_pattern(mtf_payload: dict[str, Any]) -> PatternEvidence:
    if not mtf_payload:
        return PatternEvidence(
            "MTF Alignment",
            PatternStatus.INSUFFICIENT_DATA,
            0.0,
            caveats=["MTF evidence unavailable."],
        )

    score = float(mtf_payload.get("confluence_score") or mtf_payload.get("score") or 0)
    status = (
        PatternStatus.CONFIRMED
        if score >= 70
        else PatternStatus.CANDIDATE
        if score >= 45
        else PatternStatus.ABSENT
    )
    return PatternEvidence(
        pattern="MTF Alignment",
        status=status,
        confidence=round(min(score / 100.0, 1.0), 2),
        evidence=[str(item) for item in (mtf_payload.get("rationale") or [])[:5]],
        metrics=mtf_payload,
    )


def _annotations_from_patterns(patterns: list[PatternEvidence], *, include_targets: bool = True) -> list[ChartAnnotation]:
    annotations: list[ChartAnnotation] = []
    for pattern in patterns:
        if pattern.status not in {PatternStatus.CONFIRMED, PatternStatus.CANDIDATE}:
            continue
        if pattern.zones.pivot is not None:
            annotations.append(
                ChartAnnotation(
                    kind="pivot",
                    label=f"{pattern.pattern} Pivot",
                    price=pattern.zones.pivot,
                    color="#22c55e",
                )
            )
        if pattern.zones.support is not None:
            annotations.append(
                ChartAnnotation(
                    kind="support",
                    label=f"{pattern.pattern} Support",
                    price=pattern.zones.support,
                    color="#38bdf8",
                )
            )
        if pattern.zones.invalidation is not None:
            annotations.append(
                ChartAnnotation(
                    kind="invalidation",
                    label="Invalidation",
                    price=pattern.zones.invalidation,
                    color="#ef4444",
                )
            )
        if include_targets and pattern.zones.target_1 is not None:
            annotations.append(
                ChartAnnotation(
                    kind="target",
                    label="Target 1",
                    price=pattern.zones.target_1,
                    color="#f59e0b",
                )
            )
    return annotations


def run_visual_scan(
    symbol: str,
    *,
    input_data: VisualScanInput | None = None,
    output_dir: str | Path = "reports/visual_scan",
    capture_tradingview: bool = True,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    loaded = load_visual_scan_input(symbol, input_data=input_data)

    trend = detect_trend_structure(loaded.daily, benchmark=loaded.benchmark)
    vcp = detect_vcp(loaded.daily)
    cup = detect_cup_with_handle(loaded.daily)
    pivot = vcp.zones.pivot or cup.zones.pivot
    breakout = detect_breakout_retest(loaded.daily, pivot=pivot)
    volume = detect_volume_quality(loaded.daily)
    source_trail = dict(loaded.source_trail)
    mtf_payload = dict(loaded.mtf)
    if mtf_payload:
        source_trail["mtf"] = {"status": "injected", "timeframes": mtf_payload.get("timeframes", [])}
    else:
        mtf_payload = _derive_mtf_payload(loaded.symbol, loaded.daily)
        source_trail["mtf"] = {
            "status": "derived" if mtf_payload else "missing",
            "timeframes": mtf_payload.get("timeframes", []),
        }
    mtf = _mtf_pattern(mtf_payload)

    patterns = [trend, mtf, vcp, cup, breakout, volume]
    verdict = score_visual_scan(loaded.symbol, patterns)
    annotations = _annotations_from_patterns(patterns, include_targets=bool(verdict.targets))

    asset_dir = Path(output_dir) / "assets"
    chart_paths: dict[str, str] = {}
    try:
        chart_paths = render_visual_scan_charts(
            symbol=loaded.symbol,
            run_id=run_id[:8],
            daily=loaded.daily,
            weekly=loaded.weekly,
            annotations=annotations,
            output_dir=asset_dir,
        )
    except Exception as exc:
        loaded.missing_evidence.append(f"chart_assets: {exc}")

    tradingview: dict[str, Any] = {
        "status": "not_attempted",
        "message": "TradingView capture disabled.",
    }
    if capture_tradingview:
        tradingview = capture_tradingview_screenshot(
            loaded.symbol,
            output_dir=asset_dir,
            run_id=run_id[:8],
        )

    pack = VisualScanPack(
        run_id=run_id,
        symbol=loaded.symbol,
        as_of=str(loaded.daily["trade_date"].max().date()) if not loaded.daily.empty else "",
        verdict=verdict,
        patterns=patterns,
        annotations=annotations,
        chart_paths=chart_paths,
        tradingview=tradingview,
        source_trail=source_trail,
        missing_evidence=loaded.missing_evidence,
    )
    saved = save_visual_scan_outputs(pack, output_dir=output_dir)
    summary = (
        f"{loaded.symbol} Visual Scan: {verdict.stance} | Score {verdict.score} | "
        f"Confidence {verdict.confidence}. Report: {saved['html_path']}"
    )

    return {
        "success": True,
        "symbol": loaded.symbol,
        "run_id": run_id,
        "summary": summary,
        **saved,
        "pack": pack.to_dict(),
    }
