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
        subtasks: Ordered list of subtasks. Order is preserved by default;
                  contiguous runs of [shuffle:yes] tasks within the same
                  [group:X] may be locally reordered (higher complexity
                  first) so demanding tasks claim peak-energy slots.
        free_slots: Chronologically sorted list of {"start", "end"} dicts.
        user_energy_levels: e.g. {"morning": "high", "afternoon": "medium",
                             "evening": "low"}. Defaults to that mapping.
        work_start: User's working hours start "HH:MM" (kept for API consistency).

    Returns:
        List of ProposedEvent dicts, sorted chronologically.

    ALGORITHM:
    1. Resolve each period's energy score from user_energy_levels.
    2. Decide ordering:
       - With structural tags → safe_structural_shuffle by complexity desc.
       - Without tags → preserve LLM order strictly.
    3. For each subtask, score every ELIGIBLE slot by
       abs(slot_energy - task_complexity); a slot is eligible only if it
       starts at or after min_allowed_start (the end time of the previous
       task). Tie-break by earliest start so equal-fit slots still front-load.
    4. Place the task in the best-scoring eligible slot, return remainder
       to pool.
    5. Sort scheduled events chronologically and return.

    ORDERING GUARANTEE:
    min_allowed_start grows monotonically after each placement. Slots that
    start before it are never considered, so the calendar order always
    matches the dependency order even when energy optimisation would
    otherwise pick an earlier slot for a later task.

    KEY DESIGN POINTS:
    - The user's actual energy_levels argument drives placement — no
      hard-coded "morning preference" that ignored night-owl users.
    - Complexity comes from the explicit [complexity:*] tag if present;
      duration is only a fallback because the LLM's duration estimates
      are not always reliable.
    """
    if user_energy_levels is None:
        user_energy_levels = {
            "morning": "high",
            "afternoon": "medium",
            "evening": "low",
        }

    # Normalise energy labels to numeric scores. The COMPLEXITY_SCORE table
    # is reused intentionally — both scales share the low/medium/high
    # vocabulary so they can be compared directly.
    energy_scores = {
        period: COMPLEXITY_SCORE.get(level, 2)
        for period, level in user_energy_levels.items()
    }

    # Parse and sort slots chronologically.
    slot_pool: list[tuple[datetime.datetime, datetime.datetime]] = [
        (
            datetime.datetime.fromisoformat(slot["start"]),
            datetime.datetime.fromisoformat(slot["end"]),
        )
        for slot in free_slots
    ]
    slot_pool.sort(key=lambda interval: interval[0])

    if has_any_structural_tags(subtasks):
        subtasks_for_scheduling = safe_structural_shuffle(
            subtasks,
            run_sort_key=complexity_score,
        )
    else:
        # No structural tags: STRICTLY preserve LLM-provided order.
        subtasks_for_scheduling = list(subtasks)

    scheduled: list[ProposedEvent] = []
    # Grows monotonically: each task must start no earlier than where the
    # previous task ended, so the calendar order matches the dependency order.
    min_allowed_start: datetime.datetime | None = None

    for subtask in subtasks_for_scheduling:
        duration = datetime.timedelta(minutes=subtask["duration_minutes"])
        task_complexity = complexity_score(subtask)

        # Score every ELIGIBLE slot. A slot is eligible only if it starts
        # at or after min_allowed_start. Lower diff = better energy match;
        # tie-break by earliest start so equal-fit slots still front-load.
        best_idx: int | None = None
        best_key: tuple[int, datetime.datetime] | None = None

        for idx, (slot_start, slot_end) in enumerate(slot_pool):
            if min_allowed_start is not None and slot_start < min_allowed_start:
                continue
            if slot_end - slot_start < duration:
                continue

            slot_period = _classify_slot_by_time(slot_start)
            slot_energy_score = energy_scores.get(slot_period, 2)
            score_diff = abs(slot_energy_score - task_complexity)

            key = (score_diff, slot_start)
            if best_key is None or key < best_key:
                best_key = key
                best_idx = idx

        if best_idx is None:
            continue

        slot_start, slot_end = slot_pool.pop(best_idx)
        event_end = slot_start + duration

        scheduled.append(
            ProposedEvent(
                name=subtask["name"],
                description=subtask["description"],
                start=slot_start.isoformat(),
                end=event_end.isoformat(),
            )
        )

        min_allowed_start = event_end

        if event_end < slot_end:
            slot_pool.append((event_end, slot_end))
            slot_pool.sort(key=lambda interval: interval[0])

    scheduled.sort(key=lambda event: event["start"])
    return scheduled