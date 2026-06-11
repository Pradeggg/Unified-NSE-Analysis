from __future__ import annotations

import shlex

from .fundamental_driver import FundamentalDriverResult, diagnose_fundamental_driver


_METRIC_ALIASES = {
    "eps": "eps",
    "earnings": "eps",
    "earnings-per-share": "eps",
    "roce": "roce",
    "return-on-capital-employed": "roce",
    "margin": "margin",
    "margins": "margin",
    "opm": "margin",
    "debt": "debt",
    "borrowings": "debt",
    "cashflow": "cashflow",
    "cash-flow": "cashflow",
    "cash": "cashflow",
}


def _parse_diagnose_command(text: str) -> tuple[str, str]:
    parts = shlex.split(text)
    if parts and parts[0].lower() == "/diagnose":
        parts = parts[1:]
    if len(parts) < 2:
        raise ValueError("Usage: /diagnose SYMBOL eps|roce|margin|debt|cashflow")
    symbol = parts[0].strip().upper()
    metric = _METRIC_ALIASES.get(parts[1].strip().lower())
    if not metric:
        raise ValueError("Metric must be one of: eps, roce, margin, debt, cashflow")
    return symbol, metric


def _format_bridge(bridge: dict) -> list[str]:
    if not bridge:
        return ["- No metric bridge available."]
    lines = []
    for key, value in bridge.items():
        label = key.replace("_", " ").title()
        suffix = "%" if key.endswith("_pct") else (" pp" if key.endswith("_pp") else "")
        lines.append(f"- {label}: {value}{suffix if value is not None and isinstance(value, (int, float)) else ''}")
    return lines


def render_fundamental_driver_result(result: FundamentalDriverResult) -> str:
    lines = [
        f"## Fundamental Driver Diagnosis — {result.symbol} {result.metric.upper()}",
        "",
        f"**Short Answer:** {result.short_answer}",
        "",
        "### Metric Bridge",
        *_format_bridge(result.metric_bridge),
        "",
        "### Evidence",
    ]
    lines.extend(f"- {item}" for item in (result.evidence or ("No evidence rows available.",)))
    lines.extend(
        [
            "",
            "### Interpretation",
            f"- {result.interpretation}",
            "",
            "### What to Watch",
        ]
    )
    lines.extend(f"- {item}" for item in (result.what_to_watch or ("Fresh financial statements",)))
    if result.warnings:
        lines.extend(["", "### Warnings"])
        lines.extend(f"- {item}" for item in result.warnings)
    lines.extend(["", "Not investment advice. For research and learning only."])
    return "\n".join(lines)


def handle_diagnose_command(text: str) -> str:
    try:
        symbol, metric = _parse_diagnose_command(text)
        result = diagnose_fundamental_driver(symbol, metric)
    except Exception as exc:
        return f"## Fundamental Driver Diagnosis\n\n**Error:** {exc}"
    return render_fundamental_driver_result(result)
