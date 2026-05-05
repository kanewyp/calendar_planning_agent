# =============================================================================
# src/calendar_api/mock_calendar.py — Mock calendar for development & testing
# =============================================================================
# Returns busy blocks generated from a fixed weekday pattern so the entire
# pipeline can be developed and tested without Google OAuth credentials.
# Activated when CALENDAR_MODE=mock in .env.
#
# The events are generated on the fly from `_WEEKDAY_PATTERN` for every
# weekday inside the requested [time_min, time_max] window. This means the
# mock calendar always has events around "today" instead of going stale at
# a hardcoded date.
# =============================================================================

from __future__ import annotations

import datetime
import uuid
from typing import Any


# Per-weekday list of (summary, start "HH:MM", end "HH:MM"). Times are UTC.
# Monday = 0 ... Friday = 4. Weekends are skipped.
_WEEKDAY_PATTERN: dict[int, list[tuple[str, str, str]]] = {
    0: [  # Monday
        ("Team standup", "09:30", "10:00"),
        ("Sprint planning", "14:00", "15:30"),
    ],
    1: [  # Tuesday
        ("1:1 with manager", "11:00", "11:30"),
    ],
    2: [  # Wednesday
        ("Design review", "10:00", "11:00"),
        ("Lunch meeting", "12:00", "13:00"),
    ],
    3: [  # Thursday
        ("Team standup", "09:30", "10:00"),
        ("Workshop", "14:00", "16:00"),
    ],
    4: [  # Friday
        ("Demo day", "15:00", "16:00"),
    ],
}


def _parse_hhmm(value: str) -> datetime.time:
    hour, minute = value.split(":")
    return datetime.time(int(hour), int(minute), tzinfo=datetime.timezone.utc)


def _events_on_day(day: datetime.date) -> list[dict[str, str]]:
    """Concrete event dicts for the weekday pattern on `day`, UTC-anchored."""
    pattern = _WEEKDAY_PATTERN.get(day.weekday(), [])
    events: list[dict[str, str]] = []
    for _summary, start_str, end_str in pattern:
        start_dt = datetime.datetime.combine(day, _parse_hhmm(start_str))
        end_dt = datetime.datetime.combine(day, _parse_hhmm(end_str))
        events.append(
            {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            }
        )
    return events


def fetch_mock_busy_blocks(
    time_min: datetime.datetime,
    time_max: datetime.datetime,
) -> list[dict[str, str]]:
    """Return mock busy blocks within the given time window.

    Mirrors the interface of calendar_api.events.fetch_busy_blocks().

    Events are generated from `_WEEKDAY_PATTERN` for every weekday between
    `time_min` and `time_max` so the mock calendar tracks "today" instead of
    a baked-in date.

    Args:
        time_min: Start of window (timezone-aware).
        time_max: End of window (timezone-aware).

    Returns:
        Sorted list of {"start": <ISO>, "end": <ISO>} dicts.
    """
    if time_min >= time_max:
        return []

    busy_blocks: list[dict[str, str]] = []
    current = time_min.date()
    last_day = time_max.date()

    while current <= last_day:
        for event in _events_on_day(current):
            event_start = datetime.datetime.fromisoformat(event["start"])
            event_end = datetime.datetime.fromisoformat(event["end"])
            if event_end <= time_min or event_start >= time_max:
                continue
            busy_blocks.append(event)
        current += datetime.timedelta(days=1)

    busy_blocks.sort(key=lambda block: block["start"])
    return busy_blocks


def create_mock_event(
    summary: str,
    description: str,
    start: datetime.datetime,
    end: datetime.datetime,
) -> dict[str, Any]:
    """Simulate creating an event (just print + return a fake response)."""
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
