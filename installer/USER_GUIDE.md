# Agent Adda — Comprehensive User Guide

> **Audience:** end-users installing Agent Adda for the first time, operators
> running it day-to-day, and engineers debugging it.
>
> **Scope:** install → configure → run → tune → troubleshoot → uninstall.
>
> **Companion docs:** [INSTALL.md](INSTALL.md) (quick reference), [README.md](../README.md) (project overview).

---

## Table of Contents

1. [What you're installing](#1-what-youre-installing)
2. [Pre-flight checklist](#2-pre-flight-checklist)
3. [Installation paths](#3-installation-paths)
4. [Configuration: API keys & .env](#4-configuration-api-keys--env)
5. [PostgreSQL setup](#5-postgresql-setup)
6. [Running the agent](#6-running-the-agent)
7. [Background services](#7-background-services-launchd--systemd)
8. [Daily operations cheatsheet](#8-daily-operations-cheatsheet)
9. [Troubleshooting playbook](#9-troubleshooting-playbook)
10. [Performance tuning](#10-performance-tuning)
11. [Upgrading](#11-upgrading)
12. [Uninstall](#12-uninstall)
13. [FAQ](#13-faq)

---

## 1. What you're installing

Agent Adda is a market-intelligence agent for the NSE (Indian equities) with five layers:

| Layer | Tech | Required? |
|---|---|---|
| **EOD data store** | PostgreSQL (`market`, `scores`, `report` schemas) | ✅ yes |
| **Intraday capture** | Python daemon → `intraday.quote_snapshots` (60s tick) | ✅ yes |
| **Agent REPL** | `nse_agent.py` (prompt_toolkit) with slash commands | ✅ yes |
| **LLM backend** | OpenAI **or** local Ollama | ⚠ at least one |
| **Reports / email** | HTML + PDF (Playwright) + SMTP | optional |

Disk footprint: **~1.5 GB** (venv ~800 MB, Playwright Chromium ~400 MB, data grows ~50 MB/month).

---

## 2. Pre-flight checklist

| # | Requirement | macOS | Linux | Windows |
|---|---|---|---|---|
| 1 | Python 3.11+ | `brew install python@3.13` | `apt install python3.11 python3.11-venv` | use **WSL2** |
| 2 | PostgreSQL 14+ running | `brew install postgresql@16 && brew services start postgresql@16` | `apt install postgresql && sudo systemctl start postgresql` | inside WSL |
| 3 | Git | preinstalled | `apt install git` | inside WSL |
| 4 | Internet egress | required (NSE API + LLM) | required | required |
| 5 | (optional) `ffmpeg` | `brew install ffmpeg` | `apt install ffmpeg` | for `/listen` voice |
| 6 | (optional) `R` | `brew install r` | `apt install r-base` | for legacy R scripts |

Verify with:

```bash
python3 --version          # 3.11.0 or higher
psql --version             # 14 or higher
pg_isready                 # accepting connections
```

---

## 3. Installation paths

### 3a. One-line install (recommended)

```bash
git clone <repo-url> Unified-NSE-Analysis
cd Unified-NSE-Analysis
./installer/install.sh
```

This:
- Detects OS, installs missing system packages (Homebrew/apt/dnf).
- Creates `.venv` and installs ~128 pip packages.
- Optionally installs Playwright Chromium.
- Drops into the interactive wizard for `.env` + PostgreSQL + services.
- Runs `doctor.py` for a final green-light.

### 3b. Headless / CI install

```bash
./installer/install.sh --skip-system --skip-wizard --with-dev
.venv/bin/python installer/setup_wizard.py --non-interactive
```

`--with-dev` also installs `pytest` so `make -C installer test` works immediately.

### 3c. Manual install (full control)

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
pip install -r requirements-dev.txt        # optional, for tests
playwright install --with-deps chromium    # optional, for PDF reports

cp installer/.env.template .env
# edit .env — set PG_DSN at minimum

createdb nse_market
psql nse_market -f postgres/<each schema>.sql

python installer/doctor.py
```

### 3d. Re-run / repair

The installer is **fully idempotent**. Re-run any time after a `git pull`, machine restore, or to add an API key:

```bash
./installer/install.sh                          # full re-run
.venv/bin/python installer/setup_wizard.py      # re-prompt only
make -C installer install-deps                  # refresh pip deps only
make -C installer doctor                        # health check only
```

---

## 4. Configuration: API keys & .env

The wizard creates `.env` with **chmod 600** (owner-read only). Every key is optional except `PG_DSN`.

| Key | Required? | Used for | Where to obtain |
|---|---|---|---|
| `PG_DSN` | ✅ | All DB I/O | Local install |
| `OPENAI_API_KEY` | ⚠* | LLM agent backend | https://platform.openai.com/api-keys |
| `OPENAI_MODEL` | optional | LLM model name (default `gpt-4o`) | — |
| `OLLAMA_HOST` | ⚠* | Local LLM backend (free) | https://ollama.com — `ollama serve` |
| `OLLAMA_MODEL` | optional | Local model (default `granite4`) | `ollama pull granite4` |
| `SERPAPI_API_KEY` | optional | Web search for catalysts/news | https://serpapi.com |
| `ANTHROPIC_API_KEY` | optional | Claude sector-rotation narratives | https://console.anthropic.com |
| `SMTP_HOST` + creds | optional | Email reports | your SMTP provider |
| `AGENT_ADDA_CAPTURE_INTERVAL_SEC` | optional | Capture cadence (default 60) | — |
| `AGENT_ADDA_CAPTURE_RETENTION_MIN` | optional | Snapshot retention (default 120) | — |

*⚠ At least one of OpenAI / Ollama is needed for full LLM features. Without either,
the agent returns templated answers and the `_quality_check` layer flags the response.*

To add or change a key later:

```bash
.venv/bin/python installer/setup_wizard.py
# (existing values are preserved; press Enter to keep)
```

Or hand-edit `.env` and run `installer/doctor.py` to verify.

---

## 5. PostgreSQL setup

### 5a. Default DSN

```
dbname=nse_market user=nse_admin host=/tmp
```

`host=/tmp` uses the unix socket (typical for Homebrew Postgres on macOS). For
TCP/remote use:

```
dbname=nse_market user=nse_admin host=db.example.com port=5432 password=secret
```

### 5b. Provisioning

The wizard offers to run:

```sql
CREATE ROLE nse_admin LOGIN;
CREATE DATABASE nse_market OWNER nse_admin;
```

then applies every `.sql` file in `postgres/` (idempotent). Check what's loaded:

```bash
psql -d nse_market -c "\dn"               # list schemas
psql -d nse_market -c "\dt market.*"      # equity tables
psql -d nse_market -c "\dt intraday.*"    # quote_snapshots
```

### 5c. Verifying with doctor

`installer/doctor.py` checks 8 critical tables and prints row counts. A fresh
install will show 0 rows in `market.equity_eod` until you load data.

You have **three options** to populate the database:

**Option A — Restore a historical seed (≤ 2 minutes, ~60 MB tarball)**

```bash
./installer/restore_data_seed.sh agent-adda-data-*.tar.gz
```

If the distributor shipped you `agent-adda-data-<version>.tar.gz` alongside the
code bundle, this restores all historical EOD prices, scores, breadth and
reports in a single `pg_restore` call. Idempotent (`--clean --if-exists`).

**Option B — Bootstrap from scratch via daily_refresh (slow, free)**

```bash
.venv/bin/python daily_refresh.py    # ~5–8 minutes, today's data only
```

History grows organically; let the launchd/systemd service do this nightly.

**Option C — Both (recommended)**

Restore the seed, then schedule `daily_refresh.py` to keep it current.

---

## 6. Running the agent

```bash
# Plain
.venv/bin/python nse_agent.py

# Or via Make (handles cwd)
make -C installer agent
```

You'll see:
- The capture daemon status line ("intraday capture: started")
- A prompt: `agent ▸ `

Useful commands inside the REPL:

| Command | What it does |
|---|---|
| `/help` | List all slash commands |
| `/recap` | Last-120-min market recap (uses live capture) |
| `/recap 30` | Last 30 minutes only |
| `/heat` | Sector heat-calendar with 12-month matrix + LLM commentary |
| `/intel TICKER` | Stock brief (fundamentals + technicals + catalysts) |
| `/scan` | Run breakout / pullback / reversal screeners |
| `/listen` | Voice input (requires `ffmpeg` + microphone) |
| `/portfolio` | Holdings tracker view |
| `/exit` | Quit (capture daemon stops automatically) |

Free-text queries work too: *"what happened in metals today?"*, *"is RELIANCE setting up for a breakout?"*.

The **self-check intelligence layer** (`Agent._quality_check`) prepends a
`▶ HEADS-UP` block when responses look thin or tools failed, and offers
context-aware follow-ups. No configuration needed.

---

## 7. Background services (launchd / systemd)

### 7a. Why
- Keep `intraday.quote_snapshots` fresh even when the REPL isn't open.
- Run `daily_refresh.py` automatically at 16:15 IST (post-market) on weekdays.

### 7b. Install

The wizard offers this on first run; otherwise:

```bash
make -C installer services-install
```

### 7c. Status / logs

**macOS (launchd):**

```bash
launchctl list | grep agentadda
tail -f /tmp/agentadda_capture.log
tail -f /tmp/agentadda_daily_refresh.log
```

**Linux (systemd user units):**

```bash
systemctl --user status agentadda-intraday-capture.service
systemctl --user status agentadda-daily-refresh.timer
journalctl --user -u agentadda-intraday-capture.service -f
```

### 7d. Remove

```bash
make -C installer services-uninstall
```

---

## 8. Daily operations cheatsheet

| Task | Command |
|---|---|
| Launch agent | `make -C installer agent` |
| Force EOD refresh now | `make -C installer refresh` |
| Health check | `make -C installer doctor` |
| Re-prompt for API keys | `make -C installer wizard` |
| Re-install pip deps | `make -C installer install-deps` |
| Run tests | `make -C installer test` |
| Tail capture log (mac) | `tail -f /tmp/agentadda_capture.log` |
| Inspect latest report | `open reports/Enhanced_Comprehensive_Analysis_*.html` |
| Check intraday rows | `psql nse_market -c "SELECT COUNT(*), MAX(captured_at) FROM intraday.quote_snapshots;"` |
| Full make help | `make -C installer help` |

---

## 9. Troubleshooting playbook

> **Step 1 always:** `make -C installer doctor` — surfaces ~90 % of issues.

### 9a. Install / setup failures

| Symptom | Diagnosis | Fix |
|---|---|---|
| `install.sh: command not found` | not executable | `chmod +x installer/install.sh` |
| `Homebrew not found` | macOS missing brew | install Homebrew per the printed URL, re-run |
| `pip install failed` | network / mirror issue | `.venv/bin/pip install -r requirements.txt --verbose` to see real error |
| `playwright: Executable doesn't exist` | Chromium not downloaded | `.venv/bin/playwright install chromium` |
| Wizard hangs at PG step | `psql` can't reach server | `pg_isready`; start service: `brew services start postgresql@16` |

### 9b. Runtime / agent failures

| Symptom | Diagnosis | Fix |
|---|---|---|
| Agent prints "no LLM backend configured" | `OPENAI_API_KEY` and `OLLAMA_HOST` both empty | re-run wizard, set at least one |
| `/recap` returns single stock brief | (regression) slash not registered | pull latest; run `make test` to confirm |
| Footer says "SQLite intraday/live tables" | (stale label) | pull latest — fixed in current release |
| `/heat` dumps 90 raw rows | (planner misroute) | pull latest — fixed |
| Empty `intraday.quote_snapshots` | capture daemon not running | check `tail /tmp/agentadda_capture.log`; ensure market hours (09:00–15:45 IST); reload service |
| `OperationalError: could not connect` | wrong `PG_DSN` | `psql "$PG_DSN"` to test; re-run wizard |
| `ModuleNotFoundError: psycopg2` | venv not activated / partial install | `make -C installer install-deps` |
| Reports missing logo | `docs/Agent-adda-logo.jpg` absent | clone refresh, or place file manually |
| Voice (`/listen`) fails | `ffmpeg` missing | `brew install ffmpeg` (mac) / `apt install ffmpeg` (Linux) |
| Agent very slow on first reply | LLM cold-start | normal; subsequent replies cache |

### 9c. Background-service failures

| Symptom | Fix |
|---|---|
| `launchctl load` returns 5 (input/output) | unload first: `launchctl unload ~/Library/LaunchAgents/com.agentadda.*.plist` then re-load |
| `launchctl list` doesn't show the unit | check `/tmp/agentadda_capture.err` for crash trace |
| systemd: `Failed to enable: No such file or directory` | run `systemctl --user daemon-reload` after `services-install` |
| Logs not appearing | ensure `/tmp` writable (mac) or `/var/log` writable (Linux) |
| Capture only runs during market hours | by design — check `intraday_capture.py` `MARKET_OPEN_HHMM`/`MARKET_CLOSE_HHMM` |

### 9d. Database / data integrity

```bash
# Row counts per critical table
psql nse_market -c "
  SELECT 'equity_eod' AS t, COUNT(*) FROM market.equity_eod
  UNION ALL SELECT 'index_eod', COUNT(*) FROM market.index_eod
  UNION ALL SELECT 'quote_snapshots', COUNT(*) FROM intraday.quote_snapshots
  UNION ALL SELECT 'fundamental_scores', COUNT(*) FROM scores.fundamental_scores;"

# Latest data freshness
psql nse_market -c "SELECT MAX(trade_date) FROM market.equity_eod;"
psql nse_market -c "SELECT MAX(captured_at) FROM intraday.quote_snapshots;"
```

If `equity_eod` is stale: `make -C installer refresh`.
If `quote_snapshots` is stale during market hours: restart the capture service.

### 9e. Get a debug bundle

```bash
.venv/bin/python installer/doctor.py > /tmp/agentadda_doctor.txt
.venv/bin/python --version >> /tmp/agentadda_doctor.txt
.venv/bin/pip freeze >> /tmp/agentadda_doctor.txt
tail -100 /tmp/agentadda_capture.log >> /tmp/agentadda_doctor.txt 2>/dev/null
echo "PG_DSN set: $(grep -c '^PG_DSN=' .env)" >> /tmp/agentadda_doctor.txt
```

Share `/tmp/agentadda_doctor.txt` (it strips API key values — only key names are shown by doctor).

---

## 10. Performance tuning

### 10a. Capture daemon

Override via `.env`:

```bash
AGENT_ADDA_CAPTURE_INTERVAL_SEC=60       # how often to poll NSE (lower = more load)
AGENT_ADDA_CAPTURE_RETENTION_MIN=120     # how long to keep snapshots (higher = bigger table)
AGENT_ADDA_CAPTURE_PRUNE_SEC=1800        # how often to delete old rows
```

Sweet spots:
- **Day-trader:** `INTERVAL=30`, `RETENTION=240` (more granular, more storage)
- **Swing/positional:** `INTERVAL=120`, `RETENTION=60` (lighter)
- **Default:** `60 / 120 / 1800` (balanced)

### 10b. PostgreSQL

```sql
-- Add an index if /recap feels slow
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_quote_snap_captured
  ON intraday.quote_snapshots (captured_at DESC);

-- Vacuum once a week
VACUUM (ANALYZE) intraday.quote_snapshots;
VACUUM (ANALYZE) market.equity_eod;
```

In `postgresql.conf` for moderate machines (16 GB RAM):

```
shared_buffers = 4GB
effective_cache_size = 12GB
work_mem = 64MB
maintenance_work_mem = 512MB
```

### 10c. LLM latency

| Lever | Effect |
|---|---|
| Switch `OPENAI_MODEL` from `gpt-4o` → `gpt-4o-mini` | 3–5× faster, cheaper, slightly less narrative depth |
| Use Ollama (`OLLAMA_MODEL=granite4` or `llama3.1`) | Zero network latency; quality varies |
| Set `AGENT_TOOL_TIMEOUT_SEC=15` (env) | Cap individual tool calls |

### 10d. Reports / HTML rendering

- Skip PDF: don't install Playwright (`./installer/install.sh` gracefully skips).
- Reduce HTML report size: limit universe in `core/config.py` (`SCAN_UNIVERSE`).
- Email throttling: send weekly digest instead of daily (`email_nse_reports.py --weekly`).

### 10e. Disk

- `intraday.quote_snapshots` self-prunes; bounded at `RETENTION_MINUTES`.
- `reports/` accumulates HTML files — archive monthly:

```bash
mkdir -p reports/archive/$(date +%Y-%m)
mv reports/Enhanced_Comprehensive_Analysis_$(date -v-1m +%Y%m)*.html reports/archive/$(date +%Y-%m)/ 2>/dev/null
```

### 10f. Memory

- The agent process is normally ~250–400 MB RSS. If it grows past 1 GB, restart
  the REPL — stateful caches (LLM context, sector tables) are rebuilt cheaply.
- Capture daemon < 50 MB RSS.

---

## 11. Upgrading

```bash
git pull
./installer/install.sh --skip-system     # refresh deps + re-apply migrations
make -C installer test                    # confirm green
make -C installer services-install        # re-render launchd/systemd if changed
```

If a migration fails, the wizard prints the SQL line — fix manually:

```bash
psql nse_market -f postgres/<failing>.sql
```

---

## 12. Uninstall

### 12a. Soft (keep data, remove venv & services)

```bash
make -C installer uninstall
```

This removes `.venv` and background services. **Preserved:** `.env`, `reports/`, `data/`, the PostgreSQL database.

### 12b. Hard (drop everything)

```bash
make -C installer uninstall
rm -rf .env data/ reports/ logs/
dropdb nse_market                        # WARNING: deletes all market data
dropuser nse_admin
```

PostgreSQL itself, Homebrew, Python — all stay installed.

### 12c. Full wipe

```bash
cd ..
rm -rf Unified-NSE-Analysis
brew services stop postgresql@16         # optional
brew uninstall postgresql@16 ffmpeg      # optional
```

---

## 13. FAQ

**Q: Can I run without an LLM key?**
A: Yes. Templated responses still work; `/recap`, `/heat`, `/scan` produce raw data. The
   `_quality_check` layer prepends a HEADS-UP suggesting you set a key.

**Q: Is the data stored anywhere besides my machine?**
A: No. PostgreSQL is local. Outbound calls go only to NSE (data), the LLM provider
   you configured, and (if set) SerpAPI / SMTP. No telemetry.

**Q: Can I share my install with a teammate?**
A: Yes — the entire `installer/` is portable. They run `./installer/install.sh` and
   the wizard. Don't copy your `.env` (it contains your keys).

**Q: How do I move to a new machine?**
A: `pg_dump nse_market > backup.sql` on old → `psql nse_market < backup.sql` on new.
   Re-run the installer. Copy `.env` over the new template (or re-prompt via wizard).

**Q: The agent gives different answers each time — bug?**
A: No. LLM responses are stochastic by default. Set `OPENAI_TEMPERATURE=0` in `.env`
   for deterministic phrasing.

**Q: Where are the logs?**
A: macOS: `/tmp/agentadda_*.log`. Linux: `/var/log/agentadda_*.log` or
   `journalctl --user -u agentadda-*`. Agent REPL: stdout only (redirect with `tee`).

**Q: How do I contribute / file a bug?**
A: Generate a debug bundle (§9e) and open an issue with the repo. Include `doctor.py` output.

---

*Last reviewed: 2026-05. For the latest, see [INSTALL.md](INSTALL.md) and `make -C installer help`.*
