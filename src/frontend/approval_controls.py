# =============================================================================
# src/frontend/approval_controls.py — Strategy picker + reject button
# =============================================================================
# Renders per-strategy "Pick this plan" buttons and a "Reject all" button.
# Returns the user's choice so app.py can resume the graph.
#
# STEPS TO COMPLETE:
# 1. For each strategy, display a "Pick this plan" button.
# 2. Display a "Reject all" button separately.
# 3. Return the user's choice.
# =============================================================================

from __future__ import annotations

import streamlit as st


STRATEGY_NAMES = ["deadline_first", "min_fragmentation", "energy_aware"]
STRATEGY_BUTTON_LABELS = {
    "deadline_first": "Pick: Finish Earliest",
    "min_fragmentation": "Pick: Keep Time Contiguous",
    "energy_aware": "Pick: Energy-Aware",
}


def render_strategy_buttons(candidates_identical: bool = False) -> tuple[str | None, str | None]:
    """Render strategy selection buttons and return the user's decision.

    Args:
        candidates_identical: If True, show a single "Approve" button
            instead of three strategy buttons (all plans are the same).

    Returns:
        Tuple of (action, strategy_name):
        - ("approve", "deadline_first") if user picked a strategy
          (or approved in collapsed mode)
        - ("reject", None) if user clicked Reject
        - (None, None) if no button pressed yet

    STEPS:
    1. If candidates_identical:
       a. Show a single st.button("Approve Schedule", type="primary").
       b. On click → return ("approve", "deadline_first").
    2. Otherwise:
       a. Create three columns with st.columns(3).
       b. In each column, place a st.button with the strategy label.
       c. On any click → return ("approve", strategy_name).
    3. Below the strategy buttons, render a "Reject All" button.
       On click → return ("reject", None).
    4. If no button pressed → return (None, None).
    """
    if candidates_identical:
        if st.button("Approve Schedule", type="primary", use_container_width=True):
            return ("approve", "deadline_first")
    else:
        strategy_columns = st.columns(3)
        for strategy_name, column in zip(STRATEGY_NAMES, strategy_columns):
            label = STRATEGY_BUTTON_LABELS[strategy_name]
            with column:
                if st.button(label, type="primary", use_container_width=True):
                    return ("approve", strategy_name)

    st.divider()
    if st.button("Reject All", use_container_width=True):
        return ("reject", None)

    return (None, None)
