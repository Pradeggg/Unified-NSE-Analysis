"""Alias source for hybrid symbol resolution.

This module owns the *neutral* alias map used to seed
``market.symbol_aliases`` and to drive the dict-tier of the hybrid resolver.

Design notes (AA-HSR-2)
-----------------------

* The module must not import :mod:`terminal.tools` — that creates a circular
  dependency once :mod:`terminal.tools.resolve_symbol` is rewritten in AA-HSR-4
  to call into ``terminal.symbol_search``. Constants that previously lived in
  ``terminal.tools`` (``_FO_INDEX_ALIASES``, ``_COMMON_STOCK_ALIASES``,
  ``_GENERIC_NAME_TOKENS``) are duplicated here. They remain the source of
  truth for resolver code; ``terminal.tools`` keeps its own copies until
  AA-HSR-4 collapses both onto this module.
* Postgres access goes through :mod:`terminal.postgres_tools`, which is the
  neutral DSN helper. We never reach into ``terminal.tools._pg_fetchall``.
* The module degrades gracefully:  if Postgres is unreachable we still emit
  the manual / index / sector-hint aliases so downstream tests can run
  without a live database.

Public surface
--------------

``KIND_WEIGHTS``        — alias-kind → weight mapping (per backlog AA-HSR-2).
``AliasRecord``         — one row of ``market.symbol_aliases``.
``classify_alias()``    — heuristic that picks one of the six ``kind`` values.
``iter_aliases()``      — yields :class:`AliasRecord` from all configured
                          sources (manual aliases, F&O index aliases, sector
                          hints, Postgres ``ref.instruments`` /
                          ``scores.mv_latest_snapshot``).
``build_alias_map()``   — dict view ``{normalized_name: symbol}`` used by the
                          dict-tier of the resolver.
``alias_summary()``     — quick counts grouped by ``kind`` / ``source``,
                          used by the seed script and by emptiness checks.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, Iterator

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Weights — locked by AA-HSR-2 acceptance criteria.
# ---------------------------------------------------------------------------

KIND_WEIGHTS: dict[str, float] = {
    "official":    1.0,
    "symbol":      0.9,
    "short":       0.7,
    "alias":       0.6,
    "sector_hint": 0.5,
    "manual":      0.9,
}

VALID_KINDS: frozenset[str] = frozenset(KIND_WEIGHTS)


# ---------------------------------------------------------------------------
# Index-level F&O aliases (mirrors terminal.tools._FO_INDEX_ALIASES).
# Kept here so the resolver can seed without touching terminal.tools.
# ---------------------------------------------------------------------------

_FO_INDEX_ALIASES: dict[str, str] = {
    "NIFTY MIDCAP":             "MIDCPNIFTY",
    "NIFTY MIDCAP 50":          "MIDCPNIFTY",
    "NIFTY MIDCAP SELECT":      "MIDCPNIFTY",
    "NIFTY MIDCAP100":          "MIDCPNIFTY",
    "NIFTY MIDCAP 100":         "MIDCPNIFTY",
    "MIDCAP NIFTY":             "MIDCPNIFTY",
    "MIDCPNIFTY":               "MIDCPNIFTY",
    "NIFTY BANK":               "BANKNIFTY",
    "BANK NIFTY":               "BANKNIFTY",
    "BANKNIFTY":                "BANKNIFTY",
    "NIFTY FINANCIAL":          "FINNIFTY",
    "NIFTY FINANCIAL SERVICES": "FINNIFTY",
    "NIFTY FIN":                "FINNIFTY",
    "FINNIFTY":                 "FINNIFTY",
    "NIFTY":                    "NIFTY",
    "NIFTY 50":                 "NIFTY",
    "NIFTY50":                  "NIFTY",
    "NIFTY NEXT 50":            "NIFTYNXT50",
    "NIFTY NXT 50":             "NIFTYNXT50",
    "NIFTYNXT50":               "NIFTYNXT50",
}

_MANUAL_STOCK_ALIASES: dict[str, str] = {
    "BAJAJ FINANCE":                  "BAJFINANCE",
    "BAJAJ FIN":                      "BAJFINANCE",
    "BAJAJ FINSERV":                  "BAJAJFINSV",
    "HDFC BANK":                      "HDFCBANK",
    "ICICI BANK":                     "ICICIBANK",
    "KOTAK BANK":                     "KOTAKBANK",
    "TATA STEEL":                     "TATASTEEL",
    "TATA MOTORS":                    "TATAMOTORS",
    "TATA TECHNOLOGIES":              "TATATECH",
    "TATA TECHNOLOGIES LIMITED":      "TATATECH",
    "USL":                            "UNITDSPR",
    "UNITED SPIRITS":                 "UNITDSPR",
    "UNITED SPIRITS LIMITED":         "UNITDSPR",
    "DIAGEO INDIA":                   "UNITDSPR",
    "BHARAT PETROLEUM":               "BPCL",
    "BHARAT PETROLEUM CORPORATION":   "BPCL",
    "MAHINDRA AND MAHINDRA":          "M&M",
    "MAHINDRA & MAHINDRA":            "M&M",
    "HINDUSTAN LEVER":                "HINDUNILVR",
    "HUL":                            "HINDUNILVR",
    "HINDUSTAN UNILEVER":             "HINDUNILVR",
    "STATE BANK OF INDIA":            "SBIN",
    "STATE BANK":                     "SBIN",
    "ASIAN PAINTS":                   "ASIANPAINT",
    "POWER GRID":                     "POWERGRID",
    "POWER GRID CORPORATION":         "POWERGRID",
    "ADANI PORTS":                    "ADANIPORTS",
    "ADANI ENTERPRISES":              "ADANIENT",
    "RELIANCE INDUSTRIES":            "RELIANCE",
    "TATA CONSULTANCY":               "TCS",
    "TATA CONSULTANCY SERVICES":      "TCS",
    "TATA INVESTMENT":                "TATAINVEST",
    "TATA INVESTMENT CORPORATION":    "TATAINVEST",
    "BHARAT FORGE":                   "BHARATFORG",
    "MARUTI SUZUKI":                  "MARUTI",
    "SUN PHARMA":                     "SUNPHARMA",
    "SBI":                            "SBIN",
    "STATE BANK OF INDIA":            "SBIN",
    "DR REDDY":                       "DRREDDY",
    "DR REDDYS":                      "DRREDDY",
    "DIXON TECH":                     "DIXON",
    "DIXON TECHNOLOGIES":             "DIXON",
    "LARSEN AND TOUBRO":              "LT",
    "LARSEN & TOUBRO":                "LT",
    "PREMIER ENERGIES":               "PREMIERENE",
    "HINDUSTAN AERONAUTICS":          "HAL",
    "BAJAJ AUTO":                     "BAJAJ-AUTO",
    "CHENNPETRO":                     "CHENNPETRO",
    "CHENNAI PETROLEUM":              "CHENNPETRO",
    "CHENNAI PETROLEUM CORPORATION":  "CHENNPETRO",
    "CHENNAI PETROLEUM CORPORATION LIMITED": "CHENNPETRO",
    "CPCL":                           "CHENNPETRO",
}


# Generic business / industry words that must never become single-token aliases
# on their own — they collide across dozens of issuers.
_GENERIC_NAME_TOKENS: frozenset[str] = frozenset({
    "AUTO", "BANK", "BHARAT", "CEMENT", "COAL", "COMPANIES", "COMPANY",
    "CORP", "CORPORATION", "ELECTRIC", "ELECTRICALS", "ELECTRONICS",
    "ENERGIES", "ENERGY", "ENTERPRISE", "ENTERPRISES", "FINANCE",
    "FINANCIAL", "FINSERV", "FOODS", "GAS", "GLOBAL", "GROUP", "GROWTH",
    "HINDUSTAN", "HOLDING", "HOLDINGS", "HOTEL", "HOTELS", "INC", "INDIA",
    "INDIAN", "INDUSTRIES", "INDUSTRY", "INFRA", "INFRASTRUCTURE",
    "INTERNATIONAL", "INVEST", "INVESTMENT", "INVESTMENTS", "LEVER",
    "LIMITED", "LTD", "MANUFACTURING", "MOTOR", "MOTORS", "NATIONAL",
    "NETWORK", "NETWORKS", "PHARMA", "PHARMACEUTICALS", "POWER",
    "PRIVATE", "PRODUCTS", "PROJECTS", "PUBLIC", "SERVICES", "SOLUTIONS",
    "STEEL", "SYSTEMS", "TECH", "TECHNOLOGIES", "TECHNOLOGY",
})


# Sector-hint aliases — single keywords that should not be auto-resolved but
# are sometimes typed as if they were symbols. We seed them at very low
# weight so the trigram retriever can still surface a sector index when the
# query is unambiguous (e.g. "auto sector").
_SECTOR_HINTS: dict[str, str] = {
    "BANK SECTOR":  "BANKNIFTY",
    "AUTO SECTOR":  "NIFTYAUTO",
    "IT SECTOR":    "NIFTYIT",
    "PHARMA SECTOR": "NIFTYPHARMA",
    "FMCG SECTOR":  "NIFTYFMCG",
    "METAL SECTOR": "NIFTYMETAL",
    "PSU BANK SECTOR": "NIFTYPSUBANK",
}


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AliasRecord:
    """One row destined for ``market.symbol_aliases``.

    ``weight`` is denormalised from ``KIND_WEIGHTS[kind]`` so the seed script
    can write a flat table without re-deriving it. ``source`` is the
    high-level origin (``manual``, ``fo_index``, ``sector_hint``,
    ``ref_instruments``, ``mv_latest_snapshot``) — useful for auditing.
    """

    symbol: str
    name:   str
    kind:   str
    weight: float
    source: str

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be non-empty")
        if not self.name:
            raise ValueError("name must be non-empty")
        if self.kind not in VALID_KINDS:
            raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}, got {self.kind!r}")
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(f"weight must be in [0, 1], got {self.weight!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_LOOKUP_RE = re.compile(r"[^A-Z0-9]+")


def _norm_key(value: str) -> str:
    """Lower-case-insensitive, punctuation-stripped lookup key."""
    return _LOOKUP_RE.sub("", str(value or "").upper())


def classify_alias(name: str, symbol: str) -> str:
    """Pick a ``kind`` for a (name, symbol) pair.

    Rules:
      * exact normalized match → ``symbol``
      * 3+ tokens              → ``official``
      * exactly 2 tokens       → ``short``
      * everything else        → ``alias``
    """
    if _norm_key(name) == _norm_key(symbol):
        return "symbol"
    tokens = re.findall(r"[A-Za-z0-9&]+", str(name))
    if len(tokens) >= 3:
        return "official"
    if len(tokens) == 2:
        return "short"
    return "alias"


# ---------------------------------------------------------------------------
# Source readers
# ---------------------------------------------------------------------------


def _emit_manual() -> Iterator[AliasRecord]:
    """Manually curated aliases from ``_MANUAL_STOCK_ALIASES``.

    These are highest-priority hand-curated disambiguations and always carry
    the ``manual`` kind (weight 0.9) regardless of token count.
    """
    seen: set[tuple[str, str]] = set()
    for name, sym in _MANUAL_STOCK_ALIASES.items():
        key = (sym, name)
        if key in seen:
            continue
        seen.add(key)
        yield AliasRecord(
            symbol=sym, name=name, kind="manual",
            weight=KIND_WEIGHTS["manual"], source="manual",
        )


def _emit_fo_indices() -> Iterator[AliasRecord]:
    """F&O index aliases. ``MIDCPNIFTY`` itself is ``symbol``; the human
    expansions ("NIFTY MIDCAP SELECT") are ``official``."""
    for name, sym in _FO_INDEX_ALIASES.items():
        yield AliasRecord(
            symbol=sym, name=name,
            kind=classify_alias(name, sym),
            weight=KIND_WEIGHTS[classify_alias(name, sym)],
            source="fo_index",
        )


def _emit_sector_hints() -> Iterator[AliasRecord]:
    for name, sym in _SECTOR_HINTS.items():
        yield AliasRecord(
            symbol=sym, name=name, kind="sector_hint",
            weight=KIND_WEIGHTS["sector_hint"], source="sector_hint",
        )


def _emit_postgres_instruments() -> Iterator[AliasRecord]:
    """Yield aliases from ``ref.instruments`` / ``scores.mv_latest_snapshot``.

    Gracefully returns an empty iterator if Postgres is unavailable or the
    expected tables are missing — the seed script handles emptiness checks.
    """
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:                                  # pragma: no cover
        log.info("psycopg2 unavailable; skipping pg alias source: %s", exc)
        return

    from terminal import postgres_tools as pg

    sql = """
        SELECT symbol, company_name, 'ref_instruments'        AS source
        FROM   ref.instruments
        WHERE  symbol IS NOT NULL
        UNION ALL
        SELECT symbol, company_name, 'mv_latest_snapshot'     AS source
        FROM   scores.mv_latest_snapshot
        WHERE  symbol IS NOT NULL
    """

    try:
        conn = pg._connect()
    except Exception as exc:
        log.info("pg connect failed; skipping pg alias source: %s", exc)
        return

    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    except Exception as exc:
        log.info("pg alias query failed; skipping pg alias source: %s", exc)
        return
    finally:
        try:
            conn.close()
        except Exception:
            pass

    seen_symbol: set[str] = set()
    seen_name:   set[tuple[str, str]] = set()
    for sym, name, source in rows:
        if not sym:
            continue
        sym_u = str(sym).upper().strip()
        if not sym_u:
            continue
        if sym_u not in seen_symbol:
            seen_symbol.add(sym_u)
            yield AliasRecord(
                symbol=sym_u, name=sym_u, kind="symbol",
                weight=KIND_WEIGHTS["symbol"], source=source,
            )
        if name:
            name_u = str(name).upper().strip()
            key = (sym_u, name_u)
            if name_u and key not in seen_name:
                seen_name.add(key)
                kind = classify_alias(name_u, sym_u)
                yield AliasRecord(
                    symbol=sym_u, name=name_u, kind=kind,
                    weight=KIND_WEIGHTS[kind], source=source,
                )


# ---------------------------------------------------------------------------
# Public iteration
# ---------------------------------------------------------------------------


def iter_aliases(*, include_pg: bool = True) -> Iterator[AliasRecord]:
    """Yield deduplicated :class:`AliasRecord` rows from every configured source.

    Dedup key is ``(symbol, name, kind)`` — matches the
    ``market.symbol_aliases`` primary key from the AA-HSR-3 migration.
    Sources are emitted in priority order: ``manual`` first, then ``fo_index``,
    ``sector_hint``, finally Postgres. Earlier sources win on dedup, so a
    manually-curated entry will not be overwritten by a lower-quality auto
    entry within the same (symbol, name, kind) cell.
    """
    seen: set[tuple[str, str, str]] = set()
    sources: list[Iterable[AliasRecord]] = [
        _emit_manual(),
        _emit_fo_indices(),
        _emit_sector_hints(),
    ]
    if include_pg:
        sources.append(_emit_postgres_instruments())

    for source in sources:
        for record in source:
            key = (record.symbol, record.name, record.kind)
            if key in seen:
                continue
            seen.add(key)
            # Reject single-token "names" that match a generic business word
            # — these would otherwise collide across dozens of issuers.
            if record.kind in {"alias", "short"} and _norm_key(record.name) in {
                _norm_key(tok) for tok in _GENERIC_NAME_TOKENS
            }:
                continue
            yield record


def build_alias_map(*, include_pg: bool = True) -> dict[str, str]:
    """``{normalized_name: symbol}`` view used by the dict tier."""
    out: dict[str, str] = {}
    for record in iter_aliases(include_pg=include_pg):
        key = _norm_key(record.name)
        if key:
            out.setdefault(key, record.symbol)
    return out


def alias_summary(records: Iterable[AliasRecord] | None = None) -> dict[str, dict[str, int]]:
    """Summary used by the seed script for the post-load report.

    Shape: ``{"total": N, "by_kind": {kind: count}, "by_source": {source: count}}``.
    """
    if records is None:
        records = list(iter_aliases())
    by_kind:   dict[str, int] = {}
    by_source: dict[str, int] = {}
    total = 0
    for record in records:
        total += 1
        by_kind[record.kind] = by_kind.get(record.kind, 0) + 1
        by_source[record.source] = by_source.get(record.source, 0) + 1
    return {"total": total, "by_kind": by_kind, "by_source": by_source}
