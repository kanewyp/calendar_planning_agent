# =============================================================================
# tests/llm_integration/test_rationale_real.py — Real-LLM rationale tests
# =============================================================================
# Calls generate_rationales_node with genuine Vertex AI / Gemini 2.5 Flash.
# One session-scoped fixture makes three LLM calls (one per strategy).
# All 25 tests reuse that single result.
#
# Assertions are structural — not exact strings — to tolerate LLM variation.
# =============================================================================

from __future__ import annotations

import pytest

from src.orchestration.nodes.generate_rationales import generate_rationales_node
from tests.llm_integration.conftest import (
    CANDIDATE_DEADLINE_FIRST,
    CANDIDATE_ENERGY_AWARE,
    CANDIDATE_MIN_FRAGMENTATION,
    CANDIDATE_VALIDATIONS,
    SIMPLE_SUBTASKS,
)

_STRATEGIES = ("deadline_first", "min_fragmentation", "energy_aware")

# Known mock-mode fallback text — real LLM responses must NOT match this exactly.
_MOCK_FALLBACK = (
    "This strategy uses the available work blocks according to its "
    "scheduling rule while keeping all proposed events visible for review."
)


# ---------------------------------------------------------------------------
# Session-scoped fixture — three real LLM calls, shared across all tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def real_rationales(requires_real_llm):
    """Generate rationales for all three strategies. One session fixture, three LLM calls."""
    state = {
        "goal": "Learn SQL basics in one week",
        "context": "Complete beginner, 1-2 hours each evening",
        "work_start": "09:00",
        "work_end": "18:00",
        "energy_levels": {
            "morning": "high",
            "afternoon": "medium",
            "evening": "low",
        },
        "subtasks": SIMPLE_SUBTASKS,
        "candidate_deadline_first": CANDIDATE_DEADLINE_FIRST,
        "candidate_min_fragmentation": CANDIDATE_MIN_FRAGMENTATION,
        "candidate_energy_aware": CANDIDATE_ENERGY_AWARE,
        "candidate_validations": CANDIDATE_VALIDATIONS,
    }
    return generate_rationales_node(state)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rationales(result: dict) -> dict[str, str]:
    return result["candidate_rationales"]


# ===========================================================================
# T-R01–T-R09  Shape and basic content
# ===========================================================================

# T-R01
@pytest.mark.integration
def test_r01_result_has_rationales_key(real_rationales):
    assert "candidate_rationales" in real_rationales, (
        f"Keys returned: {list(real_rationales.keys())}"
    )


# T-R02
@pytest.mark.integration
def test_r02_rationales_value_is_dict(real_rationales):
    r = _rationales(real_rationales)
    assert isinstance(r, dict), f"Expected dict, got {type(r).__name__}"


# T-R03
@pytest.mark.integration
def test_r03_all_three_strategy_keys_present(real_rationales):
    r = _rationales(real_rationales)
    for strategy in _STRATEGIES:
        assert strategy in r, f"Missing strategy key '{strategy}'. Keys: {list(r.keys())}"


# T-R04
@pytest.mark.integration
def test_r04_deadline_first_rationale_nonempty(real_rationales):
    text = _rationales(real_rationales).get("deadline_first", "")
    assert isinstance(text, str) and text.strip()


# T-R05
@pytest.mark.integration
def test_r05_min_fragmentation_rationale_nonempty(real_rationales):
    text = _rationales(real_rationales).get("min_fragmentation", "")
    assert isinstance(text, str) and text.strip()


# T-R06
@pytest.mark.integration
def test_r06_energy_aware_rationale_nonempty(real_rationales):
    text = _rationales(real_rationales).get("energy_aware", "")
    assert isinstance(text, str) and text.strip()


# T-R07
@pytest.mark.integration
def test_r07_all_three_rationales_are_distinct(real_rationales):
    texts = [_rationales(real_rationales)[s] for s in _STRATEGIES]
    unique = set(t.strip() for t in texts)
    assert len(unique) == 3, "Two or more rationales are identical — each strategy should differ."


# T-R08
@pytest.mark.integration
def test_r08_rationales_within_word_limit(real_rationales):
    """Prompt requests ≤ 60 words; allow 3× tolerance for LLM drift."""
    for strategy, text in _rationales(real_rationales).items():
        wc = len(text.split())
        assert wc <= 180, (
            f"'{strategy}' rationale is {wc} words (limit 180, prompt target 60)."
        )


# T-R09
@pytest.mark.integration
def test_r09_each_rationale_has_multiple_words(real_rationales):
    """A single-word stub or error message is not a valid rationale."""
    for strategy, text in _rationales(real_rationales).items():
        wc = len(text.split())
        assert wc > 3, f"'{strategy}' rationale has only {wc} word(s): {text!r}"


# ===========================================================================
# T-R10–T-R15  Error-signal absence
# ===========================================================================

# T-R10
@pytest.mark.integration
def test_r10_no_traceback_in_rationales(real_rationales):
    for strategy, text in _rationales(real_rationales).items():
        assert "Traceback" not in text, (
            f"'{strategy}' rationale contains 'Traceback' — looks like an error dump."
        )


# T-R11
@pytest.mark.integration
def test_r11_no_provider_error_in_rationales(real_rationales):
    for strategy, text in _rationales(real_rationales).items():
        assert "LLM provider request failed" not in text, (
            f"'{strategy}' rationale contains a provider error message."
        )


# T-R12
@pytest.mark.integration
def test_r12_no_rationale_matches_mock_fallback(real_rationales):
    """If any rationale equals the mock fallback exactly, the LLM was not actually called."""
    for strategy, text in _rationales(real_rationales).items():
        assert text.strip() != _MOCK_FALLBACK, (
            f"'{strategy}' rationale matches the mock fallback string — "
            "check that LLM_PROVIDER is not 'mock'."
        )


# T-R13
@pytest.mark.integration
def test_r13_no_rationale_starts_with_error(real_rationales):
    for strategy, text in _rationales(real_rationales).items():
        assert not text.strip().lower().startswith("error"), (
            f"'{strategy}' rationale starts with 'error': {text[:80]!r}"
        )


# T-R14
@pytest.mark.integration
def test_r14_no_rationale_is_json_blob(real_rationales):
    """Rationale should be prose, not accidentally a raw JSON object."""
    for strategy, text in _rationales(real_rationales).items():
        assert not text.strip().startswith("{"), (
            f"'{strategy}' rationale starts with '{{' — may be a JSON blob."
        )


# T-R15
@pytest.mark.integration
def test_r15_no_rationale_is_only_whitespace(real_rationales):
    for strategy, text in _rationales(real_rationales).items():
        assert text.strip(), f"'{strategy}' rationale is empty or only whitespace."


# ===========================================================================
# T-R16–T-R20  Sentence-level structure
# ===========================================================================

# T-R16
@pytest.mark.integration
def test_r16_deadline_first_contains_sentence_end(real_rationales):
    text = _rationales(real_rationales)["deadline_first"]
    assert "." in text or "!" in text, (
        "deadline_first rationale has no sentence-ending punctuation."
    )


# T-R17
@pytest.mark.integration
def test_r17_min_fragmentation_contains_sentence_end(real_rationales):
    text = _rationales(real_rationales)["min_fragmentation"]
    assert "." in text or "!" in text


# T-R18
@pytest.mark.integration
def test_r18_energy_aware_contains_sentence_end(real_rationales):
    text = _rationales(real_rationales)["energy_aware"]
    assert "." in text or "!" in text


# T-R19
@pytest.mark.integration
def test_r19_each_rationale_under_2000_chars(real_rationales):
    """Sanity cap: no single rationale should be a wall of text."""
    for strategy, text in _rationales(real_rationales).items():
        assert len(text) <= 2000, (
            f"'{strategy}' rationale is {len(text)} chars — suspiciously long."
        )


# T-R20
@pytest.mark.integration
def test_r20_combined_rationales_under_6000_chars(real_rationales):
    total = sum(len(t) for t in _rationales(real_rationales).values())
    assert total <= 6000, f"Combined rationale length is {total} chars."


# ===========================================================================
# T-R21–T-R25  Dict-level invariants
# ===========================================================================

# T-R21
@pytest.mark.integration
def test_r21_rationale_dict_has_exactly_three_keys(real_rationales):
    r = _rationales(real_rationales)
    assert len(r) == 3, f"Expected exactly 3 keys, got {len(r)}: {list(r.keys())}"


# T-R22
@pytest.mark.integration
def test_r22_rationale_dict_keys_match_expected_set(real_rationales):
    expected = set(_STRATEGIES)
    actual = set(_rationales(real_rationales).keys())
    assert actual == expected, f"Unexpected keys: extra={actual - expected}, missing={expected - actual}"


# T-R23
@pytest.mark.integration
def test_r23_result_has_debug_trace_key(real_rationales):
    """The node should emit a debug trace event."""
    assert "debug_trace" in real_rationales, (
        "generate_rationales_node did not emit a debug_trace. "
        "Check that trace_update() is called before returning."
    )


# T-R24
@pytest.mark.integration
def test_r24_deadline_first_word_count_at_least_10(real_rationales):
    wc = len(_rationales(real_rationales)["deadline_first"].split())
    assert wc >= 10, f"deadline_first rationale has only {wc} words — too short to be useful."


# T-R25
@pytest.mark.integration
def test_r25_energy_aware_word_count_at_least_10(real_rationales):
    wc = len(_rationales(real_rationales)["energy_aware"].split())
    assert wc >= 10, f"energy_aware rationale has only {wc} words — too short to be useful."
