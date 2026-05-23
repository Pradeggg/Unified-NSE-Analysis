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
import subprocess
import textwrap
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
    "portfolio":        "latest/portfolio.html",
    "seasonal":         "latest/seasonal_calendar.html",
    "calendar":         "latest/seasonal_calendar.html",
    "us":               "latest/us_market_report.html",
    "us-market":        "latest/us_market_report.html",
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
    note: str = ""              # optional user-supplied context for LLM
    dry_run: bool = False
    extra_attachments: list[Path] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.report_path is not None and bool(self.to)


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in re.split(r"[,;\s]+", value or "") if v.strip()]


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
        elif low in {"--note", "--context", "-n"}:
            i += 1
            cmd.note = tokens[i] if i < len(tokens) else ""
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


def send_via_outlook(
    subject: str,
    html_body: str,
    to_addrs: list[str],
    bcc_addrs: list[str],
    attachments: list[Path],
    send_immediately: bool,
) -> str:
    """Compose (and optionally send) the email via Microsoft Outlook on macOS.

    Returns a short status string.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    body_path = LOG_DIR / f"_email_body_{datetime.now():%Y%m%d_%H%M%S}.html"
    body_path.write_text(html_body, encoding="utf-8")

    final_action = "send newMsg" if send_immediately else "open newMsg"
    to_block  = _applescript_recipients("to",  to_addrs)
    bcc_block = _applescript_recipients("bcc", bcc_addrs)

    subj_e        = subject.replace('"', '\\"')
    body_path_str = str(body_path).replace('"', '\\"')
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

    script = f'''
set htmlBody to (do shell script "cat " & quoted form of "{body_path_str}")
tell application "Microsoft Outlook"
    activate
    set newMsg to make new outgoing message with properties {{subject:"{subj_e}"}}
    set content of newMsg to htmlBody
{to_block}
{bcc_block}
{attach_block}
    {final_action}
end tell
'''

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
    }


def email_command_usage() -> str:
    """Help text shown when /email is invoked with no args or bad args."""
    return textwrap.dedent("""\
        /email <report> --to a@x.com[,b@y.com] [--bcc c@z.com] [--as body|attachment|both] [--send] [--note "..."]

        Recipients: comma, semicolon or whitespace separated (e.g. "a@x.com;b@y.com").
        Reports:
          sector | stage2 | index | portfolio | seasonal | us
          dashboard | market | pulse        (auto-picks newest reports/dashboards/market_dashboard_*.html)
          <path-to-file>                    (absolute or project-relative)
        Modes:
          --as body         Inline LLM-rendered HTML body (no attachment)
          --as attachment   Attach report + LLM cover note
          --as both         Default. Attach report + LLM exec summary in body
        Flags:
          --send            Send immediately (default opens as draft for review)
          --dry-run         Render body to logs/, don't touch Outlook
          --note "..."      Extra context for the LLM composer
          --attach <path>   Extra file to attach (repeatable; adds to the report)

        Examples:
          /email sector --to pgorai@deloitte.com
          /email dashboard --to "a@x.com;b@y.com" --send
          /email stage2 --to a@x.com --bcc b@y.com,c@z.com --send
          /email reports/latest/index_intelligence.html --to a@x.com --as body --send
    """)
