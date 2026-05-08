"""
terminal/monitor.py — Background alert monitoring engine for Agent Adda.

Runs persistent daemon threads that scan NSE stocks every N minutes
for technical signals and emit alerts to a thread-safe queue.

Strategies
──────────
• breakout      — EMA crossover + volume confirmation (15m candles)
• volume_surge  — Volume > 2× 20-bar average with price move > 0.5%
• reversal      — RSI divergence or extreme oversold/overbought + price turn
• momentum      — MACD crossover + RSI in momentum zone (40–70 BUY, 30–60 SELL)
• supertrend    — Supertrend state flip (bull → bear or bear → bull)
• vcp           — VCP contraction pattern detected
• all           — All strategies combined

Usage in chat
─────────────
  /monitor start [strategy] [index]   — activate a monitor
  /monitor stop [strategy|all]        — deactivate
  /monitor status                     — show active monitors + last alert times
  /monitor list                       — show available strategies
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ── Alert dataclass ────────────────────────────────────────────────────────────

@dataclass
class Alert:
    strategy:    str
    symbol:      str
    direction:   str        # BUY | SELL | WATCH
    signal:      str        # human-readable signal name
    entry:       float | None = None
    target:      float | None = None
    stoploss:    float | None = None
    rr:          float | None = None
    confidence:  str = "medium"   # low | medium | high
    note:        str = ""
    as_of:       str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    index:       str = "NIFTY 500"

    @property
    def emoji(self) -> str:
        return "🟢" if self.direction == "BUY" else ("🔴" if self.direction == "SELL" else "🟡")

    @property
    def confidence_bar(self) -> str:
        return {"low": "▪▫▫", "medium": "▪▪▫", "high": "▪▪▪"}.get(self.confidence, "▪▫▫")


# ── Strategy definitions ───────────────────────────────────────────────────────

STRATEGIES = {
    "breakout": {
        "description": "EMA 9/21 crossover + volume ≥ 1.5× average → price breakout",
        "interval":    "15m",
        "yf_strats":   ["ema", "volume"],
        "min_rr":      1.3,
    },
    "volume_surge": {
        "description": "Volume spike > 2× 20-bar average with price move > 0.5%",
        "interval":    "15m",
        "yf_strats":   ["volume"],
        "min_rr":      1.0,
    },
    "reversal": {
        "description": "RSI extreme (>75 bearish, <30 bullish) + Bollinger mean-reversion",
        "interval":    "15m",
        "yf_strats":   ["rsi", "bollinger"],
        "min_rr":      1.5,
    },
    "momentum": {
        "description": "MACD bullish/bearish crossover + RSI in momentum zone",
        "interval":    "15m",
        "yf_strats":   ["macd", "rsi"],
        "min_rr":      1.3,
    },
    "supertrend": {
        "description": "Supertrend indicator state flip (bullish/bearish change)",
        "interval":    "15m",
        "yf_strats":   ["supertrend"],
        "min_rr":      1.5,
    },
    "vcp": {
        "description": "Volatility Contraction Pattern — tight range with decreasing volume",
        "interval":    "15m",
        "yf_strats":   ["vcp", "volume"],
        "min_rr":      2.0,
    },
    # ── New strategies ────────────────────────────────────────────────────────
    "orb": {
        "description": "Opening Range Breakout — price breaks above/below first-bar range with volume",
        "interval":    "5m",
        "yf_strats":   ["orb", "volume"],
        "min_rr":      1.5,
    },
    "gap_go": {
        "description": "Gap and Go — gap up/down > 0.5% with bullish/bearish continuation + MACD",
        "interval":    "5m",
        "yf_strats":   ["gap"],
        "min_rr":      1.3,
    },
    "vwap": {
        "description": "VWAP Reclaim/Loss — price crossing VWAP proxy (EMA9) with RSI confirmation",
        "interval":    "15m",
        "yf_strats":   ["vwap", "ema"],
        "min_rr":      1.3,
    },
    "engulfing": {
        "description": "Candlestick patterns — bullish/bearish engulfing near key EMA levels",
        "interval":    "15m",
        "yf_strats":   ["engulfing"],
        "min_rr":      1.5,
    },
    "ema_ribbon": {
        "description": "EMA Ribbon — EMA 9/21/50 all stacking in same direction (trend confirmation)",
        "interval":    "15m",
        "yf_strats":   ["ema_ribbon"],
        "min_rr":      1.5,
    },
    "multi_confirm": {
        "description": "Multi-signal confluence — 3 of 4 indicators agree (MACD + EMA + RSI + Volume)",
        "interval":    "15m",
        "yf_strats":   ["multi_confirm"],
        "min_rr":      1.5,
    },
    "rsi_divergence": {
        "description": "RSI Divergence — price and RSI disagree, signalling hidden reversal strength",
        "interval":    "15m",
        "yf_strats":   ["rsi_divergence"],
        "min_rr":      1.8,
    },
    "all": {
        "description": "All strategies: breakout + volume + reversal + momentum + supertrend + VCP "
                       "+ ORB + Gap&Go + VWAP + Engulfing + EMA Ribbon + Multi-confirm + RSI Div",
        "interval":    "15m",
        "yf_strats":   None,    # None = run all
        "min_rr":      1.3,
    },
}

# ── Worker thread ──────────────────────────────────────────────────────────────

class AlertWorker(threading.Thread):
    """Background daemon thread that scans an NSE index every `interval_min` minutes."""

    def __init__(
        self,
        strategy: str,
        alert_queue: queue.Queue,
        index: str = "NIFTY 500",
        interval_min: int = 15,
        top_n: int = 8,
        direction: str = "all",
    ):
        super().__init__(daemon=True, name=f"monitor-{strategy}")
        self.strategy      = strategy
        self.alert_queue   = alert_queue
        self.index         = index
        self.interval_min  = interval_min
        self.top_n         = top_n
        self.direction     = direction
        self._stop_event   = threading.Event()
        self.last_run:  datetime | None = None
        self.last_count: int = 0
        self.run_count:  int = 0
        self.errors:     int = 0

    def stop(self):
        self._stop_event.set()

    @property
    def is_running(self) -> bool:
        return self.is_alive() and not self._stop_event.is_set()

    def _run_scan(self) -> list[Alert]:
        """Execute one scan cycle; returns list of Alert objects."""
        from terminal.tools import scan_intraday_market

        cfg = STRATEGIES.get(self.strategy, STRATEGIES["all"])
        try:
            result = scan_intraday_market(
                index            = self.index,
                interval         = cfg["interval"],
                strategies       = cfg["yf_strats"],
                direction_filter = self.direction if self.direction != "all" else "all",
                min_rr           = cfg["min_rr"],
                top_n            = self.top_n,
            )
        except Exception as e:
            return [Alert(
                strategy   = self.strategy,
                symbol     = "SCAN_ERROR",
                direction  = "WATCH",
                signal     = f"Scan error: {e}",
                confidence = "low",
                index      = self.index,
            )]

        alerts: list[Alert] = []
        for sig in result.get("top_buy", []):
            alerts.append(_sig_to_alert(sig, self.strategy, "BUY", self.index))
        for sig in result.get("top_sell", []):
            alerts.append(_sig_to_alert(sig, self.strategy, "SELL", self.index))

        return alerts

    def run(self):
        # Brief initial delay to let the session warm up
        time.sleep(5)
        while not self._stop_event.is_set():
            try:
                alerts = self._run_scan()
                self.last_run   = datetime.now()
                self.last_count = len(alerts)
                self.run_count += 1
                if alerts:
                    self.alert_queue.put({
                        "type":     "alerts",
                        "strategy": self.strategy,
                        "index":    self.index,
                        "alerts":   alerts,
                        "as_of":    self.last_run.strftime("%H:%M:%S"),
                        "run_n":    self.run_count,
                    })
                else:
                    # Heartbeat so user knows monitor is alive
                    self.alert_queue.put({
                        "type":     "heartbeat",
                        "strategy": self.strategy,
                        "index":    self.index,
                        "as_of":    self.last_run.strftime("%H:%M:%S"),
                        "run_n":    self.run_count,
                    })
            except Exception as e:
                self.errors += 1
                self.alert_queue.put({
                    "type":    "error",
                    "strategy": self.strategy,
                    "message": str(e),
                })
            # Wait for next cycle (check stop event every 30s for responsive shutdown)
            wait_secs = self.interval_min * 60
            for _ in range(wait_secs // 30):
                if self._stop_event.is_set():
                    return
                time.sleep(30)
            remaining = wait_secs % 30
            if remaining and not self._stop_event.is_set():
                time.sleep(remaining)


def _sig_to_alert(sig: dict, strategy: str, direction: str, index: str) -> Alert:
    """Convert a scan_intraday_market signal dict to an Alert."""
    rr   = sig.get("risk_reward") or sig.get("rr")
    conf = "high" if rr and rr >= 2.0 else ("medium" if rr and rr >= 1.5 else "low")
    return Alert(
        strategy   = strategy,
        symbol     = sig.get("symbol", "?"),
        direction  = direction,
        signal     = sig.get("strategy") or sig.get("signal", strategy),
        entry      = sig.get("entry"),
        target     = sig.get("target"),
        stoploss   = sig.get("stoploss"),
        rr         = rr,
        confidence = conf,
        note       = sig.get("note", ""),
        index      = index,
    )


# ── Monitor manager ────────────────────────────────────────────────────────────

class MonitorManager:
    """Manages all background alert workers and the shared alert queue."""

    def __init__(self):
        self.queue:   queue.Queue        = queue.Queue()
        self._workers: dict[str, AlertWorker] = {}  # key = "{strategy}:{index}"

    def _worker_key(self, strategy: str, index: str) -> str:
        return f"{strategy}:{index}"

    def start(
        self,
        strategy: str     = "all",
        index: str        = "NIFTY 500",
        interval_min: int = 15,
        top_n: int        = 8,
        direction: str    = "all",
    ) -> str:
        """Start a background alert worker. Returns status message."""
        strategy = strategy.lower().strip()
        if strategy not in STRATEGIES:
            return (
                f"Unknown strategy '{strategy}'. "
                f"Available: {', '.join(STRATEGIES)}"
            )

        key = self._worker_key(strategy, index)
        if key in self._workers and self._workers[key].is_running:
            return f"⚠️  Monitor '{strategy}' on {index} is already running."

        worker = AlertWorker(
            strategy     = strategy,
            alert_queue  = self.queue,
            index        = index,
            interval_min = interval_min,
            top_n        = top_n,
            direction     = direction,
        )
        worker.start()
        self._workers[key] = worker
        return (
            f"✅ Monitor '{strategy}' started — scanning {index} every {interval_min}m. "
            f"Alerts will appear automatically. Use /monitor stop {strategy} to deactivate."
        )

    def stop(self, strategy: str = "all", index: str | None = None) -> str:
        """Stop a worker. Pass strategy='all' to stop everything."""
        stopped = []
        if strategy == "all":
            for key, w in list(self._workers.items()):
                w.stop()
                stopped.append(key)
        else:
            strategy = strategy.lower().strip()
            for key, w in list(self._workers.items()):
                strat, idx = key.split(":", 1)
                if strat == strategy and (index is None or idx == index):
                    w.stop()
                    stopped.append(key)

        if not stopped:
            return "No matching active monitors found."
        # Clean up stopped workers
        for key in stopped:
            self._workers.pop(key, None)
        return f"⏹ Stopped: {', '.join(stopped)}"

    def status(self) -> list[dict]:
        """Return status for all known workers."""
        out = []
        for key, w in self._workers.items():
            strat, idx = key.split(":", 1)
            out.append({
                "key":        key,
                "strategy":   strat,
                "index":      idx,
                "running":    w.is_running,
                "interval":   f"{w.interval_min}m",
                "last_run":   w.last_run.strftime("%H:%M:%S") if w.last_run else "not yet",
                "last_count": w.last_count,
                "run_count":  w.run_count,
                "errors":     w.errors,
            })
        return out

    def drain_alerts(self, max_items: int = 50) -> list[dict]:
        """Non-blocking drain of queued alert batches. Returns list of event dicts."""
        events = []
        try:
            while len(events) < max_items:
                events.append(self.queue.get_nowait())
        except queue.Empty:
            pass
        return events

    def any_active(self) -> bool:
        return any(w.is_running for w in self._workers.values())


# Module-level singleton
_manager: MonitorManager | None = None


def get_monitor() -> MonitorManager:
    global _manager
    if _manager is None:
        _manager = MonitorManager()
    return _manager
