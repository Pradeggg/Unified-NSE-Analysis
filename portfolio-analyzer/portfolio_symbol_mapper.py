#!/usr/bin/env python3
"""Local broker-symbol to NSE-symbol resolver for portfolio holdings."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent

_STOP_TOKENS = {
    "A",
    "AN",
    "AND",
    "CO",
    "COMPANY",
    "CORP",
    "CORPORATION",
    "LTD",
    "LIMITED",
    "MFG",
    "OF",
    "PRIVATE",
    "PVT",
    "S",
    "THE",
}

_TOKEN_ALIASES = {
    "DEPO": "DEPOSITORY",
    "DIVIS": "DIVI",
    "IND": "INDIA",
    "INS": "INSURANCE",
    "INSURA": "INSURANCE",
    "LAB": "LABORATORIES",
    "LABS": "LABORATORIES",
    "LUB": "LUBRICANTS",
    "LUBRICANT": "LUBRICANTS",
    "MNGT": "MANAGEMENT",
    "PRU": "PRUDENTIAL",
    "PRUD": "PRUDENTIAL",
    "RT": "RETAIL",
    "RTL": "RETAIL",
    "SER": "SERVICES",
    "SERV": "SERVICES",
    "TECH": "TECHNOLOGIES",
    "TECHNO": "TECHNOLOGIES",
    "TECHNOLOGY": "TECHNOLOGIES",
}


@dataclass(frozen=True)
class SymbolRecord:
    symbol: str
    company_name: str
    source: str
    key: str
    tokens: frozenset[str]


@dataclass(frozen=True)
class SymbolMatch:
    symbol: str
    method: str
    score: float
    matched_name: str = ""
    rationale: str = ""


_MANUAL_OVERRIDES = {
    # Tata Motors demerger: broker aliases now represent separate listed entities.
    ("TATCOV", "TATA MOTORS LIMITED"): SymbolMatch(
        "TMCV",
        "manual",
        1.0,
        "TATA MOTORS COMMERCIAL VEHICLES LIMITED",
        "Manual override: Tata Motors CV demerged into TMCV.",
    ),
    ("TATMOT", "TATA MOTORS PAX VEHICLES LTD"): SymbolMatch(
        "TMPV",
        "manual",
        1.0,
        "TATA MOTORS PASSENGER VEHICLES LIMITED",
        "Manual override: Tata Motors PV trades as TMPV after demerger.",
    ),
    # Broker portfolio aliases that are absent from older local NSE reference files.
    ("KWAWAL", "KWALITY WALLS INDIA LIMITED"): SymbolMatch(
        "KWIL",
        "manual",
        1.0,
        "KWALITY WALL'S (INDIA) LIMITED",
        "Manual override: NSE symbol KWIL.",
    ),
    # BSE-only holding; keep broker symbol for NSE-centric phases, but make the audit explicit.
    ("SANPAR", "SANJIVANI PARANTERAL LTD"): SymbolMatch(
        "SANPAR",
        "bse_only",
        1.0,
        "BSE:531569; not NSE-listed",
        "Manual override: Sanjivani Paranteral is BSE-only, code 531569.",
    ),
}


def _tokens(value: str) -> list[str]:
    raw = str(value or "").upper().replace("&", " AND ")
    raw = re.sub(r"[^A-Z0-9 ]", " ", raw)
    tokens = []
    for token in raw.split():
        token = _TOKEN_ALIASES.get(token, token)
        if token not in _STOP_TOKENS:
            tokens.append(token)
    return tokens


def _key(value: str) -> str:
    return " ".join(_tokens(value))


def _record(symbol: str, company_name: str, source: str) -> SymbolRecord | None:
    sym = str(symbol or "").strip().upper()
    name = str(company_name or "").strip().upper()
    key = _key(name)
    if not sym or not key:
        return None
    return SymbolRecord(sym, name, source, key, frozenset(key.split()))


def build_symbol_index(records: list[tuple[str, str, str]]) -> list[SymbolRecord]:
    """Build a deduped symbol index from ``(symbol, company_name, source)`` rows."""
    out: list[SymbolRecord] = []
    seen: set[tuple[str, str]] = set()
    for symbol, company_name, source in records:
        rec = _record(symbol, company_name, source)
        if rec is None:
            continue
        dedupe_key = (rec.symbol, rec.key)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        out.append(rec)
    return out


@lru_cache(maxsize=1)
def load_default_symbol_index() -> list[SymbolRecord]:
    """Load local NSE symbol/name sources without requiring Postgres or network."""
    rows: list[tuple[str, str, str]] = []

    names_path = PROJECT_ROOT / "organized" / "data" / "company_names_mapping.csv"
    if names_path.exists():
        try:
            df = pd.read_csv(names_path)
            for _, row in df.iterrows():
                rows.append((row.get("SYMBOL"), row.get("COMPANY_NAME"), "company_names_mapping"))
        except Exception:
            pass

    graph_path = PROJECT_ROOT / "data" / "nse_graph.json"
    if graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            for symbol, node in (graph.get("nodes") or {}).items():
                if isinstance(node, dict) and node.get("type") == "stock":
                    rows.append((symbol, node.get("company_name"), "nse_graph"))
        except Exception:
            pass

    return build_symbol_index(rows)


def resolve_symbol(
    *,
    broker_symbol: str,
    company_name: str = "",
    index: list[SymbolRecord] | None = None,
    min_score: float = 0.86,
) -> SymbolMatch:
    """Resolve a broker symbol/company label to a canonical NSE symbol."""
    broker = str(broker_symbol or "").strip().upper()
    company = str(company_name or "").strip().upper()
    manual = _MANUAL_OVERRIDES.get((broker, company))
    if manual:
        return manual
    idx = index if index is not None else load_default_symbol_index()
    valid_symbols = {rec.symbol for rec in idx}
    if broker and broker in valid_symbols:
        return SymbolMatch(broker, "exact", 1.0, broker)

    query_key = _key(company_name)
    query_tokens = frozenset(query_key.split())
    if not query_tokens:
        return SymbolMatch(broker, "unmapped", 0.0, "")

    best: tuple[float, SymbolRecord] | None = None
    second_score = 0.0
    for rec in idx:
        overlap = len(query_tokens & rec.tokens) / max(len(query_tokens | rec.tokens), 1)
        coverage = len(query_tokens & rec.tokens) / max(min(len(query_tokens), len(rec.tokens)), 1)
        seq = SequenceMatcher(None, query_key, rec.key).ratio()
        substring_bonus = 0.0
        if query_key in rec.key or rec.key in query_key:
            substring_bonus = 0.08
        score = min(1.0, (0.55 * coverage) + (0.25 * overlap) + (0.20 * seq) + substring_bonus)
        if best is None or score > best[0]:
            second_score = best[0] if best is not None else 0.0
            best = (score, rec)
        elif score > second_score:
            second_score = score

    if best is None or best[0] < min_score:
        return SymbolMatch(broker, "unmapped", best[0] if best else 0.0, best[1].company_name if best else "")
    if best[0] - second_score < 0.04:
        return SymbolMatch(broker, "ambiguous", best[0], best[1].company_name)
    return SymbolMatch(best[1].symbol, "company_name", best[0], best[1].company_name)


def candidate_matches(
    *,
    broker_symbol: str,
    company_name: str = "",
    index: list[SymbolRecord] | None = None,
    limit: int = 8,
) -> list[SymbolRecord]:
    """Return top local candidates for deterministic or LLM adjudication."""
    broker = str(broker_symbol or "").strip().upper()
    query_key = _key(company_name)
    query_tokens = frozenset(query_key.split())
    idx = index if index is not None else load_default_symbol_index()
    scored: list[tuple[float, SymbolRecord]] = []
    for rec in idx:
        overlap = len(query_tokens & rec.tokens) / max(len(query_tokens | rec.tokens), 1)
        coverage = len(query_tokens & rec.tokens) / max(min(len(query_tokens), len(rec.tokens)), 1)
        seq = SequenceMatcher(None, query_key, rec.key).ratio() if query_key else 0.0
        prefix = SequenceMatcher(None, broker, rec.symbol).ratio() if broker else 0.0
        score = (0.50 * coverage) + (0.20 * overlap) + (0.20 * seq) + (0.10 * prefix)
        if query_key and (query_key in rec.key or rec.key in query_key):
            score += 0.08
        scored.append((min(1.0, score), rec))
    scored.sort(key=lambda item: item[0], reverse=True)
    out: list[SymbolRecord] = []
    seen: set[str] = set()
    for _score, rec in scored:
        if rec.symbol in seen:
            continue
        seen.add(rec.symbol)
        out.append(rec)
        if len(out) >= limit:
            break
    return out


def resolve_symbol_with_llm(
    *,
    broker_symbol: str,
    company_name: str,
    index: list[SymbolRecord] | None = None,
    client=None,
    model: str = "gpt-4o",
) -> SymbolMatch:
    """Use GPT-4o to choose from local candidate symbols, never free-form symbols."""
    candidates = candidate_matches(
        broker_symbol=broker_symbol,
        company_name=company_name,
        index=index,
        limit=8,
    )
    if not candidates:
        return SymbolMatch(str(broker_symbol or "").strip().upper(), "llm_unmapped", 0.0, "")

    candidate_symbols = {c.symbol for c in candidates}
    prompt = {
        "broker_symbol": str(broker_symbol or "").strip().upper(),
        "broker_company_name": str(company_name or "").strip(),
        "allowed_candidates": [
            {"symbol": c.symbol, "company_name": c.company_name, "source": c.source}
            for c in candidates
        ],
        "instruction": (
            "Choose the NSE symbol matching the broker holding. Return unmapped if none "
            "of the allowed candidates is clearly the same listed equity. Do not invent symbols."
        ),
    }

    if client is None:
        from openai import OpenAI

        client = OpenAI()

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You map Indian broker portfolio aliases to canonical NSE symbols. "
                    "Use only allowed_candidates. Prefer unmapped over a weak guess."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "portfolio_symbol_mapping",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "One allowed candidate symbol, or unmapped.",
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low", "unmapped"],
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": ["symbol", "confidence", "rationale"],
                },
            }
        },
    )
    try:
        payload = json.loads(response.output_text)
    except Exception:
        return SymbolMatch(str(broker_symbol or "").strip().upper(), "llm_invalid", 0.0, "")

    symbol = str(payload.get("symbol") or "").strip().upper()
    confidence = str(payload.get("confidence") or "").strip().lower()
    rationale = str(payload.get("rationale") or "").strip()
    if symbol == "UNMAPPED" or confidence == "unmapped":
        return SymbolMatch(str(broker_symbol or "").strip().upper(), "llm_unmapped", 0.0, "", rationale)
    if symbol not in candidate_symbols:
        return SymbolMatch(str(broker_symbol or "").strip().upper(), "llm_rejected", 0.0, "", rationale)
    score = {"high": 0.95, "medium": 0.8, "low": 0.6}.get(confidence, 0.0)
    if score < 0.8:
        return SymbolMatch(str(broker_symbol or "").strip().upper(), "llm_low_confidence", score, "", rationale)
    matched = next((c.company_name for c in candidates if c.symbol == symbol), "")
    return SymbolMatch(symbol, "llm", score, matched, rationale)
