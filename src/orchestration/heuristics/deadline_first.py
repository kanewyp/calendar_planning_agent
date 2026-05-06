# =============================================================================
# src/orchestration/heuristics/deadline_first.py — Deadline-first scheduling
# =============================================================================
# Schedules subtasks as EARLY as possible to maximise buffer before the
# deadline. Greedy: takes the first slot that fits each subtask in
# (potentially locally-reordered) order.
#
# Pure function with no LLM or API calls — fully unit-testable.
# =============================================================================

from __future__ import annotations

import datetime

from src.orchestration.state import Subtask, ProposedEvent
from src.orchestration.heuristics._structural import (
    has_any_structural_tags,
    safe_structural_shuffle,
)


def schedule_deadline_first(
    subtasks: list[Subtask],
    free_slots: list[dict[str, str]],
) -> list[ProposedEvent]:
    """Schedule subtasks into the earliest available free slots.

    Args:
        subtasks: Ordered list of subtasks. Groups are learning phases and
                  execute in first-appearance order. Within a phase, contiguous
                  [shuffle:yes] runs may be locally reordered (longer first)
                  so larger tasks claim earlier viable slots.
        free_slots: Chronologically sorted list of {"start", "end"} dicts.

    Returns:
        List of ProposedEvent dicts.

    ORDERING GUARANTEE:
    Each task's slot must start at or after the previous task's end time
    (min_allowed_start). This prevents a smaller task from being placed
    in a leftover slot that is chronologically earlier than where a larger
    task landed, which would silently invert the learning sequence on the
    calendar even when the processing order is correct.

    EDGE CASES:
    - More subtasks than slots → schedule what fits, leave the rest for
      the validator to flag.
    - Subtask longer than any free slot → skip it (validator will flag).
    """
    if has_any_structural_tags(subtasks):
        subtasks_for_scheduling = safe_structural_shuffle(
            subtasks,
            run_sort_key=lambda s: int(s["duration_minutes"]),
        )
    else:
        # No structural tags: STRICTLY preserve LLM-provided order.
        # Reordering by duration would risk violating any dependencies the
        # LLM did not explicitly mark as shufflable.
        subtasks_for_scheduling = list(subtasks)

    available_slots: list[tuple[datetime.datetime, datetime.datetime]] = [
        (
            datetime.datetime.fromisoformat(slot["start"]),
            datetime.datetime.fromisoformat(slot["end"]),
        )
        for slot in free_slots
    ]
    available_slots.sort(key=lambda interval: interval[0])

    scheduled: list[ProposedEvent] = []
    # Grows monotonically: each task must start no earlier than where the
    # previous task ended, so the calendar order matches the dependency order.
    min_allowed_start: datetime.datetime | None = None

    for subtask in subtasks_for_scheduling:
        duration = datetime.timedelta(minutes=subtask["duration_minutes"])
        chosen_idx: int | None = None
        chosen_start: datetime.datetime | None = None

        for idx, (slot_start, slot_end) in enumerate(available_slots):
            candidate_start = slot_start
            if min_allowed_start is not None and candidate_start < min_allowed_start:
                candidate_start = min_allowed_start
            if slot_end - candidate_start >= duration:
                chosen_idx = idx
                chosen_start = candidate_start
                break

        if chosen_idx is None:
            continue

        slot_start, slot_end = available_slots.pop(chosen_idx)
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

        if slot_start < event_start:
            available_slots.append((slot_start, event_start))
        if event_end < slot_end:
            available_slots.append((event_end, slot_end))
        available_slots.sort(key=lambda interval: interval[0])

    return scheduled
