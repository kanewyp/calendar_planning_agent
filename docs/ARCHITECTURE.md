# Architecture

This is the stable system-design reference for the Calendar Planning Agent. For changing implementation status, use `docs/STATUS.md`.

## Purpose

The app takes a natural-language goal, decomposes it into subtasks with Claude, finds free time on the user's calendar, builds three candidate schedules, validates them, shows all candidates to the user, and writes only the approved candidate.

## Module Map

```text
config/
  settings.py

src/
  app.py
  frontend/
    intake_form.py
    schedule_display.py
    approval_controls.py
  calendar_api/
    auth.py
    events.py
    free_slots.py
    mock_calendar.py
  llm_client/
    client.py
  orchestration/
    state.py
    graph.py
    nodes/
    heuristics/
  validator/
    constraints.py
```

## Graph Flow

```text
decompose_goal
  -> fetch_events
  -> deadline_first
  -> min_fragmentation
  -> energy_aware
  -> validate_candidates
  -> generate_rationales
  -> build_proposal
  -> human_approval
  -> write_events or END
```

The three heuristic branches write separate candidate keys, then `validate_candidates` validates all three. The app presents all candidates; there is no automatic winner and no repair loop.

## State Contract

The graph state is defined in `src/orchestration/state.py`.

Core user-input fields:

- `goal: str`
- `deadline: str`
- `context: str`
- `work_start: str`
- `work_end: str`
- `max_session_minutes: int`

Calendar and decomposition fields:

- `busy_blocks: list[dict[str, str]]`
- `free_slots: list[dict[str, str]]`
- `subtasks: list[Subtask]`

Candidate fields:

- `candidate_deadline_first: list[ProposedEvent]`
- `candidate_min_fragmentation: list[ProposedEvent]`
- `candidate_energy_aware: list[ProposedEvent]`
- `candidate_validations: dict[str, ValidationResult]`
- `candidate_rationales: dict[str, str]`
- `candidates_identical: bool`

Approval/write fields:

- `selected_strategy: str | None`
- `user_approved: bool | None`
- `final_schedule: list[ProposedEvent]`
- `write_results: list[dict[str, Any]]`

## Key Types

```python
class Subtask(TypedDict):
    name: str
    description: str
    duration_minutes: int

class ProposedEvent(TypedDict):
    name: str
    description: str
    start: str
    end: str

class Violation(TypedDict):
    event_name: str
    violation_type: str
    description: str

class ValidationResult(TypedDict):
    passed: bool
    violations: list[Violation]
```

Datetime values inside dicts are ISO 8601 strings. Working hours are `"HH:MM"` strings in graph state and `datetime.time` values inside pure functions.

## Approval Contract

Current behavior:

1. `run_graph_until_approval(graph, user_inputs)` builds initial state and runs until `human_approval`.
2. The paused state contains all candidates, validations, rationales, and `candidates_identical`.
3. In approve flow, `src/app.py` sets `graph_state["selected_strategy"] = strategy_name`.
4. `resume_graph(graph, graph_state, approved=True)` validates the selected strategy, sets `final_schedule`, and calls `write_events_node`.
5. Reject flow calls `resume_graph(graph, graph_state, approved=False)` and exits with no writes.

Open design option: refactor `resume_graph` to accept `selected_strategy` explicitly instead of relying on app-owned state mutation.

## Scheduling Strategies

- `deadline_first`: greedy earliest-slot assignment.
- `min_fragmentation`: largest-slot / longest-task strategy.
- `energy_aware`: places heavier tasks earlier when possible.

All heuristics must remain pure: no LLM calls, no API calls, no Streamlit calls, and no persistence.

## Validation Rules

`src/validator/constraints.py` checks:

- `OVERLAP`: candidate event overlaps an existing busy block.
- `SELF_OVERLAP`: candidate events overlap each other.
- `OUT_OF_HOURS`: event falls outside configured working hours.
- `DEADLINE_EXCEEDED`: event ends after the deadline.

Validator logic must remain deterministic and pure.

## Calendar Rules

- `CALENDAR_MODE=mock` uses `src/calendar_api/mock_calendar.py`.
- `CALENDAR_MODE=live` uses Google Calendar wrappers.
- Writes are add-only. Never call Google Calendar `events().update()` or `events().delete()`.
- Agent-created live events should include the `[CALENDAR_AGENT]` tag in descriptions.

## LLM Rules

- All LLM calls go through `src/llm_client/client.py`.
- Current model: `claude-sonnet-4-20250514`.
- Tests must mock `_call_anthropic`; never make real LLM calls in tests.

## Frontend Flow

`src/app.py` manages phases:

```text
intake -> running -> review -> done
```

- `intake`: collect user inputs.
- `running`: build graph and run to approval.
- `review`: render candidates and approval/reject controls.
- `done`: show final result and allow restart.
