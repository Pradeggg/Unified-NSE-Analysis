"""NSE cash-market session awareness for Agent Adda.

The regular equity/capital-market session is modeled in IST:
- pre-open awareness starts at 09:00
- regular trading opens at 09:15
- regular trading closes at 15:30

Holiday seed data covers NSE Capital Market Segment 2026 circulars:
- NSE/CMTR/71775, dated 12 Dec 2025
- NSE/CMTR/72260, dated 12 Jan 2026, adding 15 Jan 2026
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
PRE_OPEN_START = time(9, 0)
REGULAR_OPEN = time(9, 15)
REGULAR_CLOSE = time(15, 30)

NSE_CAPITAL_MARKET_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 15): "Municipal Corporation Election in Maharashtra",
    date(2026, 1, 26): "Republic Day",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 26): "Shri Ram Navami",
    date(2026, 3, 31): "Shri Mahavir Jayanti",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 28): "Bakri Id",
    date(2026, 6, 26): "Muharram",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 10): "Diwali-Balipratipada",
    date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev",
    date(2026, 12, 25): "Christmas",
}


@dataclass(frozen=True)
class MarketSessionStatus:
    now_ist: datetime
    is_trading_day: bool
    is_open: bool
    phase: str
    reason: str
    open_at: datetime | None
    close_at: datetime | None
    next_open_at: datetime

    @property
    def clock_label(self) -> str:
        return format_session_clock(self.now_ist)

    @property
    def status_label(self) -> str:
        state = "OPEN" if self.is_open else "CLOSED"
        next_open = format_session_clock(self.next_open_at)
        if self.is_open:
            close_label = self.close_at.strftime("%H:%M IST") if self.close_at else "15:30 IST"
            return f"NSE equity market is {state} ({self.reason}); closes at {close_label}."
        return f"NSE equity market is {state} ({self.reason}). Next open: {next_open}."

    @property
    def compact_label(self) -> str:
        if self.is_open:
            close_label = self.close_at.strftime("%H:%M") if self.close_at else "15:30"
            return f"NSE: OPEN until {close_label}"
        if self.phase == "pre_market":
            return "NSE: CLOSED, opens 09:15"
        if self.phase == "pre_open":
            return "NSE: PRE-OPEN, regular 09:15"
        return f"NSE: CLOSED, next {self.next_open_at.strftime('%a %H:%M')}"


def _as_ist(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(IST)
    if now.tzinfo is None:
        return now.replace(tzinfo=IST)
    return now.astimezone(IST)


def format_session_clock(now: datetime | None = None) -> str:
    return _as_ist(now).strftime("%a, %d %b %Y %H:%M:%S IST")


def _combine(day: date, value: time) -> datetime:
    return datetime.combine(day, value, tzinfo=IST)


def is_nse_trading_day(day: date, holidays: dict[date, str] | None = None) -> bool:
    holiday_map = holidays if holidays is not None else NSE_CAPITAL_MARKET_HOLIDAYS_2026
    return day.weekday() < 5 and day not in holiday_map


def _next_open_after(now_ist: datetime, holidays: dict[date, str]) -> datetime:
    candidate = now_ist.date()
    for _ in range(370):
        open_at = _combine(candidate, REGULAR_OPEN)
        if is_nse_trading_day(candidate, holidays) and open_at > now_ist:
            return open_at
        candidate += timedelta(days=1)
    raise RuntimeError("Unable to find next NSE open within 370 days")


def market_session_status(
    now: datetime | None = None,
    holidays: dict[date, str] | None = None,
) -> MarketSessionStatus:
    holiday_map = holidays if holidays is not None else NSE_CAPITAL_MARKET_HOLIDAYS_2026
    now_ist = _as_ist(now)
    today = now_ist.date()
    current_time = now_ist.time()
    open_at = _combine(today, REGULAR_OPEN)
    close_at = _combine(today, REGULAR_CLOSE)

    if today in holiday_map:
        phase = "closed_holiday"
        reason = f"trading holiday: {holiday_map[today]}"
        is_trading_day = False
        is_open = False
    elif today.weekday() >= 5:
        phase = "closed_weekend"
        reason = "weekend"
        is_trading_day = False
        is_open = False
    elif current_time < PRE_OPEN_START:
        phase = "pre_market"
        reason = "before pre-open; regular session is 09:15-15:30 IST"
        is_trading_day = True
        is_open = False
    elif current_time < REGULAR_OPEN:
        phase = "pre_open"
        reason = "pre-open window; regular session is 09:15-15:30 IST"
        is_trading_day = True
        is_open = False
    elif current_time <= REGULAR_CLOSE:
        phase = "open"
        reason = "regular session"
        is_trading_day = True
        is_open = True
    else:
        phase = "post_close"
        reason = "after close; regular session is 09:15-15:30 IST"
        is_trading_day = True
        is_open = False

    next_open = open_at if is_trading_day and now_ist < open_at else _next_open_after(now_ist, holiday_map)
    return MarketSessionStatus(
        now_ist=now_ist,
        is_trading_day=is_trading_day,
        is_open=is_open,
        phase=phase,
        reason=reason,
        open_at=open_at if is_trading_day else None,
        close_at=close_at if is_trading_day else None,
        next_open_at=next_open,
    )


def market_context_for_agent(now: datetime | None = None) -> str:
    status = market_session_status(now)
    trading_day = "trading day" if status.is_trading_day else "non-trading day"
    guardrail = (
        "Live NSE data may be used for current intraday context."
        if status.is_open
        else "Market is closed; do not imply live market movement. Use EOD/latest available data, label stale or fallback data clearly, and state the next open time."
    )
    return (
        f"NSE market clock: {status.clock_label}. "
        f"{status.status_label} Today is a {trading_day}. "
        f"Regular equity session: 09:15-15:30 IST; pre-open awareness starts 09:00 IST. "
        f"{guardrail}"
    )
