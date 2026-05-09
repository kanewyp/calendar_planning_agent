# =============================================================================
# tests/pipeline_unit/test_rationale_quality.py — T77–T86
# =============================================================================
# Tests for generate_rationales_node().
#
# Patch target: src.orchestration.nodes.generate_rationales.call_llm_text
#
# Iteration order inside generate_rationales_node (Python dict preserves insertion order):
#   1st call → "deadline_first"
#   2nd call → "min_fragmentation"
#   3rd call → "energy_aware"
#
# FALLBACK BEHAVIOUR: if the first call raises, skip_llm_after_failure=True
#   and ALL three strategies receive the deterministic fallback rationale.
# =============================================================================

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.orchestration.nodes.generate_rationales import generate_rationales_node
from tests.pipeline_unit.conftest import base_rationale_state, subtask

_PATCH = "src.orchestration.nodes.generate_rationales.call_llm_text"


def _make_violation(event_name: str) -> dict:
    return {
        "event_name": event_name,
        "violation_type": "DEADLINE_EXCEEDED",
        "description": f"{event_name} ends after deadline.",
    }


# =============================================================================
# T77–T86
# =============================================================================


class TestRationaleQuality:

    # T77
    def test_deadline_rationale_contains_deadline_keywords(self):
        """T77: deadline_first rationale mentions scheduling urgency or deadlines."""
        rationales = [
            "This schedule finishes all tasks early to maximise deadline buffer.",
            "Focus blocks reduce context switching and minimise fragmentation.",
            "Tasks are placed in morning high-energy slots matching cognitive demands.",
        ]
        with patch(_PATCH, side_effect=rationales):
            result = generate_rationales_node(base_rationale_state())

        dl_rationale = result["candidate_rationales"]["deadline_first"]
        keywords = {"early", "deadline", "buffer", "front-load", "finish", "finishes"}
        assert any(kw in dl_rationale.lower() for kw in keywords), (
            f"Deadline rationale should mention scheduling urgency. Got: {dl_rationale!r}"
        )

    # T78
    def test_fragmentation_rationale_contains_fragmentation_keywords(self):
        """T78: min_fragmentation rationale mentions focus or fragmentation reduction."""
        rationales = [
            "Tasks are scheduled as early as possible to protect the deadline.",
            "Contiguous focus blocks reduce context switching throughout the day.",
            "Morning energy aligns with demanding cognitive tasks.",
        ]
        with patch(_PATCH, side_effect=rationales):
            result = generate_rationales_node(base_rationale_state())

        frag_rationale = result["candidate_rationales"]["min_fragmentation"]
        keywords = {"focus", "contiguous", "fragmentation", "context switch", "block", "switching"}
        assert any(kw in frag_rationale.lower() for kw in keywords), (
            f"Fragmentation rationale should mention contiguous blocks. Got: {frag_rationale!r}"
        )

    # T79
    def test_energy_rationale_contains_energy_keywords(self):
        """T79: energy_aware rationale mentions energy levels or cognitive demand."""
        rationales = [
            "All tasks are front-loaded to create maximum deadline buffer.",
            "Tasks fill the largest available blocks to reduce calendar fragmentation.",
            "High-energy morning slots are reserved for demanding cognitive tasks.",
        ]
        with patch(_PATCH, side_effect=rationales):
            result = generate_rationales_node(base_rationale_state())

        energy_rationale = result["candidate_rationales"]["energy_aware"]
        keywords = {"energy", "morning", "afternoon", "cognitive", "demanding", "high-energy"}
        assert any(kw in energy_rationale.lower() for kw in keywords), (
            f"Energy rationale should mention energy or cognitive load. Got: {energy_rationale!r}"
        )

    # T80
    def test_each_rationale_within_word_limit(self):
        """T80: node stores rationales as returned; 60-word mocks remain within 80-word buffer."""
        sixty_words = ("This schedule is designed to complete all tasks as early as possible "
                       "ensuring maximum buffer before the deadline while respecting working "
                       "hours and maintaining task dependency order throughout the week.")
        # Exactly 40 words — well within 80-word limit
        short_rationale = ("Tasks are scheduled early to protect the deadline. "
                           "No constraint violations were found.")
        rationales = [sixty_words, sixty_words, short_rationale]
        with patch(_PATCH, side_effect=rationales):
            result = generate_rationales_node(base_rationale_state())

        for strategy, rationale in result["candidate_rationales"].items():
            word_count = len(rationale.split())
            assert word_count <= 80, (
                f"{strategy}: rationale has {word_count} words (limit 80). "
                f"Content: {rationale!r}"
            )

    # T81
    def test_rationale_mentions_violations_when_violations_exist(self):
        """T81: rationale content (from mock) containing 'violation' is stored intact."""
        violations_state = base_rationale_state(
            violations={
                "deadline_first": {
                    "passed": False,
                    "violations": [_make_violation("Task A")],
                },
                "min_fragmentation": {"passed": True, "violations": []},
                "energy_aware": {"passed": True, "violations": []},
            }
        )
        rationales = [
            "This schedule has 1 constraint violation: Task A exceeds the deadline.",
            "No violations found for this strategy.",
            "No violations found for this strategy.",
        ]
        with patch(_PATCH, side_effect=rationales):
            result = generate_rationales_node(violations_state)

        dl_rationale = result["candidate_rationales"]["deadline_first"]
        assert "violation" in dl_rationale.lower(), (
            "Rationale content mentioning violations must be stored without stripping."
        )

    # T82
    def test_rationale_does_not_inject_violation_text_when_passed(self):
        """T82: node does not add 'violation' text when the mock returns a clean rationale."""
        clean_rationale = "Tasks are well scheduled and all constraints pass."
        with patch(_PATCH, return_value=clean_rationale):
            result = generate_rationales_node(base_rationale_state())

        for strategy, rationale in result["candidate_rationales"].items():
            assert "violation" not in rationale.lower(), (
                f"{strategy} rationale should not contain 'violation' when none exist."
            )

    # T83
    def test_fallback_rationale_used_when_llm_raises(self):
        """T83: when call_llm_text raises, all three strategies get a non-empty fallback."""
        with patch(_PATCH, side_effect=RuntimeError("LLM unavailable")):
            result = generate_rationales_node(base_rationale_state())

        rationales = result["candidate_rationales"]
        assert set(rationales.keys()) == {"deadline_first", "min_fragmentation", "energy_aware"}
        for strategy, rationale in rationales.items():
            assert isinstance(rationale, str) and len(rationale) > 0, (
                f"{strategy}: fallback rationale is empty or missing."
            )

    # T84
    def test_fallback_rationale_includes_event_count(self):
        """T84: fallback rationale for a 3-event candidate mentions the event count."""
        events = [
            {"name": f"Task {i}", "description": "desc",
             "start": f"2026-05-11T{9+i}:00:00+00:00",
             "end": f"2026-05-11T{10+i}:00:00+00:00"}
            for i in range(3)
        ]
        state = base_rationale_state(
            deadline_events=events,
            frag_events=events,
            energy_events=events,
        )
        with patch(_PATCH, side_effect=RuntimeError("LLM unavailable")):
            result = generate_rationales_node(state)

        dl_rationale = result["candidate_rationales"]["deadline_first"]
        assert "3" in dl_rationale, (
            f"Fallback rationale should mention event count (3). Got: {dl_rationale!r}"
        )

    # T85
    def test_fallback_rationale_includes_violation_info(self):
        """T85: fallback rationale for a strategy with 2 violations mentions the count."""
        violations_state = base_rationale_state(
            violations={
                "deadline_first": {
                    "passed": False,
                    "violations": [_make_violation("Task A"), _make_violation("Task B")],
                },
                "min_fragmentation": {"passed": True, "violations": []},
                "energy_aware": {"passed": True, "violations": []},
            }
        )
        with patch(_PATCH, side_effect=RuntimeError("LLM unavailable")):
            result = generate_rationales_node(violations_state)

        dl_rationale = result["candidate_rationales"]["deadline_first"]
        assert "2" in dl_rationale, (
            f"Fallback rationale should mention violation count (2). Got: {dl_rationale!r}"
        )

    # T86
    def test_three_rationales_are_distinct_from_each_other(self):
        """T86: the three strategy rationales stored in state are all different strings."""
        rationales = [
            "Deadline-first schedules tasks as early as possible to protect the deadline.",
            "Min-fragmentation keeps focus blocks contiguous to reduce context switching.",
            "Energy-aware places demanding tasks in high-energy morning slots.",
        ]
        with patch(_PATCH, side_effect=rationales):
            result = generate_rationales_node(base_rationale_state())

        stored = list(result["candidate_rationales"].values())
        assert len(set(stored)) == 3, (
            "All three rationale strings must be distinct from each other."
        )
