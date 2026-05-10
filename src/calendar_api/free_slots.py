# =============================================================================
# src/calendar_api/free_slots.py — Free-slot computation
# =============================================================================
# Given a list of busy blocks and the user's working-hour preferences,
# computes available time slots that the scheduler can use.
#
# This module is pure logic with no API calls — fully unit-testable.
#
# STEPS TO COMPLETE:
# 1. Implement compute_free_slots().
# 2. Implement _day_working_window() helper.
# =============================================================================

from __future__ import annotations

import datetime


def compute_free_slots(
    busy_blocks: list[dict[str, str]],
    horizon_start: datetime.datetime,
    horizon_end: datetime.datetime,
    work_start: datetime.time,
    work_end: datetime.time,
    include_weekends: bool = False,
) -> list[dict[str, str]]:
    """Compute free time slots between busy blocks within working hours.

    Args:
        busy_blocks: Sorted list of {"start": <ISO>, "end": <ISO>} dicts.
        horizon_start: Earliest datetime to consider (now).
        horizon_end: Latest datetime to consider (deadline).
        work_start: Daily working hours start (e.g. 09:00).
        work_end: Daily working hours end (e.g. 18:00).
        include_weekends: If False, skip Saturday (5) and Sunday (6).

    Returns:
        List of {"start": <ISO>, "end": <ISO>} free-slot dicts, sorted
        chronologically.

    STEPS:
    1. Generate a list of working-day dates from horizon_start.date()
       to horizon_end.date() (inclusive).
       a. Skip weekends unless include_weekends is True.
    2. For each working day, compute the working window:
       a. day_start = datetime.combine(day, work_start, tzinfo=...)
       b. day_end   = datetime.combine(day, work_end,   tzinfo=...)
       c. Clamp day_start to max(day_start, horizon_start).
       d. Clamp day_end   to min(day_end,   horizon_end).
       e. If day_start >= day_end, skip this day.
    3. Collect all busy blocks that overlap with this day's window.
       a. Merge overlapping busy blocks to avoid double-counting.
    4. Walk through the day window:
       a. current_time = day_start
       b. For each busy block in this day (sorted):
          - If busy.start > current_time → gap found → append free slot.
          - Advance current_time = max(current_time, busy.end).
       c. After all busy blocks, if current_time < day_end → final gap.
    5. Return the full list of free slots across all days.
    """
    if horizon_start >= horizon_end:
        return []

    # Parse and sort busy intervals once. Keep only intervals that intersect the horizon.
    parsed_busy: list[tuple[datetime.datetime, datetime.datetime]] = []
    for block in busy_blocks:
        block_start = datetime.datetime.fromisoformat(block["start"])
        block_end = datetime.datetime.fromisoformat(block["end"])

        if block_end <= horizon_start or block_start >= horizon_end:
            continue

        start = max(block_start, horizon_start)
        end = min(block_end, horizon_end)
        if start < end:
            parsed_busy.append((start, end))

    parsed_busy.sort(key=lambda item: item[0])

    # Merge overlaps once globally to avoid re-merging per day window.
    merged_busy: list[tuple[datetime.datetime, datetime.datetime]] = []
    for interval_start, interval_end in parsed_busy:
        if not merged_busy or merged_busy[-1][1] < interval_start:
            merged_busy.append((interval_start, interval_end))
        else:
            last_start, last_end = merged_busy[-1]
            merged_busy[-1] = (last_start, max(last_end, interval_end))

    free_slots: list[dict[str, str]] = []

    tz = horizon_start.tzinfo
    current_day = horizon_start.date()
    last_day = horizon_end.date()

    busy_idx = 0
    busy_count = len(merged_busy)

    while current_day <= last_day:
        is_weekend = current_day.weekday() >= 5
        if not include_weekends and is_weekend:
            current_day += datetime.timedelta(days=1)
            continue

        day_start, day_end = _day_working_window(current_day, work_start, work_end, tz)
        day_start = max(day_start, horizon_start)
        day_end = min(day_end, horizon_end)

        if day_start >= day_end:
            current_day += datetime.timedelta(days=1)
            continue

        # Skip busy intervals that end before this day's window.
        while busy_idx < busy_count and merged_busy[busy_idx][1] <= day_start:
            busy_idx += 1

        # Walk overlaps directly from merged intervals; no per-day temp merge list.
        current_time = day_start
        scan_idx = busy_idx
        while scan_idx < busy_count and merged_busy[scan_idx][0] < day_end:
            busy_start = max(merged_busy[scan_idx][0], day_start)
            busy_end = min(merged_busy[scan_idx][1], day_end)
            if busy_start > current_time:
                free_slots.append(
                    {"start": current_time.isoformat(), "end": busy_start.isoformat()}
                )
            if busy_end > current_time:
                current_time = busy_end

            # Current merged interval continues past this day; next intervals cannot overlap this day.
            if merged_busy[scan_idx][1] > day_end:
                break
            scan_idx += 1

        if current_time < day_end:
            free_slots.append({"start": current_time.isoformat(), "end": day_end.isoformat()})

        current_day += datetime.timedelta(days=1)

    return free_slots


def _day_working_window(
    day: datetime.date,
    work_start: datetime.time,
    work_end: datetime.time,
    tz: datetime.tzinfo | None = None,
) -> tuple[datetime.datetime, datetime.datetime]:
    """Return the (start_dt, end_dt) working window for a single day.

    STEPS:
    1. Combine day + work_start + tz → start_dt.
    2. Combine day + work_end   + tz → end_dt.
    3. Return (start_dt, end_dt).
    """
    start_dt = datetime.datetime.combine(day, work_start, tzinfo=tz)
    end_dt = datetime.datetime.combine(day, work_end, tzinfo=tz)
    return start_dt, end_dt
