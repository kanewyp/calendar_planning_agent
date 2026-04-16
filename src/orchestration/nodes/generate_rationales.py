# =============================================================================
# src/orchestration/nodes/generate_rationales.py — Per-strategy LLM rationales
# =============================================================================
# Calls the LLM once per candidate strategy to produce a short explanation
# of the tradeoff each strategy makes. These are shown side-by-side in the
# frontend so the user can make an informed choice.
#
# READS FROM STATE:  subtasks, goal, context,
#                     candidate_deadline_first, candidate_min_fragmentation,
#                     candidate_energy_aware, candidate_validations
# WRITES TO STATE:   candidate_rationales
# =============================================================================

from __future__ import annotations

from typing import Any

from src.llm_client.client import call_llm_text
from src.orchestration.state import AgentState


STRATEGY_DESCRIPTIONS = {
    "deadline_first": "Finish as early as possible to maximise buffer before the deadline.",
    "min_fragmentation": "Keep free time contiguous by filling largest slots first.",
    "energy_aware": "Place demanding tasks in the morning, lighter ones in the afternoon.",
}

RATIONALE_PROMPT = """You are explaining one possible schedule to the user.

The user wanted to achieve: {goal}
Context: {context}

Strategy: {strategy_name} — {strategy_description}

The goal was broken into these subtasks (with estimated durations):
{subtasks_summary}

This strategy produced the following scheduled events:
{schedule_summary}

Violations found: {violation_count} ({violation_summary})

Write 2–3 sentences explaining:
1. What tradeoff this strategy makes.
2. Why this schedule looks the way it does given the user's calendar.
3. If there are violations, briefly note what they are.

Be concise, specific, and helpful.
"""


def generate_rationales_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: generate one rationale per strategy via LLM.

    STEPS:
    1. Build subtasks_summary from state["subtasks"].
    2. For each strategy ("deadline_first", "min_fragmentation", "energy_aware"):
       a. Get the candidate schedule from the corresponding state key.
       b. Build schedule_summary for that candidate.
       c. Get violation info from state["candidate_validations"][strategy].
       d. Format RATIONALE_PROMPT with all values.
       e. Call call_llm_text(prompt) to get the rationale.
    3. Return {
           "candidate_rationales": {
               "deadline_first": rationale_1,
               "min_fragmentation": rationale_2,
               "energy_aware": rationale_3,
           }
       }

    PERFORMANCE NOTE:
    This makes 3 LLM calls. Consider using a smaller/faster model
    (e.g. claude-haiku-4-5-20251001) for rationale generation.
    """
    pass  # TODO: implement
