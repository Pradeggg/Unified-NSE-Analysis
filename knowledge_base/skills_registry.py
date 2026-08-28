"""BM25-powered index over Agent Adda skills, commands, tools, and workflows.

This module is the fast (sub-millisecond, zero-LLM) search layer for the
*tools/commands/skills* surface of Agent Adda — complementing the ChromaDB
vector store (financial documents).  Coding assistants should query this
layer FIRST before searching source code.

Sources indexed
---------------
1. reports/latest/launcher_data.json  — 138 launcher entries (skills/repl/screener/pipeline)
2. skill_store/stored/*.yml           — 5 detailed skill YAMLs with tool_plan_template
3. .claude/skills/*/SKILL.md          — 9 project Claude skills (daily-pipeline, etc.)
4. knowledge_base/entries/workflows.yaml — curated workflow definitions
5. mcp_server.py tool catalogue       — 9 MCP tools (built-in definitions)

Usage
-----
    from knowledge_base.skills_registry import SkillsRegistry
    reg = SkillsRegistry()                  # loads + indexes on first call
    hits = reg.search("run daily pipeline", k=5)
    for h in hits:
        print(h["score"], h["entry"]["cli"])

    ctx = reg.context_block("chart RELIANCE", k=3)  # ready for prompt injection
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import yaml  # PyYAML — already in project deps

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_PATH   = ROOT / "reports" / "latest" / "launcher_data.json"
SKILL_STORE_DIR = ROOT / "skill_store" / "stored"
CLAUDE_SKILLS   = ROOT / ".claude" / "skills"
WORKFLOWS_YAML  = ROOT / "knowledge_base" / "entries" / "workflows.yaml"

# ── source file token estimates (for savings calculation) ─────────────────────
# Rough token counts for the source files a user would otherwise need to read.
SOURCE_FILE_TOKENS: dict[str, int] = {
    "nse_agent.py": 14000,
    "daily_refresh.py": 7500,
    "terminal/tools.py": 11000,
    "terminal/chart_engine.py": 4000,
    "sector_rotation_tracker.py": 5500,
    "sector_rotation_report.py": 3500,
    "fixed_nse_universe_analysis.py": 4500,
    "postgres/loader.py": 6000,
    "mcp_server.py": 3000,
    "CLAUDE.md": 3200,
    ".claude/skills/daily-pipeline/SKILL.md": 2000,
    ".claude/skills/fundamental-analyze/SKILL.md": 1800,
    ".claude/skills/tradingview-chart/SKILL.md": 1200,
    "skill_store/stored/equity_chart_v1.yml": 1200,
    "skill_store/stored/intraday_fno_alert_scan_v1.yml": 1500,
    "scripts/backfill_screener_fundamentals.py": 2000,
    "scripts/materialize_stage2_vcp_picks.py": 1800,
}

# category → list of source files typically needed to answer a query
CATEGORY_SOURCES: dict[str, list[str]] = {
    "pipeline":  ["daily_refresh.py", "postgres/loader.py", "CLAUDE.md"],
    "skill":     ["nse_agent.py", ".claude/skills/daily-pipeline/SKILL.md", "CLAUDE.md"],
    "repl":      ["nse_agent.py"],
    "screener":  ["terminal/tools.py", "nse_agent.py"],
    "workflow":  ["daily_refresh.py", "CLAUDE.md"],
    "chart":     ["terminal/chart_engine.py", "skill_store/stored/equity_chart_v1.yml"],
    "mcp":       ["mcp_server.py"],
    "reference": ["CLAUDE.md"],
}


def _source_token_estimate(category: str, tags: list[str]) -> int:
    """Estimate how many tokens a user would need to read without KB."""
    srcs = set(CATEGORY_SOURCES.get(category, ["CLAUDE.md"]))
    if "chart" in tags:
        srcs.update(CATEGORY_SOURCES["chart"])
    if "pipeline" in tags or "daily" in tags:
        srcs.update(CATEGORY_SOURCES["pipeline"])
    if "screener" in tags or "scan" in tags:
        srcs.update(CATEGORY_SOURCES["screener"])
    return sum(SOURCE_FILE_TOKENS.get(s, 1500) for s in srcs)


# ── tokenization ──────────────────────────────────────────────────────────────
_STOP = frozenset(
    "a an the and or of to in for with from on at by is are was were be been "
    "it its this that which who how what when where why will can do does "
    "get run python show find list make build create update generate".split()
)


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens, stop-words removed, min len 2."""
    tokens = re.findall(r"[a-z0-9_/]+", text.lower())
    return [t for t in tokens if len(t) >= 2 and t not in _STOP]


def _rerank_boost(entry: dict) -> float:
    """Small deterministic boost for more actionable, canonical entries."""
    cat = str(entry.get("category") or "").strip().lower()
    eid = str(entry.get("id") or "").strip()
    cli = str(entry.get("cli") or "").strip()

    boost = 0.0

    # Prefer curated workflows as canonical operational paths.
    if cat == "workflow" or eid.startswith("workflow_"):
        boost += 2.5

    # Prefer entries that actually run something.
    cli_l = cli.lower()
    if cli_l.startswith(("python ", ".venv", "./", "agent_adda_", "agentadda_", "agent adda")):
        boost += 0.8
    if cli_l.startswith("cd "):
        boost -= 2.0
    if not cli or cli_l.startswith("#"):
        boost -= 0.8

    # Slightly downweight project_skill stubs that aren't executable.
    if cat == "project_skill" and not cli_l.startswith(("python ", "./", ".venv")):
        boost -= 0.2

    return boost


# ── loaders ───────────────────────────────────────────────────────────────────

def _load_launcher() -> list[dict]:
    if not LAUNCHER_PATH.exists():
        return []
    data = json.loads(LAUNCHER_PATH.read_text(encoding="utf-8"))
    entries = []
    for item in data:
        entries.append({
            "id":            item.get("id", ""),
            "title":         item.get("id", "").replace("_", " "),
            "description":   item.get("description", ""),
            "category":      item.get("category", "unknown"),
            "tags":          item.get("tags", []),
            "input_patterns": item.get("input_patterns", []),
            "cli":           item.get("cli", ""),
            "status":        item.get("status", ""),
            "source":        "launcher_data.json",
            "source_file_tokens": _source_token_estimate(
                item.get("category", "unknown"), item.get("tags", [])
            ),
        })
    return entries


def _load_skill_store_yamls() -> list[dict]:
    entries = []
    for yf in SKILL_STORE_DIR.glob("*.yml"):
        try:
            d = yaml.safe_load(yf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        # Build cli from tool_plan_template if no direct cli
        cli_steps: list[str] = []
        for step in (d.get("tool_plan_template") or []):
            cmd = step.get("command", "")
            if cmd:
                cli_steps.append(cmd)
        cli = cli_steps[0] if cli_steps else f"python nse_agent.py --query \"{d.get('title', d.get('id', ''))} [SYMBOL]\""
        entries.append({
            "id":             d.get("id", yf.stem),
            "title":          d.get("title", d.get("id", yf.stem)),
            "description":    d.get("description", ""),
            "category":       "skill_store",
            "tags":           d.get("tags", []),
            "input_patterns": d.get("input_patterns", []),
            "cli":            cli,
            "status":         d.get("status", ""),
            "source":         f"skill_store/stored/{yf.name}",
            "tool_plan":      d.get("tool_plan_template", []),
            "evidence":       d.get("evidence_required", {}),
            "source_file_tokens": _source_token_estimate("skill", d.get("tags", [])),
        })
    return entries


def _load_project_skills() -> list[dict]:
    entries = []
    if not CLAUDE_SKILLS.exists():
        return entries
    for skill_dir in CLAUDE_SKILLS.iterdir():
        if not skill_dir.is_dir():
            continue
        md = skill_dir / "SKILL.md"
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8", errors="ignore")
        # Extract frontmatter
        name = skill_dir.name
        description = ""
        if text.startswith("---"):
            fm_end = text.find("---", 3)
            if fm_end > 0:
                fm = text[3:fm_end]
                for line in fm.splitlines():
                    if line.startswith("description:"):
                        description = line.partition(":")[2].strip()
                        break
                if not description:
                    description = text[fm_end + 3:].strip()[:300]
        else:
            description = text[:300].strip()

        # Build CLI from SKILL.md body
        cli_match = re.search(r"```(?:bash)?\n(.+?)```", text, re.DOTALL)
        if cli_match:
            block = cli_match.group(1).strip()
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            # Prefer a "real" executable command over a repo-navigation step.
            preferred = None
            for ln in lines:
                if ln.lower().startswith("cd "):
                    continue
                if ln.startswith("#"):
                    continue
                preferred = ln
                break
            cli = preferred or (lines[0] if lines else "")
        else:
            cli = f"# see .claude/skills/{name}/SKILL.md"

        # Extract trigger phrases from description / headings
        patterns = re.findall(r'"([^"]{10,80})"', text[:500])

        entries.append({
            "id":             name,
            "title":          name.replace("-", " ").title(),
            "description":    description[:600],
            "category":       "project_skill",
            "tags":           name.split("-"),
            "input_patterns": patterns[:8],
            "cli":            cli[:200],
            "status":         "production",
            "source":         f".claude/skills/{name}/SKILL.md",
            "source_file_tokens": _source_token_estimate("skill", name.split("-")),
        })
    return entries


def _load_workflows_yaml() -> list[dict]:
    if not WORKFLOWS_YAML.exists():
        return []
    try:
        # workflows.yaml is a multi-document YAML stream (uses `---`).
        # safe_load() would fail with "expected a single document in the stream".
        docs = list(yaml.safe_load_all(WORKFLOWS_YAML.read_text(encoding="utf-8")))
    except Exception:
        return []

    items: list[dict] = []
    for d in docs:
        if isinstance(d, list):
            items.extend([x for x in d if isinstance(x, dict)])
        elif isinstance(d, dict):
            items.append(d)

    entries: list[dict] = []
    for item in items:
        if not item.get("id"):
            continue
        entries.append({**item, "source": "knowledge_base/entries/workflows.yaml"})
    return entries


# ── built-in MCP tools (hardcoded, not auto-read from mcp_server.py) ──────────
_MCP_TOOLS: list[dict] = [
    {"id": "mcp_get_market_overview",    "title": "MCP: Market Overview",
     "description": "NIFTY breadth, A/D, FII/DII flows, global indices from MCP",
     "cli": "# via MCP: call get_market_overview()", "tags": ["mcp", "market", "overview"],
     "input_patterns": ["market overview via mcp", "mcp market status"]},
    {"id": "mcp_get_stage2_picks",       "title": "MCP: Stage 2 Picks",
     "description": "Stage 2 uptrend stocks with RSI/RS/technical score, filtered by index",
     "cli": "# via MCP: call get_stage2_picks(index='NIFTY 500')", "tags": ["mcp", "stage2", "picks"],
     "input_patterns": ["stage 2 picks via mcp", "mcp stage2 stocks"]},
    {"id": "mcp_get_stock_profile",      "title": "MCP: Stock Profile",
     "description": "Full single-stock profile: stage, price, RSI, fundamentals, 30d history",
     "cli": "# via MCP: call get_stock_profile(symbol='RELIANCE')", "tags": ["mcp", "stock", "profile"],
     "input_patterns": ["stock profile via mcp", "mcp stock details SYMBOL"]},
    {"id": "mcp_get_swing_candidates",   "title": "MCP: Swing Candidates",
     "description": "Liquid Stage 2 stocks suitable for swing trading",
     "cli": "# via MCP: call get_swing_candidates(limit=15)", "tags": ["mcp", "swing", "stage2"],
     "input_patterns": ["swing candidates via mcp"]},
    {"id": "mcp_get_sector_rotation",    "title": "MCP: Sector Rotation",
     "description": "Sector-level stage distribution and relative strength",
     "cli": "# via MCP: call get_sector_rotation()", "tags": ["mcp", "sector", "rotation"],
     "input_patterns": ["sector rotation via mcp"]},
    {"id": "mcp_get_strategy_lab",       "title": "MCP: Strategy Lab",
     "description": "Backtest leaderboard or trade log for 8 built-in strategies",
     "cli": "# via MCP: call get_strategy_lab(strategy_id='vcp_momentum')", "tags": ["mcp", "strategy", "backtest"],
     "input_patterns": ["strategy lab via mcp", "backtest results mcp"]},
    {"id": "mcp_get_fno_signals",        "title": "MCP: F&O Signals",
     "description": "PCR, OI buildup, max pain, OI changes for derivatives",
     "cli": "# via MCP: call get_fno_signals(symbol='NIFTY', limit=20)", "tags": ["mcp", "fno", "options", "oi"],
     "input_patterns": ["fno signals via mcp", "options data mcp"]},
    {"id": "mcp_get_bulk_block_deals",   "title": "MCP: Bulk/Block Deals",
     "description": "Institutional bulk/block deal activity",
     "cli": "# via MCP: call get_bulk_block_deals(symbol='HDFC')", "tags": ["mcp", "bulk", "block", "institutional"],
     "input_patterns": ["bulk deals via mcp", "block deals mcp"]},
    {"id": "mcp_get_corporate_events",   "title": "MCP: Corporate Events",
     "description": "Dividends, bonuses, rights, AGMs, splits, result dates",
     "cli": "# via MCP: call get_corporate_events(days_ahead=30)", "tags": ["mcp", "events", "dividend", "results"],
     "input_patterns": ["corporate events via mcp", "result dates mcp"]},
]

def _load_mcp_tools() -> list[dict]:
    return [
        {**t, "category": "mcp", "status": "production",
         "source": "mcp_server.py",
         "source_file_tokens": SOURCE_FILE_TOKENS["mcp_server.py"]}
        for t in _MCP_TOOLS
    ]


# ── SkillsRegistry ────────────────────────────────────────────────────────────

class SkillsRegistry:
    """BM25-indexed catalogue of all Agent Adda skills/commands/tools/workflows.

    Thread-safe read; index is rebuilt in-memory (no disk cache needed —
    < 150 ms to build from ~160 entries on cold start).
    """

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._corpus: list[list[str]] = []       # tokenized docs for BM25
        self._bm25 = None
        self._built = False

    def _ensure_built(self) -> None:
        if self._built:
            return
        t0 = time.perf_counter()
        entries: list[dict] = []
        entries.extend(_load_launcher())
        entries.extend(_load_skill_store_yamls())
        entries.extend(_load_project_skills())
        entries.extend(_load_workflows_yaml())
        entries.extend(_load_mcp_tools())

        # Deduplicate on id (skill_store YAML overrides launcher if same id)
        seen: dict[str, int] = {}
        deduped: list[dict] = []
        for e in entries:
            eid = e.get("id", "")
            if eid and eid in seen:
                # keep whichever has more detail (longer description)
                if len(e.get("description", "")) > len(deduped[seen[eid]].get("description", "")):
                    deduped[seen[eid]] = e
            else:
                seen[eid] = len(deduped)
                deduped.append(e)

        self._entries = deduped
        # Build BM25 corpus
        self._corpus = [
            _tokenize(
                " ".join([
                    e.get("id", ""),
                    e.get("title", ""),
                    e.get("description", ""),
                    " ".join(e.get("tags", [])),
                    " ".join(e.get("input_patterns", [])),
                    e.get("category", ""),
                ])
            )
            for e in self._entries
        ]
        try:
            from rank_bm25 import BM25Okapi  # type: ignore
            self._bm25 = BM25Okapi(self._corpus)
        except ImportError:
            self._bm25 = None

        elapsed_ms = (time.perf_counter() - t0) * 1000
        self._build_ms = elapsed_ms
        self._built = True

    # ── public API ────────────────────────────────────────────────────────────

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """BM25 search. Returns list of {score, entry} dicts, best first."""
        self._ensure_built()
        if not self._entries:
            return []

        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        pool_k = max(k * 6, 30)
        if self._bm25 is not None:
            scores = self._bm25.get_scores(q_tokens)
            ranked = sorted(
                enumerate(scores), key=lambda x: x[1], reverse=True
            )[:pool_k]
        else:
            # Fallback: simple TF overlap
            def tf(idx: int) -> float:
                doc = set(self._corpus[idx])
                return sum(1 for t in q_tokens if t in doc) / max(len(q_tokens), 1)
            ranked = sorted(
                [(i, tf(i)) for i in range(len(self._entries))],
                key=lambda x: x[1], reverse=True,
            )[:pool_k]

        # Post-rank heuristics: prefer canonical workflows and actionable CLIs.
        rescored: list[tuple[int, float]] = []
        for idx, score in ranked:
            if score <= 0:
                continue
            e = self._entries[idx]
            rescored.append((idx, float(score) + _rerank_boost(e)))

        rescored.sort(key=lambda x: x[1], reverse=True)
        rescored = rescored[:k]
        return [{"score": float(score), "entry": self._entries[idx]} for idx, score in rescored]

    def get_by_id(self, entry_id: str) -> dict | None:
        """Exact lookup by id."""
        self._ensure_built()
        for e in self._entries:
            if e.get("id") == entry_id:
                return e
        return None

    def count(self) -> int:
        self._ensure_built()
        return len(self._entries)

    def context_block(
        self,
        query: str,
        k: int = 5,
        max_tokens: int = 2000,
        compact: bool = False,
    ) -> str:
        """Return a markdown context block suitable for injecting into any prompt.

        Parameters
        ----------
        query : str
            Natural-language query from the coding assistant.
        k : int
            Max entries to include.
        max_tokens : int
            Soft cap on output size (estimated tokens, not guaranteed).
        compact : bool
            If True, emit minimal one-liner format.
        """
        hits = self.search(query, k=k)
        if not hits:
            return f"<!-- KB: no results for '{query}' -->"

        lines: list[str] = [
            f"<!-- Agent Adda KB: top {len(hits)} results for '{query}' -->",
            "",
        ]
        approx_tokens = 50
        for i, h in enumerate(hits, 1):
            e = h["entry"]
            score = h["score"]
            entry_lines: list[str] = []
            if compact:
                entry_lines = [
                    f"### {i}. {e.get('title') or e.get('id')} (score={score:.2f})",
                    f"**CLI:** `{e.get('cli', 'n/a')}`",
                    f"{e.get('description', '')[:150]}",
                ]
            else:
                entry_lines = [
                    f"### {i}. {e.get('title') or e.get('id')}",
                    f"**Category:** {e.get('category')} | **Score:** {score:.2f} | **Source:** {e.get('source', '')}",
                    f"**Description:** {e.get('description', '')}",
                ]
                if e.get("cli"):
                    entry_lines.append(f"**CLI:**\n```bash\n{e['cli']}\n```")
                if e.get("input_patterns"):
                    pats = e["input_patterns"][:3]
                    entry_lines.append(f"**Trigger phrases:** {' | '.join(pats)}")
                if e.get("tags"):
                    entry_lines.append(f"**Tags:** {', '.join(e['tags'][:8])}")

            chunk = "\n".join(entry_lines) + "\n"
            chunk_tokens = max(1, int(len(chunk.split()) * 1.35))
            if approx_tokens + chunk_tokens > max_tokens and i > 1:
                lines.append(f"*… {len(hits) - i + 1} more results omitted (token budget)*")
                break
            lines.append(chunk)
            approx_tokens += chunk_tokens

        lines.append("<!-- end KB results -->")
        return "\n".join(lines)

    @property
    def stats(self) -> dict:
        self._ensure_built()
        cats: dict[str, int] = {}
        for e in self._entries:
            c = e.get("category", "unknown")
            cats[c] = cats.get(c, 0) + 1
        return {
            "total_entries": len(self._entries),
            "categories": cats,
            "build_ms": round(getattr(self, "_build_ms", 0), 1),
            "bm25_backend": "rank_bm25" if self._bm25 is not None else "tf_overlap_fallback",
        }


# ── flat file export (for grep / awk / shell search) ─────────────────────────

INDEX_DIR      = ROOT / "knowledge_base" / "index"
FLAT_TXT_PATH  = INDEX_DIR / "kb_flat.txt"       # human/grep-friendly blocks
TSV_PATH       = INDEX_DIR / "kb_index.tsv"       # tab-separated: awk/cut-friendly
JSONL_PATH     = INDEX_DIR / "kb_index.jsonl"     # one JSON per line: jq-friendly


def export_flat_indexes(registry: "SkillsRegistry | None" = None) -> dict:
    """Generate grep/awk/jq-friendly flat index files.

    Files written
    -------------
    index/kb_flat.txt   — searchable text blocks (grep -i, rg)
    index/kb_index.tsv  — id<TAB>category<TAB>cli<TAB>description<TAB>tags
    index/kb_index.jsonl— one entry per line (jq, ripgrep)

    Returns dict with file paths and entry count.
    """
    if registry is None:
        registry = get_registry()
    registry._ensure_built()

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # ── kb_flat.txt ──────────────────────────────────────────────────────────
    flat_lines: list[str] = [
        "# Agent Adda Knowledge Base — flat text index",
        "# grep -i 'daily pipeline' knowledge_base/index/kb_flat.txt",
        "# grep -A8 'id: daily_refresh' knowledge_base/index/kb_flat.txt",
        "#" + "─" * 76,
        "",
    ]
    for e in registry._entries:
        flat_lines.extend([
            f"id: {e.get('id', '')}",
            f"title: {e.get('title') or e.get('id', '')}",
            f"category: {e.get('category', '')}",
            f"description: {e.get('description', '')}",
            f"cli: {e.get('cli', '')}",
            f"tags: {' '.join(e.get('tags', []))}",
            f"patterns: {' | '.join(e.get('input_patterns', [])[:5])}",
            f"source: {e.get('source', '')}",
            "─" * 60,
            "",
        ])
    FLAT_TXT_PATH.write_text("\n".join(flat_lines), encoding="utf-8")

    # ── kb_index.tsv ─────────────────────────────────────────────────────────
    def _tsv_clean(s: str) -> str:
        return str(s).replace("\t", " ").replace("\n", " ").replace("\r", "")

    tsv_lines = ["id\tcategory\ttitle\tcli\tdescription\ttags\tsource"]
    for e in registry._entries:
        tsv_lines.append("\t".join([
            _tsv_clean(e.get("id", "")),
            _tsv_clean(e.get("category", "")),
            _tsv_clean(e.get("title") or e.get("id", "")),
            _tsv_clean(e.get("cli", "")),
            _tsv_clean(e.get("description", "")[:200]),
            _tsv_clean(" ".join(e.get("tags", []))),
            _tsv_clean(e.get("source", "")),
        ]))
    TSV_PATH.write_text("\n".join(tsv_lines), encoding="utf-8")

    # ── kb_index.jsonl ────────────────────────────────────────────────────────
    import json as _json
    jsonl_lines = []
    for e in registry._entries:
        row = {
            "id":          e.get("id", ""),
            "category":    e.get("category", ""),
            "title":       e.get("title") or e.get("id", ""),
            "cli":         e.get("cli", ""),
            "description": e.get("description", "")[:300],
            "tags":        e.get("tags", []),
            "input_patterns": e.get("input_patterns", [])[:5],
            "source":      e.get("source", ""),
        }
        jsonl_lines.append(_json.dumps(row, ensure_ascii=False))
    JSONL_PATH.write_text("\n".join(jsonl_lines), encoding="utf-8")

    return {
        "entries":   len(registry._entries),
        "flat_txt":  str(FLAT_TXT_PATH),
        "tsv":       str(TSV_PATH),
        "jsonl":     str(JSONL_PATH),
    }


# ── module-level singleton ────────────────────────────────────────────────────
_registry: SkillsRegistry | None = None


def get_registry() -> SkillsRegistry:
    global _registry
    if _registry is None:
        _registry = SkillsRegistry()
    return _registry
