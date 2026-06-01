"""Provider-agnostic LLM wrapper. Supports Anthropic, OpenAI, and Ollama."""
from __future__ import annotations

import json
import logging
from typing import List, Optional

import requests

from .config import LLMConfig

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.provider = cfg.provider

    def complete(self, system: str, user: str, history: Optional[List[dict]] = None) -> str:
        history = history or []
        if self.provider == "anthropic":
            return self._anthropic(system, user, history)
        if self.provider == "openai":
            return self._openai(system, user, history)
        if self.provider == "ollama":
            return self._ollama(system, user, history)
        raise LLMError(f"Unknown LLM provider: {self.provider}")

    # ---- Anthropic ----
    def _anthropic(self, system: str, user: str, history: List[dict]) -> str:
        if not self.cfg.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY not set")
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("anthropic package not installed. pip install anthropic") from exc
        client = anthropic.Anthropic(api_key=self.cfg.anthropic_api_key)
        messages = list(history) + [{"role": "user", "content": user}]
        resp = client.messages.create(
            model=self.cfg.anthropic_model,
            system=system,
            max_tokens=self.cfg.max_output_tokens,
            temperature=self.cfg.temperature,
            messages=messages,
        )
        return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()

    # ---- OpenAI ----
    def _openai(self, system: str, user: str, history: List[dict]) -> str:
        if not self.cfg.openai_api_key:
            raise LLMError("OPENAI_API_KEY not set")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMError("openai package not installed. pip install openai") from exc
        client = OpenAI(api_key=self.cfg.openai_api_key)
        messages = [{"role": "system", "content": system}] + list(history) + [{"role": "user", "content": user}]
        resp = client.chat.completions.create(
            model=self.cfg.openai_model,
            messages=messages,
            temperature=self.cfg.temperature,
            max_tokens=self.cfg.max_output_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    # ---- Ollama ----
    def _ollama(self, system: str, user: str, history: List[dict]) -> str:
        messages = [{"role": "system", "content": system}] + list(history) + [{"role": "user", "content": user}]
        try:
            resp = requests.post(
                f"{self.cfg.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.cfg.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": self.cfg.temperature,
                        "num_predict": self.cfg.max_output_tokens,
                    },
                },
                timeout=120,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise LLMError(f"Ollama call failed: {exc}") from exc
        data = resp.json()
        if "message" in data and isinstance(data["message"], dict):
            return (data["message"].get("content") or "").strip()
        return json.dumps(data)[:2000]
