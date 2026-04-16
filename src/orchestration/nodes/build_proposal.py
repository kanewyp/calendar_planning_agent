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
    pass  # TODO: implement
