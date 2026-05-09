# =============================================================================
# tests/llm_integration/test_critic_real.py — Real-LLM decomposition critic tests
# =============================================================================
# Three scenarios, each with its own session-scoped fixture (one LLM call each):
#
#   Good path (T-C01–T-C12)   — worked-example plan; issues should be advisory only
#   Flawed: vague mega-task    (T-C13–T-C21) — one-line "Do everything" task
#   Flawed: wrong group order  (T-C22–T-C29) — sequential tasks sharing one group
# =============================================================================

from __future__ import annotations

import pytest

from src.orchestration.nodes.decomposition_review import decomposition_critic_node


# ---------------------------------------------------------------------------
# Good-path subtasks: the DECOMPOSITION_PROMPT's own worked-example plan
# ---------------------------------------------------------------------------

_WORKED_EXAMPLE_SUBTASKS = [
    {"name": "Install Python and IDE", "description": "[group:environment] [shuffle:no] [complexity:low] Install Python 3.x and set up VS Code with the Python extension.", "duration_minutes": 30},
    {"name": "First program", "description": "[group:first_program] [shuffle:no] [complexity:low] Write and run a hello-world script to verify the toolchain works.", "duration_minutes": 20},
    {"name": "Variables and types", "description": "[group:basics] [shuffle:no] [complexity:medium] Read about variables, primitive types, and assignment with small exercises.", "duration_minutes": 50},
    {"name": "Lists", "description": "[group:data_structures] [shuffle:yes] [complexity:medium] Practice list creation, indexing, and common methods.", "duration_minutes": 50},
    {"name": "Tuples", "description": "[group:data_structures] [shuffle:yes] [complexity:medium] Practice tuple operations and immutability.", "duration_minutes": 45},
    {"name": "Dictionaries", "description": "[group:data_structures] [shuffle:yes] [complexity:medium] Practice dict creation, lookup, and iteration.", "duration_minutes": 60},
    {"name": "Loops", "description": "[group:control_flow] [shuffle:no] [complexity:medium] for/while loops and their use with collections.", "duration_minutes": 60},
    {"name": "Functions", "description": "[group:functions] [shuffle:no] [complexity:high] Define functions, parameters, return values, and scope.", "duration_minutes": 90},
    {"name": "Mini project: todo CLI", "description": "[group:capstone] [shuffle:no] [complexity:high] Build a small command-line todo app integrating dicts, loops, and functions.", "duration_minutes": 120},
]

# ---------------------------------------------------------------------------
# Flawed scenario A: single vague mega-task
# ---------------------------------------------------------------------------

_FLAWED_MEGA_SUBTASKS = [
    {
        "name": "Do everything",
        "description": (
            "[group:work] [shuffle:no] [complexity:high] "
            "Research, outline, write, revise, and submit the full paper."
        ),
        "duration_minutes": 90,
    },
]

# ---------------------------------------------------------------------------
# Flawed scenario B: sequential tasks jammed into one shuffle:yes group
# (designing, building, testing, and releasing — all marked as interchangeable)
# ---------------------------------------------------------------------------

_FLAWED_GROUPS_SUBTASKS = [
    {"name": "Design UI mockups", "description": "[group:all_work] [shuffle:yes] [complexity:medium] Create wireframes for all screens.", "duration_minutes": 60},
    {"name": "Implement frontend screens", "description": "[group:all_work] [shuffle:yes] [complexity:high] Build the UI based on mockups.", "duration_minutes": 90},
    {"name": "Build backend API", "description": "[group:all_work] [shuffle:yes] [complexity:high] Implement REST endpoints used by the frontend.", "duration_minutes": 90},
    {"name": "Write automated tests", "description": "[group:all_work] [shuffle:yes] [complexity:medium] Test frontend and backend together.", "duration_minutes": 60},
    {"name": "Submit to App Store", "description": "[group:all_work] [shuffle:yes] [complexity:low] Package and submit the finished app.", "duration_minutes": 30},
]


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_critic_good(requires_real_llm):
    return decomposition_critic_node({
        "goal": "Learn Python basics in 2 weeks",
        "deadline": "2026-12-14",
        "context": "Complete beginner, 1-2 hours available each day",
        "max_session_minutes": 120,
        "subtasks": _WORKED_EXAMPLE_SUBTASKS,
    })


@pytest.fixture(scope="session")
def real_critic_flawed_mega(requires_real_llm):
    return decomposition_critic_node({
        "goal": "Write a research paper on climate change",
        "deadline": "2026-12-31",
        "context": "Academic writing, need peer-reviewed sources",
        "max_session_minutes": 90,
        "subtasks": _FLAWED_MEGA_SUBTASKS,
    })


@pytest.fixture(scope="session")
def real_critic_flawed_groups(requires_real_llm):
    return decomposition_critic_node({
        "goal": "Build and deploy a mobile app to the App Store",
        "deadline": "2026-12-31",
        "context": "Solo developer, first mobile app project",
        "max_session_minutes": 90,
        "subtasks": _FLAWED_GROUPS_SUBTASKS,
    })


# ===========================================================================
# GOOD PATH — worked-example plan  (T-C01–T-C12)
# ===========================================================================

# T-C01
@pytest.mark.integration
def test_c01_good_has_passed_key(real_critic_good):
    assert "decomposition_review_passed" in real_critic_good


# T-C02
@pytest.mark.integration
def test_c02_good_passed_is_bool(real_critic_good):
    passed = real_critic_good["decomposition_review_passed"]
    assert isinstance(passed, bool), f"Expected bool, got {type(passed).__name__}: {passed!r}"


# T-C03
@pytest.mark.integration
def test_c03_good_has_issues_key(real_critic_good):
    assert "decomposition_review_issues" in real_critic_good


# T-C04
@pytest.mark.integration
def test_c04_good_issues_is_list(real_critic_good):
    issues = real_critic_good["decomposition_review_issues"]
    assert isinstance(issues, list), f"Expected list, got {type(issues).__name__}"


# T-C05
@pytest.mark.integration
def test_c05_good_has_revision_instruction_key(real_critic_good):
    assert "decomposition_revision_instruction" in real_critic_good


# T-C06
@pytest.mark.integration
def test_c06_good_revision_instruction_is_string(real_critic_good):
    instruction = real_critic_good["decomposition_revision_instruction"]
    assert isinstance(instruction, str)


# T-C07
@pytest.mark.integration
def test_c07_good_issues_are_advisory_only(real_critic_good):
    """For the prompt's own worked-example plan, no issue should be 'critical' severity."""
    critical = [
        i for i in real_critic_good["decomposition_review_issues"]
        if i.get("severity", "").lower() == "critical"
    ]
    assert not critical, (
        "Critic found critical issues in the prompt's own worked-example plan. "
        "Critical issues:\n"
        + "\n".join(f"  {i.get('subtask')}: {i.get('issue')}" for i in critical)
    )


# T-C08
@pytest.mark.integration
def test_c08_good_each_issue_has_severity(real_critic_good):
    for i, issue in enumerate(real_critic_good["decomposition_review_issues"], 1):
        assert "severity" in issue, f"Issue {i} missing 'severity' field"
        assert isinstance(issue["severity"], str) and issue["severity"].strip()


# T-C09
@pytest.mark.integration
def test_c09_good_each_issue_has_subtask(real_critic_good):
    for i, issue in enumerate(real_critic_good["decomposition_review_issues"], 1):
        assert "subtask" in issue, f"Issue {i} missing 'subtask' field"


# T-C10
@pytest.mark.integration
def test_c10_good_each_issue_has_issue_field(real_critic_good):
    for i, issue in enumerate(real_critic_good["decomposition_review_issues"], 1):
        assert "issue" in issue, f"Issue {i} missing 'issue' field"
        assert isinstance(issue["issue"], str) and issue["issue"].strip()


# T-C11
@pytest.mark.integration
def test_c11_good_each_issue_has_suggestion(real_critic_good):
    for i, issue in enumerate(real_critic_good["decomposition_review_issues"], 1):
        assert "suggestion" in issue, f"Issue {i} missing 'suggestion' field"


# T-C12
@pytest.mark.integration
def test_c12_good_revision_instruction_not_excessively_long(real_critic_good):
    """revision_instruction is described as 'concise'. Anything over 1000 chars is suspicious."""
    instruction = real_critic_good["decomposition_revision_instruction"]
    assert len(instruction) <= 1000, (
        f"revision_instruction is {len(instruction)} chars — "
        "likely the LLM wrote a full plan instead of a concise instruction."
    )


# ===========================================================================
# FLAWED PATH A — single vague mega-task  (T-C13–T-C21)
# ===========================================================================

# T-C13
@pytest.mark.integration
def test_c13_mega_has_passed_key(real_critic_flawed_mega):
    assert "decomposition_review_passed" in real_critic_flawed_mega


# T-C14
@pytest.mark.integration
def test_c14_mega_has_issues_key(real_critic_flawed_mega):
    assert "decomposition_review_issues" in real_critic_flawed_mega


# T-C15
@pytest.mark.integration
def test_c15_mega_has_revision_instruction_key(real_critic_flawed_mega):
    assert "decomposition_revision_instruction" in real_critic_flawed_mega


# T-C16
@pytest.mark.integration
def test_c16_mega_critic_flags_vague_task(real_critic_flawed_mega):
    """A single "Do everything" task must be flagged in some way."""
    passed = real_critic_flawed_mega["decomposition_review_passed"]
    issues = real_critic_flawed_mega["decomposition_review_issues"]
    instruction = real_critic_flawed_mega["decomposition_revision_instruction"]
    assert (not passed) or bool(issues) or bool(instruction.strip()), (
        "Critic let a single vague 'Do everything' task pass without any feedback."
    )


# T-C17
@pytest.mark.integration
def test_c17_mega_issues_nonempty(real_critic_flawed_mega):
    issues = real_critic_flawed_mega["decomposition_review_issues"]
    assert len(issues) > 0, "Critic found no issues for a single vague task covering an entire project."


# T-C18
@pytest.mark.integration
def test_c18_mega_revision_instruction_nonempty(real_critic_flawed_mega):
    instruction = real_critic_flawed_mega["decomposition_revision_instruction"]
    assert instruction.strip(), "revision_instruction is empty for a clearly flawed plan."


# T-C19
@pytest.mark.integration
def test_c19_mega_each_issue_has_all_fields(real_critic_flawed_mega):
    required_fields = {"severity", "subtask", "issue", "suggestion"}
    for i, issue in enumerate(real_critic_flawed_mega["decomposition_review_issues"], 1):
        missing = required_fields - set(issue)
        assert not missing, f"Issue {i} missing fields: {missing}"


# T-C20
@pytest.mark.integration
def test_c20_mega_issue_descriptions_nonempty(real_critic_flawed_mega):
    for i, issue in enumerate(real_critic_flawed_mega["decomposition_review_issues"], 1):
        assert isinstance(issue.get("issue"), str) and issue["issue"].strip(), (
            f"Issue {i} has empty 'issue' description"
        )


# T-C21
@pytest.mark.integration
def test_c21_mega_suggestion_fields_are_strings(real_critic_flawed_mega):
    for i, issue in enumerate(real_critic_flawed_mega["decomposition_review_issues"], 1):
        assert isinstance(issue.get("suggestion"), str), (
            f"Issue {i} 'suggestion' is not a string"
        )


# ===========================================================================
# FLAWED PATH B — wrong group assignments  (T-C22–T-C29)
# ===========================================================================

# T-C22
@pytest.mark.integration
def test_c22_groups_has_passed_key(real_critic_flawed_groups):
    assert "decomposition_review_passed" in real_critic_flawed_groups


# T-C23
@pytest.mark.integration
def test_c23_groups_has_issues_key(real_critic_flawed_groups):
    assert "decomposition_review_issues" in real_critic_flawed_groups


# T-C24
@pytest.mark.integration
def test_c24_groups_has_revision_instruction_key(real_critic_flawed_groups):
    assert "decomposition_revision_instruction" in real_critic_flawed_groups


# T-C25
@pytest.mark.integration
def test_c25_groups_critic_flags_bad_ordering(real_critic_flawed_groups):
    """All sequential tasks in one shuffle:yes group should be flagged."""
    passed = real_critic_flawed_groups["decomposition_review_passed"]
    issues = real_critic_flawed_groups["decomposition_review_issues"]
    instruction = real_critic_flawed_groups["decomposition_revision_instruction"]
    assert (not passed) or bool(issues) or bool(instruction.strip()), (
        "Critic passed sequential design→build→test→ship tasks all in one shuffle:yes group."
    )


# T-C26
@pytest.mark.integration
def test_c26_groups_issues_nonempty(real_critic_flawed_groups):
    issues = real_critic_flawed_groups["decomposition_review_issues"]
    assert len(issues) > 0, (
        "Critic found no issues for a plan where design, implementation, testing, "
        "and App Store submission are all in the same shuffle:yes group."
    )


# T-C27
@pytest.mark.integration
def test_c27_groups_each_issue_has_all_fields(real_critic_flawed_groups):
    required_fields = {"severity", "subtask", "issue", "suggestion"}
    for i, issue in enumerate(real_critic_flawed_groups["decomposition_review_issues"], 1):
        missing = required_fields - set(issue)
        assert not missing, f"Issue {i} missing fields: {missing}"


# T-C28
@pytest.mark.integration
def test_c28_groups_passed_is_false(real_critic_flawed_groups):
    """A plan where submission comes before design (shuffle:yes) must fail the critic."""
    passed = real_critic_flawed_groups["decomposition_review_passed"]
    assert not passed, (
        "Critic passed a plan where App Store submission is shuffleable with design mockups. "
        "This plan has obvious sequential dependencies that shuffle:yes would break."
    )


# T-C29
@pytest.mark.integration
def test_c29_groups_revision_instruction_nonempty(real_critic_flawed_groups):
    instruction = real_critic_flawed_groups["decomposition_revision_instruction"]
    assert instruction.strip(), "revision_instruction empty for a plan with wrong group assignments."
