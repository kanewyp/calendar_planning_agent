# =============================================================================
# src/orchestration/heuristics/_structural.py — Shared structural-tag parsing
# =============================================================================
# Single source of truth for the tags the decomposition LLM embeds in
# subtask name/description fields:
#
#     [group:<id>]                  — learning phase identifier
#     [seq:<integer>]               — strict ordering inside a group
#     [shuffle:yes|no]              — whether the task may be locally reordered
#     [complexity:low|medium|high]  — cognitive load (independent of duration)
#
# Imported by:
#   - The three scheduling heuristics in src/orchestration/heuristics/.
#   - The post-LLM tag-quality check in
#     src/orchestration/nodes/decompose_goal.py.
#
# Why this module exists:
#   Before consolidation the same regex + helpers were copy-pasted across
#   each heuristic. With a fourth caller arriving (decompose_goal's
#   validation) the duplication became a real drift hazard. Centralising it
#   here keeps every consumer of the tag protocol on the same parse rules.
#
# Pure functions, no LLM/API calls — fully unit-testable.
# =============================================================================

from __future__ import annotations

import re
from typing import Any, Callable

from src.orchestration.state import Subtask


# Numeric mapping for [complexity:*] AND for energy_levels values
# ("low"/"medium"/"high"). The two scales share a vocabulary so they can be
# compared as magnitudes inside energy_aware.py.
COMPLEXITY_SCORE: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

# Matches [key:value] anywhere in the text. Whitespace inside is tolerated.
# We deliberately match anywhere (not anchored) so the LLM can put tags at
# the start of a description (preferred) or scattered through it.
TAG_PATTERN = re.compile(
    r"\[(?P<key>[a-z_]+)\s*:\s*(?P<value>[^\]]+)\]",
    re.IGNORECASE,
)


def tag_map(subtask: Subtask) -> dict[str, str]:
    """Return all [key:value] tags from name+description as a lowercased dict.

    Keys and values are lowercased and whitespace-stripped. If the same key
    appears more than once, the last occurrence wins.
    """
    text = f"{subtask['name']} {subtask['description']}"
    return {
        match.group("key").strip().lower(): match.group("value").strip().lower()
        for match in TAG_PATTERN.finditer(text)
    }


def group_id(subtask: Subtask) -> str:
    """Return the [group:*] value, or 'default' when absent."""
    return tag_map(subtask).get("group", "default")


def seq_id(subtask: Subtask) -> int | None:
    """Return the [seq:N] (or [order:N]) value as int, or None.

    Tasks with a sequence id are hard-locked: they cannot be shuffled
    regardless of [shuffle:yes].
    """
    tags = tag_map(subtask)
    raw = tags.get("seq") or tags.get("order")
    if raw is None:
        return None
    return int(raw) if raw.isdigit() else None


def shuffle_allowed(subtask: Subtask) -> bool:
    """Return True when the LLM has explicitly opted into local reordering."""
    return tag_map(subtask).get("shuffle", "no") in {"yes", "true", "1"}


def complexity_score(subtask: Subtask) -> int:
    """Return a 1-3 cognitive-load score.

    Order of precedence:
    1. Explicit [complexity:low|medium|high] tag — the LLM's structured signal.
    2. Duration-based fallback when no tag is present.

    Generalisation note: we never inspect names/descriptions for keywords
    (no `if "install" in name`) so this stays usable for any domain.
    """
    raw = tag_map(subtask).get("complexity")
    if raw and raw in COMPLEXITY_SCORE:
        return COMPLEXITY_SCORE[raw]

    minutes = subtask["duration_minutes"]
    if minutes >= 90:
        return 3
    if minutes >= 60:
        return 2
    return 1


def has_any_structural_tags(subtasks: list[Subtask]) -> bool:
    """Return True if any subtask carries any [key:value] tag."""
    return any(
        TAG_PATTERN.search(f"{s['name']} {s['description']}")
        for s in subtasks
    )


def safe_structural_shuffle(
    subtasks: list[Subtask],
    run_sort_key: Callable[[Subtask], Any],
) -> list[Subtask]:
    """Return tasks in dependency-safe phase order.

    Safety guarantees:
    - Groups are phase blocks; all tasks in a group execute before the next
      group, and groups execute in first-appearance order.
    - Tasks with [seq:N] are hard-locked by sequence — never reordered.
    - Inside each group block, reordering only happens within contiguous runs
      where ALL tasks have [shuffle:yes] AND no sequence id.
    - Within each shufflable run, tasks are sorted by ``run_sort_key``
      *descending*; callers pass the ordering that best matches their heuristic
      (e.g. duration-desc for fragmentation, complexity-desc for energy fit).

    Args:
        subtasks: ordered list (LLM-provided order is the baseline).
        run_sort_key: callable(Subtask) -> sortable. Sort is reverse=True.

    Returns:
        Reordered list containing the same elements as ``subtasks``.
    """
    grouped: dict[str, list[Subtask]] = {}
    group_order: list[str] = []
    for subtask in subtasks:
        gid = group_id(subtask)
        if gid not in grouped:
            grouped[gid] = []
            group_order.append(gid)
        grouped[gid].append(subtask)

    result: list[Subtask] = []
    for gid in group_order:
        block = grouped[gid]
        i = 0
        while i < len(block):
            if seq_id(block[i]) is not None or not shuffle_allowed(block[i]):
                result.append(block[i])
                i += 1
                continue

            j = i
            run: list[Subtask] = []
            while (
                j < len(block)
                and seq_id(block[j]) is None
                and shuffle_allowed(block[j])
            ):
                run.append(block[j])
                j += 1

            run_sorted = sorted(run, key=run_sort_key, reverse=True)
            result.extend(run_sorted)
            i = j

    return result
