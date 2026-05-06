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
# Monday = 0 ... Friday = 4. Weekends produce no busy blocks (dict miss →
# empty list), so Saturday and Sunday are fully free within work hours —
# they act as an implicit large-block scenario without any extra code.
#
# =============================================================================
# TEST SCENARIO MAP  (assumes work_start=09:00, work_end=18:00)
# =============================================================================
#
# Day        Free slots                       Max   Purpose
# ---------  -------------------------------  ----  ---------------------------
# Monday     30m | 60m | 150m | 120m          150m  Mixed sizes — tests all
#            (morning fragments + solid             schedulers against varied
#             mid-day and afternoon blocks)         slot inventory
#
# Tuesday    360m afternoon only               360m  Morning BLOCKED — forces
#            (09:00-12:00 fully busy)               energy_aware satisficing:
#                                                   high-complexity tasks must
#                                                   accept afternoon (diff=1)
#
# Wednesday  ~30m evening only                  30m  Near-FULLY BLOCKED — tasks
#            (09:00-17:30 covered by two             >30m cannot be placed here;
#             back-to-back meetings)                 tests graceful skip-ahead
#
# Thursday   30m|45m|30m|45m|45m|30m|30m       45m  HEAVILY FRAGMENTED — max
#            (seven short meetings scatter           slot is 45m; any task
#             the day into tiny gaps)               >45m must wait for Friday
#
# Friday     300m morning | 180m afternoon     300m  LARGE BLOCKS — canonical
#            (one meeting at 14:00-15:00)           day for min_fragmentation
#                                                   large-block preference and
#                                                   energy_aware morning peak
#
# Weekend    Full work-hour window (no busy)   540m  IMPLICIT large-block test;
# (Sat/Sun)  slots — entirely free                  also exercises multi-week
#                                                   scheduling near deadline
# =============================================================================
#
# KEY BEHAVIOURS THIS MATRIX EXERCISES:
#
# deadline_first
#   - Packs Monday's 30/60min morning gaps first, then mid-day/afternoon
#   - Jumps over Wednesday's blocked day cleanly
#   - Cascades into Thursday small slots for short tasks only
#   - Moves to Friday's 300min block for any task >45min that didn't fit Thu
#
# min_fragmentation
#   - Shuffle reordering (longer tasks first) means large tasks claim
#     Friday 300min / Monday 150min before smaller tasks consume them
#   - Thursday's 45m ceiling forces large tasks to skip ahead — tests that
#     min_allowed_start + earliest-fit doesn't cascade into far-future slots
#
# energy_aware  (morning=high, afternoon=medium, evening=low default)
#   - Tuesday: NO morning slots → satisficing must accept afternoon for any
#     complexity level; verifies pass-0 miss triggers pass-1 fallback
#   - Wednesday: only evening slot → satisficing reaches pass-2 fallback
#   - Friday: morning slots available → high-complexity tasks placed at peak
#   - Monday: morning fragments (30m/60m) → tests short tasks fill morning,
#     longer tasks fall through to afternoon
_WEEKDAY_PATTERN: dict[int, list[tuple[str, str, str]]] = {
    0: [  # Monday — MIXED: fragmented morning, solid mid-day, solid afternoon
        # Free: 09:00-09:30 (30m) | 10:00-11:00 (60m) |
        #       11:30-14:00 (150m) | 16:00-18:00 (120m)
        ("Team standup",     "09:30", "10:00"),
        ("1:1 with manager", "11:00", "11:30"),
        ("Sprint planning",  "14:00", "16:00"),
    ],
    1: [  # Tuesday — MORNING BLOCKED: large afternoon block only
        # Free: 12:00-18:00 (360m)
        # Triggers energy_aware satisficing: no morning available at all
        ("All-hands meeting", "09:00", "12:00"),
    ],
    2: [  # Wednesday — NEAR-FULLY BLOCKED: back-to-back all day
        # Free: 17:30-18:00 (30m evening only)
        # Tasks >30m are skipped; schedulers must look ahead to Thursday/Friday
        ("Strategy session",  "09:00", "13:00"),
        ("Planning workshop", "13:00", "17:30"),
    ],
    3: [  # Thursday — HEAVILY FRAGMENTED: seven meetings, max gap = 45m
        # Free: 09:00-09:30 (30m) | 10:00-10:45 (45m) | 11:30-12:00 (30m) |
        #       13:00-13:45 (45m) | 14:30-15:15 (45m) | 16:00-16:30 (30m) |
        #       17:30-18:00 (30m)
        # Any task requiring >45m cannot be placed here → must wait for Friday
        ("Standup",       "09:30", "10:00"),
        ("Design review", "10:45", "11:30"),
        ("Lunch sync",    "12:00", "13:00"),
        ("Code review",   "13:45", "14:30"),
        ("Demo prep",     "15:15", "16:00"),
        ("Team retro",    "16:30", "17:30"),
    ],
    4: [  # Friday — LARGE BLOCKS: 5hr morning + 3hr afternoon
        # Free: 09:00-14:00 (300m) | 15:00-18:00 (180m)
        # Canonical large-block day: min_fragmentation's preferred target;
        # energy_aware places high-complexity tasks in the morning peak
        ("End-of-week sync", "14:00", "15:00"),
    ],
    # Saturday (5) and Sunday (6) are absent → no busy blocks → fully free.
    # compute_free_slots will produce one large slot per weekend day within
    # work hours. This implicitly tests scheduling across week boundaries.
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