# Agent Adda — Installation Guide

A ship-anywhere bundle for the Agent Adda NSE analysis platform: PostgreSQL-backed
EOD + intraday data, an agentic REPL with LLM/voice/web-search, and end-of-day
HTML/email reports.

> All API keys are **optional**. The agent runs in degraded mode without them.
> Only PostgreSQL is required.

---

## 1. One-line install (recommended)

From the project root:

```bash
./installer/install.sh
```

This will:

1. Detect your OS and verify required system binaries (Python 3.11+, `psql`, `ffmpeg`*).
2. Create `.venv/` and install all pip dependencies from `requirements.txt`.
3. Install Playwright Chromium (used for HTML→PDF report rendering).
4. Hand off to [`installer/setup_wizard.py`](setup_wizard.py) which:
   * Prompts for API keys and writes `.env` (chmod 600, existing values preserved).
   * Tests the PostgreSQL connection (offers to create the DB + role).
   * Applies idempotent migrations from `postgres/*.sql`.
   * Optionally installs `launchd` / `systemd` units for daily refresh + intraday capture.
   * Runs the [`doctor.py`](doctor.py) health check.

> *`ffmpeg` is only needed if you intend to use voice input/output (`/listen`).

### Common flags

```bash
./installer/install.sh --check         # diagnose only, change nothing
./installer/install.sh --skip-system   # skip OS-binary check (already provisioned)
./installer/install.sh --skip-wizard   # bootstrap venv + pip only
```

---

## 2. System requirements

| OS              | Required                            | Optional                        |
| --------------- | ----------------------------------- | ------------------------------- |
| **macOS 12+**   | Homebrew, Python 3.11+, PostgreSQL  | ffmpeg (voice), R (EOD ETL)     |
| **Linux**       | apt/dnf, Python 3.11+, PostgreSQL   | ffmpeg, R, systemd              |
| **Windows**     | Use **WSL2 + Ubuntu** (no native)   | —                               |

PostgreSQL must be reachable. Default DSN: `dbname=nse_market user=nse_admin host=/tmp`
(unix socket on macOS Homebrew installs).

---

## 3. API keys & integrations

All optional. `setup_wizard.py` asks for each; you can re-run it anytime to add more.

| Env-var               | Used by                                  | Where to get                                 |
| --------------------- | ---------------------------------------- | -------------------------------------------- |
| `OPENAI_API_KEY`      | LLM agent backend                        | https://platform.openai.com/api-keys         |
| `OLLAMA_HOST`         | Local LLM (no cloud)                     | https://ollama.com (run `ollama serve`)      |
| `SERPAPI_API_KEY`     | Web search (catalysts, news)             | https://serpapi.com                          |
| `ANTHROPIC_API_KEY`   | Sector-rotation narratives (Claude)      | https://console.anthropic.com                |
| `SMTP_HOST` + creds   | Email reports (`email_nse_reports.py`)   | your SMTP provider (Gmail app password, etc) |

If neither `OPENAI_API_KEY` nor `OLLAMA_HOST` is set, the agent will fall back to
deterministic templated answers and `doctor.py` will warn.

---

## 4. After install

```bash
# Run the agent
.venv/bin/python nse_agent.py

# Daily EOD refresh (also scheduled by launchd if you opted in)
.venv/bin/python daily_refresh.py

# Re-run the wizard (e.g. to add an API key)
.venv/bin/python installer/setup_wizard.py

# Health check (read-only)
.venv/bin/python installer/doctor.py
```

Or via the Makefile:

```bash
make -C installer help
make -C installer agent
make -C installer doctor
```

---

## 5. Background services

The wizard offers to install always-on services so `intraday.quote_snapshots`
stays current and `daily_refresh.py` runs at 16:15 IST on weekdays even when
the REPL isn't open.

### macOS — launchd

Templates: [`installer/launchd/`](launchd/) (placeholders `__VENV__`, `__ROOT__`).
The wizard renders them into `~/Library/LaunchAgents/` and loads via `launchctl`.

```bash
launchctl list | grep agentadda             # check status
tail -f /tmp/agentadda_capture.log          # live log
make -C installer services-uninstall        # remove
```

### Linux — systemd (user units)

Templates: [`installer/systemd/`](systemd/).

```bash
make -C installer services-install
systemctl --user status agentadda-intraday-capture.service
journalctl --user -u agentadda-intraday-capture.service -f
```

---

## 6. Manual install (fallback)

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
playwright install --with-deps chromium       # optional, for PDF reports

cp installer/.env.template .env               # then edit values
psql -d postgres -c "CREATE DATABASE nse_market OWNER nse_admin;"
psql -d nse_market -f postgres/<each migration>.sql

python installer/doctor.py
python nse_agent.py
```

---

## 7. Troubleshooting

| Symptom                                          | First step                                             |
| ------------------------------------------------ | ------------------------------------------------------ |
| `psycopg2.OperationalError: could not connect`   | Verify `PG_DSN`; on macOS check `brew services list`   |
| `playwright: Executable doesn't exist`           | `.venv/bin/playwright install chromium`                |
| `/recap` returns a single stock brief            | (fixed — but if it recurs) ensure `nse_agent.py` is up |
| Agent says "Sources: SQLite intraday/live..."    | (fixed) — rebuild `.venv` or pull latest               |
| Intraday quote_snapshots stops updating          | `launchctl list \| grep capture`; check `/tmp/agentadda_capture.log` |
| Tests fail                                       | `make -C installer test` then read failing trace       |

Run `python installer/doctor.py` first — it surfaces 90 % of issues with a
single PASS/WARN/FAIL summary.

---

## 8. Uninstall

```bash
make -C installer uninstall      # removes .venv + services; preserves .env, data, reports
```

To also drop the database: `dropdb nse_market` (PostgreSQL stays installed).

---

## 9. Layout

```
installer/
├── install.sh                 # OS bootstrap + venv + pip
├── setup_wizard.py            # interactive .env + PG + services
├── doctor.py                  # read-only health check
├── Makefile                   # convenience targets
├── INSTALL.md                 # ← you are here
├── .env.template              # auto-generated by wizard
├── launchd/
│   ├── com.agentadda.daily_refresh.plist.tmpl
│   └── com.agentadda.intraday_capture.plist.tmpl
└── systemd/
    ├── agentadda-daily-refresh.service
    ├── agentadda-daily-refresh.timer
    └── agentadda-intraday-capture.service
```
