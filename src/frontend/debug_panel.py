from __future__ import annotations

from typing import Any

import streamlit as st

from src.orchestration.state import AgentState, DebugTraceEvent


def render_debug_trace(state: AgentState) -> None:
    """Render the graph debug trace for local troubleshooting."""
    trace = state.get("debug_trace", [])
    if not trace:
        return

    with st.expander(f"Debug trace ({len(trace)} step(s))"):
        st.text_area(
            "Compact report",
            value=format_debug_report(state),
            height=280,
        )
        st.json(trace)


def format_debug_report(state: AgentState) -> str:
    """Build a compact text report that can be pasted into a debug thread."""
    trace = state.get("debug_trace", [])
    lines = [
        f"Goal: {state.get('goal', '')}",
        f"Deadline: {state.get('deadline', '')}",
        f"Work hours: {state.get('work_start', '')}-{state.get('work_end', '')}",
        f"Trace steps: {len(trace)}",
        "",
    ]

    for event in trace:
        lines.extend(_format_trace_event(event))
        lines.append("")

    return "\n".join(lines).strip()


def _format_trace_event(event: DebugTraceEvent) -> list[str]:
    node = event.get("node", "unknown")
    status = event.get("status", "unknown")
    summary = event.get("summary", {})
    details = event.get("details", {})

    lines = [f"{node} [{status}]"]
    for key, value in summary.items():
        lines.append(f"- {key}: {_compact_value(value)}")

    if node == "decompose_goal":
        items = details.get("items", [])
        lines.append(f"- subtasks: {_format_named_items(items)}")
    elif node.startswith("schedule_"):
        events = details.get("events", [])
        lines.append(f"- events: {_format_named_items(events)}")
    elif node == "validate_candidates":
        for strategy, validation in details.items():
            lines.append(
                f"- {strategy}: passed={validation.get('passed')} "
                f"violations={validation.get('violation_count')}"
            )

    return lines


def _compact_value(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, list):
        return f"{len(value)} item(s)"
    return str(value)


def _format_named_items(items: list[dict[str, Any]], limit: int = 8) -> str:
    if not items:
        return "none"

    names = [str(item.get("name", "Untitled")) for item in items[:limit]]
    if len(items) > limit:
        names.append(f"... +{len(items) - limit} more")
    return "; ".join(names)
