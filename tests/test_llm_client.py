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

from config.settings import settings
from src.llm_client.client import (
    GEMINI_OPENAI_BASE_URL,
    MAX_RETRIES,
    VERTEX_OPENAI_BASE_URL_TEMPLATE,
    _clean_llm_json,
    _parse_json_with_recovery,
    call_llm_json,
    call_llm_text,
)


class _FakeAPIError(anthropic.APIError):
    """Minimal APIError subclass for tests — skips the parent's strict __init__."""

    def __init__(self, message: str = "fake api error") -> None:
        Exception.__init__(self, message)


_PATCH_TARGET = "src.llm_client.client._call_llm"


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

    def test_retry_prompt_contains_error_and_snippet(self):
        """On JSON failure the retry prompt should include the parse error and
        a snippet of the broken response so the model can self-correct."""
        calls: list[str] = []

        def _fake_call_llm(prompt, **kwargs):
            calls.append(prompt)
            if len(calls) == 1:
                return "definitely not json {"
            return '[{"name": "fixed"}]'

        with patch(_PATCH_TARGET, side_effect=_fake_call_llm):
            result = call_llm_json("original prompt")

        assert result == [{"name": "fixed"}]
        assert len(calls) == 2
        # Retry prompt should reference original prompt, error, and snippet
        assert "original prompt" in calls[1]
        assert "Parse error" in calls[1]
        assert "definitely not json" in calls[1]


class TestJsonRecovery:
    """Tests for the JSON cleaning and recovery helpers."""

    def test_strips_markdown_code_fences(self):
        raw = "```json\n[{\"a\": 1}]\n```"
        assert _parse_json_with_recovery(raw) == [{"a": 1}]

    def test_removes_trailing_commas_in_object(self):
        raw = '{"a": 1, "b": 2,}'
        assert _parse_json_with_recovery(raw) == {"a": 1, "b": 2}

    def test_removes_trailing_commas_in_array(self):
        raw = '[1, 2, 3,]'
        assert _parse_json_with_recovery(raw) == [1, 2, 3]

    def test_normalises_smart_quotes(self):
        raw = '[\u201cvalue\u201d]'
        assert _parse_json_with_recovery(raw) == ["value"]

    def test_strips_leading_prose(self):
        raw = 'Here is your JSON:\n[{"name": "task"}]'
        assert _parse_json_with_recovery(raw) == [{"name": "task"}]

    def test_python_literals_converted(self):
        raw = '{"flag": True, "other": None}'
        assert _parse_json_with_recovery(raw) == {"flag": True, "other": None}

    def test_valid_json_returned_unchanged(self):
        raw = '[{"name": "task", "duration_minutes": 60}]'
        result = _parse_json_with_recovery(raw)
        assert result[0]["name"] == "task"
        assert result[0]["duration_minutes"] == 60

    def test_gemini_style_response_with_trailing_comma_and_fence(self):
        """Simulate the exact format Gemini sometimes returns."""
        raw = (
            "```json\n"
            "[\n"
            '  {"name": "Learn basics", "description": "Read docs.", "duration_minutes": 60,},\n'
            '  {"name": "Build project", "description": "Write code.", "duration_minutes": 90}\n'
            "]\n"
            "```"
        )
        result = _parse_json_with_recovery(raw)
        assert len(result) == 2
        assert result[0]["name"] == "Learn basics"




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


class TestProviderConfig:
    def test_mock_provider_returns_deterministic_responses(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
        monkeypatch.setattr(settings, "LLM_DECOMPOSITION_MODEL", "")
        monkeypatch.setattr(settings, "LLM_RATIONALE_MODEL", "")

        subtasks = call_llm_json("prompt")
        rationale = call_llm_text("prompt")

        assert len(subtasks) == 3
        assert subtasks[0]["name"] == "Clarify goal requirements"
        assert "scheduling rule" in rationale

    def test_gemini_provider_uses_openai_compatible_endpoint(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
        monkeypatch.setattr(settings, "LLM_API_KEY", "")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")
        monkeypatch.setattr(settings, "LLM_BASE_URL", "")
        monkeypatch.setattr(settings, "LLM_RATIONALE_MODEL", "")

        with patch(
            "src.llm_client.client._post_json",
            return_value={"choices": [{"message": {"content": "Gemini rationale"}}]},
        ) as post_json:
            assert call_llm_text("prompt") == "Gemini rationale"

        url = post_json.call_args.args[0]
        headers = post_json.call_args.kwargs["headers"]
        payload = post_json.call_args.kwargs["payload"]
        assert url == f"{GEMINI_OPENAI_BASE_URL}/chat/completions"
        assert headers["Authorization"] == "Bearer gemini-key"
        assert payload["model"] == "gemini-2.5-flash"

    def test_openai_compatible_provider_uses_configured_endpoint(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")
        monkeypatch.setattr(settings, "LLM_API_KEY", "provider-key")
        monkeypatch.setattr(settings, "LLM_BASE_URL", "https://api.example.com/v1/")
        monkeypatch.setattr(settings, "LLM_RATIONALE_MODEL", "cheap-rationale-model")

        with patch(
            "src.llm_client.client._post_json",
            return_value={"choices": [{"message": {"content": "Provider text"}}]},
        ) as post_json:
            assert call_llm_text("prompt") == "Provider text"

        url = post_json.call_args.args[0]
        headers = post_json.call_args.kwargs["headers"]
        payload = post_json.call_args.kwargs["payload"]
        assert url == "https://api.example.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer provider-key"
        assert payload["model"] == "cheap-rationale-model"

    def test_vertex_ai_provider_uses_adc_token_and_project_endpoint(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_PROVIDER", "vertex_ai")
        monkeypatch.setattr(settings, "VERTEX_PROJECT_ID", "calendar-agent-project")
        monkeypatch.setattr(settings, "VERTEX_LOCATION", "us-central1")
        monkeypatch.setattr(settings, "LLM_RATIONALE_MODEL", "google/gemini-2.5-flash")

        with (
            patch("src.llm_client.client._get_vertex_access_token", return_value="vertex-token"),
            patch(
                "src.llm_client.client._post_json",
                return_value={"choices": [{"message": {"content": "Vertex text"}}]},
            ) as post_json,
        ):
            assert call_llm_text("prompt") == "Vertex text"

        url = post_json.call_args.args[0]
        headers = post_json.call_args.kwargs["headers"]
        payload = post_json.call_args.kwargs["payload"]
        expected_base_url = VERTEX_OPENAI_BASE_URL_TEMPLATE.format(
            project_id="calendar-agent-project",
            location="us-central1",
        )
        assert url == f"{expected_base_url}/chat/completions"
        assert headers["Authorization"] == "Bearer vertex-token"
        assert payload["model"] == "google/gemini-2.5-flash"

    def test_vertex_ai_provider_requires_project_id(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_PROVIDER", "vertex_ai")
        monkeypatch.setattr(settings, "VERTEX_PROJECT_ID", "")

        with patch("src.llm_client.client._get_vertex_access_token", return_value="token"):
            with pytest.raises(ValueError, match="VERTEX_PROJECT_ID is required"):
                call_llm_text("prompt")

    def test_anthropic_provider_uses_legacy_key(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
        monkeypatch.setattr(settings, "LLM_API_KEY", "")
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "anthropic-key")
        monkeypatch.setattr(settings, "LLM_RATIONALE_MODEL", "")

        with patch(
            "src.llm_client.client._call_anthropic",
            return_value="Anthropic text",
        ) as call_anthropic:
            assert call_llm_text("prompt") == "Anthropic text"

        assert call_anthropic.call_args.kwargs["api_key"] == "anthropic-key"
        assert call_anthropic.call_args.kwargs["model"] == "claude-sonnet-4-20250514"
