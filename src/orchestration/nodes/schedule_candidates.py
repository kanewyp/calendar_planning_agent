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

import datetime
from typing import Any

from src.orchestration.debug_trace import (
    has_structural_tags,
    make_trace_event,
    summarize_schedule,
    summarize_subtask_order,
    trace_update,
)
from src.orchestration.state import AgentState
from src.orchestration.heuristics.deadline_first import schedule_deadline_first
from src.orchestration.heuristics.minimize_fragmentation import schedule_min_fragmentation
from src.orchestration.heuristics.energy_aware import schedule_energy_aware
from src.orchestration.heuristics._structural import (
    complexity_score,
    has_any_structural_tags,
    safe_structural_shuffle,
)


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

    candidate = schedule_deadline_first(subtasks, free_slots)
    return _candidate_update(
        "deadline_first",
        "candidate_deadline_first",
        candidate,
        subtasks=subtasks,
        subtask_count=len(subtasks),
        free_slot_count=len(free_slots),
        summary_extra={
        },
    )


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

    candidate = schedule_min_fragmentation(subtasks, free_slots)
    return _candidate_update(
        "min_fragmentation",
        "candidate_min_fragmentation",
        candidate,
        subtasks=subtasks,
        subtask_count=len(subtasks),
        free_slot_count=len(free_slots),
        summary_extra={
            "structural_mode": has_structural_tags(subtasks),
        },
    )


def energy_aware_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: produce a candidate via the energy-aware heuristic.

    STEPS:
    1. Extract subtasks, free_slots, work_start, and energy_levels from state.
    2. Call schedule_energy_aware(subtasks, free_slots, energy_levels).
    3. Return {"candidate_energy_aware": result}.
    """
    subtasks = state.get("subtasks")
    free_slots = state.get("free_slots")
    work_start_raw = state.get("work_start")
    energy_levels = state.get("energy_levels")

    if not isinstance(subtasks, list) or not isinstance(free_slots, list):
        raise ValueError("energy_aware_node: missing subtasks/free_slots list in state")

    if not isinstance(work_start_raw, str):
        raise ValueError(
            "energy_aware_node: work_start missing or not a HH:MM string"
        )

    candidate = schedule_energy_aware(
        subtasks,
        free_slots,
        user_energy_levels=energy_levels,
        work_start=work_start_raw,
    )
    return _candidate_update(
        "energy_aware",
        "candidate_energy_aware",
        candidate,
        subtasks=subtasks,
        subtask_count=len(subtasks),
        free_slot_count=len(free_slots),
        summary_extra={
            "energy_levels": energy_levels if isinstance(energy_levels, dict) else None,
            "structural_mode": has_structural_tags(subtasks),
        },
        schedule_energy_levels=energy_levels if isinstance(energy_levels, dict) else None,
    )


def _candidate_update(
    strategy_name: str,
    state_key: str,
    candidate: list[dict[str, Any]],
    *,
    subtasks: list[dict[str, Any]],
    subtask_count: int,
    free_slot_count: int,
    summary_extra: dict[str, Any] | None = None,
    schedule_energy_levels: dict[str, str] | None = None,
) -> dict[str, Any]:
    expected_order = _expected_order_for_strategy(strategy_name, subtasks)
    order_diagnostics = _order_diagnostics(expected_order, candidate)
    summary = {
        "strategy": strategy_name,
        "scheduled_event_count": len(candidate),
        "unscheduled_subtask_count": max(subtask_count - len(candidate), 0),
        "free_slot_count": free_slot_count,
        "subtask_order_before": summarize_subtask_order(subtasks),
        "expected_dependency_order": summarize_subtask_order(expected_order),
        "scheduled_order": _scheduled_order(candidate),
        "chronological_order": order_diagnostics["chronological_order"],
        "order_inversion_count": order_diagnostics["order_inversion_count"],
    }
    if summary_extra:
        summary.update(summary_extra)

    details = summarize_schedule(candidate, energy_levels=schedule_energy_levels)
    details["order_inversions"] = order_diagnostics["order_inversions"]
    details["order_inversion_sample_limit"] = order_diagnostics[
        "order_inversion_sample_limit"
    ]

    trace = make_trace_event(
        f"schedule_{strategy_name}",
        summary=summary,
        details=details,
    )
    return {state_key: candidate, **trace_update(trace)}


def _scheduled_order(candidate: list[dict[str, Any]]) -> list[str]:
    return [event["name"] for event in candidate]


def _chronological_events(candidate: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidate,
        key=lambda event: datetime.datetime.fromisoformat(
            event["start"].replace("Z", "+00:00")
        ),
    )


def _order_diagnostics(
    expected_subtasks: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    sample_limit: int = 20,
) -> dict[str, Any]:
    chronological_events = _chronological_events(candidate)
    chronological_order = _scheduled_order(chronological_events)
    original_index = {
        subtask["name"]: index
        for index, subtask in enumerate(expected_subtasks)
    }
    scheduled_indices = [
        original_index.get(event["name"])
        for event in chronological_events
    ]

    inversions: list[dict[str, Any]] = []
    inversion_count = 0
    for earlier_position, earlier_index in enumerate(scheduled_indices):
        if earlier_index is None:
            continue
        for later_position in range(earlier_position + 1, len(scheduled_indices)):
            later_index = scheduled_indices[later_position]
            if later_index is None or earlier_index <= later_index:
                continue

            inversion_count += 1
            if len(inversions) >= sample_limit:
                continue

            earlier_event = chronological_events[earlier_position]
            later_event = chronological_events[later_position]
            inversions.append(
                {
                    "scheduled_before": earlier_event["name"],
                    "scheduled_before_start": earlier_event["start"],
                    "scheduled_before_original_index": earlier_index,
                    "should_have_preceded": later_event["name"],
                    "should_have_preceded_start": later_event["start"],
                    "should_have_preceded_original_index": later_index,
                }
            )

    return {
        "chronological_order": chronological_order,
        "order_inversion_count": inversion_count,
        "order_inversions": inversions,
        "order_inversion_sample_limit": sample_limit,
    }


def _expected_order_for_strategy(
    strategy_name: str,
    subtasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the dependency order a strategy is expected to preserve.

    With structural tags, groups are phase blocks and execute in the order they
    first appear. Strategy-specific shuffling is allowed only inside a phase for
    [shuffle:yes] tasks. Without structural tags, the raw LLM order remains the
    dependency contract.
    """
    if not has_any_structural_tags(subtasks):
        return subtasks

    if strategy_name == "energy_aware":
        return safe_structural_shuffle(subtasks, run_sort_key=complexity_score)

    if strategy_name in {"deadline_first", "min_fragmentation"}:
        return safe_structural_shuffle(
            subtasks,
            run_sort_key=lambda subtask: int(subtask["duration_minutes"]),
        )

    return subtasks
