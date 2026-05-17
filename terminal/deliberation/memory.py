"""Lightweight in-session memory for watchlists and user theses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryStore:
    watchlist: list[str] = field(default_factory=list)
    theses: dict[str, str] = field(default_factory=dict)

    def remember_symbol(self, symbol: str) -> None:
        sym = (symbol or "").strip().upper()
        if sym and sym not in self.watchlist:
            self.watchlist.append(sym)

    def remember_thesis(self, symbol: str, thesis: str) -> None:
        sym = (symbol or "").strip().upper()
        if sym and thesis:
            self.theses[sym] = thesis.strip()
