"""
Send the latest NSE Market Report via email (Gmail SMTP) as an HTML attachment.
"""
import os
import glob
import sys
import smtplib
from pathlib import Path
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


def get_latest_report() -> Path | None:
    root = Path(__file__).parent.parent
    files = sorted(glob.glob(str(root / "reports" / "NSE_Market_Report_*.html")), reverse=True)
    return Path(files[0]) if files else None


def send_email(report_path: Path) -> None:
    smtp_host = "smtp.gmail.com"
    smtp_port = 587
    from_addr = os.environ["EMAIL_FROM"]
    to_addr   = os.environ["EMAIL_TO"]
    password  = os.environ["EMAIL_PASSWORD"]

    date_str = datetime.utcnow().strftime("%d %b %Y")

    msg = MIMEMultipart("mixed")
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg["Subject"] = f"NSE Auto Components Report — {date_str}"

    body = MIMEText(f"""Hi,

Please find attached the NSE Auto Components Intelligence Report for {date_str}.

Report covers:
• Auto Components sector — top 15 composite shortlist
• Fundamental + Technical + RS scoring
• Backtest summary & sector context

Open the attached HTML file in your browser to view the full interactive report.

—
Unified NSE Analysis Pipeline
For research use only. Not investment advice.
""", "plain")
    msg.attach(body)

    # Attach the HTML report
    with open(report_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{report_path.name}"')
    msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(from_addr, password)
        server.sendmail(from_addr, to_addr, msg.as_string())

    print(f"Email sent to {to_addr} with attachment {report_path.name}")


def main() -> None:
    report_path = get_latest_report()
    if not report_path:
        print("No report found — skipping email.")
        sys.exit(0)

    print(f"Sending report: {report_path.name}")
    send_email(report_path)


if __name__ == "__main__":
    main()
