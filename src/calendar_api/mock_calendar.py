# =============================================================================
# src/calendar_api/mock_calendar.py — Mock calendar for development & testing
# =============================================================================
# Returns hardcoded busy blocks so the entire pipeline can be developed and
# tested without Google OAuth credentials.  Activated when
# CALENDAR_MODE=mock in .env.
#
# STEPS TO COMPLETE:
# 1. Define realistic mock busy blocks spanning ~2 weeks.
# 2. Implement the same interface as the real calendar module.
# =============================================================================

from __future__ import annotations

import datetime
import uuid
from typing import Any


# ---------------------------------------------------------------------------
# Hardcoded mock events — edit these to match your testing scenarios
# ---------------------------------------------------------------------------
# Each dict has "summary", "start", "end" (ISO 8601 strings, UTC).
# These simulate a typical two-week calendar with meetings and events.
MOCK_EVENTS: list[dict[str, str]] = [
    # Week 1 — Monday
    {"summary": "Team standup",    "start": "2026-04-06T09:30:00+00:00", "end": "2026-04-06T10:00:00+00:00"},
    {"summary": "Sprint planning", "start": "2026-04-06T14:00:00+00:00", "end": "2026-04-06T15:30:00+00:00"},
    # Week 1 — Tuesday
    {"summary": "1:1 with manager","start": "2026-04-07T11:00:00+00:00", "end": "2026-04-07T11:30:00+00:00"},
    # Week 1 — Wednesday
    {"summary": "Design review",   "start": "2026-04-08T10:00:00+00:00", "end": "2026-04-08T11:00:00+00:00"},
    {"summary": "Lunch meeting",   "start": "2026-04-08T12:00:00+00:00", "end": "2026-04-08T13:00:00+00:00"},
    # Week 1 — Thursday
    {"summary": "Team standup",    "start": "2026-04-09T09:30:00+00:00", "end": "2026-04-09T10:00:00+00:00"},
    # Week 1 — Friday
    {"summary": "Demo day",        "start": "2026-04-10T15:00:00+00:00", "end": "2026-04-10T16:00:00+00:00"},
    # Week 2 — Monday
    {"summary": "Team standup",    "start": "2026-04-13T09:30:00+00:00", "end": "2026-04-13T10:00:00+00:00"},
    {"summary": "Backlog grooming","start": "2026-04-13T13:00:00+00:00", "end": "2026-04-13T14:00:00+00:00"},
    # Week 2 — Tuesday
    {"summary": "1:1 with manager","start": "2026-04-14T11:00:00+00:00", "end": "2026-04-14T11:30:00+00:00"},
    {"summary": "Workshop",        "start": "2026-04-14T14:00:00+00:00", "end": "2026-04-14T16:00:00+00:00"},
    # Week 2 — Wednesday
    {"summary": "Design review",   "start": "2026-04-15T10:00:00+00:00", "end": "2026-04-15T11:00:00+00:00"},
    # Week 2 — Thursday
    {"summary": "Team standup",    "start": "2026-04-16T09:30:00+00:00", "end": "2026-04-16T10:00:00+00:00"},
    # Week 2 — Friday
    {"summary": "Retro",           "start": "2026-04-17T16:00:00+00:00", "end": "2026-04-17T17:00:00+00:00"},
]


def fetch_mock_busy_blocks(
    time_min: datetime.datetime,
    time_max: datetime.datetime,
) -> list[dict[str, str]]:
    """Return mock busy blocks within the given time window.

    Mirrors the interface of calendar_api.events.fetch_busy_blocks().

    Args:
        time_min: Start of window (timezone-aware).
        time_max: End of window (timezone-aware).

    Returns:
        List of {"start": <ISO>, "end": <ISO>} dicts.

    STEPS:
    1. Iterate over MOCK_EVENTS.
    2. Parse each event's start/end strings to datetime objects.
    3. Keep only events where start >= time_min and end <= time_max.
    4. Return as [{"start": ..., "end": ...}, ...].
    """
    busy_blocks: list[dict[str, str]] = []

    for event in MOCK_EVENTS:
        event_start = datetime.datetime.fromisoformat(event["start"])
        event_end = datetime.datetime.fromisoformat(event["end"])

        # Treat any interval overlap as busy in the requested window.
        if event_end <= time_min or event_start >= time_max:
            continue

        busy_blocks.append(
            {
                "start": event_start.isoformat(),
                "end": event_end.isoformat(),
            }
        )

    busy_blocks.sort(key=lambda block: block["start"])
    return busy_blocks


def create_mock_event(
    summary: str,
    description: str,
    start: datetime.datetime,
    end: datetime.datetime,
) -> dict[str, Any]:
    """Simulate creating an event (just print + return a fake response).

    STEPS:
    1. Print a log line: f"[MOCK] Created event: {summary} {start} → {end}"
    2. Return a dict mimicking the Google API response, e.g.:
       {"id": "<uuid>", "summary": summary, "status": "confirmed", ...}
    """
    event_id = str(uuid.uuid4())
    print(f"[MOCK] Created event: {summary} {start.isoformat()} -> {end.isoformat()}")

    return {
        "id": event_id,
        "summary": summary,
        "description": description,
        "status": "confirmed",
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
        "htmlLink": f"https://mock.calendar/events/{event_id}",
    }
