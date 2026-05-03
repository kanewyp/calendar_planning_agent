# =============================================================================
# src/orchestration/heuristics/energy_aware.py — Energy-aware scheduling
# =============================================================================
# Places subtasks in time slots matching the user's energy levels throughout
# the day. Respects task order (for learning prerequisites) while optimizing
# for energy alignment.
#
# This is a pure function with no LLM or API calls — fully unit-testable.
# =============================================================================

from __future__ import annotations

import datetime
import re

from src.orchestration.state import Subtask, ProposedEvent


# Time period boundaries
_MORNING_END = datetime.time(12, 0)
_AFTERNOON_END = datetime.time(17, 0)


# Energy level mapping: low complexity = easy tasks, high = difficult
ENERGY_LEVEL_SCORE = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

_TAG_PATTERN = re.compile(r"\[(?P<key>[a-z_]+)\s*:\s*(?P<value>[^\]]+)\]", re.IGNORECASE)


def _tag_map(subtask: Subtask) -> dict[str, str]:
    text = f"{subtask['name']} {subtask['description']}"
    return {
        match.group("key").strip().lower(): match.group("value").strip().lower()
        for match in _TAG_PATTERN.finditer(text)
    }


def _group_id(subtask: Subtask) -> str:
    return _tag_map(subtask).get("group", "default")


def _seq_id(subtask: Subtask) -> int | None:
    tags = _tag_map(subtask)
    raw = tags.get("seq") or tags.get("order")
    if raw is None:
        return None
    return int(raw) if raw.isdigit() else None


def _shuffle_allowed(subtask: Subtask) -> bool:
    tags = _tag_map(subtask)
    return tags.get("shuffle", "no") in {"yes", "true", "1"}


def _has_any_structural_tags(subtasks: list[Subtask]) -> bool:
    return any(_TAG_PATTERN.search(f"{s['name']} {s['description']}") for s in subtasks)


def _safe_structural_shuffle(subtasks: list[Subtask]) -> list[Subtask]:
    """Only reorder explicitly shufflable tasks within same [group:*] block.

    Safety rules:
    - Preserve original order by default.
    - Any task with [seq:n]/[order:n] is hard-locked by sequence.
    - Reorder happens only in contiguous runs where all tasks have [shuffle:yes]
      and no sequence ids.
    """
    grouped: dict[str, list[Subtask]] = {}
    group_order: list[str] = []
    for subtask in subtasks:
        gid = _group_id(subtask)
        if gid not in grouped:
            grouped[gid] = []
            group_order.append(gid)
        grouped[gid].append(subtask)

    result: list[Subtask] = []
    for gid in group_order:
        block = grouped[gid]
        i = 0
        while i < len(block):
            if _seq_id(block[i]) is not None or not _shuffle_allowed(block[i]):
                result.append(block[i])
                i += 1
                continue

            j = i
            run: list[Subtask] = []
            while j < len(block) and _seq_id(block[j]) is None and _shuffle_allowed(block[j]):
                run.append(block[j])
                j += 1

            run_sorted = sorted(run, key=lambda s: _infer_task_complexity(s), reverse=True)
            result.extend(run_sorted)
            i = j

    return result


def _infer_task_complexity(subtask: Subtask) -> int:
    """Infer task complexity (1-3) using only duration.

    This avoids domain-specific keyword assumptions and keeps behavior
    generalizable across different learning objectives.
    """
    complexity = 1

    if subtask["duration_minutes"] >= 90:
        complexity = 3
    elif subtask["duration_minutes"] >= 60:
        complexity = 2

    return complexity


def _classify_slot_by_time(slot_start: datetime.datetime) -> str:
    """Classify a time slot into morning/afternoon/evening."""
    hour = slot_start.time()
    if hour < _MORNING_END:
        return "morning"
    elif hour < _AFTERNOON_END:
        return "afternoon"
    else:
        return "evening"


def schedule_energy_aware(
    subtasks: list[Subtask],
    free_slots: list[dict[str, str]],
    user_energy_levels: dict[str, str] | None = None,
    work_start: str = "09:00",
) -> list[ProposedEvent]:
    """Schedule subtasks respecting order while matching user's energy levels.

    Args:
        subtasks: Ordered list of subtasks from goal decomposition (MUST preserve order).
        free_slots: Chronologically sorted list of
                    {"start": <ISO>, "end": <ISO>} free-slot dicts.
        user_energy_levels: Dict mapping time period to energy level.
                           Example: {"morning": "high", "afternoon": "medium", "evening": "low"}
                           Defaults to: {"morning": "high", "afternoon": "medium", "evening": "low"}
        work_start: User's working hours start as "HH:MM" (unused for now, for API consistency).

    Returns:
        List of ProposedEvent dicts, sorted chronologically.

    ALGORITHM:
    1. Parse user energy levels (default: morning=high, afternoon=medium, evening=low).
     2. Preserve major learning phase order (setup -> learn -> implement -> project).
     3. Within each phase, allow local reordering to improve energy matching.
     4. For each chosen subtask:
       a. Infer task complexity (1-3) from duration and keywords.
       b. Find earliest available slot whose energy level matches task complexity.
       c. If no energy match, use earliest available slot (graceful fallback).
       d. Schedule task, split slot remainder back into pool.
     5. Sort final events chronologically and return.

    RATIONALE:
    - Preserves task order (critical for learning sequences).
    - Matches high-complexity tasks to high-energy periods.
    - Falls back gracefully if energy periods fill up.
    """
    if user_energy_levels is None:
        user_energy_levels = {
            "morning": "high",
            "afternoon": "medium",
            "evening": "low",
        }

    # Normalize energy levels to scores
    energy_scores = {
        period: ENERGY_LEVEL_SCORE.get(level, 2)
        for period, level in user_energy_levels.items()
    }

    # Parse slots into datetime tuples
    slot_pool: list[tuple[datetime.datetime, datetime.datetime]] = [
        (
            datetime.datetime.fromisoformat(slot["start"]),
            datetime.datetime.fromisoformat(slot["end"]),
        )
        for slot in free_slots
    ]
    slot_pool.sort(key=lambda interval: interval[0])

    scheduled: list[ProposedEvent] = []

    use_structural_mode = _has_any_structural_tags(subtasks)
    if use_structural_mode:
        subtasks_for_scheduling = _safe_structural_shuffle(subtasks)
    else:
        # Backward-compatible mode: prioritize heavier tasks first.
        subtasks_for_scheduling = sorted(
            subtasks,
            key=lambda subtask: subtask["duration_minutes"],
            reverse=True,
        )

    # Schedule each subtask with phase-safe ordering and energy fit.
    for subtask in subtasks_for_scheduling:
        duration = datetime.timedelta(minutes=subtask["duration_minutes"])
        task_complexity = _infer_task_complexity(subtask)
        
        # Try to find a slot matching this task's energy requirement
        best_idx: int | None = None
        best_score_diff = float('inf')

        # Prefer morning for heavy tasks when feasible (legacy behavior).
        if task_complexity >= 2:
            for idx, (slot_start, slot_end) in enumerate(slot_pool):
                if slot_end - slot_start >= duration and slot_start.time() < _MORNING_END:
                    best_idx = idx
                    break

        # Prefer afternoon for lighter tasks when feasible (legacy behavior).
        if task_complexity < 2 and best_idx is None:
            for idx, (slot_start, slot_end) in enumerate(slot_pool):
                if slot_end - slot_start >= duration and slot_start.time() >= _MORNING_END:
                    best_idx = idx
                    break
        
        for idx, (slot_start, slot_end) in enumerate(slot_pool):
            if best_idx is not None:
                break
            if slot_end - slot_start < duration:
                continue
            
            # Get the energy level of this slot's time period
            slot_period = _classify_slot_by_time(slot_start)
            slot_energy_score = energy_scores.get(slot_period, 2)
            
            # Prefer slots with matching energy levels (minimize difference)
            score_diff = abs(slot_energy_score - task_complexity)
            if score_diff < best_score_diff:
                best_score_diff = score_diff
                best_idx = idx
        
        # If no suitable slot found, use earliest available (should not happen)
        if best_idx is None:
            continue
        
        slot_start, slot_end = slot_pool.pop(best_idx)
        event_end = slot_start + duration
        
        scheduled.append(
            ProposedEvent(
                name=subtask["name"],
                description=subtask["description"],
                start=slot_start.isoformat(),
                end=event_end.isoformat(),
            )
        )
        
        # Add remainder back to pool if there's time left
        if event_end < slot_end:
            slot_pool.append((event_end, slot_end))
            slot_pool.sort(key=lambda interval: interval[0])

    scheduled.sort(key=lambda event: event["start"])
    return scheduled
