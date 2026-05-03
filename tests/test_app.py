from __future__ import annotations

from src.app import _format_planning_error


def test_format_planning_error_explains_missing_llm_key():
    root_cause = ValueError("LLM API key is not set. Set LLM_API_KEY.")
    exc = RuntimeError(
        "Goal decomposition failed: unable to get a valid subtask list from the LLM"
    )
    exc.__cause__ = root_cause

    message = _format_planning_error(exc)

    assert "LLM API key is not set" in message
    assert "CALENDAR_MODE=mock skips Google Calendar credentials" in message
    assert "planning still needs an LLM" in message
    assert "LLM_PROVIDER=mock" in message


def test_format_planning_error_keeps_anthropic_key_compatibility():
    root_cause = ValueError("ANTHROPIC_API_KEY is not set")
    exc = RuntimeError("Goal decomposition failed")
    exc.__cause__ = root_cause

    message = _format_planning_error(exc)

    assert "ANTHROPIC_API_KEY is not set" in message
    assert "LLM_API_KEY" in message


def test_format_planning_error_includes_unknown_failure():
    exc = RuntimeError("unexpected graph failure")

    assert _format_planning_error(exc) == "Planning failed: unexpected graph failure"
