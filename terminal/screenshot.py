"""terminal/screenshot.py — `/screenshot` slash-command capability for Agent Adda.

Captures a screenshot via macOS `screencapture`, then dispatches /email with the
image as attachment + LLM-drafted cover note via the existing email_dispatcher.

Modes (--mode):
  interactive  Default. User drags a selection box (screencapture -i).
  window       User clicks a window (screencapture -W).
  full         Full screen, all displays (screencapture).
  delayed      Full screen, 5-second delay (screencapture -T 5).

Added 2026-05-20 (PG): one-step capture-and-mail with LLM cover note.
"""
from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from terminal.email_dispatcher import (
    SIGNATURE_BLOCK,  # noqa: F401  (re-used for body envelope by email_dispatcher)
    run_email_command,
)

ROOT = Path(__file__).resolve().parent.parent
SHOTS_DIR = ROOT / "reports" / "screenshots"


@dataclass
class ScreenshotCommand:
    to: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    mode: str = "interactive"      # interactive | window | full | delayed
    send: bool = False
    note: str = ""
    dry_run: bool = False
    no_email: bool = False         # capture-only, no /email dispatch
    output: Path | None = None     # explicit output path
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and (self.no_email or bool(self.to))


_VALID_MODES = {"interactive", "window", "full", "delayed"}


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in re.split(r"[,;\s]+", value or "") if v.strip()]


def parse_screenshot_command(text: str) -> ScreenshotCommand:
    """Parse `/screenshot [--to ...] [--bcc ...] [--mode ...] [--send] [--note "..."] [--dry-run] [--no-email] [--out path]`."""
    cmd = ScreenshotCommand()
    raw = re.sub(r"^\s*/screenshot\b", "", text or "", flags=re.IGNORECASE).strip()
    try:
        tokens = shlex.split(raw) if raw else []
    except ValueError as exc:
        cmd.error = f"could not parse command ({exc})"
        return cmd

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if low in {"--to", "-t"}:
            i += 1
            cmd.to.extend(_split_csv(tokens[i]) if i < len(tokens) else [])
        elif low in {"--bcc", "-b"}:
            i += 1
            cmd.bcc.extend(_split_csv(tokens[i]) if i < len(tokens) else [])
        elif low in {"--mode", "-m"}:
            i += 1
            cmd.mode = (tokens[i] if i < len(tokens) else "interactive").lower()
        elif low in {"--interactive", "--select"}:
            cmd.mode = "interactive"
        elif low == "--window":
            cmd.mode = "window"
        elif low == "--full":
            cmd.mode = "full"
        elif low in {"--delayed", "--timer"}:
            cmd.mode = "delayed"
        elif low == "--send":
            cmd.send = True
        elif low == "--draft":
            cmd.send = False
        elif low == "--dry-run":
            cmd.dry_run = True
        elif low == "--no-email":
            cmd.no_email = True
        elif low in {"--note", "--context", "-n"}:
            i += 1
            cmd.note = tokens[i] if i < len(tokens) else ""
        elif low in {"--out", "-o"}:
            i += 1
            cmd.output = Path(tokens[i]).expanduser() if i < len(tokens) else None
        elif tok.startswith("--"):
            cmd.error = f"unknown flag: {tok}"
            return cmd
        else:
            cmd.error = f"unexpected token: {tok}"
            return cmd
        i += 1

    if cmd.mode not in _VALID_MODES:
        cmd.error = f"--mode must be one of: {sorted(_VALID_MODES)} (got '{cmd.mode}')"
        return cmd
    if not cmd.no_email and not cmd.to:
        cmd.error = "no --to recipients supplied (use --no-email to capture only)"
        return cmd
    return cmd


def _capture(out_path: Path, mode: str) -> tuple[bool, str]:
    """Invoke macOS screencapture. Returns (ok, message)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "interactive":
        argv = ["screencapture", "-i", str(out_path)]
        prompt = "drag a selection box on screen…"
    elif mode == "window":
        argv = ["screencapture", "-W", str(out_path)]
        prompt = "click the window to capture…"
    elif mode == "full":
        argv = ["screencapture", str(out_path)]
        prompt = "capturing full screen…"
    elif mode == "delayed":
        argv = ["screencapture", "-T", "5", str(out_path)]
        prompt = "capturing full screen in 5 seconds…"
    else:
        return False, f"unknown mode: {mode}"

    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError:
        return False, "screencapture not found (macOS only)"
    except Exception as exc:
        return False, f"screencapture failed: {exc}"

    if not out_path.exists() or out_path.stat().st_size == 0:
        # User cancelled (e.g. Esc in interactive mode) — screencapture exits 0
        # but writes no file.
        return False, f"no file written (cancelled?) — stderr: {proc.stderr.strip() or 'n/a'}"
    return True, prompt


def run_screenshot_command(text: str, agent: Any) -> dict:
    """Parse + dispatch `/screenshot ...`. Returns a status dict.

    Status dict keys: ok (bool), message (str), screenshot (path),
                      email (dict from email_dispatcher) | None
    """
    cmd = parse_screenshot_command(text)
    if not cmd.ok:
        return {"ok": False, "message": cmd.error or "command failed"}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = cmd.output or (SHOTS_DIR / f"screenshot_{cmd.mode}_{ts}.png")

    ok, prompt = _capture(out_path, cmd.mode)
    if not ok:
        return {"ok": False, "message": prompt, "screenshot": str(out_path)}

    result: dict = {
        "ok": True,
        "screenshot": str(out_path),
        "mode": cmd.mode,
        "size_kb": round(out_path.stat().st_size / 1024, 1),
    }
    if cmd.no_email:
        result["message"] = f"saved screenshot to {out_path} ({result['size_kb']} KB)"
        return result

    # PG 2026-05-20: capture the prior REPL turn's terminal output (styled HTML)
    # and use it as the body-source attachment so the LLM cover note describes
    # what the user was actually looking at — not just the PNG filename.
    context_path: Path | None = None
    try:
        from terminal.renderer import get_last_turn_capture
        ctx_html, ctx_text = get_last_turn_capture()
    except Exception:
        ctx_html, ctx_text = "", ""
    if (ctx_text or "").strip():
        ctx_header = (
            "<div style=\"font-family:Arial,Helvetica,sans-serif;"
            "padding:12px 16px;background:#1a365d;color:#fff;"
            "border-radius:6px;margin:0 0 14px 0;\">"
            "<div style=\"font-size:16px;font-weight:bold;\">"
            "Agent Adda · terminal context for screenshot</div>"
            f"<div style=\"font-size:12px;color:#cbd5e0;margin-top:4px;\">"
            f"<b>Screenshot:</b> {out_path.name} ({result['size_kb']} KB) · "
            f"mode: {cmd.mode} · captured: {datetime.now():%Y-%m-%d %H:%M:%S}"
            f"</div></div>"
        )
        ctx_doc = ctx_html or f"<pre>{ctx_text}</pre>"
        if "<body" in ctx_doc:
            ctx_doc = re.sub(
                r"(<body[^>]*>)", r"\1\n" + ctx_header, ctx_doc, count=1
            )
        else:
            ctx_doc = ctx_header + ctx_doc
        context_path = out_path.with_name(out_path.stem + "_context.html")
        try:
            context_path.write_text(ctx_doc, encoding="utf-8")
        except Exception:
            context_path = None

    # Hand off to /email. Two modes:
    #   • terminal context available → use it as the report (body summary) and
    #     attach the PNG as an extra attachment. Mode `both` = attach + summary.
    #   • no context (e.g. first-turn screenshot) → fall back to PNG-only with
    #     LLM cover note based on filename + --note.
    flags = ["--to", ",".join(cmd.to)]
    if cmd.bcc:
        flags += ["--bcc", ",".join(cmd.bcc)]
    if cmd.send and not cmd.dry_run:
        flags.append("--send")
    if cmd.dry_run:
        flags.append("--dry-run")
    note = cmd.note or f"Screenshot captured via /screenshot ({cmd.mode} mode) at {datetime.now():%Y-%m-%d %H:%M IST}."

    if context_path is not None:
        flags += ["--as", "both", "--attach", str(out_path)]
        primary = context_path
    else:
        flags += ["--as", "attachment"]
        primary = out_path

    email_cmd = f'/email {primary} {" ".join(flags)} --note {shlex.quote(note)}'
    email_result = run_email_command(email_cmd, agent)

    result["email"] = email_result
    result["context"] = str(context_path) if context_path else ""
    result["message"] = (
        f"screenshot saved ({result['size_kb']} KB) · "
        + (email_result.get("message", "email dispatch failed") if email_result.get("ok")
           else f"email failed: {email_result.get('message')}")
    )
    result["ok"] = bool(email_result.get("ok"))
    return result


def screenshot_command_usage() -> str:
    return (
        "/screenshot --to a@x.com [--bcc b@y.com] [--mode interactive|window|full|delayed] "
        "[--send] [--note \"...\"] [--dry-run] [--no-email] [--out <path>]\n\n"
        "Modes:\n"
        "  interactive  Default — drag a selection box (Esc to cancel)\n"
        "  window       Click a window to capture it\n"
        "  full         Full screen, all displays\n"
        "  delayed      Full screen, 5-second timer\n\n"
        "Flags:\n"
        "  --send        Send immediately (default opens Outlook draft for review)\n"
        "  --dry-run     Render preview HTML, don't touch Outlook\n"
        "  --no-email    Only capture to disk, skip email\n"
        "  --note \"…\"  Extra context appended to the LLM cover-note prompt\n"
        "  --out <path>  Custom output path (default: reports/screenshots/screenshot_<mode>_<ts>.png)\n\n"
        "Examples:\n"
        "  /screenshot --to pgorai@deloitte.com\n"
        "  /screenshot --mode window --to a@x.com --send\n"
        "  /screenshot --mode full --to \"a@x.com;b@y.com\" --note \"Stage 2 chart\" --send\n"
        "  /screenshot --no-email --out ~/Desktop/shot.png\n"
    )
