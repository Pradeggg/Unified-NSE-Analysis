"""Common paths, env loader, lightweight helpers for the KB pipeline."""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

# PG-kb: project root = parent of knowledge_base/
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REGISTRY_PATH = DATA_DIR / "financial_sources_registry.json"

KB_DIR        = DATA_DIR / "knowledge_base"
RAW_DIR       = KB_DIR / "raw"
MANIFEST_PATH = KB_DIR / "manifest.jsonl"
CHUNKS_PATH   = KB_DIR / "chunks.jsonl"
QA_PATH       = KB_DIR / "qa.jsonl"
CHROMA_DIR    = KB_DIR / "chroma"

KB_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 "
    "AgentAdda-KB/1.0"
)


def load_dotenv() -> None:
    """Load .env without requiring python-dotenv."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def safe_filename(name: str) -> str:
    """Strip path-unsafe characters."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:200] or "unnamed"


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
