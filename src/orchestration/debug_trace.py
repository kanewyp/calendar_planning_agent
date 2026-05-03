from __future__ import annotations

import datetime
from typing import Any

from src.orchestration.state import DebugTraceEvent, ProposedEvent, Subtask, ValidationResult


def make_trace_event(
    node: str,
    *,
    summary: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    status: str = "success",
) -> DebugTraceEvent:
    """Build a compact, JSON-safe trace event for a graph node."""
    return DebugTraceEvent(
        node=node,
        status=status,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        summary=summary or {},
        details=details or {},
    )


def trace_update(event: DebugTraceEvent) -> dict[str, list[DebugTraceEvent]]:
    """Return a LangGraph reducer-friendly update for one trace event."""
    return {"debug_trace": [event]}


def summarize_subtasks(subtasks: list[Subtask]) -> dict[str, Any]:
    total_minutes = sum(subtask["duration_minutes"] for subtask in subtasks)
    return {
        "count": len(subtasks),
        "total_minutes": total_minutes,
        "max_duration_minutes": max(
            (subtask["duration_minutes"] for subtask in subtasks),
            default=0,
        ),
        "items": [
            {
                "name": subtask["name"],
                "duration_minutes": subtask["duration_minutes"],
            }
            for subtask in subtasks
        ],
    }


def summarize_schedule(schedule: list[ProposedEvent]) -> dict[str, Any]:
    return {
        "event_count": len(schedule),
        "first_event": _summarize_event(schedule[0]) if schedule else None,
        "last_event": _summarize_event(schedule[-1]) if schedule else None,
        "events": [_summarize_event(event) for event in schedule],
    }


def summarize_validations(
    validations: dict[str, ValidationResult],
) -> dict[str, dict[str, Any]]:
    return {
        strategy: {
            "passed": validation["passed"],
            "violation_count": len(validation["violations"]),
            "violation_types": [
                violation["violation_type"]
                for violation in validation["violations"]
            ],
        }
        for strategy, validation in validations.items()
    }


def _summarize_event(event: ProposedEvent) -> dict[str, str]:
    return {
        "name": event["name"],
        "start": event["start"],
        "end": event["end"],
    }
