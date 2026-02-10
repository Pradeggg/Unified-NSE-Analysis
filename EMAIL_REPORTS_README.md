# Email NSE Reports

Send the latest NSE (National Stock Exchange) analysis reports to the distribution list. Supports **Microsoft Outlook on your Mac** (no credentials) or **SMTP** (direct send).

---

## Quick start (Outlook)

From the project root:

```bash
python3 email_nse_reports.py --outlook --latest
```

Outlook opens a new message with all recipients and attachments. Review and click **Send**. No passwords required.

---

## What gets sent

| Item | Description |
|------|-------------|
| **To** | Sen, Avirup; Khan, Hina Tabassum; Binjola, Maheshanand; Bhatia, Hitesh; Mahale, Ashish; Chouhan, Kapil |
| **Subject** | `NSE Analysis Reports – <date>` (e.g. 5 Feb 2026; date is taken from the latest report when using `--latest`) |
| **Body** | Short overview, list of attachments, how to use (open HTML in browser, CSV in Excel), sign-off |
| **Attachments** | Interactive Dashboard (HTML), Long-Term Screeners (HTML), Market Breadth (HTML), Analysis Report (MD), Enhanced results (CSV) |

The email body is generated automatically and includes a clear description of each attachment and how to open/use the files.

---

## Usage

| Command | Description |
|--------|-------------|
| `python3 email_nse_reports.py --outlook --latest` | **Recommended.** Open Outlook with the **latest** reports (auto-detected). |
| `python3 email_nse_reports.py --outlook` | Open Outlook with the default report set. |
| `python3 email_nse_reports.py --outlook --latest --dry-run` | Show recipients and attachments only; no Outlook window. |
| `python3 email_nse_reports.py --latest` | Send via **SMTP** (requires `EMAIL_USER` and `EMAIL_PASSWORD`). |

Use `--latest` so the script picks the most recent report files and sets the email subject date from them.

---

## Recipients

Configured in `email_nse_reports.py` (list `RECIPIENTS`):

- Sen, Avirup (avsen@deloitte.com)
- Khan, Hina Tabassum (hikhan@deloitte.com)
- Binjola, Maheshanand (mbinjola@deloitte.com)
- Bhatia, Hitesh (hibhatia@deloitte.com)
- Mahale, Ashish (amahale@deloitte.com)
- Chouhan, Kapil (kchouhan@deloitte.com)

To add or remove recipients, edit the `RECIPIENTS` list at the top of `email_nse_reports.py`.

---

## SMTP (optional)

To send directly without opening Outlook (e.g. from a server or script):

1. Set environment variables:

   ```bash
   export EMAIL_USER=your.name@deloitte.com
   export EMAIL_PASSWORD=your_password
   ```

2. Run:

   ```bash
   python3 email_nse_reports.py --latest
   ```

For Office 365 with MFA, use an **app password** as `EMAIL_PASSWORD`. Default SMTP: `smtp.office365.com:587`.

---

## Troubleshooting

| Issue | What to do |
|-------|------------|
| Outlook doesn’t open | Ensure **Microsoft Outlook** (not just Mail.app) is installed. The script uses AppleScript and targets "Microsoft Outlook". |
| “No report files found” | Run from the **project root** (where `reports/` lives). Use `--latest` to auto-detect the newest reports. |
| Wrong or old reports | Use `--latest` so the script finds the most recent files and sets the subject date from them. |
| AppleScript error | If the script fails with an AppleScript error, check that paths don’t contain characters that break quoting. Report paths are under `reports/` and usually have no special characters. |
| SMTP auth failed | Check `EMAIL_USER` and `EMAIL_PASSWORD`. For MFA, use an app password. |

---

## Attachments (when using `--latest`)

- **NSE_Interactive_Dashboard_*.html** – Technical scores and rankings
- **NSE_Long_Term_Screeners_*.html** – Long-term patterns and screeners
- **NIFTY500_Market_Breadth_*.html** – Market breadth (e.g. % above/below DMAs)
- **NSE_Analysis_Report_*.md** – Summary and top performers
- **comprehensive_nse_enhanced_*.csv** – Full results for analysis in Excel

Open HTML files in a browser; open the CSV in Excel or any spreadsheet tool.
