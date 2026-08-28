#!/usr/bin/env python3
"""Push Agent Adda reports to the agentadda/www website repo.

Copies a generated HTML report into the Next.js/Cloudflare Pages site at
agentadda.in/stocks/reports by:
  1. Placing the HTML file  → {www_repo}/public/reports/{slug}.html
  2. Writing an MDX entry   → {www_repo}/src/content/stocks/reports/{slug}.mdx
  3. Committing + pushing   → triggers Cloudflare rebuild

Usage examples:
  # Publish a preset report (sector_rotation, stage2_tracker, swing_playbook, eod_market, morning_market)
  python scripts/push_to_www.py --preset sector_rotation
  python scripts/push_to_www.py --preset stage2_tracker --date 2026-08-20

  # Publish all daily presets at once
  python scripts/push_to_www.py --all-daily

  # Publish a fully custom report
  python scripts/push_to_www.py \\
    --html reports/latest/my_report.html \\
    --slug my-report-2026-08-20 \\
    --title "My Report — 20 Aug 2026" \\
    --excerpt "Short description." \\
    --type deep-research \\
    --tickers RELIANCE,TCS \\
    --sector "Energy,IT" \\
    --tags "Daily,AI Analysis"

  # Dry-run (no commit/push)
  python scripts/push_to_www.py --preset stage2_tracker --dry-run

Environment variable:
  AGENTADDA_WWW_REPO  Path to cloned agentadda/www repo.
                      Default: ~/Documents/Projects/agentadda-www
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

try:
    from knowledge_base.episode_store import EpisodeHandle, EpisodeStore  # type: ignore
except Exception:  # pragma: no cover
    EpisodeHandle = None  # type: ignore
    EpisodeStore = None  # type: ignore

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent  # Unified-NSE-Analysis/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_WWW_REPO = Path.home() / "Documents" / "Projects" / "agentadda-www"
WWW_REPO_URL = "https://github.com/agentadda/www.git"

# ---------------------------------------------------------------------------
# Preset report configurations
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict] = {
    "sector_rotation": {
        "html_source": "reports/latest/sector_rotation.html",
        "slug_prefix": "sector-rotation",
        "title_tmpl": "Sector Rotation Report — {date_fmt}",
        "excerpt": (
            "Daily sector rotation analysis across NSE using Weinstein Stage classification, "
            "relative strength ranking, and AI-generated sector commentary. "
            "Identifies which sectors are in Stage 1 (base), Stage 2 (uptrend), Stage 3 (top), "
            "and Stage 4 (decline)."
        ),
        "report_type": "sector-rotation",
        "tickers": [],
        "sector": ["All Sectors"],
        "tags": ["Sector Rotation", "Weinstein Stage", "Daily Analysis", "NSE", "AI Analysis"],
        "read_time": "8 min read",
    },
    "stage2_tracker": {
        "html_source": "reports/latest/stage2_tracker.html",
        "slug_prefix": "stage2-tracker",
        "title_tmpl": "Stage 2 Breakout Tracker — {date_fmt}",
        "excerpt": (
            "Full universe scan of NSE stocks currently in Weinstein Stage 2 uptrend. "
            "Each stock is scored on technical momentum, fundamental quality, relative strength, "
            "and VCP pattern detection. Includes entry signals, stop-loss levels, and sector context."
        ),
        "report_type": "stage2-tracker",
        "tickers": [],
        "sector": ["All Sectors"],
        "tags": ["Stage 2", "Weinstein", "Breakout", "Screener", "Daily Analysis", "NSE"],
        "read_time": "12 min read",
    },
    "swing_playbook": {
        "html_source": "reports/latest/swing_playbook.html",
        "slug_prefix": "swing-playbook",
        "title_tmpl": "Swing Trade Playbook — {date_fmt}",
        "excerpt": (
            "AI-curated swing trade setups for the current session. Each setup is selected "
            "using the AgentAdda 12-layer framework: Stage 2 base, RS ≥ 65, TechScore ≥ 65, "
            "Supertrend bullish, and VCP / consolidation breakout pattern confirmed."
        ),
        "report_type": "swing-playbook",
        "tickers": [],
        "sector": ["All Sectors"],
        "tags": ["Swing Trading", "VCP", "Breakout", "Setups", "NSE", "AI Analysis"],
        "read_time": "6 min read",
    },
    "top_picks": {
        "html_source": "reports/latest/top_picks.html",
        "slug_prefix": "top-picks",
        "title_tmpl": "Top Investment Picks — {date_fmt}",
        "excerpt": (
            "AgentAdda's curated high-conviction stock picks for the session — scored across "
            "Weinstein Stage 2 momentum, technical strength (RSI, MACD, Supertrend), fundamental "
            "quality (earnings, sales growth, financial health), and VCP pattern confirmation. "
            "Includes per-stock deep dives, entry levels, stop-loss, and sector context."
        ),
        "report_type": "top-picks",
        "tickers": [],
        "sector": ["All Sectors"],
        "tags": ["Top Picks", "Stage 2", "VCP", "High Conviction", "NSE", "AI Analysis"],
        "read_time": "15 min read",
    },
    "eod_market": {
        "html_source": "reports/latest/eod_market_report.html",
        "slug_prefix": "eod-market-report",
        "title_tmpl": "EOD Market Report — {date_fmt}",
        "excerpt": (
            "End-of-day market intelligence report covering NIFTY 50, BANK NIFTY, and sector "
            "breadth. Includes advance/decline, McClellan Oscillator, FII/DII flows, top movers, "
            "and regime state."
        ),
        "report_type": "eod-report",
        "tickers": ["NIFTY50", "BANKNIFTY"],
        "sector": ["Indices", "Market Breadth"],
        "tags": ["EOD", "Market Overview", "Breadth", "FII/DII", "Daily Analysis"],
        "read_time": "5 min read",
    },
    "morning_market": {
        "html_source": "reports/latest/morning_market.html",
        "slug_prefix": "morning-market",
        "title_tmpl": "Morning Market — {date_fmt}",
        "excerpt": (
            "Opening market intelligence dashboard covering NIFTY, Bank Nifty, broader indices, "
            "sector leadership, top gainers and losers, momentum, F&O context, and global and "
            "commodity cues."
        ),
        "report_type": "morning-market",
        "tickers": ["NIFTY50", "BANKNIFTY", "INDIAVIX"],
        "sector": ["Indices", "Market Breadth", "F&O", "Global Cues"],
        "tags": [
            "Morning Market",
            "Opening View",
            "Market Overview",
            "Breadth",
            "F&O",
            "Global Cues",
            "Daily Analysis",
        ],
        "read_time": "6 min read",
    },
    "midday_market": {
        "html_source": "reports/latest/midday_market.html",
        "slug_prefix": "midday-market",
        "title_tmpl": "Midday Market — {date_fmt}",
        "excerpt": (
            "Midday market intelligence dashboard covering NIFTY, Bank Nifty, broader indices, "
            "sector leadership, top gainers and losers, momentum, F&O context, and global and "
            "commodity cues for the second half of the session."
        ),
        "report_type": "midday-market",
        "tickers": ["NIFTY50", "BANKNIFTY", "INDIAVIX"],
        "sector": ["Indices", "Market Breadth", "F&O", "Global Cues"],
        "tags": [
            "Midday Market",
            "Intraday View",
            "Market Overview",
            "Breadth",
            "F&O",
            "Global Cues",
            "Daily Analysis",
        ],
        "read_time": "6 min read",
    },
}

# ---------------------------------------------------------------------------
# Pre-push HTML quality gate
# ---------------------------------------------------------------------------

class _QIssue(NamedTuple):
    severity: str   # "error" | "warn"
    message: str


# Patterns that should NEVER appear in rendered text nodes.
# These match visible content only; we strip <script>/<style> blocks first.
_VISIBLE_NAN_RE = re.compile(
    r"(?:"
    r"[+\-]?nan%"          # "+nan%", "-nan%", "nan%"
    r"|[+\-]?NaN%"         # same, uppercase
    r"|>\s*nan\s*<"        # ">nan<" in a cell
    r"|>\s*NaN\s*<"        # ">NaN<" in a cell
    r"|>\s*undefined\s*<"  # ">undefined<"
    r"|>\s*None\s*<"       # ">None<"
    r")",
    re.IGNORECASE,
)

# Patterns that indicate the report generator crashed mid-run.
_BROKEN_MARKERS = [
    "Traceback (most recent call last)",
    "Error generating report",
    "REPORT GENERATION FAILED",
]

# Minimum acceptable file size in bytes — anything smaller is almost certainly truncated.
_MIN_BYTES: dict[str, int] = {
    "eod_market":     75_000,
    "sector_rotation": 400_000,
    "stage2_tracker": 500_000,
    "swing_playbook":  30_000,
    "morning_market":  25_000,
    "midday_market":   25_000,
}
_DEFAULT_MIN_BYTES = 30_000


def _strip_scripts(html: str) -> str:
    """Remove <script> and <style> blocks so regex matches only visible content."""
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>",  "", html, flags=re.DOTALL | re.IGNORECASE)
    return html


def validate_html(html_path: Path, preset_key: str = "") -> list[_QIssue]:
    """
    Run a quality gate on an HTML report before it is pushed to production.

    Returns a list of _QIssue objects.  Any item with severity=="error" should
    block the push; "warn" items are logged but do not block.
    """
    issues: list[_QIssue] = []

    if not html_path.exists():
        return [_QIssue("error", f"File not found: {html_path}")]

    raw = html_path.read_text(encoding="utf-8", errors="replace")
    size = html_path.stat().st_size
    min_bytes = _MIN_BYTES.get(preset_key, _DEFAULT_MIN_BYTES)

    # 1. Size check — catches truncated / empty files
    if size < min_bytes:
        issues.append(_QIssue(
            "error",
            f"File is only {size:,} bytes — expected ≥ {min_bytes:,} bytes. "
            "The report may be truncated or failed to generate.",
        ))

    # 2. Crash / error marker check
    for marker in _BROKEN_MARKERS:
        if marker in raw:
            issues.append(_QIssue("error", f"Crash marker found in HTML: {marker!r}"))

    # 3. Visible NaN / undefined check (script+style stripped)
    visible = _strip_scripts(raw)
    matches = _VISIBLE_NAN_RE.findall(visible)
    if matches:
        unique = sorted(set(m.strip() for m in matches))
        issues.append(_QIssue(
            "error",
            f"Visible NaN/undefined values in rendered content ({len(matches)} hit(s)): "
            + ", ".join(repr(u) for u in unique[:6])
            + (" …" if len(unique) > 6 else ""),
        ))

    # 4. Placeholder check — generic "Coming soon" / "No data available" blocks
    placeholder_re = re.compile(
        r"(?:Coming soon|No data available|PLACEHOLDER|TODO:.*?</)",
        re.IGNORECASE,
    )
    ph_hits = placeholder_re.findall(visible)
    if ph_hits:
        issues.append(_QIssue(
            "warn",
            f"{len(ph_hits)} placeholder string(s) found in rendered content.",
        ))

    return issues


def _print_issues(issues: list[_QIssue], html_path: Path) -> bool:
    """Print issues and return True if any are errors (blocking)."""
    errors = [i for i in issues if i.severity == "error"]
    warns  = [i for i in issues if i.severity == "warn"]
    for w in warns:
        print(f"  ⚠  WARN  {w.message}")
    for e in errors:
        print(f"  ✗  ERROR {e.message}")
    return bool(errors)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def run_git(args: list[str], *, cwd: Path, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _is_agentadda_www_repo(repo_path: Path) -> bool:
    """Allowlist check: only agentadda/www is allowed for git commit/push by default."""
    try:
        origin = run_git(["remote", "get-url", "origin"], cwd=repo_path, check=False).strip()
    except Exception:
        return False
    if not origin:
        return False
    origin = origin.replace("git@github.com:", "https://github.com/").rstrip("/")
    return origin.endswith("github.com/agentadda/www.git") or origin.endswith("github.com/agentadda/www")


def ensure_www_repo(repo_path: Path) -> None:
    """Clone or pull the www repo."""
    if (repo_path / ".git").exists():
        print(f"  [www] pulling latest from origin → {repo_path}")
        run_git(["pull", "--ff-only"], cwd=repo_path)
    else:
        print(f"  [www] cloning {WWW_REPO_URL} → {repo_path}")
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", WWW_REPO_URL, str(repo_path)], check=True
        )


# ---------------------------------------------------------------------------
# MDX generation
# ---------------------------------------------------------------------------

def _yaml_list(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(f'"{s}"' for s in items) + "]"


def build_mdx(
    *,
    title: str,
    date_iso: str,
    excerpt: str,
    report_type: str,
    report_date_fmt: str,
    tickers: list[str],
    sector: list[str],
    tags: list[str],
    read_time: str,
    html_filename: str,
    body: str,
) -> str:
    frontmatter = textwrap.dedent(f"""\
        ---
        title: "{title}"
        date: "{date_iso}"
        excerpt: "{excerpt}"
        reportType: "{report_type}"
        reportDate: "{report_date_fmt}"
        tickers: {_yaml_list(tickers)}
        sector: {_yaml_list(sector)}
        tags: {_yaml_list(tags)}
        readTime: "{read_time}"
        isHistorical: true
        reportHtmlPath: "/reports/{html_filename}"
        ---
        """)
    return frontmatter + "\n" + body + "\n"


# ---------------------------------------------------------------------------
# Core publish function
# ---------------------------------------------------------------------------

def publish_report(
    *,
    html_path: Path,
    slug: str,
    title: str,
    date_iso: str,
    excerpt: str,
    report_type: str,
    report_date_fmt: str,
    tickers: list[str],
    sector: list[str],
    tags: list[str],
    read_time: str,
    mdx_body: str,
    www_repo: Path,
    dry_run: bool,
    push: bool,
    preset_key: str = "",
    force: bool = False,
    episode_id: str = "",
    allow_non_agentadda_www_git: bool = False,
) -> bool:
    store = EpisodeStore() if EpisodeStore else None
    handle = None
    owns = False
    if store and EpisodeHandle:
        env_handle = EpisodeHandle.from_env()
        if env_handle:
            handle = env_handle
        elif episode_id:
            handle = EpisodeHandle(episode_id=episode_id)
        else:
            handle = store.start_episode(
                goal=f"publish_report slug={slug}",
                caller="push_to_www",
                tags=["publish", "www", preset_key or "custom"],
                metadata={"slug": slug, "preset": preset_key, "push": push, "dry_run": dry_run},
            )
            owns = True

    html_filename = f"{slug}.html"
    mdx_filename = f"{slug}.mdx"

    dest_html = www_repo / "public" / "reports" / html_filename
    dest_mdx = www_repo / "src" / "content" / "stocks" / "reports" / mdx_filename

    # ── Quality gate ──────────────────────────────────────────────────────────
    print(f"  [validate] checking {html_path.name} …")
    issues = validate_html(html_path, preset_key=preset_key)
    has_errors = _print_issues(issues, html_path)
    if store and handle:
        err_n = sum(1 for i in issues if i.severity == "error")
        warn_n = sum(1 for i in issues if i.severity == "warn")
        store.log_validator(
            handle,
            name=f"publish_quality_gate:{preset_key or 'custom'}",
            ok=(err_n == 0 or bool(force)),
            details={
                "slug": slug,
                "preset": preset_key,
                "html_path": str(html_path),
                "errors": err_n,
                "warnings": warn_n,
                "forced": bool(force),
            },
        )
    if has_errors and not force:
        print(
            f"  ✗ BLOCKED — {slug} not published. "
            "Fix the errors above, then re-run. "
            "Use --force to override (not recommended)."
        )
        if store and handle and owns:
            store.end_episode(
                handle,
                status="FAILED",
                summary="blocked by quality gate",
                metadata={"slug": slug, "preset": preset_key, "has_errors": True},
            )
        return False
    if not issues:
        print("  ✓ Quality gate passed — no issues found.")
    elif not has_errors:
        print("  ✓ Quality gate passed with warnings (see above).")
    # ─────────────────────────────────────────────────────────────────────────

    mdx_content = build_mdx(
        title=title,
        date_iso=date_iso,
        excerpt=excerpt,
        report_type=report_type,
        report_date_fmt=report_date_fmt,
        tickers=tickers,
        sector=sector,
        tags=tags,
        read_time=read_time,
        html_filename=html_filename,
        body=mdx_body,
    )

    if dry_run:
        print(f"  [dry-run] would copy  {html_path} → {dest_html}")
        print(f"  [dry-run] would write {dest_mdx}")
        print("  [dry-run] MDX preview:")
        for line in mdx_content.splitlines()[:20]:
            print(f"    {line}")
        if store and handle:
            store.log_artifact(handle, artifact_type="publish_dryrun_dest_html", locator=str(dest_html))
            store.log_artifact(handle, artifact_type="publish_dryrun_dest_mdx", locator=str(dest_mdx))
            if owns:
                store.end_episode(handle, status="SUCCESS", summary="dry-run publish preview", metadata={"slug": slug})
        return True

    dest_html.parent.mkdir(parents=True, exist_ok=True)
    dest_mdx.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(html_path, dest_html)
    dest_mdx.write_text(mdx_content, encoding="utf-8")
    if store and handle:
        store.log_artifact(handle, artifact_type="source_html", locator=str(html_path), meta={"preset": preset_key})
        store.log_artifact(handle, artifact_type="www_public_html", locator=str(dest_html), meta={"slug": slug})
        store.log_artifact(handle, artifact_type="www_mdx", locator=str(dest_mdx), meta={"slug": slug})

    print(f"  ✓ HTML → {dest_html.relative_to(www_repo)}")
    print(f"  ✓ MDX  → {dest_mdx.relative_to(www_repo)}")

    allow_git = _is_agentadda_www_repo(www_repo) or allow_non_agentadda_www_git
    if not allow_git:
        print("  [git] skipped (only agentadda/www is allowed by default). Re-run with --allow-non-agentadda-www-git to override.")
        if store and handle:
            store.log_step(handle, step="git skipped (repo not allowlisted)", tool_name="git", status="info")
            if owns:
                store.end_episode(
                    handle,
                    status="PARTIAL",
                    summary="copied files but did not commit (external git disabled)",
                    metadata={"slug": slug, "www_repo": str(www_repo)},
                )
        return True

    # Commit
    run_git(["add", str(dest_html), str(dest_mdx)], cwd=www_repo)
    status = run_git(["status", "--short"], cwd=www_repo)
    if not status:
        print("  [git] no changes to commit (report already up to date)")
    else:
        run_git(
            ["commit", "-m", f"publish: {title}"],
            cwd=www_repo,
        )
        print(f"  [git] committed: publish: {title}")
    if store and handle:
        try:
            sha = run_git(["rev-parse", "HEAD"], cwd=www_repo).strip()
        except Exception:
            sha = ""
        if sha:
            store.log_artifact(handle, artifact_type="git_commit", locator=sha, meta={"repo": str(www_repo)})

    if push:
        run_git(["push", "origin", "main"], cwd=www_repo)
        print("  [git] pushed to origin/main → Cloudflare rebuild triggered")
        if store and handle:
            store.log_artifact(handle, artifact_type="git_push", locator="origin/main", meta={"repo": str(www_repo)})
    else:
        print("  [git] push skipped (use --push to deploy)")
        if store and handle:
            store.log_step(handle, step="git push skipped", tool_name="git", status="info")
    if store and handle and owns:
        store.end_episode(handle, status="SUCCESS", summary="publish completed", metadata={"slug": slug, "pushed": bool(push)})
    return True


def notify_published_report(
    *,
    report_key: str,
    title: str,
    slug: str,
    dry_run: bool = False,
) -> bool:
    try:
        from terminal.email_dispatcher import send_report_email  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 - publish should not be rolled back for email import failure.
        print(f"  [notify] failed to import email dispatcher: {type(exc).__name__}: {exc}")
        return False

    url = f"https://agentadda.in/stocks/reports/{slug}"
    subject = f"Agent Adda: {title}"
    note = (
        f"{title} has been published to Agent Adda Market Intelligence. "
        f"Live report URL: {url}. Keep the email concise, factual, evidence-led, "
        "and research-only. Mention that this is not investment advice."
    )
    result = send_report_email(
        report_key,
        mode="both",
        send=not dry_run,
        subject=subject,
        note=note,
    )
    if not isinstance(result, dict):
        print(f"  [notify] failed: unexpected result from email dispatcher: {result!r}")
        return False
    recipients = result.get("recipients", {})
    to_label = ", ".join(recipients.get("to") or []) or "none"
    bcc_label = ", ".join(recipients.get("bcc") or []) or "none"
    if result.get("ok"):
        action = "previewed" if dry_run else "sent"
        print(f"  [notify] {action}: {result.get('subject')}")
        print(f"  [notify] to={to_label}")
        print(f"  [notify] bcc={bcc_label}")
        return True
    print(f"  [notify] failed: {result.get('message')}")
    print(f"  [notify] to={to_label}")
    print(f"  [notify] bcc={bcc_label}")
    return False


def notification_report_key(spec: dict) -> str:
    return str(spec.get("preset_key") or spec.get("report_type") or "").replace("-", "_")


# ---------------------------------------------------------------------------
# Preset helpers
# ---------------------------------------------------------------------------

def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and not os.environ.get(key):
            os.environ[key] = value.strip().strip('"').strip("'")


def _report_text_for_summary(html_path: Path) -> str:
    md_path = html_path.with_suffix(".md")
    if md_path.exists():
        return md_path.read_text(encoding="utf-8", errors="replace")[:18_000]
    raw = html_path.read_text(encoding="utf-8", errors="replace")
    raw = _strip_scripts(raw)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:18_000]


def llm_mdx_summary_body(preset_key: str, title: str, excerpt: str, html_path: Path) -> str | None:
    """Generate the website report summary from the actual report artifact."""
    if preset_key != "eod_market":
        return None
    _load_env_file(ROOT / ".env")
    _load_env_file(ROOT.parent / ".env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("  [summary] LLM skipped: OPENAI_API_KEY not configured")
        return None

    report_text = _report_text_for_summary(html_path)
    prompt = textwrap.dedent(f"""\
        Write the MDX page summary for an Agent Adda report page.

        Report title: {title}
        Short excerpt: {excerpt}

        Use only the evidence in the report text below. Do not invent numbers.
        Write concise Markdown, not HTML. Return STRICT JSON:
        {{
          "body_markdown": "<markdown body>"
        }}

        Required structure:
        - Start with the exact report title as the first line.
        - Add the short excerpt.
        - Add a detailed executive summary of what the report says for this date.
        - Explain how to read the main embedded report: index tape, breadth/participation, sector leadership/pressure, top movers, flows/regime, and next-session watch.
        - End with a clear research-only disclaimer.
        - Keep it factual, useful, and suitable above the embedded main report.

        REPORT TEXT:
        {report_text}
    """)
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=api_key, timeout=60)
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write concise, evidence-grounded market report summaries for "
                        "Agent Adda. Do not add unsupported claims or advice."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_completion_tokens=900,
        )
        content = response.choices[0].message.content or "{}"
        body = str(json.loads(content).get("body_markdown") or "").strip()
        if body:
            print("  [summary] LLM-generated MDX summary")
            return body
    except Exception as exc:  # noqa: BLE001 - publish should still have a fallback.
        print(f"  [summary] LLM summary failed ({type(exc).__name__}: {exc})")
    return None


def preset_mdx_body(preset_key: str, title: str, excerpt: str) -> str:
    if preset_key == "eod_market":
        return textwrap.dedent(f"""\
            {title}

            {excerpt}

            This end-of-day report is the main Agent Adda close-of-market briefing. It is designed to summarize what happened after the full session has completed, where participation was broad or narrow, which parts of the market led or weakened, and what should be watched in the next trading session.

            The first layer is the index tape: NIFTY 50 and BANK NIFTY levels, day range, closing move, and whether the session held its opening strength or faded into the close. This gives the high-level risk tone before looking at individual stocks.

            The second layer is participation. Advance/decline, hourly breadth, average stock movement, volume, McClellan context, and regime state help separate a healthy market from a narrow index-led move. Weak breadth near the close is treated differently from a broad, confirmed rally.

            The third layer is leadership and pressure. Sector breadth, top gainers, top losers, and theme-level rotation show where capital is moving and where selling pressure is concentrated. These sections are useful for preparing the next day's watchlist, but they are not buy or sell calls by themselves.

            The final layer is the next-session watch. Use it to identify confirmation levels, risk pockets, and sectors or stocks that need follow-through. The embedded HTML report contains the full tables, breadth timeline, movers, event log, and market context for deeper review.

            This report was generated by the AgentAdda market intelligence system and is published as an educational showcase. It is research-only market intelligence, not personalised investment advice, not a trade recommendation, and not a substitute for independent verification or professional guidance.
            """)

    if preset_key == "midday_market":
        return textwrap.dedent(f"""\
            {title}

            {excerpt}

            This midday note is written as a market commentary for active retail investors. It is meant to answer a practical question: after the opening move has played out, is participation broadening, narrowing, or rotating into a smaller set of themes?

            Read the dashboard in layers. Start with NIFTY, Bank Nifty, broader indices, and India VIX to understand the market's risk tone. Then compare sector leaders against weak pockets to see whether the session is supported by broad participation or only by a few isolated pockets. The top gainers and losers table helps identify where price action is strongest or weakest, while the momentum screen should be treated as watchlist context rather than a fresh recommendation.

            The F&O section is intentionally framed as context, not as a standalone directional signal. PCR, max pain, call/put walls, and buildup need to confirm with price action and intraday range behaviour before they become useful. Global and commodity cues are included as background, with their own timestamps, so stale or cached evidence is not mistaken for live confirmation.

            For retail investors, the core use of this report is preparation: identify what deserves attention, what should be avoided because the move is stretched, and what needs confirmation before any capital is committed. It is research-only market intelligence, not personalised advice, not a trade call, and not a substitute for independent verification or professional guidance.
            """)

    if preset_key == "morning_market":
        return textwrap.dedent(f"""\
            {title}

            {excerpt}

            This morning note is written as a market-opening commentary for active retail investors. It is designed to turn the first market snapshot into a structured read of risk appetite, sector participation, stock-level movers, F&O positioning, and global cues.

            The dashboard should be read from the top down. First, confirm whether NIFTY, Bank Nifty, broader indices, and India VIX agree with the opening stance. Next, compare sector leaders with weak pockets to separate genuine breadth from a narrow opening move. Top gainers, losers, and momentum names are watchlist inputs; they are not buy or sell instructions.

            The first 15-30 minutes matter because early moves can reverse quickly. Price acceptance, breadth, volume, and Bank Nifty confirmation carry more weight than a single index tick. F&O evidence is useful only when PCR, buildup, and price action align.

            For retail investors, the purpose is to prepare a cleaner watchlist, avoid chasing stretched names, and frame the day's risk before acting. It is research-only market intelligence, not personalised advice, not a trade call, and not a substitute for independent verification or professional guidance.
            """)

    if preset_key == "swing_playbook":
        return textwrap.dedent(f"""\
            {title}

            {excerpt}

            This playbook is written as a tactical market commentary for active retail investors and swing traders. It translates the full Agent Adda setup table into a clearer read on what is working, what needs confirmation, and how risk should be controlled before any trade is considered.

            Start with the market regime before looking at individual names. Swing setups are only useful when index direction, breadth, volatility, and sector participation give them enough room to work. If the report marks the tape as choppy, risk-off, or confirmation-dependent, the shortlist should be treated as a prepared watchlist rather than an instruction to enter.

            The table ranks candidates using Weinstein stage, technical strength, relative strength, and fundamental quality. Stage 2 names generally indicate established uptrends, while early Stage 1 names require more patience and stronger confirmation. Entry triggers, stops, and targets are scenario levels; they require intraday confirmation, volume support, and position sizing discipline.

            For retail investors, the practical use is to identify a small number of clean setups, check them on charts, wait for price acceptance above trigger levels, and avoid over-sizing in weak market conditions. This is research-only market intelligence, not personalised advice, not a trade call, and not a buy/sell recommendation.
            """)

    return (
        f"{title}\n\n"
        f"{excerpt}\n\n"
        "This report was generated by the AgentAdda market intelligence system and is "
        "published as an educational showcase. Not investment advice."
    )


def preset_to_args(preset_key: str, date_iso: str) -> dict:
    cfg = PRESETS[preset_key]
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    date_fmt = dt.strftime("%-d %b %Y")  # e.g. "20 Aug 2026"
    slug = f"{cfg['slug_prefix']}-{date_iso}"
    title = cfg["title_tmpl"].format(date_fmt=date_fmt)
    return dict(
        html_source=cfg["html_source"],
        slug=slug,
        title=title,
        date_iso=date_iso,
        excerpt=cfg["excerpt"],
        report_type=cfg["report_type"],
        report_date_fmt=date_fmt,
        tickers=cfg["tickers"],
        sector=cfg["sector"],
        tags=cfg["tags"],
        read_time=cfg["read_time"],
        preset_key=preset_key,   # passed through for quality-gate sizing
        mdx_body=preset_mdx_body(preset_key, title, cfg["excerpt"]),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish Agent Adda HTML reports to the agentadda/www website.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        help="Publish a preset report type.",
    )
    mode.add_argument(
        "--all-daily",
        action="store_true",
        help="Publish all daily presets (sector_rotation, stage2_tracker, swing_playbook, eod_market).",
    )
    mode.add_argument(
        "--html",
        type=Path,
        help="Path to the HTML report (custom mode).",
    )

    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Report date (YYYY-MM-DD). Default: today.")
    parser.add_argument("--slug", help="URL slug (required for --html mode).")
    parser.add_argument("--title", help="Report title (required for --html mode).")
    parser.add_argument("--excerpt", help="Short description (required for --html mode).")
    parser.add_argument(
        "--type",
        dest="report_type",
        choices=["fo-alert", "deep-research", "portfolio-analysis", "morning-market", "midday-market"],
        help="Report type.",
    )
    parser.add_argument("--tickers", default="", help="Comma-separated NSE tickers.")
    parser.add_argument("--sector", default="All Sectors", help="Comma-separated sectors.")
    parser.add_argument("--tags", default="AI Analysis,NSE", help="Comma-separated tags.")
    parser.add_argument("--read-time", default="5 min read", help="Estimated read time.")

    parser.add_argument(
        "--www-repo",
        type=Path,
        default=Path(os.environ.get("AGENTADDA_WWW_REPO", str(DEFAULT_WWW_REPO))),
        help="Path to the agentadda/www repo. Default: ~/Documents/Projects/agentadda-www",
    )
    parser.add_argument("--no-pull", action="store_true", help="Skip git pull on www repo.")
    parser.add_argument("--push", action="store_true", help="Push to GitHub after committing.")
    parser.add_argument(
        "--allow-non-agentadda-www-git",
        action="store_true",
        help="Allow git add/commit/push in a repo that is not agentadda/www (not recommended).",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Skip the post-publish email notification. Notifications are sent by default when --push is used.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the quality gate and push even if errors are found. Not recommended.",
    )

    args = parser.parse_args()

    www_repo = args.www_repo.expanduser().resolve()
    if args.push and not args.dry_run:
        # Safety: only allow pushing when repo is agentadda/www unless explicitly overridden.
        if not _is_agentadda_www_repo(www_repo) and not args.allow_non_agentadda_www_git:
            parser.error("--push is only allowed for agentadda/www (use --allow-non-agentadda-www-git to override).")

    # Ensure www repo is available
    if not args.dry_run:
        if not args.no_pull:
            ensure_www_repo(www_repo)
    else:
        print(f"  [dry-run] www repo: {www_repo}")

    # Determine which reports to publish
    to_publish: list[dict] = []

    if args.all_daily:
        for key in ("sector_rotation", "stage2_tracker", "swing_playbook", "eod_market"):
            to_publish.append(preset_to_args(key, args.date))

    elif args.preset:
        to_publish.append(preset_to_args(args.preset, args.date))

    else:  # custom --html mode
        if not args.slug:
            parser.error("--slug is required with --html")
        if not args.title:
            parser.error("--title is required with --html")
        if not args.excerpt:
            parser.error("--excerpt is required with --html")
        if not args.report_type:
            parser.error("--type is required with --html")

        dt = datetime.strptime(args.date, "%Y-%m-%d")
        to_publish.append(dict(
            html_source=str(args.html),
            slug=args.slug,
            title=args.title,
            date_iso=args.date,
            excerpt=args.excerpt,
            report_type=args.report_type,
            report_date_fmt=dt.strftime("%-d %b %Y"),
            tickers=[t.strip() for t in args.tickers.split(",") if t.strip()],
            sector=[s.strip() for s in args.sector.split(",") if s.strip()],
            tags=[t.strip() for t in args.tags.split(",") if t.strip()],
            read_time=args.read_time,
            mdx_body=f"{args.title}\n\n{args.excerpt}\n\nGenerated by AgentAdda. Not investment advice.",
        ))

    # Publish each
    errors: list[str] = []
    for spec in to_publish:
        html_path = (ROOT / spec["html_source"]).resolve()
        if not html_path.exists():
            msg = f"HTML not found: {html_path}"
            print(f"  ⚠ {msg}")
            errors.append(msg)
            continue
        llm_body = llm_mdx_summary_body(
            spec.get("preset_key", ""),
            spec["title"],
            spec["excerpt"],
            html_path,
        )
        if llm_body:
            spec["mdx_body"] = llm_body

        print(f"\n→ Publishing: {spec['slug']}")
        try:
            published = publish_report(
                html_path=html_path,
                slug=spec["slug"],
                title=spec["title"],
                date_iso=spec["date_iso"],
                excerpt=spec["excerpt"],
                report_type=spec["report_type"],
                report_date_fmt=spec["report_date_fmt"],
                tickers=spec["tickers"],
                sector=spec["sector"],
                tags=spec["tags"],
                read_time=spec["read_time"],
                mdx_body=spec["mdx_body"],
                www_repo=www_repo,
                dry_run=args.dry_run,
                push=args.push,
                preset_key=spec.get("preset_key", ""),
                force=args.force,
                allow_non_agentadda_www_git=bool(args.allow_non_agentadda_www_git),
            )
        except Exception as exc:
            print(f"  ✗ Failed: {exc}")
            errors.append(str(exc))
            continue

        if not published:
            errors.append(f"{spec['slug']} blocked by quality gate")
            continue

        if args.dry_run:
            if args.push and not args.no_notify:
                print(f"  [dry-run] would notify configured recipients for {notification_report_key(spec)}")
            continue

        if args.push and not args.no_notify:
            notified = notify_published_report(
                report_key=notification_report_key(spec),
                title=spec["title"],
                slug=spec["slug"],
            )
            if not notified:
                errors.append(f"{spec['slug']} published but notification failed")
        elif args.push:
            print("  [notify] skipped by --no-notify")

    if errors:
        print(f"\n✗ {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"\n✅ Done — {len(to_publish) - len(errors)} report(s) published.")
    if not args.push and not args.dry_run:
        print("   Re-run with --push to deploy to Cloudflare.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
