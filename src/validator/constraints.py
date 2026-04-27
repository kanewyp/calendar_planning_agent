# =============================================================================
# src/validator/constraints.py — Deterministic constraint validator
# =============================================================================
# Pure Python module — NO LLM involvement.
# Checks four hard constraints on a proposed schedule and returns a
# structured report of any violations found.
#
# This module must be fully unit-testable with mock data.
#
# CONSTRAINTS CHECKED:
# 1. No proposed event overlaps an existing busy block.
# 2. No two proposed events overlap each other.
# 3. Every proposed event falls within working hours.
# 4. Every proposed event ends before or at the deadline.
# =============================================================================

from __future__ import annotations

import datetime
from typing import Any

from src.orchestration.state import ProposedEvent, Violation, ValidationResult


def validate_schedule(
    schedule: list[ProposedEvent],
    busy_blocks: list[dict[str, str]],
    work_start: datetime.time,
    work_end: datetime.time,
    deadline: datetime.datetime,
) -> ValidationResult:
    """Validate a proposed schedule against all hard constraints.

    Args:
        schedule: List of ProposedEvent dicts to validate.
        busy_blocks: Existing calendar busy blocks [{"start": ..., "end": ...}].
        work_start: Daily working hours start time (e.g. 09:00).
        work_end: Daily working hours end time (e.g. 18:00).
        deadline: Hard deadline datetime (timezone-aware).

    Returns:
        ValidationResult: {"passed": bool, "violations": [Violation, ...]}

    STEPS:
    1. Initialise an empty list: violations = []

    2. CHECK 1 — Overlap with busy blocks:
       For each proposed event:
         For each busy block:
           Parse both to datetime intervals.
           If intervals_overlap(event_start, event_end, busy_start, busy_end):
             Append Violation(
                 event_name=event["name"],
                 violation_type="OVERLAP",
                 description=f"Overlaps with existing event from {busy_start} to {busy_end}"
             )

    3. CHECK 2 — Self-overlap (proposed events overlapping each other):
       For each unique pair (i, j) where i < j:
         If intervals_overlap(event_i_start, event_i_end, event_j_start, event_j_end):
           Append Violation(
               event_name=f"{event_i['name']} & {event_j['name']}",
               violation_type="SELF_OVERLAP",
               description="Two proposed events overlap each other"
           )

    4. CHECK 3 — Working hours:
       For each proposed event:
         event_start_time = event_start.time()
         event_end_time   = event_end.time()
         If event_start_time < work_start or event_end_time > work_end:
           Append Violation(
               event_name=event["name"],
               violation_type="OUT_OF_HOURS",
               description=f"Event is outside working hours ({work_start}–{work_end})"
           )

    5. CHECK 4 — Deadline:
       For each proposed event:
         If event_end > deadline:
           Append Violation(
               event_name=event["name"],
               violation_type="DEADLINE_EXCEEDED",
               description=f"Event ends at {event_end}, after deadline {deadline}"
           )

    6. Return {"passed": len(violations) == 0, "violations": violations}
    """
    violations: list[Violation] = []

    # CHECK 1 — Overlap with busy blocks
    for event in schedule:
        event_start = datetime.datetime.fromisoformat(event["start"])
        event_end = datetime.datetime.fromisoformat(event["end"])

        for busy_block in busy_blocks:
            busy_start = datetime.datetime.fromisoformat(busy_block["start"])
            busy_end = datetime.datetime.fromisoformat(busy_block["end"])

            if intervals_overlap(event_start, event_end, busy_start, busy_end):
                violations.append(
                    Violation(
                        event_name=event["name"],
                        violation_type="OVERLAP",
                        description=f"Overlaps with existing event from {busy_start.isoformat()} to {busy_end.isoformat()}",
                    )
                )

    # CHECK 2 — Self-overlap (proposed events overlapping each other)
    for i in range(len(schedule)):
        for j in range(i + 1, len(schedule)):
            event_i = schedule[i]
            event_j = schedule[j]

            event_i_start = datetime.datetime.fromisoformat(event_i["start"])
            event_i_end = datetime.datetime.fromisoformat(event_i["end"])
            event_j_start = datetime.datetime.fromisoformat(event_j["start"])
            event_j_end = datetime.datetime.fromisoformat(event_j["end"])

            if intervals_overlap(event_i_start, event_i_end, event_j_start, event_j_end):
                violations.append(
                    Violation(
                        event_name=f"{event_i['name']} & {event_j['name']}",
                        violation_type="SELF_OVERLAP",
                        description="Two proposed events overlap each other",
                    )
                )

    # CHECK 3 — Working hours
    for event in schedule:
        event_start = datetime.datetime.fromisoformat(event["start"])
        event_end = datetime.datetime.fromisoformat(event["end"])

        event_start_time = event_start.time()
        event_end_time = event_end.time()

        if event_start_time < work_start or event_end_time > work_end:
            violations.append(
                Violation(
                    event_name=event["name"],
                    violation_type="OUT_OF_HOURS",
                    description=f"Event is outside working hours ({work_start}–{work_end})",
                )
            )

    # CHECK 4 — Deadline
    for event in schedule:
        event_end = datetime.datetime.fromisoformat(event["end"])

        if event_end > deadline:
            violations.append(
                Violation(
                    event_name=event["name"],
                    violation_type="DEADLINE_EXCEEDED",
                    description=f"Event ends at {event_end.isoformat()}, after deadline {deadline.isoformat()}",
                )
            )

    return ValidationResult(passed=len(violations) == 0, violations=violations)


def intervals_overlap(
    start_a: datetime.datetime,
    end_a: datetime.datetime,
    start_b: datetime.datetime,
    end_b: datetime.datetime,
) -> bool:
    """Return True if two time intervals [start_a, end_a) and [start_b, end_b) overlap.

    STEPS:
    1. Two intervals overlap if and only if: start_a < end_b AND start_b < end_a.
    2. Return the boolean result.
    """
    return start_a < end_b and start_b < end_a
