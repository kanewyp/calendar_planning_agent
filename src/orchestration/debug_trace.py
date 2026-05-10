from __future__ import annotations

import datetime
import re
from typing import Any

from src.orchestration.state import DebugTraceEvent, ProposedEvent, Subtask, ValidationResult


_TAG_PATTERN = re.compile(r"\[(?P<key>[a-z_]+)\s*:\s*(?P<value>[^\]]+)\]", re.IGNORECASE)
_MORNING_END = datetime.time(12, 0)
_AFTERNOON_END = datetime.time(17, 0)


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
    items = [_summarize_subtask(subtask) for subtask in subtasks]
    return {
        "count": len(subtasks),
        "total_minutes": total_minutes,
        "max_duration_minutes": max(
            (subtask["duration_minutes"] for subtask in subtasks),
            default=0,
        ),
        "structural_tagged_count": sum(
            1 for item in items if item["has_structural_tags"]
        ),
        "items": items,
    }


def summarize_schedule(
    schedule: list[ProposedEvent],
    *,
    energy_levels: dict[str, str] | None = None,
    event_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "event_count": len(schedule),
        "first_event": (
            _summarize_event(schedule[0], energy_levels, event_metadata)
            if schedule
            else None
        ),
        "last_event": (
            _summarize_event(schedule[-1], energy_levels, event_metadata)
            if schedule
            else None
        ),
        "events": [
            _summarize_event(event, energy_levels, event_metadata)
            for event in schedule
        ],
    }


def has_structural_tags(subtasks: list[Subtask]) -> bool:
    """Return whether any subtask carries scheduler structural tags."""
    return any(_extract_structural_tags(subtask)["has_structural_tags"] for subtask in subtasks)


def summarize_subtask_order(subtasks: list[Subtask]) -> list[str]:
    """Return subtask names in their current order for trace comparison."""
    return [subtask["name"] for subtask in subtasks]


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


def _summarize_subtask(subtask: Subtask) -> dict[str, Any]:
    tags = _extract_structural_tags(subtask)
    return {
        "name": subtask["name"],
        "duration_minutes": subtask["duration_minutes"],
        **tags,
    }


def _extract_structural_tags(subtask: Subtask) -> dict[str, Any]:
    text = f"{subtask['name']} {subtask['description']}"
    raw_tags = {
        match.group("key").strip().lower(): match.group("value").strip().lower()
        for match in _TAG_PATTERN.finditer(text)
    }
    raw_seq = raw_tags.get("seq") or raw_tags.get("order")
    return {
        "has_structural_tags": bool(raw_tags),
        "group": raw_tags.get("group"),
        "seq": int(raw_seq) if raw_seq and raw_seq.isdigit() else raw_seq,
        "shuffle": _parse_bool(raw_tags.get("shuffle")),
    }


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    if value in {"yes", "true", "1"}:
        return True
    if value in {"no", "false", "0"}:
        return False
    return None


def _summarize_event(
    event: ProposedEvent,
    energy_levels: dict[str, str] | None = None,
    event_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    period = _classify_iso_period(event["start"])
    summary = {
        "name": event["name"],
        "start": event["start"],
        "end": event["end"],
        "period": period,
    }
    if energy_levels is not None:
        summary["period_energy_level"] = energy_levels.get(period)
    if event_metadata is not None:
        summary.update(event_metadata.get(event["name"], {}))
    return summary


def _classify_iso_period(value: str) -> str:
    start = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    time_value = start.time()
    if time_value < _MORNING_END:
        return "morning"
    if time_value < _AFTERNOON_END:
        return "afternoon"
    return "evening"
