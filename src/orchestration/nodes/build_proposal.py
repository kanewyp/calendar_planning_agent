# =============================================================================
# src/orchestration/nodes/build_proposal.py — Assemble the final proposal
# =============================================================================
# Packages all three validated candidates, their rationales, and a
# near-duplicate flag into the format expected by the frontend.
#
# READS FROM STATE:  candidate_deadline_first, candidate_min_fragmentation,
#                     candidate_energy_aware, candidate_validations,
#                     candidate_rationales
# WRITES TO STATE:   candidates_identical
# =============================================================================

from __future__ import annotations

from typing import Any

from src.orchestration.state import AgentState, ProposedEvent


def build_proposal_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: detect near-duplicates and package proposal for frontend.

    STEPS:
    1. Read all three candidate schedules from state.
    2. Check if the three candidates are near-identical:
       a. Sort each candidate's events chronologically by start time.
       b. Compare event start/end times across all three.
       c. If all events match within a small tolerance (e.g. same start/end),
          set candidates_identical = True.
       d. Otherwise candidates_identical = False.
    3. Return {"candidates_identical": candidates_identical}.

    NOTE: When candidates_identical is True, the frontend should collapse
    the three-column view into a single "All strategies agree" view with
    a simple approve/reject flow.
    """
    candidate_keys = (
        "candidate_deadline_first",
        "candidate_min_fragmentation",
        "candidate_energy_aware",
    )
    missing = [k for k in candidate_keys if k not in state]
    if missing:
        raise ValueError(
            f"build_proposal_node missing required candidate keys: {missing}"
        )

    signatures: list[list[tuple[str, str, str, str]]] = []
    required_event_keys = {"name", "description", "start", "end"}
    for key in candidate_keys:
        candidate = state[key]
        if not isinstance(candidate, list):
            raise ValueError(
                f"build_proposal_node: {key} is not a list (got {type(candidate).__name__})"
            )

        normalized_candidate: list[tuple[str, str, str, str]] = []
        for index, event in enumerate(candidate, start=1):
            if not isinstance(event, dict):
                raise ValueError(
                    f"build_proposal_node: {key} event {index} is not an object"
                )

            missing_keys = required_event_keys - set(event)
            if missing_keys:
                raise ValueError(
                    f"build_proposal_node: {key} event {index} missing keys "
                    f"{sorted(missing_keys)}"
                )

            normalized_candidate.append(
                (
                    event["name"],
                    event["description"],
                    event["start"],
                    event["end"],
                )
            )

        signature = sorted(
            normalized_candidate
        )
        signatures.append(signature)

    candidates_identical = signatures[0] == signatures[1] == signatures[2]
    return {"candidates_identical": candidates_identical}
