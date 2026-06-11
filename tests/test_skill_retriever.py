from __future__ import annotations


class FakeEmbeddingProvider:
    def __init__(self, *, fail: bool = False):
        self.fail = fail

    def embed_texts(self, texts, model=None):
        if self.fail:
            raise RuntimeError("embedding unavailable")

        class Result:
            vectors = [[0.1] * 384]

        Result.model = model or "fake-sentence-transformer"
        return Result()


class FakeRetrieverRepo:
    def __init__(self):
        self.logged_events = []
        self.vector_calls = []
        self.cards = [
            {
                "id": "generated_v1",
                "version": 1,
                "status": "generated",
                "domain": "market_analysis",
                "title": "Generated",
                "tags": ["market"],
                "input_patterns": ["market review"],
            },
            {
                "id": "stage2_breakout_v1",
                "version": 1,
                "status": "validated",
                "domain": "screening",
                "title": "Stage 2 Breakout",
                "tags": ["stage 2", "breakout", "swing"],
                "input_patterns": ["show stage 2 breakout stocks"],
                "card_payload": {
                    "id": "stage2_breakout_v1",
                    "version": 1,
                    "status": "validated",
                    "domain": "screening",
                    "title": "Stage 2 Breakout",
                    "description": "Find stage 2 breakout stocks.",
                    "input_patterns": ["show stage 2 breakout stocks"],
                    "tags": ["stage 2", "breakout", "swing"],
                    "evidence_required": {"tables": ["scores.stage_snapshots"]},
                    "sql_templates": [
                        {
                            "name": "stage2",
                            "sql": "SELECT symbol FROM scores.stage_snapshots LIMIT 5",
                            "safety_status": "passed",
                        }
                    ],
                    "output_contract": ["candidates"],
                    "validation_rules": ["sql_is_read_only"],
                },
            },
            {
                "id": "market_rotation_v1",
                "version": 1,
                "status": "validated",
                "domain": "market_analysis",
                "title": "Market Rotation",
                "tags": ["market_regime", "sector_rotation", "last_3_months"],
                "input_patterns": ["last 3 months market analysis", "market regime and stage 2 leadership over 3 months"],
            },
            {
                "id": "quarterly_results_v1",
                "version": 1,
                "status": "production",
                "domain": "fundamentals",
                "title": "Quarterly Results",
                "tags": ["quarterly results", "eps", "revenue"],
                "input_patterns": ["latest quarterly results analysis"],
            },
            {
                "id": "test_failed_v1",
                "version": 1,
                "status": "test_failed",
                "domain": "screening",
                "title": "Bad",
                "tags": ["breakout"],
                "input_patterns": ["breakout"],
            },
        ]
        self.vector_rows = [
            {
                "skill_id": "stage2_breakout_v1",
                "version": 1,
                "status": "validated",
                "domain": "screening",
                "title": "Stage 2 Breakout",
                "tags": ["stage 2", "breakout", "swing"],
                "input_patterns": ["show stage 2 breakout stocks"],
                "vector_score": 0.82,
            },
            {
                "skill_id": "generated_v1",
                "version": 1,
                "status": "generated",
                "domain": "market_analysis",
                "title": "Generated",
                "tags": ["market"],
                "input_patterns": ["market review"],
                "vector_score": 0.99,
            },
        ]

    def list_runtime_eligible(self, domain=None):
        rows = [row for row in self.cards if row["status"] in {"validated", "production"}]
        if domain:
            rows = [row for row in rows if row["domain"] == domain]
        return rows

    def search_vector_candidates(self, vector, model, *, limit=30, statuses=("validated", "production")):
        self.vector_calls.append((vector, model, limit, statuses))
        return self.vector_rows[:limit]

    def log_retrieval(self, event):
        self.logged_events.append(event)
        return 101


def test_retrieve_skill_candidates_merges_vector_and_tag_candidates_and_logs_event():
    from terminal.skills.retriever import retrieve_skill_candidates

    repo = FakeRetrieverRepo()

    candidates = retrieve_skill_candidates(
        "Show Stage 2 breakout swing stocks",
        repo=repo,
        embedding_provider=FakeEmbeddingProvider(),
        top_n=5,
    )

    assert [candidate.skill_id for candidate in candidates] == ["stage2_breakout_v1"]
    assert candidates[0].vector_score == 0.82
    assert candidates[0].tag_score > 0
    assert candidates[0].matched_tags == ("breakout", "stage 2", "swing")
    assert candidates[0].metadata["output_contract"] == ["candidates"]
    assert candidates[0].metadata["evidence_required"] == {"tables": ["scores.stage_snapshots"]}
    assert candidates[0].metadata["sql_templates"][0]["name"] == "stage2"
    assert repo.vector_calls
    assert len(repo.logged_events) == 1
    assert repo.logged_events[0]["candidates"][0]["skill_id"] == "stage2_breakout_v1"
    assert repo.logged_events[0]["selected_skill_id"] is None


def test_retrieve_skill_candidates_excludes_non_runtime_status_cards():
    from terminal.skills.retriever import retrieve_skill_candidates

    repo = FakeRetrieverRepo()

    candidates = retrieve_skill_candidates(
        "market breakout",
        repo=repo,
        embedding_provider=FakeEmbeddingProvider(),
        top_n=10,
    )

    ids = {candidate.skill_id for candidate in candidates}
    assert "generated_v1" not in ids
    assert "test_failed_v1" not in ids


def test_retrieve_skill_candidates_uses_tag_only_fallback_when_embeddings_unavailable():
    from terminal.skills.retriever import retrieve_skill_candidates

    repo = FakeRetrieverRepo()

    candidates = retrieve_skill_candidates(
        "latest quarterly results EPS revenue",
        repo=repo,
        embedding_provider=FakeEmbeddingProvider(fail=True),
        top_n=3,
    )

    assert [candidate.skill_id for candidate in candidates] == ["quarterly_results_v1"]
    assert candidates[0].vector_score is None
    assert candidates[0].tag_score > 0
    assert repo.logged_events[0]["metadata"]["vector_error"].startswith("RuntimeError")


def test_retrieve_skill_candidates_ignores_generic_analysis_overlap():
    from terminal.skills.retriever import retrieve_skill_candidates

    repo = FakeRetrieverRepo()

    candidates = retrieve_skill_candidates(
        "latest quarterly results analysis for V2RETAIL",
        repo=repo,
        top_n=5,
    )

    assert [candidate.skill_id for candidate in candidates] == ["quarterly_results_v1"]


def test_retrieve_skill_candidates_supports_domain_filter_for_tag_path():
    from terminal.skills.retriever import retrieve_skill_candidates

    repo = FakeRetrieverRepo()

    candidates = retrieve_skill_candidates(
        "quarterly results",
        repo=repo,
        domain="screening",
        top_n=3,
    )

    assert candidates == []
    assert repo.vector_calls == []


def test_retrieve_skill_candidates_applies_domain_filter_to_vector_path():
    from terminal.skills.retriever import retrieve_skill_candidates

    repo = FakeRetrieverRepo()

    candidates = retrieve_skill_candidates(
        "stage 2 breakout",
        repo=repo,
        embedding_provider=FakeEmbeddingProvider(),
        domain="fundamentals",
        top_n=3,
    )

    assert candidates == []
    assert repo.vector_calls


def test_retrieve_skill_candidates_fails_open_when_runtime_list_errors():
    from terminal.skills.retriever import retrieve_skill_candidates

    class BrokenRepo:
        def list_runtime_eligible(self, domain=None):
            raise RuntimeError("db unavailable")

        def log_retrieval(self, event):
            self.event = event
            return 1

    repo = BrokenRepo()

    candidates = retrieve_skill_candidates("market analysis", repo=repo, top_n=3)

    assert candidates == []
    assert "tag_list_error=RuntimeError" in repo.event["metadata"]["vector_error"]
