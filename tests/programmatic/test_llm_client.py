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
    LLMResponseTruncated,
    MAX_RETRIES,
    VERTEX_OPENAI_BASE_URL_TEMPLATE,
    _call_anthropic,
    _parse_json_with_recovery,
    _call_openai_compatible,
    call_llm_json,
    call_llm_text,
    get_llm_metadata,
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

    def test_truncated_json_response_does_not_retry(self):
        with patch(
            _PATCH_TARGET,
            side_effect=LLMResponseTruncated("json truncated"),
        ) as m:
            with pytest.raises(ValueError, match="after 1 attempts"):
                call_llm_json("prompt")
        assert m.call_count == 1

    def test_retry_on_api_error(self):
        with patch(
            _PATCH_TARGET,
            side_effect=[_FakeAPIError(), '{"ok": true}'],
        ) as m:
            assert call_llm_json("prompt") == {"ok": True}
        assert m.call_count == 2

    def test_recovery_handles_markdown_fences_and_trailing_commas(self):
        text = """```json
        [
            {"name": "Task", "done": True, "notes": None,},
        ]
        ```"""

        assert _parse_json_with_recovery(text) == [
            {"name": "Task", "done": True, "notes": None}
        ]

    def test_recovery_extracts_json_from_surrounding_text(self):
        text = 'Here is the JSON:\n[{"name": "Task"}]\nHope this helps.'

        assert _parse_json_with_recovery(text) == [{"name": "Task"}]

    def test_retry_prompt_includes_parse_error_context(self):
        responses = ['[{"name": "unterminated}', '[{"name": "Task"}]']

        with patch(_PATCH_TARGET, side_effect=responses) as m:
            assert call_llm_json("prompt") == [{"name": "Task"}]

        retry_prompt = m.call_args_list[1].args[0]
        assert "could not be parsed as JSON" in retry_prompt
        assert "Unterminated string" in retry_prompt

    def test_metadata_includes_decomposition_token_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
        monkeypatch.setattr(settings, "LLM_DECOMPOSITION_MODEL", "")
        monkeypatch.setattr(settings, "LLM_DECOMPOSITION_MAX_TOKENS", 9000)

        metadata = get_llm_metadata("decomposition")

        assert metadata["max_tokens"] == "9000"
        assert metadata["model"] == "mock"

    def test_mock_provider_metadata_ignores_configured_live_model(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
        monkeypatch.setattr(settings, "LLM_RATIONALE_MODEL", "google/gemini-live")

        metadata = get_llm_metadata("rationale")

        assert metadata["model"] == "mock"


class TestCallLlmText:
    def test_returns_text(self):
        with patch(_PATCH_TARGET, return_value="Some rationale text.") as m:
            assert call_llm_text("prompt") == "Some rationale text."
        assert m.call_count == 1

    def test_truncated_text_response_does_not_retry(self):
        with patch(
            _PATCH_TARGET,
            side_effect=LLMResponseTruncated("rationale truncated"),
        ) as m:
            with pytest.raises(LLMResponseTruncated, match="rationale truncated"):
                call_llm_text("prompt")
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
        monkeypatch.setattr(settings, "LLM_RATIONALE_MAX_TOKENS", 2048)

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
        assert payload["max_tokens"] == 2048

    def test_decomposition_uses_larger_token_budget(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
        monkeypatch.setattr(settings, "LLM_API_KEY", "")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")
        monkeypatch.setattr(settings, "LLM_BASE_URL", "")
        monkeypatch.setattr(settings, "LLM_DECOMPOSITION_MODEL", "")
        monkeypatch.setattr(settings, "LLM_DECOMPOSITION_MAX_TOKENS", 8192)

        with patch(
            "src.llm_client.client._post_json",
            return_value={
                "choices": [
                    {"message": {"content": '[{"name": "Task"}]'}}
                ]
            },
        ) as post_json:
            assert call_llm_json("prompt") == [{"name": "Task"}]

        payload = post_json.call_args.kwargs["payload"]
        assert payload["max_tokens"] == 8192

    def test_anthropic_max_tokens_stop_reason_is_actionable(self):
        class FakeMessages:
            def create(self, **kwargs):
                _ = kwargs
                return type(
                    "Response",
                    (),
                    {
                        "stop_reason": "max_tokens",
                        "content": [type("Content", (), {"text": "partial"})()],
                    },
                )()

        class FakeClient:
            messages = FakeMessages()

        with patch("src.llm_client.client._build_anthropic_client", return_value=FakeClient()):
            with pytest.raises(RuntimeError, match="truncated at max_tokens"):
                _call_anthropic(
                    "prompt",
                    model="claude",
                    api_key="key",
                    purpose="decomposition",
                    max_tokens=4096,
                )

    def test_openai_compatible_decomposition_length_finish_reason_is_actionable(self):
        with patch(
            "src.llm_client.client._post_json",
            return_value={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '[{"name": "unfinished'},
                    }
                ]
            },
        ):
            with pytest.raises(LLMResponseTruncated) as exc_info:
                _call_openai_compatible(
                    "prompt",
                    model="model",
                    api_key="key",
                    base_url="https://api.example.com/v1",
                    purpose="decomposition",
                )
        assert "valid JSON" in str(exc_info.value)
        assert "LLM_DECOMPOSITION_MAX_TOKENS" in str(exc_info.value)

    def test_openai_compatible_rationale_length_finish_reason_is_actionable(self):
        with patch(
            "src.llm_client.client._post_json",
            return_value={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "partial rationale"},
                    }
                ]
            },
        ):
            with pytest.raises(LLMResponseTruncated) as exc_info:
                _call_openai_compatible(
                    "prompt",
                    model="model",
                    api_key="key",
                    base_url="https://api.example.com/v1",
                    purpose="rationale",
                    max_tokens=2048,
                )
        assert "text response" in str(exc_info.value)
        assert "LLM_RATIONALE_MAX_TOKENS above 2048" in str(exc_info.value)

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
