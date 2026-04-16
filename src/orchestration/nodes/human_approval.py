# =============================================================================
# src/orchestration/nodes/human_approval.py — Human-in-the-loop pause point
# =============================================================================
# This node is a terminal waiting point where the graph pauses until the
# frontend sends back the user's strategy choice or rejection.
#
# In the user-choice model, the frontend presents all three candidates
# side-by-side (or collapsed if near-identical) and the user either:
#   1. Picks one strategy → sets selected_strategy + user_approved=True
#   2. Rejects all        → sets user_approved=False
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
      3. Updates state["selected_strategy"] and state["user_approved"].
      4. Resumes the graph.

    When the graph resumes and this node executes:

    STEPS:
    1. If state["user_approved"] is True and state["selected_strategy"] is set:
       a. Look up the candidate schedule using STRATEGY_TO_STATE_KEY.
       b. Return {"final_schedule": chosen_candidate}.
    2. If state["user_approved"] is False:
       a. Return {} — the conditional edge routes to END.
    """
    pass  # TODO: implement
