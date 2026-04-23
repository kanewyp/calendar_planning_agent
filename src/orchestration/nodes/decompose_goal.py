# =============================================================================
# src/orchestration/nodes/decompose_goal.py — Goal decomposition node
# =============================================================================
# Calls the LLM to break the user's goal into concrete subtasks.
# This is the FIRST node in the graph and the most critical for quality.
#
# READS FROM STATE:  goal, deadline, context, max_session_minutes
# WRITES TO STATE:   subtasks
# =============================================================================

from __future__ import annotations

from typing import Any

from src.llm_client.client import call_llm_json
from src.orchestration.state import AgentState, Subtask


# ---------------------------------------------------------------------------
# Prompt template for goal decomposition
# ---------------------------------------------------------------------------
DECOMPOSITION_PROMPT = """You are an expert project planner. Given a user's goal, deadline, and context, \
decompose the goal into a list of concrete, actionable subtasks.

RULES:
- Return ONLY a JSON array — no markdown, no code fences, no preamble.
- Each element must be an object with exactly three fields:
    "name"             (string): short title for the subtask
    "description"      (string): 1–2 sentences describing what the work involves
    "duration_minutes" (integer): estimated focused-work time in minutes
- Subtasks must reflect genuine domain knowledge, be ordered logically, and
  be sized realistically for focused work sessions.
- No single subtask should exceed {max_session} minutes.
- The total estimated time should be achievable before the deadline.
- Avoid generic filler tasks like "review progress" unless truly needed.

USER GOAL: {goal}
DEADLINE: {deadline}
BACKGROUND CONTEXT: {context}
MAX SESSION LENGTH: {max_session} minutes
"""


def decompose_goal_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: decompose the user's goal into subtasks via LLM.

    STEPS:
    1. Format DECOMPOSITION_PROMPT with state values.
    2. Call call_llm_json(prompt) — this returns a parsed Python object.
       a. The LLM client handles retries internally (up to 2 retries).
    3. Validate that the response is a list of dicts with the required keys.
       a. For each item, ensure "name" is a non-empty string.
       b. Ensure "duration_minutes" is a positive integer.
       c. Ensure "duration_minutes" <= state["max_session_minutes"].
          If it exceeds, split it or cap it (implementation choice).
    4. Convert each dict into a Subtask TypedDict.
    5. Return {"subtasks": subtasks_list}.

    ERROR HANDLING:
    - If call_llm_json raises after all retries, raise a clear error
      that app.py can catch and display to the user.
    """
    max_session = state["max_session_minutes"]
    prompt = DECOMPOSITION_PROMPT.format(
        goal=state["goal"],
        deadline=state["deadline"],
        context=state.get("context", ""),
        max_session=max_session,
    )

    try:
        raw = call_llm_json(prompt)
    except Exception as exc:
        raise RuntimeError(
            "Goal decomposition failed: unable to get a valid subtask list from the LLM"
        ) from exc

    if not isinstance(raw, list) or not raw:
        raise ValueError(
            "Goal decomposition failed: expected a non-empty JSON array of subtasks"
        )

    subtasks: list[Subtask] = []
    required_keys = {"name", "description", "duration_minutes"}
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(
                f"Goal decomposition failed: subtask {index} is not an object"
            )

        missing_keys = required_keys - set(item)
        extra_keys = set(item) - required_keys
        if missing_keys or extra_keys:
            details: list[str] = []
            if missing_keys:
                details.append(f"missing keys {sorted(missing_keys)}")
            if extra_keys:
                details.append(f"unexpected keys {sorted(extra_keys)}")
            raise ValueError(
                f"Goal decomposition failed: subtask {index} has invalid fields "
                f"({', '.join(details)})"
            )

        name = item["name"]
        description = item["description"]
        duration = item["duration_minutes"]

        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Goal decomposition failed: subtask {index} has an invalid name"
            )
        if not isinstance(description, str):
            raise ValueError(
                f"Goal decomposition failed: subtask {index} has an invalid description"
            )
        if not isinstance(duration, int) or duration <= 0:
            raise ValueError(
                f"Goal decomposition failed: subtask {index} has an invalid duration"
            )
        if duration > max_session:
            raise ValueError(
                f"Goal decomposition failed: subtask {index} duration {duration} "
                f"exceeds max session {max_session}"
            )

        subtasks.append(
            Subtask(
                name=name.strip(),
                description=description,
                duration_minutes=duration,
            )
        )

    return {"subtasks": subtasks}
