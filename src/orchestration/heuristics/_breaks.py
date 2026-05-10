from __future__ import annotations

import datetime


def break_delta(break_minutes: int) -> datetime.timedelta:
    """Return a non-negative buffer duration between proposed sessions."""
    return datetime.timedelta(minutes=max(int(break_minutes), 0))


def next_allowed_start(
    event_end: datetime.datetime,
    break_minutes: int,
) -> datetime.datetime:
    """Earliest start time for the next proposed session."""
    return event_end + break_delta(break_minutes)
