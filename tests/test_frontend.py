# =============================================================================
# tests/test_frontend.py — Frontend module tests
# =============================================================================
# Tests for the Streamlit frontend components.
#
# NOTE: Streamlit widgets can be tricky to unit-test.  Consider using
# streamlit.testing.v1 (AppTest) for integration-style tests, or test
# the underlying logic functions directly.
#
# STEPS TO COMPLETE:
# 1. Write tests for the intake form validation logic.
# 2. Write tests for schedule display formatting.
# 3. Write tests for approval button state handling.
# =============================================================================

from __future__ import annotations

import datetime
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from src.frontend import approval_controls
from src.frontend import debug_panel
from src.frontend import intake_form
from src.frontend import schedule_display


@contextmanager
def _noop_context_manager(*args, **kwargs) -> Iterator[None]:
    _ = args, kwargs
    yield


class _DummyColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = exc_type, exc, tb
        return False


def _patch_intake_streamlit(
    monkeypatch: pytest.MonkeyPatch,
    *,
    goal: str,
    deadline: datetime.date,
    context: str,
    work_start: datetime.time,
    work_end: datetime.time,
    max_session_minutes: int,
    submitted: bool,
) -> list[str]:
    """Patch Streamlit calls used by render_intake_form and return captured errors."""
    error_messages: list[str] = []

    monkeypatch.setattr(intake_form.st, "form", _noop_context_manager)
    monkeypatch.setattr(intake_form.st, "text_input", lambda *args, **kwargs: goal)
    monkeypatch.setattr(intake_form.st, "date_input", lambda *args, **kwargs: deadline)
    monkeypatch.setattr(intake_form.st, "text_area", lambda *args, **kwargs: context)

    def _columns(_count: int):
        return (_DummyColumn(), _DummyColumn())

    monkeypatch.setattr(intake_form.st, "columns", _columns)

    time_values = iter((work_start, work_end))
    monkeypatch.setattr(intake_form.st, "time_input", lambda *args, **kwargs: next(time_values))
    monkeypatch.setattr(
        intake_form.st,
        "number_input",
        lambda *args, **kwargs: max_session_minutes,
    )
    monkeypatch.setattr(
        intake_form.st,
        "form_submit_button",
        lambda *args, **kwargs: submitted,
    )
    monkeypatch.setattr(intake_form.st, "error", lambda message: error_messages.append(message))

    return error_messages


class TestIntakeFormValidation:
    """Test the validation rules in render_intake_form."""

    def test_empty_goal_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """Submitting with an empty goal should fail validation.

        STEPS:
        1. Extract the validation logic from render_intake_form into a
           testable function, or test via streamlit.testing.v1.AppTest.
        2. Provide an empty string for goal.
        3. Assert that the function returns None or raises an error.
        """
        today = datetime.date.today()
        errors = _patch_intake_streamlit(
            monkeypatch,
            goal="   ",
            deadline=today + datetime.timedelta(days=7),
            context="context",
            work_start=datetime.time(9, 0),
            work_end=datetime.time(18, 0),
            max_session_minutes=90,
            submitted=True,
        )

        result = intake_form.render_intake_form()

        assert result is None
        assert errors == ["Please describe your goal."]

    def test_past_deadline_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """A deadline in the past should fail validation.

        STEPS:
        1. Set deadline = datetime.date.today() - timedelta(days=1).
        2. Assert validation rejects it.
        """
        today = datetime.date.today()
        errors = _patch_intake_streamlit(
            monkeypatch,
            goal="Learn React",
            deadline=today - datetime.timedelta(days=1),
            context="context",
            work_start=datetime.time(9, 0),
            work_end=datetime.time(18, 0),
            max_session_minutes=90,
            submitted=True,
        )

        result = intake_form.render_intake_form()

        assert result is None
        assert errors == ["Deadline must be in the future."]

    def test_invalid_work_hours_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """work_start >= work_end should fail validation.

        STEPS:
        1. Set work_start = 18:00, work_end = 09:00.
        2. Assert validation rejects it.
        """
        today = datetime.date.today()
        errors = _patch_intake_streamlit(
            monkeypatch,
            goal="Learn React",
            deadline=today + datetime.timedelta(days=7),
            context="context",
            work_start=datetime.time(18, 0),
            work_end=datetime.time(9, 0),
            max_session_minutes=90,
            submitted=True,
        )

        result = intake_form.render_intake_form()

        assert result is None
        assert errors == ["Work start must be earlier than work end."]

    def test_valid_inputs_pass(self, monkeypatch: pytest.MonkeyPatch):
        """A complete, valid set of inputs should pass.

        STEPS:
        1. Provide valid goal, deadline (future), context, hours, session_len.
        2. Assert the returned dict has all expected keys.
        """
        today = datetime.date.today()
        errors = _patch_intake_streamlit(
            monkeypatch,
            goal="  Learn React basics  ",
            deadline=today + datetime.timedelta(days=10),
            context="  Some context  ",
            work_start=datetime.time(9, 0),
            work_end=datetime.time(18, 0),
            max_session_minutes=120,
            submitted=True,
        )

        result = intake_form.render_intake_form()

        assert errors == []
        assert result is not None
        assert result["goal"] == "Learn React basics"
        assert result["context"] == "Some context"
        assert result["max_session_minutes"] == 120
        assert result["work_start"] == datetime.time(9, 0)
        assert result["work_end"] == datetime.time(18, 0)
        assert isinstance(result["deadline"], datetime.date)


class TestScheduleDisplay:
    """Test schedule display formatting helpers."""

    def test_render_schedule_groups_by_date(self, sample_valid_schedule):
        """Events should be grouped by date for display.

        STEPS:
        1. Extract any formatting helper from schedule_display.py.
        2. Pass sample_valid_schedule.
        3. Assert events are grouped correctly.
        """
        grouped = schedule_display._group_events_by_day(sample_valid_schedule)

        assert len(grouped) == 2
        days = list(grouped.keys())
        assert days[0].isoformat() == "2026-04-06"
        assert days[1].isoformat() == "2026-04-07"
        assert len(grouped[days[0]]) == 2
        assert len(grouped[days[1]]) == 1


class TestDebugPanel:
    def test_format_debug_report_includes_trace_summaries(self):
        state = {
            "goal": "Learn Python",
            "deadline": "2026-05-15",
            "work_start": "09:00",
            "work_end": "18:00",
            "debug_trace": [
                {
                    "node": "decompose_goal",
                    "status": "success",
                    "summary": {"provider": "vertex_ai", "model": "google/gemini"},
                    "details": {
                        "items": [
                            {"name": "Set up Python", "duration_minutes": 60},
                            {"name": "Build calculator", "duration_minutes": 90},
                        ]
                    },
                },
                {
                    "node": "validate_candidates",
                    "status": "success",
                    "summary": {},
                    "details": {
                        "deadline_first": {
                            "passed": True,
                            "violation_count": 0,
                        }
                    },
                },
            ],
        }

        report = debug_panel.format_debug_report(state)

        assert "Goal: Learn Python" in report
        assert "decompose_goal [success]" in report
        assert "provider: vertex_ai" in report
        assert "Set up Python" in report
        assert "deadline_first: passed=True violations=0" in report


class TestApprovalControls:
    """Test strategy approval/rejection button behavior."""

    def test_identical_candidates_approve(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(approval_controls.st, "button", lambda *args, **kwargs: True)
        monkeypatch.setattr(approval_controls.st, "divider", lambda: None)

        action, strategy = approval_controls.render_strategy_buttons(candidates_identical=True)

        assert (action, strategy) == ("approve", "deadline_first")

    def test_reject_all(self, monkeypatch: pytest.MonkeyPatch):
        button_presses = iter((False, False, False, True))

        monkeypatch.setattr(
            approval_controls.st,
            "button",
            lambda *args, **kwargs: next(button_presses),
        )
        monkeypatch.setattr(
            approval_controls.st,
            "columns",
            lambda _count: (_DummyColumn(), _DummyColumn(), _DummyColumn()),
        )
        monkeypatch.setattr(approval_controls.st, "divider", lambda: None)

        action, strategy = approval_controls.render_strategy_buttons(candidates_identical=False)

        assert (action, strategy) == ("reject", None)
