# =============================================================================
# tests/test_calendar_api.py — Calendar API module tests
# =============================================================================
# Tests for free-slot computation and mock calendar.
# Real Google Calendar API calls should NOT be tested here — those require
# integration tests with real credentials.
#
# STEPS TO COMPLETE:
# 1. Test compute_free_slots with various busy-block configurations.
# 2. Test mock calendar fetch/create functions.
# 3. Test edge cases: no busy blocks, all-day blocks, weekends.
# =============================================================================

from __future__ import annotations

import datetime

from src.calendar_api.free_slots import compute_free_slots
from src.calendar_api.mock_calendar import create_mock_event, fetch_mock_busy_blocks


UTC = datetime.timezone.utc


def dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute, tzinfo=UTC)


class TestComputeFreeSlots:
    """Test the free-slot computation logic."""

    def test_no_busy_blocks_gives_full_days(self, work_start, work_end):
        """With no busy blocks, every working day should be fully free.

        STEPS:
        1. Call compute_free_slots with empty busy_blocks list.
        2. Set horizon to a 3-day window.
        3. Assert result contains one free slot per working day,
           each spanning work_start to work_end.
        """
        free_slots = compute_free_slots(
            busy_blocks=[],
            horizon_start=dt(2026, 4, 6, 0),
            horizon_end=dt(2026, 4, 8, 23, 59),
            work_start=work_start,
            work_end=work_end,
        )

        assert free_slots == [
            {
                "start": "2026-04-06T09:00:00+00:00",
                "end": "2026-04-06T18:00:00+00:00",
            },
            {
                "start": "2026-04-07T09:00:00+00:00",
                "end": "2026-04-07T18:00:00+00:00",
            },
            {
                "start": "2026-04-08T09:00:00+00:00",
                "end": "2026-04-08T18:00:00+00:00",
            },
        ]

    def test_single_busy_block_splits_day(self, work_start, work_end):
        """A single busy block in the middle splits the day into two free slots.

        STEPS:
        1. Provide one busy block from 12:00 to 13:00.
        2. Assert two free slots: 09:00–12:00 and 13:00–18:00.
        """
        free_slots = compute_free_slots(
            busy_blocks=[
                {
                    "start": "2026-04-06T12:00:00+00:00",
                    "end": "2026-04-06T13:00:00+00:00",
                }
            ],
            horizon_start=dt(2026, 4, 6, 0),
            horizon_end=dt(2026, 4, 6, 23, 59),
            work_start=work_start,
            work_end=work_end,
        )

        assert free_slots == [
            {
                "start": "2026-04-06T09:00:00+00:00",
                "end": "2026-04-06T12:00:00+00:00",
            },
            {
                "start": "2026-04-06T13:00:00+00:00",
                "end": "2026-04-06T18:00:00+00:00",
            },
        ]

    def test_overlapping_busy_blocks_merged(self, work_start, work_end):
        """Overlapping busy blocks should be merged before gap computation.

        STEPS:
        1. Provide two overlapping blocks: 10:00–12:00 and 11:00–13:00.
        2. Assert they are treated as one block: 10:00–13:00.
        """
        free_slots = compute_free_slots(
            busy_blocks=[
                {
                    "start": "2026-04-06T10:00:00+00:00",
                    "end": "2026-04-06T12:00:00+00:00",
                },
                {
                    "start": "2026-04-06T11:00:00+00:00",
                    "end": "2026-04-06T13:00:00+00:00",
                },
            ],
            horizon_start=dt(2026, 4, 6, 0),
            horizon_end=dt(2026, 4, 6, 23, 59),
            work_start=work_start,
            work_end=work_end,
        )

        assert free_slots == [
            {
                "start": "2026-04-06T09:00:00+00:00",
                "end": "2026-04-06T10:00:00+00:00",
            },
            {
                "start": "2026-04-06T13:00:00+00:00",
                "end": "2026-04-06T18:00:00+00:00",
            },
        ]

    def test_weekends_excluded_by_default(self, work_start, work_end):
        """Saturday and Sunday should be skipped unless include_weekends=True.

        STEPS:
        1. Set horizon to span a weekend.
        2. Assert no free slots on Saturday/Sunday.
        """
        free_slots = compute_free_slots(
            busy_blocks=[],
            horizon_start=dt(2026, 4, 10, 0),
            horizon_end=dt(2026, 4, 13, 23, 59),
            work_start=work_start,
            work_end=work_end,
        )

        dates = {
            datetime.datetime.fromisoformat(slot["start"]).date()
            for slot in free_slots
        }
        assert dates == {
            datetime.date(2026, 4, 10),
            datetime.date(2026, 4, 13),
        }

    def test_weekends_included_if_flag_set(self, work_start, work_end):
        """With include_weekends=True, weekend days should produce free slots.

        STEPS:
        1. Same as above but include_weekends=True.
        2. Assert free slots exist on weekend days.
        """
        free_slots = compute_free_slots(
            busy_blocks=[],
            horizon_start=dt(2026, 4, 10, 0),
            horizon_end=dt(2026, 4, 13, 23, 59),
            work_start=work_start,
            work_end=work_end,
            include_weekends=True,
        )

        dates = [
            datetime.datetime.fromisoformat(slot["start"]).date()
            for slot in free_slots
        ]
        assert dates == [
            datetime.date(2026, 4, 10),
            datetime.date(2026, 4, 11),
            datetime.date(2026, 4, 12),
            datetime.date(2026, 4, 13),
        ]

    def test_horizon_clamping(self, work_start, work_end):
        """Free slots should be clamped to the horizon boundaries.

        STEPS:
        1. Set horizon_start to 14:00 today (mid-afternoon).
        2. Assert the first free slot starts at 14:00, not 09:00.
        """
        free_slots = compute_free_slots(
            busy_blocks=[],
            horizon_start=dt(2026, 4, 6, 14),
            horizon_end=dt(2026, 4, 6, 23, 59),
            work_start=work_start,
            work_end=work_end,
        )

        assert free_slots == [
            {
                "start": "2026-04-06T14:00:00+00:00",
                "end": "2026-04-06T18:00:00+00:00",
            }
        ]


class TestMockCalendar:
    """Test the mock calendar data module."""

    def test_fetch_returns_only_events_in_window(self):
        """mock fetch should filter events outside the time window.

        STEPS:
        1. Call fetch_mock_busy_blocks with a narrow 1-day window.
        2. Assert only events on that day are returned.
        """
        busy_blocks = fetch_mock_busy_blocks(
            dt(2026, 4, 8, 0),
            dt(2026, 4, 9, 0),
        )

        assert busy_blocks == [
            {
                "start": "2026-04-08T10:00:00+00:00",
                "end": "2026-04-08T11:00:00+00:00",
            },
            {
                "start": "2026-04-08T12:00:00+00:00",
                "end": "2026-04-08T13:00:00+00:00",
            },
        ]

    def test_create_mock_event_returns_dict(self):
        """create_mock_event should return a response-like dict.

        STEPS:
        1. Call create_mock_event with sample data.
        2. Assert the returned dict has "id" and "summary" keys.
        """
        response = create_mock_event(
            summary="Read React docs",
            description="Study the introductory docs.",
            start=dt(2026, 4, 6, 10),
            end=dt(2026, 4, 6, 11),
        )

        assert response["id"]
        assert response["summary"] == "Read React docs"
        assert response["description"] == "Study the introductory docs."
        assert response["status"] == "confirmed"
        assert response["start"]["dateTime"] == "2026-04-06T10:00:00+00:00"
        assert response["end"]["dateTime"] == "2026-04-06T11:00:00+00:00"
