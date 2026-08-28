#!/usr/bin/env bash
# =============================================================================
# Multi-step agentic research workflow: Auto Components (and reusable for others)
# =============================================================================
# Prerequisites: ollama with granite4 (or set OLLAMA_MODEL); web search done
# externally or via prior step. This script runs local steps and documents flow.
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
OLLAMA_MODEL="${OLLAMA_MODEL:-granite4:latest}"

echo "=== Research workflow: working-sector ==="
echo "Step 0: Hypothesis and definition (Phase 0) – already in hypothesis_auto_components.md"
echo "Step 1: Literature notes (Phase 1) – already in literature_notes_auto_components.md"
echo "Step 2: Sector narrative via Ollama Granite (Phase 1) – generate and save"
echo "Step 3: Universe CSV (Phase 1) – already in auto_components_universe.csv"
echo "Step 4: Optional – run R pipeline for data + screens (Phase 2–3)"
echo ""

# --- Step 2: Regenerate sector narrative using Ollama ---
echo ">>> Step 2: Calling Ollama ($OLLAMA_MODEL) for sector narrative..."
if [ -f prompt_for_narrative.txt ]; then
  PAYLOAD=$(python3 -c "
import json
with open('prompt_for_narrative.txt') as f:
    p = f.read()
print(json.dumps({'model': '$OLLAMA_MODEL', 'prompt': p, 'stream': False}))
")
  RESPONSE=$(curl -s http://localhost:11434/api/generate -d "$PAYLOAD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('response',''))")
else
  RESPONSE=""
  echo "Prompt file prompt_for_narrative.txt not found; skip narrative generation."
fi
if [ -n "$RESPONSE" ]; then
  {
    echo "# Sector Narrative: Auto Components (India)"
    echo ""
    echo "**Generated:** $(date +%Y-%m-%d) (Ollama $OLLAMA_MODEL)"
    echo ""
    echo "---"
    echo ""
    echo "$RESPONSE"
  } > sector_narrative_auto_components.md
  echo "Saved to sector_narrative_auto_components.md"
else
  echo "Warning: No response from Ollama; skip if narrative already exists."
fi

echo ""
echo ">>> Step 3: Universe file – check auto_components_universe.csv"
wc -l auto_components_universe.csv

echo ""
echo ">>> Step 4: Next steps (manual or via R)"
echo "  - Run NSE data load filtered to universe (see auto_components_deep_analysis_plan.md)"
echo "  - Add RS vs Nifty Auto (and Nifty 500); run technical + fundamental pipeline"
echo "  - Merge and apply screens; optional backtest (Phase 4)"
echo "  - Write final sector note (Phase 5) using sector_narrative_auto_components.md and literature_notes_auto_components.md"
echo ""
echo "=== Workflow step (script) complete ==="
