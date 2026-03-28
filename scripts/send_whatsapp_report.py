"""
Send the latest NSE Market Report via WhatsApp using Twilio.
Finds the most recently generated HTML report and sends a summary + public link.
"""
import os
import glob
import sys
from pathlib import Path
from datetime import datetime

from twilio.rest import Client


def get_latest_report() -> tuple[Path, str] | None:
    """Return (path, repo-relative-path) for the latest NSE market report."""
    root = Path(__file__).parent.parent
    files = sorted(glob.glob(str(root / "reports" / "NSE_Market_Report_*.html")), reverse=True)
    if not files:
        return None
    p = Path(files[0])
    return p, f"reports/{p.name}"


def build_message(report_path: Path, report_url: str) -> str:
    date_str = datetime.utcnow().strftime("%d %b %Y")
    return (
        f"*NSE Auto Components Report — {date_str}*\n\n"
        f"📊 Auto-generated after market close (NSE)\n\n"
        f"*Report covers:*\n"
        f"• Auto Components sector — top 15 composite shortlist\n"
        f"• Fundamental + Technical + RS scoring\n"
        f"• Backtest summary & sector context\n\n"
        f"🔗 *View report:*\n{report_url}\n\n"
        f"_For research use only. Not investment advice._"
    )


def send_whatsapp(message: str) -> None:
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = os.environ["TWILIO_FROM"]   # e.g. whatsapp:+14155238886
    to_number = os.environ["TWILIO_TO"]       # e.g. whatsapp:+919XXXXXXXXX

    client = Client(account_sid, auth_token)
    msg = client.messages.create(
        from_=from_number,
        to=to_number,
        body=message,
    )
    print(f"WhatsApp message sent. SID: {msg.sid}")


def main() -> None:
    result = get_latest_report()
    if not result:
        print("No report found — skipping WhatsApp notification.")
        sys.exit(0)

    report_path, repo_rel_path = result
    print(f"Sending report: {repo_rel_path}")

    repo = os.environ.get("GITHUB_REPOSITORY", "pradeggg/unified-nse-analysis")
    report_url = (
        f"https://htmlpreview.github.io/?"
        f"https://raw.githubusercontent.com/{repo}/main/{repo_rel_path}"
    )

    message = build_message(report_path, report_url)
    send_whatsapp(message)


if __name__ == "__main__":
    main()
