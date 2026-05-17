"""HTML dashboard generator for Strategy Council runs.

Renders a single self-contained HTML file summarizing a :class:`CouncilResult`.
No external templating library — pure ``str.format`` so the dependency
surface stays minimal. Sections rendered:

* **Header** — symbol, recommendation, locked strategy id, run timestamp.
* **Evidence snapshot** — as-of date, technical close, regime, factor,
  microstructure, missing/freshness summary.
* **Iterations table** — per-iteration candidate count, best validation
  return, critic verdicts.
* **Critiques summary** — aggregated issues and required changes.

The generator is defensive: any missing optional fields are rendered as
``—`` so partial enrichments still produce a readable dashboard.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from backtesting.strategy_council.types import CouncilResult


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".") if value != 0 else "0"
    return escape(str(value))


def _best_val_return(results: tuple) -> str:
    vals: list[float] = []
    for r in results:
        ret = r.metrics.get("total_return_pct")
        if isinstance(ret, (int, float)):
            vals.append(float(ret))
    if not vals:
        return "—"
    return f"{max(vals):.2f}%"


def _render_evidence(result: CouncilResult) -> str:
    ev = result.evidence
    regime = (ev.market or {}).get("regime") or {}
    factor = (ev.market or {}).get("factor_exposure") or {}
    micro = (ev.market or {}).get("microstructure") or {}
    rows = [
        ("Symbol", _fmt(ev.symbol)),
        ("As of", _fmt(ev.as_of)),
        ("Close", _fmt(ev.technical.get("close"))),
        ("Bars", _fmt(ev.technical.get("bars"))),
        ("Regime", _fmt(regime.get("regime")) + (f" (bias {regime.get('bias_pct')}%)" if regime.get("available") else "")),
        ("Beta", _fmt(factor.get("beta")) if factor.get("available") else "—"),
        ("ATR%", _fmt(micro.get("atr_pct")) if micro.get("available") else "—"),
        ("Missing", ", ".join(sorted(set(ev.missing))) or "—"),
        ("Freshness", ", ".join(f"{k}={v}" for k, v in (ev.freshness or {}).items()) or "—"),
    ]
    body = "".join(f"<tr><th>{escape(k)}</th><td>{v}</td></tr>" for k, v in rows)
    return f"<table class='kv'>{body}</table>"


def _render_iterations(result: CouncilResult) -> str:
    if not result.iterations:
        return "<p class='empty'>No iterations recorded.</p>"
    head = (
        "<tr><th>#</th><th>Candidates</th><th>Best train</th>"
        "<th>Best validation</th><th>Critic verdicts</th></tr>"
    )
    rows: list[str] = []
    for it in result.iterations:
        verdicts = ", ".join(f"{c.critic}:{c.verdict}" for c in it.critiques) or "—"
        rows.append(
            "<tr>"
            f"<td>{it.index}</td>"
            f"<td>{len(it.candidates)}</td>"
            f"<td>{_best_val_return(it.train_results)}</td>"
            f"<td>{_best_val_return(it.validation_results)}</td>"
            f"<td>{escape(verdicts)}</td>"
            "</tr>"
        )
    return f"<table class='grid'><thead>{head}</thead><tbody>{''.join(rows)}</tbody></table>"


def _render_critiques(result: CouncilResult) -> str:
    if not result.iterations:
        return ""
    final = result.iterations[-1].critiques
    if not final:
        return "<p class='empty'>No critiques in final iteration.</p>"
    blocks: list[str] = []
    for c in final:
        issues_html = "".join(f"<li>{escape(i)}</li>" for i in c.issues) or "<li>—</li>"
        changes_html = (
            "".join(f"<li>{escape(ch)}</li>" for ch in c.required_changes) or "<li>—</li>"
        )
        blocks.append(
            f"<section class='critic'>"
            f"<h3>{escape(c.critic)} — <span class='verdict {escape(c.verdict)}'>{escape(c.verdict)}</span></h3>"
            f"<h4>Issues</h4><ul>{issues_html}</ul>"
            f"<h4>Required changes</h4><ul>{changes_html}</ul>"
            f"</section>"
        )
    return "".join(blocks)


def _render_locked(result: CouncilResult) -> str:
    locked = result.locked_strategy
    if locked is None:
        return "<p class='empty'>No locked strategy.</p>"
    return (
        "<table class='kv'>"
        f"<tr><th>Strategy</th><td>{escape(locked.strategy_id)}</td></tr>"
        f"<tr><th>Horizon</th><td>{locked.horizon_days}d</td></tr>"
        f"<tr><th>Origin</th><td>{escape(locked.origin)}</td></tr>"
        f"<tr><th>Thesis</th><td>{escape(locked.thesis)}</td></tr>"
        "</table>"
    )


_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; color: #1a1a1a; }
h1 { margin: 0 0 0.5rem; }
h2 { margin-top: 2rem; border-bottom: 2px solid #ddd; padding-bottom: 0.25rem; }
.kv, .grid { border-collapse: collapse; margin: 0.5rem 0 1rem; }
.kv th, .kv td, .grid th, .grid td { border: 1px solid #ddd; padding: 0.35rem 0.7rem; }
.kv th { background: #f5f5f5; text-align: left; font-weight: 600; min-width: 8rem; }
.grid th { background: #f5f5f5; }
.recommendation { padding: 0.4rem 0.9rem; border-radius: 0.4rem; font-weight: 700; display: inline-block; }
.recommendation.TRADE_RESEARCH { background: #e7f6ec; color: #1f7a3a; }
.recommendation.WAIT { background: #fff7e0; color: #8a6d00; }
.recommendation.NO_TRADE { background: #fdecec; color: #b32d2d; }
.verdict { padding: 0.1rem 0.4rem; border-radius: 0.25rem; font-size: 0.85em; }
.verdict.accept { background: #e7f6ec; color: #1f7a3a; }
.verdict.revise { background: #fff7e0; color: #8a6d00; }
.verdict.reject { background: #fdecec; color: #b32d2d; }
.critic { margin: 0.7rem 0; padding: 0.6rem 0.9rem; background: #fafafa; border-left: 4px solid #888; }
.empty { color: #888; font-style: italic; }
footer { margin-top: 3rem; color: #888; font-size: 0.85em; }
"""


def render_dashboard_html(result: CouncilResult, *, generated_at: str | None = None) -> str:
    """Render the full HTML document for ``result``."""
    generated = generated_at or datetime.now().isoformat(timespec="seconds")
    title = f"Strategy Council — {result.config.symbol}"
    recommendation = result.recommendation
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{escape(title)}</h1>
<p>Recommendation: <span class="recommendation {escape(recommendation)}">{escape(recommendation)}</span></p>
<p><strong>Rationale:</strong> {escape(result.rationale)}</p>

<h2>Locked strategy</h2>
{_render_locked(result)}

<h2>Evidence</h2>
{_render_evidence(result)}

<h2>Iterations</h2>
{_render_iterations(result)}

<h2>Final critiques</h2>
{_render_critiques(result)}

<footer>Generated {escape(generated)}. Research-only output — not investment advice.</footer>
</body>
</html>
"""


def write_dashboard(
    result: CouncilResult,
    output_dir: Path | str,
    *,
    filename: str | None = None,
) -> Path:
    """Render and write the dashboard HTML; return the resulting path."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        symbol = (result.config.symbol or "council").upper().replace("/", "_")
        filename = f"dashboard_{symbol}_{ts}.html"
    path = out_dir / filename
    path.write_text(render_dashboard_html(result), encoding="utf-8")
    return path


__all__ = ["render_dashboard_html", "write_dashboard"]
