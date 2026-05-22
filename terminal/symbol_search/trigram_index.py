"""Tier-1 trigram retriever (AA-HSR-3).

Issues a parameterised ``pg_trgm`` similarity query against
``market.symbol_aliases`` and returns ranked candidates. Degrades gracefully
to an empty list (no exceptions raised to callers) when:

* ``psycopg2`` is not importable
* ``terminal.postgres_tools._connect()`` raises (PG unavailable)
* the ``pg_trgm`` extension is missing (``UndefinedFunction``)
* the ``market.symbol_aliases`` table is missing or empty

The dict tier of the resolver (AA-HSR-1 / AA-HSR-4) is responsible for the
non-PG fallback path. This module never raises on the happy path; it logs at
``info`` level and returns ``[]``.

Query design notes
------------------

* The query computes a raw trigram similarity (``similarity(lower(name), :q)``)
  in a CTE and a weighted score (``raw * weight``) in the outer select.
* Ordering — locked by the AA-HSR-3 acceptance criteria — is::

      ORDER BY weighted_score DESC, raw_score DESC, kind ASC, symbol ASC

  ``kind`` and ``symbol`` are deterministic tiebreakers so result order is
  stable across processes and connection pools.
* The ``raw_score >= :min_raw`` filter rejects mid-word coincidences (the
  source of the GNA bug — ``similarity("intradaysignals", "gna") ~ 0.15``).
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from .schema import ResolveCandidate

log = logging.getLogger(__name__)


SIMILARITY_THRESHOLD: float = 0.30          # used by % operator in pg_trgm
MID_WORD_REJECT_BELOW: float = 0.25         # post-filter floor on raw similarity
DEFAULT_TOP_N: int = 10


_QUERY_SQL = """
WITH scored AS (
    SELECT symbol,
           name,
           kind,
           weight,
           similarity(lower(name), lower(%(q)s)) AS raw_score
    FROM   market.symbol_aliases
    WHERE  lower(name) %% lower(%(q)s)
)
SELECT symbol,
       name,
       kind,
       weight,
       raw_score,
       (raw_score * weight) AS weighted_score
FROM   scored
WHERE  raw_score >= %(min_raw)s
ORDER  BY weighted_score DESC,
          raw_score      DESC,
          kind           ASC,
          symbol         ASC
LIMIT  %(limit)s
"""


# ---------------------------------------------------------------------------
# Connection helpers (kept private to ease test patching).
# ---------------------------------------------------------------------------


@contextmanager
def _open_connection() -> Iterator[object | None]:
    """Yield a psycopg2 connection or ``None`` if unavailable.

    Never raises — degraded path is ``yield None``.
    """
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:                                  # pragma: no cover
        log.info("psycopg2 unavailable; trigram retriever disabled: %s", exc)
        yield None
        return

    try:
        from terminal import postgres_tools as pg
        conn = pg._connect()
    except Exception as exc:
        log.info("postgres unavailable; trigram retriever disabled: %s", exc)
        yield None
        return

    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _is_recoverable_pg_error(exc: BaseException) -> bool:
    """Identify errors that map to "graceful degrade" — missing extension /
    missing table / empty table — versus real bugs that should bubble up.

    psycopg2 raises ``UndefinedFunction`` (pg_trgm missing) or
    ``UndefinedTable`` (market.symbol_aliases missing) for the degrade case.
    We match on the SQLSTATE in ``pgcode`` to avoid depending on the exact
    psycopg2 class name across versions.
    """
    pgcode = getattr(exc, "pgcode", None)
    # 42883 undefined_function, 42P01 undefined_table, 42704 undefined_object
    return pgcode in {"42883", "42P01", "42704"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def lookup(
    query: str,
    *,
    top_n: int = DEFAULT_TOP_N,
    min_raw: float = MID_WORD_REJECT_BELOW,
) -> list[ResolveCandidate]:
    """Return ranked trigram candidates for ``query``.

    Returns ``[]`` on any of: empty query, PG unavailable, extension missing,
    table missing, table empty, or any other recoverable error.
    """
    if not query or not str(query).strip():
        return []
    if top_n <= 0:
        return []

    with _open_connection() as conn:
        if conn is None:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    _QUERY_SQL,
                    {"q": query, "min_raw": float(min_raw), "limit": int(top_n)},
                )
                rows = cur.fetchall()
        except Exception as exc:
            if _is_recoverable_pg_error(exc):
                log.info(
                    "trigram lookup degraded for %r (pgcode=%s)",
                    query, getattr(exc, "pgcode", None),
                )
                return []
            log.warning("trigram lookup failed for %r: %s", query, exc)
            return []

    if not rows:
        return []

    by_symbol: dict[str, ResolveCandidate] = {}
    for symbol, name, _kind, _weight, raw_score, weighted_score in rows:
        sym_u = str(symbol).upper()
        raw_f = float(raw_score)
        weighted_f = float(weighted_score)
        cand = ResolveCandidate(
            symbol=sym_u,
            score=min(1.0, max(0.0, weighted_f)),
            raw_score=raw_f,
            methods=("trigram",),
            matched=str(name) or sym_u,
        )
        # The query is already ordered; dedupe on symbol, keeping first (best).
        if sym_u not in by_symbol:
            by_symbol[sym_u] = cand

    return list(by_symbol.values())


def benchmark(queries: list[str], *, top_n: int = DEFAULT_TOP_N) -> dict[str, float]:
    """Tiny benchmark helper used by AA-HSR-5. Returns a summary dict::

        {"n": int, "p50_ms": float, "p95_ms": float, "max_ms": float}

    Returns zeros when the retriever is degraded (e.g. CI without PG).
    """
    if not queries:
        return {"n": 0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}

    timings_ms: list[float] = []
    for q in queries:
        t0 = time.perf_counter()
        lookup(q, top_n=top_n)
        timings_ms.append((time.perf_counter() - t0) * 1000.0)

    timings_ms.sort()
    n = len(timings_ms)
    p50 = timings_ms[max(0, n // 2 - 1)]
    p95_idx = max(0, min(n - 1, int(round(0.95 * (n - 1)))))
    p95 = timings_ms[p95_idx]
    return {
        "n": float(n),
        "p50_ms": float(p50),
        "p95_ms": float(p95),
        "max_ms": float(timings_ms[-1]),
    }


# Constant referenced by tests / acceptance criteria — keep it importable so
# downstream refactors do not silently change the SQL ordering contract.
ORDER_BY_CLAUSE = "weighted_score DESC, raw_score DESC, kind ASC, symbol ASC"
