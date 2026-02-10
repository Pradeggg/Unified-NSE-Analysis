#!/usr/bin/env python3
"""
Email NSE Analysis Reports to distribution list.
- Use --outlook to compose in Microsoft Outlook on this Mac (no credentials needed).
- Otherwise uses SMTP (set EMAIL_USER and EMAIL_PASSWORD).
"""

import os
import sys
import smtplib
import subprocess
import tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

# Recipients (Deloitte)
RECIPIENTS = [
    "avsen@deloitte.com",      # Sen, Avirup
    "hikhan@deloitte.com",     # Khan, Hina Tabassum
    "mbinjola@deloitte.com",   # Binjola, Maheshanand
    "hibhatia@deloitte.com",   # Bhatia, Hitesh
    "amahale@deloitte.com",    # Mahale, Ashish
    "kchouhan@deloitte.com",   # Chouhan, Kapil
]

# Script directory = project root
SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = SCRIPT_DIR / "reports"

# Default report files (latest as of script creation; use --latest to auto-detect)
DEFAULT_REPORT_FILES = [
    "NSE_Interactive_Dashboard_20260205_20260206_103033.html",
    "NSE_Long_Term_Screeners_20260205_20260206_103033.html",
    "NIFTY500_Market_Breadth_20260206_103136.html",
    "NSE_Analysis_Report_20260205_20260206_103033.md",
    "comprehensive_nse_enhanced_05022026_20260206_103033.csv",
]

# SMTP (Office 365)
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_USER = os.environ.get("EMAIL_USER", "")  # e.g. your.name@deloitte.com
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD") or os.environ.get("EMAIL_APP_PASSWORD", "")

# Subject and body (report_date_str can be overridden when building from latest reports)
DEFAULT_REPORT_DATE = "5 Feb 2026"


def _format_report_date_from_paths(report_paths: list) -> str:
    """Derive report date string from latest report filename (e.g. 20260205 -> 5 Feb 2026)."""
    if not report_paths:
        return DEFAULT_REPORT_DATE
    from datetime import datetime
    name = Path(report_paths[0]).stem
    # Try YYYYMMDD in filename (e.g. 20260205)
    for part in name.split("_"):
        if len(part) == 8 and part.isdigit():
            try:
                d = datetime.strptime(part, "%Y%m%d")
                day = d.day
                return f"{day} {d.strftime('%b %Y')}"  # 5 Feb 2026
            except ValueError:
                pass
    # Try DDMMYYYY (e.g. 05022026)
    for part in name.split("_"):
        if len(part) == 8 and part.isdigit():
            try:
                d = datetime.strptime(part, "%d%m%Y")
                return f"{d.day} {d.strftime('%b %Y')}"
            except ValueError:
                pass
    return DEFAULT_REPORT_DATE


def get_email_content(report_paths: list):
    """Return (subject, body) for the email. Uses report date from paths when available."""
    report_date = _format_report_date_from_paths(report_paths)
    subject = f"NSE Analysis Reports – {report_date}"
    body = f"""Dear Team,

Please find attached the latest NSE (National Stock Exchange) analysis reports. Data is as of {report_date}.

----------------------------------------------------------------------
  ATTACHMENTS
----------------------------------------------------------------------

  *  NSE Interactive Dashboard (HTML)
     Technical scores, trading signals, and stock rankings.

  *  NSE Long-Term Screeners (HTML)
     Long-term patterns, momentum breakouts, and screeners.

  *  NIFTY500 Market Breadth (HTML)
     Percentage of stocks above/below key moving averages (20/50/100/200 DMA).

  *  NSE Analysis Report (Markdown)
     Executive summary and top performers.

  *  Comprehensive NSE Enhanced (CSV)
     Full results for further analysis in Excel.

----------------------------------------------------------------------
  HOW TO USE
----------------------------------------------------------------------

  *  HTML files  →  Open in a web browser (Chrome, Edge, Safari) for
     interactive dashboards and filters.

  *  CSV file    →  Open in Excel or any spreadsheet tool for sorting
     and filtering.

  *  Markdown    →  View in any text editor or Markdown viewer.

----------------------------------------------------------------------

This is an automated distribution. For questions on methodology or
data, please reach out to the analysis team.

Best regards,
NSE Analysis
"""
    return subject, body


def find_latest_reports():
    """Find latest report files by pattern (most recent by date in filename)."""
    patterns = [
        "NSE_Interactive_Dashboard_*.html",
        "NSE_Long_Term_Screeners_*.html",
        "NIFTY500_Market_Breadth_*.html",
        "NSE_Analysis_Report_*.md",
        "comprehensive_nse_enhanced_*.csv",
    ]
    found = []
    for pattern in patterns:
        matches = sorted(REPORTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            found.append(matches[0])
    return found


def build_message(sender: str, report_paths: list, subject: str, body: str) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    for filepath in report_paths:
        path = Path(filepath)
        if not path.is_file():
            print(f"Warning: skipping (not found): {path}", file=sys.stderr)
            continue
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        msg.attach(part)
        print(f"Attached: {path.name}")

    return msg


def _escape_applescript(s: str) -> str:
    """Escape string for use inside AppleScript double-quoted string (no newlines)."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "")


def send_via_outlook(report_paths: list, subject: str, body: str) -> None:
    """Compose a new message in Microsoft Outlook with recipients and attachments. User clicks Send."""
    if not report_paths:
        print("No report files to attach.", file=sys.stderr)
        sys.exit(1)
    subject_escaped = _escape_applescript(subject)
    # Body: use "line1" & return & "line2" so newlines work in Outlook
    body_lines = [line.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "") for line in body.split("\n")]
    body_escaped = " & return & ".join(f'"{ln}"' for ln in body_lines)
    # Attachment lines: set f to (POSIX file "/path"), make new attachment with properties {file:f}
    attachment_lines = []
    for i, path in enumerate(report_paths):
        path_str = str(Path(path).resolve())
        path_escaped = path_str.replace("\\", "\\\\").replace('"', '\\"')
        var = f"attFile{i}"
        attachment_lines.append(f'set {var} to (POSIX file "{path_escaped}")')
        attachment_lines.append(f'make new attachment at end of attachments with properties {{file:{var}}}')
    attachments_script = "\n        ".join(attachment_lines)
    # Recipient lines (inside tell newMessage)
    recipient_lines = []
    for addr in RECIPIENTS:
        recipient_lines.append(
            f'make new to recipient at end of to recipients with properties {{email address:{{address:"{addr}"}}}}'
        )
    recipients_script = "\n        ".join(recipient_lines)
    script = f'''tell application "Microsoft Outlook"
    set newMessage to make new outgoing message with properties {{subject:"{subject_escaped}", content:({body_escaped})}}
    tell newMessage
        {recipients_script}
        {attachments_script}
    end tell
    open newMessage
end tell
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False) as f:
        f.write(script)
        tmp = f.name
    try:
        result = subprocess.run(["osascript", tmp], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print("Outlook AppleScript error:", result.stderr or result.stdout, file=sys.stderr)
            sys.exit(1)
        print("Outlook opened with a new message. Review and click Send.")
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def send_email(use_latest: bool = False, report_files: list = None, subject: str = None, body: str = None):
    if report_files is None:
        report_files = []

    if use_latest:
        report_paths = find_latest_reports()
        if not report_paths:
            print("No latest reports found in", REPORTS_DIR, file=sys.stderr)
            sys.exit(1)
        print("Using latest reports:")
        for p in report_paths:
            print(" ", p.name)
    else:
        report_paths = [REPORTS_DIR / f for f in (report_files or DEFAULT_REPORT_FILES)]
        report_paths = [p for p in report_paths if p.exists()]
        if not report_paths:
            print("No report files found. Use --latest to auto-detect.", file=sys.stderr)
            sys.exit(1)

    if not EMAIL_USER or not EMAIL_PASSWORD:
        print(
            "Set EMAIL_USER and EMAIL_PASSWORD (or EMAIL_APP_PASSWORD) in environment.\n"
            "Example: export EMAIL_USER=your.name@deloitte.com\n"
            "         export EMAIL_PASSWORD=your_password",
            file=sys.stderr,
        )
        sys.exit(1)

    if subject is None or body is None:
        subject, body = get_email_content([str(p) for p in report_paths])
    msg = build_message(EMAIL_USER, report_paths, subject, body)

    print(f"Sending to {len(RECIPIENTS)} recipients...")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, RECIPIENTS, msg.as_string())
        print("Email sent successfully.")
    except smtplib.SMTPAuthenticationError as e:
        print("SMTP authentication failed. Check EMAIL_USER and EMAIL_PASSWORD.", file=sys.stderr)
        print(e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print("Failed to send email:", e, file=sys.stderr)
        sys.exit(1)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Email NSE analysis reports")
    parser.add_argument(
        "--outlook",
        action="store_true",
        help="Open Microsoft Outlook with a new message (recipients + attachments). You click Send.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Auto-detect and use the latest report files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list recipients and attachments, do not send",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific report filenames (in reports/). Default: use built-in list.",
    )
    args = parser.parse_args()

    if args.latest:
        report_paths = find_latest_reports()
        report_list = [str(p) for p in report_paths]
    else:
        report_list = [str(REPORTS_DIR / f) for f in (args.files or DEFAULT_REPORT_FILES)]
        report_paths = [Path(p) for p in report_list if Path(p).exists()]

    report_path_list = [str(p) for p in report_paths]
    subject, body = get_email_content(report_path_list)

    print("Subject:", subject)
    print("Recipients:", ", ".join(RECIPIENTS))
    print("Attachments:")
    for p in report_paths:
        print(" ", p.name if isinstance(p, Path) else Path(p).name)

    if args.dry_run:
        print("\nDry run – no email sent.")
        return

    if args.outlook:
        send_via_outlook(report_path_list, subject, body)
        return

    send_email(use_latest=args.latest, report_files=args.files or None, subject=subject, body=body)


if __name__ == "__main__":
    main()
