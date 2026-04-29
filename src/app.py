# =============================================================================
# src/app.py — Streamlit application entry point
# =============================================================================
# Run with:  streamlit run src/app.py
#
# This file wires together the frontend components and the orchestration
# backend. It manages Streamlit session state to hold the LangGraph execution
# state across user interactions (form submit → agent runs → user picks
# strategy → write events).
#
# STEPS TO COMPLETE:
# 1. Initialise session-state keys on first load (see _init_session_state).
# 2. Render the intake form; on submit, package inputs and kick off the graph.
# 3. While the graph is running, show a spinner / loading state.
# 4. Once the graph reaches the human-approval node, display all three
#    candidate schedules with rationales and violation badges.
# 5. On strategy pick → resume graph → write events → show success.
# 6. On reject all    → reset session → show "no changes made".
# =============================================================================

import streamlit as st

from src.frontend.intake_form import render_intake_form
from src.frontend.schedule_display import render_all_candidates
from src.frontend.approval_controls import render_strategy_buttons
from src.orchestration.graph import build_graph, run_graph_until_approval, resume_graph


def _init_session_state() -> None:
    """Ensure all required keys exist in st.session_state.

    STEPS:
    1. Set default values for:
       - "graph_state"  → None   (holds paused LangGraph state)
       - "phase"        → "intake"  (one of: intake | running | review | done)
       - "result"       → None   (final result message to display)
    2. Any additional keys your modules need can be added here.
    """
    defaults = {
      "graph_state": None,
      "graph": None,
      "user_inputs": None,
      "phase": "intake",
      "result": None,
    }
    for key, value in defaults.items():
      if key not in st.session_state:
        st.session_state[key] = value


def main() -> None:
    """Top-level Streamlit page layout and control flow.

    STEPS:
    1. Call st.set_page_config with a title and layout.
    2. Call _init_session_state().
    3. Branch on st.session_state["phase"]:

       "intake":
         a. Call render_intake_form() — returns a dict of user inputs or None.
         b. If the form was submitted, set phase to "running", store inputs.
         c. Call st.rerun() so the spinner appears on next render cycle.

       "running":
         a. Show st.spinner("Agent is planning your schedule…").
         b. Build the LangGraph graph via build_graph().
         c. Call run_graph_until_approval(graph, user_inputs).
         d. Store the returned paused state in session_state["graph_state"].
         e. Set phase to "review" and st.rerun().

       "review":
         a. Extract the graph_state.
         b. Call render_all_candidates(graph_state) — shows three columns
            (or collapsed view if candidates_identical).
         c. Call render_strategy_buttons(graph_state.get("candidates_identical", False)).
         d. If ("approve", strategy_name):
            - Set phase to "done".
            - Call resume_graph(graph, graph_state, approved=True)
              with selected_strategy=strategy_name.
            - Store success message in session_state["result"].
         e. If ("reject", None):
            - Set phase to "done".
            - Store rejection message.
         f. st.rerun().

       "done":
         a. Display st.session_state["result"] (success or rejection message).
         b. Offer a "Start over" button that resets session state.
    """
    st.set_page_config(page_title="Calendar Planning Agent", layout="wide")
    st.title("Calendar Planning Agent")
    _init_session_state()

    phase = st.session_state["phase"]

    if phase == "intake":
      user_inputs = render_intake_form()
      if user_inputs is not None:
        st.session_state["user_inputs"] = user_inputs
        st.session_state["phase"] = "running"
        st.rerun()
      return

    if phase == "running":
      with st.spinner("Agent is planning your schedule..."):
        graph = build_graph()
        paused_state = run_graph_until_approval(graph, st.session_state["user_inputs"])

      st.session_state["graph"] = graph
      st.session_state["graph_state"] = paused_state
      st.session_state["phase"] = "review"
      st.rerun()
      return

    if phase == "review":
      graph_state = st.session_state.get("graph_state")
      if not graph_state:
        st.error("Missing planning state. Please start over.")
        st.session_state["phase"] = "done"
        st.session_state["result"] = "Planning state was lost. No calendar changes were made."
        st.rerun()
        return

      render_all_candidates(graph_state)
      action, strategy_name = render_strategy_buttons(
        graph_state.get("candidates_identical", False)
      )

      if action == "approve" and strategy_name is not None:
        graph = st.session_state.get("graph") or build_graph()
        graph_state["selected_strategy"] = strategy_name
        final_state = resume_graph(graph, graph_state, approved=True)

        written_count = len(final_state.get("write_results", []))
        st.session_state["result"] = (
          f"Schedule approved with strategy '{strategy_name}'. "
          f"Created {written_count} calendar event(s)."
        )
        st.session_state["graph_state"] = final_state
        st.session_state["phase"] = "done"
        st.rerun()
        return

      if action == "reject":
        graph = st.session_state.get("graph") or build_graph()
        final_state = resume_graph(graph, graph_state, approved=False)

        st.session_state["result"] = "Schedule rejected. No calendar changes were made."
        st.session_state["graph_state"] = final_state
        st.session_state["phase"] = "done"
        st.rerun()
        return

      return

    if phase == "done":
      result_message = st.session_state.get("result")
      if result_message:
        st.success(result_message)

      if st.button("Start over", type="primary"):
        for key in ["graph_state", "graph", "user_inputs", "result"]:
          st.session_state[key] = None
        st.session_state["phase"] = "intake"
        st.rerun()


if __name__ == "__main__":
    main()
