# =============================================================================
# src/frontend/schedule_display.py — Google-Calendar-style review view
# =============================================================================
# Renders the agent's three candidate schedules as a Google-Calendar-like view
# by embedding FullCalendar 6 inside an iframe via Streamlit's `components.html`.
# Existing `busy_blocks` are drawn alongside the heuristic's proposed events so
# the user can see overlap with their real calendar.
#
# Public surface used by app.py and tests:
#   - render_calendar_view(state)        — main entry point for review phase
#   - render_violation_badge(validation) — kept for shared badge rendering
#   - render_collapsed_view(state)       — used when all candidates match
#   - _group_events_by_day(schedule)     — helper retained for unit tests
# =============================================================================

from __future__ import annotations

import datetime
from typing import Any

import streamlit as st

from config.settings import settings
from src.frontend.calendar_events import (
    STRATEGY_COLORS,
    build_calendar_events,
)
from src.frontend.calendar_html import build_calendar_html
from src.frontend.task_breakdown import render_task_breakdown
from src.orchestration.state import AgentState, ValidationResult


STRATEGY_LABELS: dict[str, tuple[str, str]] = {
    "deadline_first": ("Finish Earliest", "Maximises buffer before deadline"),
    "min_fragmentation": ("Keep Time Contiguous", "Fills largest slots first"),
    "energy_aware": ("Energy-Aware", "Heavy work mornings, light afternoons"),
}

ACTIVE_STRATEGY_KEY = "active_strategy_view"
ACTIVE_VIEW_KEY = "active_calendar_view"

_VIEW_OPTIONS: dict[str, str] = {
    "Month": "dayGridMonth",
    "Week": "timeGridWeek",
    "Day": "timeGridDay",
}

_CALENDAR_HEIGHT_BY_VIEW: dict[str, int] = {
    "dayGridMonth": 760,
    "timeGridWeek": 820,
    "timeGridDay": 820,
}


def _parse_iso_datetime(value: str) -> datetime.datetime:
    """Parse ISO datetime values from state, including trailing Z format."""
    normalized = value.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(normalized)


def _group_events_by_day(
    schedule: list[dict[str, Any]],
) -> dict[datetime.date, list[tuple[datetime.datetime, datetime.datetime, dict[str, Any]]]]:
    """Group events by calendar date, sorted by start time."""
    grouped: dict[
        datetime.date,
        list[tuple[datetime.datetime, datetime.datetime, dict[str, Any]]],
    ] = {}

    for event in schedule:
        start_dt = _parse_iso_datetime(event["start"])
        end_dt = _parse_iso_datetime(event["end"])
        grouped.setdefault(start_dt.date(), []).append((start_dt, end_dt, event))

    for events in grouped.values():
        events.sort(key=lambda item: item[0])

    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _resolve_active_strategy(state: AgentState) -> str:
    if state.get("candidates_identical", False):
        st.session_state[ACTIVE_STRATEGY_KEY] = "deadline_first"
        return "deadline_first"

    current = st.session_state.get(ACTIVE_STRATEGY_KEY, "deadline_first")
    if current not in STRATEGY_LABELS:
        current = "deadline_first"
        st.session_state[ACTIVE_STRATEGY_KEY] = current
    return current


def _render_header(state: AgentState) -> tuple[str, str]:
    """Render the heuristic + view picker row and return (strategy, view)."""
    strategy_keys = list(STRATEGY_LABELS.keys())
    strategy_labels = [STRATEGY_LABELS[name][0] for name in strategy_keys]

    title_col, view_col, picker_col = st.columns([3, 2, 3])

    with title_col:
        st.subheader("Proposed schedule")
        st.caption(
            "Gray blocks are existing events. Colored blocks are AI proposals. "
            "Click any event for details."
        )

    with view_col:
        view_label = st.radio(
            "View",
            list(_VIEW_OPTIONS.keys()),
            index=list(_VIEW_OPTIONS.keys()).index(
                st.session_state.get(ACTIVE_VIEW_KEY, "Month")
            ),
            horizontal=True,
            label_visibility="collapsed",
            key="calendar_view_radio",
        )
    st.session_state[ACTIVE_VIEW_KEY] = view_label
    initial_view = _VIEW_OPTIONS[view_label]

    with picker_col:
        if state.get("candidates_identical", False):
            st.markdown("**Heuristic**: all three matched")
            active_strategy = "deadline_first"
        else:
            current = _resolve_active_strategy(state)
            selected_label = st.radio(
                "Heuristic",
                strategy_labels,
                index=strategy_keys.index(current),
                horizontal=True,
                label_visibility="collapsed",
                key="strategy_radio",
            )
            active_strategy = strategy_keys[strategy_labels.index(selected_label)]
            st.session_state[ACTIVE_STRATEGY_KEY] = active_strategy

    return active_strategy, initial_view


def _render_strategy_summary(state: AgentState, strategy_name: str) -> None:
    title, subtitle = STRATEGY_LABELS[strategy_name]
    badge_col, info_col = st.columns([1, 4])

    validation = state.get("candidate_validations", {}).get(
        strategy_name,
        ValidationResult(passed=True, violations=[]),
    )
    rationale = state.get("candidate_rationales", {}).get(
        strategy_name,
        "No rationale available yet.",
    )

    with badge_col:
        render_violation_badge(validation)

    with info_col:
        color = STRATEGY_COLORS[strategy_name]
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:8px;"
            f"font-weight:500;font-size:15px;'>"
            f"<span style='display:inline-block;width:12px;height:12px;"
            f"border-radius:50%;background:{color};'></span>"
            f"{title} — <span style='color:#5f6368;font-weight:400;'>{subtitle}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.info(rationale)


def render_calendar_view(state: AgentState) -> str:
    """Render the calendar review screen and return the active strategy.

    The strategy is also stored in `st.session_state[ACTIVE_STRATEGY_KEY]`
    so app.py / approval_controls can pick it up when the user approves.
    """
    if state.get("candidates_identical", False):
        st.info("All three strategies produced the same schedule.")

    active_strategy, initial_view = _render_header(state)
    _render_strategy_summary(state, active_strategy)
    render_task_breakdown(state, active_strategy)

    events = build_calendar_events(state, active_strategy)
    work_start = str(state.get("work_start") or "08:00")
    work_end = str(state.get("work_end") or "20:00")
    fallback_iso = state.get("deadline") or datetime.date.today().isoformat()

    html_doc = build_calendar_html(
        events,
        initial_view=initial_view,
        work_start=work_start,
        work_end=work_end,
        fallback_date_iso=str(fallback_iso),
        app_timezone=settings.APP_TIMEZONE,
    )

    st.iframe(
        html_doc,
        height=_CALENDAR_HEIGHT_BY_VIEW.get(initial_view, 800),
    )

    if not events:
        st.caption("No events to display for this heuristic yet.")

    return active_strategy


def render_violation_badge(validation: ValidationResult) -> None:
    """Show a compact violation indicator."""
    if validation["passed"]:
        st.success("No conflicts")
        return

    violations = validation.get("violations", [])
    st.error(f"{len(violations)} conflict(s)")
    with st.expander("View conflict details"):
        for violation in violations:
            event_name = violation.get("event_name", "Unknown event")
            violation_type = violation.get("violation_type", "UNKNOWN")
            description = violation.get("description", "")
            st.write(f"- {event_name} [{violation_type}]: {description}")


def render_collapsed_view(state: AgentState) -> None:
    """Backward-compatible helper for the all-candidates-identical case."""
    st.info("All three strategies produced the same schedule.")
    render_calendar_view(state)


def render_all_candidates(state: AgentState) -> None:
    """Deprecated: kept as a thin wrapper around `render_calendar_view`."""
    render_calendar_view(state)
