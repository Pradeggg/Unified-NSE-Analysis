#!/usr/bin/env python3
"""
fund_dashboard_build.py — Combine fund_lab.html + fund_inception HTML
into a single tabbed fund_dashboard.html with properly scoped CSS.

Usage:
    python tools/fund_dashboard_build.py
    python tools/fund_dashboard_build.py --open
    python tools/fund_dashboard_build.py --inception reports/latest/fund_inception_20260815.html

Reads:
    reports/latest/fund_lab.html
    reports/latest/fund_inception_YYYYMMDD.html  (latest found automatically)

Writes:
    reports/latest/fund_dashboard.html
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
LATEST = ROOT / "reports" / "latest"
OUT   = LATEST / "fund_dashboard.html"


# ── helpers ────────────────────────────────────────────────────────────────────

def get_html(path: Path) -> str:
    return path.read_text()

def extract_body(html: str) -> str:
    m = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    return m.group(1).strip() if m else html

def extract_styles(html: str) -> str:
    parts = re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
    return "\n".join(parts)


def scope_css(css: str, scope_id: str) -> str:
    """
    Prefix every CSS rule with `scope_id` so styles from two pages
    don't bleed into each other.

    Strips:  :root{}, html{}, *,*::before,*::after{} — handled centrally.
    Converts: body{} → scope_id (tab container becomes the layout root).
    Recurses: into @media blocks.
    """
    # strip global resets that we handle once at the top
    css = re.sub(r':root\s*\{[^}]*\}',                      '', css, flags=re.DOTALL)
    css = re.sub(r'html\s*\{[^}]*\}',                       '', css, flags=re.DOTALL)
    css = re.sub(r'\*\s*,\s*\*::before\s*,\s*\*::after\s*\{[^}]*\}', '', css, flags=re.DOTALL)

    result = []
    i = 0
    while i < len(css):
        # @media / @keyframes — recurse into body
        m = re.match(r'(@(?:media|keyframes)[^{]*)\{', css[i:], re.DOTALL)
        if m:
            prefix = m.group(0)
            depth, j = 0, i + len(prefix) - 1
            while j < len(css):
                if css[j] == '{':  depth += 1
                elif css[j] == '}':
                    depth -= 1
                    if depth == 0:
                        inner = css[i + len(prefix):j]
                        result.append(prefix + scope_css(inner, scope_id) + '}')
                        i = j + 1
                        break
                j += 1
            else:
                i = j
            continue

        # comments — pass through
        m = re.match(r'(/\*.*?\*/\s*)', css[i:], re.DOTALL)
        if m:
            result.append(m.group(1))
            i += len(m.group(1))
            continue

        # ordinary rule
        m = re.match(r'([^{@/]+)\{([^}]*)\}', css[i:], re.DOTALL)
        if m:
            sel_raw = m.group(1).strip()
            body    = m.group(2)
            scoped  = []
            for sel in sel_raw.split(','):
                sel = sel.strip()
                if not sel:
                    continue
                if sel == 'body':
                    scoped.append(scope_id)
                else:
                    scoped.append(f'{scope_id} {sel}')
            if scoped:
                result.append(', '.join(scoped) + ' {' + body + '}\n')
            i += len(m.group(0))
            continue

        result.append(css[i])
        i += 1

    return ''.join(result)


# ── unified base CSS (dark theme, tab chrome) ──────────────────────────────────

BASE_CSS = """
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }

/* ── Unified dark palette ── */
:root {
  /* Accent */
  --acc:#00ccb0; --acc-dim:rgba(0,204,176,.13);

  /* Surfaces (Fund Lab dark) */
  --bg:#07101c;  --surface:#0d1b2a; --card:#132337; --card-hi:#172b42;
  --bdr:#1e3348; --bdr-hi:#28466a;

  /* Text */
  --tx:#dceaf8;  --tx-m:#4d6f8e;  --tx-d:#253d54;

  /* Semantic colours */
  --gain:#1ed97a;  --gain-dim:rgba(30,217,122,.13);
  --loss:#ff4560;  --loss-dim:rgba(255,69,96,.13);
  --warn:#f5a623;
  --sc-col:#7bc8f5; --mc-col:#e8932d;

  /* Order-sheet semantic (dark-mapped) */
  --border:#1e3348;
  --text:#dceaf8;  --text2:#4d6f8e; --text3:#253d54;
  --hold:#1ed97a;  --add:#58a6ff;   --exit:#ff4560;  --weak:#f5a623;
  --shadow:0 1px 4px rgba(0,0,0,.3);

  /* Typography */
  --mono:'SF Mono','Cascadia Code','Fira Code',ui-monospace,Menlo,monospace;
  --sans:-apple-system,BlinkMacSystemFont,'Inter','Helvetica Neue',sans-serif;
}

html  { font-size:14px; background:var(--bg); color:var(--tx); }
body  { font-family:var(--sans); background:var(--bg); color:var(--tx); margin:0; padding:0; }

/* ── Tab bar ── */
.tab-bar {
  display:flex; gap:0;
  border-bottom:2px solid var(--bdr);
  background:var(--surface);
  padding:0 20px;
  position:sticky; top:0; z-index:100;
}
.tab-btn {
  padding:12px 24px; cursor:pointer; border:none; background:none;
  color:var(--tx-m); font-size:14px; font-weight:600;
  border-bottom:3px solid transparent; margin-bottom:-2px;
  transition:color .15s, border-color .15s;
}
.tab-btn:hover  { color:var(--tx); }
.tab-btn.active { color:#58a6ff; border-bottom-color:#58a6ff; }

.tab-pane         { display:none; }
.tab-pane.active  { display:block; padding:20px 24px; max-width:1300px; margin:0 auto; }
"""

TAB_JS = """
function switchTab(id, btn) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}
"""


# ── find latest inception HTML ─────────────────────────────────────────────────

def find_inception(override: str | None) -> Path:
    if override:
        p = Path(override)
        if not p.exists():
            sys.exit(f"ERROR: inception file not found: {override}")
        return p
    candidates = sorted(LATEST.glob("fund_inception_*.html"), reverse=True)
    if not candidates:
        sys.exit("ERROR: no fund_inception_*.html found in reports/latest/")
    return candidates[0]


# ── main ───────────────────────────────────────────────────────────────────────

def build(inception_path: Path | None = None) -> Path:
    lab_path      = LATEST / "fund_lab.html"
    inception_path = find_inception(str(inception_path) if inception_path else None)

    if not lab_path.exists():
        sys.exit(f"ERROR: {lab_path} not found — run: python tools/fund_lab_pnl.py --report")

    lab_html   = get_html(lab_path)
    order_html = get_html(inception_path)

    lab_body   = extract_body(lab_html)
    order_body = extract_body(order_html)

    lab_css   = scope_css(extract_styles(lab_html),   "#tab-lab")
    order_css = scope_css(extract_styles(order_html), "#tab-orders")

    dashboard = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fund Dashboard — Agent Adda</title>
<style>
{BASE_CSS}
/* ── Fund Lab (scoped) ── */
{lab_css}
/* ── Order Sheet (scoped) ── */
{order_css}
</style>
</head><body>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('tab-lab',this)">📊 Fund Lab — P&amp;L</button>
  <button class="tab-btn" onclick="switchTab('tab-orders',this)">📋 Order Sheet</button>
</div>

<div id="tab-lab" class="tab-pane active">
{lab_body}
</div>

<div id="tab-orders" class="tab-pane">
{order_body}
</div>

<script>{TAB_JS}</script>
</body></html>"""

    OUT.write_text(dashboard)
    print(f"✓  fund_dashboard.html  ({len(dashboard):,} bytes)")
    print(f"   lab:      {lab_path.name}")
    print(f"   orders:   {inception_path.name}")
    return OUT


def main():
    ap = argparse.ArgumentParser(description="Rebuild fund_dashboard.html")
    ap.add_argument("--inception", metavar="PATH",
                    help="Path to fund_inception HTML (default: latest in reports/latest/)")
    ap.add_argument("--open", action="store_true", dest="open_browser",
                    help="Open the dashboard in the default browser after building")
    args = ap.parse_args()

    out = build(Path(args.inception) if args.inception else None)

    if args.open_browser:
        import subprocess
        subprocess.run(["open", str(out)])


if __name__ == "__main__":
    main()
