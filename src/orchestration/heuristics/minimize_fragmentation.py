# =============================================================================
# src/orchestration/heuristics/minimize_fragmentation.py — Minimise fragmentation
# =============================================================================
# Reduces calendar fragmentation by filling each day as fully as possible
# before advancing: within dependency-safe shuffle groups, longer tasks are
# processed first and placed in the largest slot on the earliest available
# day.
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
    """Schedule subtasks to minimise calendar fragmentation.

    Args:
        subtasks: Ordered list of subtasks. Contiguous runs of [shuffle:yes]
                  tasks within the same [group:X] are reordered longest-first
                  so heavy tasks are processed before lighter ones within each
                  dependency-safe window.
        free_slots: Chronologically sorted list of {"start", "end"} dicts.

    Returns:
        List of ProposedEvent dicts.

    TWO OPERATING MODES:

    STRUCTURAL MODE (subtasks carry [group:X] / [shuffle:yes] tags):
      Task ordering: safe_structural_shuffle reorders within shuffle groups
                     by duration DESC — longer tasks are processed first.
      Slot selection: "largest slot on earliest available day"
        Step 1 — find target_date: the earliest date on which any eligible
                 slot (starts >= min_allowed_start AND long enough) exists.
        Step 2 — pick largest: among all eligible slots on target_date,
                 take the one with the greatest duration.
      Effect: heavy tasks claim large blocks early in the day; lighter tasks
              fill the gaps. Each day is used as fully as possible before the
              schedule advances. This is genuinely different from deadline_first,
              which always takes the EARLIEST slot regardless of its size (and
              may leave large afternoon blocks untouched while packing small
              tasks into small morning gaps).

    FALLBACK MODE (no structural tags — LLM did not emit tags):
      Task ordering: LLM-provided order is preserved strictly.
      Slot selection: earliest fitting slot (identical to deadline_first).
      Rationale: without shuffle groups we cannot safely reorder by duration.
                 "Largest on earliest day" without reordering is actively
                 harmful — small tasks that appear early in LLM order would
                 consume large slots before larger tasks further down the list
                 ever get a turn. Earliest-fitting-slot is the safe fallback.

    ORDERING GUARANTEE (both modes):
      min_allowed_start grows monotonically after each placement. Each task
      is placed only in a slot that starts at or after the previous task's
      end time, so calendar order always matches dependency order.

    EDGE CASES:
      - More subtasks than slots -> schedule what fits; validator flags rest.
      - Subtask longer than any remaining slot -> skip; validator flags it.
    """
    use_structural_mode = has_any_structural_tags(subtasks)

    if use_structural_mode:
        subtasks_for_scheduling = safe_structural_shuffle(
            subtasks,
            run_sort_key=lambda s: int(s["duration_minutes"]),
        )
    else:
        subtasks_for_scheduling = list(subtasks)

    # Keep pool sorted chronologically so Step 1 is a simple linear scan.
    slot_pool: list[tuple[datetime.datetime, datetime.datetime]] = sorted(
        (
            datetime.datetime.fromisoformat(slot["start"]),
            datetime.datetime.fromisoformat(slot["end"]),
        )
        for slot in free_slots
    )

    scheduled: list[ProposedEvent] = []
    # Grows monotonically: each task must start no earlier than where the
    # previous task ended, so calendar order matches dependency order.
    min_allowed_start: datetime.datetime | None = None

    for subtask in subtasks_for_scheduling:
        duration = datetime.timedelta(minutes=subtask["duration_minutes"])
        chosen_idx: int | None = None

        if use_structural_mode:
            # ── STRUCTURAL: largest slot on earliest available day ──────────

            # Step 1: earliest date with any eligible slot.
            target_date: datetime.date | None = None
            for slot_start, slot_end in slot_pool:
                if min_allowed_start is not None and slot_start < min_allowed_start:
                    continue
                if slot_end - slot_start >= duration:
                    target_date = slot_start.date()
                    break  # pool is sorted; first match is the earliest date

            if target_date is None:
                continue  # no slot fits anywhere; validator will flag

            # Step 2: largest eligible slot on that date.
            max_slot_size: datetime.timedelta | None = None
            for idx, (slot_start, slot_end) in enumerate(slot_pool):
                if min_allowed_start is not None and slot_start < min_allowed_start:
                    continue
                if slot_start.date() != target_date:
                    continue
                slot_duration = slot_end - slot_start
                if slot_duration >= duration:
                    if max_slot_size is None or slot_duration > max_slot_size:
                        max_slot_size = slot_duration
                        chosen_idx = idx

        else:
            # ── FALLBACK: earliest fitting slot (safe when order unknown) ───
            for idx, (slot_start, slot_end) in enumerate(slot_pool):
                if min_allowed_start is not None and slot_start < min_allowed_start:
                    continue
                if slot_end - slot_start >= duration:
                    chosen_idx = idx
                    break

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
            remainder = (event_end, slot_end)
            insert_at = next(
                (i for i, (s, _) in enumerate(slot_pool) if s >= event_end),
                len(slot_pool),
            )
            slot_pool.insert(insert_at, remainder)

    scheduled.sort(key=lambda event: event["start"])
    return scheduled