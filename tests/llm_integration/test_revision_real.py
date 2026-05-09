# =============================================================================
# tests/llm_integration/test_revision_real.py — Real-LLM revision node tests
# =============================================================================
# Calls revise_decomposition_node with genuine Vertex AI / Gemini 2.5 Flash.
# The critic issues and revision instruction are hardcoded (no LLM needed for
# them) — only the revision call itself touches the real LLM.
#
# One session-scoped fixture makes one LLM call. All 15 tests share it.
# =============================================================================

from __future__ import annotations

import pytest

from src.orchestration.nodes.decomposition_review import revise_decomposition_node


# ---------------------------------------------------------------------------
# Input: a single vague task + hardcoded critic feedback
# ---------------------------------------------------------------------------

_ORIGINAL_SUBTASKS = [
    {
        "name": "Do everything",
        "description": (
            "[group:work] [shuffle:no] [complexity:high] "
            "Research, outline, write, revise, and submit the full paper."
        ),
        "duration_minutes": 90,
    },
]

_CRITIC_ISSUES = [
    {
        "severity": "critical",
        "subtask": "Do everything",
        "issue": (
            "This single task attempts to cover the entire research paper lifecycle. "
            "It is far too vague and too large to schedule meaningfully."
        ),
        "suggestion": (
            "Split into at least 4 tasks: source research, outline drafting, "
            "body writing, and proofreading/submission."
        ),
    }
]

_REVISION_INSTRUCTION = (
    "Split the single vague 'Do everything' task into at least 4 concrete, "
    "schedulable tasks: one for research, one for outlining, one for drafting, "
    "and one for revision and submission. Each task should have a realistic "
    "duration and appropriate structural tags."
)


# ---------------------------------------------------------------------------
# Session-scoped fixture — one real LLM call, shared across all tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_revision(requires_real_llm):
    """Revise a flawed single-task plan using hardcoded critic feedback. One LLM call."""
    state = {
        "goal": "Write a research paper on climate change",
        "deadline": "2026-12-31",
        "context": "Academic writing, need peer-reviewed sources",
        "max_session_minutes": 90,
        "subtasks": _ORIGINAL_SUBTASKS,
        "decomposition_review_issues": _CRITIC_ISSUES,
        "decomposition_revision_instruction": _REVISION_INSTRUCTION,
    }
    return revise_decomposition_node(state)


# ===========================================================================
# T-V01–T-V15
# ===========================================================================

# T-V01
@pytest.mark.integration
def test_v01_revision_result_has_subtasks_key(real_revision):
    assert "subtasks" in real_revision, (
        f"revise_decomposition_node result keys: {list(real_revision.keys())}"
    )


# T-V02
@pytest.mark.integration
def test_v02_revised_subtasks_is_nonempty_list(real_revision):
    tasks = real_revision["subtasks"]
    assert isinstance(tasks, list) and len(tasks) > 0


# T-V03
@pytest.mark.integration
def test_v03_revised_subtask_count_in_range(real_revision):
    n = len(real_revision["subtasks"])
    assert 3 <= n <= 12, (
        f"Revision instruction asked for ≥4 tasks; got {n}. "
        "Expected count in the prompt's standard range of 3–12."
    )


# T-V04
@pytest.mark.integration
def test_v04_revised_count_greater_than_original(real_revision):
    """Revision must produce more tasks than the single original vague task."""
    n = len(real_revision["subtasks"])
    assert n > 1, (
        f"Revised subtask count is {n}. "
        "Revision of a single vague task must produce multiple concrete tasks."
    )


# T-V05
@pytest.mark.integration
def test_v05_revised_all_names_nonempty(real_revision):
    for i, t in enumerate(real_revision["subtasks"], 1):
        name = t.get("name")
        assert isinstance(name, str) and name.strip(), f"Subtask {i} has invalid name: {name!r}"


# T-V06
@pytest.mark.integration
def test_v06_revised_all_descriptions_are_strings(real_revision):
    for i, t in enumerate(real_revision["subtasks"], 1):
        desc = t.get("description")
        assert isinstance(desc, str), f"Subtask {i} description is not a string: {desc!r}"


# T-V07
@pytest.mark.integration
def test_v07_revised_durations_valid(real_revision):
    for i, t in enumerate(real_revision["subtasks"], 1):
        dur = t.get("duration_minutes")
        assert isinstance(dur, int) and 0 < dur <= 90, (
            f"Subtask {i} duration {dur!r} must be a positive int ≤ 90"
        )


# T-V08
@pytest.mark.integration
def test_v08_revised_at_least_one_group_tag(real_revision):
    descs = [t["description"] for t in real_revision["subtasks"]]
    assert any("[group:" in d for d in descs), (
        "No revised description contains [group:…] tag."
    )


# T-V09
@pytest.mark.integration
def test_v09_revised_at_least_one_complexity_tag(real_revision):
    descs = [t["description"] for t in real_revision["subtasks"]]
    assert any("[complexity:" in d for d in descs)


# T-V10
@pytest.mark.integration
def test_v10_vague_task_name_not_in_revised_output(real_revision):
    """The original 'Do everything' task must not survive revision unchanged."""
    names = [t["name"] for t in real_revision["subtasks"]]
    assert "Do everything" not in names, (
        f"Revised subtasks still contain 'Do everything': {names}"
    )


# T-V11
@pytest.mark.integration
def test_v11_result_has_decomposition_revised_key(real_revision):
    assert "decomposition_revised" in real_revision, (
        f"Keys returned: {list(real_revision.keys())}"
    )


# T-V12
@pytest.mark.integration
def test_v12_decomposition_revised_is_true(real_revision):
    assert real_revision["decomposition_revised"] is True, (
        f"decomposition_revised should be True, got {real_revision['decomposition_revised']!r}"
    )


# T-V13
@pytest.mark.integration
def test_v13_result_has_revision_count_key(real_revision):
    assert "decomposition_revision_count" in real_revision


# T-V14
@pytest.mark.integration
def test_v14_revision_count_is_at_least_one(real_revision):
    count = real_revision["decomposition_revision_count"]
    assert isinstance(count, int) and count >= 1, (
        f"decomposition_revision_count must be ≥ 1, got {count!r}"
    )


# T-V15
@pytest.mark.integration
def test_v15_revised_task_names_are_unique(real_revision):
    names = [t["name"] for t in real_revision["subtasks"]]
    assert len(names) == len(set(names)), (
        f"Duplicate task names in revision: {[n for n in names if names.count(n) > 1]}"
    )
