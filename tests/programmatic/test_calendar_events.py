from __future__ import annotations

import pytest

from src.frontend.calendar_events import (
    EXISTING_COLOR,
    STRATEGY_COLORS,
    STRATEGY_STATE_KEYS,
    build_calendar_events,
)


def _proposed(name: str, start: str, end: str, description: str = "") -> dict:
    return {
        "name": name,
        "description": description,
        "start": start,
        "end": end,
    }


class TestBuildCalendarEvents:
    def test_empty_state_returns_empty_list(self) -> None:
        assert build_calendar_events({}, "deadline_first") == []

    def test_unknown_strategy_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            build_calendar_events({}, "not_a_strategy")

    def test_only_busy_blocks_marked_existing(self) -> None:
        state = {
            "busy_blocks": [
                {"start": "2026-05-04T09:00:00+00:00", "end": "2026-05-04T10:00:00+00:00"},
                {"start": "2026-05-04T13:00:00+00:00", "end": "2026-05-04T14:00:00+00:00"},
            ],
        }

        events = build_calendar_events(state, "deadline_first")

        assert len(events) == 2
        for event in events:
            assert event["extendedProps"]["kind"] == "existing"
            assert event["extendedProps"]["strategy"] is None
            assert event["backgroundColor"] == EXISTING_COLOR
            assert event["title"] == "Busy"

    def test_only_proposed_events_use_strategy_color(self) -> None:
        state = {
            "candidate_min_fragmentation": [
                _proposed(
                    "Write tests",
                    "2026-05-05T09:00:00+00:00",
                    "2026-05-05T10:30:00+00:00",
                    description="cover edge cases",
                ),
            ],
        }

        events = build_calendar_events(state, "min_fragmentation")

        assert len(events) == 1
        event = events[0]
        assert event["extendedProps"]["kind"] == "proposed"
        assert event["extendedProps"]["strategy"] == "min_fragmentation"
        assert event["extendedProps"]["description"] == "cover edge cases"
        assert event["backgroundColor"] == STRATEGY_COLORS["min_fragmentation"]
        assert event["title"] == "Write tests"

    def test_busy_and_proposed_combined(self) -> None:
        state = {
            "busy_blocks": [
                {"start": "2026-05-04T09:00:00+00:00", "end": "2026-05-04T10:00:00+00:00"},
            ],
            "candidate_deadline_first": [
                _proposed(
                    "Read paper",
                    "2026-05-04T11:00:00+00:00",
                    "2026-05-04T12:00:00+00:00",
                ),
                _proposed(
                    "Draft notes",
                    "2026-05-05T09:00:00+00:00",
                    "2026-05-05T10:00:00+00:00",
                ),
            ],
        }

        events = build_calendar_events(state, "deadline_first")

        kinds = [e["extendedProps"]["kind"] for e in events]
        assert kinds == ["existing", "proposed", "proposed"]
        assert events[0]["start"] == "2026-05-04T09:00:00+00:00"
        assert events[1]["backgroundColor"] == STRATEGY_COLORS["deadline_first"]

    def test_strategy_selects_correct_candidate_key(self) -> None:
        state = {
            "candidate_deadline_first": [
                _proposed("A", "2026-05-04T09:00:00+00:00", "2026-05-04T10:00:00+00:00"),
            ],
            "candidate_energy_aware": [
                _proposed("B", "2026-05-04T11:00:00+00:00", "2026-05-04T12:00:00+00:00"),
                _proposed("C", "2026-05-04T13:00:00+00:00", "2026-05-04T14:00:00+00:00"),
            ],
        }

        deadline_events = build_calendar_events(state, "deadline_first")
        energy_events = build_calendar_events(state, "energy_aware")

        assert [e["title"] for e in deadline_events] == ["A"]
        assert [e["title"] for e in energy_events] == ["B", "C"]
        assert energy_events[0]["backgroundColor"] == STRATEGY_COLORS["energy_aware"]

    def test_overlap_between_busy_and_proposed_preserved(self) -> None:
        state = {
            "busy_blocks": [
                {"start": "2026-05-04T09:00:00+00:00", "end": "2026-05-04T10:30:00+00:00"},
            ],
            "candidate_deadline_first": [
                _proposed(
                    "Conflict task",
                    "2026-05-04T10:00:00+00:00",
                    "2026-05-04T11:00:00+00:00",
                ),
            ],
        }

        events = build_calendar_events(state, "deadline_first")

        assert len(events) == 2
        assert events[0]["extendedProps"]["kind"] == "existing"
        assert events[1]["extendedProps"]["kind"] == "proposed"

    def test_strategy_keys_match_state_schema(self) -> None:
        assert set(STRATEGY_STATE_KEYS) == set(STRATEGY_COLORS)
        for key in STRATEGY_STATE_KEYS.values():
            assert key.startswith("candidate_")
