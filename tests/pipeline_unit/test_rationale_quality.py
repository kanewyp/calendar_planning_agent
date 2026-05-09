# =============================================================================
# tests/pipeline_unit/test_rationale_quality.py — T77–T86
# =============================================================================
# Tests for generate_rationales_node().
#
# T77–T82, T86: Real-LLM tests using the 'real_rationale' session fixture.
# T83–T85: Error-handling tests (kept mocked — they test fallback behavior
#           when the LLM raises, which can only be exercised via a mock error).
#
# Patch target (T83–T85 only): src.orchestration.nodes.generate_rationales.call_llm_text
# =============================================================================

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.orchestration.nodes.generate_rationales import generate_rationales_node
from tests.pipeline_unit.conftest import base_rationale_state, subtask

_PATCH = "src.orchestration.nodes.generate_rationales.call_llm_text"

_STRATEGIES = ("deadline_first", "min_fragmentation", "energy_aware")


def _make_violation(event_name: str) -> dict:
    return {
        "event_name": event_name,
        "violation_type": "DEADLINE_EXCEEDED",
        "description": f"{event_name} ends after deadline.",
    }


# =============================================================================
# T77–T82, T86  — Real-LLM tests (shared real_rationale session fixture)
# =============================================================================

class TestRationaleQuality:

    # T77
    def test_deadline_rationale_is_nonempty_string(self, real_rationale):
        """T77: deadline_first rationale must be a non-empty string from the real LLM."""
        text = real_rationale["candidate_rationales"].get("deadline_first", "")
        assert isinstance(text, str) and text.strip(), (
            "deadline_first rationale is empty or not a string"
        )

    # T78
    def test_min_fragmentation_rationale_is_nonempty_string(self, real_rationale):
        """T78: min_fragmentation rationale must be a non-empty string from the real LLM."""
        text = real_rationale["candidate_rationales"].get("min_fragmentation", "")
        assert isinstance(text, str) and text.strip()

    # T79
    def test_energy_aware_rationale_is_nonempty_string(self, real_rationale):
        """T79: energy_aware rationale must be a non-empty string from the real LLM."""
        text = real_rationale["candidate_rationales"].get("energy_aware", "")
        assert isinstance(text, str) and text.strip()

    # T80
    def test_each_rationale_within_word_limit(self, real_rationale):
        """T80: each rationale should stay within 180 words (3× the prompt's 60-word target)."""
        for strategy, text in real_rationale["candidate_rationales"].items():
            wc = len(text.split())
            assert wc <= 180, (
                f"'{strategy}' rationale is {wc} words — prompt targets ≤60 words "
                f"(allowing 3× tolerance for LLM drift)."
            )

    # T81
    def test_all_three_strategy_keys_present(self, real_rationale):
        """T81: candidate_rationales dict must contain all three strategy keys."""
        rationales = real_rationale["candidate_rationales"]
        for strategy in _STRATEGIES:
            assert strategy in rationales, (
                f"Missing strategy key '{strategy}'. Keys: {list(rationales.keys())}"
            )

    # T82
    def test_rationales_do_not_contain_error_text(self, real_rationale):
        """T82: no rationale should start with 'Error' or contain 'Traceback'."""
        for strategy, text in real_rationale["candidate_rationales"].items():
            assert not text.strip().lower().startswith("error"), (
                f"'{strategy}' rationale starts with 'error': {text[:80]!r}"
            )
            assert "Traceback" not in text, (
                f"'{strategy}' rationale contains 'Traceback' — looks like an error dump."
            )

    # T86
    def test_three_rationales_are_distinct(self, real_rationale):
        """T86: the three strategy rationales must all be different strings."""
        stored = [real_rationale["candidate_rationales"][s] for s in _STRATEGIES]
        assert len(set(stored)) == 3, (
            "All three rationale strings must be distinct from each other."
        )

    # =========================================================================
    # T83–T85  — Error-handling tests (kept mocked: test LLM fallback behavior)
    # =========================================================================

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

