# =============================================================================
# tests/pipeline_unit/test_heuristic_energy_aware.py — T59–T76
# =============================================================================
# Tests for schedule_energy_aware() — places tasks in slots whose energy
# level best matches the task's complexity.
#
# ENERGY / COMPLEXITY SCORE MAP (from _structural.py):
#   "low" → 1 | "medium" → 2 | "high" → 3
#
# SLOT PERIOD CLASSIFICATION (from energy_aware.py):
#   hour < 12:00            → "morning"
#   12:00 <= hour < 17:00   → "afternoon"
#   hour >= 17:00           → "evening"
#
# SCORE DIFF: abs(slot_energy_score - task_complexity_score)
#   Lower is better. Ties broken by earliest candidate_start.
#
# KEY RULE (from project requirements):
#   [complexity:high]   → should go to high-energy slot (score_diff=0)
#   [complexity:medium] → should go to medium or high slot (score_diff=0 or 1)
#   [complexity:low]    → should go to low-energy slot (score_diff=0)
#   A non-zero best match is acceptable only when no zero-diff slot exists.
#
# ALGORITHM (Earliest-Day Energy Match):
#   1. Find earliest date with any eligible (fitting) slot.
#   2. On that date pick the slot with lowest score_diff (tie → earliest start).
#
# All tests are pure-function calls — no mocking required.
# =============================================================================

from __future__ import annotations

import datetime

from src.orchestration.heuristics.energy_aware import schedule_energy_aware
from tests.pipeline_unit.conftest import slot, subtask, tagged_subtask

UTC = datetime.timezone.utc

# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _s(name: str, duration: int, complexity: str, group: str = "g",
        shuffle: str = "no") -> dict:
    return tagged_subtask(name, group, shuffle, complexity, duration)


def _untagged(name: str, duration: int) -> dict:
    return subtask(name, "Plain description without structural tags.", duration)


def _hour(event: dict) -> int:
    return datetime.datetime.fromisoformat(event["start"]).hour


def _period(event: dict) -> str:
    h = _hour(event)
    if h < 12:
        return "morning"
    if h < 17:
        return "afternoon"
    return "evening"


HIGH_ENERGY: dict[str, str] = {"morning": "high", "afternoon": "medium", "evening": "low"}
CUSTOM_AFTERNOON_HIGH: dict[str, str] = {"morning": "low", "afternoon": "high", "evening": "medium"}

# =============================================================================
# T59–T76
# =============================================================================


class TestEnergyAware:

    # T59
    def test_high_complexity_task_placed_in_morning_high_energy_slot(self):
        """T59: [complexity:high] lands in morning (energy=high, score_diff=0)."""
        tasks = [_s("Hard Task", 60, "high")]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T11:00:00+00:00"),  # morning
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T15:00:00+00:00"),  # afternoon
        ]
        result = schedule_energy_aware(tasks, slots, HIGH_ENERGY)

        assert len(result) == 1
        assert _period(result[0]) == "morning", (
            "[complexity:high] should go to the high-energy morning slot."
        )

    # T60
    def test_medium_complexity_task_placed_in_best_energy_slot(self):
        """T60: [complexity:medium] picks best score_diff slot on earliest day.

        Scenario A: morning slot too small (30min) for 60-min task → must use afternoon.
        Scenario B: both slots fit; afternoon has score_diff=0 vs morning's 1 → afternoon.
        """
        # Scenario A: size constraint forces afternoon
        tasks_a = [_s("Med Task", 60, "medium")]
        slots_a = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T09:30:00+00:00"),  # 30min only
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T15:00:00+00:00"),  # 120min
        ]
        result_a = schedule_energy_aware(tasks_a, slots_a, HIGH_ENERGY)
        assert len(result_a) == 1
        assert _period(result_a[0]) == "afternoon", (
            "Scenario A: morning slot too small; task must go to afternoon."
        )

        # Scenario B: both fit; afternoon is better energy match (score_diff=0 vs 1)
        tasks_b = [_s("Med Task", 45, "medium")]
        slots_b = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T11:00:00+00:00"),  # morning (score_diff=1)
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T15:00:00+00:00"),  # afternoon (score_diff=0)
        ]
        result_b = schedule_energy_aware(tasks_b, slots_b, HIGH_ENERGY)
        assert len(result_b) == 1
        assert _period(result_b[0]) == "afternoon", (
            "Scenario B: afternoon has score_diff=0 (medium energy = medium complexity); must win."
        )

    # T61
    def test_low_complexity_task_placed_in_evening_low_energy_slot(self):
        """T61: [complexity:low] lands in evening (energy=low, score_diff=0)."""
        tasks = [_s("Easy Task", 30, "low")]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # morning
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T14:00:00+00:00"),  # afternoon
            slot("2026-05-11T18:00:00+00:00", "2026-05-11T19:00:00+00:00"),  # evening
        ]
        result = schedule_energy_aware(tasks, slots, HIGH_ENERGY)

        assert len(result) == 1
        assert _period(result[0]) == "evening", (
            "[complexity:low] should go to the low-energy evening slot (score_diff=0)."
        )

    # T62
    def test_high_complexity_not_in_low_energy_slot_when_high_available(self):
        """T62: [complexity:high] must not land in low-energy afternoon when morning is free."""
        tasks = [_s("Hard Task", 45, "high")]
        energy = {"morning": "high", "afternoon": "low", "evening": "low"}
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # morning
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T14:00:00+00:00"),  # afternoon
        ]
        result = schedule_energy_aware(tasks, slots, energy)

        assert _period(result[0]) == "morning", (
            "High-complexity task should not be in low-energy afternoon slot."
        )

    # T63
    def test_medium_complexity_not_in_low_when_medium_available_same_day(self):
        """T63: [complexity:medium] picks afternoon (score_diff=0) over evening (score_diff=1)."""
        tasks = [_s("Med Task", 30, "medium")]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),   # morning (diff=1)
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T14:00:00+00:00"),   # afternoon (diff=0)
            slot("2026-05-11T18:00:00+00:00", "2026-05-11T19:00:00+00:00"),   # evening (diff=1)
        ]
        result = schedule_energy_aware(tasks, slots, HIGH_ENERGY)

        assert _period(result[0]) == "afternoon"

    # T64  — FIXED: both tasks are [shuffle:yes] in same group so high-complexity is processed first
    def test_easy_task_does_not_consume_high_energy_slot(self):
        """T64: easy task must NOT take the morning slot away from the hard task.
        Both are [shuffle:yes] so energy_aware processes high-complexity first."""
        tasks = [
            _s("Easy Task", 30, "low", group="g", shuffle="yes"),
            _s("Hard Task", 30, "high", group="g", shuffle="yes"),
        ]
        energy = {"morning": "high", "afternoon": "medium", "evening": "low"}
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),   # morning
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T14:00:00+00:00"),   # afternoon
        ]
        result = schedule_energy_aware(tasks, slots, energy)

        hard = next(e for e in result if e["name"] == "Hard Task")
        easy = next(e for e in result if e["name"] == "Easy Task")
        assert _period(hard) == "morning", "High-complexity task should claim the morning slot."
        assert _period(easy) != "morning", "Easy task should not be in the high-energy morning slot."

    # T65
    def test_custom_energy_profile_routes_task_to_correct_period(self):
        """T65: custom profile morning=low, afternoon=high → high-complexity goes to afternoon."""
        tasks = [_s("Hard Task", 45, "high")]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # morning (low)
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T14:00:00+00:00"),  # afternoon (high)
            slot("2026-05-11T18:00:00+00:00", "2026-05-11T19:00:00+00:00"),  # evening (medium)
        ]
        result = schedule_energy_aware(tasks, slots, CUSTOM_AFTERNOON_HIGH)

        assert _period(result[0]) == "afternoon", (
            "With afternoon=high energy, a high-complexity task must go to afternoon."
        )

    # T66
    def test_best_match_slot_chosen_over_acceptable_match(self):
        """T66: medium task picks afternoon (score_diff=0) over morning (score_diff=1)."""
        tasks = [_s("Med Task", 45, "medium")]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T11:00:00+00:00"),  # morning (diff=1)
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T14:00:00+00:00"),  # afternoon (diff=0)
        ]
        result = schedule_energy_aware(tasks, slots, HIGH_ENERGY)

        assert _period(result[0]) == "afternoon"

    # T67  — FIXED: all 3 energy periods specified; only morning+afternoon slots present
    def test_tie_in_score_diff_broken_by_earliest_start(self):
        """T67: morning and afternoon both have score_diff=1 for medium task → morning wins (earlier)."""
        energy = {"morning": "high", "afternoon": "low", "evening": "low"}
        # morning: energy_score=3, medium task=2 → diff=1
        # afternoon: energy_score=1, medium task=2 → diff=1
        tasks = [_s("Med Task", 30, "medium")]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # morning (diff=1)
            slot("2026-05-11T13:00:00+00:00", "2026-05-11T14:00:00+00:00"),  # afternoon (diff=1)
        ]
        result = schedule_energy_aware(tasks, slots, energy)

        assert _period(result[0]) == "morning", (
            "Equal score_diff → tie-break by earliest start → morning slot wins."
        )

    # T68  — FIXED: clean scenario using only morning+afternoon; earliest day beats later-day perfect match
    def test_earliest_day_beats_better_energy_match_on_later_day(self):
        """T68: near-match on Day1 afternoon beats a perfect match on Day2 morning."""
        # Day1 has only morning slots: score_diff=1 for medium task (morning=high)
        # Day2 has afternoon slot: score_diff=0 (afternoon=medium)
        # Algorithm: find EARLIEST day with fitting slot → Day1 wins even with worse energy.
        energy = {"morning": "high", "afternoon": "medium", "evening": "low"}
        tasks = [_s("Med Task", 30, "medium")]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # Day1 morning (diff=1)
            slot("2026-05-12T13:00:00+00:00", "2026-05-12T14:00:00+00:00"),  # Day2 afternoon (diff=0)
        ]
        result = schedule_energy_aware(tasks, slots, energy)

        assert len(result) == 1
        start = datetime.datetime.fromisoformat(result[0]["start"])
        assert start.date() == datetime.date(2026, 5, 11), (
            "Earliest-day logic: Day1 near-match must beat Day2 perfect match."
        )

    # T69
    def test_task_placed_on_earliest_date_with_any_eligible_slot(self):
        """T69: task is skipped on Day1 (no fitting slot) and placed on Day2."""
        tasks = [_s("Task A", 90, "high")]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T09:30:00+00:00"),  # Day1: 30min only
            slot("2026-05-12T09:00:00+00:00", "2026-05-12T12:00:00+00:00"),  # Day2: 180min
        ]
        result = schedule_energy_aware(tasks, slots, HIGH_ENERGY)

        start = datetime.datetime.fromisoformat(result[0]["start"])
        assert start.date() == datetime.date(2026, 5, 12)

    # T70
    def test_dependency_order_preserved_despite_energy_placement(self):
        """T70: phase1 group events must all finish before phase2 events start."""
        tasks = [
            _s("Phase1-A", 45, "high", group="phase1"),
            _s("Phase2-A", 45, "medium", group="phase2"),
        ]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T11:00:00+00:00"),
            slot("2026-05-12T09:00:00+00:00", "2026-05-12T11:00:00+00:00"),
        ]
        result = schedule_energy_aware(tasks, slots, HIGH_ENERGY)

        p1_events = [e for e in result if "Phase1" in e["name"]]
        p2_events = [e for e in result if "Phase2" in e["name"]]
        assert p1_events and p2_events

        max_p1_end = max(datetime.datetime.fromisoformat(e["end"]) for e in p1_events)
        min_p2_start = min(datetime.datetime.fromisoformat(e["start"]) for e in p2_events)
        assert max_p1_end <= min_p2_start

    # T71
    def test_min_allowed_start_prevents_chronological_inversion(self):
        """T71: output events are always in chronological start-time order."""
        tasks = [_s(f"Task {i}", 30 + i * 10, "medium") for i in range(4)]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00"),
            slot("2026-05-12T09:00:00+00:00", "2026-05-12T18:00:00+00:00"),
        ]
        result = schedule_energy_aware(tasks, slots, HIGH_ENERGY)

        starts = [datetime.datetime.fromisoformat(e["start"]) for e in result]
        assert starts == sorted(starts)

    # T72
    def test_shuffle_yes_run_sorted_by_complexity_descending(self):
        """T72: shuffle:yes run sorted high→medium→low; highest-complexity gets first pick."""
        tasks = [
            _s("Low Task", 30, "low", group="g", shuffle="yes"),
            _s("High Task", 60, "high", group="g", shuffle="yes"),
            _s("Med Task", 45, "medium", group="g", shuffle="yes"),
        ]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_energy_aware(tasks, slots, HIGH_ENERGY)

        # High task processed first → gets 09:00 slot (earliest)
        assert result[0]["name"] == "High Task", (
            "Shuffle:yes run sorted by complexity DESC — high task must have earliest start."
        )

    # T73
    def test_seq_tags_hard_locked_energy_aware(self):
        """T73: [seq:1]=low-complexity processed before [seq:2]=high, preserving seq order."""
        tasks = [
            tagged_subtask("Seq1-Low", "g", "no", "low", 30, seq=1),
            tagged_subtask("Seq2-High", "g", "no", "high", 30, seq=2),
        ]
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        result = schedule_energy_aware(tasks, slots, HIGH_ENERGY)

        seq1 = next(e for e in result if "Seq1" in e["name"])
        seq2 = next(e for e in result if "Seq2" in e["name"])
        assert seq1["start"] < seq2["start"], (
            "[seq:1] must start before [seq:2] regardless of complexity-based energy preference."
        )

    # T74
    def test_empty_subtasks_returns_empty_energy_aware(self):
        """T74: no subtasks → empty output."""
        slots = [slot("2026-05-11T09:00:00+00:00", "2026-05-11T18:00:00+00:00")]
        assert schedule_energy_aware([], slots, HIGH_ENERGY) == []

    # T75
    def test_no_fitting_slots_returns_empty_energy_aware(self):
        """T75: task too large for any slot → empty output, no exception."""
        tasks = [_s("Big Task", 180, "high")]
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T10:00:00+00:00"),  # 60 min
            slot("2026-05-12T09:00:00+00:00", "2026-05-12T10:00:00+00:00"),  # 60 min
        ]
        assert schedule_energy_aware(tasks, slots, HIGH_ENERGY) == []

    # T76
    def test_duration_fallback_for_untagged_tasks(self):
        """T76: without [complexity:*] tag, duration drives score: ≥90→high, ≥60→medium, <60→low."""
        # ≥90min → score 3 (high) → should prefer morning (energy=high, diff=0)
        heavy = _untagged("Heavy Untagged", 90)
        # <60min → score 1 (low) → should prefer evening (energy=low, diff=0)
        light = _untagged("Light Untagged", 30)
        slots = [
            slot("2026-05-11T09:00:00+00:00", "2026-05-11T12:00:00+00:00"),  # morning (180min)
            slot("2026-05-11T18:00:00+00:00", "2026-05-11T19:30:00+00:00"),  # evening (90min)
        ]
        result = schedule_energy_aware([heavy, light], slots, HIGH_ENERGY)

        heavy_event = next(e for e in result if "Heavy" in e["name"])
        light_event = next(e for e in result if "Light" in e["name"])
        assert _period(heavy_event) == "morning", "High-score duration task should go to high-energy morning."
        assert _period(light_event) == "evening", "Low-score duration task should go to low-energy evening."
