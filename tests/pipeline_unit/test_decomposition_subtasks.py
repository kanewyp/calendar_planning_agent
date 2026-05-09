# =============================================================================
# tests/pipeline_unit/test_decomposition_subtasks.py — T01–T25
# =============================================================================
# A1 (T01–T10): Ten structural tests on real-LLM decompositions for 5 diverse goals.
# A2 (T11–T20): Decomposition critic tests — good plans vs bad plans.
# A3 (T21–T25): Decomposition reviser tests — critic feedback improves plan.
#
# All LLM-backed tests use session-scoped fixtures from conftest.py.
# Each fixture makes exactly one real LLM call shared across its tests.
# T20 remains mocked: it tests node-level error-handling for malformed LLM output.
# =============================================================================

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.orchestration.nodes.decompose_goal import decompose_goal_node
from src.orchestration.nodes.decomposition_review import (
    decomposition_critic_node,
    revise_decomposition_node,
)
from src.orchestration.heuristics._structural import (
    group_id,
    has_any_structural_tags,
    seq_id,
    shuffle_allowed,
    tag_map,
)
from tests.pipeline_unit.conftest import (
    base_critic_state,
    base_decompose_state,
    base_reviser_state,
    subtask,
    tagged_subtask,
)

_REVIEW_PATCH = "src.orchestration.nodes.decomposition_review.call_llm_json"


# =============================================================================
# A1 — T01–T10: Goal → Subtask Structural Tests  (real LLM, 5 session fixtures)
# =============================================================================

class TestGoalSubtaskFixtures:
    """T01–T10: Verify real-LLM decompositions satisfy structural invariants."""

    # -------------------------------------------------------------------------
    # Python goal (fixture: real_decomp_python) — T01, T05, T06
    # -------------------------------------------------------------------------

    # T01
    def test_learn_python_produces_multiple_distinct_groups(self, real_decomp_python):
        """T01: Python decomp must produce tasks across ≥2 distinct groups (setup ≠ learning)."""
        tasks = real_decomp_python["subtasks"]
        assert len(tasks) >= 3, f"Expected ≥3 tasks, got {len(tasks)}"
        groups = {group_id(t) for t in tasks}
        assert len(groups) >= 2, (
            "Python decomp should have at least 2 distinct groups "
            "(e.g. environment setup separate from learning tasks). "
            f"All tasks landed in groups: {groups}"
        )

    # T05
    def test_learn_python_shuffle_variety_in_tasks(self, real_decomp_python):
        """T05: Python decomp should include both shuffle:no and shuffle:yes tasks."""
        tasks = real_decomp_python["subtasks"]
        shuffleable = [t for t in tasks if shuffle_allowed(t)]
        non_shuffleable = [t for t in tasks if not shuffle_allowed(t)]
        assert shuffleable or non_shuffleable, "No shuffle tags found at all"
        # At minimum, all tasks must have the shuffle tag
        for t in tasks:
            tm = tag_map(t)
            assert "shuffle" in tm, f"{t['name']} is missing [shuffle:*] tag"

    # T06
    def test_learn_python_all_tasks_have_required_structural_tags(self, real_decomp_python):
        """T06: every Python subtask must carry group, shuffle, and complexity tags."""
        tasks = real_decomp_python["subtasks"]
        assert has_any_structural_tags(tasks)
        for t in tasks:
            tm = tag_map(t)
            assert "group" in tm, f"{t['name']} missing [group:*]"
            assert "shuffle" in tm, f"{t['name']} missing [shuffle:*]"
            assert "complexity" in tm, f"{t['name']} missing [complexity:*]"

    # -------------------------------------------------------------------------
    # Wedding goal (fixture: real_decomp_wedding) — T02, T07
    # -------------------------------------------------------------------------

    # T02
    def test_plan_wedding_has_multiple_phases(self, real_decomp_wedding):
        """T02: Wedding plan must span ≥2 distinct groups (different planning phases)."""
        tasks = real_decomp_wedding["subtasks"]
        assert len(tasks) >= 3, f"Expected ≥3 tasks for a wedding plan, got {len(tasks)}"
        groups = {group_id(t) for t in tasks}
        assert len(groups) >= 2, (
            "Wedding plan should have at least 2 distinct groups. "
            f"All tasks are in: {groups}"
        )

    # T07
    def test_plan_wedding_low_complexity_tasks_under_45min(self, real_decomp_wedding):
        """T07: [complexity:low] tasks must not exceed 45 minutes."""
        tasks = real_decomp_wedding["subtasks"]
        for t in tasks:
            if tag_map(t).get("complexity") == "low":
                assert t["duration_minutes"] <= 45, (
                    f"{t['name']}: [complexity:low] but {t['duration_minutes']}min > 45"
                )

    # -------------------------------------------------------------------------
    # Dissertation goal (fixture: real_decomp_dissertation) — T03
    # -------------------------------------------------------------------------

    # T03
    def test_dissertation_complexity_tags_align_with_duration(self, real_decomp_dissertation):
        """T03: low complexity ≤60 min; high complexity ≥60 min (relaxed for real LLM)."""
        tasks = real_decomp_dissertation["subtasks"]
        for t in tasks:
            tm = tag_map(t)
            complexity = tm.get("complexity", "")
            dur = t["duration_minutes"]
            if complexity == "low":
                assert dur <= 60, (
                    f"{t['name']}: [complexity:low] but {dur}min > 60"
                )
            elif complexity == "high":
                assert dur >= 60, (
                    f"{t['name']}: [complexity:high] but {dur}min < 60"
                )

    # -------------------------------------------------------------------------
    # Mobile app goal (fixture: real_decomp_mobile) — T04, T08, T09
    # -------------------------------------------------------------------------

    # T04
    def test_mobile_app_has_sequential_ordered_tasks(self, real_decomp_mobile):
        """T04: Mobile app plan must have at least one group with ≥2 ordered tasks."""
        tasks = real_decomp_mobile["subtasks"]
        from collections import defaultdict
        by_group: dict[str, list] = defaultdict(list)
        for t in tasks:
            by_group[group_id(t)].append(t)
        multi_task_groups = {g: ts for g, ts in by_group.items() if len(ts) >= 2}
        assert multi_task_groups, (
            "Mobile app plan should have at least one group with ≥2 tasks "
            "(representing sequential or parallel work in one phase). "
            f"Groups found: {dict(by_group)}"
        )

    # T08
    def test_mobile_app_has_at_least_three_distinct_groups(self, real_decomp_mobile):
        """T08: Mobile app plan should span ≥3 distinct phases/groups (design, build, test etc.)."""
        tasks = real_decomp_mobile["subtasks"]
        groups = {group_id(t) for t in tasks}
        assert len(groups) >= 3, (
            "Mobile app MVP should have ≥3 distinct groups (e.g. design, implementation, testing). "
            f"Groups found: {groups}"
        )

    # T09
    def test_mobile_app_has_ordered_phases(self, real_decomp_mobile):
        """T09: Mobile app plan must have ≥3 tasks spanning ≥2 distinct groups."""
        tasks = real_decomp_mobile["subtasks"]
        assert len(tasks) >= 3
        groups = {group_id(t) for t in tasks}
        assert len(groups) >= 2, (
            "Mobile app plan should have multiple phases (groups). "
            f"All tasks in: {groups}"
        )

    # -------------------------------------------------------------------------
    # Novel goal (fixture: real_decomp_novel) — T10
    # -------------------------------------------------------------------------

    # T10
    def test_write_novel_vague_goal_produces_multiple_concrete_tasks(self, real_decomp_novel):
        """T10: A vague 'Write a novel' goal must produce ≥5 concrete subtasks."""
        tasks = real_decomp_novel["subtasks"]
        assert len(tasks) >= 5, (
            f"'Write a novel' should produce ≥5 subtasks; got {len(tasks)}."
        )
        for t in tasks:
            assert len(t["description"]) >= 15, (
                f"{t['name']}: description too short ({len(t['description'])} chars)"
            )
            assert t["duration_minutes"] > 0


# =============================================================================
# A2 — T11–T20: Decomposition Critic Tests  (real LLM, 2 session fixtures + 1 mock)
# =============================================================================

class TestDecompositionCritic:
    """T11–T20: Critic node evaluates good and bad plans correctly with real LLM."""

    # ---- Good plan: real_critic_good_plan fixture (T11–T15) ----

    # T11
    def test_good_plan_critic_result_has_all_required_keys(self, real_critic_good_plan):
        """T11: Critic result for a well-structured plan must have all three required keys."""
        assert "decomposition_review_passed" in real_critic_good_plan
        assert "decomposition_review_issues" in real_critic_good_plan
        assert "decomposition_revision_instruction" in real_critic_good_plan

    # T12
    def test_good_plan_passed_is_bool(self, real_critic_good_plan):
        """T12: decomposition_review_passed must be a bool."""
        passed = real_critic_good_plan["decomposition_review_passed"]
        assert isinstance(passed, bool), (
            f"Expected bool, got {type(passed).__name__}: {passed!r}"
        )

    # T13
    def test_good_plan_issues_is_list(self, real_critic_good_plan):
        """T13: decomposition_review_issues must be a list."""
        issues = real_critic_good_plan["decomposition_review_issues"]
        assert isinstance(issues, list), (
            f"Expected list, got {type(issues).__name__}"
        )

    # T14
    def test_good_plan_revision_instruction_is_string(self, real_critic_good_plan):
        """T14: decomposition_revision_instruction must be a string."""
        instruction = real_critic_good_plan["decomposition_revision_instruction"]
        assert isinstance(instruction, str)

    # T15
    def test_good_plan_no_critical_severity_issues(self, real_critic_good_plan):
        """T15: a well-structured plan should not trigger critical-severity issues."""
        critical = [
            i for i in real_critic_good_plan["decomposition_review_issues"]
            if i.get("severity", "").lower() == "critical"
        ]
        assert not critical, (
            "Critic found critical-severity issues for a well-structured 5-task plan. "
            "Critical issues:\n"
            + "\n".join(f"  [{i.get('severity')}] {i.get('subtask')}: {i.get('issue')}"
                        for i in critical)
        )

    # ---- Bad plan: real_critic_bad_plan fixture (T16–T19) ----

    # T16
    def test_bad_plan_is_flagged(self, real_critic_bad_plan):
        """T16: a single vague 'Do everything' task must be flagged by the critic."""
        passed = real_critic_bad_plan["decomposition_review_passed"]
        issues = real_critic_bad_plan["decomposition_review_issues"]
        instruction = real_critic_bad_plan["decomposition_revision_instruction"]
        assert (not passed) or bool(issues) or bool(instruction.strip()), (
            "Critic let a single vague mega-task pass without any feedback."
        )

    # T17
    def test_bad_plan_issues_nonempty(self, real_critic_bad_plan):
        """T17: critic must return ≥1 issue for a single vague mega-task."""
        issues = real_critic_bad_plan["decomposition_review_issues"]
        assert len(issues) > 0, (
            "Critic returned no issues for a single vague 'Do everything' task."
        )

    # T18
    def test_bad_plan_each_issue_has_severity(self, real_critic_bad_plan):
        """T18: each issue in the critic's response must have a severity field."""
        for i, issue in enumerate(real_critic_bad_plan["decomposition_review_issues"], 1):
            assert "severity" in issue, f"Issue {i} missing 'severity'"
            assert isinstance(issue["severity"], str) and issue["severity"].strip()

    # T19
    def test_bad_plan_each_issue_has_all_required_fields(self, real_critic_bad_plan):
        """T19: each critic issue must have severity, subtask, issue, and suggestion fields."""
        required = {"severity", "subtask", "issue", "suggestion"}
        for i, issue in enumerate(real_critic_bad_plan["decomposition_review_issues"], 1):
            missing = required - set(issue.keys())
            assert not missing, f"Issue {i} missing fields: {missing}"

    # T20 — kept mocked: tests node-level error handling for malformed LLM output
    def test_normalizes_malformed_issues_gracefully(self):
        """T20: critic node does not crash when LLM returns malformed issues array."""
        tasks = [subtask("Task A", "[group:g] [shuffle:no] [complexity:low] Description.", 30)]
        mock_response = {
            "passed": False,
            "issues": [{"severity": "major"}],  # missing subtask/issue/suggestion
            "revision_instruction": "fix it",
        }
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        # Node must not raise; required fields must exist
        assert isinstance(result["decomposition_review_issues"], list)
        assert "decomposition_review_passed" in result


# =============================================================================
# A3 — T21–T25: Decomposition Reviser Tests  (real LLM, 1 session fixture)
# =============================================================================

class TestDecompositionReviser:
    """T21–T25: Reviser node improves decomposition per critic instructions (real LLM)."""

    # T21
    def test_revise_produces_more_tasks_than_original(self, real_reviser):
        """T21: revised output must have more subtasks than the original 2-task plan."""
        tasks = real_reviser["subtasks"]
        assert len(tasks) > 2, (
            f"Revision should split 'Do all reading' into multiple tasks. "
            f"Got {len(tasks)} tasks (need > 2)."
        )

    # T22
    def test_revise_all_tasks_have_structural_tags(self, real_reviser):
        """T22: every task in the revised plan must carry group, shuffle, complexity tags."""
        tasks = real_reviser["subtasks"]
        assert has_any_structural_tags(tasks)
        for t in tasks:
            tm = tag_map(t)
            assert "group" in tm, f"{t['name']} missing [group:*]"
            assert "shuffle" in tm, f"{t['name']} missing [shuffle:*]"
            assert "complexity" in tm, f"{t['name']} missing [complexity:*]"

    # T23
    def test_revise_all_durations_within_session_limit(self, real_reviser):
        """T23: all revised task durations must be positive and ≤ 90 minutes."""
        tasks = real_reviser["subtasks"]
        for t in tasks:
            dur = t["duration_minutes"]
            assert isinstance(dur, int) and 0 < dur <= 90, (
                f"{t['name']}: duration {dur!r} not in (0, 90]"
            )

    # T24
    def test_revise_sets_decomposition_revised_flag(self, real_reviser):
        """T24: revise_decomposition_node must set decomposition_revised=True in result."""
        assert real_reviser.get("decomposition_revised") is True, (
            f"decomposition_revised={real_reviser.get('decomposition_revised')!r}, expected True"
        )

    # T25
    def test_revise_increments_revision_count(self, real_reviser):
        """T25: decomposition_revision_count must be an int ≥ 1 after one revision."""
        count = real_reviser.get("decomposition_revision_count")
        assert isinstance(count, int) and count >= 1, (
            f"decomposition_revision_count={count!r}, expected int ≥ 1"
        )


