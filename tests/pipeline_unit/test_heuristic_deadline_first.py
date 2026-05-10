# =============================================================================
# tests/pipeline_unit/test_heuristic_deadline_first.py — T26–T43
# =============================================================================
# Tests for schedule_deadline_first() — the earliest-slot greedy strategy.
#
# CRITICAL INVARIANT:
#   A task must land in the earliest slot it fits.  If an earlier slot had
#   room and the task went elsewhere, the test fails.
#
# All tests are pure-function calls — no mocking required.
# Key design rule (confirmed in code): after placing a task, deadline_first
#   re-inserts the unused slot remainder back into the pool.  The
#   min_allowed_start grows monotonically so later tasks cannot claim slots
#   that sit before the current frontier.
# =============================================================================

from __future__ import annotations

import datetime

import pytest

from src.orchestration.heuristics.deadline_first import schedule_deadline_first
from tests.pipeline_unit.conftest import slot, subtask, tagged_subtask, isodt

UTC = datetime.timezone.utc

# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _s(name: str, duration: int, group: str = "g", shuffle: str = "yes",
        complexity: str = "medium") -> dict:
    return tagged_subtask(name, group, shuffle, complexity, duration)


def _untagged(name: str, duration: int) -> dict:
    return subtask(name, "Plain description without any tags.", duration)


def _starts_at(event: dict, hour: int, minute: int = 0) -> bool:
    dt_str = event["start"]
    dt = datetime.datetime.fromisoformat(dt_str)
    return dt.hour == hour and dt.minute == minute


# =============================================================================
# T26–T43
# =============================================================================


class TestDeadlineFirst:

    # T26
    def test_single_task_placed_in_first_available_slot(self):
        """T26: one task, one slot → task starts at slot's start."""
        tasks = [_s("Task A", 60)]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T12:00:00+00:00")]
        result = schedule_deadline_first(tasks, slots)

        assert len(result) == 1
        assert result[0]["start"] == "2026-05-11T09:00:00+00:00"
        assert result[0]["end"] == "2026-05-11T10:00:00+00:00"

    # T27
    def test_task_placed_in_earlier_slot_not_later(self):
        """T27: two slots — task must land in the 09:00 slot, not 14:00."""
        tasks = [_s("Task A", 60)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:30:00+00:00"),
            slot("2026-05-11T14:00:00+00:00", "2026-05-11T16:00:00+00:00"),
        ]
        result = schedule_deadline_first(tasks, slots)

        assert len(result) == 1
        assert _starts_at(result[0], 9)

    # T28
    def test_second_task_cannot_precede_first_task_end(self):
        """T28: min_allowed_start grows — task B cannot start before task A ends."""
        tasks = [_s("Task A", 60), _s("Task B", 60)]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T12:00:00+00:00")]
        result = schedule_deadline_first(tasks, slots)

        assert len(result) == 2
        end_a = datetime.datetime.fromisoformat(result[0]["end"])
        start_b = datetime.datetime.fromisoformat(result[1]["start"])
        assert start_b >= end_a

    # T29
    def test_three_tasks_fill_slots_front_to_back(self):
        """T29: three 60-min tasks each fill one 60-min slot → land in three separate slots."""
        tasks = [_s("Task A", 60), _s("Task B", 60), _s("Task C", 60)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),
            slot("2026-05-11T11:00:00+00:00", "2026-05-11T12:00:00+00:00"),
            slot("2026-05-11T14:00:00+00:00", "2026-05-11T15:00:00+00:00"),
        ]
        result = schedule_deadline_first(tasks, slots)

        assert len(result) == 3
        assert _starts_at(result[0], 9)
        assert _starts_at(result[1], 11)
        assert _starts_at(result[2], 14)

    # T30
    def test_task_cannot_be_placed_in_later_slot_when_earlier_fits(self):
        """T30: critical invariant — 90-min task fits first 180-min slot, not second."""
        tasks = [_s("Task A", 90)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T12:00:00+00:00"),  # 180 min
            slot("2026-05-11T14:00:00+00:00", "2026-05-11T16:00:00+00:00"),  # 120 min
        ]
        result = schedule_deadline_first(tasks, slots)

        assert len(result) == 1
        assert _starts_at(result[0], 9), (
            "Task should be in the 09:00 slot — using the later slot violates earliest-first."
        )

    # T31  — FIXED: B is blocked by min_allowed_start after A lands at 11:00
    def test_shuffle_yes_larger_task_lands_in_later_slot_smaller_task_follows(self):
        """T31: shuffle:yes run sorted longest-first; A(90min) skips small slot,
        B(30min) follows A due to monotonic min_allowed_start — not at 09:00."""
        tasks = [_s("Task B", 30), _s("Task A", 90)]  # LLM order: B first, A second
        # Both [shuffle:yes] in same group → sorted DESC by duration: A=90 processed first
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # 60min
            slot("2026-05-11T11:00:00+00:00", "2026-05-11T14:00:00+00:00"),  # 180min
        ]
        result = schedule_deadline_first(tasks, slots)

        assert len(result) == 2
        # After sort DESC: A(90) processed first
        a = next(e for e in result if e["name"] == "Task A")
        b = next(e for e in result if e["name"] == "Task B")
        # A(90min) doesn't fit 09:00–10:00 (60min) → lands at 11:00
        assert _starts_at(a, 11), f"Task A should start at 11:00, got {a['start']}"
        # B(30min): min_allowed_start=12:30 (after A ends); 09:00 slot is blocked → B at 12:30
        assert _starts_at(b, 12, 30), f"Task B should start at 12:30, got {b['start']}"

    # T32
    def test_no_chronological_inversion_in_output(self):
        """T32: output events are always in chronological start-time order."""
        tasks = [_s(f"Task {i}", 30 + i * 10) for i in range(5)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00"),
            slot("2026-05-12T09:00:00+00:00", "2026-05-12T18:00:00+00:00"),
        ]
        result = schedule_deadline_first(tasks, slots)

        starts = [datetime.datetime.fromisoformat(e["start"]) for e in result]
        assert starts == sorted(starts), "Output events are not in chronological order."

    # T33
    def test_group_a_tasks_precede_group_b_tasks(self):
        """T33: all phase1 tasks end before any phase2 task starts."""
        tasks = [
            _s("A1", 30, group="phase1"), _s("A2", 30, group="phase1"),
            _s("B1", 30, group="phase2"), _s("B2", 30, group="phase2"),
        ]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_deadline_first(tasks, slots)

        phase1_ends = [
            datetime.datetime.fromisoformat(e["end"])
            for e in result if "A" in e["name"]
        ]
        phase2_starts = [
            datetime.datetime.fromisoformat(e["start"])
            for e in result if "B" in e["name"]
        ]
        assert phase1_ends and phase2_starts
        assert max(phase1_ends) <= min(phase2_starts), (
            "A phase2 task started before all phase1 tasks finished."
        )

    # T34
    def test_seq_tagged_tasks_not_reordered(self):
        """T34: [seq:1,2,3] hard-locks order even when durations would suggest a reorder."""
        tasks = [
            tagged_subtask("Seq1", "g", "no", "medium", 90, seq=1),
            tagged_subtask("Seq2", "g", "no", "medium", 30, seq=2),
            tagged_subtask("Seq3", "g", "no", "medium", 60, seq=3),
        ]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_deadline_first(tasks, slots)

        assert [e["name"] for e in result] == ["Seq1", "Seq2", "Seq3"]

    # T35
    def test_shuffle_no_tasks_preserve_llm_order(self):
        """T35: [shuffle:no] tasks are not reordered regardless of duration differences."""
        tasks = [
            _s("A", 60, shuffle="no"),
            _s("B", 90, shuffle="no"),
            _s("C", 30, shuffle="no"),
        ]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_deadline_first(tasks, slots)

        assert [e["name"] for e in result] == ["A", "B", "C"]

    # T36
    def test_break_minutes_creates_gap_between_events(self):
        """T36: break_minutes=15 inserts a 15-min buffer between consecutive events."""
        tasks = [_s("Task A", 30), _s("Task B", 30)]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T12:00:00+00:00")]
        result = schedule_deadline_first(tasks, slots, break_minutes=15)

        assert len(result) == 2
        end_a = datetime.datetime.fromisoformat(result[0]["end"])
        start_b = datetime.datetime.fromisoformat(result[1]["start"])
        gap = start_b - end_a
        assert gap >= datetime.timedelta(minutes=15), (
            f"Break gap is {gap}, expected ≥ 15 minutes."
        )

    # T37
    def test_zero_break_minutes_allows_adjacent_events(self):
        """T37: break_minutes=0 → second task starts exactly when first ends."""
        tasks = [_s("Task A", 30), _s("Task B", 30)]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T11:00:00+00:00")]
        result = schedule_deadline_first(tasks, slots, break_minutes=0)

        assert len(result) == 2
        assert result[0]["end"] == result[1]["start"]

    # T38
    def test_empty_subtasks_returns_empty(self):
        """T38: no subtasks → empty output regardless of available slots."""
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_deadline_first([], slots)
        assert result == []

    # T39
    def test_empty_free_slots_returns_empty(self):
        """T39: no slots → nothing can be scheduled."""
        tasks = [_s("Task A", 60)]
        result = schedule_deadline_first(tasks, [])
        assert result == []

    # T40
    def test_oversized_task_skipped_others_placed(self):
        """T40: a task longer than every slot is skipped; others still schedule."""
        tasks = [_s("Small", 30), _s("Giant", 90), _s("Small2", 30)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # 60 min — too small for Giant
        ]
        # Giant (90min) won't fit any slot (only 60min available)
        result = schedule_deadline_first(tasks, slots)

        names = [e["name"] for e in result]
        assert "Giant" not in names
        assert "Small" in names

    # T41
    def test_all_tasks_placed_when_capacity_exactly_matches(self):
        """T41: two 60-min tasks + a 120-min slot → both placed, none left out."""
        tasks = [_s("Task A", 60), _s("Task B", 60)]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T11:00:00+00:00")]
        result = schedule_deadline_first(tasks, slots, break_minutes=0)

        assert len(result) == 2

    # T42
    def test_no_structural_tags_preserves_llm_order(self):
        """T42: without structural tags, LLM order is preserved exactly."""
        tasks = [_untagged("Alpha", 30), _untagged("Beta", 90), _untagged("Gamma", 60)]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_deadline_first(tasks, slots)

        assert [e["name"] for e in result] == ["Alpha", "Beta", "Gamma"]

    # T43
    def test_output_events_fall_within_free_slots(self):
        """T43: each scheduled event's [start, end] lies within its source slot."""
        tasks = [_s("Task A", 60), _s("Task B", 45), _s("Task C", 30)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T11:00:00+00:00"),
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T15:00:00+00:00"),
        ]
        result = schedule_deadline_first(tasks, slots)

        all_slot_pairs = [
            (datetime.datetime.fromisoformat(s["start"]),
             datetime.datetime.fromisoformat(s["end"]))
            for s in slots
        ]
        for event in result:
            ev_start = datetime.datetime.fromisoformat(event["start"])
            ev_end = datetime.datetime.fromisoformat(event["end"])
            fits = any(
                slot_s <= ev_start and ev_end <= slot_e
                for slot_s, slot_e in all_slot_pairs
            )
            assert fits, (
                f"{event['name']} [{event['start']}–{event['end']}] "
                "falls outside all free slots."
            )
