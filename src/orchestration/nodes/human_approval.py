# =============================================================================
# src/orchestration/nodes/human_approval.py — Human-in-the-loop pause point
# =============================================================================
# This node is a terminal waiting point where the graph pauses until the
# frontend sends back the user's strategy choice or rejection.
#
# In the user-choice model, the frontend presents all three candidates
# side-by-side (or collapsed if near-identical). The resume_graph helper then
# records either:
#   1. A picked strategy → selected_strategy + user_approved=True
#   2. Reject all        → user_approved=False
#
# READS FROM STATE:  user_approved, selected_strategy
# WRITES TO STATE:   final_schedule (populated from the chosen candidate)
# =============================================================================

from __future__ import annotations

from typing import Any

from src.orchestration.state import AgentState


STRATEGY_TO_STATE_KEY = {
    "deadline_first": "candidate_deadline_first",
    "min_fragmentation": "candidate_min_fragmentation",
    "energy_aware": "candidate_energy_aware",
}


def human_approval_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: pause for human strategy selection.

    The graph is configured with interrupt_before=["human_approval"] so
    execution pauses before entering this node. The frontend then:
      1. Displays all three candidates with rationales and violations.
      2. Collects the user's choice (pick a strategy or reject all).
      3. Calls resume_graph with the approval decision and selected strategy.

    When the graph resumes and this node executes:

    STEPS:
    1. If state["user_approved"] is True and state["selected_strategy"] is set:
       a. Look up the candidate schedule using STRATEGY_TO_STATE_KEY.
       b. Return {"final_schedule": chosen_candidate}.
    2. If state["user_approved"] is False:
       a. Return {} — the conditional edge routes to END.
    """
    user_approved = state.get("user_approved")

    if user_approved is False:
        return {}

    if user_approved is not True:
        raise ValueError(
            "human_approval_node resumed without a boolean user_approved value "
            f"(got {user_approved!r})"
        )

    selected_strategy = state.get("selected_strategy")
    if selected_strategy not in STRATEGY_TO_STATE_KEY:
        raise ValueError(
            f"human_approval_node: invalid selected_strategy {selected_strategy!r}; "
            f"expected one of {sorted(STRATEGY_TO_STATE_KEY)}"
        )

    state_key = STRATEGY_TO_STATE_KEY[selected_strategy]
    if state_key not in state:
        raise ValueError(
            f"human_approval_node: candidate '{state_key}' is missing from state"
        )

    return {"final_schedule": state[state_key]}
