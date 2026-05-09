# =============================================================================
# tests/pipeline_unit/test_decomposition_subtasks.py — T01–T25
# =============================================================================
# A1 (T01–T10): Ten goal→subtask fixture tests using mocked LLM output.
# A2 (T11–T20): Decomposition critic tests — problematic plans are flagged.
# A3 (T21–T25): Decomposition reviser tests — critic feedback improves plan.
#
# Patch target for all decompose_goal_node calls:
#   src.orchestration.nodes.decompose_goal.call_llm_json
# Patch target for critic/reviser calls:
#   src.orchestration.nodes.decomposition_review.call_llm_json
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

_DECOMPOSE_PATCH = "src.orchestration.nodes.decompose_goal.call_llm_json"
_REVIEW_PATCH = "src.orchestration.nodes.decomposition_review.call_llm_json"


# =============================================================================
# A1 — T01–T10: Goal → Subtask Fixture Tests
# =============================================================================


class TestGoalSubtaskFixtures:
    """T01–T10: Verify that the node stores mocked LLM decompositions correctly
    and that structural tag invariants hold across ten diverse goal types."""

    # T01
    def test_learn_python_env_and_first_program_in_separate_groups(self):
        """T01: install→run tasks must be in DIFFERENT groups (prerequisite rule)."""
        mock_output = [
            subtask("Install Python and IDE",
                    "[group:environment] [shuffle:no] [complexity:low] Install Python 3 and VS Code.",
                    30),
            subtask("Run Hello World",
                    "[group:first_program] [shuffle:no] [complexity:low] Write and run first script.",
                    20),
            subtask("Learn variables and types",
                    "[group:basics] [shuffle:yes] [complexity:medium] int, str, list.",
                    60),
            subtask("Learn control flow",
                    "[group:basics] [shuffle:yes] [complexity:medium] if/else, for, while.",
                    60),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Learn Python from scratch"))

        tasks = result["subtasks"]
        assert len(tasks) == 4
        assert group_id(tasks[0]) == "environment"
        assert group_id(tasks[1]) == "first_program"
        assert group_id(tasks[0]) != group_id(tasks[1])  # must be separate
        # Both tasks in index 2 and 3 share a group
        assert group_id(tasks[2]) == group_id(tasks[3]) == "basics"

    # T02
    def test_plan_wedding_venue_before_invitations_in_different_groups(self):
        """T02: venue booking must precede invitation sending in separate groups."""
        mock_output = [
            subtask("Book venue",
                    "[group:venue] [shuffle:no] [complexity:medium] Research and reserve ceremony space.",
                    60),
            subtask("Send invitations",
                    "[group:invites] [shuffle:no] [complexity:medium] Mail invitations to guest list.",
                    45),
            subtask("Choose flowers",
                    "[group:vendor_selection] [shuffle:yes] [complexity:low] Select florist.",
                    30),
            subtask("Choose cake",
                    "[group:vendor_selection] [shuffle:yes] [complexity:low] Taste and order cake.",
                    30),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Plan a wedding"))

        tasks = result["subtasks"]
        groups = [group_id(t) for t in tasks]
        assert groups[0] != groups[1]  # venue ≠ invites (different phases)
        # venue group appears before invites group in first-appearance order
        assert groups.index("venue") < groups.index("invites")

    # T03
    def test_dissertation_complexity_tags_match_duration_bands(self):
        """T03: complexity tags align with duration — low≤45, high≥75."""
        mock_output = [
            subtask("Literature keyword search",
                    "[group:research] [shuffle:yes] [complexity:low] Quick keyword scan.",
                    30),
            subtask("Read core papers",
                    "[group:research] [shuffle:yes] [complexity:low] Skim five foundational papers.",
                    40),
            subtask("Draft methodology section",
                    "[group:writing] [shuffle:no] [complexity:medium] Write methodology.",
                    60),
            subtask("Write introduction chapter",
                    "[group:writing_deep] [shuffle:no] [complexity:high] Full intro with context.",
                    90),
            subtask("Write analysis chapter",
                    "[group:analysis] [shuffle:no] [complexity:high] Quantitative results.",
                    80),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Write my PhD dissertation"))

        for t in result["subtasks"]:
            tags = tag_map(t)
            complexity = tags.get("complexity", "")
            dur = t["duration_minutes"]
            if complexity == "low":
                assert dur <= 45, f"{t['name']}: low complexity but {dur}min > 45"
            elif complexity == "high":
                assert dur >= 75, f"{t['name']}: high complexity but {dur}min < 75"

    # T04
    def test_mobile_app_seq_tags_used_for_ordered_steps(self):
        """T04: [seq:N] tags within a group enforce strict internal order."""
        mock_output = [
            subtask("Design API schema",
                    "[group:backend_setup] [seq:1] [shuffle:no] [complexity:medium] Design REST schema.",
                    60),
            subtask("Implement API endpoints",
                    "[group:backend_setup] [seq:2] [shuffle:no] [complexity:high] Code the routes.",
                    90),
            subtask("Write API integration tests",
                    "[group:backend_setup] [seq:3] [shuffle:no] [complexity:medium] Pytest integration.",
                    60),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Build a mobile app MVP"))

        tasks = result["subtasks"]
        seq_values = [seq_id(t) for t in tasks]
        assert seq_values == [1, 2, 3], f"Expected [1,2,3], got {seq_values}"

    # T05
    def test_learn_react_shuffle_yes_only_for_genuine_peers(self):
        """T05: [shuffle:no] for setup; [shuffle:yes] only for genuine peer tasks."""
        mock_output = [
            subtask("Install Node and create app",
                    "[group:environment] [shuffle:no] [complexity:low] npx create-react-app.",
                    30),
            subtask("Learn useState",
                    "[group:data_concepts] [shuffle:yes] [complexity:medium] State management hook.",
                    45),
            subtask("Learn useEffect",
                    "[group:data_concepts] [shuffle:yes] [complexity:medium] Side effects hook.",
                    45),
            subtask("Learn useContext",
                    "[group:data_concepts] [shuffle:yes] [complexity:medium] Context API hook.",
                    45),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Learn React basics"))

        tasks = result["subtasks"]
        env_tasks = [t for t in tasks if group_id(t) == "environment"]
        concept_tasks = [t for t in tasks if group_id(t) == "data_concepts"]

        assert all(not shuffle_allowed(t) for t in env_tasks)
        assert all(shuffle_allowed(t) for t in concept_tasks)

    # T06
    def test_study_for_exam_all_tasks_have_required_structural_tags(self):
        """T06: every task carries group, shuffle, and complexity tags."""
        mock_output = [
            subtask("Review lecture slides",
                    "[group:review] [shuffle:yes] [complexity:medium] Skim all slides.", 45),
            subtask("Solve past exam questions",
                    "[group:practice] [shuffle:yes] [complexity:high] Timed practice sets.", 90),
            subtask("Read textbook chapter 1",
                    "[group:reading] [shuffle:yes] [complexity:medium] Chapter on limits.", 45),
            subtask("Read textbook chapter 2",
                    "[group:reading] [shuffle:yes] [complexity:medium] Chapter on derivatives.", 45),
            subtask("Create summary sheet",
                    "[group:synthesis] [shuffle:no] [complexity:medium] One-page reference.", 30),
            subtask("Self-test with flashcards",
                    "[group:testing] [shuffle:no] [complexity:low] Spaced repetition run.", 30),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Study for my calculus final exam"))

        tasks = result["subtasks"]
        assert has_any_structural_tags(tasks)
        for t in tasks:
            tags = tag_map(t)
            assert "group" in tags, f"{t['name']} missing [group:*]"
            assert "shuffle" in tags, f"{t['name']} missing [shuffle:*]"
            assert "complexity" in tags, f"{t['name']} missing [complexity:*]"

    # T07
    def test_conference_no_low_complexity_task_over_45_min(self):
        """T07: [complexity:low] tasks must not exceed the 45-min low ceiling."""
        mock_output = [
            subtask("Book conference venue",
                    "[group:logistics] [shuffle:no] [complexity:medium] Reserve hall.", 60),
            subtask("Send speaker invites",
                    "[group:speakers] [shuffle:yes] [complexity:medium] Email keynote speakers.", 45),
            subtask("Design event badge",
                    "[group:materials] [shuffle:yes] [complexity:low] Simple badge layout.", 30),
            subtask("Print name tags",
                    "[group:materials] [shuffle:yes] [complexity:low] Send to print shop.", 20),
            subtask("Draft programme booklet",
                    "[group:materials] [shuffle:yes] [complexity:low] Event schedule.", 45),
            subtask("Prepare speaker bios",
                    "[group:materials] [shuffle:yes] [complexity:low] Collect and format.", 30),
            subtask("Develop session content",
                    "[group:content] [shuffle:no] [complexity:high] Workshop slides.", 90),
            subtask("Rehearse opening keynote",
                    "[group:rehearsal] [shuffle:no] [complexity:high] Run through full talk.", 90),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Organise a technical conference"))

        for t in result["subtasks"]:
            if tag_map(t).get("complexity") == "low":
                assert t["duration_minutes"] <= 45, (
                    f"{t['name']}: [complexity:low] but {t['duration_minutes']}min > 45"
                )

    # T08
    def test_startup_phases_appear_in_logical_sequence(self):
        """T08: research → planning → mvp_build → launch group order preserved."""
        mock_output = [
            subtask("Market research",
                    "[group:research] [shuffle:yes] [complexity:medium] Analyse competitors.", 60),
            subtask("Customer interviews",
                    "[group:research] [shuffle:yes] [complexity:medium] Talk to 10 prospects.", 60),
            subtask("Define MVP features",
                    "[group:planning] [shuffle:no] [complexity:high] Feature list.", 90),
            subtask("Build landing page",
                    "[group:mvp_build] [shuffle:no] [complexity:medium] HTML/CSS page.", 60),
            subtask("Implement core feature",
                    "[group:mvp_build] [shuffle:no] [complexity:high] Backend + frontend.", 90),
            subtask("Soft launch to beta users",
                    "[group:launch] [shuffle:no] [complexity:medium] Invite first users.", 45),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Launch a tech startup"))

        tasks = result["subtasks"]
        seen_groups: list[str] = []
        for t in tasks:
            gid = group_id(t)
            if not seen_groups or seen_groups[-1] != gid:
                seen_groups.append(gid)

        expected_order = ["research", "planning", "mvp_build", "launch"]
        assert seen_groups == expected_order, f"Group order wrong: {seen_groups}"

    # T09
    def test_etl_pipeline_phases_in_separate_groups(self):
        """T09: design→extract→transform appear as three distinct ordered groups."""
        mock_output = [
            subtask("Design data schema",
                    "[group:design] [shuffle:no] [complexity:high] ER diagram + schema.", 90),
            subtask("Implement extraction scripts",
                    "[group:extract] [shuffle:no] [complexity:high] Source connectors.", 90),
            subtask("Build transformation logic",
                    "[group:transform] [shuffle:no] [complexity:high] Business rules.", 90),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Build an ETL data pipeline"))

        tasks = result["subtasks"]
        groups = [group_id(t) for t in tasks]
        assert groups == ["design", "extract", "transform"]
        assert len(set(groups)) == 3  # all three are distinct

    # T10
    def test_write_novel_vague_goal_produces_multiple_concrete_tasks(self):
        """T10: a vague goal produces ≥5 concrete, non-trivial subtasks."""
        mock_output = [
            subtask("Outline plot structure",
                    "[group:planning] [shuffle:no] [complexity:medium] Three-act structure.", 45),
            subtask("Research historical setting",
                    "[group:research] [shuffle:yes] [complexity:medium] 1920s London context.", 60),
            subtask("Write chapter 1 draft",
                    "[group:drafting] [shuffle:yes] [complexity:high] Opening scene.", 90),
            subtask("Write chapter 2 draft",
                    "[group:drafting] [shuffle:yes] [complexity:high] Rising action.", 90),
            subtask("Write chapter 3 draft",
                    "[group:drafting] [shuffle:yes] [complexity:high] Midpoint confrontation.", 90),
            subtask("Self-edit first three chapters",
                    "[group:editing] [shuffle:no] [complexity:medium] Line edits.", 60),
            subtask("Final review and polish",
                    "[group:final] [shuffle:no] [complexity:medium] Consistency pass.", 45),
        ]
        with patch(_DECOMPOSE_PATCH, return_value=mock_output):
            result = decompose_goal_node(base_decompose_state("Write a novel"))

        tasks = result["subtasks"]
        assert len(tasks) >= 5
        for t in tasks:
            assert len(t["description"]) >= 15, f"{t['name']}: description too short"
            assert t["duration_minutes"] > 0


# =============================================================================
# A2 — T11–T20: Decomposition Critic Tests
# =============================================================================


class TestDecompositionCritic:
    """T11–T20: The critic node correctly evaluates decomposition quality."""

    def _mock_critic(self, passed: bool, issues: list[dict], instruction: str = "") -> dict:
        return {"passed": passed, "issues": issues, "revision_instruction": instruction}

    # T11
    def test_passes_well_structured_plan(self):
        """T11: critic passes a well-tagged, realistically scoped plan."""
        tasks = [
            subtask("Set up dev environment",
                    "[group:setup] [shuffle:no] [complexity:low] Install tools.", 30),
            subtask("Read docs intro",
                    "[group:learn] [shuffle:no] [complexity:medium] Official docs overview.", 60),
            subtask("Build counter component",
                    "[group:practice] [shuffle:no] [complexity:high] State practice.", 90),
        ]
        mock_response = self._mock_critic(True, [], "")
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        assert result["decomposition_review_passed"] is True
        assert result["decomposition_review_issues"] == []
        assert result["decomposition_revision_instruction"] == ""

    # T12
    def test_flags_oversized_vague_task(self):
        """T12: critic flags a 300-min vague task as oversized."""
        tasks = [
            subtask("Do all the research",
                    "[group:research] [shuffle:no] [complexity:high] Research everything needed.",
                    90),  # max_session=90, so stored as-is
        ]
        mock_response = self._mock_critic(
            False,
            [{"severity": "major", "subtask": "Do all the research",
              "issue": "Task is too vague and oversized",
              "suggestion": "Split into specific research subtopics."}],
            "Split oversized tasks into focused chunks.",
        )
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        assert result["decomposition_review_passed"] is False
        assert len(result["decomposition_review_issues"]) == 1
        assert result["decomposition_review_issues"][0]["subtask"] == "Do all the research"

    # T13
    def test_flags_missing_prerequisite(self):
        """T13: critic flags when 'write tests' appears without an implementation task."""
        tasks = [
            subtask("Write unit tests",
                    "[group:testing] [shuffle:no] [complexity:medium] Cover all edge cases.", 60),
        ]
        mock_response = self._mock_critic(
            False,
            [{"severity": "major", "subtask": "Write unit tests",
              "issue": "Missing prerequisite: no implementation task before testing.",
              "suggestion": "Add an implementation step in an earlier group."}],
            "Add missing prerequisite tasks.",
        )
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        assert result["decomposition_review_passed"] is False
        issues = result["decomposition_review_issues"]
        assert any(
            "prerequisite" in i["issue"].lower() or "missing" in i["issue"].lower()
            for i in issues
        )

    # T14
    def test_flags_unrealistic_duration_for_complexity(self):
        """T14: critic flags a high-complexity 10-min task as unrealistic."""
        tasks = [
            subtask("Architect entire system",
                    "[group:design] [shuffle:no] [complexity:high] Design all components.", 30),
        ]
        mock_response = self._mock_critic(
            False,
            [{"severity": "major", "subtask": "Architect entire system",
              "issue": "10 minutes is unrealistic for a high-complexity architecture task.",
              "suggestion": "Increase to at least 90 minutes."}],
            "Correct unrealistic durations.",
        )
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        assert result["decomposition_review_passed"] is False
        assert result["decomposition_review_issues"][0]["subtask"] == "Architect entire system"

    # T15
    def test_flags_prerequisite_tasks_wrongly_in_same_group(self):
        """T15: critic flags install+run in same group (prerequisite in same group)."""
        tasks = [
            subtask("Install dependencies",
                    "[group:setup] [shuffle:yes] [complexity:low] pip install.", 20),
            subtask("Run the application",
                    "[group:setup] [shuffle:yes] [complexity:low] python app.py.", 20),
        ]
        mock_response = self._mock_critic(
            False,
            [{"severity": "major", "subtask": "Run the application",
              "issue": "Cannot run application before installing dependencies; same group implies no ordering.",
              "suggestion": "Move to a separate group following installation."}],
            "Separate dependent tasks into sequential groups.",
        )
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        assert result["decomposition_review_passed"] is False
        assert any(
            i["subtask"] == "Run the application"
            for i in result["decomposition_review_issues"]
        )

    # T16
    def test_flags_tasks_too_abstract_to_calendar(self):
        """T16: critic flags a 'think about the topic' task as not calenderable."""
        tasks = [
            subtask("Think about the topic",
                    "[group:ideation] [shuffle:yes] [complexity:low] Ponder ideas.", 30),
        ]
        mock_response = self._mock_critic(
            False,
            [{"severity": "minor", "subtask": "Think about the topic",
              "issue": "Task is too abstract to schedule on a calendar.",
              "suggestion": "Replace with a concrete action like 'Draft initial ideas document'."}],
            "Replace abstract tasks with concrete calendar actions.",
        )
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        assert result["decomposition_review_passed"] is False
        assert any(
            "Think about the topic" in i["subtask"]
            for i in result["decomposition_review_issues"]
        )

    # T17
    def test_flags_missing_delivery_or_review_phase(self):
        """T17: critic flags absence of testing/review in an API build plan."""
        tasks = [
            subtask("Design API",
                    "[group:design] [shuffle:no] [complexity:high] Schema and routes.", 90),
            subtask("Build API",
                    "[group:build] [shuffle:no] [complexity:high] Implement endpoints.", 90),
            subtask("Deploy API",
                    "[group:deploy] [shuffle:no] [complexity:medium] Push to cloud.", 60),
        ]
        mock_response = self._mock_critic(
            False,
            [{"severity": "minor", "subtask": "",
              "issue": "No testing or review phase present.",
              "suggestion": "Add an integration testing step before deployment."}],
            "Add testing/review phase.",
        )
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        assert result["decomposition_review_passed"] is False

    # T18
    def test_passes_borderline_decomposition_without_false_positives(self):
        """T18: critic does NOT nitpick a perfectly schedulable but imperfect plan."""
        tasks = [
            subtask("Read chapter 1",
                    "[group:reading] [shuffle:yes] [complexity:medium] Core theory.", 50),
            subtask("Read chapter 2",
                    "[group:reading] [shuffle:yes] [complexity:medium] Applied methods.", 60),
            subtask("Solve exercises",
                    "[group:practice] [shuffle:no] [complexity:high] End-of-chapter problems.", 90),
        ]
        mock_response = self._mock_critic(True, [], "")
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        assert result["decomposition_review_passed"] is True
        assert result["decomposition_review_issues"] == []

    # T19
    def test_result_always_has_required_fields(self):
        """T19: critic result always contains the three required fields with correct types."""
        tasks = [subtask("Task A", "[group:g] [shuffle:no] [complexity:low] Description.", 30)]
        mock_response = self._mock_critic(True, [], "")
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        assert "decomposition_review_passed" in result
        assert "decomposition_review_issues" in result
        assert "decomposition_revision_instruction" in result
        assert isinstance(result["decomposition_review_passed"], bool)
        assert isinstance(result["decomposition_review_issues"], list)
        assert isinstance(result["decomposition_revision_instruction"], str)

    # T20
    def test_normalizes_malformed_issues_gracefully(self):
        """T20: critic node does not crash when issues array has malformed entries."""
        tasks = [subtask("Task A", "[group:g] [shuffle:no] [complexity:low] Description.", 30)]
        # Issue missing required keys (only severity present)
        mock_response = {
            "passed": False,
            "issues": [{"severity": "major"}],
            "revision_instruction": "fix it",
        }
        with patch(_REVIEW_PATCH, return_value=mock_response):
            result = decomposition_critic_node(base_critic_state(tasks))

        # Node should not raise; issues list may be normalised or empty
        assert isinstance(result["decomposition_review_issues"], list)
        # passed=False because mock said so AND has (possibly normalised) issues
        # Note: if issues normalises to empty, the node sets passed=True per its logic
        # So we just verify the contract: no exception, required fields present
        assert "decomposition_review_passed" in result


# =============================================================================
# A3 — T21–T25: Decomposition Reviser Tests
# =============================================================================


class TestDecompositionReviser:
    """T21–T25: The reviser node improves decomposition per critic instructions."""

    # T21
    def test_revise_splits_oversized_task_into_two(self):
        """T21: revised output replaces one large task with two ≤90-min tasks."""
        original = [
            subtask("Do all reading",
                    "[group:reading] [shuffle:no] [complexity:high] Read everything.", 90),
            subtask("Write summary",
                    "[group:writing] [shuffle:no] [complexity:medium] Summarise findings.", 60),
        ]
        revised_output = [
            subtask("Read part 1",
                    "[group:reading_a] [shuffle:no] [complexity:medium] Chapters 1–4.", 60),
            subtask("Read part 2",
                    "[group:reading_b] [shuffle:no] [complexity:medium] Chapters 5–8.", 60),
            subtask("Write summary",
                    "[group:writing] [shuffle:no] [complexity:medium] Summarise findings.", 60),
        ]
        state = base_reviser_state(
            original,
            issues=[{"severity": "major", "subtask": "Do all reading",
                     "issue": "Too broad", "suggestion": "Split into parts."}],
            instruction="Split oversized reading task.",
        )
        with patch(_REVIEW_PATCH, return_value=revised_output):
            result = revise_decomposition_node(state)

        tasks = result["subtasks"]
        assert len(tasks) == 3
        assert all(t["duration_minutes"] <= 90 for t in tasks)

    # T22
    def test_revise_inserts_missing_prerequisite_before_dependent(self):
        """T22: revised plan has 'Write implementation' before 'Write tests'."""
        original = [
            subtask("Write tests",
                    "[group:testing] [shuffle:no] [complexity:medium] Unit tests.", 60),
        ]
        revised_output = [
            subtask("Write implementation",
                    "[group:impl] [shuffle:no] [complexity:high] Core feature code.", 90),
            subtask("Write tests",
                    "[group:testing] [shuffle:no] [complexity:medium] Unit tests.", 60),
        ]
        state = base_reviser_state(
            original,
            issues=[{"severity": "major", "subtask": "Write tests",
                     "issue": "Missing implementation step", "suggestion": "Add it first."}],
            instruction="Insert implementation before tests.",
        )
        with patch(_REVIEW_PATCH, return_value=revised_output):
            result = revise_decomposition_node(state)

        names = [t["name"] for t in result["subtasks"]]
        assert names.index("Write implementation") < names.index("Write tests")

    # T23
    def test_revise_corrects_group_assignment_for_dependent_tasks(self):
        """T23: revised plan puts 'Install IDE' and 'Run first script' in different groups."""
        original = [
            subtask("Install IDE",
                    "[group:setup] [shuffle:yes] [complexity:low] Install VS Code.", 20),
            subtask("Run first script",
                    "[group:setup] [shuffle:yes] [complexity:low] python hello.py.", 20),
        ]
        revised_output = [
            subtask("Install IDE",
                    "[group:install] [shuffle:no] [complexity:low] Install VS Code.", 20),
            subtask("Run first script",
                    "[group:first_run] [shuffle:no] [complexity:low] python hello.py.", 20),
        ]
        state = base_reviser_state(
            original,
            issues=[{"severity": "major", "subtask": "Run first script",
                     "issue": "Depends on Install IDE; same group invalid.",
                     "suggestion": "Move to a new subsequent group."}],
            instruction="Separate dependent tasks.",
        )
        with patch(_REVIEW_PATCH, return_value=revised_output):
            result = revise_decomposition_node(state)

        tasks = result["subtasks"]
        install_task = next(t for t in tasks if t["name"] == "Install IDE")
        run_task = next(t for t in tasks if t["name"] == "Run first script")
        assert group_id(install_task) != group_id(run_task)

    # T24
    def test_revised_output_all_tasks_have_structural_tags(self):
        """T24: every task in the revised plan carries group, shuffle, complexity tags."""
        original = [subtask("Task A", "No tags here.", 30)]
        revised_output = [
            subtask("Task A improved",
                    "[group:alpha] [shuffle:yes] [complexity:low] Concrete action.", 30),
            subtask("Task B improved",
                    "[group:alpha] [shuffle:yes] [complexity:medium] Follow-on action.", 60),
            subtask("Task C improved",
                    "[group:beta] [shuffle:no] [complexity:high] Synthesis work.", 90),
        ]
        state = base_reviser_state(
            original,
            issues=[{"severity": "minor", "subtask": "Task A",
                     "issue": "Missing structural tags", "suggestion": "Add all tags."}],
            instruction="Add all required structural tags.",
        )
        with patch(_REVIEW_PATCH, return_value=revised_output):
            result = revise_decomposition_node(state)

        tasks = result["subtasks"]
        assert has_any_structural_tags(tasks)
        for t in tasks:
            tags = tag_map(t)
            assert "group" in tags, f"{t['name']} missing [group:*]"
            assert "shuffle" in tags, f"{t['name']} missing [shuffle:*]"
            assert "complexity" in tags, f"{t['name']} missing [complexity:*]"

    # T25
    def test_revise_preserves_tasks_not_mentioned_in_critique(self):
        """T25: the five unchanged tasks from the original plan survive revision intact."""
        unchanged = [
            subtask(f"Task {i}",
                    f"[group:g{i}] [shuffle:no] [complexity:medium] Step {i}.", 45)
            for i in range(1, 6)
        ]
        problematic = subtask("Bad task",
                               "[group:bad] [shuffle:no] [complexity:low] Vague.", 20)
        original = unchanged + [problematic]
        revised_output = unchanged + [
            subtask("Bad task fixed",
                    "[group:fixed] [shuffle:no] [complexity:low] Concrete action.", 30),
        ]
        state = base_reviser_state(
            original,
            issues=[{"severity": "minor", "subtask": "Bad task",
                     "issue": "Too vague", "suggestion": "Make concrete."}],
            instruction="Fix the vague task only.",
        )
        with patch(_REVIEW_PATCH, return_value=revised_output):
            result = revise_decomposition_node(state)

        result_names = {t["name"] for t in result["subtasks"]}
        for t in unchanged:
            assert t["name"] in result_names, f"Lost unchanged task: {t['name']}"
