from __future__ import annotations

import re


ALIASES = {
    "d mart": "DMART",
    "dmart": "DMART",
    "avenue supermarts": "DMART",
    "nifty bank": "NIFTY BANK",
    "bank nifty": "NIFTY BANK",
}

SUPPORTED_VOICE_LANGUAGES = "English and Hindi"
VOICE_SALUTATION = "I am the Market Intelligence Assistant from Agent Adda."


def validate_supported_spoken_language(transcript: str) -> dict:
    text = (transcript or "").strip()
    if not text:
        return {"ok": False, "error": "empty transcript; please speak in English or Hindi and try again"}

    unsupported = []
    for ch in text:
        code = ord(ch)
        if _is_allowed_english_hindi_char(code):
            continue
        if ch.isspace() or ch in ".,!?;:'\"()[]{}-/₹%&+*#@":
            continue
        unsupported.append(ch)

    if unsupported:
        sample = "".join(unsupported[:12])
        return {
            "ok": False,
            "error": f"unsupported transcript language/script detected ({sample}); please speak in English or Hindi only",
        }
    return {"ok": True}


def validate_actionable_spoken_query(transcript: str) -> dict:
    text = re.sub(r"\s+", " ", transcript or "").strip().lower()
    if text in {"answer", "answer.", "response", "respond"}:
        return {
            "ok": False,
            "error": "I heard only a control word, not a clear market question. Please ask again with a stock, index, sector, or market topic.",
        }
    return {"ok": True}


def _is_allowed_english_hindi_char(code: int) -> bool:
    # ASCII covers English plus romanized Hindi, numbers, and punctuation.
    if 0x0000 <= code <= 0x007F:
        return True
    # Devanagari block covers Hindi written in native script.
    if 0x0900 <= code <= 0x097F:
        return True
    # Common Indic punctuation marks.
    if code in (0x0964, 0x0965):
        return True
    return False


def normalize_spoken_query(transcript: str) -> str:
    text = re.sub(r"\s+", " ", transcript or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    for alias, symbol in ALIASES.items():
        if alias in lowered:
            text = re.sub(alias, symbol, text, flags=re.I)
    lowered = text.lower()
    if any(phrase in lowered for phrase in ("your read on", "view on", "what do you think", "analyze", "analyse")):
        return f"Analyze this spoken market question: {text}. Include evidence, market context, risk, and what to watch next."
    return f"Answer this spoken market question: {text}. Be concise, evidence-aware, risk-first, and research-only."


def build_spoken_summary(query: str, answer: str, max_words: int = 170) -> str:
    clean = re.sub(r"\s+", " ", answer or "").strip()
    clean = re.sub(r"━━━.*?━━━", "", clean).strip()
    words = clean.split()
    excerpt = " ".join(words[: max(40, max_words - 58)])
    if not excerpt:
        excerpt = "I could not produce a reliable market read from the available evidence."
    follow_up = build_voice_follow_up_prompt(query)
    return (
        f"{VOICE_SALUTATION} My read: {excerpt} "
        "The risk is that stale or incomplete data can change the conclusion, so verify the source trail. "
        f"{follow_up} "
        "This is AI-generated research-only audio, not investment advice."
    )


def build_voice_follow_up_prompt(query: str) -> str:
    lowered = (query or "").lower()
    if any(word in lowered for word in ("dmart", "reliance", "tcs", "infy", "sbin", "stock", "company")):
        return "Would you like me to go deeper into technical levels, business quality, or the latest news next?"
    if any(word in lowered for word in ("market", "nifty", "bank", "sector", "mood")):
        return "Would you like me to check sector leadership, FII-DII flows, or specific stocks next?"
    if any(word in lowered for word in ("portfolio", "holding", "holdings")):
        return "Would you like me to review position risk, sector concentration, or exit watchpoints next?"
    return "What would you like me to check next: technicals, fundamentals, news, or risk?"
