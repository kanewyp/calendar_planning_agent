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
    pass  # TODO: implement


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
    pass  # TODO: implement


def render_collapsed_view(state: AgentState) -> None:
    """Display a single schedule when all strategies produced the same result.

    STEPS:
    1. Show st.info("All three strategies produced the same schedule.").
    2. Pick any candidate (e.g. deadline_first) and render it with
       render_single_schedule().
    3. Show the rationale from any strategy (they'll be similar).
    4. Show violations if any.
    """
    pass  # TODO: implement


def render_violation_badge(validation: ValidationResult) -> None:
    """Show a compact violation indicator.

    STEPS:
    1. If validation["passed"] → st.success("No conflicts").
    2. Else → st.error(f"{len(validation['violations'])} conflict(s)").
    3. Optionally expand to show violation details in an st.expander.
    """
    pass  # TODO: implement
