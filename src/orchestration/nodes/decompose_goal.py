# =============================================================================
# src/orchestration/nodes/decompose_goal.py — Goal decomposition node
# =============================================================================
# Calls the LLM to break the user's goal into concrete subtasks.
# This is the FIRST node in the graph and the most critical for quality —
# every downstream heuristic depends on the structural tags this prompt
# elicits.
#
# READS FROM STATE:  goal, deadline, context, max_session_minutes
# WRITES TO STATE:   subtasks
# =============================================================================

from __future__ import annotations

import sys
from typing import Any

from src.llm_client.client import call_llm_json, get_llm_metadata
from src.orchestration.debug_trace import (
    make_trace_event,
    summarize_subtasks,
    trace_update,
)
from src.orchestration.heuristics._structural import tag_map
from src.orchestration.state import AgentState, Subtask


# ---------------------------------------------------------------------------
# Prompt template for goal decomposition.
# ---------------------------------------------------------------------------
# This prompt is the most important LLM-facing surface in the agent. The
# scheduler downstream relies on the LLM placing prerequisites into
# *separate* [group:*] blocks; if the LLM gets that wrong the whole
# schedule can run prerequisites after their dependents.
#
# The prompt therefore:
#   - Defines a "group" by its invariant ("no prerequisites among members"),
#     not by topic.
#   - Shows worked WRONG/RIGHT examples in two unrelated domains so the rule
#     reads as general, not Python-specific.
#   - Pins durations to complexity bands so a 75-min trivial task or a
#     60-min hard task becomes obviously off-pattern to the model.
# ---------------------------------------------------------------------------
DECOMPOSITION_PROMPT = """You are an expert curriculum and project planner. Given a user's goal, deadline, and context, decompose the goal into concrete, actionable subtasks for a calendar scheduling system.

================================================================
OUTPUT FORMAT
================================================================
Return ONLY a JSON array — no markdown, no code fences, no preamble.

Each element MUST be an object with EXACTLY these three fields:
- "name"             (string)  short title
- "description"      (string)  1-2 sentences with structural tags PREFIXED
- "duration_minutes" (integer) estimated focused-work time

Field names are case-sensitive. Do NOT emit "duration" or "time" — use "duration_minutes".

================================================================
STRUCTURAL TAGS (place at the START of each description)
================================================================
Every description MUST begin with these tags, in this exact form:

    [group:<id>] [shuffle:yes|no] [complexity:low|medium|high] <prose...>

Optional fourth tag for ordered sub-steps within a group:

    [seq:<positive integer>]

----------------------------------------------------------------
[group:<id>] — read carefully, this is the most error-prone tag
----------------------------------------------------------------
A "group" is a set of tasks that share NO prerequisite relationship AMONG THEMSELVES. Tasks in the same group could be done in any order without breaking comprehension.

CRITICAL RULE: If task B requires task A to be done first (B can't make sense without A having happened), they MUST be in DIFFERENT groups. Groups execute in the order they first appear.

Self-test before assigning a group: "If I shuffled the order of these tasks within the group, would something break?" If yes → different groups. If no → same group is fine.

WORKED EXAMPLES — internalise these before writing the JSON.

  Goal: "learn Python"
  ❌ WRONG: "Install Python IDE" and "Print Hello World" both in [group:setup]
     These are NOT independent. You cannot run a script without installing
     the IDE first. Putting them in the same group says "either order is
     fine," which is false.

  ✅ RIGHT:
     - "Install Python IDE"   → [group:environment]
     - "Print Hello World"    → [group:first_program]
     Two distinct groups. Because the second group appears after the first
     in the list, it executes after.

  ✅ ALSO RIGHT: "Learn lists", "Learn tuples", "Learn dictionaries" all in
     [group:data_structures]. These three are genuine peers — none of them
     requires another to be learned first.

  Goal: "plan a wedding"
  ❌ WRONG: "Book venue" and "Send invitations" both in [group:planning]
     Invitations need a venue first. Different groups.

  ✅ RIGHT:
     - "Book venue"          → [group:venue]
     - "Send invitations"    → [group:invites]

  ✅ ALSO RIGHT: "Choose flowers", "Choose cake", "Choose music" all in
     [group:vendor_selection] — independent vendor decisions.

----------------------------------------------------------------
[shuffle:yes|no]
----------------------------------------------------------------
- "yes": this task is genuinely interchangeable with its peers in the same
  group. Use ONLY when you have verified the self-test above.
- "no":  preserve relative order. DEFAULT TO "no" when in doubt.

If a group contains tasks with [seq:N], those are hard-locked by sequence
regardless of shuffle.

----------------------------------------------------------------
[complexity:low|medium|high]
----------------------------------------------------------------
Cognitive demand. MUST be consistent with duration_minutes (see DURATION GUIDANCE).
- low:    rote, mechanical, single-step actions
- medium: applying a known concept with some practice
- high:   deep understanding, multi-step problem solving, integration

----------------------------------------------------------------
[seq:N] — optional
----------------------------------------------------------------
Use when tasks within a group must run in a specific order (1, 2, 3, ...).
Tasks with [seq:N] are not shuffled.

================================================================
DURATION GUIDANCE — read carefully, this is the second most common LLM mistake
================================================================
Set duration_minutes based on cognitive load AND material volume. VARY DURATIONS REALISTICALLY across the plan. DO NOT default everything to 60 minutes.

Use these bands and keep the [complexity:*] tag CONSISTENT:

    15-30  min   trivial action       e.g. install a tool, read a short intro     → [complexity:low]
    30-45  min   light practice       e.g. one concept with brief exercises       → [complexity:low] or [complexity:medium]
    45-75  min   standard topic       e.g. concept + hands-on exercises           → [complexity:medium]
    75-120 min   complex topic        e.g. deep dive, multi-concept integration   → [complexity:high]
    120+   min   integrative project  e.g. capstone applying many concepts        → [complexity:high]

CRITICAL — common failure modes to avoid:
- A 75-minute task with [complexity:low] is almost certainly mis-tagged or mis-estimated.
- A 60-minute task with [complexity:high] is almost certainly mis-tagged or mis-estimated.
- If most of your subtasks have the same duration_minutes, you have NOT differentiated
  by complexity. Re-estimate.
- HARD LIMIT: No single subtask may exceed {max_session} minutes. This is a hard
  system constraint. If a topic naturally takes longer, split it into two subtasks
  in separate groups. Never emit a duration_minutes value above {max_session}.

================================================================
GENERAL RULES
================================================================
- Reflect genuine domain knowledge — no filler.
- Total estimated time should be achievable before the deadline.
- The number of subtasks should fit the goal's complexity (don't pad).
- Avoid generic "review progress" tasks unless genuinely needed.

================================================================
WORKED EXAMPLE (illustrative — adapt to the user's actual goal)
================================================================
For "Learn Python basics in 2 weeks", a good decomposition looks like:

[
  {{"name": "Install Python and IDE", "description": "[group:environment] [shuffle:no] [complexity:low] Install Python 3.x and set up VS Code with the Python extension.", "duration_minutes": 30}},
  {{"name": "First program", "description": "[group:first_program] [shuffle:no] [complexity:low] Write and run a hello-world script to verify the toolchain works.", "duration_minutes": 20}},
  {{"name": "Variables and types", "description": "[group:basics] [shuffle:no] [complexity:medium] Read about variables, primitive types, and assignment with small exercises.", "duration_minutes": 50}},
  {{"name": "Lists", "description": "[group:data_structures] [shuffle:yes] [complexity:medium] Practice list creation, indexing, and common methods.", "duration_minutes": 50}},
  {{"name": "Tuples", "description": "[group:data_structures] [shuffle:yes] [complexity:medium] Practice tuple operations and immutability.", "duration_minutes": 45}},
  {{"name": "Dictionaries", "description": "[group:data_structures] [shuffle:yes] [complexity:medium] Practice dict creation, lookup, and iteration.", "duration_minutes": 60}},
  {{"name": "Loops", "description": "[group:control_flow] [shuffle:no] [complexity:medium] for/while loops and their use with collections.", "duration_minutes": 60}},
  {{"name": "Functions", "description": "[group:functions] [shuffle:no] [complexity:high] Define functions, parameters, return values, and scope.", "duration_minutes": 90}},
  {{"name": "Mini project: todo CLI", "description": "[group:capstone] [shuffle:no] [complexity:high] Build a small command-line todo app integrating dicts, loops, and functions.", "duration_minutes": 120}}
]

Notice:
- environment → first_program → basics → data_structures → control_flow → functions → capstone. Each is a distinct group; they execute in that order.
- "Lists / Tuples / Dictionaries" share a group AND have [shuffle:yes] because they are genuine peers.
- Setup tasks are 20-30 min ([complexity:low]). Concepts are 45-60 min. Functions is 90 min ([complexity:high]). The capstone is 120 min ([complexity:high]). Durations actually vary.

================================================================
USER REQUEST
================================================================
GOAL:                {goal}
DEADLINE:            {deadline}
BACKGROUND CONTEXT:  {context}
MAX SESSION LENGTH:  {max_session} minutes

Now produce the JSON array.
"""


# Bands used by the post-LLM consistency check (must match the prompt above).
_LOW_DURATION_CEILING = 45
_HIGH_DURATION_FLOOR = 75
_MAX_WARNINGS = 20


def _check_tag_quality(subtasks: list[Subtask]) -> dict[str, Any]:
    """Inspect tags for common LLM mistakes; return diagnostics for tracing.

    This function does NOT raise. It produces a structured warning report
    that is attached to the trace event so reviewers can see when the
    decomposition LLM is misbehaving (missing tags or complexity-duration
    mismatches) without breaking the pipeline.

    The heuristics already cope with missing tags by treating everything
    as group "default" with no shuffle, so absent tags degrade gracefully.

    NOTE: We intentionally cannot detect the most damaging error —
    prerequisites placed in the same shuffle group — because that would
    require domain knowledge the validator doesn't have. The prompt is
    the only fix for that class of error.
    """
    missing_group = 0
    missing_complexity = 0
    mismatch = 0
    warnings: list[str] = []

    for index, subtask in enumerate(subtasks, start=1):
        tags = tag_map(subtask)

        if "group" not in tags:
            missing_group += 1
        if "complexity" not in tags:
            missing_complexity += 1

        complexity = tags.get("complexity")
        duration = subtask["duration_minutes"]

        if complexity == "low" and duration > _LOW_DURATION_CEILING:
            mismatch += 1
            if len(warnings) < _MAX_WARNINGS:
                warnings.append(
                    f"subtask {index} '{subtask['name']}': "
                    f"[complexity:low] but {duration} min "
                    f"(low-complexity tasks should rarely exceed "
                    f"{_LOW_DURATION_CEILING} min)"
                )
        elif complexity == "high" and duration < _HIGH_DURATION_FLOOR:
            mismatch += 1
            if len(warnings) < _MAX_WARNINGS:
                warnings.append(
                    f"subtask {index} '{subtask['name']}': "
                    f"[complexity:high] but {duration} min "
                    f"(high-complexity tasks should rarely fall below "
                    f"{_HIGH_DURATION_FLOOR} min)"
                )

    return {
        "missing_group_tag_count": missing_group,
        "missing_complexity_tag_count": missing_complexity,
        "complexity_duration_mismatch_count": mismatch,
        "warnings": warnings,
    }


def decompose_goal_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: decompose the user's goal into subtasks via LLM.

    STEPS:
    1. Format DECOMPOSITION_PROMPT with state values.
    2. Call call_llm_json(prompt) — handles retries internally.
    3. Validate each item is {name, description, duration_minutes} with
       sensible types and duration <= max_session_minutes.
    4. Run _check_tag_quality to surface missing/mismatched tags as
       trace warnings (non-fatal).
    5. Return {"subtasks": subtasks_list, ...trace}.

    ERROR HANDLING:
    - If call_llm_json raises after all retries, raise a clear error.
    - Tag quality issues are reported via the trace, not raised — the
      heuristics tolerate missing tags by design.
    """
    max_session = state["max_session_minutes"]
    prompt = DECOMPOSITION_PROMPT.format(
        goal=state["goal"],
        deadline=state["deadline"],
        context=state.get("context", ""),
        max_session=max_session,
    )

    try:
        raw = call_llm_json(prompt, purpose="decomposition")
    except Exception as exc:
        # Print full error details to stderr for debugging.
        import traceback
        error_msg = f"\n{'='*70}\nDEBUG: LLM Call Failed\n{'='*70}\n"
        error_msg += f"Provider: {get_llm_metadata('decomposition')}\n"
        error_msg += f"Error Type: {type(exc).__name__}\n"
        error_msg += f"Error Message: {str(exc)}\n"
        error_msg += f"Traceback:\n{traceback.format_exc()}\n"
        error_msg += "=" * 70 + "\n"
        print(error_msg, file=sys.stderr)

        raise RuntimeError(
            f"Goal decomposition failed: {str(exc)}"
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

        # Normalise common LLM variations.
        if "duration" in item and "duration_minutes" not in item:
            item["duration_minutes"] = item.pop("duration")

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

    # Non-fatal tag-quality inspection. Surfaced through trace details so
    # reviewers can spot upstream LLM misbehaviour without breaking runs.
    tag_quality = _check_tag_quality(subtasks)

    details = dict(summarize_subtasks(subtasks))
    details["tag_quality_warnings"] = tag_quality["warnings"]

    trace = make_trace_event(
        "decompose_goal",
        summary={
            "goal": state["goal"],
            "deadline": state["deadline"],
            "subtask_count": len(subtasks),
            "missing_group_tag_count": tag_quality["missing_group_tag_count"],
            "missing_complexity_tag_count": tag_quality["missing_complexity_tag_count"],
            "complexity_duration_mismatch_count": tag_quality[
                "complexity_duration_mismatch_count"
            ],
            **get_llm_metadata("decomposition"),
        },
        details=details,
    )

    return {"subtasks": subtasks, **trace_update(trace)}