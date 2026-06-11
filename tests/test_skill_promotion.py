from __future__ import annotations


class FakeSkillRepo:
    def __init__(self, cards):
        self.cards = {card["id"]: dict(card) for card in cards}
        self.upserts = []
        self.feedback = []

    def get_skill_card(self, skill_id, version=None):
        return dict(self.cards.get(skill_id) or {})

    def upsert_skill_card(self, card):
        self.upserts.append(dict(card))
        self.cards[card["id"]] = dict(card)
        return dict(card)

    def save_feedback(self, event):
        self.feedback.append(dict(event))
        return len(self.feedback)

    def list_skill_cards(self, status=None, domain=None):
        rows = list(self.cards.values())
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if domain:
            rows = [row for row in rows if row.get("domain") == domain]
        return rows


def _card(skill_id, status, **overrides):
    value = {
        "id": skill_id,
        "version": 1,
        "status": status,
        "domain": "market_analysis",
        "title": "Promotion Test Skill",
        "description": "A skill card used in promotion tests.",
        "input_patterns": ["promotion test"],
        "tags": ["promotion"],
        "evidence_required": {"tables": ["market.index_eod"]},
        "tool_plan_template": [],
        "output_contract": ["summary"],
        "validation_rules": ["required_tables_exist"],
        "synthesis_guidance": "Use validated evidence only.",
    }
    value.update(overrides)
    return value


def test_cannot_promote_generated_directly_to_production():
    from terminal.skills.promote import promote_skill

    repo = FakeSkillRepo([_card("generated_skill_v1", "generated")])

    result = promote_skill("generated_skill_v1", target_status="production", repository=repo)

    assert result.ok is False
    assert "cannot promote" in result.message
    assert repo.upserts == []
    assert repo.feedback
    assert repo.feedback[-1]["feedback_type"] == "skill_promotion"


def test_can_promote_review_pending_with_passed_review_to_validated():
    from terminal.skills.promote import promote_skill

    repo = FakeSkillRepo([
        _card("reviewed_skill_v1", "review_pending", review={"status": "pass", "findings": []})
    ])

    result = promote_skill("reviewed_skill_v1", target_status="validated", repository=repo)

    assert result.ok is True
    assert result.from_status == "review_pending"
    assert result.to_status == "validated"
    assert repo.cards["reviewed_skill_v1"]["status"] == "validated"
    assert repo.feedback[-1]["feedback_payload"]["to_status"] == "validated"


def test_promotion_requires_validation_pass():
    from terminal.skills.promote import promote_skill

    repo = FakeSkillRepo([
        _card(
            "failed_review_skill_v1",
            "review_pending",
            review={"status": "needs_heal", "findings": ["bad sql"]},
        )
    ])

    result = promote_skill("failed_review_skill_v1", target_status="validated", repository=repo)

    assert result.ok is False
    assert "validation pass" in result.message
    assert repo.upserts == []


def test_can_deprecate_bad_card():
    from terminal.skills.promote import deprecate_skill

    repo = FakeSkillRepo([_card("bad_skill_v1", "test_failed", validation_errors=["bad sql"])])

    result = deprecate_skill("bad_skill_v1", repository=repo, reason="unsafe sql")

    assert result.ok is True
    assert result.from_status == "test_failed"
    assert result.to_status == "deprecated"
    assert repo.cards["bad_skill_v1"]["status"] == "deprecated"
    assert repo.feedback[-1]["feedback_payload"]["reason"] == "unsafe sql"


def test_list_skills_uses_repository_filters():
    from terminal.skills.promote import list_skills

    repo = FakeSkillRepo([
        _card("a_v1", "validated", domain="market_analysis"),
        _card("b_v1", "review_pending", domain="screening"),
    ])

    rows = list_skills(repository=repo, status="review_pending")

    assert [row["id"] for row in rows] == ["b_v1"]


def test_agent_adda_parser_accepts_skill_commands():
    from agent_adda.cli import build_parser

    parser = build_parser()

    assert parser.parse_args(["skills", "list"]).skills_command == "list"
    promote_args = parser.parse_args(["skills", "promote", "reviewed_skill_v1", "--to", "validated"])
    assert promote_args.skills_command == "promote"
    assert promote_args.skill_id == "reviewed_skill_v1"
    assert promote_args.to_status == "validated"
    assert parser.parse_args(["skills", "deprecate", "bad_skill_v1"]).skills_command == "deprecate"
