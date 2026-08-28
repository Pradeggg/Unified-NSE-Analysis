#!/usr/bin/env python3
"""Curated RSS/Atom ingestion into company_intel evidence store (Phase 1, FTS-only).

Workflow:
  1) Load curated sources from `config/research_sources.yml`
  2) Sync into `company_intel.research_sources` (upsert)
  3) Fetch active feeds and store:
       - `company_intel.source_documents`
       - `company_intel.evidence_chunks`

Notes:
  - This ingests feed entry titles + short summaries as evidence (not full articles).
  - Keep sources ToS-safe: prefer official RSS/Atom feeds and press releases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "research_sources.yml"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pg_conn():
    import psycopg2

    dsn = os.environ.get("AGENT_ADDA_PG_DSN") or os.environ.get("PG_DSN") or "dbname=nse_market user=nse_admin host=/tmp"
    return psycopg2.connect(dsn)


@dataclass(frozen=True)
class FeedSource:
    source_name: str
    source_kind: str
    source_url: str
    source_tier: int
    document_type: str
    symbol: str
    tags: dict[str, Any]
    is_active: bool
    notes: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _safe_text(value: Any, *, max_chars: int = 8_000) -> str:
    s = (value or "").strip() if isinstance(value, str) else str(value or "").strip()
    if len(s) > max_chars:
        return s[: max_chars - 1] + "…"
    return s


def _parse_dt(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        # RSS: "Tue, 27 Aug 2026 12:34:56 GMT"
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        # Atom: RFC3339 / ISO-8601
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


DEFAULT_USER_AGENT = "AgentAddaResearchBot/1.0"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _fetch_bytes(
    url: str,
    *,
    timeout: float = 30.0,
    max_bytes: int = 5_000_000,
    retries: int = 2,
) -> bytes:
    """Fetch feed bytes with a small retry policy.

    Some publishers block non-browser User-Agents (403). We try the Agent Adda UA
    first for transparency, then retry with a common browser UA.
    """
    user_agents = [DEFAULT_USER_AGENT, BROWSER_USER_AGENT]
    last_exc: Exception | None = None

    for attempt in range(max(1, int(retries) + 1)):
        for ua in user_agents:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": ua,
                    "Accept": "application/rss+xml, application/atom+xml, text/xml, application/xml, */*",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    content = resp.read(max_bytes + 1)
                    if len(content) > max_bytes:
                        raise ValueError(f"Feed exceeds max_bytes ({max_bytes})")
                    return content
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                # If it's not retryable (e.g., invalid URL), don't keep looping.
                if "403" not in msg and "Forbidden" not in msg and "timed out" not in msg and "Timeout" not in msg:
                    break
        time.sleep(0.25 * (attempt + 1))

    raise last_exc or RuntimeError("Feed fetch failed")


def _xml_root(xml_bytes: bytes) -> ET.Element:
    # Strip BOM if present
    if xml_bytes.startswith(b"\xef\xbb\xbf"):
        xml_bytes = xml_bytes[3:]
    return ET.fromstring(xml_bytes)  # noqa: S314 - controlled fetch + max_bytes cap


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(node: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        if _strip_ns(child.tag).lower() in wanted:
            return (child.text or "").strip()
    return ""


def _atom_link(entry: ET.Element) -> str:
    for child in list(entry):
        if _strip_ns(child.tag).lower() != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        if not href:
            continue
        rel = (child.attrib.get("rel") or "alternate").strip().lower()
        if rel == "alternate":
            return href
        if rel == "self":
            # keep only if we don't find alternate
            fallback = href
            if fallback:
                return fallback
    return ""


def parse_feed_entries(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Parse RSS/Atom feed bytes into a list of entry dicts.

    Returned keys:
      - title, link, guid, summary, published_at (datetime|None), raw_date
    """
    root = _xml_root(xml_bytes)
    root_name = _strip_ns(root.tag).lower()
    entries: list[dict[str, Any]] = []

    # RSS 2.0
    if root_name == "rss" or root.find("./channel") is not None:
        channel = root.find("./channel") if root_name == "rss" else root
        if channel is None:
            return []
        for item in channel.findall("./item"):
            title = _child_text(item, "title")
            link = _child_text(item, "link")
            guid = _child_text(item, "guid") or link
            summary = _child_text(item, "description") or _child_text(item, "summary")
            raw_date = _child_text(item, "pubDate") or _child_text(item, "date")
            published_at = _parse_dt(raw_date)
            entries.append(
                {
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "summary": summary,
                    "published_at": published_at,
                    "raw_date": raw_date,
                }
            )
        return entries

    # Atom
    if root_name == "feed":
        for entry in root.findall(".//{*}entry"):
            title = _child_text(entry, "title")
            link = _atom_link(entry) or _child_text(entry, "link")
            guid = _child_text(entry, "id") or link
            summary = _child_text(entry, "summary") or _child_text(entry, "content")
            raw_date = _child_text(entry, "published") or _child_text(entry, "updated")
            published_at = _parse_dt(raw_date)
            entries.append(
                {
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "summary": summary,
                    "published_at": published_at,
                    "raw_date": raw_date,
                }
            )
        return entries

    # Unknown format
    return []


def load_sources(config_path: Path) -> list[FeedSource]:
    try:
        import yaml  # PyYAML
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"PyYAML is required to read {config_path}: {exc}") from exc

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    sources = data.get("sources") or []
    out: list[FeedSource] = []
    for row in sources:
        if not isinstance(row, dict):
            continue
        source_name = str(row.get("source_name", "")).strip()
        source_kind = str(row.get("source_kind", "")).strip().lower()
        source_url = str(row.get("source_url", "")).strip()
        if not source_name or not source_kind or not source_url:
            continue
        out.append(
            FeedSource(
                source_name=source_name,
                source_kind=source_kind,
                source_url=source_url,
                source_tier=int(row.get("source_tier", 3) or 3),
                document_type=str(row.get("document_type") or "news_rss").strip(),
                symbol=str(row.get("symbol") or "").strip().upper(),
                tags=dict(row.get("tags") or {}),
                is_active=bool(True if row.get("is_active") is None else row.get("is_active")),
                notes=str(row.get("notes") or "").strip(),
            )
        )
    return out


def sync_sources(conn: Any, sources: list[FeedSource], *, dry_run: bool) -> dict[str, int]:
    with conn.cursor() as cur:
        for src in sources:
            if dry_run:
                continue
            cur.execute(
                """
                INSERT INTO company_intel.research_sources
                    (source_name, source_kind, source_url, symbol, document_type, source_tier, tags, is_active, notes, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, NOW())
                ON CONFLICT (source_kind, source_url) DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    symbol = EXCLUDED.symbol,
                    document_type = EXCLUDED.document_type,
                    source_tier = EXCLUDED.source_tier,
                    tags = EXCLUDED.tags,
                    is_active = EXCLUDED.is_active,
                    notes = EXCLUDED.notes,
                    updated_at = NOW()
                """,
                (
                    src.source_name,
                    src.source_kind,
                    src.source_url,
                    src.symbol,
                    src.document_type,
                    int(src.source_tier),
                    json.dumps(src.tags or {}, ensure_ascii=False),
                    bool(src.is_active),
                    src.notes,
                ),
            )
        if not dry_run:
            conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM company_intel.research_sources")
        total = int(cur.fetchone()[0])
    return {"total": total, "synced": len(sources)}


def _tier_confidence(source_tier: int) -> float:
    tier = int(source_tier or 3)
    if tier <= 1:
        return 0.8
    if tier == 2:
        return 0.7
    if tier == 3:
        return 0.6
    return 0.5


def _category_for_document_type(document_type: str) -> str:
    dt = (document_type or "").strip().lower()
    if dt.startswith(("nse_", "bse_", "exchange_")):
        return "filing"
    if dt.startswith(("rbi_", "sebi_", "pib_", "policy_", "regulator_")):
        return "policy"
    if dt.startswith(("credit_", "rating_")):
        return "credit"
    return "news"


def ingest_active_rss(
    conn: Any,
    *,
    max_items_per_feed: int,
    since_days: int,
    sleep_ms: int,
    dry_run: bool,
) -> dict[str, Any]:
    fetched_at = _now_iso()
    since_cutoff: datetime | None = None
    if since_days > 0:
        since_cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    stats = {
        "feeds": 0,
        "entries_seen": 0,
        "documents_inserted": 0,
        "documents_skipped": 0,
        "errors": [],
        "fetched_at": fetched_at,
    }

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_id, source_name, source_url, symbol, document_type, source_tier, tags
            FROM company_intel.research_sources
            WHERE is_active = TRUE AND source_kind = 'rss'
            ORDER BY source_tier ASC, source_name ASC
            """
        )
        sources = cur.fetchall()

    for source_id, source_name, feed_url, symbol, document_type, source_tier, tags in sources:
        parsed_tags: dict[str, Any] = {}
        if isinstance(tags, dict):
            parsed_tags = tags
        elif isinstance(tags, str) and tags.strip():
            try:
                parsed = json.loads(tags)
                parsed_tags = parsed if isinstance(parsed, dict) else {}
            except Exception:
                parsed_tags = {}

        stats["feeds"] += 1
        try:
            xml_bytes = _fetch_bytes(str(feed_url))
            entries = parse_feed_entries(xml_bytes)
        except Exception as exc:
            stats["errors"].append({"feed_url": str(feed_url), "error": str(exc)})
            continue

        for entry in entries[: max_items_per_feed or 0]:
            stats["entries_seen"] += 1
            title = _safe_text(entry.get("title", ""), max_chars=500)
            link = _safe_text(entry.get("link", ""), max_chars=1000)
            guid = _safe_text(entry.get("guid", ""), max_chars=1000)
            summary = _safe_text(entry.get("summary", ""), max_chars=4_000)
            published_at: datetime | None = entry.get("published_at")
            if since_cutoff and published_at and published_at < since_cutoff:
                continue

            canonical = link or guid or (title + (entry.get("raw_date") or ""))
            document_id = f"rss_{_sha256(canonical)[:32]}"
            evidence_text = (title + "\n" + summary).strip()
            if not evidence_text:
                continue

            evidence_date = ""
            if published_at:
                evidence_date = published_at.date().isoformat()

            meta = {
                "source_id": int(source_id),
                "feed_url": str(feed_url),
                "entry_link": link,
                "entry_guid": guid,
                "title": title,
                "summary": summary,
                "published_at": published_at.isoformat() if published_at else "",
                "fetched_at": fetched_at,
                "tags": parsed_tags,
            }

            if dry_run:
                stats["documents_inserted"] += 1
                continue

            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO company_intel.source_documents
                            (document_id, symbol, source_tier, source_name, source_url, document_type,
                             document_date, local_path, content_hash, fetch_status, parse_status, failure_reason, metadata)
                        VALUES
                            (%s, %s, %s, %s, %s, %s,
                             %s, %s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (document_id) DO NOTHING
                        """,
                        (
                            document_id,
                            (symbol or "").strip().upper(),
                            int(source_tier),
                            str(source_name),
                            (link or "").strip(),
                            str(document_type or "news_rss"),
                            evidence_date,
                            "",
                            _sha256(evidence_text),
                            "ok",
                            "rss",
                            "",
                            json.dumps(meta, ensure_ascii=False),
                        ),
                    )
                    inserted = cur.rowcount > 0
                    if not inserted:
                        stats["documents_skipped"] += 1
                        continue

                    cur.execute(
                        """
                        INSERT INTO company_intel.evidence_chunks
                            (document_id, symbol, category, text, page_number, table_id, source_tier, confidence, evidence_date)
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            document_id,
                            (symbol or "").strip().upper(),
                            _category_for_document_type(str(document_type or "")),
                            evidence_text,
                            None,
                            "",
                            int(source_tier),
                            float(_tier_confidence(int(source_tier))),
                            evidence_date,
                        ),
                    )
                conn.commit()
                stats["documents_inserted"] += 1
            except Exception as exc:
                conn.rollback()
                stats["errors"].append({"feed_url": str(feed_url), "entry": link or guid, "error": str(exc)})

        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)

    return stats


def main() -> None:
    ap = argparse.ArgumentParser(prog="ingest_news_feeds.py")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--sync-only", action="store_true")
    ap.add_argument("--ingest-only", action="store_true")
    ap.add_argument("--max-items-per-feed", type=int, default=25)
    ap.add_argument("--since-days", type=int, default=7)
    ap.add_argument("--sleep-ms", type=int, default=250)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    sources = load_sources(config_path)

    conn = _pg_conn()
    conn.autocommit = False

    try:
        sync_result = sync_sources(conn, sources, dry_run=bool(args.dry_run))
        print(f"research_sources sync: {sync_result['synced']} from config, {sync_result['total']} total in PG")

        if args.sync_only and not args.ingest_only:
            return

        if args.ingest_only and not args.sync_only:
            # still ok: we already synced; ingestion reads from PG.
            pass

        ingest_stats = ingest_active_rss(
            conn,
            max_items_per_feed=int(args.max_items_per_feed),
            since_days=int(args.since_days),
            sleep_ms=int(args.sleep_ms),
            dry_run=bool(args.dry_run),
        )
        print(json.dumps(ingest_stats, indent=2))
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
