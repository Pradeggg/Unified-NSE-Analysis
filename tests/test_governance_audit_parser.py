from terminal.governance.audit_parser import (
    classify_auditor,
    extract_auditor_section,
    extract_text_from_pdf,
    parse_audit_text,
)


def test_extract_auditor_section_accepts_marker_at_character_zero():
    text = (
        "Independent Auditor's Report\n"
        "To the Members of Example Limited\n"
        "In our opinion, the financial statements give a true and fair view.\n"
        "Balance Sheet\n"
        "Assets and liabilities"
    )

    section = extract_auditor_section(text)

    assert section is not None
    assert section.startswith("Independent Auditor's Report")
    assert "Balance Sheet" not in section


def test_parse_audit_text_detects_big4_clean_opinion_and_eom_absence():
    text = (
        "Independent Auditor's Report\n"
        "For Deloitte Haskins & Sells LLP\n"
        "Chartered Accountants\n"
        "In our opinion the financial statements give a true and fair view.\n"
        "Key Audit Matter 1 Revenue recognition\n"
        "Key Audit Matter 2 Tax matters\n"
        "Balance Sheet\n"
    )

    signal = parse_audit_text(text, revenue_cr=1000)

    assert signal.auditor_name == "Deloitte Haskins & Sells LLP"
    assert signal.auditor_tier == "Big4"
    assert signal.opinion_type == "Clean"
    assert signal.emphasis_of_matter is False
    assert signal.key_audit_matters_count == 2


def test_parse_audit_text_detects_qualified_opinion_and_related_party_pct():
    text = (
        "Independent Auditor's Report\n"
        "For Gupta & Associates\n"
        "Qualified opinion\n"
        "Except for the matters described below, the statements are prepared.\n"
        "Emphasis of Matter\n"
        "Related party transactions aggregated to Rs. 250 crore.\n"
        "Statement of Profit and Loss\n"
    )

    signal = parse_audit_text(text, revenue_cr=1000)

    assert signal.auditor_tier == "Unknown"
    assert signal.opinion_type == "Qualified"
    assert signal.emphasis_of_matter is True
    assert signal.related_party_txn_pct_revenue == 25.0


def test_classify_auditor_identifies_mid_tier():
    assert classify_auditor("Lodha & Co LLP") == "MidTier"


def test_extract_text_from_missing_pdf_returns_empty_string(tmp_path):
    assert extract_text_from_pdf(tmp_path / "missing.pdf") == ""


def test_classify_auditor_handles_punctuated_initials():
    assert classify_auditor("S.R. Batliboi & Co LLP") == "Big4"
    assert classify_auditor("B.S.R. & Co. LLP") == "Big4"
    assert classify_auditor("S.P. Jain & Associates") == "MidTier"


def test_parse_audit_text_keeps_realistic_section_when_balance_sheet_is_in_sentence():
    text = (
        "Independent Auditor's Report\n"
        "In our opinion the financial statements comprise the Balance Sheet as at March 31, 2026.\n"
        "Key Audit Matter 1 Revenue recognition\n"
        "Related party transactions aggregated to Rs. 250 crore.\n"
        "For and on behalf of the Board\n"
        "For S.R. Batliboi & Co LLP\n"
        "Balance Sheet\n"
    )

    signal = parse_audit_text(text, revenue_cr=1000)

    assert signal.auditor_name == "S.R. Batliboi & Co LLP"
    assert signal.auditor_tier == "Big4"
    assert signal.key_audit_matters_count == 1
    assert signal.related_party_txn_pct_revenue == 25.0


def test_parse_audit_text_does_not_treat_note_number_as_rpt_amount():
    text = (
        "Independent Auditor's Report\n"
        "For Gupta & Associates\n"
        "Related party disclosures are in Note 43 to the financial statements.\n"
        "Statement of Profit and Loss\n"
    )

    signal = parse_audit_text(text, revenue_cr=1000)

    assert signal.related_party_txn_pct_revenue == 0.0


def test_parse_audit_text_uses_declared_lakh_unit_for_rpt_amount():
    text = (
        "Independent Auditor's Report\n"
        "Rs. in lakhs\n"
        "For Gupta & Associates\n"
        "Related party transactions aggregated to 2500.\n"
        "Statement of Profit and Loss\n"
    )

    signal = parse_audit_text(text, revenue_cr=1000)

    assert signal.related_party_txn_pct_revenue == 2.5


def test_extract_auditor_section_skips_table_of_contents_page_lines():
    text = (
        "Contents\n"
        "Independent Auditor's Report 124\n"
        "Balance Sheet 136\n"
        "Independent Auditor's Report\n"
        "For B.S.R. & Co. LLP\n"
        "In our opinion the financial statements give a true and fair view.\n"
        "Balance Sheet\n"
    )

    section = extract_auditor_section(text)
    signal = parse_audit_text(text, revenue_cr=1000)

    assert section is not None
    assert section.startswith("Independent Auditor's Report\nFor B.S.R.")
    assert signal.auditor_name == "B.S.R. & Co. LLP"
    assert signal.auditor_tier == "Big4"
    assert signal.opinion_type == "Clean"


def test_parse_audit_text_ignores_generic_independent_auditor_prose_before_heading():
    text = (
        "The audit committee meets the independent auditors periodically.\n"
        "The financial statements are prepared on historical cost basis except for financial instruments.\n"
        "Independent Auditor's Report\n"
        "To the Members of Example Limited\n"
        "For Deloitte Haskins & Sells LLP\n"
        "In our opinion the financial statements give a true and fair view.\n"
        "Balance Sheet\n"
    )

    section = extract_auditor_section(text)
    signal = parse_audit_text(text)

    assert section is not None
    assert section.startswith("Independent Auditor's Report")
    assert signal.auditor_name == "Deloitte Haskins & Sells LLP"
    assert signal.opinion_type == "Clean"


def test_parse_audit_text_skips_board_report_auditors_reports_summary():
    text = (
        "Auditors' reports\n"
        "The Auditors' Report for fiscal 2026 does not contain any qualification.\n"
        "The financial statements are prepared on historical cost basis except for financial instruments.\n"
        "Independent Auditor's Report\n"
        "To the Members of Example Limited\n"
        "For Deloitte Haskins & Sells LLP\n"
        "In our opinion the financial statements give a true and fair view.\n"
        "Balance Sheet\n"
    )

    section = extract_auditor_section(text)
    signal = parse_audit_text(text)

    assert section is not None
    assert section.startswith("Independent Auditor's Report")
    assert signal.opinion_type == "Clean"
