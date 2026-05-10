# =============================================================================
# src/orchestration/nodes/write_events.py — Write approved events to calendar
# =============================================================================
# Called only after the user clicks "Approve".  Creates each proposed event
# on the user's Google Calendar (or mock calendar).
#
# READS FROM STATE:  final_schedule
# WRITES TO STATE:   write_results
# =============================================================================

from __future__ import annotations

import datetime
from typing import Any

from config.settings import settings
from src.orchestration.debug_trace import make_trace_event, trace_update
from src.orchestration.state import AgentState


def write_events_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: write all approved events to the calendar.

    STEPS:
    1. Read final_schedule from state.
    2. Branch on settings.CALENDAR_MODE:
       a. "mock":
          - For each event, call mock_calendar.create_mock_event(
                event["name"], event["description"],
                parse(event["start"]), parse(event["end"])
            ).
       b. "live":
          - Call events.create_events_batch(final_schedule).
    3. Collect all API responses into a list.
    4. Return {"write_results": responses}.
    """
    final_schedule = state.get("final_schedule")
    if not isinstance(final_schedule, list):
        raise ValueError(
            "write_events_node: final_schedule missing or not a list "
            f"(got {type(final_schedule).__name__})"
        )

    mode = settings.CALENDAR_MODE
    responses: list[dict[str, Any]] = []

    if mode == "mock":
        from src.calendar_api.mock_calendar import create_mock_event

        for event in final_schedule:
            start_dt = datetime.datetime.fromisoformat(event["start"])
            end_dt = datetime.datetime.fromisoformat(event["end"])
            responses.append(
                create_mock_event(
                    event["name"], event["description"], start_dt, end_dt
                )
            )
    elif mode == "live":
        from src.calendar_api.events import create_events_batch

        responses = create_events_batch(
            final_schedule,
            calendar_id=settings.GOOGLE_CALENDAR_ID,
            color_id=settings.AGENT_EVENT_COLOR_ID,
        )
    else:
        raise ValueError(
            f"write_events_node: unknown CALENDAR_MODE {mode!r}; "
            "expected 'mock' or 'live'"
        )

    trace = make_trace_event(
        "write_events",
        summary={
            "calendar_mode": mode,
            "requested_event_count": len(final_schedule),
            "written_event_count": len(responses),
        },
        details={
            "event_names": [
                event.get("name", "Untitled event")
                for event in final_schedule
            ],
            "calendar_id": settings.GOOGLE_CALENDAR_ID,
            "agent_event_color_id": settings.AGENT_EVENT_COLOR_ID,
        },
    )

    return {"write_results": responses, **trace_update(trace)}
