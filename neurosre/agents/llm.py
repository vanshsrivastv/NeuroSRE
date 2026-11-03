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
    """Chain of chat models tried in order: primary model, then backup model, then rules (None)."""

    def __init__(self, provider: str | None = None):
        self.provider = (provider or config.LLM_PROVIDER).lower()
        self.chats: list[tuple[str, object]] = []
        self.last_error: str | None = None
        self.calls = 0
        self.failures = 0          # calls where *every* model failed and the rules took over
        self.backup_used = 0       # calls answered by the backup model
        try:
            if self.provider == "groq" and config.GROQ_API_KEY:
                from langchain_groq import ChatGroq
                for model in dict.fromkeys(m for m in (config.GROQ_MODEL, config.GROQ_BACKUP_MODEL) if m):
                    extra = {"reasoning_effort": config.GROQ_REASONING_EFFORT} if "gpt-oss" in model else {}
                    self.chats.append((model, ChatGroq(model=model, api_key=config.GROQ_API_KEY,
                                                       temperature=config.LLM_TEMPERATURE, max_retries=2,
                                                       timeout=45, **extra)))
            elif self.provider == "anthropic" and config.ANTHROPIC_API_KEY:
                from langchain_anthropic import ChatAnthropic
                self.chats.append((config.ANTHROPIC_MODEL, ChatAnthropic(
                    model=config.ANTHROPIC_MODEL, api_key=config.ANTHROPIC_API_KEY,
                    temperature=config.LLM_TEMPERATURE, max_retries=2, timeout=45)))
            elif self.provider not in ("offline", "rules"):
                self.last_error = f"no API key configured for provider '{self.provider}'"
        except Exception as exc:  # pragma: no cover - import/config problems
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.chats = []
        if not self.chats:
            self.provider = "offline"

    # a single settable model, kept for tests that plug in a stub
    @property
    def chat(self):
        return self.chats[0][1] if self.chats else None

    @chat.setter
    def chat(self, value) -> None:
        self.chats = [("stub-model", value)] if value is not None else []

    @property
    def model_name(self) -> str:
        return self.chats[0][0] if self.chats else "rule-based"

    @model_name.setter
    def model_name(self, value: str) -> None:
        if self.chats:
            self.chats[0] = (value, self.chats[0][1])

    @property
    def enabled(self) -> bool:
        return bool(self.chats)

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model_name}" if self.enabled else "offline (rule-based)"

    def structured(self, schema: type[T], system: str, user: str) -> tuple[T | None, float, str]:
        """Return (parsed output or None, seconds taken, model that answered or "")."""
        if not self.enabled:
            return None, 0.0, ""
        t0 = time.time()
        self.calls += 1
        for i, (model, chat) in enumerate(self.chats):
            try:
                out = chat.with_structured_output(schema).invoke([("system", system), ("human", user)])
                if isinstance(out, dict):
                    out = schema.model_validate(out)
                if i > 0:
                    self.backup_used += 1
                return out, time.time() - t0, model
            except Exception as exc:
                self.last_error = f"{model}: {type(exc).__name__}: {str(exc)[:300]}"
                log.warning("LLM call to %s failed: %s", model, self.last_error)
        self.failures += 1
        log.warning("all models failed, falling back to rules")
        return None, time.time() - t0, ""
