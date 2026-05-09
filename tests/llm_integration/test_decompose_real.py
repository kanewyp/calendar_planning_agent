# =============================================================================
# tests/llm_integration/test_decompose_real.py — Real-LLM decomposition tests
# =============================================================================
# Calls decompose_goal_node with genuine Vertex AI / Gemini 2.5 Flash.
# All assertions are structural: shape, types, and invariants — not exact text.
#
# Two session-scoped fixtures make one LLM call each.
# T-D01–T-D15 test the SQL goal; T-D16–T-D30 test the conference-talk goal.
# =============================================================================

from __future__ import annotations

import re

import pytest

from src.orchestration.nodes.decompose_goal import decompose_goal_node


_MAX_SESSION = 90  # shared max session for both scenarios

# ---------------------------------------------------------------------------
# Session-scoped fixtures — one LLM call each
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_decomposition_sql(requires_real_llm):
    """Decompose 'Learn SQL basics in one week'. One real LLM call."""
    state = {
        "goal": "Learn SQL basics in one week",
        "deadline": "2026-12-07",
        "context": "Complete beginner, 1-2 hours available each evening on a laptop",
        "max_session_minutes": _MAX_SESSION,
    }
    return decompose_goal_node(state)


@pytest.fixture(scope="session")
def real_decomposition_talk(requires_real_llm):
    """Decompose 'Write and deliver a 10-minute conference talk'. One real LLM call."""
    state = {
        "goal": "Write and deliver a 10-minute conference talk on machine learning",
        "deadline": "2026-12-14",
        "context": "Experienced engineer, first time public speaking, slides needed",
        "max_session_minutes": _MAX_SESSION,
    }
    return decompose_goal_node(state)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _subtasks(result: dict) -> list[dict]:
    return result["subtasks"]


# ===========================================================================
# GOAL A — "Learn SQL basics in one week"  (T-D01–T-D15)
# ===========================================================================

# T-D01
@pytest.mark.integration
def test_d01_sql_result_has_subtasks_key(real_decomposition_sql):
    assert "subtasks" in real_decomposition_sql


# T-D02
@pytest.mark.integration
def test_d02_sql_subtasks_is_nonempty_list(real_decomposition_sql):
    tasks = _subtasks(real_decomposition_sql)
    assert isinstance(tasks, list) and len(tasks) > 0


# T-D03
@pytest.mark.integration
def test_d03_sql_subtask_count_in_range(real_decomposition_sql):
    n = len(_subtasks(real_decomposition_sql))
    assert 3 <= n <= 12, f"Prompt asks for 3–12 subtasks; LLM returned {n}"


# T-D04
@pytest.mark.integration
def test_d04_sql_all_names_nonempty_strings(real_decomposition_sql):
    for i, t in enumerate(_subtasks(real_decomposition_sql), 1):
        name = t.get("name")
        assert isinstance(name, str) and name.strip(), f"Subtask {i} invalid name: {name!r}"


# T-D05
@pytest.mark.integration
def test_d05_sql_all_descriptions_are_strings(real_decomposition_sql):
    for i, t in enumerate(_subtasks(real_decomposition_sql), 1):
        desc = t.get("description")
        assert isinstance(desc, str), f"Subtask {i} description is not a string: {desc!r}"


# T-D06
@pytest.mark.integration
def test_d06_sql_durations_valid(real_decomposition_sql):
    for i, t in enumerate(_subtasks(real_decomposition_sql), 1):
        dur = t.get("duration_minutes")
        assert isinstance(dur, int) and 0 < dur <= _MAX_SESSION, (
            f"Subtask {i} duration {dur!r} must be int in (0, {_MAX_SESSION}]"
        )


# T-D07
@pytest.mark.integration
def test_d07_sql_at_least_one_group_tag(real_decomposition_sql):
    descs = [t["description"] for t in _subtasks(real_decomposition_sql)]
    assert any("[group:" in d for d in descs), (
        "No description contains [group:…] tag. Descriptions:\n"
        + "\n".join(f"  {d!r}" for d in descs)
    )


# T-D08
@pytest.mark.integration
def test_d08_sql_at_least_one_complexity_tag(real_decomposition_sql):
    descs = [t["description"] for t in _subtasks(real_decomposition_sql)]
    assert any("[complexity:" in d for d in descs)


# T-D09
@pytest.mark.integration
def test_d09_sql_at_least_one_shuffle_tag(real_decomposition_sql):
    descs = [t["description"] for t in _subtasks(real_decomposition_sql)]
    assert any("[shuffle:" in d for d in descs), (
        "No description contains [shuffle:…] tag. Prompt requires [shuffle:yes|no]."
    )


# T-D10
@pytest.mark.integration
def test_d10_sql_all_task_names_unique(real_decomposition_sql):
    names = [t["name"] for t in _subtasks(real_decomposition_sql)]
    assert len(names) == len(set(names)), (
        f"Duplicate task names: {[n for n in names if names.count(n) > 1]}"
    )


# T-D11
@pytest.mark.integration
def test_d11_sql_at_least_two_distinct_groups(real_decomposition_sql):
    """A sequential learning goal must have ≥2 groups (dependency structure)."""
    groups = set()
    for t in _subtasks(real_decomposition_sql):
        m = re.search(r"\[group:([^\]]+)\]", t.get("description", ""))
        if m:
            groups.add(m.group(1))
    assert len(groups) >= 2, (
        f"Only {len(groups)} distinct group(s) found: {groups}. "
        "A sequential learning goal needs multiple dependency groups."
    )


# T-D12
@pytest.mark.integration
def test_d12_sql_complexity_values_valid(real_decomposition_sql):
    """All [complexity:…] values must be 'low', 'medium', or 'high'."""
    allowed = {"low", "medium", "high"}
    for i, t in enumerate(_subtasks(real_decomposition_sql), 1):
        m = re.search(r"\[complexity:([^\]]+)\]", t.get("description", ""))
        if m:
            val = m.group(1).strip()
            assert val in allowed, f"Subtask {i} has unknown complexity value: {val!r}"


# T-D13
@pytest.mark.integration
def test_d13_sql_at_least_one_nontrivial_task(real_decomposition_sql):
    """A non-trivial goal should have at least one medium/high-complexity task."""
    descs = [t["description"] for t in _subtasks(real_decomposition_sql)]
    nontrivial = [d for d in descs if "[complexity:medium]" in d or "[complexity:high]" in d]
    assert nontrivial, "All tasks tagged [complexity:low] for a multi-day learning goal is suspicious."


# T-D14
@pytest.mark.integration
def test_d14_sql_total_duration_is_positive(real_decomposition_sql):
    total = sum(t["duration_minutes"] for t in _subtasks(real_decomposition_sql))
    assert total > 0


# T-D15
@pytest.mark.integration
def test_d15_sql_no_empty_descriptions(real_decomposition_sql):
    for i, t in enumerate(_subtasks(real_decomposition_sql), 1):
        assert t.get("description", "").strip(), f"Subtask {i} has empty description"


# ===========================================================================
# GOAL B — "Write and deliver a 10-minute conference talk"  (T-D16–T-D30)
# ===========================================================================

# T-D16
@pytest.mark.integration
def test_d16_talk_result_has_subtasks_key(real_decomposition_talk):
    assert "subtasks" in real_decomposition_talk


# T-D17
@pytest.mark.integration
def test_d17_talk_subtasks_is_nonempty_list(real_decomposition_talk):
    tasks = _subtasks(real_decomposition_talk)
    assert isinstance(tasks, list) and len(tasks) > 0


# T-D18
@pytest.mark.integration
def test_d18_talk_subtask_count_in_range(real_decomposition_talk):
    n = len(_subtasks(real_decomposition_talk))
    assert 3 <= n <= 12, f"Prompt asks for 3–12 subtasks; LLM returned {n}"


# T-D19
@pytest.mark.integration
def test_d19_talk_all_names_nonempty_strings(real_decomposition_talk):
    for i, t in enumerate(_subtasks(real_decomposition_talk), 1):
        name = t.get("name")
        assert isinstance(name, str) and name.strip(), f"Subtask {i} invalid name: {name!r}"


# T-D20
@pytest.mark.integration
def test_d20_talk_all_descriptions_are_strings(real_decomposition_talk):
    for i, t in enumerate(_subtasks(real_decomposition_talk), 1):
        desc = t.get("description")
        assert isinstance(desc, str), f"Subtask {i} description is not a string: {desc!r}"


# T-D21
@pytest.mark.integration
def test_d21_talk_durations_valid(real_decomposition_talk):
    for i, t in enumerate(_subtasks(real_decomposition_talk), 1):
        dur = t.get("duration_minutes")
        assert isinstance(dur, int) and 0 < dur <= _MAX_SESSION, (
            f"Subtask {i} duration {dur!r} must be int in (0, {_MAX_SESSION}]"
        )


# T-D22
@pytest.mark.integration
def test_d22_talk_at_least_one_group_tag(real_decomposition_talk):
    descs = [t["description"] for t in _subtasks(real_decomposition_talk)]
    assert any("[group:" in d for d in descs)


# T-D23
@pytest.mark.integration
def test_d23_talk_at_least_one_complexity_tag(real_decomposition_talk):
    descs = [t["description"] for t in _subtasks(real_decomposition_talk)]
    assert any("[complexity:" in d for d in descs)


# T-D24
@pytest.mark.integration
def test_d24_talk_at_least_one_shuffle_tag(real_decomposition_talk):
    descs = [t["description"] for t in _subtasks(real_decomposition_talk)]
    assert any("[shuffle:" in d for d in descs)


# T-D25
@pytest.mark.integration
def test_d25_talk_all_task_names_unique(real_decomposition_talk):
    names = [t["name"] for t in _subtasks(real_decomposition_talk)]
    assert len(names) == len(set(names)), (
        f"Duplicate task names: {[n for n in names if names.count(n) > 1]}"
    )


# T-D26
@pytest.mark.integration
def test_d26_talk_at_least_two_distinct_groups(real_decomposition_talk):
    groups = set()
    for t in _subtasks(real_decomposition_talk):
        m = re.search(r"\[group:([^\]]+)\]", t.get("description", ""))
        if m:
            groups.add(m.group(1))
    assert len(groups) >= 2, (
        f"Only {len(groups)} distinct group(s): {groups}. "
        "A talk has research → outline → slides → practice phases."
    )


# T-D27
@pytest.mark.integration
def test_d27_talk_complexity_values_valid(real_decomposition_talk):
    allowed = {"low", "medium", "high"}
    for i, t in enumerate(_subtasks(real_decomposition_talk), 1):
        m = re.search(r"\[complexity:([^\]]+)\]", t.get("description", ""))
        if m:
            val = m.group(1).strip()
            assert val in allowed, f"Subtask {i} has unknown complexity value: {val!r}"


# T-D28
@pytest.mark.integration
def test_d28_talk_at_least_one_nontrivial_task(real_decomposition_talk):
    descs = [t["description"] for t in _subtasks(real_decomposition_talk)]
    nontrivial = [d for d in descs if "[complexity:medium]" in d or "[complexity:high]" in d]
    assert nontrivial, "All tasks tagged [complexity:low] for a conference talk goal is suspicious."


# T-D29
@pytest.mark.integration
def test_d29_talk_total_duration_is_positive(real_decomposition_talk):
    total = sum(t["duration_minutes"] for t in _subtasks(real_decomposition_talk))
    assert total > 0


# T-D30
@pytest.mark.integration
def test_d30_talk_no_empty_descriptions(real_decomposition_talk):
    for i, t in enumerate(_subtasks(real_decomposition_talk), 1):
        assert t.get("description", "").strip(), f"Subtask {i} has empty description"
