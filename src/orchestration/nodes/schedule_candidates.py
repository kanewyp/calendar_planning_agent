# =============================================================================
# src/orchestration/nodes/schedule_candidates.py — Three scheduling heuristics
# =============================================================================
# Each function is a LangGraph node that produces one candidate schedule
# by assigning subtasks to free slots using a different strategy.
#
# All three branches run in parallel (or sequentially, then scored together).
#
# READS FROM STATE:  subtasks, free_slots, work_start, work_end,
#                     max_session_minutes
# WRITES TO STATE:   candidate_deadline_first | candidate_min_fragmentation |
#                     candidate_energy_aware
# =============================================================================

from __future__ import annotations

from typing import Any

from src.orchestration.state import AgentState
from src.orchestration.heuristics.deadline_first import schedule_deadline_first
from src.orchestration.heuristics.minimize_fragmentation import schedule_min_fragmentation
from src.orchestration.heuristics.energy_aware import schedule_energy_aware


def deadline_first_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: produce a candidate via the deadline-first heuristic.

    STEPS:
    1. Extract subtasks and free_slots from state.
    2. Call schedule_deadline_first(subtasks, free_slots).
    3. Return {"candidate_deadline_first": result}.
    """
    subtasks = state.get("subtasks")
    free_slots = state.get("free_slots")

    if not isinstance(subtasks, list) or not isinstance(free_slots, list):
        raise ValueError(
            "deadline_first_node: missing subtasks/free_slots list in state"
        )

    return {
        "candidate_deadline_first": schedule_deadline_first(subtasks, free_slots)
    }


def min_fragmentation_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: produce a candidate via the minimize-fragmentation heuristic.

    STEPS:
    1. Extract subtasks and free_slots from state.
    2. Call schedule_min_fragmentation(subtasks, free_slots).
    3. Return {"candidate_min_fragmentation": result}.
    """
    subtasks = state.get("subtasks")
    free_slots = state.get("free_slots")

    if not isinstance(subtasks, list) or not isinstance(free_slots, list):
        raise ValueError(
            "min_fragmentation_node: missing subtasks/free_slots list in state"
        )

    return {
        "candidate_min_fragmentation": schedule_min_fragmentation(subtasks, free_slots)
    }


def energy_aware_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: produce a candidate via the energy-aware heuristic.

    STEPS:
    1. Extract subtasks, free_slots, and work_start from state.
    2. Call schedule_energy_aware(subtasks, free_slots, work_start).
    3. Return {"candidate_energy_aware": result}.
    """
    subtasks = state.get("subtasks")
    free_slots = state.get("free_slots")
    work_start_raw = state.get("work_start")

    if not isinstance(subtasks, list) or not isinstance(free_slots, list):
        raise ValueError("energy_aware_node: missing subtasks/free_slots list in state")

    if not isinstance(work_start_raw, str):
        raise ValueError(
            "energy_aware_node: work_start missing or not a HH:MM string"
        )

    return {
        "candidate_energy_aware": schedule_energy_aware(
            subtasks,
            free_slots,
            work_start=work_start_raw,
        )
    }
