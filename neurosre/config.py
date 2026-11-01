"""Central configuration, read from environment variables / a .env file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("NEUROSRE_DATA_DIR", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

RUNBOOK_DIR = ROOT / "neurosre" / "knowledge" / "runbooks"
CHROMA_DIR = DATA_DIR / "chroma"
DB_PATH = DATA_DIR / "neurosre.db"

# LLM provider: "groq" (default), "anthropic", or "offline" (rule-based, no network)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5").strip()
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# Agent behaviour
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "3"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))

# Simulator
TICK_SECONDS = float(os.getenv("TICK_SECONDS", "2"))
AUTO_FAULT_EVERY_SECONDS = float(os.getenv("AUTO_FAULT_EVERY_SECONDS", "45"))
