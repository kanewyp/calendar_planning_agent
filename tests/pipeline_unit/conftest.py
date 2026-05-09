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


# ===========================================================================
# Real-LLM session fixtures (used by T01–T25 and T77–T86)
# ===========================================================================
# These fixtures make genuine Vertex AI / Gemini 2.5 Flash calls.
# They are session-scoped so each goal calls the LLM exactly once regardless
# of how many tests share the fixture.
# Tests automatically skip if credentials are unavailable.
# ===========================================================================

import os  # noqa: E402


def _adc_available() -> bool:
    """Return True if Google Application Default Credentials can be refreshed."""
    try:
        import google.auth
        import google.auth.transport.requests

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
        creds.refresh(google.auth.transport.requests.Request())
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def requires_real_llm():
    """Skip all dependent tests if LLM_PROVIDER=mock or ADC is unavailable."""
    from config.settings import settings

    if settings.LLM_PROVIDER == "mock":
        pytest.skip(
            "LLM_PROVIDER=mock — set LLM_PROVIDER=vertex_ai to run real-LLM pipeline tests."
        )
    if settings.LLM_PROVIDER == "vertex_ai" and not _adc_available():
        pytest.skip(
            "Google Application Default Credentials not available — "
            "set GOOGLE_APPLICATION_CREDENTIALS to a valid service-account JSON."
        )


# ---------------------------------------------------------------------------
# Decomposition session fixtures — one LLM call per goal (5 goals, 10 tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_decomp_python(requires_real_llm):
    """Decompose 'Learn Python from scratch' — covers T01, T05, T06."""
    from src.orchestration.nodes.decompose_goal import decompose_goal_node
    return decompose_goal_node(base_decompose_state("Learn Python from scratch"))


@pytest.fixture(scope="session")
def real_decomp_wedding(requires_real_llm):
    """Decompose 'Plan a wedding' — covers T02, T07."""
    from src.orchestration.nodes.decompose_goal import decompose_goal_node
    return decompose_goal_node(base_decompose_state("Plan a wedding"))


@pytest.fixture(scope="session")
def real_decomp_dissertation(requires_real_llm):
    """Decompose 'Write my PhD dissertation' — covers T03."""
    from src.orchestration.nodes.decompose_goal import decompose_goal_node
    return decompose_goal_node(base_decompose_state("Write my PhD dissertation"))


@pytest.fixture(scope="session")
def real_decomp_mobile(requires_real_llm):
    """Decompose 'Build a mobile app MVP' — covers T04, T08, T09."""
    from src.orchestration.nodes.decompose_goal import decompose_goal_node
    return decompose_goal_node(base_decompose_state("Build a mobile app MVP"))


@pytest.fixture(scope="session")
def real_decomp_novel(requires_real_llm):
    """Decompose 'Write a novel' — covers T10."""
    from src.orchestration.nodes.decompose_goal import decompose_goal_node
    return decompose_goal_node(base_decompose_state("Write a novel"))


# ---------------------------------------------------------------------------
# Critic session fixtures — one LLM call per scenario (2 calls)
# ---------------------------------------------------------------------------

_GOOD_CRITIC_TASKS = [
    subtask("Set up dev environment",
            "[group:setup] [shuffle:no] [complexity:low] Install Python and VS Code.", 30),
    subtask("Learn core syntax",
            "[group:basics] [shuffle:no] [complexity:medium] Variables, types, control flow.", 60),
    subtask("Practice collections",
            "[group:collections] [shuffle:yes] [complexity:medium] Lists, dicts, sets.", 60),
    subtask("Practice functions",
            "[group:functions] [shuffle:no] [complexity:high] Parameters, return values, scope.", 90),
    subtask("Build mini project",
            "[group:capstone] [shuffle:no] [complexity:high] CLI todo app using all concepts.", 90),
]

_BAD_CRITIC_TASKS = [
    subtask("Do everything",
            "[group:work] [shuffle:no] [complexity:high] "
            "Research, outline, write, revise, and submit the full paper.", 90),
]


@pytest.fixture(scope="session")
def real_critic_good_plan(requires_real_llm):
    """Critic result for a well-structured 5-task plan — shared by T11–T15."""
    from src.orchestration.nodes.decomposition_review import decomposition_critic_node
    return decomposition_critic_node(base_critic_state(_GOOD_CRITIC_TASKS))


@pytest.fixture(scope="session")
def real_critic_bad_plan(requires_real_llm):
    """Critic result for a single vague mega-task — shared by T16–T19."""
    from src.orchestration.nodes.decomposition_review import decomposition_critic_node
    return decomposition_critic_node(
        base_critic_state(
            _BAD_CRITIC_TASKS,
            goal="Write a research paper on climate change",
        )
    )


# ---------------------------------------------------------------------------
# Reviser session fixture — one LLM call, shared by T21–T25
# ---------------------------------------------------------------------------

_REVISER_ORIGINAL = [
    subtask("Do all reading",
            "[group:reading] [shuffle:no] [complexity:high] Read everything.", 90),
    subtask("Write summary",
            "[group:writing] [shuffle:no] [complexity:medium] Summarise findings.", 60),
]
_REVISER_ISSUES = [
    {
        "severity": "major",
        "subtask": "Do all reading",
        "issue": "Too broad — covers too much material in one session.",
        "suggestion": "Split into 2–3 focused reading sessions by topic.",
    }
]
_REVISER_INSTRUCTION = (
    "Split 'Do all reading' into at least 2 concrete reading sessions, "
    "each focused on a specific topic or chapter range, with appropriate tags."
)


@pytest.fixture(scope="session")
def real_reviser(requires_real_llm):
    """Revision result for oversized reading task — shared by T21–T25."""
    from src.orchestration.nodes.decomposition_review import revise_decomposition_node
    return revise_decomposition_node(
        base_reviser_state(
            _REVISER_ORIGINAL,
            issues=_REVISER_ISSUES,
            instruction=_REVISER_INSTRUCTION,
        )
    )


# ---------------------------------------------------------------------------
# Rationale session fixture — three LLM calls (one per strategy), shared by T77–T82, T86
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_rationale(requires_real_llm):
    """Rationale generation for all three strategies — shared by T77–T82, T86."""
    from src.orchestration.nodes.generate_rationales import generate_rationales_node
    return generate_rationales_node(base_rationale_state())
