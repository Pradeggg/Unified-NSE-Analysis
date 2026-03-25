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


def get_latest_report() -> Path | None:
    reports_dir = Path(__file__).parent.parent / "reports"
    pattern = str(reports_dir / "NSE_Market_Report_*.html")
    files = sorted(glob.glob(pattern), reverse=True)
    return Path(files[0]) if files else None


def build_message(report_path: Path, report_url: str) -> str:
    date_str = datetime.utcnow().strftime("%d %b %Y")
    report_name = report_path.stem  # e.g. NSE_Market_Report_20260325

    return (
        f"*NSE Market Intelligence Report — {date_str}*\n\n"
        f"📊 Auto-generated after market close (NSE)\n\n"
        f"*Report covers:*\n"
        f"• NSE Universe (803 stocks) — BUY signals, index dashboard, top-ranked stocks\n"
        f"• Auto Components sector deep-dive — top 15 shortlist, backtest summary\n\n"
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
    report_path = get_latest_report()
    if not report_path:
        print("No report found — skipping WhatsApp notification.")
        sys.exit(0)

    # Build a public GitHub raw URL pointing to main branch
    repo = os.environ.get("GITHUB_REPOSITORY", "pradeggg/unified-nse-analysis")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    report_url = (
        f"https://htmlpreview.github.io/?"
        f"https://raw.githubusercontent.com/{repo}/{branch}/reports/{report_path.name}"
    )

    message = build_message(report_path, report_url)
    send_whatsapp(message)


if __name__ == "__main__":
    main()
