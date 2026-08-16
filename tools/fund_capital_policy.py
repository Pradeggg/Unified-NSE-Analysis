#!/usr/bin/env python3
"""
Shared Agent Adda capital policy — loader, stop inference, and fresh-mode sizing.

All fund tools should read budgets, slot counts, and risk/sector caps from
``data/fund_capital_policy.yaml`` via this module instead of hardcoding rupees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = ROOT / "data" / "fund_capital_policy.yaml"


@dataclass(frozen=True)
class CapitalPolicy:
    """Rupee and slot limits for the combined SmallCap + MidCap paper portfolio."""

    total_nav: float
    budget_sc: float
    budget_mc: float
    slots_sc: int
    slots_mc: int
    fund_score_min: float
    watch_n: int
    high_conviction_tech: float
    high_conviction_fund: float
    trade_risk_normal: float
    trade_risk_high_conviction: float
    open_risk_cap: float
    min_reward_risk: float
    max_stop_distance_pct: float
    default_stop_pct: float
    sector_cap: float
    single_stock_cap: float
    policy_note: str
    as_of: str

    def slot_budget(self, sleeve: str) -> float:
        """Equal-weight slot budget for a sleeve (``smallcap`` or ``midcap``)."""
        if sleeve == "smallcap":
            return self.budget_sc / self.slots_sc if self.slots_sc else 0.0
        return self.budget_mc / self.slots_mc if self.slots_mc else 0.0

    def sleeve_budget(self, sleeve: str) -> float:
        return self.budget_sc if sleeve == "smallcap" else self.budget_mc

    def sleeve_slots(self, sleeve: str) -> int:
        return self.slots_sc if sleeve == "smallcap" else self.slots_mc


def _default_policy() -> CapitalPolicy:
    """In-code fallback matching the 15 Aug 2026 Rs. 4L working note."""
    return CapitalPolicy(
        total_nav=400_000,
        budget_sc=200_000,
        budget_mc=200_000,
        slots_sc=9,
        slots_mc=15,
        fund_score_min=65,
        watch_n=5,
        high_conviction_tech=73,
        high_conviction_fund=75,
        trade_risk_normal=2_500,
        trade_risk_high_conviction=4_000,
        open_risk_cap=24_000,
        min_reward_risk=2.0,
        max_stop_distance_pct=12.0,
        default_stop_pct=10.0,
        sector_cap=100_000,
        single_stock_cap=40_000,
        policy_note="docs/fund_policies/research_updates/2026-08-15-smallcap-midcap-4l-strategy-review.md",
        as_of="2026-08-15",
    )


def _from_mapping(raw: dict[str, Any]) -> CapitalPolicy:
    nav = raw.get("nav") or {}
    slots = raw.get("slots") or {}
    gates = raw.get("gates") or {}
    risk = raw.get("risk") or {}
    caps = raw.get("caps") or {}
    base = _default_policy()
    return CapitalPolicy(
        total_nav=float(nav.get("total", base.total_nav)),
        budget_sc=float(nav.get("smallcap", base.budget_sc)),
        budget_mc=float(nav.get("midcap", base.budget_mc)),
        slots_sc=int(slots.get("smallcap", base.slots_sc)),
        slots_mc=int(slots.get("midcap", base.slots_mc)),
        fund_score_min=float(gates.get("fund_score_min", base.fund_score_min)),
        watch_n=int(gates.get("watch_n", base.watch_n)),
        high_conviction_tech=float(gates.get("high_conviction_tech", base.high_conviction_tech)),
        high_conviction_fund=float(gates.get("high_conviction_fund", base.high_conviction_fund)),
        trade_risk_normal=float(risk.get("trade_risk_normal", base.trade_risk_normal)),
        trade_risk_high_conviction=float(
            risk.get("trade_risk_high_conviction", base.trade_risk_high_conviction)
        ),
        open_risk_cap=float(risk.get("open_risk_cap", base.open_risk_cap)),
        min_reward_risk=float(risk.get("min_reward_risk", base.min_reward_risk)),
        max_stop_distance_pct=float(risk.get("max_stop_distance_pct", base.max_stop_distance_pct)),
        default_stop_pct=float(risk.get("default_stop_pct", base.default_stop_pct)),
        sector_cap=float(caps.get("sector", base.sector_cap)),
        single_stock_cap=float(caps.get("single_stock", base.single_stock_cap)),
        policy_note=str(raw.get("policy_note") or base.policy_note),
        as_of=str(raw.get("as_of") or base.as_of),
    )


@lru_cache(maxsize=1)
def load_capital_policy(path: str | Path | None = None) -> CapitalPolicy:
    """Load the shared YAML policy, falling back to in-code Rs. 4L defaults."""
    policy_path = Path(path) if path else POLICY_PATH
    if not policy_path.exists():
        return _default_policy()
    try:
        import yaml
    except ImportError:
        return _default_policy()
    with policy_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        return _default_policy()
    return _from_mapping(raw)


def is_high_conviction(row: dict, policy: CapitalPolicy | None = None) -> bool:
    """True when TechScore and FundScore both clear the high-conviction gates."""
    policy = policy or load_capital_policy()
    tech = float(row.get("tech_score") or 0)
    fund = float(row.get("fund_score") or 0)
    return tech >= policy.high_conviction_tech and fund >= policy.high_conviction_fund


def infer_stop(row: dict, policy: CapitalPolicy | None = None) -> tuple[float | None, str]:
    """
    Infer a long-only stop from SMA50, Supertrend, or the default percent.

    The tighter valid level (higher price, still below last) is preferred so
    size is set from setup invalidation, not from a convenient slot budget.
    """
    policy = policy or load_capital_policy()
    price = float(row.get("price") or 0)
    if price <= 0:
        return None, "missing_price"

    candidates: list[tuple[str, float]] = []
    for key, label in (("sma50", "sma50"), ("supertrend_value", "supertrend")):
        raw = row.get(key)
        try:
            level = float(raw) if raw not in (None, "") else 0.0
        except (TypeError, ValueError):
            level = 0.0
        if 0 < level < price:
            candidates.append((label, level))

    if candidates:
        # Tighter stop = smaller distance = higher price below last.
        label, stop = max(candidates, key=lambda item: item[1])
        return round(stop, 2), label

    stop = round(price * (1 - policy.default_stop_pct / 100.0), 2)
    return stop, "default_pct"


@dataclass
class SizedPosition:
    """Result of applying slot, risk, sector, stock, and cash constraints."""

    qty: int
    est_cost: float
    stop: float | None
    stop_source: str
    stop_distance_pct: float
    risk_rs: float
    trade_risk_allowed: float
    sector: str
    binding: str
    skip_reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.qty >= 1 and not self.skip_reason


@dataclass
class ExposureBook:
    """Running combined-portfolio exposure used while filling fresh-mode slots."""

    policy: CapitalPolicy
    budget_sc: float | None = None
    budget_mc: float | None = None
    sector_used: dict[str, float] = field(default_factory=dict)
    stock_used: dict[str, float] = field(default_factory=dict)
    sleeve_spent: dict[str, float] = field(
        default_factory=lambda: {"smallcap": 0.0, "midcap": 0.0}
    )
    open_risk_used: float = 0.0

    def _sleeve_budget(self, sleeve: str) -> float:
        if sleeve == "smallcap":
            return self.budget_sc if self.budget_sc is not None else self.policy.budget_sc
        return self.budget_mc if self.budget_mc is not None else self.policy.budget_mc

    def remaining_cash(self, sleeve: str) -> float:
        return max(0.0, self._sleeve_budget(sleeve) - self.sleeve_spent.get(sleeve, 0.0))

    def remaining_stock(self, symbol: str) -> float:
        return max(0.0, self.policy.single_stock_cap - self.stock_used.get(symbol, 0.0))

    def remaining_sector(self, sector: str) -> float:
        """Uncapped when sector is blank — we cannot enforce an unknown bucket."""
        if not sector:
            return math.inf
        return max(0.0, self.policy.sector_cap - self.sector_used.get(sector, 0.0))

    def remaining_open_risk(self) -> float:
        return max(0.0, self.policy.open_risk_cap - self.open_risk_used)

    def seed(
        self,
        symbol: str,
        cost: float,
        sector: str = "",
        risk_rs: float = 0.0,
        sleeve: str = "midcap",
    ) -> None:
        """Record an already-held position before fresh-mode fill."""
        if cost <= 0:
            return
        self.stock_used[symbol] = self.stock_used.get(symbol, 0.0) + cost
        if sector:
            self.sector_used[sector] = self.sector_used.get(sector, 0.0) + cost
        self.sleeve_spent[sleeve] = self.sleeve_spent.get(sleeve, 0.0) + cost
        self.open_risk_used += max(0.0, risk_rs)

    def commit(self, symbol: str, sized: SizedPosition, sleeve: str) -> None:
        """Add an accepted fresh row to the running book."""
        if not sized.accepted:
            return
        self.seed(symbol, sized.est_cost, sized.sector, sized.risk_rs, sleeve)


def _qty_from_budget(budget: float, price: float) -> int:
    if price <= 0 or not math.isfinite(budget) or budget <= 0:
        return 0
    return int(budget / price)


def size_fresh_row(
    row: dict,
    *,
    alloc_per: float,
    sleeve: str,
    policy: CapitalPolicy | None = None,
    book: ExposureBook | None = None,
) -> SizedPosition:
    """
    Size one fresh-mode row as the minimum of slot, risk, stock, sector, and cash.

    MidCap rows always get a stop and a rupee risk figure. SmallCap uses the
    same formula so both sleeves share one capital policy.
    """
    policy = policy or load_capital_policy()
    book = book or ExposureBook(policy)
    price = float(row.get("price") or 0)
    symbol = str(row.get("symbol") or "")
    sector = str(row.get("sector") or "").strip()

    empty = SizedPosition(
        qty=0, est_cost=0.0, stop=None, stop_source="", stop_distance_pct=0.0,
        risk_rs=0.0, trade_risk_allowed=0.0, sector=sector, binding="slot",
    )

    if price <= 0:
        return SizedPosition(**{**empty.__dict__, "skip_reason": "missing price", "binding": "price"})

    stop, stop_source = infer_stop(row, policy)
    if stop is None or stop <= 0 or stop >= price:
        return SizedPosition(
            **{**empty.__dict__, "stop": stop, "stop_source": stop_source,
               "skip_reason": "invalid stop", "binding": "risk"}
        )

    stop_dist = price - stop
    stop_pct = (stop_dist / price) * 100.0
    if stop_pct > policy.max_stop_distance_pct:
        return SizedPosition(
            qty=0, est_cost=0.0, stop=stop, stop_source=stop_source,
            stop_distance_pct=round(stop_pct, 2), risk_rs=0.0,
            trade_risk_allowed=0.0, sector=sector, binding="risk",
            skip_reason=(
                f"stop {stop_pct:.1f}% via {stop_source} wider than "
                f"{policy.max_stop_distance_pct:.0f}%"
            ),
        )

    allowed_risk = (
        policy.trade_risk_high_conviction
        if is_high_conviction(row, policy)
        else policy.trade_risk_normal
    )
    allowed_risk = min(allowed_risk, book.remaining_open_risk())
    if allowed_risk <= 0:
        return SizedPosition(
            qty=0, est_cost=0.0, stop=stop, stop_source=stop_source,
            stop_distance_pct=round(stop_pct, 2), risk_rs=0.0,
            trade_risk_allowed=0.0, sector=sector, binding="open_risk",
            skip_reason="open-risk cap full",
        )

    limits = {
        "slot": _qty_from_budget(alloc_per, price),
        "risk": _qty_from_budget(allowed_risk, stop_dist),
        "stock": _qty_from_budget(book.remaining_stock(symbol), price),
        "cash": _qty_from_budget(book.remaining_cash(sleeve), price),
    }
    # Blank sector is not pooled into an "Unknown" bucket.
    if sector:
        limits["sector"] = _qty_from_budget(book.remaining_sector(sector), price)
    binding = min(limits, key=lambda key: (limits[key], key))
    qty = limits[binding]

    if qty < 1:
        reasons = {
            "slot": f"price ₹{price:,.2f} exceeds slot ₹{alloc_per:,.0f}",
            "risk": (
                f"risk qty 0 at ₹{allowed_risk:,.0f} risk / "
                f"₹{stop_dist:,.2f} stop distance"
            ),
            "stock": f"single-stock cap ₹{policy.single_stock_cap:,.0f} exhausted",
            "cash": "sleeve cash exhausted",
            "sector": f"sector cap ₹{policy.sector_cap:,.0f} exhausted ({sector})",
        }
        return SizedPosition(
            qty=0, est_cost=0.0, stop=stop, stop_source=stop_source,
            stop_distance_pct=round(stop_pct, 2), risk_rs=0.0,
            trade_risk_allowed=allowed_risk, sector=sector, binding=binding,
            skip_reason=reasons[binding],
        )

    est_cost = round(qty * price, 2)
    risk_rs = round(qty * stop_dist, 2)
    return SizedPosition(
        qty=qty,
        est_cost=est_cost,
        stop=stop,
        stop_source=stop_source,
        stop_distance_pct=round(stop_pct, 2),
        risk_rs=risk_rs,
        trade_risk_allowed=allowed_risk,
        sector=sector,
        binding=binding,
    )


def apply_size_to_row(
    row: dict,
    sized: SizedPosition,
    alloc_per: float,
) -> dict:
    """Copy sizing fields onto a fresh-mode row dict."""
    price = float(row.get("price") or 0)
    shortfall = round(alloc_per - sized.est_cost, 2) if sized.qty else round(alloc_per, 2)
    return {
        **row,
        "_fresh_qty": sized.qty,
        "_fresh_est_cost": sized.est_cost,
        "_fresh_shortfall": shortfall,
        "_fresh_stop": sized.stop,
        "_fresh_stop_source": sized.stop_source,
        "_fresh_stop_pct": sized.stop_distance_pct,
        "_fresh_risk_rs": sized.risk_rs,
        "_fresh_binding": sized.binding,
        "_fresh_sector": sized.sector,
        "_fresh_skip_reason": sized.skip_reason,
        "sector": sized.sector or row.get("sector") or "",
        "price": price,
    }
