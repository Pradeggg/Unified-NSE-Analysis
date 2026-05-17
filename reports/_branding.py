"""Shared branding / disclaimer assets for all Agent Adda HTML reports.

PG-report-branding: Centralizes logo embed, header, disclaimer banners and
print-page header/footer so every report (sector_rotation, enhanced
comprehensive, etc.) shares the same look-and-feel.
"""
from __future__ import annotations

import base64
import html as _h
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_LOGO_PATH = ROOT / "docs" / "Agent-adda-logo.jpg"

AGENT_BRAND = "Agent Adda - Market Intelligence Agent"

DISCLAIMER_BANNER = (
    "This report is not investment advice. It is a learning journey demonstrating how AI "
    "and rules-based agents can be applied to financial markets. Validate all data, prices, "
    "liquidity, corporate events, and risk independently before making any financial decision."
)

PRINT_FOOTER_DISCLAIMER = (
    "Disclaimer: Not investment advice or a trading recommendation. Educational AI/rules-based "
    "market intelligence only. Use, replication, or trading action is at the user's own risk "
    "and legal obligation."
)

FULL_LEGAL_DISCLAIMER = (
    "This report is provided strictly for educational, research, and learning purposes as part of a journey "
    "to understand how AI agents and rules-based agents can be applied to financial-market data. It is not "
    "investment advice, trading advice, portfolio advice, a research recommendation, or a solicitation to buy, "
    "sell, hold, short, or otherwise transact in any security, derivative, index, fund, or financial instrument. "
    "The information, scores, signals, narratives, charts, model outputs, and examples in this report must not "
    "be replicated, redistributed, automated, or used with any intent of trading, recommending trades, advising "
    "others, managing money, or making financial decisions. Anyone choosing to use, interpret, adapt, copy, "
    "replicate, distribute, or act on this information does so entirely at their own risk, responsibility, and "
    "legal and regulatory obligation. Agent Adda is not a SEBI-registered investment adviser, research analyst, "
    "portfolio manager, broker, or any other SEBI-registered market intermediary. Agent Adda, its creators, "
    "contributors, systems, agents, and associated persons accept no responsibility or liability for losses, "
    "damages, legal consequences, regulatory consequences, tax consequences, opportunity costs, or any other "
    "implications arising directly or indirectly from the use of this information by any person or organization. "
    "All market data can be delayed, incomplete, inaccurate, stale, or affected by corporate actions, liquidity, "
    "data-provider issues, model limitations, prompt limitations, or rule-design limitations. Users must consult "
    "qualified SEBI-registered professionals and independently verify all facts before making any financial or "
    "legal decision."
)


def asset_data_uri(path: Path = AGENT_LOGO_PATH) -> str:
    """Return a `data:` URI for embedding a local image (logo) into HTML."""
    try:
        if not path.exists():
            return ""
        mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
    except Exception:
        return ""


# ── HTML fragments ────────────────────────────────────────────────────────────
def base_css() -> str:
    """Return the standard light-theme CSS shared across reports."""
    return """
:root{--bg:#f0f4f8;--card:#fff;--text:#1a2332;--muted:#64748b;--border:#e2e8f0;
--primary:#1e3a5f;--primary-alt:#2563eb;--hdr-h:56px;--nav-h:44px;--radius:8px;
--shadow:0 1px 3px rgba(0,0,0,.08);--shadow-md:0 4px 8px rgba(0,0,0,.1)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Inter",sans-serif;
background:var(--bg);color:var(--text);line-height:1.6;font-size:14px}
a{color:var(--primary-alt);text-decoration:none}

/* Header */
.site-hdr{background:var(--primary);color:#fff;position:sticky;top:0;z-index:200;
box-shadow:var(--shadow-md);height:var(--hdr-h)}
.hdr-inner{max-width:1400px;margin:0 auto;padding:0 20px;height:100%;display:flex;
align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.hdr-brand{display:flex;align-items:center;gap:10px;min-width:0}
.brand-logo{width:38px;height:38px;border-radius:8px;object-fit:cover;background:#fff;
border:1px solid rgba(255,255,255,.4);flex-shrink:0}
.hdr-copy{min-width:0}
.hdr-kicker{font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
color:rgba(255,255,255,.78);line-height:1.2;white-space:nowrap}
.hdr-title{font-size:1.05rem;font-weight:700;letter-spacing:-.02em;white-space:nowrap}
.hdr-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.mbadge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;
font-weight:600;white-space:nowrap}
.mbadge-date{background:rgba(255,255,255,.18);color:#fff}
.mbadge-data{background:rgba(255,255,255,.1);color:rgba(255,255,255,.85)}

/* Disclaimer banner */
.disc{background:#fff8e1;border-bottom:1px solid #ffe082;color:#5d4037;
padding:7px 20px;font-size:11px;text-align:center;line-height:1.45}
.disc strong{font-weight:800}
.print-page-header,.print-page-footer{display:none}

/* Nav */
.main-nav{background:var(--card);border-bottom:2px solid var(--border);position:sticky;
top:var(--hdr-h);z-index:190}
.nav-inner{max-width:1400px;margin:0 auto;padding:0 16px;display:flex;overflow-x:auto;gap:0}
.nav-btn{background:none;border:none;padding:10px 18px;font-size:13px;font-weight:500;
color:var(--muted);cursor:pointer;border-bottom:2.5px solid transparent;margin-bottom:-2px;
transition:all .15s;white-space:nowrap}
.nav-btn:hover{color:var(--primary-alt)}
.nav-btn.active{color:var(--primary);border-bottom-color:var(--primary);font-weight:700}

/* Content */
.content{max-width:1400px;margin:0 auto;padding:20px}
.tab-pane{display:none}.tab-pane.active{display:block}

/* Metric cards */
.metrics-row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.metric-card{flex:1;min-width:160px;background:var(--card);border-radius:var(--radius);
border:1px solid var(--border);padding:14px 16px;box-shadow:var(--shadow)}
.metric-label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;
color:var(--muted);margin-bottom:5px}
.metric-value{font-size:1.6rem;font-weight:800;color:var(--primary);line-height:1}
.metric-sub{font-size:11px;color:var(--muted);margin-top:3px}

/* Cards */
.card{background:var(--card);border-radius:var(--radius);border:1px solid var(--border);
box-shadow:var(--shadow);padding:18px;margin-bottom:16px}
.card-title{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
color:var(--muted);margin-bottom:10px}
.card h2{font-size:16px;color:var(--primary);margin:0 0 10px}

/* Tables */
.tbl-wrap{display:block;width:100%;overflow-x:auto;border-radius:var(--radius);
border:1px solid var(--border);background:var(--card);margin-bottom:16px;
box-shadow:var(--shadow)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#f8fafc;color:#334155;text-align:left;padding:10px 12px;font-weight:700;
font-size:11px;text-transform:uppercase;letter-spacing:.04em;border-bottom:2px solid var(--border);
position:sticky;top:0;cursor:pointer;user-select:none;white-space:nowrap}
th.sortable::after{content:" ↕";color:#cbd5e1;font-size:9px}
th.sort-asc::after{content:" ▲";color:var(--primary-alt)}
th.sort-desc::after{content:" ▼";color:var(--primary-alt)}
td{padding:9px 12px;border-top:1px solid var(--border);white-space:nowrap}
tbody tr:hover td{background:#f8fafc}
.num{font-variant-numeric:tabular-nums;text-align:right}
.pos{color:#16a34a;font-weight:600}.neg{color:#dc2626;font-weight:600}
.muted{color:var(--muted)}

/* Badges */
.badge{display:inline-block;padding:3px 9px;border-radius:999px;font-size:10px;
font-weight:800;text-transform:uppercase;letter-spacing:.04em}
.b-STRONGBUY{background:#dcfce7;color:#14532d}
.b-BUY{background:#d1fae5;color:#047857}
.b-HOLD{background:#fef9c3;color:#854d0e}
.b-WEAKHOLD{background:#ffedd5;color:#c2410c}
.b-SELL{background:#fee2e2;color:#991b1b}
.b-BULLISH{background:#dcfce7;color:#166534}
.b-NEUTRAL{background:#f1f5f9;color:#475569}
.b-BEARISH{background:#fee2e2;color:#991b1b}
.dot{display:inline-block;width:14px;text-align:center;font-weight:700}
.dot.ok{color:#16a34a}.dot.no{color:#dc2626}

/* Legal disclaimer pane */
.legal-disclaimer{background:#fff;border:1px solid var(--border);border-radius:var(--radius);
box-shadow:var(--shadow);padding:22px;margin-top:16px}
.legal-disclaimer h2{font-size:18px;color:var(--primary);margin-bottom:10px}
.legal-disclaimer p{font-size:13px;line-height:1.75;color:var(--text);margin-bottom:10px}
.legal-disclaimer .legal-alert{font-weight:800;color:#991b1b;background:#fef2f2;
border:1px solid #fecaca;border-radius:6px;padding:10px 12px}

/* Print */
@media print{
  .main-nav,.disc{display:none!important}
  .tab-pane{display:block!important;page-break-inside:avoid}
  .site-hdr{position:relative!important;box-shadow:none}
  .print-page-footer{display:block!important;position:fixed;bottom:0;left:0;right:0;
    min-height:12mm;border-top:1px solid #cbd5e1;background:#fff;color:#475569;
    font-size:7.5px;line-height:1.25;padding:2mm 7mm;z-index:9999;
    -webkit-print-color-adjust:exact;print-color-adjust:exact}
  .legal-disclaimer{break-before:page;page-break-before:always;box-shadow:none;border:1px solid #cbd5e1}
  body{background:#fff}
}
"""


def header_html(report_title: str, meta_badges: list[str]) -> str:
    """Sticky header with Agent Adda logo + brand + report title + meta badges."""
    logo_uri = asset_data_uri()
    logo_tag = (
        f'<img class="brand-logo" src="{logo_uri}" alt="Agent Adda logo">'
        if logo_uri else ""
    )
    badges = "".join(
        f'<span class="mbadge {"mbadge-date" if i==0 else "mbadge-data"}">{_h.escape(b)}</span>'
        for i, b in enumerate(meta_badges)
    )
    return (
        '<header class="site-hdr"><div class="hdr-inner">'
        '<div class="hdr-brand">'
        f'{logo_tag}'
        '<div class="hdr-copy">'
        f'<div class="hdr-kicker">{_h.escape(AGENT_BRAND)}</div>'
        f'<div class="hdr-title">{_h.escape(report_title)}</div>'
        '</div></div>'
        f'<div class="hdr-meta">{badges}</div>'
        '</div></header>'
    )


def disclaimer_strip() -> str:
    """Yellow disclaimer banner under the header."""
    return (
        '<div class="disc"><strong>Disclaimer:</strong> '
        f'{_h.escape(DISCLAIMER_BANNER)}</div>'
    )


def print_only_header_footer(report_title: str) -> str:
    """Hidden-on-screen, visible-in-print header & footer for paginated PDFs."""
    return (
        f'<div class="print-page-header"><span>{_h.escape(AGENT_BRAND)}</span>'
        f'<span>{_h.escape(report_title)}</span></div>'
        f'<div class="print-page-footer">{_h.escape(PRINT_FOOTER_DISCLAIMER)}</div>'
    )


def full_legal_pane() -> str:
    """The standalone tab-pane containing the long-form legal disclaimer."""
    return (
        '<section id="tab-disclaimer" class="tab-pane">'
        '<div class="legal-disclaimer">'
        '<h2>Full Disclaimer &amp; Use Restrictions</h2>'
        f'<p class="legal-alert">{_h.escape(PRINT_FOOTER_DISCLAIMER)}</p>'
        f'<p>{_h.escape(FULL_LEGAL_DISCLAIMER)}</p>'
        '</div></section>'
    )


def tab_nav_script() -> str:
    """Vanilla JS: tab switcher + sortable tables (click any th)."""
    return """
<script>
(function(){
  // Tabs
  var btns=document.querySelectorAll('.nav-btn');
  var panes=document.querySelectorAll('.tab-pane');
  function activate(name){
    btns.forEach(function(b){b.classList.toggle('active',b.dataset.tab===name)});
    panes.forEach(function(p){p.classList.toggle('active',p.id==='tab-'+name)});
  }
  btns.forEach(function(b){b.addEventListener('click',function(){activate(b.dataset.tab)})});

  // Sortable tables — click <th data-sort="num|str"> to toggle sort
  document.querySelectorAll('table.sortable').forEach(function(tbl){
    var ths=tbl.querySelectorAll('thead th');
    ths.forEach(function(th,idx){
      if(th.dataset.sort==='off') return;
      th.classList.add('sortable');
      th.addEventListener('click',function(){
        var asc=!th.classList.contains('sort-asc');
        ths.forEach(function(t){t.classList.remove('sort-asc','sort-desc')});
        th.classList.add(asc?'sort-asc':'sort-desc');
        var rows=Array.from(tbl.tBodies[0].rows);
        var kind=th.dataset.sort||'str';
        rows.sort(function(a,b){
          var va=(a.cells[idx].dataset.v!==undefined?a.cells[idx].dataset.v:a.cells[idx].textContent).trim();
          var vb=(b.cells[idx].dataset.v!==undefined?b.cells[idx].dataset.v:b.cells[idx].textContent).trim();
          if(kind==='num'){va=parseFloat(va)||0;vb=parseFloat(vb)||0;return asc?va-vb:vb-va}
          return asc?va.localeCompare(vb):vb.localeCompare(va);
        });
        rows.forEach(function(r){tbl.tBodies[0].appendChild(r)});
      });
    });
  });
})();
</script>
"""
