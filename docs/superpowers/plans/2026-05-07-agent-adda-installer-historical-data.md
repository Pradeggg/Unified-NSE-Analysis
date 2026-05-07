# Agent Adda Installer And Historical Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-class installable CLI foundation with setup, doctor checks, and historical data bootstrap into a local SQLite store.

**Architecture:** Add a small `agent_adda` Python package that wraps existing scripts behind stable commands. Store end-user configuration in `~/.agent-adda/config.toml`, keep historical data in `~/.agent-adda/data/market_data.sqlite`, and expose installable console commands through `pyproject.toml`.

**Tech Stack:** Python standard library, SQLite, TOML via `tomllib`/`tomli`, existing project scripts as future provider adapters, `unittest` tests.

---

### Task 1: Package Entry Point

**Files:**
- Create: `pyproject.toml`
- Create: `agent_adda/__init__.py`
- Create: `agent_adda/cli.py`
- Test: `tests/test_agent_adda_cli.py`

- [ ] **Step 1: Write failing CLI tests**

```python
import unittest

from agent_adda.cli import build_parser


class AgentAddaCliTests(unittest.TestCase):
    def test_parser_accepts_core_commands(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args(["setup", "--non-interactive"]).command, "setup")
        self.assertEqual(parser.parse_args(["doctor"]).command, "doctor")
        args = parser.parse_args(["data", "bootstrap", "--historical"])
        self.assertEqual(args.command, "data")
        self.assertEqual(args.data_command, "bootstrap")
        self.assertTrue(args.historical)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_agent_adda_cli -v`

Expected: FAIL because `agent_adda.cli` does not exist.

- [ ] **Step 3: Implement CLI parser and package metadata**

Create a `pyproject.toml` with project metadata and a `agent-adda = "agent_adda.cli:main"` script. Implement `build_parser()` with `setup`, `doctor`, and `data bootstrap` commands.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_agent_adda_cli -v`

Expected: PASS.

### Task 2: Config Setup

**Files:**
- Create: `agent_adda/config/__init__.py`
- Create: `agent_adda/config/settings.py`
- Create: `agent_adda/config/wizard.py`
- Test: `tests/test_agent_adda_config.py`

- [ ] **Step 1: Write failing config tests**

```python
import tempfile
import unittest
from pathlib import Path

from agent_adda.config.settings import AppConfig, default_config, load_config, save_config


class AgentAddaConfigTests(unittest.TestCase):
    def test_default_config_uses_agent_adda_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = default_config(Path(tmp))
            self.assertEqual(cfg.home_dir, Path(tmp))
            self.assertEqual(cfg.data_dir, Path(tmp) / "data")
            self.assertEqual(cfg.database_path, Path(tmp) / "data" / "market_data.sqlite")
            self.assertEqual(cfg.model_mode, "rules")
            self.assertFalse(cfg.disclaimer_acknowledged)

    def test_save_and_load_config_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            cfg = AppConfig(
                home_dir=Path(tmp),
                data_dir=Path(tmp) / "data",
                reports_dir=Path(tmp) / "reports",
                database_path=Path(tmp) / "data" / "market_data.sqlite",
                model_mode="hybrid",
                openai_api_key_env="OPENAI_API_KEY",
                ollama_model="llama3.1",
                disclaimer_acknowledged=True,
            )
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertEqual(loaded.model_mode, "hybrid")
            self.assertTrue(loaded.disclaimer_acknowledged)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_agent_adda_config -v`

Expected: FAIL because config modules do not exist.

- [ ] **Step 3: Implement config model and non-interactive setup**

Implement `AppConfig`, `default_config()`, `save_config()`, `load_config()`, and `run_setup(non_interactive=True)`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m unittest tests.test_agent_adda_config -v`

Expected: PASS.

### Task 3: Historical Data Store

**Files:**
- Create: `agent_adda/data/__init__.py`
- Create: `agent_adda/data/historical.py`
- Test: `tests/test_agent_adda_historical.py`

- [ ] **Step 1: Write failing historical data tests**

```python
import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agent_adda.data.historical import bootstrap_historical_store


class AgentAddaHistoricalTests(unittest.TestCase):
    def test_bootstrap_loads_daily_prices_from_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            with (source / "sample.csv").open("w", newline="") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=["SYMBOL", "DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "SYMBOL": "RELIANCE",
                        "DATE": "2026-05-04",
                        "OPEN": "1400",
                        "HIGH": "1420",
                        "LOW": "1390",
                        "CLOSE": "1410",
                        "VOLUME": "12345",
                    }
                )
            db_path = root / "market_data.sqlite"
            result = bootstrap_historical_store(db_path, [source])
            self.assertEqual(result.rows_loaded, 1)
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute("select symbol, trade_date, close from daily_prices").fetchall()
            self.assertEqual(rows, [("RELIANCE", "2026-05-04", 1410.0)])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_agent_adda_historical -v`

Expected: FAIL because `agent_adda.data.historical` does not exist.

- [ ] **Step 3: Implement SQLite schema and CSV loader**

Implement a conservative loader that recognizes `SYMBOL`, `DATE`, `OPEN`, `HIGH`, `LOW`, `CLOSE`, and `VOLUME` columns, writes `daily_prices`, and records `data_refresh_log`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m unittest tests.test_agent_adda_historical -v`

Expected: PASS.

### Task 4: Doctor Command

**Files:**
- Create: `agent_adda/doctor.py`
- Test: `tests/test_agent_adda_doctor.py`

- [ ] **Step 1: Write failing doctor tests**

```python
import tempfile
import unittest
from pathlib import Path

from agent_adda.config.settings import default_config
from agent_adda.doctor import run_doctor


class AgentAddaDoctorTests(unittest.TestCase):
    def test_doctor_reports_missing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = default_config(Path(tmp))
            result = run_doctor(cfg)
            names = [check.name for check in result.checks]
            self.assertIn("config", names)
            self.assertIn("historical_database", names)
            self.assertFalse(result.ok)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_agent_adda_doctor -v`

Expected: FAIL because `agent_adda.doctor` does not exist.

- [ ] **Step 3: Implement doctor checks**

Implement checks for config directory, SQLite database presence, Python version, optional OpenAI env var, and optional Ollama executable.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m unittest tests.test_agent_adda_doctor -v`

Expected: PASS.

### Task 5: CLI Integration And Docs

**Files:**
- Modify: `agent_adda/cli.py`
- Modify: `README.md`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Add CLI integration tests**

Extend `tests/test_agent_adda_cli.py` to verify `main(["setup", "--non-interactive", "--home", tmp])` writes config and `main(["data", "bootstrap", "--historical", "--home", tmp, "--source", fixture])` creates the database.

- [ ] **Step 2: Run test to verify failure**

Run: `.venv/bin/python -m unittest tests.test_agent_adda_cli -v`

Expected: FAIL until command handlers are wired.

- [ ] **Step 3: Wire command handlers and docs**

Wire setup, doctor, and data bootstrap to real implementations. Document installation and first-run commands in `README.md`. Mark the installer/historical data backlog item as started.

- [ ] **Step 4: Run full verification**

Run:

```bash
.venv/bin/python -m unittest tests.test_agent_adda_cli tests.test_agent_adda_config tests.test_agent_adda_historical tests.test_agent_adda_doctor -v
.venv/bin/python -m py_compile agent_adda/*.py agent_adda/config/*.py agent_adda/data/*.py
```

Expected: all tests PASS and compile exits 0.
