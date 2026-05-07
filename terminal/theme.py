"""Theme and layout scale management for Agent Adda terminal."""
from __future__ import annotations
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT, "data", ".agent_config.json")

# ── Theme definitions ──────────────────────────────────────────────────────
THEMES: dict[str, dict] = {
    "dark": {
        "name": "Dark (Default)",
        "accent":    "cyan",
        "profit":    "green",
        "loss":      "red",
        "warn":      "yellow",
        "dim":       "dim",
        "title":     "bold cyan",
        "header":    "bold cyan",
        "border":    "bright_black",
        "symbol":    "bold yellow",
        "user_msg":  "bold white",
        "ai_msg":    "cyan",
        "hint":      "dim",
        "preview": [
            ("Agent Adda", "bold cyan"),
            (" ▲ RELIANCE +1.2%", "green"),
            (" ▼ INFY -0.4%", "red"),
            (" RSI: 58.2", "yellow"),
        ]
    },
    "dracula": {
        "name": "Dracula",
        "accent":    "bright_magenta",
        "profit":    "bright_green",
        "loss":      "bright_red",
        "warn":      "bright_yellow",
        "dim":       "bright_black",
        "title":     "bold bright_magenta",
        "header":    "bold bright_cyan",
        "border":    "magenta",
        "symbol":    "bold bright_cyan",
        "user_msg":  "bold bright_white",
        "ai_msg":    "bright_magenta",
        "hint":      "bright_black",
        "preview": [
            ("Agent Adda", "bold bright_magenta"),
            (" ▲ RELIANCE +1.2%", "bright_green"),
            (" ▼ INFY -0.4%", "bright_red"),
            (" RSI: 58.2", "bright_yellow"),
        ]
    },
    "solarized": {
        "name": "Solarized Dark",
        "accent":    "blue",
        "profit":    "green",
        "loss":      "red",
        "warn":      "yellow",
        "dim":       "bright_black",
        "title":     "bold blue",
        "header":    "bold cyan",
        "border":    "bright_black",
        "symbol":    "bold yellow",
        "user_msg":  "bold white",
        "ai_msg":    "blue",
        "hint":      "bright_black",
        "preview": [
            ("Agent Adda", "bold blue"),
            (" ▲ RELIANCE +1.2%", "green"),
            (" ▼ INFY -0.4%", "red"),
            (" RSI: 58.2", "yellow"),
        ]
    },
    "high-contrast": {
        "name": "High Contrast",
        "accent":    "bright_white",
        "profit":    "bright_green",
        "loss":      "bright_red",
        "warn":      "bright_yellow",
        "dim":       "white",
        "title":     "bold bright_white",
        "header":    "bold bright_white",
        "border":    "white",
        "symbol":    "bold bright_yellow",
        "user_msg":  "bold bright_white",
        "ai_msg":    "bright_white",
        "hint":      "white",
        "preview": [
            ("Agent Adda", "bold bright_white"),
            (" ▲ RELIANCE +1.2%", "bright_green"),
            (" ▼ INFY -0.4%", "bright_red"),
            (" RSI: 58.2", "bright_yellow"),
        ]
    },
    "nord": {
        "name": "Nord",
        "accent":    "bright_cyan",
        "profit":    "bright_green",
        "loss":      "bright_red",
        "warn":      "bright_yellow",
        "dim":       "bright_black",
        "title":     "bold bright_cyan",
        "header":    "bold bright_blue",
        "border":    "bright_black",
        "symbol":    "bold bright_blue",
        "user_msg":  "bold white",
        "ai_msg":    "bright_cyan",
        "hint":      "bright_black",
        "preview": [
            ("Agent Adda", "bold bright_cyan"),
            (" ▲ RELIANCE +1.2%", "bright_green"),
            (" ▼ INFY -0.4%", "bright_red"),
            (" RSI: 58.2", "bright_yellow"),
        ]
    },
}

# ── Scale definitions ──────────────────────────────────────────────────────
SCALES: dict[str, dict] = {
    "compact": {
        "name": "Compact",
        "chart_width":  80,
        "chart_height": 16,
        "table_padding": (0, 0),
        "description": "Tight layout — fits small terminals",
    },
    "normal": {
        "name": "Normal",
        "chart_width":  100,
        "chart_height": 20,
        "table_padding": (0, 1),
        "description": "Default balanced layout",
    },
    "large": {
        "name": "Large",
        "chart_width":  120,
        "chart_height": 28,
        "table_padding": (0, 2),
        "description": "Spacious layout — wide terminals / big screens",
    },
}

# ── Config persistence ─────────────────────────────────────────────────────
def _load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            return json.load(open(CONFIG_FILE))
        except Exception:
            pass
    return {}

def _save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# ── Public API ─────────────────────────────────────────────────────────────
def get_theme() -> dict:
    cfg = _load_config()
    name = cfg.get("theme", "dark")
    return THEMES.get(name, THEMES["dark"])

def set_theme(name: str) -> dict:
    if name not in THEMES:
        raise ValueError(f"Unknown theme '{name}'. Available: {list(THEMES)}")
    cfg = _load_config()
    cfg["theme"] = name
    _save_config(cfg)
    return THEMES[name]

def get_theme_name() -> str:
    return _load_config().get("theme", "dark")

def list_themes() -> list[str]:
    return list(THEMES)

def get_scale() -> dict:
    cfg = _load_config()
    name = cfg.get("scale", "normal")
    return SCALES.get(name, SCALES["normal"])

def set_scale(name: str) -> dict:
    if name not in SCALES:
        raise ValueError(f"Unknown scale '{name}'. Available: {list(SCALES)}")
    cfg = _load_config()
    cfg["scale"] = name
    _save_config(cfg)
    return SCALES[name]

def get_scale_name() -> str:
    return _load_config().get("scale", "normal")

def list_scales() -> list[str]:
    return list(SCALES)
