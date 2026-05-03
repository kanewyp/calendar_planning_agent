# =============================================================================
# src/orchestration/state.py — LangGraph state definition
# =============================================================================
# Defines the TypedDict that flows through every node of the graph.  Every
# field is documented so implementers know exactly what each node reads and
# writes.
#
# STEPS TO COMPLETE:
# 1. Review the fields below.  Add or adjust types as needed when you
#    implement individual nodes.
# =============================================================================

from __future__ import annotations

import datetime
import operator
from typing import Annotated, Any, TypedDict


class Subtask(TypedDict):
    """A single subtask produced by goal decomposition."""
    name: str                   # Short title, e.g. "Set up React dev environment"
    description: str            # 1–2 sentence description of the work
    duration_minutes: int       # Estimated duration in minutes


class ProposedEvent(TypedDict):
    """A scheduled calendar event proposed by a heuristic."""
    name: str                   # Subtask name
    description: str            # Subtask description
    start: str                  # ISO 8601 datetime string
    end: str                    # ISO 8601 datetime string


class Violation(TypedDict):
    """A single constraint violation found by the validator."""
    event_name: str             # Which event is in violation
    violation_type: str         # "OVERLAP" | "SELF_OVERLAP" | "OUT_OF_HOURS" | "DEADLINE_EXCEEDED"
    description: str            # Human-readable description


class ValidationResult(TypedDict):
    """Output of the deterministic validator."""
    passed: bool
    violations: list[Violation]


class DebugTraceEvent(TypedDict, total=False):
    """A compact observability event produced by a graph node."""
    node: str
    status: str
    created_at: str
    duration_ms: int
    summary: dict[str, Any]
    details: dict[str, Any]


class AgentState(TypedDict, total=False):
    """Full state carried through the LangGraph directed graph.

    Fields are populated progressively by different nodes.
    'total=False' means fields are optional — nodes only set what they own.
    """

    # --- User inputs (set once at the start) ---
    goal: str
    deadline: str                               # ISO date string
    context: str
    work_start: str                             # "HH:MM"
    work_end: str                               # "HH:MM"
    max_session_minutes: int

    # --- Calendar data (set by fetch_events node) ---
    busy_blocks: list[dict[str, str]]           # [{"start": ..., "end": ...}]
    free_slots: list[dict[str, str]]            # [{"start": ..., "end": ...}]

    # --- Goal decomposition (set by decompose_goal node) ---
    subtasks: list[Subtask]

    # --- Candidate schedules (set by the three heuristic branches) ---
    candidate_deadline_first: list[ProposedEvent]
    candidate_min_fragmentation: list[ProposedEvent]
    candidate_energy_aware: list[ProposedEvent]

    # --- Validation per candidate (set by validate_candidates node) ---
    # Maps strategy name → ValidationResult for each candidate
    candidate_validations: dict[str, ValidationResult]

    # --- Rationales per candidate (set by generate_rationales node) ---
    # Maps strategy name → short explanation of the tradeoff
    candidate_rationales: dict[str, str]

    # --- Near-duplicate detection (set by build_proposal node) ---
    # True if all three candidates produce effectively the same schedule
    candidates_identical: bool

    # --- User choice (set by frontend after user picks a strategy) ---
    # One of: "deadline_first" | "min_fragmentation" | "energy_aware" | None
    selected_strategy: str | None

    # --- Final output (set after user selects a strategy) ---
    final_schedule: list[ProposedEvent]

    # --- Human approval (set by approval node / frontend) ---
    # None = awaiting choice, True = picked a strategy, False = rejected all
    user_approved: bool | None

    # --- Write result ---
    write_results: list[dict[str, Any]]         # API responses from event creation

    # --- Debug trace ---
    # One compact trace event per node. The reducer lets parallel branches append.
    debug_trace: Annotated[list[DebugTraceEvent], operator.add]
