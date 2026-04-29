# =============================================================================
# src/orchestration/heuristics/deadline_first.py — Deadline-first scheduling
# =============================================================================
# Prioritises scheduling subtasks as EARLY as possible to maximise buffer
# before the deadline.  Greedy: takes the first available slot for each
# subtask in order.
#
# This is a pure function with no LLM or API calls — fully unit-testable.
# =============================================================================

from __future__ import annotations

import datetime

from src.orchestration.state import Subtask, ProposedEvent


def schedule_deadline_first(
    subtasks: list[Subtask],
    free_slots: list[dict[str, str]],
) -> list[ProposedEvent]:
    """Schedule subtasks into the earliest available free slots.

    Args:
        subtasks: Ordered list of subtasks from goal decomposition.
        free_slots: Chronologically sorted list of
                    {"start": <ISO>, "end": <ISO>} free-slot dicts.

    Returns:
        List of ProposedEvent dicts, one per subtask.

    ALGORITHM:
    1. Parse all free_slot start/end strings into datetime objects.
    2. For each subtask (in order):
       a. Iterate through available free slots.
       b. For each slot, check if (slot_end - slot_start) >= subtask.duration_minutes.
       c. If yes:
          - Create a ProposedEvent with start=slot_start,
            end=slot_start + duration.
          - If the subtask doesn't consume the entire slot, split the
            remaining portion back into the available slots list.
          - Remove the consumed portion from available slots.
          - Break to the next subtask.
       d. If a subtask's duration is longer than any single slot, consider
          splitting the subtask across multiple slots OR placing it in the
          largest slot and noting a potential violation.
    3. Return the list of ProposedEvents.

    EDGE CASES:
    - More subtasks than available slots → schedule as many as possible,
      leave the rest unscheduled and let the validator flag them.
    - Subtask longer than any free slot → place in largest slot (validator
      will flag the overflow).
    """
    available_slots: list[tuple[datetime.datetime, datetime.datetime]] = [
      (
        datetime.datetime.fromisoformat(slot["start"]),
        datetime.datetime.fromisoformat(slot["end"]),
      )
      for slot in free_slots
    ]
    available_slots.sort(key=lambda interval: interval[0])

    scheduled: list[ProposedEvent] = []

    for subtask in subtasks:
      duration = datetime.timedelta(minutes=subtask["duration_minutes"])
      chosen_idx: int | None = None

      for idx, (slot_start, slot_end) in enumerate(available_slots):
        if slot_end - slot_start >= duration:
          chosen_idx = idx
          break

      if chosen_idx is None:
        continue

      slot_start, slot_end = available_slots.pop(chosen_idx)
      event_end = slot_start + duration

      scheduled.append(
        ProposedEvent(
          name=subtask["name"],
          description=subtask["description"],
          start=slot_start.isoformat(),
          end=event_end.isoformat(),
        )
      )

      if event_end < slot_end:
        available_slots.append((event_end, slot_end))
        available_slots.sort(key=lambda interval: interval[0])

    return scheduled
