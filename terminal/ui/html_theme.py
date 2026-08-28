from __future__ import annotations


def agent_adda_dark_css() -> str:
    """Primary Agent Adda dark HTML theme (Research Council look-and-feel)."""
    return """
:root { color-scheme: dark; --bg:#081018; --panel:#101a24; --line:#263746; --text:#e7eef5; --muted:#91a4b7; --green:#38d188; --red:#ff5f6d; --yellow:#f7c948; --cyan:#51d6ff; --mag:#d97bff; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
header { padding:20px 24px 12px; border-bottom:1px solid var(--line); background:#0b141d; position:sticky; top:0; z-index:2; }
footer { padding:16px 24px; border-top:1px solid var(--line); color:var(--muted); background:#0b141d; }
h1 { margin:0; font-size:22px; letter-spacing:0; }
h2 { margin:0 0 10px; font-size:15px; color:#d8f3ff; letter-spacing:0; }
h3 { margin:10px 0 6px; font-size:13px; color:var(--cyan); letter-spacing:0; }
.sub { color:var(--muted); margin-top:4px; }
.grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; padding:16px; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; min-width:0; overflow:auto; }
.wide { grid-column:span 3; }
.summary-panel { border-color:#1f4255; background:linear-gradient(180deg,#0f1c28,#101a24); }
.lede { font-size:18px; line-height:1.35; margin:0 0 12px; color:#f4fbff; font-weight:700; }
.summary-columns { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.kpi-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
.kpi { border-top:1px solid rgba(255,255,255,.07); padding:8px 0; min-width:0; }
.kpi span, .kpi em { display:block; color:var(--muted); font-size:12px; }
.kpi b { display:block; color:var(--text); margin:3px 0; overflow-wrap:anywhere; }
.metric { display:grid; grid-template-columns:1fr auto auto; gap:10px; align-items:center; border-top:1px solid rgba(255,255,255,.07); padding:7px 0; }
.metric span, .metric em, small, p, li span { color:var(--muted); }
.metric b { color:var(--text); }
.objective { border-top:1px solid rgba(255,255,255,.07); padding-top:10px; margin:10px 0 0; }
ul, ol { margin:8px 0 0 20px; padding:0; }
li { margin:5px 0; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; border-top:1px solid rgba(255,255,255,.08); padding:8px; vertical-align:top; }
th { color:var(--muted); font-weight:700; }
pre { white-space:pre-wrap; background:#07131d; border:1px solid #1f4255; padding:12px; border-radius:6px; overflow:auto; color:#cfe7f7; }
strong { color:#f5fbff; }
a { color:var(--cyan); text-decoration:none; }
a:hover { text-decoration:underline; }
.positive { color:var(--green); }
.negative { color:var(--red); }
.warning { color:var(--yellow); }
.neutral { color:var(--muted); }
.num { text-align:right; font-variant-numeric: tabular-nums; }
.nowrap { white-space:nowrap; }
@media (max-width: 900px) { .grid { grid-template-columns:1fr; } .wide { grid-column:span 1; } .summary-columns, .kpi-grid { grid-template-columns:1fr; } }
"""

