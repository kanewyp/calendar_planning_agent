from __future__ import annotations

import json
from typing import Any

from src.llm_client.client import call_llm_json, get_llm_metadata
from src.orchestration.debug_trace import make_trace_event, trace_update
from src.orchestration.nodes.generate_rationales import STRATEGY_DESCRIPTIONS
from src.orchestration.state import AgentState


STRATEGY_STATE_KEYS = {
    "deadline_first": "candidate_deadline_first",
    "min_fragmentation": "candidate_min_fragmentation",
    "energy_aware": "candidate_energy_aware",
}

REVIEWER_DEFINITIONS = {
    "deadline_reviewer": (
        "Evaluate which schedule best protects the deadline and creates time buffer."
    ),
    "energy_reviewer": (
        "Evaluate which schedule best matches task complexity to the user's energy profile."
    ),
    "fragmentation_reviewer": (
        "Evaluate which schedule minimizes context switching and preserves usable focus blocks."
    ),
    "feasibility_reviewer": (
        "Evaluate which schedule is most realistic, low-risk, and easy for the user to follow."
    ),
}

REVIEW_PROMPT = """You are {reviewer_name}, one specialized reviewer in a multi-agent calendar planning system.

Reviewer focus: {reviewer_focus}

Compare the three deterministic candidate schedules. Hard validation results are authoritative.
Do not invent events. Do not recommend a strategy with hard violations unless every strategy has violations.

Return ONLY one JSON object with EXACTLY these fields:
- "recommended_strategy": one of "deadline_first", "min_fragmentation", "energy_aware"
- "scores": object mapping each strategy to an integer from 1 to 10
- "comments": object mapping each strategy to one concise sentence
- "summary": one concise sentence explaining your recommendation

Goal: {goal}
Context: {context}
Deadline: {deadline}
Working window: {work_start} to {work_end}
Energy profile: {energy_levels}

Strategy descriptions:
{strategy_descriptions}

Subtasks:
{subtasks_json}

Candidate schedules and validations:
{candidate_json}
"""


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _candidate_payload(state: AgentState) -> dict[str, Any]:
    validations = state["candidate_validations"]
    return {
        strategy: {
            "events": state[state_key],
            "validation": validations.get(strategy, {"passed": False, "violations": []}),
        }
        for strategy, state_key in STRATEGY_STATE_KEYS.items()
    }


def _fallback_review(reviewer_name: str, state: AgentState) -> dict[str, Any]:
    validations = state.get("candidate_validations", {})
    recommended = "deadline_first"
    for strategy in STRATEGY_STATE_KEYS:
        validation = validations.get(strategy)
        if validation and validation.get("passed"):
            recommended = strategy
            break

    scores = {
        strategy: 8 if strategy == recommended else 6
        for strategy in STRATEGY_STATE_KEYS
    }
    comments = {
        strategy: (
            "No hard violations were found."
            if validations.get(strategy, {}).get("passed")
            else "Hard validation found one or more issues."
        )
        for strategy in STRATEGY_STATE_KEYS
    }
    return {
        "recommended_strategy": recommended,
        "scores": scores,
        "comments": comments,
        "summary": (
            f"{reviewer_name} used deterministic validation results because "
            "the reviewer LLM was unavailable."
        ),
        "source": "fallback",
    }


def _normalize_review(raw: Any, reviewer_name: str, state: AgentState) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _fallback_review(reviewer_name, state)

    recommended = str(raw.get("recommended_strategy", "")).strip()
    if recommended not in STRATEGY_STATE_KEYS:
        recommended = _fallback_review(reviewer_name, state)["recommended_strategy"]

    raw_scores = raw.get("scores", {})
    scores: dict[str, int] = {}
    for strategy in STRATEGY_STATE_KEYS:
        try:
            score = int(raw_scores.get(strategy, 5))
        except (AttributeError, TypeError, ValueError):
            score = 5
        scores[strategy] = min(10, max(1, score))

    raw_comments = raw.get("comments", {})
    comments = {
        strategy: str(raw_comments.get(strategy, "")).strip()
        if isinstance(raw_comments, dict)
        else ""
        for strategy in STRATEGY_STATE_KEYS
    }

    return {
        "recommended_strategy": recommended,
        "scores": scores,
        "comments": comments,
        "summary": str(raw.get("summary", "")).strip(),
        "source": "llm",
    }


def review_candidates_node(state: AgentState) -> dict[str, Any]:
    """Run multiple specialized candidate reviewers inside one graph node."""
    required = {
        "goal",
        "deadline",
        "subtasks",
        "candidate_deadline_first",
        "candidate_min_fragmentation",
        "candidate_energy_aware",
        "candidate_validations",
    }
    missing = required - set(state)
    if missing:
        raise ValueError(
            f"review_candidates_node missing required state keys: {sorted(missing)}"
        )

    strategy_descriptions = _safe_json(STRATEGY_DESCRIPTIONS)
    candidate_json = _safe_json(_candidate_payload(state))
    subtasks_json = _safe_json(state["subtasks"])
    reviews: dict[str, dict[str, Any]] = {}
    failures: dict[str, dict[str, str]] = {}
    skip_llm_after_failure = False

    for reviewer_name, reviewer_focus in REVIEWER_DEFINITIONS.items():
        if not skip_llm_after_failure:
            prompt = REVIEW_PROMPT.format(
                reviewer_name=reviewer_name,
                reviewer_focus=reviewer_focus,
                goal=state["goal"],
                context=state.get("context", ""),
                deadline=state["deadline"],
                work_start=state.get("work_start", "unknown"),
                work_end=state.get("work_end", "unknown"),
                energy_levels=_safe_json(state.get("energy_levels", {})),
                strategy_descriptions=strategy_descriptions,
                subtasks_json=subtasks_json,
                candidate_json=candidate_json,
            )
            try:
                raw = call_llm_json(prompt, purpose="candidate_review")
                reviews[reviewer_name] = _normalize_review(raw, reviewer_name, state)
                continue
            except Exception as exc:
                failures[reviewer_name] = {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
                skip_llm_after_failure = True

        reviews[reviewer_name] = _fallback_review(reviewer_name, state)

    trace = make_trace_event(
        "review_candidates",
        summary={
            **get_llm_metadata("candidate_review"),
            "reviewer_count": len(reviews),
            "fallback_review_count": sum(
                1 for review in reviews.values() if review.get("source") == "fallback"
            ),
        },
        details={
            reviewer: {
                "recommended_strategy": review["recommended_strategy"],
                "scores": review["scores"],
                "source": review["source"],
                **({"failure": failures[reviewer]} if reviewer in failures else {}),
            }
            for reviewer, review in reviews.items()
        },
    )

    return {"candidate_reviews": reviews, **trace_update(trace)}
