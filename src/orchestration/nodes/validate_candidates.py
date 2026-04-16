# =============================================================================
# src/orchestration/nodes/validate_candidates.py — Validate all candidates
# =============================================================================
# Runs the deterministic validator on each of the three candidate schedules
# and stores per-candidate validation results. Does NOT pick a winner —
# that decision is left to the user in the frontend.
#
# READS FROM STATE:  candidate_deadline_first, candidate_min_fragmentation,
#                     candidate_energy_aware, busy_blocks, work_start,
#                     work_end, deadline
# WRITES TO STATE:   candidate_validations
# =============================================================================

from __future__ import annotations

from typing import Any

from src.orchestration.state import AgentState
from src.validator.constraints import validate_schedule


def validate_candidates_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: validate all three candidates, store results per-strategy.

    STEPS:
    1. Build the validation inputs from state:
       - busy_blocks  = state["busy_blocks"]
       - work_start   = parse state["work_start"]
       - work_end     = parse state["work_end"]
       - deadline_dt  = parse state["deadline"]

    2. For each (strategy_name, candidate) pair:
       - "deadline_first"      → state["candidate_deadline_first"]
       - "min_fragmentation"   → state["candidate_min_fragmentation"]
       - "energy_aware"        → state["candidate_energy_aware"]
       Run validate_schedule(candidate, busy_blocks, work_start, work_end, deadline_dt).

    3. Return {
           "candidate_validations": {
               "deadline_first": result_1,
               "min_fragmentation": result_2,
               "energy_aware": result_3,
           }
       }
    """
    pass  # TODO: implement
