# =============================================================================
# tests/test_orchestration.py — Orchestration layer tests
# =============================================================================
# Tests for the LangGraph nodes and heuristic scheduling functions.
# Uses mock data fixtures — no real LLM or calendar calls.
#
# STEPS TO COMPLETE:
# 1. Test each heuristic with sample subtasks and free slots.
# 2. Test validate_candidates_node with known violations.
# 3. Test build_proposal_node near-duplicate detection.
# 4. Test the full graph wiring (optional integration test).
# =============================================================================

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import patch

import pytest

from src.orchestration.nodes.build_proposal import build_proposal_node
from src.orchestration.nodes.decompose_goal import decompose_goal_node
from src.orchestration.nodes.validate_candidates import validate_candidates_node
from src.orchestration.graph import resume_graph
from src.orchestration.heuristics.deadline_first import schedule_deadline_first
from src.orchestration.heuristics.minimize_fragmentation import schedule_min_fragmentation
from src.orchestration.heuristics.energy_aware import schedule_energy_aware


class TestDecomposeGoalNode:
    def test_valid_llm_output_returns_subtasks(self):
        state = {
            "goal": "Learn React basics",
            "deadline": "2026-04-17",
            "context": "I know JavaScript already.",
            "max_session_minutes": 90,
        }
        llm_output = [
            {
                "name": "Read the intro docs",
                "description": "Work through the official React introduction.",
                "duration_minutes": 45,
            },
            {
                "name": "Build a counter",
                "description": "Practice state updates in a small component.",
                "duration_minutes": 60,
            },
        ]

        with patch(
            "src.orchestration.nodes.decompose_goal.call_llm_json",
            return_value=llm_output,
        ):
            result = decompose_goal_node(state)

        assert result == {"subtasks": llm_output}

    def test_empty_llm_output_raises(self):
        state = {
            "goal": "Learn React basics",
            "deadline": "2026-04-17",
            "max_session_minutes": 90,
        }

        with patch(
            "src.orchestration.nodes.decompose_goal.call_llm_json",
            return_value=[],
        ):
            with pytest.raises(ValueError, match="non-empty JSON array"):
                decompose_goal_node(state)

    def test_malformed_subtask_raises_instead_of_skipping(self):
        state = {
            "goal": "Learn React basics",
            "deadline": "2026-04-17",
            "max_session_minutes": 90,
        }
        llm_output = [
            {
                "name": "Read the intro docs",
                "description": "Work through the official React introduction.",
                "duration_minutes": 45,
            },
            {
                "name": "",
                "description": "This item is malformed.",
                "duration_minutes": 30,
            },
        ]

        with patch(
            "src.orchestration.nodes.decompose_goal.call_llm_json",
            return_value=llm_output,
        ):
            with pytest.raises(ValueError, match="invalid name"):
                decompose_goal_node(state)

    def test_over_limit_duration_raises(self):
        state = {
            "goal": "Learn React basics",
            "deadline": "2026-04-17",
            "max_session_minutes": 90,
        }
        llm_output = [
            {
                "name": "Build a mini app",
                "description": "Too large for one focused work session.",
                "duration_minutes": 120,
            }
        ]

        with patch(
            "src.orchestration.nodes.decompose_goal.call_llm_json",
            return_value=llm_output,
        ):
            with pytest.raises(ValueError, match="exceeds max session"):
                decompose_goal_node(state)

    def test_llm_failure_is_wrapped_with_node_context(self):
        state = {
            "goal": "Learn React basics",
            "deadline": "2026-04-17",
            "max_session_minutes": 90,
        }

        with patch(
            "src.orchestration.nodes.decompose_goal.call_llm_json",
            side_effect=ValueError("bad llm output"),
        ):
            with pytest.raises(RuntimeError, match="Goal decomposition failed"):
                decompose_goal_node(state)


class TestDeadlineFirstHeuristic:
    """Test the deadline-first scheduling strategy."""

    def test_subtasks_scheduled_earliest_possible(
        self, sample_subtasks, sample_free_slots
    ):
        """Subtasks should be placed in the earliest available slots.

        STEPS:
        1. Call schedule_deadline_first(sample_subtasks, sample_free_slots).
        2. Assert the first subtask is placed at the start of the first
           free slot.
        3. Assert all subtasks are scheduled (if enough time exists).
        """
        events = schedule_deadline_first(sample_subtasks, sample_free_slots)

        assert len(events) == len(sample_subtasks)
        assert events[0]["start"] == sample_free_slots[0]["start"]
        assert events[0]["name"] == sample_subtasks[0]["name"]
        # Output is chronologically ordered
        starts = [e["start"] for e in events]
        assert starts == sorted(starts)

    def test_slot_splitting(self, sample_free_slots):
        """A short subtask should split a long free slot, leaving the remainder.

        STEPS:
        1. Provide one subtask of 30 min and one free slot of 4 hours.
        2. Assert the subtask occupies only the first 30 min.
        3. Ideally verify remaining slot is still available for next subtask.
        """
        subtasks = [
            {"name": "Short task",  "description": "x", "duration_minutes": 30},
            {"name": "Second task", "description": "y", "duration_minutes": 30},
        ]
        big_slot = [{"start": "2026-04-06T10:00:00+00:00", "end": "2026-04-06T14:00:00+00:00"}]
        events = schedule_deadline_first(subtasks, big_slot)

        assert len(events) == 2
        assert events[0]["start"] == "2026-04-06T10:00:00+00:00"
        assert events[0]["end"]   == "2026-04-06T10:30:00+00:00"
        # Remainder used for second task
        assert events[1]["start"] == "2026-04-06T10:30:00+00:00"
        assert events[1]["end"]   == "2026-04-06T11:00:00+00:00"


class TestMinFragmentationHeuristic:
    """Test the minimize-fragmentation scheduling strategy."""

    def test_longest_subtask_gets_largest_slot(
        self, sample_subtasks, sample_free_slots
    ):
        """The longest subtask should be placed in the largest free slot.

        STEPS:
        1. Call schedule_min_fragmentation(sample_subtasks, sample_free_slots).
        2. Identify the longest subtask and the largest slot.
        3. Assert the longest subtask was placed in (or at the start of)
           the largest slot.
        """
        events = schedule_min_fragmentation(sample_subtasks, sample_free_slots)

        assert len(events) == len(sample_subtasks)
        longest_subtask = max(sample_subtasks, key=lambda s: s["duration_minutes"])
        largest_slot = max(
            sample_free_slots,
            key=lambda sl: (
                datetime.datetime.fromisoformat(sl["end"]) -
                datetime.datetime.fromisoformat(sl["start"])
            ),
        )
        longest_event = next(e for e in events if e["name"] == longest_subtask["name"])
        assert longest_event["start"] == largest_slot["start"]
        # Output is chronologically ordered
        starts = [e["start"] for e in events]
        assert starts == sorted(starts)


class TestEnergyAwareHeuristic:
    """Test the energy-aware scheduling strategy."""

    def test_heavy_tasks_in_morning(self, sample_subtasks, sample_free_slots):
        """Subtasks >= 60 min should be placed in morning slots when possible.

        STEPS:
        1. Call schedule_energy_aware(sample_subtasks, sample_free_slots).
        2. Identify events with duration >= 60 min.
        3. Assert their start times are before 12:00.
        """
        events = schedule_energy_aware(sample_subtasks, sample_free_slots)
        heavy_names = {
            s["name"] for s in sample_subtasks if s["duration_minutes"] >= 60
        }
        morning_boundary = datetime.time(12, 0)
        for event in events:
            if event["name"] in heavy_names:
                start_time = datetime.datetime.fromisoformat(event["start"]).time()
                assert start_time < morning_boundary, (
                    f"Heavy task '{event['name']}' placed after noon at {start_time}"
                )

    def test_light_tasks_in_afternoon(self, sample_subtasks, sample_free_slots):
        """Subtasks < 60 min should be placed in afternoon slots when possible.

        STEPS:
        1. Same as above, but check that short tasks start after 12:00.
        """
        # sample_subtasks has one light task: 'Set up dev environment' (30 min)
        events = schedule_energy_aware(sample_subtasks, sample_free_slots)
        light_names = {
            s["name"] for s in sample_subtasks if s["duration_minutes"] < 60
        }
        morning_boundary = datetime.time(12, 0)
        for event in events:
            if event["name"] in light_names:
                start_time = datetime.datetime.fromisoformat(event["start"]).time()
                assert start_time >= morning_boundary, (
                    f"Light task '{event['name']}' placed in morning at {start_time}"
                )


class TestValidateCandidates:
    """Test the validate_candidates node."""

    def test_all_candidates_validated(self):
        """All three candidates should receive a ValidationResult.

        STEPS:
        1. Build state with three mock candidates and busy_blocks.
        2. Run validate_candidates_node.
        3. Assert candidate_validations has entries for all three strategies.
        """
        clean_candidate = [
            {
                "name": "Read React docs",
                "description": "Official docs",
                "start": "2026-04-06T10:00:00+00:00",
                "end": "2026-04-06T11:00:00+00:00",
            }
        ]
        overlapping_candidate = [
            {
                "name": "Overlap standup",
                "description": "Conflicts with existing meeting",
                "start": "2026-04-06T09:15:00+00:00",
                "end": "2026-04-06T09:45:00+00:00",
            }
        ]
        late_candidate = [
            {
                "name": "Late work",
                "description": "Past deadline",
                "start": "2026-04-17T17:00:00+00:00",
                "end": "2026-04-17T19:00:00+00:00",
            }
        ]
        state = {
            "busy_blocks": [
                {
                    "start": "2026-04-06T09:30:00+00:00",
                    "end": "2026-04-06T10:00:00+00:00",
                }
            ],
            "work_start": "09:00",
            "work_end": "18:00",
            "deadline": "2026-04-17T18:00:00+00:00",
            "candidate_deadline_first": clean_candidate,
            "candidate_min_fragmentation": overlapping_candidate,
            "candidate_energy_aware": late_candidate,
        }

        result = validate_candidates_node(state)

        validations = result["candidate_validations"]
        assert set(validations) == {
            "deadline_first",
            "min_fragmentation",
            "energy_aware",
        }
        assert validations["deadline_first"]["passed"] is True
        assert validations["min_fragmentation"]["passed"] is False
        assert validations["energy_aware"]["passed"] is False

    def test_clean_candidate_passes(self):
        """A candidate with no constraint violations should pass validation.

        STEPS:
        1. Build a candidate with no overlaps, within working hours and deadline.
        2. Run validate_candidates_node.
        3. Assert passed=True and violations is empty.
        """
        candidate = [
            {
                "name": "Read React docs",
                "description": "Official docs",
                "start": "2026-04-06T10:00:00+00:00",
                "end": "2026-04-06T11:00:00+00:00",
            }
        ]
        state = {
            "busy_blocks": [],
            "work_start": "09:00",
            "work_end": "18:00",
            "deadline": "2026-04-17",
            "candidate_deadline_first": candidate,
            "candidate_min_fragmentation": list(candidate),
            "candidate_energy_aware": list(candidate),
        }

        result = validate_candidates_node(state)

        for validation in result["candidate_validations"].values():
            assert validation["passed"] is True
            assert validation["violations"] == []


class TestResumeGraph:
    """Test the approval/resume helper contract."""

    def test_approve_uses_explicit_selected_strategy(self):
        deadline_first = [
            {
                "name": "Read React docs",
                "description": "Official docs",
                "start": "2026-04-06T10:00:00+00:00",
                "end": "2026-04-06T11:00:00+00:00",
            }
        ]
        min_fragmentation = [
            {
                "name": "Build counter",
                "description": "Practice state",
                "start": "2026-04-06T13:00:00+00:00",
                "end": "2026-04-06T14:00:00+00:00",
            }
        ]
        paused_state = {
            "selected_strategy": "deadline_first",
            "candidate_deadline_first": deadline_first,
            "candidate_min_fragmentation": min_fragmentation,
            "candidate_energy_aware": [],
        }

        with patch(
            "src.orchestration.graph.write_events_node",
            return_value={"write_results": [{"id": "mock-event"}]},
        ) as write_events:
            result = resume_graph(
                graph=object(),
                paused_state=paused_state,
                approved=True,
                selected_strategy="min_fragmentation",
            )

        assert result["user_approved"] is True
        assert result["selected_strategy"] == "min_fragmentation"
        assert result["final_schedule"] == min_fragmentation
        assert result["write_results"] == [{"id": "mock-event"}]
        write_events.assert_called_once()

    def test_reject_does_not_require_strategy_or_write_events(self):
        paused_state = {
            "selected_strategy": "deadline_first",
            "candidate_deadline_first": [],
            "candidate_min_fragmentation": [],
            "candidate_energy_aware": [],
        }

        with patch("src.orchestration.graph.write_events_node") as write_events:
            result = resume_graph(
                graph=object(),
                paused_state=paused_state,
                approved=False,
            )

        assert result["user_approved"] is False
        assert result["selected_strategy"] is None
        assert "write_results" not in result
        write_events.assert_not_called()

    def test_approve_requires_valid_selected_strategy(self):
        paused_state = {
            "candidate_deadline_first": [],
            "candidate_min_fragmentation": [],
            "candidate_energy_aware": [],
        }

        with pytest.raises(ValueError, match="requires a valid selected_strategy"):
            resume_graph(
                graph=object(),
                paused_state=paused_state,
                approved=True,
            )

        with pytest.raises(ValueError, match="requires a valid selected_strategy"):
            resume_graph(
                graph=object(),
                paused_state=paused_state,
                approved=True,
                selected_strategy="not_a_strategy",
            )


class TestBuildProposal:
    """Test the build_proposal node."""

    def test_identical_candidates_detected(self):
        """When all three candidates produce the same schedule, detect it.

        STEPS:
        1. Build state with three identical candidate lists.
        2. Run build_proposal_node.
        3. Assert candidates_identical is True.
        """
        candidate = [
            {
                "name": "Read React docs",
                "description": "Work through the introductory documentation.",
                "start": "2026-04-06T10:00:00+00:00",
                "end": "2026-04-06T11:00:00+00:00",
            }
        ]
        state = {
            "candidate_deadline_first": candidate,
            "candidate_min_fragmentation": list(candidate),
            "candidate_energy_aware": list(candidate),
        }

        result = build_proposal_node(state)

        assert result == {"candidates_identical": True}

    def test_different_candidates_not_flagged(self):
        """When candidates differ, candidates_identical should be False.

        STEPS:
        1. Build state with three different candidate lists.
        2. Run build_proposal_node.
        3. Assert candidates_identical is False.
        """
        shared_time = {
            "description": "One hour block.",
            "start": "2026-04-06T10:00:00+00:00",
            "end": "2026-04-06T11:00:00+00:00",
        }
        state = {
            "candidate_deadline_first": [
                {"name": "Read React docs", **shared_time}
            ],
            "candidate_min_fragmentation": [
                {"name": "Build counter component", **shared_time}
            ],
            "candidate_energy_aware": [
                {"name": "Read React docs", **shared_time}
            ],
        }

        result = build_proposal_node(state)

        assert result == {"candidates_identical": False}
