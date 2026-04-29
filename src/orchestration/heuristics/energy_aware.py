# =============================================================================
# src/orchestration/heuristics/energy_aware.py — Energy-aware scheduling
# =============================================================================
# Places cognitively demanding subtasks in MORNING slots and lighter tasks
# in AFTERNOON slots, based on the assumption that morning hours are better
# for deep work.
#
# This is a pure function with no LLM or API calls — fully unit-testable.
# =============================================================================

from __future__ import annotations

import datetime

from src.orchestration.state import Subtask, ProposedEvent


# Define the boundary between "morning" and "afternoon"
_MORNING_END = datetime.time(12, 0)


def schedule_energy_aware(
    subtasks: list[Subtask],
    free_slots: list[dict[str, str]],
    work_start: str = "09:00",
) -> list[ProposedEvent]:
    """Schedule subtasks with energy-level awareness.

    Args:
        subtasks: Ordered list of subtasks from goal decomposition.
        free_slots: Chronologically sorted list of
                    {"start": <ISO>, "end": <ISO>} free-slot dicts.
        work_start: User's working hours start as "HH:MM".

    Returns:
        List of ProposedEvent dicts.

    ALGORITHM:
    1. Classify subtasks into "heavy" and "light":
       - Heavy: duration_minutes >= 60 (deep-work tasks).
       - Light: duration_minutes < 60 (admin / review tasks).
       (You can refine this heuristic — e.g. also use keywords in the
        name/description to infer cognitive load.)

    2. Split free slots into morning_slots (start < 12:00) and
       afternoon_slots (start >= 12:00).

    3. Schedule heavy subtasks into morning_slots first (earliest first).
       If morning slots run out, spill into afternoon slots.

    4. Schedule light subtasks into afternoon_slots first (earliest first).
       If afternoon slots run out, spill into remaining morning slots.

    5. Handle slot splitting the same way as the other heuristics.

    6. Sort final list chronologically and return.

    EDGE CASES:
    - All slots are in the morning → schedule everything there.
    - All subtasks are heavy → same as deadline_first within mornings.
    """
    parsed_slots: list[tuple[datetime.datetime, datetime.datetime]] = [
        (
            datetime.datetime.fromisoformat(slot["start"]),
            datetime.datetime.fromisoformat(slot["end"]),
        )
        for slot in free_slots
    ]
    parsed_slots.sort(key=lambda interval: interval[0])

    morning_pool = [slot for slot in parsed_slots if slot[0].time() < _MORNING_END]
    afternoon_pool = [slot for slot in parsed_slots if slot[0].time() >= _MORNING_END]

    heavy_subtasks = [subtask for subtask in subtasks if subtask["duration_minutes"] >= 60]
    light_subtasks = [subtask for subtask in subtasks if subtask["duration_minutes"] < 60]

    scheduled: list[ProposedEvent] = []

    def place_in_pool(
        subtask: Subtask,
        prefer_morning: bool,
    ) -> bool:
        """Place a subtask in the preferred pool, spilling to the other if needed.

        Remainder slots after a split are reclassified into the correct pool
        based on the remainder's start time, so morning_pool never accumulates
        slots that actually begin after noon.
        """
        duration = datetime.timedelta(minutes=subtask["duration_minutes"])
        pools = (
            (morning_pool, afternoon_pool) if prefer_morning
            else (afternoon_pool, morning_pool)
        )

        for pool in pools:
            for idx, (slot_start, slot_end) in enumerate(pool):
                if slot_end - slot_start < duration:
                    continue

                event_end = slot_start + duration
                scheduled.append(
                    ProposedEvent(
                        name=subtask["name"],
                        description=subtask["description"],
                        start=slot_start.isoformat(),
                        end=event_end.isoformat(),
                    )
                )

                pool.pop(idx)
                if event_end < slot_end:
                    # Reclassify remainder into the correct pool by its new start.
                    remainder = (event_end, slot_end)
                    if event_end.time() < _MORNING_END:
                        morning_pool.append(remainder)
                        morning_pool.sort(key=lambda interval: interval[0])
                    else:
                        afternoon_pool.append(remainder)
                        afternoon_pool.sort(key=lambda interval: interval[0])
                return True

        return False

    for subtask in heavy_subtasks:
        place_in_pool(subtask, prefer_morning=True)

    for subtask in light_subtasks:
        place_in_pool(subtask, prefer_morning=False)

    scheduled.sort(key=lambda event: event["start"])
    return scheduled
