# =============================================================================
# src/orchestration/graph.py — LangGraph directed-graph definition
# =============================================================================
# Assembles all nodes and edges into the stateful directed graph.
# Provides helper functions used by app.py to run and resume the graph.
#
# GRAPH TOPOLOGY (user-choice model):
#
#   START
#     │
#     ▼
#   decompose_goal
#     │
#     ▼
#   fetch_events  (fetches calendar + computes free slots)
#     │
#     ├──────────────────┬────────────────────┐
#     ▼                  ▼                    ▼
#   deadline_first   min_fragmentation   energy_aware   (parallel branches)
#     │                  │                    │
#     └──────────────────┴────────────────────┘
#                        │
#                        ▼
#                validate_candidates  (run validator on all 3, no winner picked)
#                        │
#                        ▼
#                generate_rationales  (LLM writes one rationale per strategy)
#                        │
#                        ▼
#                  build_proposal     (detect near-duplicates, package for UI)
#                        │
#                        ▼
#                  human_approval  ← (pause here, user picks a strategy or rejects)
#                    │         │
#               pick strategy  reject all
#                    │         │
#                    ▼         ▼
#              write_events   END
#                    │
#                    ▼
#                   END
#
# STEPS TO COMPLETE:
# 1. Import all node functions from src/orchestration/nodes/.
# 2. Build the StateGraph using the AgentState TypedDict.
# 3. Add nodes, edges, and conditional edges per the topology above.
# 4. Implement the two helper functions used by app.py.
#
# NOTE: No repair loop or score/pick-a-winner step. All three candidates
# are validated and presented to the user, who picks a strategy or rejects all.
# =============================================================================

from __future__ import annotations

import datetime
from typing import Any

from langgraph.graph import StateGraph, END

from src.orchestration.state import AgentState

# --- Import node functions ---
from src.orchestration.nodes.fetch_events import fetch_events_node
from src.orchestration.nodes.decompose_goal import decompose_goal_node
from src.orchestration.nodes.schedule_candidates import (
    deadline_first_node,
    min_fragmentation_node,
    energy_aware_node,
)
from src.orchestration.nodes.validate_candidates import validate_candidates_node
from src.orchestration.nodes.generate_rationales import generate_rationales_node
from src.orchestration.nodes.build_proposal import build_proposal_node
from src.orchestration.nodes.human_approval import human_approval_node
from src.orchestration.nodes.write_events import write_events_node


STRATEGY_TO_STATE_KEY = {
    "deadline_first": "candidate_deadline_first",
    "min_fragmentation": "candidate_min_fragmentation",
    "energy_aware": "candidate_energy_aware",
}


def _approval_decision(state: AgentState) -> str:
    """Conditional edge after human approval.

    STEPS:
    1. If state["user_approved"] is True and state["selected_strategy"] is set
       → return "write_events".
    2. Otherwise (rejected or no strategy chosen) → return END.
    """
    if state.get("user_approved") is True and state.get("selected_strategy"):
        return "write_events"
    return END


def build_graph() -> StateGraph:
    """Construct and compile the LangGraph directed graph.

    STEPS:
    1. Create graph = StateGraph(AgentState).
    2. Add nodes:
       graph.add_node("decompose_goal",        decompose_goal_node)
       graph.add_node("fetch_events",           fetch_events_node)
       graph.add_node("deadline_first",         deadline_first_node)
       graph.add_node("min_fragmentation",      min_fragmentation_node)
       graph.add_node("energy_aware",           energy_aware_node)
       graph.add_node("validate_candidates",    validate_candidates_node)
       graph.add_node("generate_rationales",    generate_rationales_node)
       graph.add_node("build_proposal",         build_proposal_node)
       graph.add_node("human_approval",         human_approval_node)
       graph.add_node("write_events",           write_events_node)

    3. Set entry point:
       graph.set_entry_point("decompose_goal")

    4. Add edges:
       decompose_goal → fetch_events
       fetch_events   → [deadline_first, min_fragmentation, energy_aware]
         (fan-out: all three run in parallel)
       deadline_first       → validate_candidates
       min_fragmentation    → validate_candidates
       energy_aware         → validate_candidates
         (fan-in: validate_candidates waits for all three)
       validate_candidates  → generate_rationales
       generate_rationales  → build_proposal
       build_proposal       → human_approval
       human_approval       → conditional(_approval_decision)
       write_events         → END

    5. Compile with interrupt_before=["human_approval"] and return.

    NOTE on parallelism:
    - LangGraph supports fan-out / fan-in natively.
    - The three heuristic nodes write to separate state keys
      (candidate_deadline_first, candidate_min_fragmentation,
       candidate_energy_aware) so no reducer conflict.
    - If using an older LangGraph version, run them sequentially
      and refactor to parallel later.
    """
    graph = StateGraph(AgentState)

    graph.add_node("decompose_goal", decompose_goal_node)
    graph.add_node("fetch_events", fetch_events_node)
    graph.add_node("deadline_first", deadline_first_node)
    graph.add_node("min_fragmentation", min_fragmentation_node)
    graph.add_node("energy_aware", energy_aware_node)
    graph.add_node("validate_candidates", validate_candidates_node)
    graph.add_node("generate_rationales", generate_rationales_node)
    graph.add_node("build_proposal", build_proposal_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("write_events", write_events_node)

    graph.set_entry_point("decompose_goal")

    graph.add_edge("decompose_goal", "fetch_events")

    graph.add_edge("fetch_events", "deadline_first")
    graph.add_edge("fetch_events", "min_fragmentation")
    graph.add_edge("fetch_events", "energy_aware")

    graph.add_edge("deadline_first", "validate_candidates")
    graph.add_edge("min_fragmentation", "validate_candidates")
    graph.add_edge("energy_aware", "validate_candidates")

    graph.add_edge("validate_candidates", "generate_rationales")
    graph.add_edge("generate_rationales", "build_proposal")
    graph.add_edge("build_proposal", "human_approval")

    graph.add_conditional_edges(
        "human_approval",
        _approval_decision,
        {
            "write_events": "write_events",
            END: END,
        },
    )
    graph.add_edge("write_events", END)

    return graph.compile(interrupt_before=["human_approval"])


def run_graph_until_approval(
    graph: Any,
    user_inputs: dict[str, Any],
) -> AgentState:
    """Execute the graph from START up to the human_approval node.

    This function is called by app.py when the user submits the intake form.
    The graph should run all nodes up to and including build_proposal, then
    pause at human_approval waiting for the user's decision.

    Args:
        graph: Compiled LangGraph graph object.
        user_inputs: Dict from the intake form (goal, deadline, etc.).

    Returns:
        The paused AgentState dict containing the proposed schedule,
        rationale, and any unresolved violations.

    STEPS:
    1. Build the initial state from user_inputs:
       initial_state = AgentState(
           goal=user_inputs["goal"],
           deadline=user_inputs["deadline"].isoformat(),
           context=user_inputs.get("context", ""),
           work_start=user_inputs["work_start"].strftime("%H:%M"),
           work_end=user_inputs["work_end"].strftime("%H:%M"),
           max_session_minutes=user_inputs["max_session_minutes"],
           selected_strategy=None,
           user_approved=None,
       )
    2. Invoke the graph with the initial state.
       - The graph pauses at human_approval (interrupt_before).
       - At this point, state contains all three candidates,
         their validations, their rationales, and candidates_identical.
    3. Return the paused state.
    """
    required_keys = {
        "goal",
        "deadline",
        "work_start",
        "work_end",
        "max_session_minutes",
    }
    missing = required_keys - set(user_inputs)
    if missing:
        raise ValueError(
            f"run_graph_until_approval missing required user inputs: {sorted(missing)}"
        )

    deadline_input = user_inputs["deadline"]
    if isinstance(deadline_input, datetime.date):
        deadline_value = deadline_input.isoformat()
    else:
        deadline_value = str(deadline_input)

    work_start_input = user_inputs["work_start"]
    if isinstance(work_start_input, datetime.time):
        work_start_value = work_start_input.strftime("%H:%M")
    else:
        work_start_value = str(work_start_input)

    work_end_input = user_inputs["work_end"]
    if isinstance(work_end_input, datetime.time):
        work_end_value = work_end_input.strftime("%H:%M")
    else:
        work_end_value = str(work_end_input)

    initial_state: AgentState = {
        "goal": str(user_inputs["goal"]),
        "deadline": deadline_value,
        "context": str(user_inputs.get("context", "")),
        "work_start": work_start_value,
        "work_end": work_end_value,
        "max_session_minutes": int(user_inputs["max_session_minutes"]),
        "selected_strategy": None,
        "user_approved": None,
    }

    paused_state = graph.invoke(initial_state)
    if not isinstance(paused_state, dict):
        raise RuntimeError(
            "run_graph_until_approval expected graph.invoke(...) to return a state dict"
        )

    return paused_state


def resume_graph(
    graph: Any,
    paused_state: AgentState,
    approved: bool,
) -> AgentState:
    """Resume graph execution after the user approves or rejects.

    Args:
        graph: Compiled LangGraph graph object.
        paused_state: State dict returned by run_graph_until_approval.
        approved: True if user clicked approve, False if rejected.

    Returns:
        Final AgentState after write_events or clean end.

    STEPS:
    1. Set paused_state["user_approved"] = approved.
    2. If approved:
       a. Set paused_state["selected_strategy"] to the user's chosen strategy.
       b. Set paused_state["final_schedule"] to the candidate matching
          the selected strategy.
    3. Resume graph execution from the human_approval node.
    4. Return the final state.
    """
    _ = graph
    resumed_state: AgentState = dict(paused_state)
    resumed_state["user_approved"] = approved

    if approved:
        selected_strategy = resumed_state.get("selected_strategy")
        if selected_strategy not in STRATEGY_TO_STATE_KEY:
            raise ValueError(
                "resume_graph: approved=True but selected_strategy is missing/invalid; "
                f"got {selected_strategy!r}"
            )

        strategy_state_key = STRATEGY_TO_STATE_KEY[selected_strategy]
        if strategy_state_key not in resumed_state:
            raise ValueError(
                "resume_graph: selected strategy has no candidate schedule in state; "
                f"missing key {strategy_state_key!r}"
            )

        resumed_state["final_schedule"] = resumed_state[strategy_state_key]

    approval_updates = human_approval_node(resumed_state)
    resumed_state.update(approval_updates)

    if _approval_decision(resumed_state) == "write_events":
        write_updates = write_events_node(resumed_state)
        resumed_state.update(write_updates)

    return resumed_state
