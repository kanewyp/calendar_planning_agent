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

# Maximum possible energy score difference (high=3, low=1 → max diff = 2).
_MAX_SCORE_DIFF = 2


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
                  first) so demanding tasks get first pick of peak-energy
                  slots.
        free_slots: Chronologically sorted list of {"start", "end"} dicts.
        user_energy_levels: e.g. {"morning": "high", "afternoon": "medium",
                             "evening": "low"}. Defaults to that mapping.
        work_start: User's working hours start "HH:MM" (kept for API consistency).

    Returns:
        List of ProposedEvent dicts, sorted chronologically.

    ALGORITHM — SATISFICING ENERGY MATCH:
    For each task, the slot search runs in passes of increasing tolerance:
      Pass 0: find the EARLIEST slot with score_diff == 0 (perfect match).
      Pass 1: find the EARLIEST slot with score_diff == 1 (near match).
      Pass 2: find the EARLIEST slot with score_diff == 2 (any slot).
    The first pass that yields a result is used; subsequent passes are skipped.

    WHY SATISFICING INSTEAD OF GLOBAL OPTIMISATION:
    The previous implementation used key=(score_diff, slot_start) and picked
    the globally best energy match across ALL future slots. A perfect-match
    slot on May 15 would always beat a near-match slot on May 7. When
    min_allowed_start then advanced to May 15, the remaining 10+ tasks had
    only 4 days of calendar left and fell off the deadline.

    Satisficing solves this: within each energy tier, we always pick the
    EARLIEST eligible slot, so the schedule stays anchored near the present.
    A task only jumps to a far-future slot if no nearer slot of any energy
    quality is available at all.

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

        # Satisficing multi-pass: try perfect energy match first, then
        # progressively relax until any eligible slot is accepted.
        for target_diff in range(_MAX_SCORE_DIFF + 1):
            for idx, (slot_start, slot_end) in enumerate(slot_pool):
                if min_allowed_start is not None and slot_start < min_allowed_start:
                    continue
                if slot_end - slot_start < duration:
                    continue

                slot_period = _classify_slot_by_time(slot_start)
                slot_energy_score = energy_scores.get(slot_period, 2)
                score_diff = abs(slot_energy_score - task_complexity)

                if score_diff == target_diff:
                    chosen_idx = idx
                    break  # earliest slot in this tier found; stop inner scan

            if chosen_idx is not None:
                break  # best available tier found; skip remaining passes

        if chosen_idx is None:
            continue

        slot_start, slot_end = slot_pool.pop(chosen_idx)
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

        # Return remainder to pool in sorted order so subsequent passes
        # scan slots correctly.
        if event_end < slot_end:
            remainder = (event_end, slot_end)
            insert_at = next(
                (i for i, (s, _) in enumerate(slot_pool) if s >= event_end),
                len(slot_pool),
            )
            slot_pool.insert(insert_at, remainder)

    scheduled.sort(key=lambda event: event["start"])
    return scheduled