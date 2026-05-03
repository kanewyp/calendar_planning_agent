# =============================================================================
# config/settings.py — Centralised application configuration
# =============================================================================
# Loads values from environment variables (via .env) and provides typed,
# validated defaults for the rest of the application.
#
# STEPS TO COMPLETE:
# 1. Add any new env vars your modules need to the Settings class.
# 2. If deploying on AWS, override env vars via Secrets Manager / SSM
#    rather than changing this file.
# =============================================================================

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings:
    """Read-only application settings sourced from environment variables."""

    # --- LLM provider ---
    # Supported values:
    # - "anthropic": use the Anthropic SDK.
    # - "gemini": use Gemini's OpenAI-compatible Chat Completions endpoint.
    # - "vertex_ai": use Vertex AI's OpenAI-compatible Chat Completions endpoint.
    # - "openai_compatible": use any OpenAI-compatible Chat Completions endpoint.
    # - "mock": return deterministic local responses for development.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")
    LLM_DECOMPOSITION_MODEL: str = os.getenv("LLM_DECOMPOSITION_MODEL", "")
    LLM_RATIONALE_MODEL: str = os.getenv("LLM_RATIONALE_MODEL", "")
    VERTEX_PROJECT_ID: str = os.getenv("VERTEX_PROJECT_ID", "")
    VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "global")

    # --- Provider-specific compatibility keys ---
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # --- Google Calendar ---
    GOOGLE_CLIENT_SECRET_FILE: str = os.getenv(
        "GOOGLE_CLIENT_SECRET_FILE", "credentials.json"
    )

    # "mock" → use src/calendar_api/mock_calendar.py
    # "live" → use real Google Calendar OAuth
    CALENDAR_MODE: str = os.getenv("CALENDAR_MODE", "mock")

    # --- Scheduling defaults ---
    DEFAULT_WORK_START: str = os.getenv("DEFAULT_WORK_START", "09:00")
    DEFAULT_WORK_END: str = os.getenv("DEFAULT_WORK_END", "18:00")

    # --- AWS (production only) ---
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")


# Singleton instance — import this everywhere
settings = Settings()
