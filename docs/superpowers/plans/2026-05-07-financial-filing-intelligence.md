# Financial Filing Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an auditable filing-analysis capability that starts with direct PDF/XBRL/iXBRL link ingestion and expands into NSE/BSE discovery, parsing, LLM analysis, and HTML/Markdown reports.

**Architecture:** Add a focused `financial_filing_agent.py` module with deterministic ingestion, storage, document-type detection, manifest writing, and later parser/report functions. LLM analysis will consume canonical facts and evidence maps only; raw filings remain auditable under `data/filings/`.

**Tech Stack:** Python standard library, `requests`, `unittest`, future optional PDF parser (`pymupdf` or `pdfplumber`) and XML/iXBRL parsing via `xml.etree`/`html.parser` before heavier dependencies.

---

### File Structure

- Create `financial_filing_agent.py`: direct-link ingestion, document detection, manifest persistence, future parser/report entry points.
- Create `tests/test_financial_filing_agent.py`: unit tests for detection, ingestion, idempotency, structured errors.
- Modify `docs/BACKLOG.md`: Branch F backlog and status updates.
- Later modify `terminal/tools.py`, `terminal/agent.py`, and `nse_agent.py` for terminal integration.

### Task 1: Filing Registry + Document Type Detection

**Files:**
- Create: `financial_filing_agent.py`
- Test: `tests/test_financial_filing_agent.py`

- [ ] **Step 1: Write failing tests**

```python
def test_detect_document_type_from_url_and_content_type():
    assert detect_document_type("https://example.com/result.pdf", "application/pdf", b"%PDF") == "pdf"
    assert detect_document_type("https://example.com/result.xml", "text/xml", b"<xbrli:xbrl") == "xbrl"
    assert detect_document_type("https://example.com/result.html", "text/html", b"<html ix:nonFraction") == "ixbrl"
    assert detect_document_type("https://example.com/result.zip", "application/zip", b"PK") == "zip"
    assert detect_document_type("https://example.com/result.bin", "application/octet-stream", b"abc") == "unknown"
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv/bin/python -m unittest tests.test_financial_filing_agent -v`

Expected: FAIL because `financial_filing_agent` or `detect_document_type` does not exist.

- [ ] **Step 3: Implement minimal detection**

Add:

```python
def detect_document_type(url: str, content_type: str = "", content: bytes = b"") -> str:
    ...
```

- [ ] **Step 4: Verify tests pass**

Run: `.venv/bin/python -m unittest tests.test_financial_filing_agent -v`

Expected: document type test passes.

### Task 2: Direct URL Ingestion Manifest

**Files:**
- Modify: `financial_filing_agent.py`
- Test: `tests/test_financial_filing_agent.py`

- [ ] **Step 1: Write failing tests**

```python
def test_ingest_filing_url_writes_raw_file_and_manifest(tmp_path):
    response = FakeResponse(content=b"%PDF sample", content_type="application/pdf")
    result = ingest_filing_url(
        "https://example.com/bslbmoutcome06052026.pdf",
        symbol="BLUESTARCO",
        period="FY26_Q4",
        root_dir=tmp_path,
        fetcher=lambda url: response,
    )
    assert result["status"] == "ok"
    assert result["document_type"] == "pdf"
    assert Path(result["local_path"]).exists()
    assert Path(result["manifest_path"]).exists()
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv/bin/python -m unittest tests.test_financial_filing_agent -v`

Expected: FAIL because `ingest_filing_url` does not exist.

- [ ] **Step 3: Implement ingestion**

Implement:
- safe symbol/period path normalization
- raw file write
- SHA-256
- `manifest.json`
- structured result dict

- [ ] **Step 4: Verify tests pass**

Run: `.venv/bin/python -m unittest tests.test_financial_filing_agent -v`

Expected: all ingestion tests pass.

### Task 3: Structured Error Handling + Idempotency

**Files:**
- Modify: `financial_filing_agent.py`
- Test: `tests/test_financial_filing_agent.py`

- [ ] **Step 1: Write failing tests**

```python
def test_ingest_filing_url_returns_structured_error_on_fetch_failure(tmp_path):
    def failing_fetcher(url):
        raise TimeoutError("network timeout")
    result = ingest_filing_url("https://example.com/result.pdf", root_dir=tmp_path, fetcher=failing_fetcher)
    assert result["status"] == "error"
    assert "network timeout" in result["error"]

def test_ingest_filing_url_is_idempotent_without_force(tmp_path):
    calls = []
    def fetcher(url):
        calls.append(url)
        return FakeResponse(content=b"%PDF sample", content_type="application/pdf")
    first = ingest_filing_url("https://example.com/result.pdf", root_dir=tmp_path, fetcher=fetcher)
    second = ingest_filing_url("https://example.com/result.pdf", root_dir=tmp_path, fetcher=fetcher)
    assert first["sha256"] == second["sha256"]
    assert len(calls) == 1
```

- [ ] **Step 2: Verify tests fail**

Run: `.venv/bin/python -m unittest tests.test_financial_filing_agent -v`

Expected: FAIL until idempotency and error handling are implemented.

- [ ] **Step 3: Implement structured error + idempotency**

Read existing `manifest.json` and return it when `force=False` and source URL matches.

- [ ] **Step 4: Verify tests pass**

Run: `.venv/bin/python -m unittest tests.test_financial_filing_agent -v`

Expected: all tests pass.

### Task 4: CLI Smoke Entry Point

**Files:**
- Modify: `financial_filing_agent.py`
- Test: `tests/test_financial_filing_agent.py`

- [ ] **Step 1: Write failing test**

```python
def test_build_arg_parser_accepts_analyze_url_command():
    parser = build_arg_parser()
    args = parser.parse_args(["ingest", "https://example.com/result.pdf", "--symbol", "BLUESTARCO", "--period", "FY26_Q4"])
    assert args.command == "ingest"
    assert args.symbol == "BLUESTARCO"
```

- [ ] **Step 2: Verify test fails**

Run: `.venv/bin/python -m unittest tests.test_financial_filing_agent -v`

Expected: FAIL because `build_arg_parser` does not exist.

- [ ] **Step 3: Implement parser and `main()`**

Add:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify smoke run**

Run:

```bash
.venv/bin/python financial_filing_agent.py ingest https://www.bluestarindia.com/media/404887/bslbmoutcome06052026.pdf --symbol BLUESTARCO --period FY26_Q4
```

Expected: prints JSON with `status: ok` or structured network error.

### Task 5: Future Parser/Report Backlog Checkpoint

**Files:**
- Modify: `docs/BACKLOG.md`
- Modify: `docs/superpowers/plans/2026-05-07-financial-filing-intelligence.md`

- [ ] **Step 1: Mark F0 and F1 as done in the backlog after direct-link ingestion passes tests and Blue Star smoke ingest succeeds**
- [ ] **Step 2: Leave F2-F9 ready/deferred as written**
- [ ] **Step 3: Run docs sanity checks**

Run:

```bash
rg -n "F0|F1|F2|F9|Financial Filing Intelligence" docs/BACKLOG.md docs/superpowers/plans/2026-05-07-financial-filing-intelligence.md
```

Expected: Branch F entries and implementation plan are discoverable.

### Verification

Run:

```bash
.venv/bin/python -m unittest tests.test_financial_filing_agent -v
.venv/bin/python -m py_compile financial_filing_agent.py tests/test_financial_filing_agent.py
```

Expected: all tests pass and compile succeeds.

### Commit

```bash
git add docs/BACKLOG.md docs/superpowers/specs/2026-05-07-financial-filing-intelligence-design.md docs/superpowers/plans/2026-05-07-financial-filing-intelligence.md financial_filing_agent.py tests/test_financial_filing_agent.py
git commit -m "feat: add financial filing ingestion foundation"
```

### Self-Review

- Spec coverage: F0 and F1 are covered by this plan; F2-F9 remain explicit follow-on backlog items.
- Placeholder scan: no incomplete marker placeholders are used.
- Scope check: first implementation slice is direct-link ingestion only; discovery, parsing, LLM analysis, and reports are separate tasks.
