"""Configuration loader for the stock email agent.

Reads from environment (and .env when python-dotenv is available).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _split(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class EmailConfig:
    host: str = os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com")
    port: int = int(os.getenv("GMAIL_IMAP_PORT", "993"))
    user: str = os.getenv("GMAIL_USER", "")
    app_password: str = os.getenv("GMAIL_APP_PASSWORD", "")
    mailbox: str = os.getenv("GMAIL_MAILBOX", "INBOX")
    # Default sender / keyword filters (comma separated env)
    sender_allowlist: List[str] = field(
        default_factory=lambda: _split(os.getenv("STOCK_EMAIL_SENDERS"))
    )
    keyword_filters: List[str] = field(
        default_factory=lambda: _split(
            os.getenv(
                "STOCK_EMAIL_KEYWORDS",
                "results,dividend,split,bonus,buyback,rights,agm,egm,board meeting,earnings,quarterly,annual report,corporate action",
            )
        )
    )

    def validate(self) -> None:
        if not self.user or not self.app_password:
            raise RuntimeError(
                "Gmail credentials missing. Set GMAIL_USER and GMAIL_APP_PASSWORD "
                "in your .env (use a Google App Password, not your normal one)."
            )


@dataclass
class LLMConfig:
    provider: str = os.getenv("STOCK_LLM_PROVIDER", "anthropic").lower()
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    max_output_tokens: int = int(os.getenv("STOCK_LLM_MAX_TOKENS", "1200"))
    temperature: float = float(os.getenv("STOCK_LLM_TEMPERATURE", "0.3"))


@dataclass
class AppConfig:
    email: EmailConfig = field(default_factory=EmailConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    cache_dir: str = os.getenv(
        "STOCK_EMAIL_CACHE_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp", "stock_email_agent"),
    )
    max_link_bytes: int = int(os.getenv("STOCK_EMAIL_MAX_LINK_BYTES", str(5 * 1024 * 1024)))
    request_timeout: int = int(os.getenv("STOCK_EMAIL_REQUEST_TIMEOUT", "20"))


def load_config() -> AppConfig:
    cfg = AppConfig()
    os.makedirs(cfg.cache_dir, exist_ok=True)
    return cfg
