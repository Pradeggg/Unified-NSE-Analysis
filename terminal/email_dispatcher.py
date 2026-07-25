"""terminal/email_dispatcher.py — `/email` slash-command capability for Agent Adda.

Sends Agent Adda reports via Microsoft Outlook (macOS AppleScript) with an
LLM-generated subject + well-formatted HTML body.  Two delivery modes:

  • body        — extract report text and let the LLM render an inline HTML
                  email body (no attachment).
  • attachment  — attach the report file and let the LLM write a short
                  cover-note body summarizing why it matters.
  • both        — default; attach the file AND embed an exec-summary body.

Identity: ShunyaAI-CodingAgent / Optimus  •  Added 2026-05-19 (first-class /email).
"""

from __future__ import annotations

import os
import re
import shlex
import mimetypes
import smtplib
import subprocess
import textwrap
from html import unescape
from email.message import EmailMessage as MimeEmailMessage
from email.utils import formataddr
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
LATEST_DIR = REPORTS_DIR / "latest"
DASHBOARDS_DIR = REPORTS_DIR / "dashboards"
GENERATED_DIR = REPORTS_DIR / "generated"
LOG_DIR = ROOT / "logs"

# Friendly report aliases → glob/path under reports/latest/ (or reports/)
REPORT_ALIASES: dict[str, str] = {
    "sector":           "latest/sector_rotation.html",
    "sector-rotation":  "latest/sector_rotation.html",
    "sector_rotation":  "latest/sector_rotation.html",
    "rotation":         "latest/sector_rotation.html",
    "stage2":           "latest/stage2_tracker.html",
    "stage2-tracker":   "latest/stage2_tracker.html",
    "stage2_tracker":   "latest/stage2_tracker.html",
    "tracker":          "latest/stage2_tracker.html",
    "index":            "latest/index_intelligence.html",
    "index-intel":      "latest/index_intelligence.html",
    "index_intelligence": "latest/index_intelligence.html",
    "portfolio":            "latest/portfolio.html",
    "portfolio-analysis":   "latest/portfolio_analysis.html",
    "portfolio_analysis":   "latest/portfolio_analysis.html",
    "my-portfolio":         "latest/portfolio_analysis.html",
    "strategy-lab":         "latest/portfolio_strategy_lab.html",
    "strategy_lab":     "latest/portfolio_strategy_lab.html",
    "portfolio-strategy": "latest/portfolio_strategy_lab.html",
    "paper-trading":    "latest/portfolio_strategy_lab.html",
    "seasonal":         "latest/seasonal_calendar.html",
    "calendar":         "latest/seasonal_calendar.html",
    "us":               "latest/us_market_report.html",
    "us-market":        "latest/us_market_report.html",
    "eod":              "latest/eod_market_report.html",
    "eod-market":       "latest/eod_market_report.html",
    "eod_market":       "latest/eod_market_report.html",
    "market-eod":       "latest/eod_market_report.html",
    "market_eod":       "latest/eod_market_report.html",
    "eod-market-report": "latest/eod_market_report.html",
    "rrg":               "latest/market_breadth_rrg.html",
    "breadth":           "latest/market_breadth_rrg.html",
    "market-breadth":    "latest/market_breadth_rrg.html",
    "market_breadth":    "latest/market_breadth_rrg.html",
    "rrg-report":        "latest/market_breadth_rrg.html",
    "rotation-graph":    "latest/market_breadth_rrg.html",
}

# Dynamic aliases: resolved at lookup time via the configured glob (newest match
# wins). Use these for outputs that land with a timestamp suffix and don't have
# a stable "latest" copy.
DYNAMIC_REPORT_ALIASES: dict[str, tuple[Path, str]] = {
    "dashboard":        (DASHBOARDS_DIR, "market_dashboard_*.html"),
    "market":           (DASHBOARDS_DIR, "market_dashboard_*.html"),
    "market-dashboard": (DASHBOARDS_DIR, "market_dashboard_*.html"),
    "market_dashboard": (DASHBOARDS_DIR, "market_dashboard_*.html"),
    "pulse":            (DASHBOARDS_DIR, "market_dashboard_*.html"),
    "market-pulse":     (DASHBOARDS_DIR, "market_dashboard_*.html"),
    # PG 2026-05-31: Top Investment Picks Analysis — newest dated file wins.
    "top_picks":        (REPORTS_DIR / "top_picks", "Top_Investment_Picks_Analysis_*.html"),
    "top-picks":        (REPORTS_DIR / "top_picks", "Top_Investment_Picks_Analysis_*.html"),
    "picks":            (REPORTS_DIR / "top_picks", "Top_Investment_Picks_Analysis_*.html"),
    "investment-picks": (REPORTS_DIR / "top_picks", "Top_Investment_Picks_Analysis_*.html"),
    "top_picks_report": (REPORTS_DIR / "top_picks", "Top_Investment_Picks_Analysis_*.html"),
}

# Default sender signature appended to bodies
SIGNATURE_BLOCK = textwrap.dedent("""\
    <br><br>
    <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#555;">
      Regards,<br>
      <b>Agent Adda</b><br>
      <span style="color:#888;font-size:12px;">ShunyaAI · NSE Market Intelligence</span>
    </p>
""")

# ─────────────────────────────────────────────────────────────────────────────
# Command parsing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EmailCommand:
    report_arg: str = ""
    report_path: Path | None = None
    to: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    mode: str = "both"          # body | attachment | both
    send: bool = False          # if False → open as Outlook draft for review
    subject: str = ""           # optional user-supplied subject override
    note: str = ""              # optional user-supplied context for LLM
    dry_run: bool = False
    extra_attachments: list[Path] = field(default_factory=list)
    error: str = ""
    # PG 2026-05-27: when the report is a dashboard alias, generate a fresh
    # /dashboard HTML before emailing instead of reusing the newest cached file.
    # --cached opts back into the old behavior. --drilldown passes through to
    # _write_market_dashboard_html() so the email matches `/dashboard --drilldown`.
    use_cached: bool = False
    drilldown: bool = False

    @property
    def ok(self) -> bool:
        # PG 2026-05-27: dashboard aliases may have report_path=None at parse
        # time — run_email_command() will generate a fresh dashboard before sending.
        if self.error or not self.to:
            return False
        if self.report_path is not None:
            return True
        return _is_dashboard_alias(self.report_arg)


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in re.split(r"[,;\s]+", value or "") if v.strip()]


# PG 2026-05-27: aliases that map to the live /dashboard generator. Kept in sync
# with DYNAMIC_REPORT_ALIASES — single source of truth for "is this a dashboard".
_DASHBOARD_ALIASES: set[str] = {
    "dashboard",
    "dash",
    "market",
    "market-dashboard",
    "market_dashboard",
    "pulse",
    "market-pulse",
}


def _is_dashboard_alias(arg: str) -> bool:
    """True if `arg` is a /dashboard alias eligible for fresh generation."""
    return (arg or "").strip().lower() in _DASHBOARD_ALIASES


def _generate_fresh_dashboard(agent: Any, *, drilldown: bool = False, focus: str = "") -> Path:
    """Run the same code path as `/dashboard --once --html` and return the new HTML path.

    PG 2026-05-27: `/email dashboard` now defaults to fresh generation so the
    email always matches what `/dashboard` would show, not a stale cached file.
    Lazy-imports nse_agent to avoid the circular dependency (nse_agent imports
    this module for the /email handler).
    """
    # Lazy import — nse_agent imports email_dispatcher at module load.
    import nse_agent as _na  # type: ignore

    backend = getattr(agent, "backend", None) if agent is not None else None
    if backend is None:
        snapshot = _na._fetch_market_dashboard_snapshot(focus)
    else:
        snapshot = _na._fetch_market_dashboard_snapshot(focus, llm_backend=backend)
    return _na._write_market_dashboard_html(snapshot, drilldown=drilldown, open_browser=False)


def parse_email_command(text: str) -> EmailCommand:
    """Parse `/email <report> --to ... [--bcc ...] [--as body|attachment|both] [--send] [--note "..."]`."""
    cmd = EmailCommand()
    # Strip the slash command prefix.
    raw = re.sub(r"^\s*/email\b", "", text or "", flags=re.IGNORECASE).strip()
    if not raw:
        cmd.error = "missing arguments"
        return cmd

    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        cmd.error = f"could not parse command ({exc})"
        return cmd

    i = 0
    positional: list[str] = []
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if low in {"--to", "-t"}:
            i += 1
            cmd.to.extend(_split_csv(tokens[i]) if i < len(tokens) else [])
        elif low in {"--bcc", "-b"}:
            i += 1
            cmd.bcc.extend(_split_csv(tokens[i]) if i < len(tokens) else [])
        elif low in {"--cc"}:
            # CC not separately supported — fold into TO for now.
            i += 1
            cmd.to.extend(_split_csv(tokens[i]) if i < len(tokens) else [])
        elif low in {"--as", "--mode"}:
            i += 1
            cmd.mode = (tokens[i] if i < len(tokens) else "both").lower()
        elif low == "--body":
            cmd.mode = "body"
        elif low == "--attachment":
            cmd.mode = "attachment"
        elif low == "--both":
            cmd.mode = "both"
        elif low == "--send":
            cmd.send = True
        elif low == "--draft":
            cmd.send = False
        elif low == "--dry-run":
            cmd.dry_run = True
        elif low == "--cached":
            # PG 2026-05-27: opt back into the old behavior (newest cached dashboard).
            cmd.use_cached = True
        elif low == "--fresh":
            # PG 2026-05-27: explicit fresh-generation flag (now the default for
            # dashboard aliases). Accepted for parity with /dashboard semantics.
            cmd.use_cached = False
        elif low == "--drilldown":
            # PG 2026-05-27: pass through to the dashboard generator so the email
            # matches what `/dashboard --drilldown` would render.
            cmd.drilldown = True
        elif low in {"--note", "--context", "-n"}:
            i += 1
            cmd.note = tokens[i] if i < len(tokens) else ""
        elif low in {"--subject", "--subj", "-s"}:
            i += 1
            cmd.subject = tokens[i] if i < len(tokens) else ""
        elif low in {"--attach", "--attachment-file", "-a"}:
            # PG 2026-05-20: repeatable extra attachment (in addition to the
            # resolved report). Lets /screenshot attach PNG + terminal context.
            i += 1
            if i < len(tokens):
                ap = Path(tokens[i]).expanduser()
                if not ap.is_absolute():
                    ap = (ROOT / ap).resolve()
                if not ap.exists():
                    cmd.error = f"--attach path does not exist: {ap}"
                    return cmd
                cmd.extra_attachments.append(ap)
        elif tok.startswith("--"):
            cmd.error = f"unknown flag: {tok}"
            return cmd
        else:
            positional.append(tok)
        i += 1

    if not positional:
        cmd.error = "missing <report> argument (e.g. sector, stage2, or a path)"
        return cmd

    cmd.report_arg = positional[0]
    cmd.report_path = resolve_report(cmd.report_arg)
    if cmd.report_path is None:
        # PG 2026-05-27: dashboard aliases resolve later via fresh generation
        # in run_email_command(); don't error here if there's no cached file yet.
        if not _is_dashboard_alias(cmd.report_arg):
            cmd.error = f"could not locate report '{cmd.report_arg}'"
            return cmd

    if cmd.mode not in {"body", "attachment", "both"}:
        cmd.error = f"--as must be one of: body | attachment | both (got '{cmd.mode}')"
        return cmd

    if not cmd.to:
        cmd.error = "no --to recipients supplied"
        return cmd

    return cmd


def resolve_report(key: str) -> Path | None:
    """Resolve a friendly key, filename, or path to an existing report file."""
    if not key:
        return None
    # Absolute / relative path (literal)
    p = Path(key)
    if p.is_absolute() and p.exists():
        return p
    # Relative to project root
    candidate = (ROOT / key).resolve()
    if candidate.exists():
        return candidate
    # Alias lookup
    alias = REPORT_ALIASES.get(key.lower())
    if alias:
        candidate = (REPORTS_DIR / alias).resolve()
        if candidate.exists():
            return candidate
    # Dynamic alias: newest file matching <dir>/<glob>
    dyn = DYNAMIC_REPORT_ALIASES.get(key.lower())
    if dyn:
        base_dir, pattern = dyn
        if base_dir.exists():
            matches = sorted(base_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            for m in matches:
                if m.is_file():
                    return m.resolve()
    # Direct match in reports/latest, reports/dashboards, reports/generated, reports/
    for sub in (LATEST_DIR, DASHBOARDS_DIR, GENERATED_DIR, REPORTS_DIR):
        if not sub.exists():
            continue
        for ext in (".html", ".md", ".pdf", ".txt"):
            cand = sub / f"{key}{ext}"
            if cand.exists():
                return cand
        # Glob fallback (handles dated filenames)
        for match in sorted(sub.glob(f"*{key}*"), reverse=True):
            if match.is_file() and match.suffix.lower() in {".html", ".md", ".pdf", ".txt"}:
                return match
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Report extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_report_text(path: Path, max_chars: int = 18000) -> str:
    """Return readable text from HTML / Markdown / TXT report (truncated)."""
    suffix = path.suffix.lower()
    # Image / binary attachments: skip text extraction — caller relies on the
    # filename + --note for LLM context.
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".heic"}:
        try:
            size_kb = path.stat().st_size / 1024
        except Exception:
            size_kb = 0
        return f"[image attachment: {path.name} ({size_kb:.0f} KB) — no text content]"
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return f"[error reading report: {exc}]"

    if suffix in {".md", ".txt"}:
        text = raw
    elif suffix == ".html":
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text("\n", strip=True)
        except Exception:
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(str(path))
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            text = f"[pdf extraction unavailable for {path.name}]"
    else:
        text = raw

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]"
    return text


# ─────────────────────────────────────────────────────────────────────────────
# LLM subject + body generation
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are Agent Adda's email composer. Produce a professional, executive-grade "
    "email about an NSE market research report. Output STRICT JSON with two keys: "
    '`subject` (concise <80 chars, no emojis, no quotes) and `html_body` '
    "(well-formatted HTML using inline styles only — no CSS classes, no <html> or "
    "<body> tags, Outlook-Mac safe). The HTML body MUST include: "
    "(1) a one-line market read at the top in a colored callout, "
    "(2) 3–6 key takeaways as a bulleted list, "
    "(3) a short 'What to watch' section, "
    "(4) a closing 'Action items' or 'How to use this' block. "
    "Use only <p>, <ul>, <li>, <b>, <i>, <table>, <tr>, <td>, <div>, <span>, "
    "<br>, <h2>, <h3> with inline style attributes. No external images or links "
    "to anything outside the report. Keep the tone factual, no hype."
)


def _llm_generate(backend: Any, report_name: str, report_text: str, mode: str, note: str) -> tuple[str, str]:
    """Call the agent's LLM backend to draft subject + html_body. Returns (subject, html_body)."""
    user_prompt = textwrap.dedent(f"""
        Report file: {report_name}
        Delivery mode: {mode}  (body=inline only · attachment=cover note for an attached file · both=cover note + summary)
        Extra context from the user: {note or '(none)'}

        Below is the extracted text from the report. Compose the email based on this content.
        ──────────────── REPORT BEGIN ────────────────
        {report_text}
        ───────────────── REPORT END ─────────────────

        Respond with STRICT JSON only — no prose before or after. Schema:
        {{
          "subject": "<concise subject line>",
          "html_body": "<inline-styled HTML email body>"
        }}
    """).strip()

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]
    try:
        resp = backend.chat(messages)
    except Exception as exc:
        return _fallback_subject_body(report_name, report_text, reason=f"LLM error: {exc}")

    content = (resp.get("content") or "").strip()
    # The LLM sometimes wraps JSON in code fences — strip them.
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    try:
        import json
        data = json.loads(content)
        subject = (data.get("subject") or "").strip() or f"Agent Adda — {report_name}"
        html_body = (data.get("html_body") or "").strip()
        if not html_body:
            return _fallback_subject_body(report_name, report_text, reason="LLM returned empty body")
        return subject[:160], html_body
    except Exception as exc:
        return _fallback_subject_body(report_name, report_text, reason=f"JSON parse failed: {exc}")


def _fallback_subject_body(report_name: str, report_text: str, reason: str = "") -> tuple[str, str]:
    """Deterministic, LLM-free fallback so /email never fails completely."""
    today = datetime.now().strftime("%a, %d %b %Y")
    snippet = report_text[:1200].replace("<", "&lt;").replace(">", "&gt;")
    subject = f"Agent Adda — {report_name} ({today})"
    body = textwrap.dedent(f"""
        <p style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222;">
          Sharing the latest <b>{report_name}</b> from Agent Adda (snapshot {today}).
          {('<br><i style="color:#888;font-size:12px;">[fallback render: ' + reason + ']</i>') if reason else ''}
        </p>
        <pre style="font-family:Menlo,Consolas,monospace;font-size:12px;background:#f6f8fa;
                    padding:12px;border-left:3px solid #2b6cb0;white-space:pre-wrap;color:#222;">
{snippet}
        </pre>
    """).strip()
    return subject, body


def _top_picks_explainer_html() -> str:
    """Deterministic explainer appended to Top Picks emails.

    The LLM can summarize this away when the report is attached. Keep this
    block deterministic so recipients always see the selection logic in the
    email body, not only inside the attachment.
    """
    return textwrap.dedent("""
        <div style="font-family:Arial,Helvetica,sans-serif;border:1px solid #dbeafe;
                    border-left:4px solid #2563eb;background:#f8fbff;
                    padding:14px 16px;margin:16px 0;border-radius:8px;color:#1f2937;">
          <h3 style="margin:0 0 8px;font-size:16px;color:#1e3a8a;">
            How the Top Picks are identified
          </h3>
          <p style="margin:0 0 10px;font-size:13px;line-height:1.55;">
            The Top Picks list is a research shortlist built from multiple independent confirmations,
            not a single buy signal. The ranking looks for stocks where market structure, sector
            leadership, price action, strategy evidence, fundamentals, and risk/reward point in the
            same direction.
          </p>
          <table cellpadding="0" cellspacing="0" border="0" width="100%"
                 style="border-collapse:collapse;font-size:13px;line-height:1.5;">
            <tr>
              <td style="padding:6px 8px;border-top:1px solid #e5e7eb;width:34%;font-weight:bold;color:#334155;">
                Sector rotation
              </td>
              <td style="padding:6px 8px;border-top:1px solid #e5e7eb;color:#334155;">
                Preference goes to strong stocks inside leading sectors, not isolated one-day movers.
              </td>
            </tr>
            <tr>
              <td style="padding:6px 8px;border-top:1px solid #e5e7eb;font-weight:bold;color:#334155;">
                Weinstein Stage 2 / VCP
              </td>
              <td style="padding:6px 8px;border-top:1px solid #e5e7eb;color:#334155;">
                Stage 2 means an advancing uptrend after a base; VCP means volatility has contracted
                before a potential breakout.
              </td>
            </tr>
            <tr>
              <td style="padding:6px 8px;border-top:1px solid #e5e7eb;font-weight:bold;color:#334155;">
                Portfolio Strategy Lab
              </td>
              <td style="padding:6px 8px;border-top:1px solid #e5e7eb;color:#334155;">
                Extra weight is given when the best-ranked paper strategy marks the stock as an open
                position or next BUY.
              </td>
            </tr>
            <tr>
              <td style="padding:6px 8px;border-top:1px solid #e5e7eb;font-weight:bold;color:#334155;">
                Risk and quality checks
              </td>
              <td style="padding:6px 8px;border-top:1px solid #e5e7eb;color:#334155;">
                The final rank considers relative strength, trend quality, targets, stop-loss,
                reward-to-risk, leverage, profitability, cash-flow quality, and valuation.
              </td>
            </tr>
          </table>
          <h3 style="margin:14px 0 8px;font-size:15px;color:#1e3a8a;">
            Weinstein stage framework
          </h3>
          <ul style="margin:0 0 10px;padding-left:18px;font-size:13px;line-height:1.55;color:#334155;">
            <li><b>Stage 1 - Base / Accumulation:</b> sideways action after a decline; watchlist phase.</li>
            <li><b>Stage 2 - Advancing / Uptrend:</b> breakout above the base with rising averages and improving relative strength; preferred long-only buying zone.</li>
            <li><b>Stage 3 - Top / Distribution:</b> volatility near highs and fading momentum; caution phase.</li>
            <li><b>Stage 4 - Decline / Downtrend:</b> price below key averages with lower highs/lows; usually avoided by long-only systems.</li>
          </ul>
          <p style="margin:0;font-size:12px;line-height:1.5;color:#64748b;">
            A high-ranked pick is a research shortlist candidate, not direct investment advice.
            Use the attached report for the full chart, fundamentals, targets, stops, and risk details.
          </p>
        </div>
    """).strip()


def _is_top_picks_key(report_key: str) -> bool:
    return report_key.lower() in {
        "top_picks", "top-picks", "picks", "investment-picks", "top_picks_report"
    }


def _ensure_top_picks_body_explainer(html_body: str) -> str:
    marker = "How the Top Picks are identified"
    if marker.lower() in (html_body or "").lower():
        return html_body
    return (html_body or "") + _top_picks_explainer_html()


# ─────────────────────────────────────────────────────────────────────────────
# HTML envelope
# ─────────────────────────────────────────────────────────────────────────────

def _wrap_envelope(html_body: str, report_path: Path, mode: str) -> str:
    """Wrap the LLM-generated body in a consistent header/footer."""
    today = datetime.now().strftime("%a, %d %b %Y · %H:%M IST")
    header = f"""
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="font-family:Arial,Helvetica,sans-serif;">
  <tr>
    <td style="background:#1a365d;color:#fff;padding:14px 18px;border-radius:6px 6px 0 0;">
      <span style="font-size:18px;font-weight:bold;letter-spacing:0.3px;">Agent Adda</span>
      <span style="float:right;font-size:12px;color:#cbd5e0;">{today}</span>
      <div style="font-size:13px;color:#cbd5e0;margin-top:4px;">
        Report · <b>{report_path.name}</b> · mode: <b>{mode}</b>
      </div>
    </td>
  </tr>
  <tr><td style="height:14px;"></td></tr>
</table>
""".strip()
    footer = SIGNATURE_BLOCK + (
        '<p style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#888;'
        'border-top:1px solid #eee;padding-top:8px;margin-top:14px;">'
        'Not investment advice. For research and learning only. NSE EOD + live snapshot data.'
        '</p>'
    )
    return header + html_body + footer


# ─────────────────────────────────────────────────────────────────────────────
# Outlook (macOS) dispatch
# ─────────────────────────────────────────────────────────────────────────────

def _applescript_recipients(rec_type: str, addrs: list[str]) -> str:
    lines: list[str] = []
    for addr in addrs:
        a = addr.replace('"', '\\"')
        lines.append(
            f'    make new {rec_type} recipient at newMsg with properties '
            f'{{email address:{{name:"{a}", address:"{a}"}}}}'
        )
    return "\n".join(lines)


def _applemail_recipients(rec_type: str, addrs: list[str]) -> str:
    lines: list[str] = []
    for addr in addrs:
        a = addr.replace('"', '\\"')
        lines.append(
            f'        make new {rec_type} recipient at end of {rec_type} recipients '
            f'with properties {{address:"{a}"}}'
        )
    return "\n".join(lines)


def _ensure_html_document(html_body: str) -> str:
    """Return a complete HTML document for Outlook's HTML composer.

    Outlook for Mac is more reliable when AppleScript receives a full document
    instead of a fragment beginning with a bare <div>/<table>.
    """
    body = (html_body or "").strip()
    if re.search(r"<\s*html\b", body, flags=re.IGNORECASE):
        return body
    return (
        "<!doctype html>\n"
        "<html>\n"
        "<head>\n"
        '  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "</head>\n"
        '<body style="margin:0;padding:0;background:#ffffff;">\n'
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def _html_to_plain_text(html_body: str) -> str:
    """Small plain-text fallback for Outlook accounts not composing as HTML."""
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", html_body or "")
    text = re.sub(r"(?i)</\s*(p|div|tr|h[1-6]|li|table)\s*>", "\n", text)
    text = re.sub(r"(?is)<\s*style\b.*?</\s*style\s*>", "", text)
    text = re.sub(r"(?is)<\s*script\b.*?</\s*script\s*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _load_optional_dotenv() -> None:
    """Load .env when python-dotenv is installed; no-op otherwise."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    try:
        load_dotenv(ROOT / ".env")
    except Exception:
        return


def _email_provider() -> str:
    _load_optional_dotenv()
    provider = (
        os.getenv("AGENT_ADDA_EMAIL_PROVIDER")
        or os.getenv("EMAIL_PROVIDER")
        or "outlook"
    )
    return provider.strip().lower()


def _smtp_setting(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return default


def _smtp_config() -> dict[str, str | int | bool]:
    provider = _email_provider()
    gmail_mode = provider == "gmail"
    icloud_mode = provider == "icloud"
    host = _smtp_setting(
        "SMTP_HOST",
        default="smtp.gmail.com" if gmail_mode else "smtp.mail.me.com" if icloud_mode else "smtp.office365.com",
    )
    port_raw = _smtp_setting("SMTP_PORT", default="587")
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    user = _smtp_setting("SMTP_USER", "EMAIL_USER", "GMAIL_USER")
    password = _smtp_setting(
        "SMTP_PASSWORD",
        "EMAIL_PASSWORD",
        "EMAIL_APP_PASSWORD",
        "GMAIL_APP_PASSWORD",
    )
    from_addr = _smtp_setting("SMTP_FROM", "EMAIL_FROM", default=user)
    from_name = _smtp_setting("EMAIL_FROM_NAME", default="Agent Adda")
    use_tls_raw = _smtp_setting("SMTP_USE_TLS", default="1").lower()
    return {
        "provider": provider,
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_addr": from_addr,
        "from_name": from_name,
        "use_tls": use_tls_raw not in {"0", "false", "no", "off"},
    }


def send_via_smtp(
    *,
    subject: str,
    html_body: str,
    to_addrs: list[str],
    bcc_addrs: list[str],
    attachments: list[Path],
) -> str:
    """Send the email through SMTP.

    For Gmail, use a Google App Password with:
      AGENT_ADDA_EMAIL_PROVIDER=gmail
      SMTP_USER=agentadda.in@gmail.com
      SMTP_PASSWORD=<app password>

    For iCloud Mail, use an Apple app-specific password with:
      AGENT_ADDA_EMAIL_PROVIDER=icloud
      SMTP_USER=pgorai@icloud.com
      SMTP_PASSWORD=<app-specific password>
    """
    cfg = _smtp_config()
    host = str(cfg["host"])
    port = int(cfg["port"])
    user = str(cfg["user"] or "")
    password = str(cfg["password"] or "")
    from_addr = str(cfg["from_addr"] or user)
    from_name = str(cfg["from_name"] or "Agent Adda")
    use_tls = bool(cfg["use_tls"])
    recipients = list(dict.fromkeys(list(to_addrs or []) + list(bcc_addrs or [])))

    missing = [
        name
        for name, value in {
            "SMTP_USER": user,
            "SMTP_PASSWORD": password,
            "SMTP_FROM/EMAIL_FROM": from_addr,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "SMTP email provider is selected but required setting(s) are missing: "
            + ", ".join(missing)
            + ". For Gmail, set AGENT_ADDA_EMAIL_PROVIDER=gmail, "
            "SMTP_USER=agentadda.in@gmail.com and SMTP_PASSWORD to a Google App Password. "
            "For iCloud, set AGENT_ADDA_EMAIL_PROVIDER=icloud, SMTP_USER=pgorai@icloud.com "
            "and SMTP_PASSWORD to an Apple app-specific password."
        )
    if not recipients:
        raise RuntimeError("SMTP email has no recipients")

    html_document = _ensure_html_document(html_body)
    msg = MimeEmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_addr))
    msg["To"] = ", ".join(to_addrs or [])
    if bcc_addrs:
        msg["Bcc"] = ", ".join(bcc_addrs)
    msg.set_content(_html_to_plain_text(html_document))
    msg.add_alternative(html_document, subtype="html")

    for attachment in attachments or []:
        path = Path(attachment).resolve()
        if not path.exists() or not path.is_file():
            continue
        content_type, _ = mimetypes.guess_type(str(path))
        maintype, subtype = (content_type or "application/octet-stream").split("/", 1)
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )

    with smtplib.SMTP(host, port, timeout=45) as server:
        if use_tls:
            server.starttls()
        server.login(user, password)
        server.send_message(msg, from_addr=from_addr, to_addrs=recipients)
    return f"sent via SMTP as {from_addr}"


def _build_outlook_applescript(
    *,
    subject: str,
    html_body_path: Path,
    plain_body_path: Path,
    to_addrs: list[str],
    bcc_addrs: list[str],
    attachments: list[Path],
    send_immediately: bool,
) -> str:
    final_action = "send newMsg" if send_immediately else "open newMsg"
    to_block = _applescript_recipients("to", to_addrs)
    bcc_block = _applescript_recipients("bcc", bcc_addrs)

    subj_e = subject.replace('"', '\\"')
    html_path_str = str(html_body_path).replace('"', '\\"')
    plain_path_str = str(plain_body_path).replace('"', '\\"')
    attach_lines: list[str] = []
    for att in attachments or []:
        if att is None:
            continue
        att_str = str(att).replace('"', '\\"')
        attach_lines.append(
            f'    set attachPath to POSIX file "{att_str}"\n'
            f'    make new attachment at newMsg with properties {{file:attachPath}}'
        )
    attach_block = "\n".join(attach_lines)

    return f'''
set htmlBody to (do shell script "cat " & quoted form of "{html_path_str}")
set plainBody to (do shell script "cat " & quoted form of "{plain_path_str}")
tell application "Microsoft Outlook"
    activate
    set newMsg to make new outgoing message with properties {{subject:"{subj_e}"}}
    if has html of newMsg then
        set content of newMsg to htmlBody
    else
        set plain text content of newMsg to plainBody
    end if
{to_block}
{bcc_block}
{attach_block}
    {final_action}
end tell
'''


def _build_applemail_applescript(
    *,
    subject: str,
    html_body_path: Path,
    plain_body_path: Path,
    to_addrs: list[str],
    bcc_addrs: list[str],
    attachments: list[Path],
    send_immediately: bool,
    sender: str = "",
) -> str:
    final_action = "send newMsg" if send_immediately else "set visible of newMsg to true"
    to_block = _applemail_recipients("to", to_addrs)
    bcc_block = _applemail_recipients("bcc", bcc_addrs)

    subj_e = subject.replace('"', '\\"')
    sender_e = sender.replace('"', '\\"').strip()
    html_path_str = str(html_body_path).replace('"', '\\"')
    plain_path_str = str(plain_body_path).replace('"', '\\"')
    sender_line = f'    set sender of newMsg to "{sender_e}"' if sender_e else ""
    attach_lines: list[str] = []
    for att in attachments or []:
        if att is None:
            continue
        att_str = str(att).replace('"', '\\"')
        attach_lines.append(
            f'        set attachPath to POSIX file "{att_str}"\n'
            f'        make new attachment with properties {{file name:attachPath}} at after the last paragraph'
        )
    attach_block = "\n".join(attach_lines)

    return f'''
set htmlBody to (do shell script "cat " & quoted form of "{html_path_str}")
set plainBody to (do shell script "cat " & quoted form of "{plain_path_str}")
tell application "Mail"
    activate
    set newMsg to make new outgoing message with properties {{subject:"{subj_e}", content:plainBody, visible:true}}
{sender_line}
    tell newMsg
{to_block}
{bcc_block}
{attach_block}
    end tell
    {final_action}
end tell
'''


def send_via_outlook(
    subject: str,
    html_body: str,
    to_addrs: list[str],
    bcc_addrs: list[str],
    attachments: list[Path],
    send_immediately: bool,
) -> str:
    """Compose (and optionally send) email.

    Default provider is Microsoft Outlook on macOS. Set
    AGENT_ADDA_EMAIL_PROVIDER=gmail, icloud, or smtp to send through SMTP instead.
    Set AGENT_ADDA_EMAIL_PROVIDER=applemail to compose/send through Apple Mail.

    Returns a short status string.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    body_path = LOG_DIR / f"_email_body_{datetime.now():%Y%m%d_%H%M%S}.html"
    plain_path = LOG_DIR / f"_email_body_{datetime.now():%Y%m%d_%H%M%S}.txt"
    html_document = _ensure_html_document(html_body)
    body_path.write_text(html_document, encoding="utf-8")
    plain_path.write_text(_html_to_plain_text(html_document), encoding="utf-8")

    provider = _email_provider()
    if provider in {"applemail", "mail", "apple_mail"}:
        sender = _smtp_setting("APPLEMAIL_ACCOUNT", "SMTP_FROM", "EMAIL_FROM")
        script = _build_applemail_applescript(
            subject=subject,
            html_body_path=body_path,
            plain_body_path=plain_path,
            to_addrs=to_addrs,
            bcc_addrs=bcc_addrs,
            attachments=attachments,
            send_immediately=send_immediately,
            sender=sender,
        )
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Apple Mail AppleScript failed:\n{result.stderr}")
        return "sent via Apple Mail" if send_immediately else "draft opened in Apple Mail"

    if provider in {"gmail", "icloud", "smtp"}:
        if not send_immediately:
            return (
                f"{provider} draft unavailable; preview written to {body_path}. "
                "Use --send to send through SMTP, or set AGENT_ADDA_EMAIL_PROVIDER=outlook "
                "to open an Outlook draft."
            )
        return send_via_smtp(
            subject=subject,
            html_body=html_document,
            to_addrs=to_addrs,
            bcc_addrs=bcc_addrs,
            attachments=attachments,
        )

    script = _build_outlook_applescript(
        subject=subject,
        html_body_path=body_path,
        plain_body_path=plain_path,
        to_addrs=to_addrs,
        bcc_addrs=bcc_addrs,
        attachments=attachments,
        send_immediately=send_immediately,
    )

    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Outlook AppleScript failed:\n{result.stderr}")
    return "sent" if send_immediately else "draft opened in Outlook"


# ─────────────────────────────────────────────────────────────────────────────
# Top-level entry point — invoked by nse_agent.py slash handler
# ─────────────────────────────────────────────────────────────────────────────

def run_email_command(text: str, agent: Any) -> dict:
    """Parse + dispatch a `/email ...` invocation. Returns a status dict.

    Status dict keys: ok (bool), message (str), subject, body_path (str), mode, recipients
    """
    cmd = parse_email_command(text)
    if not cmd.ok:
        return {"ok": False, "message": cmd.error or "command failed"}

    # PG 2026-05-27: For dashboard aliases, generate a fresh /dashboard HTML by
    # default so the email matches what `/dashboard` would render right now,
    # not a stale cached file. --cached opts back into the old behavior.
    fresh_generated = False
    if _is_dashboard_alias(cmd.report_arg) and not cmd.use_cached:
        try:
            cmd.report_path = _generate_fresh_dashboard(
                agent, drilldown=cmd.drilldown, focus=""
            )
            fresh_generated = True
        except Exception as exc:
            # Fall back to the newest cached dashboard if generation fails
            # (e.g. NSE allIndices unreachable). Surface the reason in --note.
            fallback = resolve_report(cmd.report_arg)
            if fallback is None:
                return {
                    "ok": False,
                    "message": (
                        f"fresh dashboard generation failed and no cached file "
                        f"found: {exc}"
                    ),
                }
            cmd.report_path = fallback
            cmd.note = (
                (cmd.note + " | " if cmd.note else "")
                + f"NOTE: fresh dashboard generation failed ({exc}); "
                  f"emailing newest cached file."
            )

    if cmd.report_path is None:
        return {"ok": False, "message": f"could not locate report '{cmd.report_arg}'"}

    report_text = extract_report_text(cmd.report_path)
    backend = getattr(agent, "backend", None)
    if backend is None:
        subject, body_html = _fallback_subject_body(cmd.report_path.name, report_text, reason="no LLM backend")
    else:
        subject, body_html = _llm_generate(
            backend,
            cmd.report_path.name,
            report_text,
            mode=cmd.mode,
            note=cmd.note,
        )
    if _is_top_picks_key(cmd.report_arg):
        body_html = _ensure_top_picks_body_explainer(body_html)
    if cmd.subject:
        subject = cmd.subject[:160]
    full_body = _wrap_envelope(body_html, cmd.report_path, cmd.mode)

    if cmd.dry_run:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        preview = LOG_DIR / f"_email_preview_{datetime.now():%Y%m%d_%H%M%S}.html"
        preview.write_text(full_body, encoding="utf-8")
        return {
            "ok": True,
            "dry_run": True,
            "message": f"dry-run · preview written to {preview}",
            "subject": subject,
            "body_path": str(preview),
            "mode": cmd.mode,
            "recipients": {"to": cmd.to, "bcc": cmd.bcc},
        }

    attachments: list[Path] = []
    if cmd.mode in {"attachment", "both"}:
        attachments.append(cmd.report_path)
    for extra in cmd.extra_attachments:
        if extra not in attachments:
            attachments.append(extra)
    # PG 2026-05-27: Outlook AppleScript `POSIX file` needs ABSOLUTE paths or
    # the attachment is silently skipped. Fresh-generated dashboards come back
    # as relative paths (reports/dashboards/...), so resolve every attachment
    # to an absolute path before handing off.
    attachments = [p.resolve() for p in attachments]
    status = send_via_outlook(
        subject=subject,
        html_body=full_body,
        to_addrs=cmd.to,
        bcc_addrs=cmd.bcc,
        attachments=attachments,
        send_immediately=cmd.send,
    )
    return {
        "ok": True,
        "dry_run": False,
        "message": status,
        "subject": subject,
        "body_path": "",
        "mode": cmd.mode,
        "recipients": {"to": cmd.to, "bcc": cmd.bcc},
        "report": str(cmd.report_path),
        "attachments": [str(p) for p in attachments],
        # PG 2026-05-27: tells the caller whether we ran /dashboard fresh or
        # fell back to a cached file.
        "fresh_generated": fresh_generated,
    }


def email_command_usage() -> str:
    """Help text shown when /email is invoked with no args or bad args."""
    return textwrap.dedent("""\
        /email <report> --to a@x.com[,b@y.com] [--bcc c@z.com] [--as body|attachment|both] [--send] [--note "..."]

        Recipients: comma, semicolon or whitespace separated (e.g. "a@x.com;b@y.com").
        Reports:
          sector | stage2 | index | portfolio | seasonal | us
          dashboard | market | pulse        (runs /dashboard fresh by default; --cached uses newest reports/dashboards/market_dashboard_*.html)
          <path-to-file>                    (absolute or project-relative)
        Modes:
          --as body         Inline LLM-rendered HTML body (no attachment)
          --as attachment   Attach report + LLM cover note
          --as both         Default. Attach report + LLM exec summary in body
        Flags:
          --send            Send immediately (default opens as draft for review)
          --dry-run         Render body to logs/, don't touch Outlook
          --subject "..."   Override the generated email subject
          --note "..."      Extra context for the LLM composer
          --attach <path>   Extra file to attach (repeatable; adds to the report)
          --cached          For dashboard aliases: skip fresh generation, use newest cached file
          --fresh           Force fresh dashboard generation (default for dashboard aliases)
          --drilldown       Pass through to /dashboard generator (more detail in HTML)

        Examples:
          /email sector --to pgorai@deloitte.com
          /email dashboard --to "a@x.com;b@y.com" --send
          /email stage2 --to a@x.com --bcc b@y.com,c@z.com --send
          /email reports/latest/index_intelligence.html --to a@x.com --as body --send

        Sender:
          Default uses Outlook. To send from Gmail SMTP, set:
            AGENT_ADDA_EMAIL_PROVIDER=gmail
            SMTP_USER=agentadda.in@gmail.com
            SMTP_PASSWORD=<Google App Password>
            SMTP_FROM=agentadda.in@gmail.com
          Gmail SMTP sends only with --send; without --send it writes a preview.
    """)


# ─────────────────────────────────────────────────────────────────────────────
# Programmatic helper for the daily refresh pipeline
# PG 2026-05-31: invoked by daily_refresh.step_email_top_picks (and CLI below)
# ─────────────────────────────────────────────────────────────────────────────

RECIPIENTS_YML = ROOT / "config" / "report_recipients.yml"


class _BackendShim:
    """Wraps a backend object so it exposes a `.backend` attribute (what
    `run_email_command`/`_llm_generate` expect from the agent parameter)."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend


def _load_recipients(report_key: str) -> dict[str, list[str]]:
    """Return {'to': [...], 'bcc': [...]} for `report_key` from
    config/report_recipients.yml. Empty lists if file/key missing."""
    out = {"to": [], "bcc": []}
    if not RECIPIENTS_YML.exists():
        return out
    try:
        import yaml  # type: ignore
    except Exception:
        return out
    try:
        data = yaml.safe_load(RECIPIENTS_YML.read_text(encoding="utf-8")) or {}
    except Exception:
        return out
    section = (data.get(report_key) or {}) if isinstance(data, dict) else {}
    if isinstance(section, dict):
        out["to"]  = [str(x) for x in (section.get("to")  or []) if x]
        out["bcc"] = [str(x) for x in (section.get("bcc") or []) if x]
    return out


def _build_default_backend() -> Any | None:
    """Try to construct an OpenAI backend (falls back to None → fallback body)."""
    try:
        from terminal.agent import _OpenAIBackend  # type: ignore
        return _OpenAIBackend()
    except Exception as exc:
        print(f"   ⚠️  email composer LLM unavailable ({exc}) — using fallback body")
        return None


def send_report_email(
    report_key: str,
    *,
    mode: str = "both",
    send: bool = False,
    subject: str = "",
    note: str = "",
    extra_to: list[str] | None = None,
    extra_bcc: list[str] | None = None,
    backend: Any | None = None,
) -> dict:
    """Compose + dispatch an email for a friendly report key using the
    recipients configured in config/report_recipients.yml.

    Returns the same status dict as run_email_command(); `ok=False` if no
    recipients are configured or the report can't be located.
    """
    report_path = resolve_report(report_key)
    if report_path is None:
        return {"ok": False, "message": f"could not locate report '{report_key}'"}

    rec = _load_recipients(report_key)
    to_addrs  = list(dict.fromkeys((rec["to"]  or []) + list(extra_to  or [])))
    bcc_addrs = list(dict.fromkeys((rec["bcc"] or []) + list(extra_bcc or [])))
    if not to_addrs and not bcc_addrs:
        return {
            "ok": False,
            "message": (
                f"no recipients configured for '{report_key}' in "
                f"{RECIPIENTS_YML.relative_to(ROOT)} — add a 'to:' or 'bcc:' list"
            ),
        }

    report_text = extract_report_text(report_path)
    # PG 2026-05-31: top_picks-specific guidance so the LLM email body
    # leads with the picks, sector tilt, risk, and 2M/4M/6M targets.
    is_top_picks = _is_top_picks_key(report_key)
    if is_top_picks and not note:
        note = (
            "This is the daily Top Investment Picks Analysis. The email body must: "
            "(a) open with a 1-line market read and the snapshot date, "
            "(b) list each top pick (symbol · sector · entry · 2M/4M/6M targets · stop-loss · R:R · risk tier) "
            "in a compact <table> with bold headers, "
            "(c) include a 'Why these picks' bulleted rationale tying back to sector rotation + stage-2 + fundamentals, "
            "(d) a 'Risks & what could go wrong' bullet block, "
            "(e) a 'How to use this report' closing block instructing the reader to open the attached HTML "
            "for full TradingView-style charts, pattern annotations, RSI, volume profile, support/resistance, "
            "fundamental scores (Piotroski/Altman/Beneish/CANSLIM), valuation, and the LLM chart narrative. "
            "Keep tone factual, no hype. Do NOT invent numbers — only use values present in the report text."
        )
    agent_shim = _BackendShim(backend if backend is not None else _build_default_backend())
    if agent_shim.backend is None:
        subj_gen, body_html = _fallback_subject_body(
            report_path.name, report_text, reason="no LLM backend"
        )
    else:
        subj_gen, body_html = _llm_generate(
            agent_shim.backend, report_path.name, report_text, mode=mode, note=note
        )
    if is_top_picks:
        body_html = _ensure_top_picks_body_explainer(body_html)
    final_subject = (subject[:160] if subject else subj_gen)
    full_body = _wrap_envelope(body_html, report_path, mode)

    attachments: list[Path] = []
    if mode in {"attachment", "both"}:
        attachments.append(report_path.resolve())

    try:
        status = send_via_outlook(
            subject=final_subject,
            html_body=full_body,
            to_addrs=to_addrs,
            bcc_addrs=bcc_addrs,
            attachments=attachments,
            send_immediately=send,
        )
    except Exception as exc:
        return {"ok": False, "message": f"Outlook dispatch failed: {exc}"}

    return {
        "ok": True,
        "message": status,
        "subject": final_subject,
        "mode": mode,
        "recipients": {"to": to_addrs, "bcc": bcc_addrs},
        "report": str(report_path),
        "attachments": [str(p) for p in attachments],
    }


def _cli_main(argv: list[str] | None = None) -> int:
    """`python -m terminal.email_dispatcher <report_key> [--send] [--mode both]`."""
    import argparse
    ap = argparse.ArgumentParser(
        description="Send a report email using config/report_recipients.yml."
    )
    ap.add_argument("report_key", help="alias such as top_picks, sector, dashboard, …")
    ap.add_argument("--mode", default="both", choices=["body", "attachment", "both"])
    ap.add_argument("--send", action="store_true",
                    help="send immediately (default: open as Outlook draft)")
    ap.add_argument("--subject", default="", help="override generated subject")
    ap.add_argument("--note", default="", help="extra context for the LLM composer")
    ap.add_argument("--to",  default="", help="extra To: addresses (comma/semicolon-separated)")
    ap.add_argument("--bcc", default="", help="extra Bcc: addresses (comma/semicolon-separated)")
    args = ap.parse_args(argv)

    extra_to  = _split_csv(args.to)  if args.to  else []
    extra_bcc = _split_csv(args.bcc) if args.bcc else []

    result = send_report_email(
        args.report_key,
        mode=args.mode,
        send=args.send,
        subject=args.subject,
        note=args.note,
        extra_to=extra_to,
        extra_bcc=extra_bcc,
    )
    if not result.get("ok"):
        print(f"❌ {result.get('message')}")
        return 1
    rec = result.get("recipients", {})
    print(f"✅ {result.get('message')}")
    print(f"   Subject : {result.get('subject')}")
    print(f"   To      : {', '.join(rec.get('to')  or []) or '—'}")
    print(f"   Bcc     : {', '.join(rec.get('bcc') or []) or '—'}")
    print(f"   Report  : {result.get('report')}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli_main(sys.argv[1:]))
