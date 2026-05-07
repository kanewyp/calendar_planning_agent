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

Goal: {goal}
Context: {context}

Strategy: {strategy_name} — {strategy_description}

User working window: {work_start} to {work_end}
User energy profile (for energy-aware interpretation):
- Morning: {energy_morning}
- Afternoon: {energy_afternoon}
- Evening: {energy_evening}

Subtask overview:
{subtasks_summary}

Schedule overview:
{schedule_summary}

Violations found: {violation_count} ({violation_summary})

Write 2 short sentences, maximum 60 words total, explaining:
1. What tradeoff this strategy makes.
2. Why this schedule looks the way it does given the user's calendar.
3. If there are violations, briefly note what they are.
4. Confirm the schedule still respects dependency/learning flow constraints.

Return plain text only. Be concise, specific, and helpful.
"""


def _root_cause(exc: BaseException) -> BaseException:
    current = exc
    while current.__cause__ is not None:
        current = current.__cause__
    return current


def _fallback_rationale(
    *,
    strategy_name: str,
    event_count: int,
    violation_count: int,
    violation_summary: str,
) -> str:
    violation_sentence = (
        "No hard-constraint violations were found."
        if violation_count == 0
        else f"Validation found {violation_count} issue(s): {violation_summary}."
    )
    return (
        f"{strategy_name} produced {event_count} scheduled event(s) using its "
        "standard scheduling tradeoff. Review the event order and times against "
        f"your calendar before approving. {violation_sentence}"
    )


def _compact_subtasks_summary(subtasks: list[dict[str, Any]]) -> str:
    total_minutes = sum(subtask["duration_minutes"] for subtask in subtasks)
    first_names = ", ".join(subtask["name"] for subtask in subtasks[:4])
    if len(subtasks) > 4:
        first_names = f"{first_names}, ..."
    return (
        f"{len(subtasks)} subtasks, {total_minutes} total minutes. "
        f"Dependency order starts with: {first_names}"
    )


def _compact_schedule_summary(candidate: list[dict[str, str]]) -> str:
    if not candidate:
        return "No events scheduled."
    first = candidate[0]
    last = candidate[-1]
    return (
        f"{len(candidate)} events. First: {first['name']} from {first['start']} "
        f"to {first['end']}. Last: {last['name']} from {last['start']} "
        f"to {last['end']}."
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

    subtasks_summary = _compact_subtasks_summary(state["subtasks"])

    strategy_state_keys = {
        "deadline_first": "candidate_deadline_first",
        "min_fragmentation": "candidate_min_fragmentation",
        "energy_aware": "candidate_energy_aware",
    }

    rationales: dict[str, str] = {}
    rationale_sources: dict[str, str] = {}
    rationale_failures: dict[str, dict[str, str]] = {}
    skip_llm_after_failure = False

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

        schedule_summary = _compact_schedule_summary(candidate)

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

        if not skip_llm_after_failure:
            try:
                rationales[strategy_name] = call_llm_text(
                    prompt,
                    purpose="rationale",
                ).strip()
                rationale_sources[strategy_name] = "llm"
                continue
            except Exception as exc:
                root = _root_cause(exc)
                rationale_failures[strategy_name] = {
                    "error_type": type(root).__name__,
                    "error_message": str(root),
                }
                skip_llm_after_failure = True

        rationales[strategy_name] = _fallback_rationale(
            strategy_name=strategy_name,
            event_count=len(candidate),
            violation_count=violation_count,
            violation_summary=violation_summary,
        )
        rationale_sources[strategy_name] = "fallback"

    trace = make_trace_event(
        "generate_rationales",
        summary={
            **get_llm_metadata("rationale"),
            "rationale_count": len(rationales),
            "fallback_rationale_count": sum(
                1 for source in rationale_sources.values() if source == "fallback"
            ),
        },
        details={
            strategy: {
                "character_count": len(rationale),
                "word_count": len(rationale.split()),
                "source": rationale_sources[strategy],
                **(
                    {"failure": rationale_failures[strategy]}
                    if strategy in rationale_failures
                    else {}
                ),
            }
            for strategy, rationale in rationales.items()
        },
    )

    return {"candidate_rationales": rationales, **trace_update(trace)}
