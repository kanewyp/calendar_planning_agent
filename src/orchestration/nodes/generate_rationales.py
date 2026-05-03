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

from src.llm_client.client import call_llm_text, get_llm_metadata
from src.orchestration.debug_trace import make_trace_event, trace_update
from src.orchestration.state import AgentState


STRATEGY_DESCRIPTIONS = {
    "deadline_first": (
        "Finish as early as possible to maximize deadline buffer, ignore energy preferences, "
        "respect per-day available work hours, and preserve strict logical/dependency order."
    ),
    "min_fragmentation": (
        "Reduce context switching by favoring contiguous blocks while preserving major learning "
        "phase order; allow only dependency-safe local reordering within a phase."
    ),
    "energy_aware": (
        "Use user-provided morning/afternoon/evening energy levels and daily work-hour constraints; "
        "preserve overall learning flow and reorder only dependency-safe subtasks."
    ),
}

RATIONALE_PROMPT = """You are explaining one possible schedule to the user.

The user wanted to achieve: {goal}
Context: {context}

Strategy: {strategy_name} — {strategy_description}

User working window: {work_start} to {work_end}
User energy profile (for energy-aware interpretation):
- Morning: {energy_morning}
- Afternoon: {energy_afternoon}
- Evening: {energy_evening}

The goal was broken into these subtasks (with estimated durations):
{subtasks_summary}

This strategy produced the following scheduled events:
{schedule_summary}

Violations found: {violation_count} ({violation_summary})

Write 2–3 sentences explaining:
1. What tradeoff this strategy makes.
2. Why this schedule looks the way it does given the user's calendar.
3. If there are violations, briefly note what they are.
4. Confirm the schedule still respects dependency/learning flow constraints.

Be concise, specific, and helpful.
"""


def _fallback_rationale(
    strategy_name: str,
    strategy_description: str,
    violation_count: int,
    violation_summary: str,
    candidate_count: int,
) -> str:
    """Return a deterministic rationale when LLM generation fails.

    This keeps planning functional under transient provider/API issues.
    """
    violation_text = (
        "No hard-constraint violations were detected."
        if violation_count == 0
        else (
            f"The validator found {violation_count} issue(s): "
            f"{violation_summary}."
        )
    )
    return (
        f"This plan uses the {strategy_name} strategy: {strategy_description} "
        f"It schedules {candidate_count} event(s) based on your available calendar "
        f"time blocks and preserves the dependency-safe learning flow. "
        f"{violation_text}"
    )


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
    required_state_keys = {
        "goal",
        "subtasks",
        "candidate_deadline_first",
        "candidate_min_fragmentation",
        "candidate_energy_aware",
        "candidate_validations",
    }
    missing = required_state_keys - set(state)
    if missing:
        raise ValueError(
            f"generate_rationales_node missing required state keys: {sorted(missing)}"
        )

    subtasks_summary = "\n".join(
        f"- {s['name']} ({s['duration_minutes']} min): {s['description']}"
        for s in state["subtasks"]
    )

    strategy_state_keys = {
        "deadline_first": "candidate_deadline_first",
        "min_fragmentation": "candidate_min_fragmentation",
        "energy_aware": "candidate_energy_aware",
    }

    rationales: dict[str, str] = {}
    rationale_sources: dict[str, str] = {}
    for strategy_name, state_key in strategy_state_keys.items():
        candidate = state[state_key]

        validation = state["candidate_validations"].get(strategy_name)
        if validation is None:
            raise ValueError(
                f"generate_rationales_node: no validation result for strategy '{strategy_name}'"
            )
        violations = validation["violations"]
        violation_count = len(violations)
        violation_summary = (
            "None"
            if violation_count == 0
            else ", ".join(v["violation_type"] for v in violations)
        )

        schedule_summary = (
            "(no events scheduled)"
            if not candidate
            else "\n".join(
                f"- {e['name']}: {e['start']} to {e['end']}" for e in candidate
            )
        )

        prompt = RATIONALE_PROMPT.format(
            goal=state["goal"],
            context=state.get("context", ""),
            strategy_name=strategy_name,
            strategy_description=STRATEGY_DESCRIPTIONS[strategy_name],
            work_start=state.get("work_start", "unknown"),
            work_end=state.get("work_end", "unknown"),
            energy_morning=state.get("energy_levels", {}).get("morning", "unspecified"),
            energy_afternoon=state.get("energy_levels", {}).get("afternoon", "unspecified"),
            energy_evening=state.get("energy_levels", {}).get("evening", "unspecified"),
            subtasks_summary=subtasks_summary,
            schedule_summary=schedule_summary,
            violation_count=violation_count,
            violation_summary=violation_summary,
        )

        try:
            rationales[strategy_name] = call_llm_text(
                prompt,
                purpose="rationale",
            ).strip()
            rationale_sources[strategy_name] = "llm"
        except Exception as exc:
            _ = exc
            rationales[strategy_name] = _fallback_rationale(
                strategy_name=strategy_name,
                strategy_description=STRATEGY_DESCRIPTIONS[strategy_name],
                violation_count=violation_count,
                violation_summary=violation_summary,
                candidate_count=len(candidate),
            )
            rationale_sources[strategy_name] = "fallback"

    trace = make_trace_event(
        "generate_rationales",
        summary={
            **get_llm_metadata("rationale"),
            "rationale_count": len(rationales),
            "fallback_count": sum(
                1 for src in rationale_sources.values() if src == "fallback"
            ),
        },
        details={
            strategy: {
                "source": rationale_sources[strategy],
                "character_count": len(rationale),
                "word_count": len(rationale.split()),
            }
            for strategy, rationale in rationales.items()
        },
    )

    return {"candidate_rationales": rationales, **trace_update(trace)}
