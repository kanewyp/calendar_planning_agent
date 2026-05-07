from __future__ import annotations

import json

from src.frontend.calendar_html import (
    FULLCALENDAR_CDN,
    _initial_calendar_date,
    build_calendar_html,
)


def _proposed_event(start: str, end: str, title: str = "Task") -> dict:
    return {
        "title": title,
        "start": start,
        "end": end,
        "backgroundColor": "#1a73e8",
        "borderColor": "#1a73e8",
        "extendedProps": {"kind": "proposed", "description": "", "strategy": "deadline_first"},
    }


def _existing_event(start: str, end: str) -> dict:
    return {
        "title": "Busy",
        "start": start,
        "end": end,
        "backgroundColor": "#9aa0a6",
        "borderColor": "#9aa0a6",
        "extendedProps": {"kind": "existing", "description": "", "strategy": None},
    }


class TestInitialCalendarDate:
    def test_uses_first_proposed_event_date(self) -> None:
        events = [
            _existing_event("2026-05-04T09:00:00+00:00", "2026-05-04T10:00:00+00:00"),
            _proposed_event("2026-05-06T11:00:00+00:00", "2026-05-06T12:00:00+00:00"),
        ]
        assert _initial_calendar_date(events, fallback_iso=None) == "2026-05-06"

    def test_falls_back_to_first_event_when_no_proposed(self) -> None:
        events = [_existing_event("2026-05-08T09:00:00+00:00", "2026-05-08T10:00:00+00:00")]
        assert _initial_calendar_date(events, fallback_iso="2099-01-01") == "2026-05-08"

    def test_uses_fallback_iso_when_no_events(self) -> None:
        assert _initial_calendar_date([], fallback_iso="2026-12-31") == "2026-12-31"

    def test_today_when_nothing_supplied(self) -> None:
        result = _initial_calendar_date([], fallback_iso=None)
        assert len(result) == 10 and result[4] == "-" and result[7] == "-"


class TestBuildCalendarHtml:
    def test_empty_events_produces_valid_html_with_empty_array(self) -> None:
        html = build_calendar_html([], fallback_date_iso="2026-05-04")

        assert "<!DOCTYPE html>" in html
        assert FULLCALENDAR_CDN in html
        assert "var EVENTS = [];" in html
        assert 'var INITIAL_DATE = "2026-05-04";' in html
        assert 'var INITIAL_VIEW = "dayGridMonth";' in html

    def test_events_are_json_serialized_into_script(self) -> None:
        events = [
            _proposed_event(
                "2026-05-06T11:00:00+00:00",
                "2026-05-06T12:00:00+00:00",
                title="Write tests",
            )
        ]

        html = build_calendar_html(events)

        serialized = json.dumps(events).replace("</", "<\\/")
        assert f"var EVENTS = {serialized};" in html
        assert "Write tests" in html
        assert 'var INITIAL_DATE = "2026-05-06";' in html

    def test_view_and_slot_bounds_propagate(self) -> None:
        html = build_calendar_html(
            [],
            initial_view="timeGridWeek",
            work_start="07:30",
            work_end="22:00",
            fallback_date_iso="2026-05-04",
        )

        assert 'var INITIAL_VIEW = "timeGridWeek";' in html
        assert 'var SLOT_MIN = "07:30";' in html
        assert 'var SLOT_MAX = "22:00";' in html

    def test_explicit_initial_date_overrides_event_derivation(self) -> None:
        events = [
            _proposed_event("2026-05-06T11:00:00+00:00", "2026-05-06T12:00:00+00:00"),
        ]
        html = build_calendar_html(events, initial_date="2027-01-15")

        assert 'var INITIAL_DATE = "2027-01-15";' in html

    def test_event_payload_xss_safe_via_json(self) -> None:
        events = [
            _proposed_event(
                "2026-05-06T11:00:00+00:00",
                "2026-05-06T12:00:00+00:00",
                title="</script><script>alert(1)</script>",
            )
        ]

        html = build_calendar_html(events)

        # json.dumps escapes the inner </script> via < so the host script
        # block cannot be terminated early by event payloads.
        assert "</script><script>alert(1)</script>" not in html
        assert "alert(1)" in html  # still present, just in the safe escaped form
