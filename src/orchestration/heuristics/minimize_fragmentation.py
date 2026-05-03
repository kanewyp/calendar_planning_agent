# =============================================================================
# src/orchestration/heuristics/minimize_fragmentation.py — Minimise fragmentation
# =============================================================================
# Places subtasks in the LARGEST available time blocks first to avoid
# scattering short sessions across the calendar.
#
# This is a pure function with no LLM or API calls — fully unit-testable.
# =============================================================================

from __future__ import annotations

import datetime
import re

from src.orchestration.state import Subtask, ProposedEvent


_TAG_PATTERN = re.compile(r"\[(?P<key>[a-z_]+)\s*:\s*(?P<value>[^\]]+)\]", re.IGNORECASE)


def _tag_map(subtask: Subtask) -> dict[str, str]:
    text = f"{subtask['name']} {subtask['description']}"
    return {
        match.group("key").strip().lower(): match.group("value").strip().lower()
        for match in _TAG_PATTERN.finditer(text)
    }


def _group_id(subtask: Subtask) -> str:
    tags = _tag_map(subtask)
    return tags.get("group", "default")


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

            run_sorted = sorted(run, key=lambda s: int(s["duration_minutes"]), reverse=True)
            result.extend(run_sorted)
            i = j

    return result


def schedule_min_fragmentation(
    subtasks: list[Subtask],
    free_slots: list[dict[str, str]],
) -> list[ProposedEvent]:
    """Schedule subtasks in large slots with phase-safe local reordering.

    Args:
        subtasks: Ordered list of subtasks from goal decomposition.
        free_slots: Chronologically sorted list of
                    {"start": <ISO>, "end": <ISO>} free-slot dicts.

    Returns:
        List of ProposedEvent dicts.

     ALGORITHM:
     1. Infer each subtask's coarse phase (setup/learn/implement/project/other).
     2. Preserve phase order based on first appearance in the original list.
     3. Within each phase only, allow local reorder (longer first) to reduce
         slot fragmentation while keeping phase-level dependency flow.
     4. Place each chosen subtask in the largest available slot that fits.
     5. Split remainder slots back into the pool and continue.
     6. Return events sorted chronologically.

    RATIONALE:
    This keeps the learning flow intact at the phase level, while still
    reducing fragmentation through limited within-phase optimization.

    EDGE CASES:
    - Same as deadline_first: handle unplaceable subtasks gracefully.
    """
    slot_pool: list[tuple[datetime.datetime, datetime.datetime]] = [
        (
            datetime.datetime.fromisoformat(slot["start"]),
            datetime.datetime.fromisoformat(slot["end"]),
        )
        for slot in free_slots
    ]

    scheduled: list[ProposedEvent] = []

    use_structural_mode = _has_any_structural_tags(subtasks)

    if use_structural_mode:
        subtasks_for_scheduling = _safe_structural_shuffle(subtasks)
    else:
        # Backward-compatible mode: original behavior when no explicit phase cues exist.
        subtasks_for_scheduling = sorted(
            subtasks,
            key=lambda subtask: subtask["duration_minutes"],
            reverse=True,
        )

    for subtask in subtasks_for_scheduling:
        duration = datetime.timedelta(minutes=subtask["duration_minutes"])
        chosen_idx: int | None = None
        max_slot_size: datetime.timedelta | None = None

        # Find the LARGEST slot that can fit this subtask
        for idx, (slot_start, slot_end) in enumerate(slot_pool):
            slot_duration = slot_end - slot_start
            if slot_duration >= duration:
                if max_slot_size is None or slot_duration > max_slot_size:
                    chosen_idx = idx
                    max_slot_size = slot_duration

        if chosen_idx is None:
            continue

        slot_start, slot_end = slot_pool.pop(chosen_idx)
        event_end = slot_start + duration

        scheduled.append(
            ProposedEvent(
                name=subtask["name"],
                description=subtask["description"],
                start=slot_start.isoformat(),
                end=event_end.isoformat(),
            )
        )

        if event_end < slot_end:
            slot_pool.append((event_end, slot_end))

    scheduled.sort(key=lambda event: event["start"])
    return scheduled
