"""Lightweight rule-based classifier for stock corporate-action emails."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from .email_client import EmailMessage

CATEGORY_PATTERNS: Dict[str, List[str]] = {
    "results": [r"\bresults?\b", r"\bearnings\b", r"\bquarterly\b", r"\bQ[1-4]\s*FY", r"\bprofit after tax\b", r"\brevenue\b"],
    "dividend": [r"\bdividend\b", r"\binterim dividend\b", r"\bfinal dividend\b", r"\brecord date\b"],
    "split": [r"\bstock split\b", r"\bshare split\b", r"\bsub[- ]?division\b"],
    "bonus": [r"\bbonus (issue|shares)\b"],
    "buyback": [r"\bbuy[- ]?back\b"],
    "rights": [r"\brights issue\b"],
    "board_meeting": [r"\bboard meeting\b", r"\bintimation of board meeting\b"],
    "agm_egm": [r"\bAGM\b", r"\bEGM\b", r"\bannual general meeting\b", r"\bextra[- ]?ordinary general meeting\b"],
    "merger_acquisition": [r"\bmerger\b", r"\bacquisition\b", r"\bdemerger\b", r"\bscheme of arrangement\b"],
    "insider_trade": [r"\binsider\b", r"\bSAST\b", r"\bPIT regulations\b"],
}

TICKER_RE = re.compile(r"\b([A-Z]{2,10})(?:[.\-:](NS|NSE|BO|BSE))?\b")


@dataclass
class Classification:
    categories: List[str] = field(default_factory=list)
    tickers: List[str] = field(default_factory=list)
    is_critical: bool = False


CRITICAL_CATEGORIES = {"results", "dividend", "split", "bonus", "buyback", "rights", "merger_acquisition"}


def classify(msg: EmailMessage) -> Classification:
    text = f"{msg.subject}\n{msg.body_text}"
    low = text.lower()
    cats: List[str] = []
    for cat, patterns in CATEGORY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, low if pat.islower() else text, re.IGNORECASE):
                cats.append(cat)
                break
    tickers = sorted({m.group(1) for m in TICKER_RE.finditer(msg.subject)
                      if 2 <= len(m.group(1)) <= 10 and m.group(1) not in {"NSE", "BSE", "AGM", "EGM", "FY", "PAT", "EPS"}})
    return Classification(
        categories=cats,
        tickers=tickers[:5],
        is_critical=any(c in CRITICAL_CATEGORIES for c in cats),
    )
