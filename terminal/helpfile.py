"""Parse the generated Agent Adda markdown helpfile for runtime help surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HELPFILE_PATH = ROOT / "docs" / "AGENT_ADDA_HELPFILE.md"


@dataclass(frozen=True)
class HelpfileCommand:
    command: str
    description: str
    section: str


@dataclass(frozen=True)
class HelpfilePrompt:
    shortcut: str
    title: str
    prompt: str
    section: str


@dataclass(frozen=True)
class HelpfileCatalog:
    path: Path
    commands: tuple[HelpfileCommand, ...] = ()
    prompts: tuple[HelpfilePrompt, ...] = ()
    sections: dict[str, str] = field(default_factory=dict)

    def section_text(self, name: str) -> str:
        query = _norm(name)
        if query in self.sections:
            return self.sections[query]
        for key, text in self.sections.items():
            if query in key or key in query:
                return text
        return ""

    def section_names(self) -> list[str]:
        return sorted(self.sections)


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().lstrip("#").split())


def _split_md_row(line: str) -> list[str]:
    raw = line.strip()
    if not raw.startswith("|") or not raw.endswith("|"):
        return []
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for ch in raw[1:-1]:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    cells.append("".join(current).strip())
    return [_strip_inline_code(cell) for cell in cells]


def _strip_inline_code(value: str) -> str:
    out = value.strip()
    if out.startswith("`") and out.endswith("`") and len(out) >= 2:
        out = out[1:-1]
    return out


@lru_cache(maxsize=1)
def load_helpfile_catalog(path: str | Path | None = None) -> HelpfileCatalog:
    help_path = Path(path) if path is not None else HELPFILE_PATH
    if not help_path.exists():
        return HelpfileCatalog(path=help_path)

    text = help_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    sections: dict[str, str] = {}
    section_order: list[tuple[str, int]] = []
    for idx, line in enumerate(lines):
        if line.startswith("## "):
            title = line[3:].strip()
            section_order.append((title, idx))
    for pos, (title, start) in enumerate(section_order):
        end = section_order[pos + 1][1] if pos + 1 < len(section_order) else len(lines)
        sections[_norm(title)] = "\n".join(lines[start:end]).strip()

    commands: list[HelpfileCommand] = []
    prompts: list[HelpfilePrompt] = []
    current_h2 = ""
    current_h3 = ""
    in_commands = False
    in_prompts = False
    for line in lines:
        if line.startswith("## "):
            current_h2 = line[3:].strip()
            current_h3 = ""
            in_commands = _norm(current_h2) == "all slash commands"
            in_prompts = _norm(current_h2) == "full prompt library"
            continue
        if line.startswith("### "):
            current_h3 = line[4:].strip()
            continue
        cells = _split_md_row(line)
        if not cells or cells[0] in {"Command", "---", "Shortcut"}:
            continue
        if in_commands and len(cells) >= 2 and cells[0]:
            commands.append(HelpfileCommand(cells[0], cells[1], current_h3 or current_h2))
        elif in_prompts and len(cells) >= 3 and cells[0].startswith("p"):
            prompts.append(HelpfilePrompt(cells[0], cells[1], cells[2], current_h3 or current_h2))

    return HelpfileCatalog(
        path=help_path,
        commands=tuple(commands),
        prompts=tuple(prompts),
        sections=sections,
    )
