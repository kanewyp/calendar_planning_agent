# =============================================================================
# tests/test_llm_client.py — LLM client module tests
# =============================================================================
# Tests that the LLM client correctly handles retries, JSON parsing, and
# error cases.  Uses mocking — does NOT make real Anthropic API calls.
# =============================================================================

from __future__ import annotations

from unittest.mock import patch

import anthropic
import pytest

from src.llm_client.client import MAX_RETRIES, call_llm_json, call_llm_text


class _FakeAPIError(anthropic.APIError):
    """Minimal APIError subclass for tests — skips the parent's strict __init__."""

    def __init__(self, message: str = "fake api error") -> None:
        Exception.__init__(self, message)


_PATCH_TARGET = "src.llm_client.client._call_anthropic"


class TestCallLlmJson:
    def test_valid_json_response_parsed(self):
        with patch(_PATCH_TARGET, return_value='[{"name": "task1"}]') as m:
            assert call_llm_json("prompt") == [{"name": "task1"}]
        assert m.call_count == 1

    def test_retry_on_invalid_json(self):
        with patch(_PATCH_TARGET, side_effect=["Here is the JSON: [...]", "[]"]) as m:
            assert call_llm_json("prompt") == []
        assert m.call_count == 2

    def test_exhausted_retries_raises(self):
        with patch(_PATCH_TARGET, return_value="not json at all") as m:
            with pytest.raises(ValueError, match="Failed to get valid JSON"):
                call_llm_json("prompt")
        assert m.call_count == MAX_RETRIES + 1

    def test_retry_on_api_error(self):
        with patch(
            _PATCH_TARGET,
            side_effect=[_FakeAPIError(), '{"ok": true}'],
        ) as m:
            assert call_llm_json("prompt") == {"ok": True}
        assert m.call_count == 2


class TestCallLlmText:
    def test_returns_text(self):
        with patch(_PATCH_TARGET, return_value="Some rationale text.") as m:
            assert call_llm_text("prompt") == "Some rationale text."
        assert m.call_count == 1

    def test_exhausted_retries_raises_runtime_error(self):
        with patch(_PATCH_TARGET, side_effect=_FakeAPIError()) as m:
            with pytest.raises(RuntimeError, match="LLM call failed"):
                call_llm_text("prompt")
        assert m.call_count == MAX_RETRIES + 1
