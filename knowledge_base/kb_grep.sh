#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# kb_grep.sh — Shell search interface for the Agent Adda Knowledge Base
#
# Searches knowledge_base/index/ files with grep/awk so the KB is queryable
# without Python (in any shell, CI, Docker, or as a quick one-liner).
#
# Usage
# ──────
#   ./knowledge_base/kb_grep.sh "daily pipeline"        # text search (default)
#   ./knowledge_base/kb_grep.sh -c pipeline             # filter by category
#   ./knowledge_base/kb_grep.sh -t vcp,stage2           # filter by tags
#   ./knowledge_base/kb_grep.sh -i "chart"              # case-insensitive
#   ./knowledge_base/kb_grep.sh --cli "daily"           # search in CLI column only
#   ./knowledge_base/kb_grep.sh --list-cats             # list all categories
#   ./knowledge_base/kb_grep.sh --list-tags             # list all tags
#   ./knowledge_base/kb_grep.sh --fmt tsv "stage2"      # raw TSV output
#   ./knowledge_base/kb_grep.sh --fmt jsonl "chart"     # JSONL output (pipe to jq)
#
# Direct grep/awk examples (no script needed)
# ────────────────────────────────────────────
#   grep -i "daily pipeline" knowledge_base/index/kb_flat.txt
#   grep -A8 "^id: daily_refresh$" knowledge_base/index/kb_flat.txt
#   awk -F'\t' '$2=="pipeline"' knowledge_base/index/kb_index.tsv
#   awk -F'\t' 'NR==1 || $2=="screener"' knowledge_base/index/kb_index.tsv | cut -f1,3,4
#   grep "vcp" knowledge_base/index/kb_index.tsv | cut -f1,4
#   cat knowledge_base/index/kb_index.jsonl | jq -r 'select(.tags[]? == "vcp") | .id + " | " + .cli'
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INDEX_DIR="$SCRIPT_DIR/index"
FLAT="$INDEX_DIR/kb_flat.txt"
TSV="$INDEX_DIR/kb_index.tsv"
JSONL="$INDEX_DIR/kb_index.jsonl"

# ── color helpers ──────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'
  DIM='\033[2m'; BOLD='\033[1m'; RESET='\033[0m'
else
  GREEN=''; YELLOW=''; CYAN=''; DIM=''; BOLD=''; RESET=''
fi

# ── check index exists ─────────────────────────────────────────────────────────
_check_index() {
  if [[ ! -f "$FLAT" ]]; then
    echo "Index not found. Rebuilding..." >&2
    if command -v python3 &>/dev/null; then
      PROJ_DIR="$(dirname "$SCRIPT_DIR")"
      VENV="$PROJ_DIR/.venv/bin/python"
      if [[ -f "$VENV" ]]; then
        "$VENV" -c "from knowledge_base.skills_registry import get_registry, export_flat_indexes; export_flat_indexes(get_registry())" 2>&1
      else
        python3 -c "
import sys; sys.path.insert(0, '$PROJ_DIR')
from knowledge_base.skills_registry import get_registry, export_flat_indexes
export_flat_indexes(get_registry())
" 2>&1
      fi
    else
      echo "ERROR: flat index not found and python3 not available." >&2
      echo "Run: python -m knowledge_base index-skills" >&2
      exit 1
    fi
  fi
}

# ── search functions ───────────────────────────────────────────────────────────

_search_flat() {
  local query="$1" icase="${2:-}"
  local gflags="-l"
  [[ -n "$icase" ]] && gflags="-il"
  # Print full block for each match
  grep $gflags "$query" "$FLAT" >/dev/null 2>&1 || { echo "No results for: $query"; return 1; }
  echo -e "${BOLD}KB results for: $query${RESET}\n"
  local in_match=0 count=0
  while IFS= read -r line; do
    if echo "$line" | grep -q "${icase:+-i}" "$query" 2>/dev/null || [[ $in_match -eq 1 ]]; then
      # find the block start (lines with id:)
      :
    fi
  done < "$FLAT"
  # Simpler: grep with context
  grep -A8 "${icase:+-i}" "$query" "$FLAT" | head -80
}

_search_tsv() {
  local query="$1" icase="${2:-}"
  local gflags=""
  [[ -n "$icase" ]] && gflags="-i"
  local header
  header=$(head -1 "$TSV")
  local results
  results=$(tail -n +2 "$TSV" | grep $gflags "$query")
  if [[ -z "$results" ]]; then echo "No results for: $query"; return 1; fi
  local count
  count=$(echo "$results" | wc -l | tr -d ' ')
  echo -e "${BOLD}${count} results for '${query}'${RESET}\n"
  echo "$results" | awk -F'\t' '{
    printf "'"${GREEN}"'[%s]'"${RESET}"' '"${CYAN}"'%s'"${RESET}"'\n", $2, $1
    printf "  '"${YELLOW}"'%s'"${RESET}"'\n", $3
    if ($4 != "") printf "  CLI: '"${DIM}"'%s'"${RESET}"'\n", $4
    if ($5 != "") printf "  '"${DIM}"'%s'"${RESET}"'\n\n", substr($5, 1, 100)
    else printf "\n"
  }'
}

_filter_category() {
  local cat="$1"
  local results
  results=$(awk -F'\t' -v c="$cat" 'NR>1 && $2==c' "$TSV")
  if [[ -z "$results" ]]; then echo "No entries with category: $cat"; return 1; fi
  local count
  count=$(echo "$results" | wc -l | tr -d ' ')
  echo -e "${BOLD}${count} entries in category '${cat}'${RESET}\n"
  echo "$results" | awk -F'\t' '{
    printf "'"${GREEN}"'%s'"${RESET}"'  '"${DIM}"'%s'"${RESET}"'\n", $1, $3
    if ($4 != "") printf "  '"${CYAN}"'%s'"${RESET}"'\n", $4
    printf "\n"
  }'
}

_filter_tags() {
  local tags="$1"  # comma-separated
  IFS=',' read -ra TAG_LIST <<< "$tags"
  local results=""
  for tag in "${TAG_LIST[@]}"; do
    tag=$(echo "$tag" | tr -d ' ')
    local matches
    matches=$(awk -F'\t' -v t="$tag" 'NR>1 && $6 ~ t' "$TSV") || true
    if [[ -n "$matches" ]]; then
      results=$(printf '%s\n%s' "$results" "$matches")
    fi
  done
  results=$(echo "$results" | sort -u | grep .)
  if [[ -z "$results" ]]; then echo "No entries with tags: $tags"; return 1; fi
  local count
  count=$(echo "$results" | wc -l | tr -d ' ')
  echo -e "${BOLD}${count} entries with tags '${tags}'${RESET}\n"
  echo "$results" | awk -F'\t' '{
    printf "'"${GREEN}"'[%s]'"${RESET}"' %s  '"${DIM}"'tags: %s'"${RESET}"'\n", $2, $1, $6
    if ($4 != "") printf "  '"${CYAN}"'%s'"${RESET}"'\n", $4
    printf "\n"
  }'
}

_search_cli() {
  local query="$1"
  local results
  results=$(awk -F'\t' -v q="$query" 'NR>1 && tolower($4) ~ tolower(q)' "$TSV")
  if [[ -z "$results" ]]; then echo "No CLI entries matching: $query"; return 1; fi
  echo "$results" | awk -F'\t' '{printf "'"${GREEN}"'%s'"${RESET}"'\n  '"${CYAN}"'%s'"${RESET}"'\n\n", $1, $4}'
}

_list_categories() {
  echo -e "${BOLD}Categories in the KB:${RESET}\n"
  tail -n +2 "$TSV" | awk -F'\t' '{print $2}' | sort | uniq -c | sort -rn | \
    awk '{printf "  '"${GREEN}"'%s'"${RESET}"'  (%d entries)\n", $2, $1}'
}

_list_tags() {
  echo -e "${BOLD}Top tags in the KB:${RESET}\n"
  tail -n +2 "$TSV" | awk -F'\t' '{n=split($6,a," "); for(i=1;i<=n;i++) print a[i]}' | \
    sort | uniq -c | sort -rn | head -40 | \
    awk '{printf "  '"${CYAN}"'%-20s'"${RESET}"' %d\n", $2, $1}'
}

_fmt_tsv() {
  local query="$1"
  echo "id	category	title	cli	description	tags"
  tail -n +2 "$TSV" | grep -i "$query"
}

_fmt_jsonl() {
  local query="$1"
  grep -i "$query" "$JSONL"
}

# ── main ───────────────────────────────────────────────────────────────────────

_check_index

# parse args
QUERY=""
CATEGORY=""
TAGS=""
ICASE=""
CLI_SEARCH=""
FMT="pretty"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--cat|--category) CATEGORY="$2"; shift 2 ;;
    -t|--tags)           TAGS="$2"; shift 2 ;;
    -i)                  ICASE="-i"; shift ;;
    --cli)               CLI_SEARCH="$2"; shift 2 ;;
    --list-cats)         _list_categories; exit 0 ;;
    --list-tags)         _list_tags; exit 0 ;;
    --fmt)               FMT="$2"; shift 2 ;;
    -h|--help)
      sed -n '/^# Usage/,/^# ─/p' "$0" | sed 's/^# //; s/^#//'
      exit 0 ;;
    -*) echo "Unknown flag: $1"; exit 1 ;;
    *)  QUERY="$1"; shift ;;
  esac
done

if [[ -n "$CLI_SEARCH" ]]; then
  _search_cli "$CLI_SEARCH"
elif [[ -n "$CATEGORY" ]]; then
  _filter_category "$CATEGORY"
elif [[ -n "$TAGS" ]]; then
  _filter_tags "$TAGS"
elif [[ -n "$QUERY" ]]; then
  if [[ "$FMT" == "tsv" ]]; then
    _fmt_tsv "$QUERY"
  elif [[ "$FMT" == "jsonl" ]]; then
    _fmt_jsonl "$QUERY"
  else
    _search_tsv "$QUERY" "$ICASE"
  fi
else
  echo "Usage: $0 [options] [query]"
  echo "       $0 --help"
  echo ""
  _list_categories
fi
