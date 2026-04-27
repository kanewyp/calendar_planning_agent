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

import datetime
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
   required = {
      "busy_blocks",
      "work_start",
      "work_end",
      "deadline",
      "candidate_deadline_first",
      "candidate_min_fragmentation",
      "candidate_energy_aware",
   }
   missing = required - set(state)
   if missing:
      raise ValueError(
         f"validate_candidates_node missing required state keys: {sorted(missing)}"
      )

   busy_blocks = state["busy_blocks"]
   if not isinstance(busy_blocks, list):
      raise ValueError("validate_candidates_node: busy_blocks must be a list")

   work_start = datetime.time.fromisoformat(state["work_start"])
   work_end = datetime.time.fromisoformat(state["work_end"])

   deadline_raw = state["deadline"]
   try:
      deadline_dt = datetime.datetime.fromisoformat(deadline_raw)
      if deadline_dt.tzinfo is None:
         deadline_dt = deadline_dt.replace(tzinfo=datetime.timezone.utc)
   except ValueError:
      deadline_date = datetime.date.fromisoformat(deadline_raw)
      deadline_dt = datetime.datetime.combine(
         deadline_date,
         datetime.time(23, 59, 59, 999999),
         tzinfo=datetime.timezone.utc,
      )

   validations = {
      "deadline_first": validate_schedule(
         state["candidate_deadline_first"],
         busy_blocks,
         work_start,
         work_end,
         deadline_dt,
      ),
      "min_fragmentation": validate_schedule(
         state["candidate_min_fragmentation"],
         busy_blocks,
         work_start,
         work_end,
         deadline_dt,
      ),
      "energy_aware": validate_schedule(
         state["candidate_energy_aware"],
         busy_blocks,
         work_start,
         work_end,
         deadline_dt,
      ),
   }

   return {"candidate_validations": validations}
