"""LLM provider wrapper.

Supports Groq (default, free tier, Llama 3.3 70B), Anthropic Claude, or
"offline" mode. Every call asks for *structured* output validated by a
Pydantic schema. If the provider is not configured or a call fails, callers
receive None and fall back to deterministic rule-based logic, so the system
never stops working during a demo.
"""
from __future__ import annotations

import logging
import time
from typing import TypeVar

from pydantic import BaseModel

from .. import config

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self, provider: str | None = None):
        self.provider = (provider or config.LLM_PROVIDER).lower()
        self.model_name = "rule-based"
        self.chat = None
        self.last_error: str | None = None
        self.calls = 0
        self.failures = 0
        try:
            if self.provider == "groq" and config.GROQ_API_KEY:
                from langchain_groq import ChatGroq
                self.chat = ChatGroq(model=config.GROQ_MODEL, api_key=config.GROQ_API_KEY,
                                     temperature=config.LLM_TEMPERATURE, max_retries=3, timeout=45)
                self.model_name = config.GROQ_MODEL
            elif self.provider == "anthropic" and config.ANTHROPIC_API_KEY:
                from langchain_anthropic import ChatAnthropic
                self.chat = ChatAnthropic(model=config.ANTHROPIC_MODEL, api_key=config.ANTHROPIC_API_KEY,
                                          temperature=config.LLM_TEMPERATURE, max_retries=3, timeout=45)
                self.model_name = config.ANTHROPIC_MODEL
            elif self.provider not in ("offline", "rules"):
                self.last_error = f"no API key configured for provider '{self.provider}'"
        except Exception as exc:  # pragma: no cover - import/config problems
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.chat = None
        if self.chat is None:
            self.provider = "offline"

    @property
    def enabled(self) -> bool:
        return self.chat is not None

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model_name}" if self.enabled else "offline (rule-based)"

    def structured(self, schema: type[T], system: str, user: str) -> tuple[T | None, float]:
        """Return (parsed_output or None, seconds taken)."""
        if not self.enabled:
            return None, 0.0
        t0 = time.time()
        self.calls += 1
        try:
            runnable = self.chat.with_structured_output(schema)
            out = runnable.invoke([("system", system), ("human", user)])
            if isinstance(out, dict):
                out = schema.model_validate(out)
            return out, time.time() - t0
        except Exception as exc:
            self.failures += 1
            self.last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            log.warning("LLM call failed, falling back to rules: %s", self.last_error)
            return None, time.time() - t0
