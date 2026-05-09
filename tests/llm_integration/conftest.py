# =============================================================================
# tests/llm_integration/conftest.py — Shared setup for real-LLM integration tests
# =============================================================================
# These tests make genuine API calls to the configured LLM provider
# (vertex_ai / gemini-2.5-flash by default). They are slow and require Google
# Application Default Credentials to be present.
#
# Run with:
#   CALENDAR_MODE=mock .venv/bin/pytest tests/llm_integration/ -v -m integration -s
#
# Skip these tests in CI by NOT passing -m integration (they will be collected
# but skipped automatically when credentials are absent).
# =============================================================================

from __future__ import annotations

import os

import pytest


# ---------------------------------------------------------------------------
# Credential guard — skip the whole suite if ADC / provider isn't usable
# ---------------------------------------------------------------------------

def _adc_available() -> bool:
    """Return True if Google Application Default Credentials can be refreshed."""
    try:
        import google.auth
        import google.auth.transport.requests

        # Ensure the env var is resolved to an absolute path so it works
        # regardless of where pytest was invoked from.
        cred_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        if cred_env and not os.path.isabs(cred_env):
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            abs_path = os.path.join(project_root, cred_env)
            if os.path.exists(abs_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        req = google.auth.transport.requests.Request()
        creds.refresh(req)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def requires_real_llm():
    """Session fixture: skip the whole session if the LLM can't be reached.

    Tests that depend on this fixture are automatically skipped when:
    - GOOGLE_APPLICATION_CREDENTIALS is missing or invalid
    - LLM_PROVIDER is set to "mock"
    """
    from config.settings import settings

    if settings.LLM_PROVIDER == "mock":
        pytest.skip(
            "LLM_PROVIDER=mock — set LLM_PROVIDER=vertex_ai (or gemini/anthropic) "
            "to run integration tests"
        )

    if settings.LLM_PROVIDER == "vertex_ai" and not _adc_available():
        pytest.skip(
            "Google Application Default Credentials not available — "
            "run: gcloud auth application-default login  OR  set "
            "GOOGLE_APPLICATION_CREDENTIALS to a valid service-account JSON"
        )


# ---------------------------------------------------------------------------
# Hard-coded subtask data used by critic and rationale tests
# (these don't need an LLM to produce — they're pre-built inputs)
# ---------------------------------------------------------------------------

SIMPLE_SUBTASKS: list[dict] = [
    {
        "name": "Set up development environment",
        "description": (
            "[group:setup] [shuffle:no] [complexity:low] "
            "Install required tools and verify the toolchain works."
        ),
        "duration_minutes": 30,
    },
    {
        "name": "Learn core syntax",
        "description": (
            "[group:fundamentals] [shuffle:no] [complexity:medium] "
            "Study variables, control flow, and functions with short exercises."
        ),
        "duration_minutes": 60,
    },
    {
        "name": "Practice with collections",
        "description": (
            "[group:fundamentals] [shuffle:yes] [complexity:medium] "
            "Work through lists, dicts, and iteration patterns."
        ),
        "duration_minutes": 50,
    },
    {
        "name": "Build a mini project",
        "description": (
            "[group:capstone] [shuffle:no] [complexity:high] "
            "Integrate syntax, collections, and functions in a small working program."
        ),
        "duration_minutes": 90,
    },
]


def _make_event(
    name: str, description: str, start: str, end: str
) -> dict[str, str]:
    return {"name": name, "description": description, "start": start, "end": end}


# Three minimal candidate schedules used by rationale tests.
# Content doesn't matter — the LLM just reads them for context.
CANDIDATE_DEADLINE_FIRST: list[dict[str, str]] = [
    _make_event(
        "Set up development environment",
        SIMPLE_SUBTASKS[0]["description"],
        "2026-12-01T09:00:00+00:00",
        "2026-12-01T09:30:00+00:00",
    ),
    _make_event(
        "Learn core syntax",
        SIMPLE_SUBTASKS[1]["description"],
        "2026-12-01T09:30:00+00:00",
        "2026-12-01T10:30:00+00:00",
    ),
    _make_event(
        "Practice with collections",
        SIMPLE_SUBTASKS[2]["description"],
        "2026-12-01T10:30:00+00:00",
        "2026-12-01T11:20:00+00:00",
    ),
    _make_event(
        "Build a mini project",
        SIMPLE_SUBTASKS[3]["description"],
        "2026-12-01T11:20:00+00:00",
        "2026-12-01T12:50:00+00:00",
    ),
]

# min_fragmentation schedule: same order, split across two days
CANDIDATE_MIN_FRAGMENTATION: list[dict[str, str]] = [
    _make_event(
        "Set up development environment",
        SIMPLE_SUBTASKS[0]["description"],
        "2026-12-01T09:00:00+00:00",
        "2026-12-01T09:30:00+00:00",
    ),
    _make_event(
        "Learn core syntax",
        SIMPLE_SUBTASKS[1]["description"],
        "2026-12-01T09:30:00+00:00",
        "2026-12-01T10:30:00+00:00",
    ),
    _make_event(
        "Practice with collections",
        SIMPLE_SUBTASKS[2]["description"],
        "2026-12-02T09:00:00+00:00",
        "2026-12-02T09:50:00+00:00",
    ),
    _make_event(
        "Build a mini project",
        SIMPLE_SUBTASKS[3]["description"],
        "2026-12-02T09:50:00+00:00",
        "2026-12-02T11:20:00+00:00",
    ),
]

# energy-aware schedule: setup and learn in morning, practice and project in afternoon
CANDIDATE_ENERGY_AWARE: list[dict[str, str]] = [
    _make_event(
        "Set up development environment",
        SIMPLE_SUBTASKS[0]["description"],
        "2026-12-01T09:00:00+00:00",
        "2026-12-01T09:30:00+00:00",
    ),
    _make_event(
        "Learn core syntax",
        SIMPLE_SUBTASKS[1]["description"],
        "2026-12-01T09:30:00+00:00",
        "2026-12-01T10:30:00+00:00",
    ),
    _make_event(
        "Practice with collections",
        SIMPLE_SUBTASKS[2]["description"],
        "2026-12-01T13:00:00+00:00",
        "2026-12-01T13:50:00+00:00",
    ),
    _make_event(
        "Build a mini project",
        SIMPLE_SUBTASKS[3]["description"],
        "2026-12-01T13:50:00+00:00",
        "2026-12-01T15:20:00+00:00",
    ),
]

CANDIDATE_VALIDATIONS: dict[str, dict] = {
    "deadline_first": {"passed": True, "violations": []},
    "min_fragmentation": {"passed": True, "violations": []},
    "energy_aware": {"passed": True, "violations": []},
}
