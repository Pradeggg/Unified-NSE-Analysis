"""
Shared CSS design tokens for all Agent Adda HTML reports.

Usage in any generator:
    from reports.report_styles import SHARED_CSS_ROOT, BASE_BODY_CSS, SHARED_TABLE_CSS

    html = f"<style>{SHARED_CSS_ROOT}{BASE_BODY_CSS}{MY_COMPONENT_CSS}</style>"

Token contract — all reports MUST use these variable names:
  Layout:   --bg, --card, --border, --radius, --shadow, --shadow-md
  Text:     --text, --muted
  Brand:    --primary, --primary-alt
  Signals:  --good, --risk, --watch
"""

# ── Canonical CSS custom property root ──────────────────────────────────────
# All six report generators import and embed this block.
# Never override individual tokens without importing the full set first.
SHARED_CSS_ROOT: str = (
    ":root{"
    "--bg:#f0f4f8;"
    "--card:#ffffff;"
    "--border:#e2e8f0;"
    "--soft-border:#f1f5f9;"
    "--text:#1a2332;"
    "--muted:#64748b;"
    "--primary:#1e3a5f;"
    "--primary-alt:#2563eb;"
    "--good:#16a34a;"
    "--risk:#dc2626;"
    "--watch:#d97706;"
    "--radius:8px;"
    "--shadow:0 1px 3px rgba(0,0,0,.08);"
    "--shadow-md:0 4px 8px rgba(0,0,0,.10);"
    "--hdr-h:56px;"
    "--container:1400px;"
    "}"
)

# ── Dark-panel variant (for RRG / chart-heavy reports) ──────────────────────
# Keep token names identical; swap to dark palette.
SHARED_CSS_ROOT_DARK: str = (
    ":root{"
    "--bg:#0f172a;"
    "--card:#1e293b;"
    "--border:#334155;"
    "--soft-border:#1e293b;"
    "--text:#e2e8f0;"
    "--muted:#94a3b8;"
    "--primary:#38bdf8;"
    "--primary-alt:#60a5fa;"
    "--good:#4ade80;"
    "--risk:#f87171;"
    "--watch:#fbbf24;"
    "--radius:12px;"
    "--shadow:0 2px 8px rgba(0,0,0,.35);"
    "--shadow-md:0 6px 20px rgba(0,0,0,.45);"
    "--hdr-h:56px;"
    "--container:1440px;"
    "}"
)

# ── Base body + box-sizing reset ─────────────────────────────────────────────
BASE_BODY_CSS: str = (
    "*{box-sizing:border-box}"
    "html{scroll-behavior:smooth}"
    "body{"
    "margin:0;"
    "background:var(--bg);"
    "color:var(--text);"
    "font-family:'Inter','Segoe UI',-apple-system,BlinkMacSystemFont,sans-serif;"
    "font-size:14px;"
    "line-height:1.6;"
    "}"
    "a{color:var(--primary-alt);text-decoration:none}"
    "a:hover{text-decoration:underline}"
)

# ── Shared table styles ───────────────────────────────────────────────────────
SHARED_TABLE_CSS: str = (
    ".tbl-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:var(--radius)}"
    "table{width:100%;border-collapse:collapse;font-size:13px}"
    "th,td{border-bottom:1px solid var(--border);padding:9px 8px;text-align:left;vertical-align:top}"
    "th{"
    "color:var(--muted);"
    "font-size:11px;"
    "text-transform:uppercase;"
    "letter-spacing:.06em;"
    "background:var(--soft-border);"
    "font-weight:600;"
    "}"
    "tr:last-child td{border-bottom:0}"
    "tr:hover td{background:#f8fafc}"
    ".num{text-align:right;font-variant-numeric:tabular-nums}"
)

# ── Signal / status pills ─────────────────────────────────────────────────────
SHARED_PILL_CSS: str = (
    ".pill{"
    "display:inline-flex;align-items:center;"
    "border-radius:999px;"
    "padding:3px 10px;"
    "font-size:11px;"
    "font-weight:700;"
    "text-transform:uppercase;"
    "letter-spacing:.04em;"
    "}"
    ".pill-good{background:#dcfce7;color:#166534}"
    ".pill-risk{background:#fee2e2;color:#991b1b}"
    ".pill-watch{background:#fef9c3;color:#854d0e}"
    ".pill-neutral{background:var(--soft-border);color:var(--muted)}"
    ".pill-primary{background:#dbeafe;color:#1e40af}"
)

# ── Card component ────────────────────────────────────────────────────────────
SHARED_CARD_CSS: str = (
    ".card{"
    "background:var(--card);"
    "border:1px solid var(--border);"
    "border-radius:var(--radius);"
    "padding:16px;"
    "box-shadow:var(--shadow);"
    "}"
    ".card+.card{margin-top:12px}"
)

# ── Container wrapper ─────────────────────────────────────────────────────────
SHARED_LAYOUT_CSS: str = (
    ".wrap{max-width:var(--container);margin:0 auto;padding:24px 16px}"
    ".section{margin-top:16px}"
    ".grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}"
    ".grid-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}"
    "@media(max-width:768px){"
    ".grid-2,.grid-3{grid-template-columns:1fr}"
    "}"
)

# ── Viewport meta tag (always include in <head>) ──────────────────────────────
VIEWPORT_META: str = '<meta name="viewport" content="width=device-width,initial-scale=1">'

# ── Convenience bundle (root + body + table + pill + card + layout) ──────────
ALL_SHARED_CSS: str = (
    SHARED_CSS_ROOT
    + BASE_BODY_CSS
    + SHARED_TABLE_CSS
    + SHARED_PILL_CSS
    + SHARED_CARD_CSS
    + SHARED_LAYOUT_CSS
)

ALL_SHARED_CSS_DARK: str = (
    SHARED_CSS_ROOT_DARK
    + BASE_BODY_CSS
    + SHARED_TABLE_CSS
    + SHARED_PILL_CSS
    + SHARED_CARD_CSS
    + SHARED_LAYOUT_CSS
)
