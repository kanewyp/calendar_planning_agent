# =============================================================================
# src/frontend/schedule_display.py — Multi-strategy schedule display
# =============================================================================
# Renders all three candidate schedules side-by-side (or collapsed if
# near-identical) with per-strategy rationales and violation badges.
#
# STEPS TO COMPLETE:
# 1. Implement render_all_candidates for the three-column layout.
# 2. Implement render_single_schedule for a single schedule table.
# 3. Implement render_collapsed_view for the near-identical case.
# =============================================================================

from __future__ import annotations

import datetime
from typing import Any

import streamlit as st

from src.orchestration.state import AgentState, ValidationResult


STRATEGY_LABELS = {
    "deadline_first": ("Finish Earliest", "Maximises buffer before deadline"),
    "min_fragmentation": ("Keep Time Contiguous", "Fills largest slots first"),
    "energy_aware": ("Energy-Aware", "Heavy work mornings, light afternoons"),
}

STRATEGY_STATE_KEYS = {
    "deadline_first": "candidate_deadline_first",
    "min_fragmentation": "candidate_min_fragmentation",
    "energy_aware": "candidate_energy_aware",
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


def render_all_candidates(state: AgentState) -> None:
    """Display all three strategy options for the user to compare.

    STEPS:
    1. Check state["candidates_identical"].
       a. If True → call render_collapsed_view(state) and return.
    2. Create three Streamlit columns: st.columns(3).
    3. For each (strategy_name, column) pair:
       a. Read the candidate schedule from state[STRATEGY_STATE_KEYS[name]].
       b. Read the validation from state["candidate_validations"][name].
       c. Read the rationale from state["candidate_rationales"][name].
       d. In the column:
          - Render the strategy label and one-line pitch from STRATEGY_LABELS.
          - Render a violation badge: green "No conflicts" or red "N conflicts".
          - Call render_single_schedule(candidate) for the event table.
          - Render the rationale with st.info().
    """
    if state.get("candidates_identical", False):
        render_collapsed_view(state)
        return

    validations = state.get("candidate_validations", {})
    rationales = state.get("candidate_rationales", {})
    columns = st.columns(3)

    for strategy_name, column in zip(STRATEGY_LABELS, columns):
        title, subtitle = STRATEGY_LABELS[strategy_name]
        candidate_key = STRATEGY_STATE_KEYS[strategy_name]
        candidate = state.get(candidate_key, [])
        validation = validations.get(
            strategy_name,
            ValidationResult(passed=True, violations=[]),
        )
        rationale = rationales.get(strategy_name, "No rationale available yet.")

        with column:
            st.subheader(title)
            st.caption(subtitle)
            render_violation_badge(validation)
            render_single_schedule(candidate)
            st.info(rationale)


def render_single_schedule(schedule: list[dict[str, Any]]) -> None:
    """Display one candidate schedule as a table/list.

    Args:
        schedule: List of ProposedEvent dicts.

    STEPS:
    1. Format start/end into human-readable strings
       e.g. "Mon Apr 07 · 09:00–10:30".
    2. Group events by date for readability.
    3. Render with st.dataframe() or iterate with st.write() for cards.
    """
    if not schedule:
        st.caption("No events scheduled.")
        return

    st.caption(f"{len(schedule)} event(s)")
    grouped_by_day = _group_events_by_day(schedule)
    for day, events in grouped_by_day.items():
        st.markdown(f"**{day.strftime('%a, %b %d')}**")
        for start_dt, end_dt, event in events:
            time_range = f"{start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}"
            description = event.get("description", "")
            title = event.get("name", "Untitled task")

            if description:
                st.write(f"- {time_range}  {title}")
                st.caption(description)
            else:
                st.write(f"- {time_range}  {title}")

        st.divider()


def render_collapsed_view(state: AgentState) -> None:
    """Display a single schedule when all strategies produced the same result.

    STEPS:
    1. Show st.info("All three strategies produced the same schedule.").
    2. Pick any candidate (e.g. deadline_first) and render it with
       render_single_schedule().
    3. Show the rationale from any strategy (they'll be similar).
    4. Show violations if any.
    """
    st.info("All three strategies produced the same schedule.")

    candidate = state.get("candidate_deadline_first", [])
    render_single_schedule(candidate)

    validation = state.get("candidate_validations", {}).get(
        "deadline_first",
        ValidationResult(passed=True, violations=[]),
    )
    render_violation_badge(validation)

    rationale = state.get("candidate_rationales", {}).get("deadline_first")
    if rationale:
        st.info(rationale)


def render_violation_badge(validation: ValidationResult) -> None:
    """Show a compact violation indicator.

    STEPS:
    1. If validation["passed"] → st.success("No conflicts").
    2. Else → st.error(f"{len(validation['violations'])} conflict(s)").
    3. Optionally expand to show violation details in an st.expander.
    """
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
