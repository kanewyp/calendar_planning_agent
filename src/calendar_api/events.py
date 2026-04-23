# =============================================================================
# src/calendar_api/events.py — Fetch and create Google Calendar events
# =============================================================================
# Provides functions to read existing events (busy blocks) and to write new
# events scheduled by the agent.  Operates in STRICT ADD-ONLY mode — no
# update or delete calls are ever made.
#
# STEPS TO COMPLETE:
# 1. Implement fetch_busy_blocks() to pull events from the calendar.
# 2. Implement create_event() to write a single event.
# 3. Implement create_events_batch() to write a list of events.
# =============================================================================

from __future__ import annotations

import datetime
from typing import Any

from src.calendar_api.auth import build_calendar_service

# Custom tag embedded in the description of every agent-created event
AGENT_TAG = "[CALENDAR_AGENT]"


def fetch_busy_blocks(
    time_min: datetime.datetime,
    time_max: datetime.datetime,
    calendar_id: str = "primary",
) -> list[dict[str, str]]:
    """Fetch all events between time_min and time_max and return busy blocks.

    Args:
        time_min: Start of the look-ahead window (inclusive), timezone-aware.
        time_max: End of the look-ahead window (exclusive), timezone-aware.
        calendar_id: Google Calendar ID, default "primary".

    Returns:
        List of dicts: [{"start": <ISO str>, "end": <ISO str>}, ...]

    STEPS:
    1. Call build_calendar_service() to get the service object.
    2. Use service.events().list(
           calendarId=calendar_id,
           timeMin=time_min.isoformat(),
           timeMax=time_max.isoformat(),
           singleEvents=True,
           orderBy="startTime",
       ).execute()
    3. Iterate over the returned "items".
       a. For each event, extract start["dateTime"] and end["dateTime"].
       b. Skip all-day events (they have "date" instead of "dateTime").
       c. Append {"start": <start_iso>, "end": <end_iso>} to the result list.
    4. Return the list sorted by start time.
    """
    service = build_calendar_service()
    response = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    busy_blocks: list[dict[str, str]] = []
    for item in response.get("items", []):
        start = item.get("start", {}).get("dateTime")
        end = item.get("end", {}).get("dateTime")
        if not start or not end:
            continue
        busy_blocks.append({"start": start, "end": end})

    busy_blocks.sort(key=lambda b: b["start"])
    return busy_blocks


def create_event(
    summary: str,
    description: str,
    start: datetime.datetime,
    end: datetime.datetime,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Create a single event on the user's Google Calendar.

    The event description is prefixed with AGENT_TAG so it can later be
    identified as agent-created.

    Args:
        summary: Event title (subtask name).
        description: Event description (subtask description).
        start: Event start datetime, timezone-aware.
        end: Event end datetime, timezone-aware.
        calendar_id: Google Calendar ID, default "primary".

    Returns:
        The Google Calendar API response dict for the created event.

    STEPS:
    1. Build the event body dict:
       {
           "summary": summary,
           "description": f"{AGENT_TAG} {description}",
           "start": {"dateTime": start.isoformat(), "timeZone": <tz>},
           "end":   {"dateTime": end.isoformat(),   "timeZone": <tz>},
       }
    2. Call service.events().insert(calendarId=calendar_id, body=event_body).execute().
    3. Return the response.

    SECURITY NOTE:
    - This function must NEVER call events().update() or events().delete().
    """
    service = build_calendar_service()
    event_body = {
        "summary": summary,
        "description": f"{AGENT_TAG} {description}",
        "start": {"dateTime": start.isoformat(), "timeZone": str(start.tzinfo)},
        "end": {"dateTime": end.isoformat(), "timeZone": str(end.tzinfo)},
    }
    return service.events().insert(calendarId=calendar_id, body=event_body).execute()


def create_events_batch(
    events: list[dict[str, Any]],
    calendar_id: str = "primary",
) -> list[dict[str, Any]]:
    """Write multiple events to the calendar sequentially.

    Args:
        events: List of event dicts, each with keys:
            name, description, start (ISO str), end (ISO str).
        calendar_id: Google Calendar ID.

    Returns:
        List of Google Calendar API response dicts.

    STEPS:
    1. Iterate over the events list.
    2. For each event, parse start/end strings to datetime objects.
    3. Call create_event(name, description, start_dt, end_dt, calendar_id).
    4. Collect and return all responses.
    """
    responses: list[dict[str, Any]] = []
    for event in events:
        start_dt = datetime.datetime.fromisoformat(event["start"])
        end_dt = datetime.datetime.fromisoformat(event["end"])
        response = create_event(
            summary=event["name"],
            description=event["description"],
            start=start_dt,
            end=end_dt,
            calendar_id=calendar_id,
        )
        responses.append(response)
    return responses
