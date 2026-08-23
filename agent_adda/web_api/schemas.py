"""Shared Pydantic schemas — mirrors browser_plugin/src/types.ts."""
from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


Exchange = Literal["NSE", "BSE"]
Timeframe = Literal["1m","3m","5m","15m","30m","1h","4h","1D","1W","1M"]
PatternStatus = Literal["confirmed","forming","none","engine_unavailable"]
ConflictPolicy = Literal["prefer_pg","show_mismatch"]

_TV_TF_MAP: dict[str, str] = {
    "1": "1m", "3": "3m", "5": "5m", "15": "15m",
    "30": "30m", "45": "30m", "60": "1h", "120": "1h",
    "240": "4h", "D": "1D", "W": "1W", "M": "1M",
}


class KeyLevels(BaseModel):
    support: Optional[float] = None
    resistance: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema100: Optional[float] = None
    ema200: Optional[float] = None
    supertrend: Optional[float] = None
    supertrend_direction: Optional[Literal["bullish","bearish"]] = None
    vwap: Optional[float] = None


class PatternFinding(BaseModel):
    pattern_type: str
    status: PatternStatus
    neckline: Optional[float] = None
    breakout_level: Optional[float] = None
    target: Optional[float] = None
    stop: Optional[float] = None
    win_rate: Optional[float] = None
    avg_move_pct: Optional[float] = None
    sample_size: Optional[int] = None
    detected_at: Optional[str] = None


class ChartCapturePayload(BaseModel):
    """Payload sent by browser plugin for chart analysis."""
    image: Optional[str] = Field(None, description="Base64-encoded PNG screenshot")
    source_url: Optional[str] = None
    page_title: Optional[str] = None
    user_symbol: str
    exchange: Exchange = "NSE"
    timeframe: Timeframe = "5m"
    visible_indicators: list[str] = Field(default_factory=list)
    user_question: str
    pg_evidence: Optional[dict] = None
    conflict_policy: ConflictPolicy = "prefer_pg"

    @field_validator("timeframe", mode="before")
    @classmethod
    def normalise_timeframe(cls, v: object) -> object:
        """Accept raw TradingView timeframe codes (e.g. '1', '60', 'D')."""
        if isinstance(v, str):
            return _TV_TF_MAP.get(v.strip(), v)
        return v


class EvidenceTrail(BaseModel):
    source: str
    as_of: str
    pg_levels_used: bool = False
    screenshot_used: bool = False
    pattern_engine_used: bool = False


class AnalysisResult(BaseModel):
    capture_id: str
    symbol: str
    exchange: Exchange
    timeframe: Timeframe
    answer: str
    key_levels: KeyLevels = Field(default_factory=KeyLevels)
    pattern_findings: list[PatternFinding] = Field(default_factory=list)
    evidence_trail: EvidenceTrail
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None


class FollowUpRequest(BaseModel):
    capture_id: str
    question: str


class TalkChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    watchlist: list[str] = Field(default_factory=list)
    mode: Literal["permissive", "strict"] = "permissive"


class TalkEvidenceItem(BaseModel):
    label: str
    value: Any = None
    source: str
    as_of: Optional[str] = None
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"


class TalkAction(BaseModel):
    label: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TalkChatResponse(BaseModel):
    session_id: str
    intent: str
    answer: str
    symbols: list[str] = Field(default_factory=list)
    comparison: list[dict[str, Any]] = Field(default_factory=list)
    screener_results: list[dict[str, Any]] = Field(default_factory=list)
    market_context: list[dict[str, Any]] = Field(default_factory=list)
    intraday_context: dict[str, Any] = Field(default_factory=dict)
    evidence: list[TalkEvidenceItem] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next_actions: list[TalkAction] = Field(default_factory=list)
    model_route: dict[str, Any] = Field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class TalkCompareRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=2, max_length=10)
    question: str = ""
    mode: Literal["permissive", "strict"] = "permissive"


class TalkScreenerRequest(BaseModel):
    screen_type: str = Field(..., min_length=1)
    top_n: int = Field(default=10, ge=1, le=30)
    symbols: list[str] = Field(default_factory=list)
    question: str = ""
    mode: Literal["permissive", "strict"] = "permissive"
