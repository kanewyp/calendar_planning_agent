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


def _parse_event_boundary(
    event_boundary: dict[str, str],
    *,
    is_end_boundary: bool,
) -> datetime.datetime | None:
    """Convert Google Calendar boundary payload to a timezone-aware datetime.

    Google returns either:
    - {"dateTime": "..."} for timed events
    - {"date": "YYYY-MM-DD"} for all-day events
    """
    raw_datetime = event_boundary.get("dateTime")
    if raw_datetime:
        parsed = datetime.datetime.fromisoformat(raw_datetime)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed

    raw_date = event_boundary.get("date")
    if not raw_date:
        return None

    day = datetime.date.fromisoformat(raw_date)
    if is_end_boundary:
        parsed = datetime.datetime.combine(day, datetime.time.min)
    else:
        parsed = datetime.datetime.combine(day, datetime.time.min)

    return parsed.replace(tzinfo=datetime.timezone.utc)


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
    busy_blocks: list[dict[str, str]] = []
    page_token: str | None = None

    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )

        for item in response.get("items", []):
            start_data = item.get("start", {})
            end_data = item.get("end", {})

            start_dt = _parse_event_boundary(start_data, is_end_boundary=False)
            end_dt = _parse_event_boundary(end_data, is_end_boundary=True)
            if not start_dt or not end_dt or start_dt >= end_dt:
                continue

            busy_blocks.append(
                {"start": start_dt.isoformat(), "end": end_dt.isoformat()}
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

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
        # dateTime includes offset; keeping payload minimal avoids invalid tz labels.
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
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
        description = str(event.get("description", ""))
        response = create_event(
            summary=event["name"],
            description=description,
            start=start_dt,
            end=end_dt,
            calendar_id=calendar_id,
        )
        responses.append(response)
    return responses
