# /eod-refresh — NSE EOD refresh

Run the standard post-market refresh, verify its outputs, and report failures with the failing stage and log path.

## Standard run

1. Confirm PostgreSQL is available:

   ```bash
   source .venv/bin/activate
   pg_isready -h /tmp -U nse_admin -d nse_market
   ```

   If unavailable, run `bash postgres/start_pg.sh start` and check again.

2. Run the pipeline after market close:

   ```bash
   source .venv/bin/activate && python daily_refresh.py --skip-email
   ```

3. Verify that the latest database snapshot date and generated reports match the intended trading date. Do not describe the refresh as successful if a required stage failed or data remains stale.

## Non-standard operations

Read [references/eod-refresh-runbook.md](references/eod-refresh-runbook.md) only when you need a targeted load, gap backfill, manual report generation, recovery procedure, direct SQL verification, or the known-issues history. Preserve the runbook commands and apply only the section relevant to the request.
