# =============================================================================
# src/orchestration/heuristics/minimize_fragmentation.py — Minimise fragmentation
# =============================================================================
# Places subtasks in the LARGEST available time blocks first to avoid
# scattering short sessions across the calendar.
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


def schedule_min_fragmentation(
    subtasks: list[Subtask],
    free_slots: list[dict[str, str]],
) -> list[ProposedEvent]:
    """Schedule subtasks into the largest fitting slots.

    Args:
        subtasks: Ordered list of subtasks. Order is preserved by default;
                  contiguous runs of [shuffle:yes] tasks within the same
                  [group:X] may be locally reordered (longer first) so
                  large tasks claim the biggest slots.
        free_slots: Chronologically sorted list of {"start", "end"} dicts.

    Returns:
        List of ProposedEvent dicts.

    ORDERING GUARANTEE:
    Each task's slot must start at or after the previous task's end time
    (min_allowed_start). Without this, a smaller task can slip into the
    leftover of an earlier slot that a larger task skipped — producing a
    calendar where task N+1 appears before task N even though the processing
    loop ran in the right order. The constraint grows monotonically so it
    never blocks a valid later slot.

    EDGE CASES:
    - Same as deadline_first: handle unplaceable subtasks gracefully.
    """
    if has_any_structural_tags(subtasks):
        subtasks_for_scheduling = safe_structural_shuffle(
            subtasks,
            run_sort_key=lambda s: int(s["duration_minutes"]),
        )
    else:
        # No structural tags: STRICTLY preserve LLM-provided order.
        # Reordering by duration globally would risk violating any
        # undeclared dependencies.
        subtasks_for_scheduling = list(subtasks)

    slot_pool: list[tuple[datetime.datetime, datetime.datetime]] = [
        (
            datetime.datetime.fromisoformat(slot["start"]),
            datetime.datetime.fromisoformat(slot["end"]),
        )
        for slot in free_slots
    ]

    scheduled: list[ProposedEvent] = []
    # Grows monotonically: each task must start no earlier than where the
    # previous task ended, so the calendar order matches the dependency order.
    min_allowed_start: datetime.datetime | None = None

    for subtask in subtasks_for_scheduling:
        duration = datetime.timedelta(minutes=subtask["duration_minutes"])
        chosen_idx: int | None = None
        max_slot_size: datetime.timedelta | None = None

        # Find the LARGEST slot that can fit this subtask and starts
        # at or after min_allowed_start.
        for idx, (slot_start, slot_end) in enumerate(slot_pool):
            if min_allowed_start is not None and slot_start < min_allowed_start:
                continue
            slot_duration = slot_end - slot_start
            if slot_duration >= duration:
                if max_slot_size is None or slot_duration > max_slot_size:
                    chosen_idx = idx
                    max_slot_size = slot_duration

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

        if event_end < slot_end:
            slot_pool.append((event_end, slot_end))

    scheduled.sort(key=lambda event: event["start"])
    return scheduled