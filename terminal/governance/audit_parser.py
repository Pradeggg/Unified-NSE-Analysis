from __future__ import annotations

import re
from pathlib import Path

from terminal.governance.models import AuditSignal


BIG4_NAMES = (
    "Deloitte",
    "Haskins & Sells",
    "Price Waterhouse",
    "PwC",
    "Ernst & Young",
    "Walker Chandiok",
    "S R Batliboi",
    "KPMG",
    "B S R",
)

MID_TIER_NAMES = (
    "Lodha & Co",
    "Chaturvedi & Shah",
    "Nangia",
    "PKF",
    "S P Jain",
)

_AUDITOR_START_MARKERS = (
    "independent auditor",
    "auditor's report",
    "to the members",
)
_AUDITOR_STOP_MARKERS = (
    "balance sheet",
    "statement of profit and loss",
    "cash flow statement",
)


def _matchable(text: str) -> str:
    lowered = str(text or "").lower()
    compact_initials = re.sub(r"\b([a-z])\s*\.\s*(?=[a-z]\s*\.?\b)", r"\1 ", lowered)
    return re.sub(r"[^a-z0-9&]+", " ", compact_initials)


def classify_auditor(name: str) -> str:
    text = _matchable(name)
    if any(_matchable(item) in text for item in BIG4_NAMES):
        return "Big4"
    if any(_matchable(item) in text for item in MID_TIER_NAMES):
        return "MidTier"
    return "Unknown"


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    path = Path(pdf_path)
    if not path.exists():
        return ""
    try:
        from pdfminer.high_level import extract_text
    except Exception:
        return ""
    try:
        return extract_text(str(path)) or ""
    except Exception:
        return ""


def extract_auditor_section(text: str) -> str | None:
    if not text:
        return None

    start = _auditor_section_start(text)
    if start is None:
        return None

    stop = len(text)
    offset = 0
    for line in text.splitlines(keepends=True):
        if offset > start and _is_stop_heading(line):
            stop = offset
            break
        offset += len(line)

    section = text[start:stop].strip()
    return section or None


def _auditor_section_start(text: str) -> int | None:
    fallback = None
    offset = 0
    for line in text.splitlines(keepends=True):
        lowered = line.lower()
        if any(marker in lowered for marker in _AUDITOR_START_MARKERS):
            if not _is_toc_line(line):
                return offset + _line_marker_offset(line)
            if fallback is None:
                fallback = offset + _line_marker_offset(line)
        offset += len(line)
    return fallback


def _line_marker_offset(line: str) -> int:
    lowered = line.lower()
    indexes = [lowered.find(marker) for marker in _AUDITOR_START_MARKERS if lowered.find(marker) >= 0]
    return min(indexes) if indexes else 0


def _is_toc_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    return bool(re.search(r"\b\d{1,4}\s*$", text)) and not re.search(r"\bfor\b|\bopinion\b|\bto\s+the\s+members\b", text, re.IGNORECASE)


def parse_audit_text(text: str, *, revenue_cr: float = 0.0) -> AuditSignal:
    section = extract_auditor_section(text) or text or ""
    auditor_name = _extract_auditor_name(section)

    return AuditSignal(
        auditor_name=auditor_name,
        auditor_tier=classify_auditor(auditor_name),
        opinion_type=_extract_opinion_type(section),
        emphasis_of_matter=bool(re.search(r"\bemphasis\s+of\s+matter\b", section, flags=re.IGNORECASE)),
        key_audit_matters_count=len(
            re.findall(r"\bkey\s+audit\s+matters?\s+\d+\b", section, flags=re.IGNORECASE)
        ),
        auditor_tenure_years=0,
        related_party_txn_pct_revenue=_related_party_pct_revenue(section, revenue_cr),
        source="annual_report",
    )


def _extract_auditor_name(text: str) -> str:
    fallback_candidate = ""
    for match in re.finditer(r"^\s*for\s+(.+?)\s*$", text, flags=re.IGNORECASE | re.MULTILINE):
        candidate = match.group(1).strip(" .,:;-")
        if "on behalf of" in candidate.lower():
            continue
        if classify_auditor(candidate) != "Unknown":
            return candidate
        fallback_candidate = fallback_candidate or candidate

    matchable_text = _matchable(text)
    for name in (*BIG4_NAMES, *MID_TIER_NAMES):
        if _matchable(name) in matchable_text:
            return name
    return fallback_candidate


def _extract_opinion_type(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\bqualified\s+opinion\b|\bexcept\s+for\b", lowered):
        return "Qualified"
    if re.search(r"\badverse\s+opinion\b", lowered):
        return "Adverse"
    if re.search(r"\bdisclaimer\s+of\s+opinion\b|\bdisclaimed\s+opinion\b", lowered):
        return "Disclaimer"
    if re.search(r"\btrue\s+and\s+fair\s+view\b|\bunmodified\s+opinion\b|\bclean\s+opinion\b", lowered):
        return "Clean"
    return "Unknown"


def _related_party_pct_revenue(text: str, revenue_cr: float) -> float:
    if revenue_cr <= 0:
        return 0.0

    default_unit = _declared_amount_unit(text)
    match = re.search(
        r"related\s+party.{0,200}?(?:aggregated\s+to|amounted\s+to|total(?:ed|led)?\s+to|transactions?\s+of)\s*"
        r"(?:rs\.?|inr|₹)?\s*([0-9][\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|million|mn)?",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            r"related\s+party.{0,200}?(?:rs\.?|inr|₹)\s*([0-9][\d,]*(?:\.\d+)?)\s*"
            r"(crores?|cr|lakhs?|million|mn)?",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if not match:
        return 0.0

    amount = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or default_unit or "crore").lower()
    if unit in {"lakh", "lakhs"}:
        amount /= 100
    elif unit in {"million", "mn"}:
        amount /= 10

    return round(amount / revenue_cr * 100, 2)


def _is_stop_heading(line: str) -> bool:
    text = line.strip().lower()
    if not text:
        return False
    if len(text.split()) > 7:
        return False
    return any(text == marker or text.startswith(marker + " ") for marker in _AUDITOR_STOP_MARKERS)


def _declared_amount_unit(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"rs\.?\s+in\s+lakh|₹\s+in\s+lakh|inr\s+in\s+lakh", lowered):
        return "lakh"
    if re.search(r"rs\.?\s+in\s+million|₹\s+in\s+million|inr\s+in\s+million", lowered):
        return "million"
    if re.search(r"rs\.?\s+in\s+crore|₹\s+in\s+crore|inr\s+in\s+crore", lowered):
        return "crore"
    return None
