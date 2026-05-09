# =============================================================================
# tests/pipeline_unit/conftest.py — Shared fixtures and helpers for LLM behavioural tests
# =============================================================================
# Module-level helpers (not fixtures) are imported directly by test modules.
# Pytest fixtures here are available to all tests under tests/pipeline_unit/.
# The top-level tests/conftest.py fixtures are also available here.
# =============================================================================

from __future__ import annotations

import datetime

import pytest


# ---------------------------------------------------------------------------
# Pure helpers — import these directly, no pytest magic needed
# ---------------------------------------------------------------------------

UTC = datetime.timezone.utc


def slot(start_iso: str, end_iso: str) -> dict[str, str]:
    """Build a free-slot dict."""
    return {"start": start_iso, "end": end_iso}


def subtask(name: str, description: str, duration_minutes: int) -> dict:
    """Build a subtask dict with exactly the three required keys."""
    return {
        "name": name,
        "description": description,
        "duration_minutes": duration_minutes,
    }


def dt(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime.datetime:
    """UTC datetime shorthand."""
    return datetime.datetime(y, mo, d, h, mi, tzinfo=UTC)


def isodt(y: int, mo: int, d: int, h: int, mi: int = 0) -> str:
    """Return ISO 8601 string in +00:00 format."""
    return dt(y, mo, d, h, mi).isoformat()


# ---------------------------------------------------------------------------
# Shared state builders for decomposition / rationale node tests
# ---------------------------------------------------------------------------

def base_decompose_state(
    goal: str = "Learn Python basics",
    deadline: str = "2026-06-01",
    context: str = "No prior experience.",
    max_session_minutes: int = 90,
) -> dict:
    return {
        "goal": goal,
        "deadline": deadline,
        "context": context,
        "max_session_minutes": max_session_minutes,
    }


def base_critic_state(subtasks: list[dict], **overrides) -> dict:
    state = base_decompose_state()
    state["subtasks"] = subtasks
    state.update(overrides)
    return state


def base_reviser_state(
    subtasks: list[dict],
    issues: list[dict],
    instruction: str,
    **overrides,
) -> dict:
    state = base_decompose_state()
    state["subtasks"] = subtasks
    state["decomposition_review_issues"] = issues
    state["decomposition_revision_instruction"] = instruction
    state.update(overrides)
    return state


def base_rationale_state(
    subtasks: list[dict] | None = None,
    deadline_events: list[dict] | None = None,
    frag_events: list[dict] | None = None,
    energy_events: list[dict] | None = None,
    violations: dict | None = None,
) -> dict:
    """Build minimal state for generate_rationales_node."""
    if subtasks is None:
        subtasks = [
            subtask("Task A", "[group:g] [shuffle:no] [complexity:medium] Study.", 60),
        ]
    if deadline_events is None:
        deadline_events = [
            {"name": "Task A", "description": "Study.", "start": "2026-05-11T09:00:00+00:00", "end": "2026-05-11T10:00:00+00:00"},
        ]
    if frag_events is None:
        frag_events = deadline_events
    if energy_events is None:
        energy_events = deadline_events
    if violations is None:
        violations = {
            "deadline_first": {"passed": True, "violations": []},
            "min_fragmentation": {"passed": True, "violations": []},
            "energy_aware": {"passed": True, "violations": []},
        }
    return {
        "goal": "Learn Python basics",
        "context": "No prior experience.",
        "work_start": "09:00",
        "work_end": "18:00",
        "energy_levels": {"morning": "high", "afternoon": "medium", "evening": "low"},
        "subtasks": subtasks,
        "candidate_deadline_first": deadline_events,
        "candidate_min_fragmentation": frag_events,
        "candidate_energy_aware": energy_events,
        "candidate_validations": violations,
    }


# ---------------------------------------------------------------------------
# Common subtask factories used across multiple test files
# ---------------------------------------------------------------------------

def tagged_subtask(
    name: str,
    group: str,
    shuffle: str,
    complexity: str,
    duration_minutes: int,
    seq: int | None = None,
) -> dict:
    """Subtask with fully populated structural tags."""
    seq_tag = f" [seq:{seq}]" if seq is not None else ""
    desc = (
        f"[group:{group}] [shuffle:{shuffle}] [complexity:{complexity}]{seq_tag} "
        f"Description of {name}."
    )
    return subtask(name, desc, duration_minutes)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def standard_energy_levels() -> dict[str, str]:
    """Canonical energy profile used by most energy-aware tests."""
    return {"morning": "high", "afternoon": "medium", "evening": "low"}


@pytest.fixture
def simple_critic_issues() -> list[dict]:
    return [
        {
            "severity": "major",
            "subtask": "Do all the research",
            "issue": "Task is too vague and oversized.",
            "suggestion": "Split into focused subtopics.",
        }
    ]
