# Agent Adda Skill Store

This folder holds the first-generation skill-store generation tooling.

The generator creates candidate skill cards from curated seed briefs. Generated
cards are intentionally marked `generated`; they are not runtime-eligible until
they pass schema validation, SQL/tool safety checks, review, and promotion.

Generation is schema-aware. The prompt includes an approved Agent Adda
PostgreSQL data model: table/column catalog, column-level descriptions and
examples, primary keys, latest-date columns, common filters, canonical join
rules, and global PostgreSQL usage rules. Generated evidence is normalized to
`evidence_required.tables`, and SQL templates are audited against the catalog
before cards are written as clean generated candidates.

Run a deterministic local generation:

```bash
.venv/bin/python -m skill_store.cli --dry-run --count 4
```

Run an OpenAI-backed generation using `.env`:

```bash
.venv/bin/python -m skill_store.cli --count 4
```

Run a schema-aware generation into a separate review folder:

```bash
.venv/bin/python -m skill_store.cli --count 4 --output-dir skill_store/generated_schema_aware_final
```

Run local review/heal after generation. Passing cards become `review_pending`;
they are still not runtime-eligible:

```bash
.venv/bin/python -m skill_store.cli --dry-run --count 4 --review-heal
```

Run a large GPT-4o corpus generation in parallel batches:

```bash
.venv/bin/python -m skill_store.cli \
  --target-count 1000 \
  --batch-size 15 \
  --parallelism 15 \
  --model gpt-4o \
  --review-heal \
  --output-dir skill_store/generated_1000_gpt4o
```

`gpt-40` is accepted as an alias for `gpt-4o`.

Configuration:

- `OPENAI_API_KEY`: loaded from `.env` when absent from the process.
- `SKILL_STORE_MODEL`: optional model override for skill generation.

The default generation model is `gpt-4o`. Informal spellings such as
`gpt 5.5` and `gpt_5_5` are still normalized to the API model id `gpt-5.5`
when explicitly requested.

The skill-store generator does not use the repo-wide `OPENAI_MODEL` by default,
so older Agent Adda runtime defaults do not silently downgrade the generated
scenario corpus.

Generated cards that reference unknown tables or columns are marked
`test_failed` with `validation_errors`; they should not be promoted.
Common generated SQL mistakes such as SQLite `date('now', ...)`, numeric
`stage = 2`, or treating `stage = 'VCP'` as a valid stage are also rejected.

## Reviewer / Healer Pipeline

The V2 pipeline supports SQL plus quarantined Python evidence tools:

- SQL is preferred for simple read-only evidence pulls.
- Python tools are allowed when SQL would become too complex, but only as
  generated review artifacts.
- Python tools must define `run(context)`, declare inputs/outputs, and remain
  read-only.
- Static policy blocks network, subprocess, filesystem writes, DB writes,
  broker/order automation, unsafe imports, and dangerous builtins.
- The review/heal pipeline runs static audits, optional Python dry-run tests
  with a timeout, reviewer decisions, and capped healing attempts before
  marking a card ready for manual approval.

Promotion remains gated:

- `generated`: produced and quarantined.
- `test_failed`: static audit, reviewer, runner, or healing failed.
- `review_pending`: static audit, reviewer, and runner passed; awaits explicit
  approval.
- `validated`: explicitly approved for runtime use.
- `production`: deployed runtime skill.
