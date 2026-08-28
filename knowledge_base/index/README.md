# KB Index Files — grep / awk / jq / ripgrep

Three flat index files for shell-based search. No Python required after the first `export`.

## Files

| File | Format | Best for |
|------|--------|----------|
| `kb_flat.txt` | Human-readable blocks | `grep`, `ripgrep (rg)`, text editors |
| `kb_index.tsv` | Tab-separated columns | `awk`, `cut`, spreadsheet import |
| `kb_index.jsonl` | One JSON per line | `jq`, `python`, streaming parsers |

### TSV columns
`id | category | title | cli | description | tags | source`

---

## grep / ripgrep examples

```bash
# Text search in flat blocks
grep -i "daily pipeline" knowledge_base/index/kb_flat.txt
grep -A8 "^id: daily_refresh$" knowledge_base/index/kb_flat.txt

# ripgrep (faster)
rg -i "vcp breakout" knowledge_base/index/kb_flat.txt
rg -l "sector rotation" knowledge_base/index/  # list matching files
```

## awk examples

```bash
# Filter by category
awk -F'\t' '$2=="pipeline"' knowledge_base/index/kb_index.tsv

# Show id + CLI for pipeline entries
awk -F'\t' 'NR==1 || $2=="pipeline" {print $1"\t"$4}' knowledge_base/index/kb_index.tsv

# Filter by category and show formatted
awk -F'\t' '$2=="screener" {printf "%s\n  %s\n\n", $1, $4}' knowledge_base/index/kb_index.tsv | head -30

# Count entries per category
awk -F'\t' 'NR>1 {cnt[$2]++} END {for(c in cnt) print cnt[c], c}' knowledge_base/index/kb_index.tsv | sort -rn

# Find entries with "chart" in description
awk -F'\t' 'tolower($5) ~ /chart/ {print $1, "|", $4}' knowledge_base/index/kb_index.tsv

# Find all pipeline CLIs
awk -F'\t' '$2=="pipeline" && $4!="" {print $4}' knowledge_base/index/kb_index.tsv
```

## jq / python -m json.tool examples

```bash
# Filter by tag
cat knowledge_base/index/kb_index.jsonl | \
  python3 -c "import sys,json; [print(d['id'],'|',d['cli'][:70]) for d in map(json.loads,sys.stdin) if 'vcp' in d.get('tags',[])]"

# Find entries with "fundamental" in description
grep "fundamental" knowledge_base/index/kb_index.jsonl | \
  python3 -c "import sys,json; [print(d['id'],'|',d['description'][:80]) for d in map(json.loads,sys.stdin)]"

# With jq (if installed)
cat knowledge_base/index/kb_index.jsonl | jq -r 'select(.category == "workflow") | .id + " | " + .cli'
cat knowledge_base/index/kb_index.jsonl | jq -r 'select(.tags[] | contains("vcp")) | .id'
cat knowledge_base/index/kb_index.jsonl | jq -r 'select(.category == "pipeline") | [.id, .cli] | @tsv'
```

## Shell script wrapper

```bash
# Search with nice output
./knowledge_base/kb_grep.sh "daily pipeline"

# Filter by category
./knowledge_base/kb_grep.sh -c pipeline
./knowledge_base/kb_grep.sh -c screener

# Filter by tag (comma-separated)
./knowledge_base/kb_grep.sh -t vcp,stage2

# Search CLI column only
./knowledge_base/kb_grep.sh --cli "sector_rotation_tracker"

# Raw output for piping
./knowledge_base/kb_grep.sh --fmt tsv "chart" | cut -f1,4
./knowledge_base/kb_grep.sh --fmt jsonl "vcp" | python3 -c "import sys,json; [print(d['id']) for d in map(json.loads,sys.stdin)]"

# List all categories / tags
./knowledge_base/kb_grep.sh --list-cats
./knowledge_base/kb_grep.sh --list-tags
```

## Python CLI

```bash
# BM25 ranked search (fastest, most relevant)
python -m knowledge_base query "chart RELIANCE"

# JSON output
python -m knowledge_base query "stage 2 screener" --format json --top 8

# Rebuild index after adding new skills/workflows
python -m knowledge_base export

# Token usage
python -m knowledge_base tokens
```

## Rebuild

Index files are pre-built and committed. To rebuild after adding entries to
`knowledge_base/entries/workflows.yaml` or new skill YAMLs:

```bash
python -m knowledge_base export
# or
python -c "from knowledge_base.skills_registry import get_registry, export_flat_indexes; export_flat_indexes(get_registry())"
```
