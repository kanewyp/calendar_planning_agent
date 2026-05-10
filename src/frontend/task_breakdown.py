from __future__ import annotations

import datetime
from collections import defaultdict, deque
from typing import Any

import streamlit as st

from src.frontend.calendar_events import STRATEGY_STATE_KEYS
from src.orchestration.heuristics._structural import TAG_PATTERN, tag_map
from src.orchestration.state import AgentState, ProposedEvent, Subtask


def _strip_structural_tags(description: str) -> str:
    """Remove scheduler-only structural tags from user-facing task text."""
    return TAG_PATTERN.sub("", description).strip()


def _parse_iso_datetime(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_schedule_window(start: str, end: str) -> str:
    start_dt = _parse_iso_datetime(start)
    end_dt = _parse_iso_datetime(end)

    day = f"{start_dt.strftime('%a %b')} {start_dt.day}"
    start_time = start_dt.strftime("%H:%M")
    end_time = end_dt.strftime("%H:%M")
    return f"{day}, {start_time}-{end_time}"


def _scheduled_events_by_name(
    schedule: list[ProposedEvent],
) -> dict[str, deque[ProposedEvent]]:
    events_by_name: dict[str, deque[ProposedEvent]] = defaultdict(deque)
    for event in schedule:
        events_by_name[event["name"]].append(event)
    return events_by_name


def build_task_breakdown_rows(
    state: AgentState,
    strategy_name: str,
) -> list[dict[str, Any]]:
    """Return table rows for subtasks plus their active-strategy placement."""
    if strategy_name not in STRATEGY_STATE_KEYS:
        raise ValueError(
            f"Unknown strategy '{strategy_name}'. "
            f"Expected one of: {sorted(STRATEGY_STATE_KEYS)}"
        )

    subtasks: list[Subtask] = list(state.get("subtasks", []) or [])
    schedule_key = STRATEGY_STATE_KEYS[strategy_name]
    schedule: list[ProposedEvent] = list(state.get(schedule_key, []) or [])
    events_by_name = _scheduled_events_by_name(schedule)

    rows: list[dict[str, Any]] = []
    for index, subtask in enumerate(subtasks, start=1):
        tags = tag_map(subtask)
        matching_event = (
            events_by_name[subtask["name"]].popleft()
            if events_by_name.get(subtask["name"])
            else None
        )

        scheduled = "Not scheduled"
        if matching_event is not None:
            scheduled = _format_schedule_window(
                matching_event["start"],
                matching_event["end"],
            )

        rows.append(
            {
                "#": index,
                "Task": subtask["name"],
                "Description": _strip_structural_tags(
                    str(subtask.get("description", ""))
                ),
                "Duration": f"{int(subtask['duration_minutes'])} min",
                "Complexity": tags.get("complexity", "-"),
                "Phase": tags.get("group", "-"),
                "Scheduled": scheduled,
            }
        )

    return rows


def render_task_breakdown(state: AgentState, active_strategy: str) -> None:
    """Render the LLM-produced task list with active-strategy schedule times."""
    rows = build_task_breakdown_rows(state, active_strategy)

    st.subheader("Task breakdown")
    if not rows:
        st.caption("No tasks were produced for this plan.")
        return

    scheduled_count = sum(1 for row in rows if row["Scheduled"] != "Not scheduled")
    total_minutes = sum(
        int(subtask["duration_minutes"])
        for subtask in state.get("subtasks", []) or []
    )

    metric_cols = st.columns(3)
    metric_cols[0].metric("Tasks", len(rows))
    metric_cols[1].metric("Scheduled", scheduled_count)
    metric_cols[2].metric("Focus time", f"{total_minutes} min")

    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            "Task": st.column_config.TextColumn("Task", width="medium"),
            "Description": st.column_config.TextColumn(
                "Description",
                width="large",
            ),
            "Duration": st.column_config.TextColumn("Duration", width="small"),
            "Complexity": st.column_config.TextColumn("Complexity", width="small"),
            "Phase": st.column_config.TextColumn("Phase", width="medium"),
            "Scheduled": st.column_config.TextColumn("Scheduled", width="medium"),
        },
    )
