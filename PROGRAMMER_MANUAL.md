# Calendar Planning Agent — Programmer Manual

> **Audience:** Any developer picking up the current integration branch.
> **Goal:** After reading this document you should understand the current architecture, implemented behavior, remaining verification gaps, and the exact signatures and data shapes every function must respect.

For faster AI/context usage, prefer `docs/ARCHITECTURE.md` and `docs/DEVELOPER_GUIDE.md`. This manual is the long-form detailed reference.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture & Module Map](#2-architecture--module-map)
3. [Data Flow Through the System](#3-data-flow-through-the-system)
4. [Shared Data Types (the Contract)](#4-shared-data-types-the-contract)
5. [Environment Setup](#5-environment-setup)
6. [Implementation Status & Dependency Graph](#6-implementation-status--dependency-graph)
7. [Phase 1 — Pure-Logic Foundation Reference](#7-phase-1--pure-logic-foundation-reference)
8. [Phase 2 — LLM Integration & Scheduling Heuristics Reference](#8-phase-2--llm-integration--scheduling-heuristics-reference)
9. [Phase 3 — Graph Wiring & Frontend Reference](#9-phase-3--graph-wiring--frontend-reference)
10. [File-by-File Implementation Reference](#10-file-by-file-implementation-reference)
11. [Testing Strategy](#11-testing-strategy)
12. [Common Pitfalls & Tips](#12-common-pitfalls--tips)

---

## 1. Project Overview

The application is a **Calendar Augmentation Agent** that:

1. Takes a user's natural-language **goal** (e.g. "Learn the basics of React by next Friday").
2. Calls an **LLM** to decompose the goal into concrete **subtasks** with time estimates.
3. Reads the user's **Google Calendar** to find busy blocks and compute **free slots**.
4. Runs **three heuristic schedulers in parallel**, each producing a candidate schedule.
5. **Validates** each candidate against four hard constraints (overlaps, working hours, deadline, self-overlap).
6. Generates a **rationale** for each strategy explaining tradeoffs.
7. Presents **all three options** to the user for **approval** via a Streamlit UI.
8. The user **picks a strategy** or rejects all.
9. On approval, **writes events** to Google Calendar (add-only, never update/delete).

### Current Status Snapshot

The current integration branch has implemented the core source modules for mock-mode development: settings, state types, LLM client, Google Calendar auth/events wrappers, free-slot computation, mock calendar, validator, three scheduling heuristics, graph nodes, graph wiring helpers, frontend components, approval controls, and `src/app.py`.

Known remaining work:
- `.venv/bin/pytest -q` currently reports `46 passed`, but several tests are still no-op `pass # TODO` stubs, especially validator/calendar API tests and `TestValidateCandidates`.
- A full `CALENDAR_MODE=mock` Streamlit walkthrough still needs to be run and recorded.
- Live Google Calendar behavior still needs real OAuth credential verification.
- `requirements.txt` and `pyproject.toml` currently disagree on LangGraph/LangChain version ranges and should be reconciled.

---

## 2. Architecture & Module Map

```
calendar_planning_agent/
│
├── config/
│   └── settings.py              ← Reads .env, provides a Settings singleton
│
├── src/
│   ├── app.py                   ← Streamlit entry point; session-state controller
│   │
│   ├── frontend/                ← MODULE 1: Streamlit UI components
│   │   ├── intake_form.py       ←   5-field form → UserInputs dict
│   │   ├── schedule_display.py  ←   Render events table + LLM rationale
│   │   └── approval_controls.py ←   Approve / Reject buttons
│   │
│   ├── calendar_api/            ← MODULE 2: Google Calendar I/O
│   │   ├── auth.py              ←   OAuth 2.0 flow + token caching
│   │   ├── events.py            ←   Fetch busy blocks + create events
│   │   ├── free_slots.py        ←   Compute free gaps (pure logic)
│   │   └── mock_calendar.py     ←   Hardcoded test data (no API needed)
│   │
│   ├── orchestration/           ← MODULE 3: LangGraph directed graph
│   │   ├── state.py             ←   AgentState TypedDict + sub-types
│   │   ├── graph.py             ←   Build / run / resume the graph
│   │   ├── nodes/               ←   One file per graph node
│   │   │   ├── decompose_goal.py
│   │   │   ├── fetch_events.py
│   │   │   ├── schedule_candidates.py
│   │   │   ├── validate_candidates.py
│   │   │   ├── generate_rationales.py
│   │   │   ├── build_proposal.py
│   │   │   ├── human_approval.py
│   │   │   └── write_events.py
│   │   └── heuristics/          ←   Three scheduling strategies
│   │       ├── deadline_first.py
│   │       ├── minimize_fragmentation.py
│   │       └── energy_aware.py
│   │
│   ├── validator/               ← MODULE 4: Deterministic constraint checker
│   │   └── constraints.py       ←   4 hard-constraint checks, no LLM
│   │
│   └── llm_client/              ← MODULE 5: Anthropic Claude wrapper
│       └── client.py            ←   call_llm_json / call_llm_text + retries
│
├── tests/
│   ├── conftest.py              ← Shared pytest fixtures
│   ├── test_validator.py
│   ├── test_calendar_api.py
│   ├── test_orchestration.py
│   ├── test_llm_client.py
│   └── test_frontend.py
│
└── infrastructure/              ← AWS deployment placeholders
```

### Module Dependency Diagram

```
                  ┌────────────┐
                  │  settings  │  (config/settings.py)
                  └─────┬──────┘
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   ┌─────────┐   ┌────────────┐   ┌──────────┐
   │validator │   │calendar_api│   │llm_client│
   │(no deps)│   │            │   │          │
   └────┬────┘   └─────┬──────┘   └─────┬────┘
        │               │               │
        └───────────────┼───────────────┘
                        ▼
               ┌─────────────────┐
               │  orchestration   │  (nodes + heuristics + graph.py)
               └────────┬────────┘
                        ▼
               ┌─────────────────┐
               │    frontend      │  (app.py + UI components)
               └─────────────────┘
```

**Key insight:** The arrow direction tells you what to build first. Modules at the TOP have zero in-project dependencies. Modules at the BOTTOM depend on everything above them. **Always build bottom-up.**

---

## 3. Data Flow Through the System

This is the end-to-end data flow, showing which function produces what and which function consumes it.

```
User fills Streamlit form
        │
        ▼
  UserInputs dict ──────────────────────────────────────┐
  {goal, deadline, context, work_start, work_end,       │
   max_session_minutes}                                 │
        │                                               │
        ▼                                               │
  ┌─────────────────┐                                   │
  │ decompose_goal  │  calls LLM via call_llm_json()    │
  │   node          │                                   │
  └────────┬────────┘                                   │
           │ produces: list[Subtask]                     │
           ▼                                            │
  ┌─────────────────┐                                   │
  │  fetch_events   │  calls mock/live calendar API     │
  │    node         │  then calls compute_free_slots()  │
  └────────┬────────┘                                   │
           │ produces: busy_blocks, free_slots           │
           │                                            │
     ┌─────┼─────────────────────┐                      │
     ▼     ▼                     ▼                      │
  deadline  min_frag          energy                    │
   _first   _mentation        _aware                   │
     │         │                 │                      │
     │  each produces: list[ProposedEvent]              │
     ▼         ▼                 ▼                      │
  ┌──────────────────────────────────┐                  │
  │    validate_candidates           │  uses validator  │
  │  validates all 3 candidates      │  (no selection)  │
  └────────────┬─────────────────────┘                  │
               │ produces: candidate_validations        │
               ▼                                        │
  ┌───────────────────┐                                 │
  │generate_rationales│  calls LLM via call_llm_text()  │
  └────────┬──────────┘  (one rationale per strategy)   │
           │ produces: candidate_rationales              │
           ▼                                            │
  ┌──────────────────┐                                  │
  │ build_proposal   │  detects near-duplicates,        │
  └────────┬─────────┘  packages for frontend           │
           │                                            │
           ▼                                            │
  ┌──────────────────┐                                  │
  │ human_approval   │  ← GRAPH PAUSES HERE             │
  └────────┬─────────┘    user sees schedule in UI      │
           │                                            │
      ┌────┴────┐                                       │
   approve   reject                                     │
      │         │                                       │
      ▼         ▼                                       │
  write_events  END (no changes)                        │
```

---

## 4. Shared Data Types (the Contract)

Every module communicates through the types defined in `src/orchestration/state.py`. **Read this file first.** Here are the critical shapes:

### Subtask
```python
class Subtask(TypedDict):
    name: str                   # "Set up React dev environment"
    description: str            # "Install Node.js, create React app"
    duration_minutes: int       # 30
```

### ProposedEvent
```python
class ProposedEvent(TypedDict):
    name: str                   # Subtask name
    description: str            # Subtask description
    start: str                  # "2026-04-06T10:00:00+00:00" (ISO 8601)
    end: str                    # "2026-04-06T10:30:00+00:00"
```

### Busy Block (plain dict)
```python
{"start": "2026-04-06T09:30:00+00:00", "end": "2026-04-06T10:00:00+00:00"}
```

### Free Slot (same shape as Busy Block)
```python
{"start": "2026-04-06T10:00:00+00:00", "end": "2026-04-06T14:00:00+00:00"}
```

### Violation
```python
class Violation(TypedDict):
    event_name: str             # "Build counter component"
    violation_type: str         # "OVERLAP" | "SELF_OVERLAP" | "OUT_OF_HOURS" | "DEADLINE_EXCEEDED"
    description: str            # Human-readable message
```

### ValidationResult
```python
class ValidationResult(TypedDict):
    passed: bool                # True if violations list is empty
    violations: list[Violation]
```

### AgentState (full graph state)
The `AgentState` TypedDict (in `state.py`) carries ALL data through the graph. Each node reads the fields it needs and returns a dict of the fields it writes. LangGraph merges the returned dict into the state automatically.

**Convention:** Every node function has signature `def node_name(state: AgentState) -> dict[str, Any]`. It returns ONLY the keys it modifies.

### UserInputs (frontend)
```python
class UserInputs(TypedDict):
    goal: str
    deadline: datetime.date
    context: str
    work_start: datetime.time
    work_end: datetime.time
    max_session_minutes: int
```

### IMPORTANT: Datetime Conventions
- **All datetimes in dicts** are ISO 8601 strings with timezone: `"2026-04-06T10:00:00+00:00"`
- **Working hours** are stored as `"HH:MM"` strings in state and `datetime.time` in function args
- **Deadline** is stored as an ISO date string `"2026-04-17"` in state
- Use `datetime.datetime.fromisoformat()` to parse and `.isoformat()` to serialise
- Always work in UTC (or a single consistent timezone)

---

## 5. Environment Setup

```bash
# 1. Clone the repo and enter it
cd calendar_planning_agent

# 2. Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Copy the env template and fill in your Anthropic key
cp .env.example .env
# Edit .env → set ANTHROPIC_API_KEY=sk-ant-...
# Leave CALENDAR_MODE=mock for now

# 5. Verify pytest runs (green today, but some no-op test stubs remain)
pytest -v

# 6. Verify imports resolve
python -c "from config.settings import settings; print(settings.CALENDAR_MODE)"
```

---

## 6. Implementation Status & Dependency Graph

This section preserves the original implementation order because it is still useful for understanding dependencies. On the current integration branch, Steps 1 through 6 are implemented in source. The main active work is Step 7-style verification, replacing no-op tests, and polishing the graph/app approval contract.

```
STEP 1 ─── Zero-dependency pure logic (implemented; tests need completion)
  │
  ├── src/validator/constraints.py          ← intervals_overlap + validate_schedule
  ├── src/calendar_api/free_slots.py        ← compute_free_slots + _day_working_window
  └── src/calendar_api/mock_calendar.py     ← fetch_mock_busy_blocks + create_mock_event
  │
  │   Tests: pytest tests/test_validator.py tests/test_calendar_api.py
  │
STEP 2 ─── LLM client (implemented; tested with mocks)
  │
  └── src/llm_client/client.py              ← _build_client, _call_anthropic,
  │                                            call_llm_json, call_llm_text
  │
  │   Tests: pytest tests/test_llm_client.py (fully mocked, no real API calls)
  │
STEP 3 ─── Scheduling heuristics (implemented)
  │
  ├── src/orchestration/heuristics/deadline_first.py
  ├── src/orchestration/heuristics/minimize_fragmentation.py
  └── src/orchestration/heuristics/energy_aware.py
  │
  │   Tests: pytest tests/test_orchestration.py (heuristic classes)
  │
STEP 4 ─── Graph nodes (implemented; validation-node tests need completion)
  │
  ├── src/orchestration/nodes/decompose_goal.py     ← needs llm_client
  ├── src/orchestration/nodes/fetch_events.py       ← needs calendar_api
  ├── src/orchestration/nodes/schedule_candidates.py← needs heuristics
  ├── src/orchestration/nodes/validate_candidates.py← needs validator
  ├── src/orchestration/nodes/generate_rationales.py← needs llm_client
  ├── src/orchestration/nodes/build_proposal.py     ← pure logic (near-duplicate detection)
  ├── src/orchestration/nodes/human_approval.py     ← maps selected strategy to final_schedule
  └── src/orchestration/nodes/write_events.py       ← needs calendar_api
  │
STEP 5 ─── Graph assembly (implemented)
  │
  └── src/orchestration/graph.py            ← build_graph, run_graph_until_approval,
  │                                            resume_graph, conditional edges
  │
  │   Test: run the full graph with mock calendar + mock LLM to verify wiring
  │
STEP 6 ─── Frontend + app entry point (implemented)
  │
  ├── src/frontend/intake_form.py
  ├── src/frontend/schedule_display.py
  ├── src/frontend/approval_controls.py
  └── src/app.py
  │
  │   Test: CALENDAR_MODE=mock streamlit run src/app.py
  │
STEP 7 ─── Real Google Calendar (wrappers implemented; live verification pending)
  │
  ├── src/calendar_api/auth.py
  └── src/calendar_api/events.py
```

---

## 7. Phase 1 — Pure-Logic Foundation Reference

These notes describe the implementation shape that now exists on the integration branch. Treat them as maintenance/reference notes, not as open implementation tasks.

### 7.1 `src/validator/constraints.py`

**Why first:** The validator has zero in-project dependencies. It's pure Python with `datetime` math. Once working, it becomes the test oracle for every other module.

**Current behavior / implementation notes:**

#### `intervals_overlap(start_a, end_a, start_b, end_b) -> bool`
The simplest function in the project. Two half-open intervals `[A, B)` overlap iff `start_a < end_b and start_b < end_a`. One line of logic.

```python
def intervals_overlap(start_a, end_a, start_b, end_b) -> bool:
    return start_a < end_b and start_b < end_a
```

#### `validate_schedule(schedule, busy_blocks, work_start, work_end, deadline) -> ValidationResult`
Walk through four checks sequentially, accumulating violations into a list:

1. **OVERLAP** — For every `(event, busy_block)` pair, parse their ISO strings to `datetime`, call `intervals_overlap`. If True, append a `Violation` with type `"OVERLAP"`.

2. **SELF_OVERLAP** — For every unique pair `(event_i, event_j)` where `i < j`, check `intervals_overlap`. Type: `"SELF_OVERLAP"`.

3. **OUT_OF_HOURS** — For each event, extract `.time()` from parsed start and end. If `start_time < work_start` or `end_time > work_end`, it's a violation. Type: `"OUT_OF_HOURS"`.

4. **DEADLINE_EXCEEDED** — For each event, if `parsed_end > deadline`, type `"DEADLINE_EXCEEDED"`.

Return `{"passed": len(violations) == 0, "violations": violations}`.

**Gotcha:** All start/end values in the dicts are ISO strings. You must parse them with `datetime.datetime.fromisoformat()` inside this function (or create a small helper).

**Targeted test command:**
```bash
pytest tests/test_validator.py -v
```

---

### 7.2 `src/calendar_api/free_slots.py`

**Why this matters:** It's pure logic with zero API calls. It depends only on `datetime` and produces the `free_slots` list that all three heuristics consume.

**Current behavior / implementation notes:**

#### `_day_working_window(day, work_start, work_end, tz) -> (datetime, datetime)`
```python
start_dt = datetime.datetime.combine(day, work_start, tzinfo=tz)
end_dt   = datetime.datetime.combine(day, work_end,   tzinfo=tz)
return (start_dt, end_dt)
```

#### `compute_free_slots(busy_blocks, horizon_start, horizon_end, work_start, work_end, include_weekends) -> list[dict]`

This is the most involved pure-logic function. The algorithm:

1. **Generate working days:** From `horizon_start.date()` to `horizon_end.date()`. Skip weekdays 5 and 6 (Sat/Sun) unless `include_weekends=True`.

2. **For each day, compute the working window:**
   - `(day_start, day_end) = _day_working_window(day, work_start, work_end, tz)`
   - Clamp: `day_start = max(day_start, horizon_start)`, `day_end = min(day_end, horizon_end)`
   - If `day_start >= day_end`, skip this day (it's outside the horizon).

3. **Collect and merge busy blocks for this day:**
   - Filter: keep only busy blocks where `busy_end > day_start and busy_start < day_end`.
   - Clamp each busy block to the day window.
   - Sort by start time.
   - Merge overlapping/adjacent blocks: walk through sorted list, if `current.end >= next.start`, extend `current.end = max(current.end, next.end)`.

4. **Walk the day window to find gaps:**
   ```python
   cursor = day_start
   for busy in merged:
       if busy.start > cursor:
           free_slots.append({"start": cursor.isoformat(), "end": busy.start.isoformat()})
       cursor = max(cursor, busy.end)
   if cursor < day_end:
       free_slots.append({"start": cursor.isoformat(), "end": day_end.isoformat()})
   ```

5. Return the full list across all days.

**Gotcha:** Make sure to use a consistent timezone (default `datetime.timezone.utc`) for all `combine()` calls.

**Test immediately:**
```bash
pytest tests/test_calendar_api.py::TestComputeFreeSlots -v
```

---

### 7.3 `src/calendar_api/mock_calendar.py`

**Why this matters:** It enables app and graph development without Google OAuth credentials.

#### `fetch_mock_busy_blocks(time_min, time_max) -> list[dict]`
Iterate over the hardcoded `MOCK_EVENTS` list. Parse each event's start/end strings. Keep events where `start >= time_min and end <= time_max`. Return as `[{"start": ..., "end": ...}]`.

#### `create_mock_event(summary, description, start, end) -> dict`
Print a log line and return a fake response dict:
```python
import uuid
return {"id": str(uuid.uuid4()), "summary": summary, "status": "confirmed"}
```

**Test:**
```bash
pytest tests/test_calendar_api.py::TestMockCalendar -v
```

---

### Phase 1 Checkpoint

Current caveat:
- `pytest tests/test_validator.py` and `pytest tests/test_calendar_api.py` pass, but many tests in those files are no-op stubs. Replace those stubs before treating the green suite as meaningful coverage.
- The source implementations are present and used by graph/app code.

---

## 8. Phase 2 — LLM Integration & Scheduling Heuristics Reference

These modules are implemented on the current integration branch. The notes below document intended behavior and maintenance expectations.

### 8.1 `src/llm_client/client.py`

**Why this matters:** The decompose_goal and rationale nodes need this, and it is testable with mocks.

#### `_build_client() -> anthropic.Anthropic`
```python
if not settings.ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not set in environment")
return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
```

#### `_call_anthropic(prompt, temperature, max_tokens) -> str`
```python
client = _build_client()
response = client.messages.create(
    model=MODEL_ID,
    max_tokens=max_tokens,
    temperature=temperature,
    messages=[{"role": "user", "content": prompt}],
)
return response.content[0].text
```

#### `call_llm_json(prompt, temperature) -> Any`
Retry loop pattern:
```python
last_error = None
for attempt in range(MAX_RETRIES + 1):
    try:
        raw = _call_anthropic(prompt, temperature)
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        last_error = e
        # Optionally append "Return ONLY valid JSON" to prompt for retry
        continue
    except anthropic.APIError as e:
        last_error = e
        continue
raise ValueError(f"Failed to get valid JSON after {MAX_RETRIES + 1} attempts: {last_error}")
```

#### `call_llm_text(prompt, temperature) -> str`
Same retry loop but no JSON parsing — just return the raw text. Raise `RuntimeError` if all retries fail.

**Test with mocks (no real API call):**
```bash
pytest tests/test_llm_client.py -v
```

Use `unittest.mock.patch` on `_call_anthropic` to control its return value.

---

### 8.2 Three Scheduling Heuristics

All three have the same contract:
- **Input:** `subtasks: list[Subtask]`, `free_slots: list[dict]` (plus `work_start` for energy-aware)
- **Output:** `list[ProposedEvent]`

They are pure functions. No API calls. The core challenge is the **slot-splitting** logic, which is shared across all three. **Implement it once as a helper and reuse it.**

#### Shared Slot-Splitting Pattern

```python
def _place_subtask_in_slot(subtask, slot_start, slot_end):
    """Place a subtask at the start of a slot. Return (event, remaining_slot_or_None)."""
    duration = datetime.timedelta(minutes=subtask["duration_minutes"])
    event_end = slot_start + duration

    event = ProposedEvent(
        name=subtask["name"],
        description=subtask["description"],
        start=slot_start.isoformat(),
        end=event_end.isoformat(),
    )

    # If there's remaining time in the slot, return it
    remaining = None
    if event_end < slot_end:
        remaining = {"start": event_end.isoformat(), "end": slot_end.isoformat()}

    return event, remaining
```

The current heuristics each own their placement logic. If future changes create meaningful duplication, extract a shared helper carefully and keep behavior covered by tests.

#### 8.2.1 `deadline_first.py` — `schedule_deadline_first(subtasks, free_slots)`

**Strategy:** Greedy earliest-first.

1. Parse all free slots into `(start_dt, end_dt)` pairs. Keep them sorted chronologically (they already are).
2. Maintain a mutable list of available slots.
3. For each subtask **in order:**
   - Find the first slot where `(slot_end - slot_start) >= timedelta(minutes=duration_minutes)`.
   - Place the subtask at `slot_start`.
   - If there's remaining time, replace the consumed slot with the remainder.
   - If no slot fits, either skip the subtask (validator will flag it) or place it in the largest available slot.
4. Return the list of `ProposedEvent` dicts.

#### 8.2.2 `minimize_fragmentation.py` — `schedule_min_fragmentation(subtasks, free_slots)`

**Strategy:** Pair longest tasks with largest slots.

1. Parse free slots.
2. Sort slots by **duration descending** (largest first).
3. Sort subtasks by **duration_minutes descending** (longest first).
4. For each subtask (longest first):
   - Find the first slot large enough.
   - Place and split.
   - Re-sort remaining slots by duration descending.
5. **After all placements, re-sort the output list by start time** (chronological order).

#### 8.2.3 `energy_aware.py` — `schedule_energy_aware(subtasks, free_slots, work_start)`

**Strategy:** Heavy tasks in morning, light tasks in afternoon.

1. Parse free slots.
2. Split slots into `morning_slots` (start.time() < 12:00) and `afternoon_slots`.
3. Classify subtasks: `heavy` = duration_minutes >= 60, `light` = < 60.
4. Schedule heavy subtasks into morning_slots (earliest-first). If morning_slots exhausted, spill into afternoon.
5. Schedule light subtasks into afternoon_slots (earliest-first). If afternoon exhausted, spill into remaining morning.
6. Sort output chronologically.

**Test all three:**
```bash
pytest tests/test_orchestration.py -v -k "Heuristic"
```

---

### Phase 2 Checkpoint

Current status:
- All three heuristics produce `list[ProposedEvent]` from fixture-style free slots.
- `call_llm_json` and `call_llm_text` are implemented and covered by mocked tests.
- Remaining work is mostly edge-case test coverage, not first implementation.

---

## 9. Phase 3 — Graph Wiring & Frontend Reference

### 9.1 Graph Nodes (Step 4 in the build order)

Each node is a small function that reads from `state`, calls one of the modules above, and returns the keys it writes. These nodes are implemented on the current integration branch.

#### `nodes/decompose_goal.py`
```python
def decompose_goal_node(state):
    prompt = DECOMPOSITION_PROMPT.format(
        goal=state["goal"],
        deadline=state["deadline"],
        context=state.get("context", ""),
        max_session=state["max_session_minutes"],
    )
    subtasks = call_llm_json(prompt)
    # Validate: ensure it's a list of dicts with required keys
    return {"subtasks": subtasks}
```

#### `nodes/fetch_events.py`
```python
def fetch_events_node(state):
    # Parse deadline, compute time_min=now, time_max=deadline
    # Branch on settings.CALENDAR_MODE → mock or live
    busy_blocks = fetch_mock_busy_blocks(time_min, time_max)  # or live
    free_slots = compute_free_slots(busy_blocks, time_min, time_max, work_start, work_end)
    return {"busy_blocks": busy_blocks, "free_slots": free_slots}
```

#### `nodes/schedule_candidates.py`
Three thin wrappers that each call the corresponding heuristic and return one key:
```python
def deadline_first_node(state):
    result = schedule_deadline_first(state["subtasks"], state["free_slots"])
    return {"candidate_deadline_first": result}
```

#### `nodes/validate_candidates.py`
Validate all three candidates (no selection — user decides):
```python
def validate_candidates_node(state):
    strategies = {
        "deadline_first": state["candidate_deadline_first"],
        "min_fragmentation": state["candidate_min_fragmentation"],
        "energy_aware": state["candidate_energy_aware"],
    }
    validations = {}
    for name, candidate in strategies.items():
        validations[name] = validate_schedule(candidate, busy, work_s, work_e, deadline)
    return {"candidate_validations": validations}
```

#### `nodes/generate_rationales.py`
For each of the 3 strategies, format a prompt with subtask summary, schedule summary, and validation results. Call `call_llm_text` for each. Return `{"candidate_rationales": {"deadline_first": r1, "min_fragmentation": r2, "energy_aware": r3}}`.

#### `nodes/build_proposal.py`
Detects near-duplicate candidates (all three produce identical start/end times). Return `{"candidates_identical": True/False}`.

#### `nodes/human_approval.py`
Maps the user's selected strategy to `final_schedule`. If `user_approved` and `selected_strategy` are set, copies the chosen candidate to `final_schedule`. Otherwise returns empty dict.

#### `nodes/write_events.py`
Branch on `CALENDAR_MODE`. Call `create_mock_event` or `create_events_batch` for each event. Return `{"write_results": responses}`.

---

### 9.2 `src/orchestration/graph.py`

**This is where everything comes together.** These are the main graph helper functions:

#### `build_graph() -> StateGraph`

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(AgentState)

# Add all nodes
graph.add_node("decompose_goal", decompose_goal_node)
graph.add_node("fetch_events", fetch_events_node)
graph.add_node("deadline_first", deadline_first_node)
graph.add_node("min_fragmentation", min_fragmentation_node)
graph.add_node("energy_aware", energy_aware_node)
graph.add_node("validate_candidates", validate_candidates_node)
graph.add_node("generate_rationales", generate_rationales_node)
graph.add_node("build_proposal", build_proposal_node)
graph.add_node("human_approval", human_approval_node)
graph.add_node("write_events", write_events_node)

# Entry
graph.set_entry_point("decompose_goal")

# Edges
graph.add_edge("decompose_goal", "fetch_events")

# Fan-out to three heuristics (parallel)
graph.add_edge("fetch_events", "deadline_first")
graph.add_edge("fetch_events", "min_fragmentation")
graph.add_edge("fetch_events", "energy_aware")

# Fan-in: all 3 heuristics -> validate_candidates
graph.add_edge("deadline_first", "validate_candidates")
graph.add_edge("min_fragmentation", "validate_candidates")
graph.add_edge("energy_aware", "validate_candidates")

# Linear continuation
graph.add_edge("validate_candidates", "generate_rationales")
graph.add_edge("generate_rationales", "build_proposal")
graph.add_edge("build_proposal", "human_approval")

# Conditional: approve or reject?
graph.add_conditional_edges("human_approval", _approval_decision)

graph.add_edge("write_events", END)

return graph.compile(interrupt_before=["human_approval"])
```

**Note on fan-out/fan-in:** The three heuristic nodes write to separate state keys (`candidate_deadline_first`, `candidate_min_fragmentation`, `candidate_energy_aware`) so there's no reducer conflict. LangGraph supports this natively.

#### Conditional Edge Functions

```python
def _approval_decision(state):
    if state.get("user_approved") is True and state.get("selected_strategy"):
        return "write_events"
    return END
```

#### `run_graph_until_approval(graph, user_inputs) -> AgentState`
```python
initial_state = {
    "goal": user_inputs["goal"],
    "deadline": user_inputs["deadline"].isoformat(),
    "context": user_inputs.get("context", ""),
    "work_start": user_inputs["work_start"].strftime("%H:%M"),
    "work_end": user_inputs["work_end"].strftime("%H:%M"),
    "max_session_minutes": user_inputs["max_session_minutes"],
    "selected_strategy": None,
    "user_approved": None,
}
# With interrupt_before=["human_approval"], the graph pauses here.
# The exact API depends on your LangGraph version.
# Typically: result = graph.invoke(initial_state)
# The result is the paused state.
return graph.invoke(initial_state)
```

#### `resume_graph(graph, paused_state, approved) -> AgentState`
```python
resumed_state = dict(paused_state)
resumed_state["user_approved"] = approved
if approved:
    # app.py currently sets selected_strategy before calling resume_graph.
    # resume_graph validates it and copies the matching candidate to final_schedule.
    ...
approval_updates = human_approval_node(resumed_state)
resumed_state.update(approval_updates)
if _approval_decision(resumed_state) == "write_events":
    resumed_state.update(write_events_node(resumed_state))
return resumed_state
```

Current contract: `app.py` sets `graph_state["selected_strategy"] = strategy_name` before calling `resume_graph(graph, graph_state, approved=True)`. This should either be documented as canonical or refactored so `resume_graph` accepts `selected_strategy` explicitly.

---

### 9.3 Frontend (Step 6)

#### `src/frontend/intake_form.py`
Build a `st.form` with five fields. All Streamlit-specific. The key output is the `UserInputs` dict.

```python
with st.form("intake_form"):
    goal = st.text_input("What do you want to accomplish?")
    deadline = st.date_input("Deadline", value=datetime.date.today() + datetime.timedelta(days=14))
    context = st.text_area("Background context (optional)", value="")
    col1, col2 = st.columns(2)
    with col1:
        work_start = st.time_input("Work day starts at", value=datetime.time(9, 0))
    with col2:
        work_end = st.time_input("Work day ends at", value=datetime.time(18, 0))
    max_session = st.number_input("Max session length (minutes)", min_value=15, max_value=240, value=90, step=15)
    submitted = st.form_submit_button("Plan my schedule")

if submitted:
    # Validate, then return UserInputs dict
    ...
```

#### `src/frontend/schedule_display.py`
Use `st.dataframe` or a `for` loop with `st.write`. Group by date. Show the rationale with `st.info()`.

#### `src/frontend/approval_controls.py`
Strategy buttons plus a reject-all control. `render_strategy_buttons()` returns `(action, strategy_name)`, where action is `"approve"`, `"reject"`, or `None`.

#### `src/app.py`
State machine with four phases: `intake` → `running` → `review` → `done`.

```python
def _init_session_state():
    defaults = {"phase": "intake", "graph_state": None, "result": None}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
```

Then branch on `st.session_state["phase"]` and call the appropriate component functions.

---

### 9.4 Real Google Calendar Auth (Step 7 — only after everything works with mock)

#### `src/calendar_api/auth.py`
Follow the `google-auth-oauthlib` standard pattern:
1. Check for `token.json` → load credentials → refresh if expired.
2. If no token, run `InstalledAppFlow.from_client_secrets_file(credentials.json, SCOPES).run_local_server(port=0)`.
3. Save the new token to disk.
4. Return the `Credentials` object.

#### `src/calendar_api/events.py`
- `fetch_busy_blocks`: Call `service.events().list(...)` with `singleEvents=True, orderBy="startTime"`.
- `create_event`: Call `service.events().insert(...)` — **NEVER** call `update` or `delete`.
- `create_events_batch`: Loop over events, call `create_event` for each.

Remember to add `AGENT_TAG = "[CALENDAR_AGENT]"` to every event description.

---

## 10. File-by-File Implementation Reference

Quick-reference table of every file, what it depends on, and its key functions.

| # | File | Depends On | Key Functions | Notes |
|---|------|-----------|---------------|-------|
| 1 | `validator/constraints.py` | nothing | `intervals_overlap()`, `validate_schedule()` | Pure Python, test first |
| 2 | `calendar_api/free_slots.py` | nothing | `compute_free_slots()`, `_day_working_window()` | Pure Python, date math |
| 3 | `calendar_api/mock_calendar.py` | nothing | `fetch_mock_busy_blocks()`, `create_mock_event()` | Hardcoded test data |
| 4 | `llm_client/client.py` | `config.settings` | `call_llm_json()`, `call_llm_text()` | Retry loop, JSON parse |
| 5 | `heuristics/deadline_first.py` | `state.py` types | `schedule_deadline_first()` | Greedy earliest-first |
| 6 | `heuristics/minimize_fragmentation.py` | `state.py` types | `schedule_min_fragmentation()` | Largest-slot-first |
| 7 | `heuristics/energy_aware.py` | `state.py` types | `schedule_energy_aware()` | Morning=deep, PM=light |
| 8 | `nodes/decompose_goal.py` | `llm_client` | `decompose_goal_node()` | LLM prompt engineering |
| 9 | `nodes/fetch_events.py` | `calendar_api` | `fetch_events_node()` | Branches mock vs live |
| 10 | `nodes/schedule_candidates.py` | heuristics | 3 thin wrapper nodes | Each returns 1 key |
| 11 | `nodes/validate_candidates.py` | `validator` | `validate_candidates_node()` | Validates all 3, no selection |
| 12 | `nodes/generate_rationales.py` | `llm_client` | `generate_rationales_node()` | One rationale per strategy |
| 13 | `nodes/build_proposal.py` | nothing | `build_proposal_node()` | Near-duplicate detection |
| 14 | `nodes/human_approval.py` | nothing | `human_approval_node()` | Maps selected strategy to final_schedule |
| 15 | `nodes/write_events.py` | `calendar_api` | `write_events_node()` | Branches mock vs live |
| 16 | `orchestration/graph.py` | all nodes | `build_graph()`, `run_graph_until_approval()`, `resume_graph()` | LangGraph assembly |
| 17 | `frontend/intake_form.py` | nothing | `render_intake_form()` | Streamlit form |
| 18 | `frontend/schedule_display.py` | nothing | `render_all_candidates()`, `render_single_schedule()`, `render_collapsed_view()`, `render_violation_badge()` | Streamlit display |
| 19 | `frontend/approval_controls.py` | nothing | `render_strategy_buttons()` | Strategy/reject controls |
| 20 | `app.py` | `graph.py`, `frontend/*` | `main()`, `_init_session_state()` | State machine |
| 21 | `calendar_api/auth.py` | Google libs | `get_credentials()`, `build_calendar_service()` | Implemented; live verification pending |
| 22 | `calendar_api/events.py` | `auth.py` | `fetch_busy_blocks()`, `create_event()`, `create_events_batch()` | Add-only; live verification pending |

---

## 11. Testing Strategy

### Run tests per-module as you build

```bash
# After Phase 1
pytest tests/test_validator.py -v
pytest tests/test_calendar_api.py -v

# After Phase 2
pytest tests/test_llm_client.py -v
pytest tests/test_orchestration.py -v

# After Phase 3
pytest tests/test_frontend.py -v
pytest -v  # all tests
```

Current caveat: `.venv/bin/pytest -q` reports `46 passed`, but several tests are still no-op stubs. Fill in `tests/test_validator.py`, `tests/test_calendar_api.py`, and `tests/test_orchestration.py::TestValidateCandidates` before relying on the suite as a quality signal.

### Test fixtures live in `tests/conftest.py`

The fixtures provide realistic sample data that all tests share:
- `sample_busy_blocks` — 3 busy blocks on Apr 6–7
- `sample_free_slots` — the expected free gaps for those blocks
- `sample_subtasks` — 5 React-learning subtasks
- `sample_valid_schedule` — a schedule with no violations
- `sample_invalid_schedule` — a schedule with 3 deliberate violations
- `work_start`, `work_end`, `deadline` — standard values

### Mocking approach for LLM tests

```python
from unittest.mock import patch

@patch("src.llm_client.client._call_anthropic")
def test_valid_json_response_parsed(mock_call):
    mock_call.return_value = '[{"name": "task1", "description": "desc", "duration_minutes": 30}]'
    result = call_llm_json("some prompt")
    assert result == [{"name": "task1", "description": "desc", "duration_minutes": 30}]
```

### End-to-end smoke test (after Phase 3)

```bash
CALENDAR_MODE=mock streamlit run src/app.py
```

1. Fill the form → submit.
2. Verify the schedule appears with the expected number of events.
3. Verify the rationale text is displayed.
4. Click approve → verify mock events are "created" (check terminal logs).
5. Click reject → verify the session ends with no changes.

---

## 12. Common Pitfalls & Tips

### Datetime Timezone Trap
**Every datetime you create must be timezone-aware.** Mixing naive and aware datetimes will throw `TypeError: can't compare offset-naive and offset-aware datetimes`. Use `datetime.timezone.utc` everywhere:
```python
now = datetime.datetime.now(datetime.timezone.utc)
```

### ISO String Parsing
`datetime.datetime.fromisoformat("2026-04-06T10:00:00+00:00")` works in Python 3.11+. If the string has a `Z` suffix instead of `+00:00`, replace it: `s.replace("Z", "+00:00")`.

### LangGraph State Merging
Each node returns a **partial dict** — only the keys it modifies. LangGraph merges this into the full state. **Never return the entire state dict from a node.** Example:
```python
# GOOD:
return {"subtasks": subtasks_list}

# BAD — overwrites everything:
state["subtasks"] = subtasks_list
return state
```

### Slot-Splitting Consistency
All three heuristics need to split free slots when a subtask doesn't consume the entire slot. If you find yourself writing the same logic three times, extract it into a shared helper in `src/orchestration/heuristics/__init__.py`.

### Google Calendar Add-Only Rule
The `events.py` module must **never** call `service.events().update()` or `service.events().delete()`. This is a hard safety rule. The only write operation is `service.events().insert()`.

### Streamlit Session State
Streamlit re-runs the entire script on every interaction. That's why all persistent data must live in `st.session_state`. The graph's paused state is stored there so it survives button clicks:
```python
st.session_state["graph_state"] = paused_state
```

### Prompt Engineering for Decomposition
The decomposition prompt is the most important prompt in the system. Key instructions to include:
- "Return ONLY a JSON array — no markdown, no code fences, no preamble."
- "Each subtask must have: name, description, duration_minutes."
- "Subtasks should reflect genuine domain knowledge, not generic checklists."
- "No single subtask should exceed {max_session} minutes."

If the LLM wraps the JSON in ` ```json ... ``` `, your `call_llm_json` will fail. Consider stripping markdown fences in the parsing step.

### Config-Driven Mock vs Live
`settings.CALENDAR_MODE` controls which calendar backend is used. In `fetch_events_node` and `write_events_node`, branch with:
```python
if settings.CALENDAR_MODE == "mock":
    # use mock_calendar functions
else:
    # use real calendar_api functions
```
This lets you develop and test the entire pipeline without Google credentials.

---

## Current Quick-Start Checklist

- [ ] `pip install -r requirements.txt` — all dependencies install
- [ ] `cp .env.example .env` — fill in `ANTHROPIC_API_KEY`
- [ ] Run `.venv/bin/pytest -q` and confirm the current baseline
- [ ] Replace remaining no-op test stubs in validator/calendar API/validation-node tests
- [ ] Run `CALENDAR_MODE=mock streamlit run src/app.py` and record a full approve/reject walkthrough
- [ ] Confirm the approval/resume contract or refactor `resume_graph` to accept `selected_strategy`
- [ ] Reconcile LangGraph/LangChain version ranges in `requirements.txt` and `pyproject.toml`
- [ ] Verify `CALENDAR_MODE=live` with real Google OAuth credentials, or explicitly defer it
