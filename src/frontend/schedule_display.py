# =============================================================================
# src/frontend/schedule_display.py — Month-calendar review view
# =============================================================================
# Renders the agent's three candidate schedules as a Google-Calendar-like month
# view. The user toggles between heuristics in the top-right and sees both the
# proposed events and their existing busy_blocks so overlaps are visible.
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
from streamlit_calendar import calendar as st_calendar

from src.frontend.calendar_events import (
    STRATEGY_COLORS,
    STRATEGY_STATE_KEYS,
    build_calendar_events,
)
from src.orchestration.state import AgentState, ValidationResult


STRATEGY_LABELS: dict[str, tuple[str, str]] = {
    "deadline_first": ("Finish Earliest", "Maximises buffer before deadline"),
    "min_fragmentation": ("Keep Time Contiguous", "Fills largest slots first"),
    "energy_aware": ("Energy-Aware", "Heavy work mornings, light afternoons"),
}

ACTIVE_STRATEGY_KEY = "active_strategy_view"
SELECTED_EVENT_KEY = "selected_calendar_event"


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


def _initial_calendar_date(state: AgentState) -> str:
    """Pick a sensible focus date for the calendar's initial render."""
    candidate = (
        state.get("candidate_deadline_first")
        or state.get("candidate_min_fragmentation")
        or state.get("candidate_energy_aware")
        or []
    )
    if candidate:
        return _parse_iso_datetime(candidate[0]["start"]).date().isoformat()

    deadline = state.get("deadline")
    if deadline:
        return str(deadline)

    return datetime.date.today().isoformat()


def _calendar_options(state: AgentState) -> dict[str, Any]:
    work_start = str(state.get("work_start") or "08:00")
    work_end = str(state.get("work_end") or "20:00")
    return {
        "initialView": "dayGridMonth",
        "initialDate": _initial_calendar_date(state),
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay",
        },
        "height": 650,
        "slotMinTime": work_start,
        "slotMaxTime": work_end,
        "navLinks": True,
        "nowIndicator": True,
        "weekNumbers": False,
        "editable": False,
        "selectable": False,
        "displayEventTime": True,
    }


def _render_strategy_toggle(state: AgentState) -> str:
    """Render the heuristic picker in the top-right and return the active key."""
    if state.get("candidates_identical", False):
        st.session_state[ACTIVE_STRATEGY_KEY] = "deadline_first"
        return "deadline_first"

    default_strategy = st.session_state.get(ACTIVE_STRATEGY_KEY, "deadline_first")
    if default_strategy not in STRATEGY_LABELS:
        default_strategy = "deadline_first"

    strategies = list(STRATEGY_LABELS.keys())
    labels = [STRATEGY_LABELS[name][0] for name in strategies]

    title_col, picker_col = st.columns([3, 2])
    with title_col:
        st.subheader("Proposed schedule")
        st.caption("Switch heuristics to compare. Gray blocks are existing events.")

    with picker_col:
        selected_label = st.radio(
            "Heuristic",
            labels,
            index=strategies.index(default_strategy),
            horizontal=True,
            label_visibility="collapsed",
            key="strategy_radio",
        )

    selected_strategy = strategies[labels.index(selected_label)]
    st.session_state[ACTIVE_STRATEGY_KEY] = selected_strategy
    return selected_strategy


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
        st.markdown(f"**{title}** — {subtitle}")
        st.info(rationale)


def _render_event_detail(click_result: dict[str, Any] | None) -> None:
    """Show details for the most recently clicked event, if any."""
    if click_result and click_result.get("callback") == "eventClick":
        event_payload = click_result.get("eventClick", {}).get("event") or {}
        if event_payload:
            st.session_state[SELECTED_EVENT_KEY] = event_payload

    selected = st.session_state.get(SELECTED_EVENT_KEY)
    if not selected:
        st.caption("Click any event in the calendar to see details.")
        return

    extended = selected.get("extendedProps", {}) or {}
    kind = extended.get("kind", "proposed")
    title = selected.get("title", "Untitled")
    start = selected.get("start", "")
    end = selected.get("end", "")

    with st.expander(f"Event details — {title}", expanded=True):
        st.write(f"**Kind:** {'AI proposal' if kind == 'proposed' else 'Existing event'}")
        st.write(f"**Time:** {start} → {end}")
        if extended.get("strategy"):
            label = STRATEGY_LABELS.get(extended["strategy"], (extended["strategy"], ""))[0]
            st.write(f"**Strategy:** {label}")
        if extended.get("description"):
            st.write(f"**Description:** {extended['description']}")
        if st.button("Clear selection", key="clear_selected_event"):
            st.session_state[SELECTED_EVENT_KEY] = None
            st.rerun()


def render_calendar_view(state: AgentState) -> str:
    """Render the month-calendar review screen and return the active strategy.

    The active strategy is also persisted in
    `st.session_state[ACTIVE_STRATEGY_KEY]` so app.py / approval_controls can
    pick it up when the user approves.
    """
    if state.get("candidates_identical", False):
        st.info("All three strategies produced the same schedule.")

    active_strategy = _render_strategy_toggle(state)
    _render_strategy_summary(state, active_strategy)

    events = build_calendar_events(state, active_strategy)
    options = _calendar_options(state)

    custom_css = "\n".join(
        [
            ".fc-event-title { font-weight: 500; }",
            ".fc-event-busy { opacity: 0.85; }",
        ]
    )

    click_result = st_calendar(
        events=events,
        options=options,
        custom_css=custom_css,
        key=f"calendar_{active_strategy}",
    )

    _render_event_detail(click_result)
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
    """Backward-compatible helper for the all-candidates-identical case.

    `render_calendar_view` already handles the identical state; this helper is
    retained because it's part of the previously published surface and a few
    callers/tests may import it directly.
    """
    st.info("All three strategies produced the same schedule.")
    render_calendar_view(state)


# Legacy aliases preserved so prior import paths keep working until callers
# migrate to `render_calendar_view`.
def render_all_candidates(state: AgentState) -> None:
    """Deprecated: kept as a thin wrapper around `render_calendar_view`."""
    render_calendar_view(state)
