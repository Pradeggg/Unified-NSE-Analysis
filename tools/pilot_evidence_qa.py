#!/usr/bin/env python3
"""Pilot QA report for evidence packs (FTS-only).

Generates a small Markdown + HTML report for a fixed list of symbols and sector overlays.
This is meant to sanity-check:
  - feed health (enough evidence volume)
  - dimension coverage (which dimensions are retrieving signal)
  - duplicates/noise (missing dates, repeated sources)
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from tools.build_evidence_pack import build_evidence_pack  # noqa: E402


DEFAULT_PILOT = [
    ("HDFCBANK", "banks_nbfc"),
    ("LT", "infra_shipping"),
    ("HAL", "defence"),
    ("SUNPHARMA", "pharma"),
    ("MARUTI", "auto"),
]


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sorted_dim_counts(dim_counts: dict[str, int]) -> list[tuple[str, int]]:
    return sorted(dim_counts.items(), key=lambda x: (-int(x[1]), x[0]))


def _top_sources(rows: list[dict[str, Any]], *, top_n: int = 6) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for r in rows:
        name = str(r.get("source_name") or "").strip() or "unknown"
        counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:top_n]


def _flatten_results(pack: dict[str, Any]) -> list[dict[str, Any]]:
    results = pack.get("results") or {}
    flat: list[dict[str, Any]] = []
    for tier_key in ("tier1_primary", "tier2_semiprimary", "tier3_secondary", "tier4_opinion"):
        flat.extend(list(results.get(tier_key) or []))
    return flat


def _missing_date_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    missing = 0
    for r in rows:
        if not (str(r.get("evidence_date") or "").strip() or str(r.get("document_date") or "").strip()):
            missing += 1
    return missing / max(1, len(rows))


def build_pilot_report(
    pilot: list[tuple[str, str]],
    *,
    days_passes: list[int],
    tier_passes: list[int],
    limit_per_query: int,
    top_snippets: int,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for symbol, overlay in pilot:
        pack = build_evidence_pack(
            symbol=symbol,
            sector_overlay=overlay,
            days_passes=days_passes,
            tier_passes=tier_passes,
            limit_per_query=limit_per_query,
            include_market_wide=True,
        )
        flat = _flatten_results(pack)
        runs.append(
            {
                "symbol": symbol,
                "overlay": overlay,
                "as_of": pack.get("as_of"),
                "counts": pack.get("counts") or {},
                "dimension_counts": pack.get("dimension_counts") or {},
                "missing_date_rate": _missing_date_rate(flat),
                "top_sources": _top_sources(flat),
                "top_snippets": {
                    k: sorted(v, key=lambda r: (-float(r.get("rank") or 0.0), int(r.get("chunk_id") or 0)), reverse=False)[:top_snippets]
                    for k, v in (pack.get("results") or {}).items()
                },
            }
        )
    return {"as_of": datetime.now(timezone.utc).isoformat(), "pilot": runs}


def render_markdown(model: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Evidence Pack Pilot QA\n")
    lines.append(f"- As of (UTC): `{model.get('as_of','')}`")
    lines.append("")

    for run in model.get("pilot") or []:
        symbol = run["symbol"]
        overlay = run["overlay"]
        counts = run.get("counts") or {}
        dim_counts = run.get("dimension_counts") or {}
        lines.append(f"## {symbol} ({overlay})")
        lines.append(f"- Tier counts: {json.dumps(counts, ensure_ascii=False)}")
        lines.append(f"- Missing date rate: `{run.get('missing_date_rate',0):.1%}`")
        lines.append("- Top sources:")
        for name, n in run.get("top_sources") or []:
            lines.append(f"  - {name}: {n}")
        lines.append("- Dimension coverage (top):")
        for dim, n in _sorted_dim_counts(dim_counts)[:8]:
            lines.append(f"  - {dim}: {n}")
        lines.append("")

        snippets = run.get("top_snippets") or {}
        for tier_key, title in [
            ("tier1_primary", "Tier 1 — Primary"),
            ("tier2_semiprimary", "Tier 2 — Semi-primary"),
            ("tier3_secondary", "Tier 3 — Secondary"),
            ("tier4_opinion", "Tier 4 — Opinion"),
        ]:
            rows = snippets.get(tier_key) or []
            if not rows:
                continue
            lines.append(f"### {title} (top {min(len(rows),5)})")
            for r in rows[:5]:
                dt = (r.get("evidence_date") or r.get("document_date") or "").strip()
                lines.append(f"- {r.get('source_name','')} | {dt} | {r.get('source_url','')}")
                lines.append(f"  - {str(r.get('snippet') or '').replace('\\n',' ')[:220]}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_html(md_text: str) -> str:
    # Minimal markdown-to-HTML (headings + lists) to keep dependencies at zero.
    esc = html.escape
    out: list[str] = []
    out.append("<!doctype html><meta charset='utf-8'>")
    out.append("<title>Evidence Pack Pilot QA</title>")
    out.append("<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;max-width:1100px;margin:32px auto;padding:0 16px;line-height:1.4}code{background:#f4f4f4;padding:2px 5px;border-radius:4px}h1,h2,h3{margin-top:22px}ul{margin-top:6px}li{margin:4px 0}a{color:#0b61d6;text-decoration:none}a:hover{text-decoration:underline}.box{border:1px solid #e7e7e7;border-radius:10px;padding:14px 16px;margin:14px 0;background:#fff}</style>")
    blocks = md_text.splitlines()
    out.append("<div class='box'>")
    in_ul = False
    for line in blocks:
        if line.startswith("# "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h1>{esc(line[2:])}</h1>")
            continue
        if line.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{esc(line[3:])}</h2>")
            continue
        if line.startswith("### "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h3>{esc(line[4:])}</h3>")
            continue
        if line.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            text = line[2:]
            # naive linkify for URLs
            if "http" in text:
                parts = text.split(" ")
                rendered = []
                for p in parts:
                    if p.startswith("http"):
                        rendered.append(f"<a href='{esc(p)}' target='_blank' rel='noopener noreferrer'>{esc(p)}</a>")
                    else:
                        rendered.append(esc(p))
                out.append(f"<li>{' '.join(rendered)}</li>")
            else:
                out.append(f"<li>{esc(text)}</li>")
            continue
        if line.startswith("  - "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{esc(line[4:])}</li>")
            continue
        if not line.strip():
            if in_ul:
                out.append("</ul>")
                in_ul = False
            continue
        out.append(f"<p>{esc(line)}</p>")
    if in_ul:
        out.append("</ul>")
    out.append("</div>")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(prog="pilot_evidence_qa.py")
    ap.add_argument("--symbols", default="", help="Comma-separated symbols (default pilot set)")
    ap.add_argument("--days-passes", default="0,7,30", help="Freshness passes (default 0,7,30)")
    ap.add_argument("--tier-passes", default="1,2,3,4", help="Tier passes (default 1,2,3,4)")
    ap.add_argument("--limit-per-query", type=int, default=6)
    ap.add_argument("--top-snippets", type=int, default=5)
    ap.add_argument("--out-dir", default="reports/latest")
    args = ap.parse_args()

    pilot = DEFAULT_PILOT
    if args.symbols.strip():
        wanted = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        overlay_map = {sym: ov for sym, ov in DEFAULT_PILOT}
        pilot = [(sym, overlay_map.get(sym, "")) for sym in wanted]

    days_passes = [int(x) for x in args.days_passes.split(",") if x.strip().isdigit()]
    tier_passes = [int(x) for x in args.tier_passes.split(",") if x.strip().isdigit()]

    model = build_pilot_report(
        pilot,
        days_passes=days_passes,
        tier_passes=tier_passes,
        limit_per_query=int(args.limit_per_query),
        top_snippets=int(args.top_snippets),
    )
    md = render_markdown(model)
    html_text = render_html(md)

    out_dir = (ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    md_path = out_dir / f"evidence_pilot_qa_{stamp}.md"
    html_path = out_dir / f"evidence_pilot_qa_{stamp}.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")

    print(json.dumps({"ok": True, "md_path": str(md_path), "html_path": str(html_path)}, indent=2))


if __name__ == "__main__":
    main()

