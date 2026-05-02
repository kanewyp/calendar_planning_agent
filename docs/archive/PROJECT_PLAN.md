# Project Plan: Calendar Planning Agent

> Archived historical plan. For current status, use `docs/STATUS.md`.

**Date:** 2026-04-17
**Team:** 2 developers
**Status:** Original implementation plan, now partially historical. The current integration branch has implemented the core application flow for mock-mode development.

---

## Current State

As of the current integration branch:
- Core source modules are implemented: settings, state types, LLM client, Google Calendar auth/events wrappers, free-slot computation, mock calendar, validator, three scheduling heuristics, graph nodes, graph wiring helpers, frontend components, approval controls, and `src/app.py`.
- The local suite reports `46 passed` with `.venv/bin/pytest -q`.
- Some tests still contain no-op `pass # TODO` bodies, especially `tests/test_validator.py`, `tests/test_calendar_api.py`, and `tests/test_orchestration.py::TestValidateCandidates`; the green suite should not be treated as complete coverage yet.
- End-to-end `CALENDAR_MODE=mock` Streamlit walkthrough and live Google Calendar verification are still pending.
- `requirements.txt` and `pyproject.toml` currently disagree on LangGraph/LangChain version ranges and should be reconciled.

This document still records the intended two-person implementation order. For current owner-specific status, see `docs/archive/WILL_STATUS.md` and `docs/archive/KANE_STATUS.md`.

---

## Team Split

| Area | Will (Person A) | Partner (Person B) |
|------|-----------------|-------------------|
| **Core focus** | LangGraph orchestration, LLM client, Google Calendar API | Pure-logic functions, heuristics, validator, frontend |
| **Phase 1** | LLM client, Google Calendar auth/events | Validator, free slots, mock calendar, 3 heuristics |
| **Phase 2** | All 8 orchestration graph nodes | Frontend intake form, schedule display |
| **Phase 3** | `graph.py` wiring, `human_approval`, `write_events` | `approval_controls.py`, `app.py` (Streamlit controller) |
| **Phase 4** | Integration tests, end-to-end testing | Unit tests for pure logic |

---

## Phase 1: Pure Logic & Infrastructure (Parallel, No Dependencies)

**Goal:** Build the foundational functions that the graph nodes will call. Both developers work independently.

**Current status:** Implemented on the integration branch. Remaining work is mostly stronger tests and live-mode verification.

### Will (Person A) -- LLM Client & Calendar API

| # | File | Functions | Notes |
|---|------|-----------|-------|
| 1 | `src/llm_client/client.py` | `_build_client()`, `_call_anthropic()`, `call_llm_json()`, `call_llm_text()` | Retry logic (up to 2), JSON parse, uses `claude-sonnet-4-20250514` |
| 2 | `src/calendar_api/auth.py` | `get_credentials()`, `build_calendar_service()` | Google OAuth 2.0, token caching at `token.json` |
| 3 | `src/calendar_api/events.py` | `fetch_busy_blocks()`, `create_event()`, `create_events_batch()` | ADD-ONLY -- never update/delete. Prefix descriptions with `[CALENDAR_AGENT]` |
| 4 | `tests/test_llm_client.py` | LLM client tests | Mock `_call_anthropic`, never hit real API |

### Partner (Person B) -- Validator, Free Slots, Heuristics

| # | File | Functions | Notes |
|---|------|-----------|-------|
| 1 | `src/validator/constraints.py` | `intervals_overlap()`, `validate_schedule()` | 4 hard constraints: overlap, self-overlap, working hours, deadline |
| 2 | `src/calendar_api/free_slots.py` | `compute_free_slots()`, `_day_working_window()` | Pure logic, no API calls |
| 3 | `src/calendar_api/mock_calendar.py` | `fetch_mock_busy_blocks()`, `create_mock_event()` | Hardcoded MOCK_EVENTS data already exists |
| 4 | `src/orchestration/heuristics/deadline_first.py` | `schedule_deadline_first()` | Greedy earliest-slot assignment |
| 5 | `src/orchestration/heuristics/minimize_fragmentation.py` | `schedule_min_fragmentation()` | Largest-slot-first |
| 6 | `src/orchestration/heuristics/energy_aware.py` | `schedule_energy_aware()` | Heavy tasks morning, light tasks afternoon |
| 7 | `tests/test_validator.py` | Validator tests | Still contains no-op stubs; needs completion |
| 8 | `tests/test_calendar_api.py` | Calendar/free-slot tests | Still contains no-op stubs; needs completion |
| 9 | `tests/test_orchestration.py` | Heuristic tests only | `TestDeadlineFirstHeuristic`, `TestMinFragmentationHeuristic`, `TestEnergyAwareHeuristic` |

### Integration Point

Function signatures are now implemented and used by graph nodes:
- Heuristics: `schedule_*(subtasks, free_slots, ...) -> list[ProposedEvent]`
- Validator: `validate_schedule(schedule, busy_blocks, work_start, work_end, deadline) -> ValidationResult`
- Free slots: `compute_free_slots(busy_blocks, time_min, time_max, work_start, work_end) -> list[dict]`

---

## Phase 2: LLM Nodes & Validation Nodes (Mostly Will)

**Goal:** Implement all graph nodes that Will owns. Partner starts frontend.

**Current status:** Implemented on the integration branch. Node coverage still needs completion for `validate_candidates_node`.

### Will (Person A) -- Graph Nodes

| # | File | Node Function | Reads from State | Writes to State |
|---|------|---------------|------------------|-----------------|
| 1 | `nodes/decompose_goal.py` | `decompose_goal_node` | goal, deadline, context, max_session_minutes | subtasks |
| 2 | `nodes/fetch_events.py` | `fetch_events_node` | deadline, work_start, work_end | busy_blocks, free_slots |
| 3 | `nodes/schedule_candidates.py` | `deadline_first_node`, `min_fragmentation_node`, `energy_aware_node` | subtasks, free_slots, work_start, work_end, max_session_minutes | candidate_deadline_first, candidate_min_fragmentation, candidate_energy_aware |
| 4 | `nodes/validate_candidates.py` | `validate_candidates_node` | all 3 candidates, busy_blocks, work_start, work_end, deadline | candidate_validations |
| 5 | `nodes/generate_rationales.py` | `generate_rationales_node` | subtasks, goal, context, all 3 candidates, candidate_validations | candidate_rationales |
| 6 | `nodes/build_proposal.py` | `build_proposal_node` | all 3 candidates | candidates_identical |

### Partner (Person B) -- Frontend Start

| # | File | Functions |
|---|------|-----------|
| 1 | `src/frontend/intake_form.py` | `render_intake_form()` -- 5-field Streamlit form returning `UserInputs` |
| 2 | `src/frontend/schedule_display.py` | `render_all_candidates()`, `render_single_schedule()`, `render_collapsed_view()`, `render_violation_badge()` |

---

## Phase 3: Graph Wiring & App Integration (Collaborative)

**Goal:** Wire the full LangGraph, connect frontend to graph, end-to-end flow.

**Current status:** Implemented on the integration branch for mock-mode development. The approval/resume contract currently works by having `app.py` set `graph_state["selected_strategy"]` before calling `resume_graph(graph, graph_state, approved=True)`. This should be documented as canonical or refactored to pass `selected_strategy` explicitly.

### Will (Person A) -- Graph Orchestration

| # | File | Functions | Notes |
|---|------|-----------|-------|
| 1 | `src/orchestration/graph.py` | `build_graph()` | Wire all nodes + edges, parallel fan-out for 3 heuristics, `interrupt_before=["human_approval"]` |
| 2 | `src/orchestration/graph.py` | `_approval_decision()` | Conditional edge: approved -> write_events, rejected -> END |
| 3 | `src/orchestration/graph.py` | `run_graph_until_approval()` | Execute graph to pause point, return paused AgentState |
| 4 | `src/orchestration/graph.py` | `resume_graph()` | Resume from user decision |
| 5 | `nodes/human_approval.py` | `human_approval_node` | Populate `final_schedule` from chosen strategy |
| 6 | `nodes/write_events.py` | `write_events_node` | Branch on CALENDAR_MODE, write events |

### Partner (Person B) -- Frontend & App Controller

| # | File | Functions | Notes |
|---|------|-----------|-------|
| 1 | `src/frontend/approval_controls.py` | `render_strategy_buttons()` | Per-strategy "Pick this plan" + "Reject all" |
| 2 | `src/app.py` | `_init_session_state()`, `main()` | Streamlit session state, phase branching, calls `run_graph_until_approval()` and `resume_graph()` |
| 3 | `tests/test_frontend.py` | All tests | |

### Integration Point

`app.py` calls Will's graph functions. Contract:
- `run_graph_until_approval(graph, user_inputs)` returns `AgentState` with all 3 candidates, rationales, validations, and `candidates_identical`
- `resume_graph(graph, paused_state, approved)` returns final `AgentState` with `write_results` if approved. Before approving, the frontend currently sets `paused_state["selected_strategy"]`.

---

## Phase 4: End-to-End Testing & Polish (Together)

**Current status:** Pending. This is now the main active phase.

1. Run full flow in `CALENDAR_MODE=mock` -- form submission through approval
2. Test with `CALENDAR_MODE=live` if Google creds are available
3. Edge cases: empty free slots, 0 subtasks, all strategies violate constraints, near-identical candidates
4. Replace no-op test stubs in validator/calendar API/validation-node tests
5. Reconcile dependency metadata between `requirements.txt` and `pyproject.toml`
6. CI green on Python 3.11 and 3.12
7. Docker compose test (`docker compose up --build`)

---

## Key Constraints to Remember

- **Add-only calendar writes** -- never `events().update()` or `events().delete()`
- **Never commit secrets** -- `.env`, `token.json`, `credentials.json` are in `.gitignore`
- **Heuristics are pure functions** -- no LLM or API calls
- **Validator is pure Python** -- no LLM involvement, deterministic
- **LLM uses `claude-sonnet-4-20250514`** with up to 2 retries
- **Mock mode** (`CALENDAR_MODE=mock`) enables full dev without Google creds
- **No repair loop** -- violations are surfaced per-candidate for user judgment
