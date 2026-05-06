# =============================================================================
# src/orchestration/heuristics/energy_aware.py — Energy-aware scheduling
# =============================================================================
# Places subtasks in time slots matching the user's energy levels throughout
# the day. Respects task order (for learning prerequisites) while optimising
# for energy alignment.
#
# Pure function with no LLM or API calls — fully unit-testable.
# =============================================================================

from __future__ import annotations

import datetime

from src.orchestration.state import Subtask, ProposedEvent
from src.orchestration.heuristics._structural import (
    COMPLEXITY_SCORE,
    complexity_score,
    has_any_structural_tags,
    safe_structural_shuffle,
)


# Time period boundaries.
_MORNING_END = datetime.time(12, 0)
_AFTERNOON_END = datetime.time(17, 0)

def _classify_slot_by_time(slot_start: datetime.datetime) -> str:
    """Classify a time slot into morning/afternoon/evening."""
    hour = slot_start.time()
    if hour < _MORNING_END:
        return "morning"
    elif hour < _AFTERNOON_END:
        return "afternoon"
    else:
        return "evening"


def schedule_energy_aware(
    subtasks: list[Subtask],
    free_slots: list[dict[str, str]],
    user_energy_levels: dict[str, str] | None = None,
    work_start: str = "09:00",
) -> list[ProposedEvent]:
    """Schedule subtasks respecting order while matching user's energy levels.

    Args:
        subtasks: Ordered list of subtasks. Groups are learning phases and
                  execute in first-appearance order. Within each phase,
                  contiguous [shuffle:yes] runs may be locally reordered
                  (higher complexity first) so demanding peer tasks get first
                  pick of peak-energy slots.
        free_slots: Chronologically sorted list of {"start", "end"} dicts.
        user_energy_levels: e.g. {"morning": "high", "afternoon": "medium",
                             "evening": "low"}. Defaults to that mapping.
        work_start: User's working hours start "HH:MM" (kept for API consistency).

    Returns:
        List of ProposedEvent dicts, sorted chronologically.

    ALGORITHM — EARLIEST-DAY ENERGY MATCH:
    For each task:
      1. Find the earliest date with any eligible slot.
      2. On that date, pick the slot with the best energy match
         (tie-break by earliest start).

    This keeps schedules anchored near the present. A perfect energy match on
    May 15 should not beat a near match on May 7, because doing so can hide
    many usable blocks and leave too little calendar before the deadline.

    ORDERING GUARANTEE:
    min_allowed_start grows monotonically after each placement. Slots that
    start before it are never considered, so calendar order always matches
    dependency order.

    KEY DESIGN POINTS:
    - The user's actual energy_levels argument drives placement.
    - Complexity comes from the explicit [complexity:*] tag if present;
      duration is only a fallback.
    """
    if user_energy_levels is None:
        user_energy_levels = {
            "morning": "high",
            "afternoon": "medium",
            "evening": "low",
        }

    energy_scores = {
        period: COMPLEXITY_SCORE.get(level, 2)
        for period, level in user_energy_levels.items()
    }

    # Sort chronologically so each pass scans slots in temporal order and
    # the first match found is the earliest eligible one.
    slot_pool: list[tuple[datetime.datetime, datetime.datetime]] = sorted(
        (
            datetime.datetime.fromisoformat(slot["start"]),
            datetime.datetime.fromisoformat(slot["end"]),
        )
        for slot in free_slots
    )

    if has_any_structural_tags(subtasks):
        subtasks_for_scheduling = safe_structural_shuffle(
            subtasks,
            run_sort_key=complexity_score,
        )
    else:
        subtasks_for_scheduling = list(subtasks)

    scheduled: list[ProposedEvent] = []
    # Grows monotonically: each task must start no earlier than where the
    # previous task ended, so calendar order matches dependency order.
    min_allowed_start: datetime.datetime | None = None

    for subtask in subtasks_for_scheduling:
        duration = datetime.timedelta(minutes=subtask["duration_minutes"])
        task_complexity = complexity_score(subtask)
        chosen_idx: int | None = None
        chosen_start: datetime.datetime | None = None

        target_date: datetime.date | None = None
        for slot_start, slot_end in slot_pool:
            candidate_start = slot_start
            if min_allowed_start is not None and candidate_start < min_allowed_start:
                candidate_start = min_allowed_start
            if slot_end - candidate_start >= duration:
                target_date = candidate_start.date()
                break

        if target_date is None:
            continue

        best_key: tuple[int, datetime.datetime] | None = None
        for idx, (slot_start, slot_end) in enumerate(slot_pool):
            candidate_start = slot_start
            if min_allowed_start is not None and candidate_start < min_allowed_start:
                candidate_start = min_allowed_start
            if candidate_start.date() != target_date:
                continue
            if slot_end - candidate_start < duration:
                continue

            slot_period = _classify_slot_by_time(candidate_start)
            slot_energy_score = energy_scores.get(slot_period, 2)
            score_diff = abs(slot_energy_score - task_complexity)
            key = (score_diff, candidate_start)
            if best_key is None or key < best_key:
                best_key = key
                chosen_idx = idx
                chosen_start = candidate_start

        if chosen_idx is None:
            continue

        slot_start, slot_end = slot_pool.pop(chosen_idx)
        event_start = chosen_start or slot_start
        event_end = event_start + duration

        scheduled.append(
            ProposedEvent(
                name=subtask["name"],
                description=subtask["description"],
                start=event_start.isoformat(),
                end=event_end.isoformat(),
            )
        )

        min_allowed_start = event_end

        # Return remainders to pool in sorted order so subsequent passes
        # scan slots correctly.
        if slot_start < event_start:
            slot_pool.append((slot_start, event_start))
        if event_end < slot_end:
            slot_pool.append((event_end, slot_end))
        slot_pool.sort(key=lambda interval: interval[0])

    scheduled.sort(key=lambda event: event["start"])
    return scheduled
