# =============================================================================
# src/frontend/approval_controls.py — Approve / Reject controls
# =============================================================================
# Renders an "Approve" button for the heuristic that the user has selected in
# the calendar view, plus a "Reject all" button. Returns the user's choice so
# app.py can resume the graph.
# =============================================================================

from __future__ import annotations

import streamlit as st


STRATEGY_NAMES = ["deadline_first", "min_fragmentation", "energy_aware"]
STRATEGY_DISPLAY_NAMES = {
    "deadline_first": "Finish Earliest",
    "min_fragmentation": "Keep Time Contiguous",
    "energy_aware": "Energy-Aware",
}


def render_strategy_buttons(
    candidates_identical: bool = False,
    active_strategy: str | None = None,
) -> tuple[str | None, str | None]:
    """Render approval / rejection buttons.

    Args:
        candidates_identical: If True, the three heuristics produced the same
            plan and the calendar shows that single plan.
        active_strategy: The heuristic currently displayed in the calendar
            view; used as the strategy that gets approved on click. Falls back
            to "deadline_first" if not provided (e.g. legacy callers).

    Returns:
        Tuple of (action, strategy_name):
        - ("approve", strategy_name) if user approved
        - ("reject", None) if user rejected
        - (None, None) if no button pressed yet
    """
    selected_strategy = active_strategy or "deadline_first"
    if selected_strategy not in STRATEGY_NAMES:
        selected_strategy = "deadline_first"

    st.divider()

    if candidates_identical:
        approve_label = "Approve schedule"
    else:
        display_name = STRATEGY_DISPLAY_NAMES[selected_strategy]
        approve_label = f"Approve '{display_name}'"

    approve_col, reject_col = st.columns(2)

    with approve_col:
        if st.button(
            approve_label,
            type="primary",
            use_container_width=True,
            key="approve_button",
        ):
            return ("approve", selected_strategy)

    with reject_col:
        if st.button(
            "Reject all",
            use_container_width=True,
            key="reject_button",
        ):
            return ("reject", None)

    return (None, None)
