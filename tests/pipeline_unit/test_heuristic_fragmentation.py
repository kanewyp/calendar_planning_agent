# =============================================================================
# tests/pipeline_unit/test_heuristic_fragmentation.py — T44–T58
# =============================================================================
# Tests for schedule_min_fragmentation() — the largest-slot-on-earliest-day
# strategy.
#
# CRITICAL INVARIANT (structural mode only):
#   On the target date (earliest date with a fitting slot), the task MUST land
#   in the LARGEST available slot.  Picking a smaller slot on the same day
#   fails the invariant.
#
# STRUCTURAL MODE is triggered when at least one subtask carries a [key:value]
# tag.  Without tags the algorithm falls back to earliest-slot (same as
# deadline_first).
#
# All tests are pure-function calls — no mocking required.
# =============================================================================

from __future__ import annotations

import datetime

import pytest

from src.orchestration.heuristics.deadline_first import schedule_deadline_first
from src.orchestration.heuristics.minimize_fragmentation import schedule_min_fragmentation
from tests.pipeline_unit.conftest import slot, subtask, tagged_subtask

UTC = datetime.timezone.utc


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _s(name: str, duration: int, group: str = "g", shuffle: str = "yes",
        complexity: str = "medium") -> dict:
    return tagged_subtask(name, group, shuffle, complexity, duration)


def _untagged(name: str, duration: int) -> dict:
    return subtask(name, "Plain description without any tags.", duration)


def _hour(event: dict) -> int:
    return datetime.datetime.fromisoformat(event["start"]).hour


def _slots_durations_min(slots_list: list[dict]) -> list[int]:
    return [
        int((datetime.datetime.fromisoformat(s["end"]) -
             datetime.datetime.fromisoformat(s["start"])).total_seconds() / 60)
        for s in slots_list
    ]


# =============================================================================
# T44–T58
# =============================================================================


class TestMinFragmentation:

    # T44
    def test_single_task_placed_when_only_large_slot_fits(self):
        """T44: 90-min task skips the 60-min slot and lands in the 240-min slot."""
        tasks = [_s("Task A", 90)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # 60 min
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T17:00:00+00:00"),  # 240 min
        ]
        result = schedule_min_fragmentation(tasks, slots)

        assert len(result) == 1
        assert _hour(result[0]) == 13, (
            "90-min task must go to 13:00 (only slot ≥ 90min on earliest day)."
        )

    # T45  — FIXED: task has structural tags to activate largest-slot mode
    def test_larger_slot_preferred_when_both_fit_same_day(self):
        """T45: 60-min task fits 09:00 (90min) and 13:00 (240min); must pick 13:00 (largest)."""
        tasks = [_s("Task A", 60)]   # structural tag triggers structural mode
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:30:00+00:00"),  # 90 min
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T17:00:00+00:00"),  # 240 min
        ]
        result = schedule_min_fragmentation(tasks, slots)

        assert len(result) == 1
        assert _hour(result[0]) == 13, (
            "Task fits both slots; min_fragmentation must pick the larger one."
        )

    # T46
    def test_two_tasks_longer_first_gets_biggest_slot(self):
        """T46: shuffle:yes run sorted longest-first; A(120) takes 240-min, B(60) takes rest."""
        tasks = [
            _s("Task B", 60, shuffle="yes"),   # shorter
            _s("Task A", 120, shuffle="yes"),  # longer (processed first after sort)
        ]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:30:00+00:00"),  # 90 min
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T17:00:00+00:00"),  # 240 min
        ]
        result = schedule_min_fragmentation(tasks, slots)

        assert len(result) == 2
        a = next(e for e in result if e["name"] == "Task A")
        b = next(e for e in result if e["name"] == "Task B")
        # A(120min): 09:00–10:30 is only 90min → goes to 13:00 (240min)
        assert _hour(a) == 13, "Longer task should go to the largest slot."
        # B(60min): follows A; lands in whichever slot remains
        assert b["start"] > a["start"] or _hour(b) != 13

    # T47
    def test_advances_to_next_day_only_when_day1_has_no_fitting_slot(self):
        """T47: 90-min task advances to Day2 when Day1 only has a 30-min slot."""
        tasks = [_s("Task A", 90)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T09:30:00+00:00"),  # Day1: 30 min
            slot("2026-05-12T09:00:00+00:00", "2026-05-12T12:00:00+00:00"),  # Day2: 180 min
        ]
        result = schedule_min_fragmentation(tasks, slots)

        assert len(result) == 1
        start = datetime.datetime.fromisoformat(result[0]["start"])
        assert start.date() == datetime.date(2026, 5, 12), (
            "Task must advance to Day2 (Day1 has no fitting slot)."
        )

    # T48  — FIXED: task has structural tag to trigger structural mode
    def test_large_slot_preferred_over_small_slot_same_day(self):
        """T48: 45-min task fits 09:00 (60min) AND 14:00 (180min); picks 14:00 (largest)."""
        tasks = [_s("Task A", 45)]  # tag activates structural mode
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # 60 min
            slot("2026-05-11T14:00:00+00:00", "2026-05-11T17:00:00+00:00"),  # 180 min
        ]
        result = schedule_min_fragmentation(tasks, slots)

        assert len(result) == 1
        assert _hour(result[0]) == 14, (
            "min_fragmentation must pick 14:00 (largest slot on earliest day), not 09:00."
        )

    # T49  — FIXED: both subtask lists carry structural tags so behaviours diverge
    def test_fragmentation_and_deadline_first_diverge_on_slot_selection(self):
        """T49: same scenario, different strategies pick different slots."""
        tasks = [_s("Task A", 30)]   # tag activates structural mode in min_fragmentation
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T09:45:00+00:00"),  # 45 min (small)
            slot("2026-05-11T14:00:00+00:00", "2026-05-11T17:00:00+00:00"),  # 180 min (large)
        ]

        dl_result = schedule_deadline_first(tasks, slots)
        frag_result = schedule_min_fragmentation(tasks, slots)

        # deadline_first → earliest fitting slot → 09:00
        assert _hour(dl_result[0]) == 9, "deadline_first should pick 09:00."
        # min_fragmentation → largest on earliest day → 14:00
        assert _hour(frag_result[0]) == 14, "min_fragmentation should pick 14:00."
        assert dl_result[0]["start"] != frag_result[0]["start"]

    # T50
    def test_shuffle_run_sorted_longest_first_before_slot_selection(self):
        """T50: shuffle:yes run processed longest-first; Task B(120) gets earliest result start."""
        tasks = [
            _s("Task A", 30, shuffle="yes"),   # shortest
            _s("Task B", 120, shuffle="yes"),  # longest → processed first
            _s("Task C", 60, shuffle="yes"),   # medium
        ]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_min_fragmentation(tasks, slots)

        # After sort DESC [B=120, C=60, A=30], B is processed first and claims 09:00
        assert result[0]["name"] == "Task B", (
            "Longest task should be scheduled first (earliest start) after shuffle sort."
        )

    # T51
    def test_no_structural_tags_fallback_matches_deadline_first(self):
        """T51: without structural tags, min_fragmentation falls back to earliest-slot."""
        tasks = [
            _untagged("Alpha", 30),
            _untagged("Beta", 60),
            _untagged("Gamma", 45),
        ]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T12:00:00+00:00"),
            slot("2026-05-11T14:00:00+00:00", "2026-05-11T17:00:00+00:00"),
        ]

        frag = schedule_min_fragmentation(tasks, slots)
        dl = schedule_deadline_first(tasks, slots)

        frag_starts = [e["start"] for e in frag]
        dl_starts = [e["start"] for e in dl]
        assert frag_starts == dl_starts, (
            "Without tags, both strategies should produce identical slot selections."
        )

    # T52
    def test_group_ordering_respected_fragmentation(self):
        """T52: all alpha group events end before any beta group event starts."""
        tasks = [
            _s("Alpha1", 45, group="alpha", shuffle="yes"),
            _s("Alpha2", 45, group="alpha", shuffle="yes"),
            _s("Beta1", 60, group="beta", shuffle="yes"),
        ]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_min_fragmentation(tasks, slots)

        alpha_ends = [
            datetime.datetime.fromisoformat(e["end"])
            for e in result if "Alpha" in e["name"]
        ]
        beta_starts = [
            datetime.datetime.fromisoformat(e["start"])
            for e in result if "Beta" in e["name"]
        ]
        assert alpha_ends and beta_starts
        assert max(alpha_ends) <= min(beta_starts)

    # T53
    def test_leftover_slot_portions_returned_to_pool(self):
        """T53: after placing task A in the big slot, the remainder is used by task B."""
        tasks = [_s("Task A", 60, shuffle="no"), _s("Task B", 60, shuffle="no")]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T17:00:00+00:00")]  # 480 min
        result = schedule_min_fragmentation(tasks, slots)

        assert len(result) == 2, "Both tasks should be scheduled from the single large slot."

    # T54
    def test_empty_subtasks_returns_empty_fragmentation(self):
        """T54: no subtasks → empty output."""
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        assert schedule_min_fragmentation([], slots) == []

    # T55
    def test_task_larger_than_all_slots_skipped_fragmentation(self):
        """T55: a 300-min task with only 120-min slots available → no output, no exception."""
        tasks = [_s("Giant", 200)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T11:00:00+00:00"),  # 120 min
            slot("2026-05-12T09:00:00+00:00", "2026-05-12T11:00:00+00:00"),  # 120 min
        ]
        result = schedule_min_fragmentation(tasks, slots)
        assert result == []

    # T56
    def test_output_chronologically_sorted_fragmentation(self):
        """T56: output events are always sorted by start time ascending."""
        tasks = [_s(f"T{i}", 30 + i * 10) for i in range(4)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00"),
            slot("2026-05-12T09:00:00+00:00", "2026-05-12T18:00:00+00:00"),
        ]
        result = schedule_min_fragmentation(tasks, slots)

        starts = [datetime.datetime.fromisoformat(e["start"]) for e in result]
        assert starts == sorted(starts)

    # T57
    def test_output_events_within_free_slots_fragmentation(self):
        """T57: every scheduled event [start, end] lies within some free slot."""
        tasks = [_s("Task A", 60), _s("Task B", 90)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T12:00:00+00:00"),
            slot("2026-05-11T14:00:00+00:00", "2026-05-11T17:00:00+00:00"),
        ]
        result = schedule_min_fragmentation(tasks, slots)

        slot_pairs = [
            (datetime.datetime.fromisoformat(s["start"]),
             datetime.datetime.fromisoformat(s["end"]))
            for s in slots
        ]
        for event in result:
            ev_s = datetime.datetime.fromisoformat(event["start"])
            ev_e = datetime.datetime.fromisoformat(event["end"])
            assert any(s <= ev_s and ev_e <= e for s, e in slot_pairs), (
                f"{event['name']} [{event['start']}–{event['end']}] outside all slots."
            )

    # T58
    def test_break_minutes_applied_fragmentation(self):
        """T58: break_minutes=15 inserts at least a 15-min gap between consecutive events."""
        tasks = [_s("Task A", 30), _s("Task B", 30)]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_min_fragmentation(tasks, slots, break_minutes=15)

        assert len(result) == 2
        end_a = datetime.datetime.fromisoformat(result[0]["end"])
        start_b = datetime.datetime.fromisoformat(result[1]["start"])
        assert start_b - end_a >= datetime.timedelta(minutes=15)
