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
GROQ_BACKUP_MODEL = os.getenv("GROQ_BACKUP_MODEL", "openai/gpt-oss-20b").strip()   # separate rate-limit quota
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low").strip()         # fewer hidden reasoning tokens
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5").strip()
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# Agent behaviour
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "3"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))
# Evidence gate: the LLM's runbook must agree with independent (evidence-only) retrieval
AGREEMENT_MARGIN = float(os.getenv("AGREEMENT_MARGIN", "0.03"))     # near-tie with the top hit still counts
MIN_RETRIEVAL_SCORE = float(os.getenv("MIN_RETRIEVAL_SCORE", "0.45"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "15"))     # seconds before giving up on a model and trying the next one

# Monitor: an alert fires only after the anomaly persists for N consecutive checks (like Prometheus "for:")
ALERT_FOR_CHECKS = int(os.getenv("ALERT_FOR_CHECKS", "2"))

# Simulator
TICK_SECONDS = float(os.getenv("TICK_SECONDS", "2"))
AUTO_FAULT_EVERY_SECONDS = float(os.getenv("AUTO_FAULT_EVERY_SECONDS", "45"))
