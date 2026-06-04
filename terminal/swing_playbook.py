from __future__ import annotations

import argparse
import csv
import html
import os
import shlex
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
PG_DSN = (
    os.environ.get("AGENT_ADDA_PG_DSN")
    or os.environ.get("PG_DSN")
    or "dbname=nse_market user=nse_admin host=/tmp"
)

REQUIRED_COLUMNS = ("symbol", "close", "volume", "stage", "technical_score")
OPTIONAL_DEFAULTS: dict[str, Any] = {
    "company_name": "",
    "sector": "Unknown",
    "turnover_cr": 0.0,
    "relative_strength": 50.0,
    "rsi_14": 50.0,
    "sma_20": 0.0,
    "sma_50": 0.0,
    "sma_200": 0.0,
    "atr_14": 0.0,
    "volume_ratio_20d": 1.0,
    "vcp_pick": 0,
    "vcp_score": 0.0,
    "vcp_breakout_pct": 0.0,
    "vcp_contraction_pct": 0.0,
    "enhanced_fund_score": 50.0,
    "sales_growth_pct": 0.0,
    "pat_growth_pct": 0.0,
    "latest_result_age_days": 9999.0,
    "is_portfolio_holding": False,
    "quantity": 0.0,
    "avg_cost": 0.0,
    "position_value": 0.0,
}


@dataclass(frozen=True)
class SwingPlaybookOptions:
    project_root: Path = ROOT
    fresh: bool = False
    section: str = "all"
    top_n: int = 10
    account_value: float | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class ScoreBreakdown:
    technical: float
    relative_strength: float
    pattern: float
    context: float
    fundamentals: float
    liquidity: float

    @property
    def total(self) -> float:
        return round(
            self.technical
            + self.relative_strength
            + self.pattern
            + self.context
            + self.fundamentals
            + self.liquidity,
            1,
        )


@dataclass(frozen=True)
class RiskPlan:
    entry_trigger: float
    initial_stop: float
    target_1: float
    target_2: float
    stop_distance_pct: float
    r_multiple_target_1: float
    r_multiple_target_2: float
    risk_note: str


@dataclass(frozen=True)
class PlaybookCandidate:
    symbol: str
    sleeve: str
    action_label: str
    score: float
    score_breakdown: ScoreBreakdown
    entry_label: str
    risk_plan: RiskPlan
    evidence: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortfolioAction:
    symbol: str
    label: str
    reason: str
    stop: float | None
    risk_note: str


@dataclass(frozen=True)
class SwingPlaybookResult:
    success: bool
    markdown: str
    html_path: str
    markdown_path: str
    candidates_csv: str
    portfolio_csv: str
    warnings: tuple[str, ...] = ()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _bool(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n", ""}:
        return False
    return False


def normalize_candidate_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if raw is None or raw.empty:
        raise ValueError("swing playbook requires at least one candidate row")
    missing_required = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing_required:
        raise ValueError(f"swing playbook missing required columns: {', '.join(missing_required)}")
    frame = raw.copy()
    filled: list[str] = []
    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in frame.columns:
            frame[column] = default
            filled.append(column)
    frame["symbol"] = frame["symbol"].astype(str).str.upper().str.strip()
    frame["stage"] = frame["stage"].fillna("UNKNOWN").astype(str).str.upper().str.strip()
    numeric_columns = [
        "close",
        "volume",
        "technical_score",
        "turnover_cr",
        "relative_strength",
        "rsi_14",
        "sma_20",
        "sma_50",
        "sma_200",
        "atr_14",
        "volume_ratio_20d",
        "vcp_pick",
        "vcp_score",
        "vcp_breakout_pct",
        "vcp_contraction_pct",
        "enhanced_fund_score",
        "sales_growth_pct",
        "pat_growth_pct",
        "latest_result_age_days",
        "quantity",
        "avg_cost",
        "position_value",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(
            float(OPTIONAL_DEFAULTS.get(column, 0.0))
        )
    ratio_rs = frame["relative_strength"].abs() <= 2
    frame.loc[ratio_rs, "relative_strength"] = frame.loc[ratio_rs, "relative_strength"] * 100
    frame["is_portfolio_holding"] = frame["is_portfolio_holding"].map(_bool)
    warnings = [f"filled missing optional columns: {', '.join(filled)}"] if filled else []
    return frame, warnings


def build_risk_plan(row: pd.Series, *, sleeve: str) -> RiskPlan:
    close = _num(row.get("close"))
    atr = _num(row.get("atr_14"), close * 0.03 if close else 0.0)
    if atr <= 0 and close > 0:
        atr = close * 0.03
    multiple = 1.8 if sleeve.upper() == "TACTICAL" else 2.4
    raw_stop = close - (atr * multiple)
    structure_stop = _num(row.get("sma_20" if sleeve.upper() == "TACTICAL" else "sma_50"), raw_stop)
    stop = min(raw_stop, structure_stop) if structure_stop > 0 else raw_stop
    entry = close * 1.01
    risk = max(entry - stop, close * 0.01)
    target_1 = entry + (risk * 1.5)
    target_2 = entry + (risk * 2.0)
    stop_distance_pct = ((entry - stop) / entry * 100.0) if entry else 0.0
    return RiskPlan(
        entry_trigger=round(entry, 2),
        initial_stop=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        stop_distance_pct=round(stop_distance_pct, 1),
        r_multiple_target_1=1.5,
        r_multiple_target_2=2.0,
        risk_note=f"Balanced profile: risk up to 1.0% account equity; stop distance {stop_distance_pct:.1f}%.",
    )


def _score_technical(row: pd.Series, *, sleeve: str) -> float:
    base = _clamp(_num(row.get("technical_score")))
    stage_bonus = 0.0
    if row.get("stage") == "STAGE_2":
        stage_bonus = 15.0
    elif row.get("stage") == "STAGE_4":
        stage_bonus = -20.0

    close = _num(row.get("close"))
    ma_bonus = 0.0
    if close > _num(row.get("sma_20")) > _num(row.get("sma_50")) > 0:
        ma_bonus += 10.0
    if close > _num(row.get("sma_50")) > _num(row.get("sma_200")) > 0:
        ma_bonus += 10.0

    rsi = _num(row.get("rsi_14"), 50.0)
    if sleeve.upper() == "TACTICAL":
        rsi_bonus = 8.0 if 50 <= rsi <= 75 else (-8.0 if rsi < 45 else 0.0)
    else:
        rsi_bonus = 8.0 if 45 <= rsi <= 72 else (-8.0 if rsi < 40 else 0.0)

    return round(_clamp(base + stage_bonus + ma_bonus + rsi_bonus) * 0.35, 2)


def _score_relative_strength(row: pd.Series) -> float:
    return round(_clamp(_num(row.get("relative_strength"), 50.0)) * 0.20, 2)


def _score_pattern(row: pd.Series) -> float:
    raw = _num(row.get("vcp_score"))
    if _num(row.get("vcp_pick")) >= 1:
        raw += 12.0
    if _num(row.get("vcp_breakout_pct")) >= 1.5:
        raw += 8.0
    if _num(row.get("vcp_contraction_pct")) >= 8:
        raw += 5.0
    return round(_clamp(raw) * 0.15, 2)


def _score_context(row: pd.Series) -> float:
    sector_strength = _num(row.get("sector_strength"), 50.0)
    market_regime_score = _num(row.get("market_regime_score"), 50.0)
    return round(_clamp((sector_strength * 0.6) + (market_regime_score * 0.4)) * 0.15, 2)


def _score_fundamentals(row: pd.Series) -> float:
    raw = _num(row.get("enhanced_fund_score"), 50.0)
    if _num(row.get("sales_growth_pct")) > 0:
        raw += 8.0
    if _num(row.get("pat_growth_pct")) > 0:
        raw += 8.0
    if _num(row.get("latest_result_age_days"), 9999.0) <= 220:
        raw += 4.0
    return round(_clamp(raw) * 0.10, 2)


def _score_liquidity(row: pd.Series) -> float:
    turnover = _num(row.get("turnover_cr"))
    volume = _num(row.get("volume"))
    raw = 30.0
    if turnover >= 20:
        raw += 40.0
    elif turnover >= 5:
        raw += 25.0
    if volume >= 1_000_000:
        raw += 30.0
    elif volume >= 250_000:
        raw += 15.0
    return round(_clamp(raw) * 0.05, 2)


def score_candidate(row: pd.Series, *, sleeve: str) -> ScoreBreakdown:
    return ScoreBreakdown(
        technical=_score_technical(row, sleeve=sleeve),
        relative_strength=_score_relative_strength(row),
        pattern=_score_pattern(row),
        context=_score_context(row),
        fundamentals=_score_fundamentals(row),
        liquidity=_score_liquidity(row),
    )


def _entry_label(row: pd.Series, score: ScoreBreakdown, *, sleeve: str) -> str:
    close = _num(row.get("close"))
    volume_ratio = _num(row.get("volume_ratio_20d"), 1.0)
    required_volume = 1.3 if sleeve.upper() == "TACTICAL" else 1.1
    if (
        row.get("stage") == "STAGE_2"
        and close > _num(row.get("sma_20"))
        and volume_ratio >= required_volume
        and score.total >= 70
    ):
        return "EOD_READY"
    return "INTRADAY_CONFIRM"


def _candidate_evidence(row: pd.Series, score: ScoreBreakdown) -> tuple[str, ...]:
    return (
        f"stage={row.get('stage')}",
        f"technical={_num(row.get('technical_score')):.1f}",
        f"RS={_num(row.get('relative_strength')):.1f}",
        f"VCP={_num(row.get('vcp_score')):.1f}",
        f"fund={_num(row.get('enhanced_fund_score')):.1f}",
        f"score={score.total:.1f}",
    )


def _to_candidate(row: pd.Series, *, sleeve: str) -> PlaybookCandidate:
    score = score_candidate(row, sleeve=sleeve)
    return PlaybookCandidate(
        symbol=str(row.get("symbol")).upper(),
        sleeve=sleeve.upper(),
        action_label="WATCHLIST" if score.total < 70 else "CANDIDATE",
        score=score.total,
        score_breakdown=score,
        entry_label=_entry_label(row, score, sleeve=sleeve),
        risk_plan=build_risk_plan(row, sleeve=sleeve),
        evidence=_candidate_evidence(row, score),
        warnings=tuple(),
    )


def rank_swing_candidates(
    frame: pd.DataFrame, *, top_n: int = 10
) -> tuple[list[PlaybookCandidate], list[PlaybookCandidate]]:
    tactical_rows = frame[frame["stage"].isin(["STAGE_1", "STAGE_2", "STAGE_3"])].copy()
    tactical_rows = tactical_rows[tactical_rows["close"] > 0]
    tactical = [_to_candidate(row, sleeve="TACTICAL") for _, row in tactical_rows.iterrows()]

    position_rows = frame[(frame["stage"] == "STAGE_2") & (frame["close"] > frame["sma_50"])].copy()
    position = [_to_candidate(row, sleeve="POSITION") for _, row in position_rows.iterrows()]

    tactical = sorted(tactical, key=lambda candidate: candidate.score, reverse=True)[:top_n]
    position = sorted(position, key=lambda candidate: candidate.score, reverse=True)[:top_n]
    return tactical, position


def _portfolio_label(row: pd.Series) -> tuple[str, str]:
    stage = str(row.get("stage") or "UNKNOWN").upper()
    tech = _num(row.get("technical_score"))
    rs = _num(row.get("relative_strength"), 50.0)
    close = _num(row.get("close"))
    sma20 = _num(row.get("sma_20"))
    sma50 = _num(row.get("sma_50"))
    if stage in {"STAGE_4"} or (close > 0 and sma50 > 0 and close < sma50 and rs < 50):
        return "EXIT_WATCH", "stage or RS has degraded and price is below key trend support"
    if stage == "STAGE_3" or (close > 0 and sma20 > 0 and close < sma20):
        return "TIGHTEN_STOP", "trend is weakening or price is below short-term support"
    if stage == "STAGE_2" and tech >= 75 and rs >= 70 and close > sma20 > 0:
        return "ADD_OK", "holding remains strong and has a defined add trigger"
    if tech >= 60 and rs >= 55:
        return "HOLD", "evidence remains acceptable"
    return "NO_FRESH_ADD", "not a sell, but fresh capital is not justified"


def build_portfolio_actions(frame: pd.DataFrame) -> list[PortfolioAction]:
    if "is_portfolio_holding" not in frame.columns:
        return []
    holdings = frame[frame["is_portfolio_holding"].map(_bool)].copy()
    actions: list[PortfolioAction] = []
    for _, row in holdings.iterrows():
        label, reason = _portfolio_label(row)
        risk = build_risk_plan(row, sleeve="POSITION")
        actions.append(
            PortfolioAction(
                symbol=str(row.get("symbol")).upper(),
                label=label,
                reason=reason,
                stop=risk.initial_stop,
                risk_note=risk.risk_note,
            )
        )
    return actions


def _candidate_table(candidates: list[PlaybookCandidate]) -> str:
    lines = [
        "| Symbol | Score | Entry Label | Trigger | Stop | Target 1 | Target 2 | Evidence |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for candidate in candidates:
        risk = candidate.risk_plan
        lines.append(
            "| "
            f"{candidate.symbol} | {candidate.score:.1f} | {candidate.entry_label} | "
            f"{risk.entry_trigger:.2f} | {risk.initial_stop:.2f} | {risk.target_1:.2f} | "
            f"{risk.target_2:.2f} | {'; '.join(candidate.evidence)} |"
        )
    return "\n".join(lines) if candidates else "_No candidates passed filters._"


def _portfolio_table(actions: list[PortfolioAction]) -> str:
    lines = ["| Symbol | Action | Stop | Reason |", "|---|---|---:|---|"]
    for action in actions:
        stop = "" if action.stop is None else f"{action.stop:.2f}"
        lines.append(f"| {action.symbol} | {action.label} | {stop} | {action.reason} |")
    return "\n".join(lines) if actions else "_No portfolio holdings were available._"


def render_markdown(
    *,
    tactical: list[PlaybookCandidate],
    position: list[PlaybookCandidate],
    portfolio_actions: list[PortfolioAction],
    warnings: list[str],
    as_of: str,
) -> str:
    swing_allowed = "YES" if tactical or position else "NO"
    lines = [
        "# Swing Trading Playbook",
        "",
        f"Generated: {as_of}",
        "",
        "## Daily Action Sheet",
        "",
        f"- Swing risk allowed: {swing_allowed}",
        "- Risk profile: Balanced; max 1.0% account risk per trade; target 8-12 open positions.",
        f"- Tactical candidates: {len(tactical)}",
        f"- Position candidates: {len(position)}",
        f"- Portfolio actions: {len(portfolio_actions)}",
        "",
        "## Tactical Swing Candidates",
        "",
        _candidate_table(tactical),
        "",
        "## Position Swing Candidates",
        "",
        _candidate_table(position),
        "",
        "## Portfolio Actions",
        "",
        _portfolio_table(portfolio_actions),
        "",
        "## Source Freshness And Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- No missing optional evidence was detected in the candidate frame.")
    lines.extend(["", "Not investment advice. For research and learning only."])
    return "\n".join(lines)


def _html_from_markdown(markdown: str, title: str) -> str:
    try:
        from terminal.reports import _md_to_html_basic

        body = _md_to_html_basic(markdown)
    except Exception:
        body = "<pre>" + html.escape(markdown) + "</pre>"
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        "<style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;color:#172033}"
        "table{border-collapse:collapse;width:100%;margin:12px 0}"
        "th,td{border:1px solid #d7dde8;padding:8px;text-align:left}"
        "th{background:#f3f6fb}.note{color:#5b6472}"
        "</style></head><body>"
        f"{body}</body></html>"
    )


def _write_candidate_csv(path: Path, candidates: list[PlaybookCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "sleeve",
                "score",
                "action_label",
                "entry_label",
                "entry_trigger",
                "initial_stop",
                "target_1",
                "target_2",
                "technical",
                "relative_strength",
                "pattern",
                "context",
                "fundamentals",
                "liquidity",
            ],
        )
        writer.writeheader()
        for candidate in candidates:
            risk = candidate.risk_plan
            breakdown = candidate.score_breakdown
            writer.writerow(
                {
                    "symbol": candidate.symbol,
                    "sleeve": candidate.sleeve,
                    "score": candidate.score,
                    "action_label": candidate.action_label,
                    "entry_label": candidate.entry_label,
                    "entry_trigger": risk.entry_trigger,
                    "initial_stop": risk.initial_stop,
                    "target_1": risk.target_1,
                    "target_2": risk.target_2,
                    "technical": breakdown.technical,
                    "relative_strength": breakdown.relative_strength,
                    "pattern": breakdown.pattern,
                    "context": breakdown.context,
                    "fundamentals": breakdown.fundamentals,
                    "liquidity": breakdown.liquidity,
                }
            )


def _write_portfolio_csv(path: Path, actions: list[PortfolioAction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "label", "stop", "reason", "risk_note"])
        writer.writeheader()
        for action in actions:
            writer.writerow(
                {
                    "symbol": action.symbol,
                    "label": action.label,
                    "stop": action.stop,
                    "reason": action.reason,
                    "risk_note": action.risk_note,
                }
            )


def _add_derived_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    close = pd.to_numeric(out["close"], errors="coerce").fillna(0.0)
    for column, factor in (("sma_20", 0.98), ("sma_50", 0.94), ("sma_200", 0.85)):
        if column not in out.columns:
            out[column] = close * factor
            continue
        values = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
        out[column] = values.where(values > 0, close * factor)
    if "atr_14" not in out.columns:
        out["atr_14"] = close * 0.035
    else:
        atr = pd.to_numeric(out["atr_14"], errors="coerce").fillna(0.0)
        out["atr_14"] = atr.where(atr > 0, close * 0.035)
    if "volume_ratio_20d" not in out.columns:
        out["volume_ratio_20d"] = 1.0
    else:
        volume_ratio = pd.to_numeric(out["volume_ratio_20d"], errors="coerce").fillna(0.0)
        out["volume_ratio_20d"] = volume_ratio.where(volume_ratio > 0, 1.0)
    return out


def _pg_table_exists(conn: Any, qualified_name: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (qualified_name,))
            row = cur.fetchone()
        return bool(row and row[0])
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def load_candidates_from_postgres(options: SwingPlaybookOptions) -> pd.DataFrame:
    import psycopg2

    limit = max(int(options.top_n or 10) * 10, 100)
    with psycopg2.connect(PG_DSN) as conn:
        has_instruments = _pg_table_exists(conn, "ref.instruments")
        has_vcp_picks = _pg_table_exists(conn, "scores.stage2_vcp_picks")

        instrument_select = (
            "COALESCE(i.company_name, s.company_name, s.symbol) AS company_name,\n"
            "            COALESCE(i.sector, s.sector, 'Unknown') AS sector,"
            if has_instruments
            else "COALESCE(s.company_name, s.symbol) AS company_name,\n"
            "            COALESCE(s.sector, 'Unknown') AS sector,"
        )
        instrument_join = "LEFT JOIN ref.instruments i ON i.symbol = s.symbol" if has_instruments else ""
        vcp_select = (
            "COALESCE(p.vcp_score, 0) AS vcp_score,\n"
            "            CASE WHEN p.symbol IS NULL THEN 0 ELSE 1 END AS vcp_pick,\n"
            "            COALESCE(p.vcp_breakout_pct, 0) AS vcp_breakout_pct,\n"
            "            COALESCE(p.vcp_contraction_pct, 0) AS vcp_contraction_pct,"
            if has_vcp_picks
            else "0.0 AS vcp_score,\n"
            "            0 AS vcp_pick,\n"
            "            0.0 AS vcp_breakout_pct,\n"
            "            0.0 AS vcp_contraction_pct,"
        )
        vcp_join = (
            "LEFT JOIN scores.stage2_vcp_picks p\n"
            "               ON p.symbol = s.symbol AND p.snapshot_date = s.snapshot_date"
            if has_vcp_picks
            else ""
        )
        query = f"""
            WITH latest AS (
                SELECT max(snapshot_date) AS snapshot_date
                FROM scores.stage_snapshots
            ),
            latest_eod AS (
                SELECT max(trade_date) AS trade_date
                FROM market.equity_eod
                WHERE series = 'EQ'
            ),
            liquid AS (
                SELECT symbol, close, volume, turnover_cr
                FROM market.equity_eod
                WHERE trade_date = (SELECT trade_date FROM latest_eod)
                  AND series = 'EQ'
                  AND close > 50
                  AND volume > 0
                ORDER BY turnover_cr DESC NULLS LAST, volume DESC NULLS LAST
                LIMIT %(limit)s
            )
            SELECT
                s.symbol,
                {instrument_select}
                l.close,
                l.volume,
                l.turnover_cr,
                s.stage,
                COALESCE(s.technical_score, 50) AS technical_score,
                COALESCE(s.relative_strength, 50) AS relative_strength,
                COALESCE(s.rsi, 50) AS rsi_14,
                {vcp_select}
                COALESCE(s.enhanced_fund_score, s.fundamental_score, 50) AS enhanced_fund_score,
                COALESCE(s.sales_growth, 0) AS sales_growth_pct,
                0.0 AS pat_growth_pct,
                9999.0 AS latest_result_age_days,
                0.0 AS sma_20,
                0.0 AS sma_50,
                0.0 AS sma_200,
                0.0 AS atr_14,
                1.0 AS volume_ratio_20d
            FROM scores.stage_snapshots s
            JOIN latest ON latest.snapshot_date = s.snapshot_date
            JOIN liquid l ON l.symbol = s.symbol
            {instrument_join}
            {vcp_join}
            WHERE s.snapshot_date = latest.snapshot_date
            ORDER BY COALESCE(s.technical_score, 0) DESC, COALESCE(s.relative_strength, 0) DESC
        """
        frame = pd.read_sql_query(query, conn, params={"limit": limit})
    if frame.empty:
        raise ValueError("no swing playbook candidates returned from PostgreSQL")
    return _add_derived_indicators(frame)


def parse_swing_playbook_args(
    text: str, project_root: Path | str | None = None
) -> SwingPlaybookOptions:
    raw = (text or "").strip()
    try:
        parts = shlex.split(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid /swing-playbook command: {exc}") from exc
    if parts and parts[0].lower() in {"/swing-playbook", "/swing_playbook"}:
        parts = parts[1:]

    parser = argparse.ArgumentParser(prog="/swing-playbook", add_help=False, exit_on_error=False)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--account-value", type=float, default=None)
    parser.add_argument("--as-of", default=None)
    section = parser.add_mutually_exclusive_group()
    section.add_argument("--all", dest="section", action="store_const", const="all")
    section.add_argument("--tactical", dest="section", action="store_const", const="tactical")
    section.add_argument("--position", dest="section", action="store_const", const="position")
    section.add_argument("--portfolio", dest="section", action="store_const", const="portfolio")
    parser.set_defaults(section="all")

    try:
        namespace, unknown = parser.parse_known_args(parts)
    except argparse.ArgumentError as exc:
        raise ValueError(str(exc)) from exc
    if unknown:
        raise ValueError(f"Unrecognized /swing-playbook option(s): {' '.join(unknown)}")
    if namespace.top_n < 1:
        raise ValueError("--top-n must be at least 1")

    return SwingPlaybookOptions(
        project_root=Path(project_root) if project_root is not None else ROOT,
        fresh=bool(namespace.fresh),
        section=namespace.section,
        top_n=namespace.top_n,
        account_value=namespace.account_value,
        as_of=namespace.as_of,
    )


def handle_swing_playbook_command(
    text: str, project_root: Path | str | None = None
) -> str:
    try:
        options = parse_swing_playbook_args(text, project_root=project_root)
        result = generate_swing_playbook(options=options)
    except Exception as exc:
        return f"Swing Playbook failed: {exc}"

    return (
        f"Swing Playbook: {result.html_path}\n"
        f"Report: {result.html_path}\n"
        f"Markdown: {result.markdown_path}\n"
        f"Candidates: {result.candidates_csv}\n"
        f"Portfolio actions: {result.portfolio_csv}"
    )


def generate_swing_playbook(
    *,
    options: SwingPlaybookOptions | None = None,
    candidates: pd.DataFrame | None = None,
) -> SwingPlaybookResult:
    options = options or SwingPlaybookOptions()
    root = Path(options.project_root)
    if candidates is None:
        candidates = load_candidates_from_postgres(options=options)
    frame, warnings = normalize_candidate_frame(candidates)
    tactical, position = rank_swing_candidates(frame, top_n=options.top_n)
    portfolio_actions = build_portfolio_actions(frame)
    if options.section == "tactical":
        position = []
        portfolio_actions = []
    elif options.section == "position":
        tactical = []
        portfolio_actions = []
    elif options.section == "portfolio":
        tactical = []
        position = []

    as_of = options.as_of or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    markdown = render_markdown(
        tactical=tactical,
        position=position,
        portfolio_actions=portfolio_actions,
        warnings=warnings,
        as_of=as_of,
    )

    today = date.today()
    archive_dir = root / "reports" / "swing_playbook" / str(today.year)
    latest_dir = root / "reports" / "latest"
    archive_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    archive_md = archive_dir / f"Swing_Playbook_{today.strftime('%Y%m%d')}.md"
    archive_html = archive_dir / f"Swing_Playbook_{today.strftime('%Y%m%d')}.html"
    latest_md = latest_dir / "swing_playbook.md"
    latest_html = latest_dir / "swing_playbook.html"
    latest_candidates = latest_dir / "swing_playbook_candidates.csv"
    latest_portfolio = latest_dir / "swing_playbook_portfolio_actions.csv"

    archive_md.write_text(markdown, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    html_text = _html_from_markdown(markdown, "Swing Trading Playbook")
    archive_html.write_text(html_text, encoding="utf-8")
    latest_html.write_text(html_text, encoding="utf-8")
    _write_candidate_csv(latest_candidates, tactical + position)
    _write_portfolio_csv(latest_portfolio, portfolio_actions)

    return SwingPlaybookResult(
        success=True,
        markdown=markdown,
        html_path=str(latest_html),
        markdown_path=str(latest_md),
        candidates_csv=str(latest_candidates),
        portfolio_csv=str(latest_portfolio),
        warnings=tuple(warnings),
    )
