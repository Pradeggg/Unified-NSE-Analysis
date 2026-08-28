# Ollama narratives → SQLite (`llm_narratives`)

Generated market and stock narratives are **stored in** `nse_analysis.db` table **`llm_narratives`**.

| Column | Meaning |
|--------|---------|
| `narrative_type` | `market` or `stock` |
| `analysis_date` | Same snapshot date as `stocks_analysis` / dashboard as-of (`YYYY-MM-DD`) |
| `symbol` | NSE symbol (uppercase); **empty string** for market-wide narrative |
| `ollama_model` | Model name used (e.g. `granite4`) |
| `content` | Full narrative text |
| `context_json` | JSON blob of facts sent to the model (for audit / refresh decisions) |
| `created_at` / `updated_at` | UTC ISO timestamps |

**Uniqueness:** one row per `(narrative_type, analysis_date, symbol)`.

## Schema creation

- Running **`fixed_nse_universe_analysis.py`** (`initialize_database`) creates the table if missing.
- Starting **`narrative_llm_server.py`** also runs `ensure_narratives_schema()` so the table exists even without re-init.

## API server

```bash
cd /path/to/Unified-NSE-Analysis
pip install -r requirements.txt   # fastapi, uvicorn, yfinance, pandas, …

export OLLAMA_MODEL=granite4      # or your pulled tag, e.g. ibm/granite4:latest
export OLLAMA_BASE=http://127.0.0.1:11434
# optional: export NSE_DB_PATH=/path/to/nse_analysis.db

python python/core/narrative_llm_server.py
# or: uvicorn narrative_llm_server:app --host 127.0.0.1 --port 8765 --app-dir python/core
```

### Endpoints

- **`GET /api/market-narrative`** — Returns cached narrative from SQLite if present; use **`refresh=1`** to call Ollama and **upsert** the row.
- **`GET /api/stock-narrative?symbol=RELIANCE`** — Same: cache first, **`refresh=1`** to regenerate and save.

Optional query: **`analysis_date=YYYY-MM-DD`** (defaults to latest `MAX(analysis_date)` in `stocks_analysis`).

### Flow

1. Request without `refresh` → read **`llm_narratives`** → return `content` if found (`cached: true`).
2. Request with `refresh=1` (or no row yet) → build JSON context from SQLite + `fundamental_scores_database.csv` + optional Yahoo/yfinance → Ollama → **`upsert_narrative`** → return `cached: false`.

## Direct SQL examples

```sql
SELECT narrative_type, analysis_date, symbol, length(content), updated_at
FROM llm_narratives
ORDER BY updated_at DESC
LIMIT 20;

SELECT content FROM llm_narratives
WHERE narrative_type = 'market' AND analysis_date = '2026-03-20' AND symbol = '';
```

## Notes

- **Yahoo / yfinance** is optional context only; install `yfinance` for headlines and quarterly snippets.
- **CORS** defaults to `*`; set `NARRATIVE_CORS_ORIGINS=https://myhost,http://localhost` if needed.

## Pipeline (automatic)

`python python/core/run_complete_analysis_pipeline.py` now runs **`narrative_pipeline_runner.py`** after universe analysis and **before** the dashboard generator, so narratives are **written to SQLite** and then **embedded** in the HTML (shareable offline).

- **`NARRATIVE_SKIP=1`** — skip narrative generation (e.g. no Ollama on this machine).
- **`NARRATIVE_MARKET_ONLY=1`** — only the market JSON narrative (faster).
- **`NARRATIVE_TOP_STOCKS=20`** — default count of top technical-score names; raise for more embedded stock narratives.
- **`NARRATIVE_FAIL_PIPELINE=1`** — exit non-zero if the **market** narrative fails (default: warn and continue).

Ollama must be running at **`OLLAMA_BASE`** (default `http://127.0.0.1:11434`) with **`OLLAMA_MODEL`** pulled (e.g. `granite4`).

Models are prompted to return **plain JSON only** (no markdown fences) with stable keys so the dashboard renders sections correctly.

## HTML dashboard integration

After narratives exist in `llm_narratives`, run:

`python python/core/generate_nse_interactive_dashboard.py`

(Or rely on the full pipeline above.)

The generated **`NSE_Interactive_Dashboard_<asof>.html`** will:

- **Overview tab** — “AI market narrative” card with text embedded from the DB; **Refresh via API** calls the narrative server (does not rewrite the HTML file; re-run the generator to re-embed).
- **Universe tab** — **AI** column and **heat map click** open a modal with embedded stock narrative (if present) plus technical + fundamental snippets; **Regenerate via API** stores a new row in SQLite.

Override the API URL when building or in the browser’s environment via **`NARRATIVE_API_BASE`** (default `http://127.0.0.1:8765`).
