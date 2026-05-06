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
from src.orchestration.nodes.fetch_events import fetch_events_node
from src.orchestration.nodes.schedule_candidates import (
    energy_aware_node,
    min_fragmentation_node,
)
from src.orchestration.nodes.validate_candidates import validate_candidates_node
from src.orchestration.nodes.write_events import write_events_node
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

        assert result["subtasks"] == llm_output
        assert result["debug_trace"][0]["node"] == "decompose_goal"
        assert result["debug_trace"][0]["details"]["count"] == 2

    def test_structural_tags_are_included_in_debug_trace(self):
        state = {
            "goal": "Learn React basics",
            "deadline": "2026-04-17",
            "context": "I know JavaScript already.",
            "max_session_minutes": 90,
        }
        llm_output = [
            {
                "name": "Read the intro docs",
                "description": (
                    "[group:foundations] [seq:1] [shuffle:no] "
                    "Work through the official React introduction."
                ),
                "duration_minutes": 45,
            },
        ]

        with patch(
            "src.orchestration.nodes.decompose_goal.call_llm_json",
            return_value=llm_output,
        ):
            result = decompose_goal_node(state)

        details = result["debug_trace"][0]["details"]
        item = details["items"][0]
        assert details["structural_tagged_count"] == 1
        assert item["has_structural_tags"] is True
        assert item["group"] == "foundations"
        assert item["seq"] == 1
        assert item["shuffle"] is False

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

    def test_structural_mode_uses_largest_slot_on_earliest_available_day(self):
        subtasks = [
            {
                "name": "Short peer",
                "description": "[group:practice] [shuffle:yes] [complexity:low] Short task.",
                "duration_minutes": 30,
            },
            {
                "name": "Long peer",
                "description": "[group:practice] [shuffle:yes] [complexity:high] Long task.",
                "duration_minutes": 90,
            },
        ]
        free_slots = [
            {
                "start": "2026-04-06T09:00:00+00:00",
                "end": "2026-04-06T10:00:00+00:00",
            },
            {
                "start": "2026-04-06T11:00:00+00:00",
                "end": "2026-04-06T13:00:00+00:00",
            },
            {
                "start": "2026-04-07T09:00:00+00:00",
                "end": "2026-04-07T13:00:00+00:00",
            },
        ]

        events = schedule_min_fragmentation(subtasks, free_slots)

        assert [event["name"] for event in events] == ["Long peer", "Short peer"]
        assert events[0]["start"] == "2026-04-06T11:00:00+00:00"
        assert events[1]["start"] == "2026-04-06T12:30:00+00:00"

    def test_phase_order_groups_before_later_phases(self):
        subtasks = [
            {
                "name": "A1",
                "description": "[group:a] [shuffle:no] [complexity:low] First phase task.",
                "duration_minutes": 30,
            },
            {
                "name": "B1",
                "description": "[group:b] [shuffle:no] [complexity:medium] Second phase task.",
                "duration_minutes": 30,
            },
            {
                "name": "A2",
                "description": "[group:a] [shuffle:no] [complexity:low] First phase follow-up.",
                "duration_minutes": 30,
            },
        ]
        free_slots = [
            {
                "start": "2026-04-06T09:00:00+00:00",
                "end": "2026-04-06T12:00:00+00:00",
            },
        ]

        events = schedule_min_fragmentation(subtasks, free_slots)

        assert [event["name"] for event in events] == ["A1", "A2", "B1"]


class TestEnergyAwareHeuristic:
    """Test the energy-aware scheduling strategy."""

    def test_satisficing_uses_near_match_before_far_perfect_match(self):
        subtasks = [
            {
                "name": "Hard topic",
                "description": "[group:deep] [shuffle:no] [complexity:high] Deep work.",
                "duration_minutes": 60,
            }
        ]
        free_slots = [
            {
                "start": "2026-04-06T13:00:00+00:00",
                "end": "2026-04-06T14:00:00+00:00",
            },
            {
                "start": "2026-04-10T09:00:00+00:00",
                "end": "2026-04-10T10:00:00+00:00",
            },
        ]

        events = schedule_energy_aware(
            subtasks,
            free_slots,
            {"morning": "high", "afternoon": "medium", "evening": "low"},
        )

        assert events[0]["start"] == "2026-04-06T13:00:00+00:00"

    def test_user_energy_profile_drives_slot_choice(self):
        subtasks = [
            {
                "name": "Light admin",
                "description": "[group:admin] [shuffle:no] [complexity:low] Simple setup.",
                "duration_minutes": 30,
            }
        ]
        free_slots = [
            {
                "start": "2026-04-06T09:00:00+00:00",
                "end": "2026-04-06T09:30:00+00:00",
            },
            {
                "start": "2026-04-06T17:00:00+00:00",
                "end": "2026-04-06T17:30:00+00:00",
            },
        ]

        events = schedule_energy_aware(
            subtasks,
            free_slots,
            {"morning": "high", "afternoon": "medium", "evening": "low"},
        )

        assert events[0]["start"] == "2026-04-06T17:00:00+00:00"


class TestScheduleCandidateNodes:
    def test_energy_aware_trace_includes_energy_and_order_metadata(self):
        state = {
            "subtasks": [
                {
                    "name": "Deep work",
                    "description": (
                        "[group:project] [seq:1] [shuffle:no] "
                        "Implement the core feature."
                    ),
                    "duration_minutes": 90,
                }
            ],
            "free_slots": [
                {
                    "start": "2026-04-06T09:00:00+00:00",
                    "end": "2026-04-06T10:30:00+00:00",
                },
            ],
            "work_start": "09:00",
            "energy_levels": {
                "morning": "low",
                "afternoon": "medium",
                "evening": "high",
            },
        }

        result = energy_aware_node(state)

        trace = result["debug_trace"][0]
        assert trace["node"] == "schedule_energy_aware"
        assert trace["summary"]["energy_levels"] == state["energy_levels"]
        assert trace["summary"]["structural_mode"] is True
        assert trace["summary"]["subtask_order_before"] == ["Deep work"]
        assert trace["summary"]["scheduled_order"] == ["Deep work"]
        assert trace["summary"]["chronological_order"] == ["Deep work"]
        assert trace["summary"]["order_inversion_count"] == 0
        assert trace["details"]["events"][0]["period"] == "morning"
        assert trace["details"]["events"][0]["period_energy_level"] == "low"
        assert trace["details"]["order_inversions"] == []

    def test_schedule_trace_uses_phase_order_for_inversion_checks(self):
        state = {
            "subtasks": [
                {
                    "name": "A1",
                    "description": "[group:a] [shuffle:no] [complexity:low] First phase task.",
                    "duration_minutes": 30,
                },
                {
                    "name": "B1",
                    "description": "[group:b] [shuffle:no] [complexity:medium] Second phase task.",
                    "duration_minutes": 30,
                },
                {
                    "name": "A2",
                    "description": "[group:a] [shuffle:no] [complexity:low] First phase follow-up.",
                    "duration_minutes": 30,
                },
            ],
            "free_slots": [
                {
                    "start": "2026-04-06T09:00:00+00:00",
                    "end": "2026-04-06T11:00:00+00:00",
                },
            ],
        }

        result = min_fragmentation_node(state)

        trace = result["debug_trace"][0]
        assert trace["summary"]["subtask_order_before"] == [
            "A1",
            "B1",
            "A2",
        ]
        assert trace["summary"]["expected_dependency_order"] == [
            "A1",
            "A2",
            "B1",
        ]
        assert trace["summary"]["chronological_order"] == [
            "A1",
            "A2",
            "B1",
        ]
        assert trace["summary"]["order_inversion_count"] == 0
        assert trace["details"]["order_inversions"] == []


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
        assert result["debug_trace"][0]["node"] == "validate_candidates"

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
        assert result["debug_trace"][0]["node"] == "human_approval"
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
        assert result["debug_trace"][0]["node"] == "human_approval"
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

        assert result["candidates_identical"] is True
        assert result["debug_trace"][0]["node"] == "build_proposal"

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

        assert result["candidates_identical"] is False
        assert result["debug_trace"][0]["node"] == "build_proposal"


class TestLiveCalendarNodeIntegration:
    def test_fetch_events_live_uses_configured_calendar_id(self, monkeypatch):
        state = {
            "deadline": "2099-01-01",
            "work_start": "09:00",
            "work_end": "18:00",
        }
        observed: dict[str, Any] = {}

        monkeypatch.setattr("src.orchestration.nodes.fetch_events.settings.CALENDAR_MODE", "live")
        monkeypatch.setattr(
            "src.orchestration.nodes.fetch_events.settings.GOOGLE_CALENDAR_ID",
            "learning-calendar@example.com",
        )

        def _fake_fetch_busy_blocks(time_min, time_max, calendar_id):
            observed["calendar_id"] = calendar_id
            return []

        monkeypatch.setattr(
            "src.orchestration.nodes.fetch_events.compute_free_slots",
            lambda **kwargs: [],
        )
        monkeypatch.setattr(
            "src.calendar_api.events.fetch_busy_blocks",
            _fake_fetch_busy_blocks,
        )

        result = fetch_events_node(state)

        assert observed["calendar_id"] == "learning-calendar@example.com"
        assert result["busy_blocks"] == []
        assert result["free_slots"] == []

    def test_write_events_live_uses_configured_calendar_id(self, monkeypatch):
        state = {
            "final_schedule": [
                {
                    "name": "Learn SQL",
                    "description": "Read indexing chapter",
                    "start": "2026-04-06T10:00:00+00:00",
                    "end": "2026-04-06T11:00:00+00:00",
                }
            ]
        }
        observed: dict[str, Any] = {}

        monkeypatch.setattr("src.orchestration.nodes.write_events.settings.CALENDAR_MODE", "live")
        monkeypatch.setattr(
            "src.orchestration.nodes.write_events.settings.GOOGLE_CALENDAR_ID",
            "learning-calendar@example.com",
        )

        def _fake_create_events_batch(events, calendar_id):
            observed["calendar_id"] = calendar_id
            return [{"id": "evt-123"}]

        monkeypatch.setattr(
            "src.calendar_api.events.create_events_batch",
            _fake_create_events_batch,
        )

        result = write_events_node(state)

        assert observed["calendar_id"] == "learning-calendar@example.com"
        assert result["write_results"] == [{"id": "evt-123"}]
