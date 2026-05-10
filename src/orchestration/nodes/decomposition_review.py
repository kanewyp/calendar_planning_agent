from __future__ import annotations

import json
from typing import Any

from src.llm_client.client import call_llm_json, get_llm_metadata
from src.orchestration.debug_trace import (
    make_trace_event,
    summarize_subtasks,
    trace_update,
)
from src.orchestration.nodes.decompose_goal import (
    DECOMPOSITION_PROMPT,
    _check_tag_quality,
    parse_and_validate_subtasks,
)
from src.orchestration.state import AgentState


DECOMPOSITION_CRITIC_PROMPT = """You are a decomposition critic for a calendar planning agent.

The first agent decomposed the user's goal into subtasks. Review the plan for scheduling quality.

Return ONLY one JSON object with EXACTLY these fields:
- "passed" (boolean): true if the decomposition is good enough to schedule.
- "issues" (array): each item has "severity", "subtask", "issue", and "suggestion".
- "revision_instruction" (string): concise instruction for revising, or "" if passed.

Mark passed=false only for meaningful issues:
- an oversized or vague task that should be split
- missing preparation, practice, review, or delivery work that is clearly needed
- durations that are unrealistic for the complexity
- dependency groups that look likely to break learning/order
- tasks that are too abstract to calendar

Do not be picky about style. If the plan is schedulable and useful, pass it.

Goal: {goal}
Deadline: {deadline}
Context: {context}
Max session length: {max_session} minutes

Subtasks:
{subtasks_json}
"""


REVISION_PROMPT = """You are revising a calendar-planning decomposition after a critic review.

Use the original decomposition as a starting point, but apply the critic's requested fixes.

{decomposition_prompt}

================================================================
CRITIC REVIEW TO APPLY
================================================================
Issues:
{issues_json}

Revision instruction:
{revision_instruction}

Return the revised JSON array only.
"""


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _normalize_issue(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "severity": str(raw.get("severity", "minor")),
        "subtask": str(raw.get("subtask", "")),
        "issue": str(raw.get("issue", "")),
        "suggestion": str(raw.get("suggestion", "")),
    }


def decomposition_critic_node(state: AgentState) -> dict[str, Any]:
    """Review the initial decomposition and request at most one revision."""
    required = {"goal", "deadline", "max_session_minutes", "subtasks"}
    missing = required - set(state)
    if missing:
        raise ValueError(
            f"decomposition_critic_node missing required state keys: {sorted(missing)}"
        )

    prompt = DECOMPOSITION_CRITIC_PROMPT.format(
        goal=state["goal"],
        deadline=state["deadline"],
        context=state.get("context", ""),
        max_session=state["max_session_minutes"],
        subtasks_json=_safe_json(state["subtasks"]),
    )

    source = "llm"
    failure: dict[str, str] | None = None
    try:
        raw = call_llm_json(prompt, purpose="decomposition_critic")
    except Exception as exc:
        raw = {
            "passed": True,
            "issues": [],
            "revision_instruction": "",
        }
        source = "fallback"
        failure = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }

    if not isinstance(raw, dict):
        raise ValueError("decomposition_critic_node expected a JSON object")

    issues = [
        issue
        for issue in (_normalize_issue(item) for item in raw.get("issues", []))
        if issue is not None
    ]
    passed = bool(raw.get("passed", True))
    if not issues:
        passed = True
    revision_instruction = str(raw.get("revision_instruction", "")).strip()

    revision_count = int(state.get("decomposition_revision_count", 0))
    trace = make_trace_event(
        "decomposition_critic",
        summary={
            **get_llm_metadata("decomposition_critic"),
            "passed": passed,
            "issue_count": len(issues),
            "source": source,
            "revision_count": revision_count,
        },
        details={
            "issues": issues,
            "revision_instruction": revision_instruction,
            **({"failure": failure} if failure else {}),
        },
    )

    return {
        "decomposition_review_passed": passed,
        "decomposition_review_issues": issues,
        "decomposition_revision_instruction": revision_instruction,
        "decomposition_revision_count": revision_count,
        **trace_update(trace),
    }


def revise_decomposition_node(state: AgentState) -> dict[str, Any]:
    """Revise subtasks once using critic feedback."""
    required = {
        "goal",
        "deadline",
        "max_session_minutes",
        "subtasks",
        "decomposition_review_issues",
        "decomposition_revision_instruction",
    }
    missing = required - set(state)
    if missing:
        raise ValueError(
            f"revise_decomposition_node missing required state keys: {sorted(missing)}"
        )

    max_session = int(state["max_session_minutes"])
    decomposition_prompt = DECOMPOSITION_PROMPT.format(
        goal=state["goal"],
        deadline=state["deadline"],
        context=state.get("context", ""),
        max_session=max_session,
    )
    prompt = REVISION_PROMPT.format(
        decomposition_prompt=decomposition_prompt,
        issues_json=_safe_json(state["decomposition_review_issues"]),
        revision_instruction=state["decomposition_revision_instruction"],
    )

    raw = call_llm_json(prompt, purpose="decomposition")
    revised_subtasks = parse_and_validate_subtasks(
        raw,
        max_session=max_session,
        error_prefix="Decomposition revision failed",
    )
    tag_quality = _check_tag_quality(revised_subtasks)
    revision_count = int(state.get("decomposition_revision_count", 0)) + 1

    details = dict(summarize_subtasks(revised_subtasks))
    details["tag_quality_warnings"] = tag_quality["warnings"]
    details["original_subtask_count"] = len(state["subtasks"])

    trace = make_trace_event(
        "revise_decomposition",
        summary={
            **get_llm_metadata("decomposition"),
            "subtask_count": len(revised_subtasks),
            "revision_count": revision_count,
            "missing_group_tag_count": tag_quality["missing_group_tag_count"],
            "missing_complexity_tag_count": tag_quality["missing_complexity_tag_count"],
            "complexity_duration_mismatch_count": tag_quality[
                "complexity_duration_mismatch_count"
            ],
        },
        details=details,
    )

    return {
        "subtasks": revised_subtasks,
        "decomposition_revised": True,
        "decomposition_revision_count": revision_count,
        **trace_update(trace),
    }
