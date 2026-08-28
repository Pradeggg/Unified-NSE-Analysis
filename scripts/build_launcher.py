#!/usr/bin/env python3
"""
scripts/build_launcher.py — Agent Adda Command Centre generator.

Scrapes skill cards (skill_store/stored/*.yml, skill_store/generated/*.yml),
merges hard-coded REPL commands + screeners, and generates:
  • reports/latest/launcher_data.json  — unified command catalogue
  • reports/latest/launcher.html       — dark-terminal command palette (Cmd+K)

Usage:
    python scripts/build_launcher.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # PyYAML
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "reports" / "latest"

# ── Single source of truth: import catalogue from tools/command_center.py ────
# This ensures the browser launcher always reflects the same 135+ commands
# that the terminal TUI shows. Never edit the lists here — edit command_center.py.

sys.path.insert(0, str(ROOT))
try:
    from tools.command_center import _REPL_COMMANDS, _SCREENERS, _PIPELINE
    _HAVE_CC = True
except Exception:
    _REPL_COMMANDS = _SCREENERS = _PIPELINE = []  # type: ignore[assignment]
    _HAVE_CC = False

def _cc_to_launcher(items: list[dict], category: str) -> list[dict[str, Any]]:
    """Convert command_center format → launcher format."""
    out = []
    for item in items:
        desc = item.get("desc", item.get("description", ""))
        out.append({
            "id":          item["id"],
            "description": desc,
            "tags":        item.get("tags", []),
            "cli":         item.get("cli", ""),
            "category":    category,
        })
    return out

REPL_COMMANDS = _cc_to_launcher(_REPL_COMMANDS, "repl")
SCREENERS     = _cc_to_launcher(_SCREENERS, "screener")
PIPELINE      = _cc_to_launcher(_PIPELINE, "pipeline")

# ── Skill card loader ─────────────────────────────────────────────────────────

def _load_yml_skills(directory: Path, skip_status: str | None = None) -> list[dict[str, Any]]:
    if not HAVE_YAML:
        return []
    skills = []
    for f in sorted(directory.glob("*.yml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            if skip_status and data.get("status") == skip_status:
                continue
            meta = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
            skill_id = data.get("id", f.stem)
            input_patterns = data.get("input_patterns", []) or []
            cli = meta.get("cli", "")
            if not cli and input_patterns:
                cli = f'AGENT_ADDA_SKILL_STORE=1 .venv/bin/python3 nse_agent.py --query "{input_patterns[0]}"'
            if not cli:
                cli = f'AGENT_ADDA_SKILL_STORE=1 .venv/bin/python3 nse_agent.py --query "{skill_id}"'
            item: dict[str, Any] = {
                "id":             skill_id,
                "description":    data.get("description", "").strip(),
                "tags":           meta.get("tags") or data.get("tags") or [],
                "input_patterns": input_patterns,
                "cli":            cli,
                "category":       "skill",
                "status":         data.get("status", ""),
            }
            skills.append(item)
        except Exception:
            pass
    return skills


def build_catalogue() -> list[dict[str, Any]]:
    seed_cards = _load_yml_skills(ROOT / "terminal" / "skills" / "seed_cards")
    stored     = _load_yml_skills(ROOT / "skill_store" / "stored")
    generated  = _load_yml_skills(ROOT / "skill_store" / "generated", skip_status="test_failed")

    all_items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(items: list[dict]) -> None:
        for item in items:
            key = item["id"].lower()
            if key not in seen:
                seen.add(key)
                all_items.append(item)

    # Skill cards first (most authoritative descriptions)
    _add(seed_cards)
    _add(stored)
    _add(generated)
    # Then command_center catalogue (single source of truth)
    _add(REPL_COMMANDS)
    _add(SCREENERS)
    _add(PIPELINE)
    return all_items


# ── HTML generator ────────────────────────────────────────────────────────────

_LAUNCHER_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Adda — Command Centre</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--surface:#161b22;--border:#21262d;--border2:#30363d;
  --text:#e6edf3;--dim:#8b949e;--dimmer:#484f58;--accent:#388bfd;
}
html,body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:13px;min-height:100vh}
/* header */
#header{display:flex;align-items:center;justify-content:space-between;padding:0 20px;height:52px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0}
.h-title{font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:600;color:var(--text)}
.h-hint{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--dimmer);background:var(--border);padding:2px 8px;border-radius:4px;border:1px solid var(--border2)}
/* search bar */
#search-wrap{padding:14px 20px;background:var(--bg);border-bottom:1px solid var(--border)}
#search{width:100%;font-family:'JetBrains Mono',monospace;font-size:14px;background:var(--surface);border:1px solid var(--border2);border-radius:6px;color:var(--text);padding:10px 14px;outline:none;transition:border .1s}
#search:focus{border-color:var(--accent)}
#search::placeholder{color:var(--dimmer)}
/* category tabs */
#tabs{display:flex;align-items:center;gap:4px;padding:8px 20px;background:var(--bg);border-bottom:1px solid var(--border);flex-wrap:wrap}
.tab-btn{font-family:'JetBrains Mono',monospace;font-size:11px;padding:4px 12px;border-radius:4px;cursor:pointer;color:var(--dim);background:transparent;border:1px solid transparent;transition:all .1s;user-select:none;display:flex;align-items:center;gap:5px}
.tab-btn:hover{color:var(--text);background:var(--border)}
.tab-btn.active{color:var(--text);background:rgba(56,139,253,0.15);border-color:var(--accent)}
.tab-count{font-size:9px;background:rgba(56,139,253,0.2);color:#58a6ff;border-radius:8px;padding:0 5px;font-weight:600}
/* cards grid */
#results{padding:14px 20px;display:flex;flex-direction:column;gap:8px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px 14px;cursor:pointer;transition:border .1s;display:flex;flex-direction:column;gap:6px}
.card:hover,.card.active{border-color:var(--accent);background:rgba(56,139,253,0.04)}
.card-header{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.card-name{font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:600;color:var(--text)}
.card-tags{display:flex;gap:4px;flex-wrap:wrap;flex-shrink:0}
.tag{font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 6px;border-radius:3px;font-weight:500}
.tag-chart,.tag-technical{background:rgba(88,166,255,0.12);color:#58a6ff}
.tag-screener,.tag-vcp,.tag-stage2{background:rgba(38,166,65,0.12);color:#3fb950}
.tag-admin,.tag-postgres,.tag-health,.tag-pipeline{background:rgba(240,136,62,0.12);color:#f0883e}
.tag-fno,.tag-intraday,.tag-derivatives,.tag-options{background:rgba(188,140,255,0.12);color:#bc8cff}
.tag-tracker,.tag-stage{background:rgba(57,211,83,0.12);color:#39d353}
.tag-market,.tag-overview,.tag-breadth,.tag-regime{background:rgba(165,214,255,0.12);color:#a5d6ff}
.tag-skill{background:rgba(56,139,253,0.12);color:#58a6ff}
.tag-default{background:rgba(139,148,158,0.12);color:#8b949e}
.card-desc{font-size:11px;color:var(--dim);line-height:1.5}
.card-cli-row{display:flex;align-items:center;gap:6px}
.card-cli{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--dimmer);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.copy-btn{flex-shrink:0;background:transparent;border:none;cursor:pointer;font-size:13px;padding:0 2px;line-height:1;opacity:0.6;transition:opacity .1s}
.copy-btn:hover{opacity:1}
/* empty */
#empty{display:none;padding:40px;text-align:center;color:var(--dimmer);font-family:'JetBrains Mono',monospace;font-size:12px;line-height:2}
/* footer */
#footer{padding:12px 20px;font-size:10px;color:var(--dimmer);font-family:'JetBrains Mono',monospace;border-top:1px solid var(--border);margin-top:auto}
/* toast */
#toast{position:fixed;bottom:24px;right:24px;background:var(--surface);border:1px solid var(--accent);border-radius:6px;padding:8px 16px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text);opacity:0;transition:opacity .2s;pointer-events:none;z-index:999}
#toast.show{opacity:1}
</style>
</head>
<body>
<div id="header">
  <span class="h-title">🤖 Agent Adda — Command Centre</span>
  <span class="h-hint">⌘K</span>
</div>
<div id="search-wrap">
  <input id="search" type="text" placeholder="🔍  Search commands, skills, screeners…" autocomplete="off" spellcheck="false">
</div>
<div id="tabs"></div>
<div id="results"></div>
<div id="empty">No commands match your search.<br>Try a symbol name, tag, or run <code>agent-adda doctor</code></div>
<div id="footer"><!-- populated by JS --></div>
<div id="toast">📋 Copied!</div>

<script>
const CATALOGUE = __CATALOGUE_JSON__;
const CATS = ['All','Skills','Screeners','Reports','Admin','REPL'];
const CAT_MAP = {skill:'Skills',screener:'Screeners',report:'Reports',admin:'Admin',repl:'REPL'};

let currentCat='All', query='', activeIdx=-1;

function tagClass(t){
  const m={chart:'tag-chart',technical:'tag-technical',screener:'tag-screener',
    vcp:'tag-vcp',stage2:'tag-stage2',admin:'tag-admin',postgres:'tag-postgres',
    health:'tag-health',pipeline:'tag-pipeline',fno:'tag-fno',intraday:'tag-intraday',
    derivatives:'tag-derivatives',options:'tag-options',tracker:'tag-tracker',
    stage:'tag-stage',market:'tag-market',overview:'tag-overview',breadth:'tag-breadth',
    regime:'tag-regime',skill:'tag-skill'};
  return m[t]||'tag-default';
}

function fuzzyScore(item, q){
  if(!q) return 1;
  const s=(item.id+' '+item.description+' '+(item.tags||[]).join(' ')+' '+(item.input_patterns||[]).join(' ')).toLowerCase();
  const terms=q.toLowerCase().split(/\\s+/);
  let score=0;
  for(const t of terms){
    if(s.includes(t)) score+=(item.id.toLowerCase().includes(t)?3:1);
    else return 0;
  }
  return score;
}

function getCatName(item){return CAT_MAP[item.category]||'Skills';}

function getFiltered(){
  return CATALOGUE
    .map(c=>({...c,_s:fuzzyScore(c,query)}))
    .filter(c=>c._s>0 && (currentCat==='All'||getCatName(c)===currentCat))
    .sort((a,b)=>b._s-a._s);
}

function copyText(text,btn){
  navigator.clipboard.writeText(text).then(()=>{
    const t=document.getElementById('toast');
    t.classList.add('show');
    if(btn){const orig=btn.textContent;btn.textContent='✓';setTimeout(()=>btn.textContent=orig,1000);}
    setTimeout(()=>t.classList.remove('show'),1500);
  }).catch(()=>{});
}

function renderTabs(filtered){
  const counts={All:filtered.length};
  for(const c of CATS.slice(1)) counts[c]=filtered.filter(x=>getCatName(x)===c).length;
  // Recount All from unfiltered query results (ignore cat filter)
  const allFiltered=CATALOGUE.map(c=>({...c,_s:fuzzyScore(c,query)})).filter(c=>c._s>0);
  counts.All=allFiltered.length;
  for(const c of CATS.slice(1)) counts[c]=allFiltered.filter(x=>getCatName(x)===c).length;

  document.getElementById('tabs').innerHTML=CATS.map(c=>`
    <button class="tab-btn${currentCat===c?' active':''}" onclick="setTab('${c}')">
      ${c}<span class="tab-count">${counts[c]||0}</span>
    </button>`).join('');
}

function renderCards(filtered){
  const res=document.getElementById('results');
  const emp=document.getElementById('empty');
  if(!filtered.length){
    res.innerHTML='';emp.style.display='block';
    emp.innerHTML=query?`No commands match "<b>${query}</b>".<br>Try a tag, symbol, or run <code>agent-adda doctor</code>`:'No commands in this category.';
    return;
  }
  emp.style.display='none';
  res.innerHTML=filtered.map((c,i)=>`
    <div class="card${i===activeIdx?' active':''}" onclick="selectCard(${i})" data-i="${i}">
      <div class="card-header">
        <span class="card-name">${c.id}</span>
        <div class="card-tags">${(c.tags||[]).slice(0,4).map(t=>`<span class="tag ${tagClass(t)}">${t}</span>`).join('')}</div>
      </div>
      <div class="card-desc">${c.description}</div>
      ${c.cli?`<div class="card-cli-row">
        <span class="card-cli">${c.cli}</span>
        <button class="copy-btn" onclick="event.stopPropagation();copyText('${c.cli.replace(/'/g,"\\'")}',this)" title="Copy CLI command">📋</button>
      </div>`:''}
    </div>`).join('');
  res._filtered=filtered;
}

function render(){
  const filtered=getFiltered();
  renderTabs(filtered);
  renderCards(filtered);
  updateFooter();
}

function updateFooter(){
  const total=CATALOGUE.length;
  document.getElementById('footer').textContent=
    `${total} commands indexed · Agent Adda · educational only — not investment advice`;
}

function setTab(cat){currentCat=cat;activeIdx=-1;render();}

function selectCard(i){
  const res=document.getElementById('results');
  const f=res._filtered;
  if(!f||!f[i]) return;
  copyText(f[i].cli||f[i].id);
  activeIdx=i;render();
}

document.getElementById('search').addEventListener('input',e=>{
  query=e.target.value;activeIdx=-1;render();
});
document.getElementById('search').addEventListener('keydown',e=>{
  const res=document.getElementById('results');
  const cards=res.querySelectorAll('.card');
  if(e.key==='ArrowDown'){e.preventDefault();activeIdx=Math.min(activeIdx+1,cards.length-1);}
  else if(e.key==='ArrowUp'){e.preventDefault();activeIdx=Math.max(activeIdx-1,0);}
  else if(e.key==='Enter'){e.preventDefault();if(activeIdx>=0)selectCard(activeIdx);else if(cards.length)selectCard(0);}
  else if(e.key==='Escape'){document.getElementById('search').value='';query='';activeIdx=-1;render();return;}
  render();
  const active=res.querySelector('.card.active');
  if(active) active.scrollIntoView({block:'nearest'});
});
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();
    const s=document.getElementById('search');s.focus();s.select();}
});

// Init
document.getElementById('search').focus();
render();
</script>
</body>
</html>"""


def generate_html(catalogue: list[dict]) -> str:
    return _LAUNCHER_HTML.replace(
        "__CATALOGUE_JSON__",
        json.dumps(catalogue, ensure_ascii=False, separators=(",", ":"))
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    catalogue = build_catalogue()

    # Write JSON
    json_path = OUT_DIR / "launcher_data.json"
    json_path.write_text(json.dumps(catalogue, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write HTML
    html = generate_html(catalogue)
    html_path = OUT_DIR / "launcher.html"
    html_path.write_text(html, encoding="utf-8")

    n_skills  = sum(1 for c in catalogue if c.get("category") == "skill")
    n_screen  = sum(1 for c in catalogue if c.get("category") == "screener")
    n_admin   = sum(1 for c in catalogue if c.get("category") == "admin")
    n_repl    = sum(1 for c in catalogue if c.get("category") == "repl")

    print(f"\n✅  Launcher saved → {html_path}")
    print(f"    {len(catalogue)} commands indexed "
          f"({n_skills} skills + {n_screen} screeners + {n_admin} admin + {n_repl} REPL commands)")


if __name__ == "__main__":
    main()
