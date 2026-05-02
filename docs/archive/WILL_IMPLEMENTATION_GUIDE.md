# Will's Implementation Guide: LangGraph Orchestration & Infrastructure

> Archived historical implementation guide. For current status, use `docs/STATUS.md`.

**Owner:** Will (Person A)
**Focus:** LLM client, Google Calendar API, all graph nodes, graph wiring
**Status:** Historical implementation guide. The current integration branch has implemented the core Will-owned pieces; use this file as design/reference context, not as a list of open implementation tasks.
**Original implementation order:** Phase 1 -> Phase 2 -> Phase 3 (sequential, each phase builds on the previous)

Current integration notes:
- `src/llm_client/client.py`, `src/calendar_api/auth.py`, and `src/calendar_api/events.py` are implemented.
- Graph nodes, graph wiring helpers, approval handling, and write-events handling are implemented on the integration branch.
- Partner-owned dependencies called by Will's nodes are now implemented in source.
- `.venv/bin/pytest -q` currently reports `46 passed`, but some tests remain no-op stubs and need completion.
- Mock-mode end-to-end Streamlit validation and live Google Calendar verification are still pending.

---

## Phase 1: LLM Client & Calendar API

These are foundational -- every graph node that calls the LLM or touches the calendar depends on them. They are implemented on the current integration branch.

---

### 1.1 `src/llm_client/client.py`

**Priority:** Implement first -- 3 of the 8 graph nodes depend on this.

#### `_build_client() -> anthropic.Anthropic`
- Read `settings.ANTHROPIC_API_KEY` from the settings singleton
- If the key is empty/missing, raise `ValueError("ANTHROPIC_API_KEY is not set")`
- Return `anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)`

#### `_call_anthropic(prompt, temperature=0.0, max_tokens=4096) -> str`
- Call `_build_client()` to get the client
- Call `client.messages.create(model=MODEL_ID, max_tokens=max_tokens, temperature=temperature, messages=[{"role": "user", "content": prompt}])`
- Return `response.content[0].text`
- Let API exceptions propagate -- callers handle retries

#### `call_llm_json(prompt, temperature=0.0) -> Any`
- Loop `for attempt in range(MAX_RETRIES + 1)` (i.e., 3 total attempts):
  - Call `_call_anthropic(prompt, temperature)`
  - Strip whitespace, try `json.loads(response_text)`
  - On success: return parsed object
  - On `json.JSONDecodeError`: if not last attempt, optionally append "Your previous response was not valid JSON. Return ONLY JSON." to the prompt and continue
  - On `anthropic.APIError`: if not last attempt, continue
- After all retries: raise `ValueError("Failed to get valid JSON after retries")`

#### `call_llm_text(prompt, temperature=0.0) -> str`
- Same retry loop but no JSON parsing
- On success: return text
- On `anthropic.APIError`: retry
- After exhaustion: raise `RuntimeError("LLM call failed after retries")`

#### Testing (`tests/test_llm_client.py`)
- Mock `_call_anthropic` (use `unittest.mock.patch`)
- Test: valid JSON response returns parsed object
- Test: invalid JSON on first try, valid on retry -> succeeds
- Test: all retries fail -> raises `ValueError`
- Test: `call_llm_text` returns text directly
- Test: API error triggers retry
- **Never make real API calls in tests**

---

### 1.2 `src/calendar_api/auth.py`

#### `get_credentials() -> Credentials`
- Check if `token.json` exists on disk
  - If yes: load with `Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)`
  - If token expired but has refresh token: `creds.refresh(google.auth.transport.requests.Request())`
  - Save refreshed token back to disk, return
- If no valid token: start OAuth flow
  - `flow = InstalledAppFlow.from_client_secrets_file(settings.GOOGLE_CLIENT_SECRET_FILE, SCOPES)`
  - `creds = flow.run_local_server(port=0)`
  - Save to `_TOKEN_PATH`
- Return credentials
- **Security:** never log/print tokens

#### `build_calendar_service() -> Resource`
- `creds = get_credentials()`
- Return `build("calendar", "v3", credentials=creds)`

---

### 1.3 `src/calendar_api/events.py`

#### `fetch_busy_blocks(time_min, time_max, calendar_id="primary") -> list[dict]`
- Call `build_calendar_service()`
- `service.events().list(calendarId=calendar_id, timeMin=time_min.isoformat(), timeMax=time_max.isoformat(), singleEvents=True, orderBy="startTime").execute()`
- Iterate items: extract `start["dateTime"]` and `end["dateTime"]`
- Skip all-day events (they have `"date"` instead of `"dateTime"`)
- Return `[{"start": start_iso, "end": end_iso}, ...]` sorted by start

#### `create_event(summary, description, start, end, calendar_id="primary") -> dict`
- Build event body:
  ```python
  {
      "summary": summary,
      "description": f"{AGENT_TAG} {description}",
      "start": {"dateTime": start.isoformat(), "timeZone": str(start.tzinfo)},
      "end": {"dateTime": end.isoformat(), "timeZone": str(end.tzinfo)},
  }
  ```
- `service.events().insert(calendarId=calendar_id, body=event_body).execute()`
- **NEVER call `events().update()` or `events().delete()`**

#### `create_events_batch(events, calendar_id="primary") -> list[dict]`
- For each event dict: parse `start`/`end` ISO strings to `datetime` objects
- Call `create_event(name, description, start_dt, end_dt, calendar_id)`
- Return list of API responses

---

## Phase 2: Graph Nodes

Each node is a function that takes `AgentState` and returns a partial state dict. Implement in this order since some nodes depend on others being testable.

---

### 2.1 `src/orchestration/nodes/decompose_goal.py`

**Depends on:** `call_llm_json` (Phase 1)

#### `decompose_goal_node(state: AgentState) -> dict`

1. Format `DECOMPOSITION_PROMPT` with:
   - `goal = state["goal"]`
   - `deadline = state["deadline"]`
   - `context = state.get("context", "")`
   - `max_session = state["max_session_minutes"]`

2. Call `call_llm_json(prompt)` -- returns a list of dicts

3. Validate each item:
   - Has keys: `"name"` (non-empty string), `"description"` (string), `"duration_minutes"` (positive int)
   - `duration_minutes <= state["max_session_minutes"]` -- current implementation raises `ValueError` if it exceeds the limit

4. Convert to `list[Subtask]` TypedDicts

5. Return `{"subtasks": subtasks_list}`

**Error handling:** If `call_llm_json` raises after retries, let it propagate -- `app.py` will catch and display.

---

### 2.2 `src/orchestration/nodes/fetch_events.py`

**Depends on:** Partner's `compute_free_slots`, `fetch_mock_busy_blocks` (Phase 1)

#### `fetch_events_node(state: AgentState) -> dict`

1. Parse `state["deadline"]` to `datetime.date`

2. Set time window:
   - `time_min = datetime.datetime.now(datetime.timezone.utc)`
   - `time_max = deadline at end of day (23:59:59 UTC)`

3. Branch on `settings.CALENDAR_MODE`:
   - `"mock"`: `from src.calendar_api.mock_calendar import fetch_mock_busy_blocks` then call it
   - `"live"`: `from src.calendar_api.events import fetch_busy_blocks` then call it

4. Parse `state["work_start"]` and `state["work_end"]` to `datetime.time`

5. Call `compute_free_slots(busy_blocks, time_min, time_max, work_start, work_end)`

6. Return `{"busy_blocks": busy_blocks, "free_slots": free_slots}`

---

### 2.3 `src/orchestration/nodes/schedule_candidates.py`

**Depends on:** Partner's 3 heuristic functions (Phase 1)

These are thin wrappers. Each node:
1. Extracts `subtasks` and `free_slots` from state
2. Calls the corresponding heuristic function
3. Returns the result under the correct state key

#### `deadline_first_node(state) -> dict`
```python
result = schedule_deadline_first(state["subtasks"], state["free_slots"])
return {"candidate_deadline_first": result}
```

#### `min_fragmentation_node(state) -> dict`
```python
result = schedule_min_fragmentation(state["subtasks"], state["free_slots"])
return {"candidate_min_fragmentation": result}
```

#### `energy_aware_node(state) -> dict`
```python
result = schedule_energy_aware(state["subtasks"], state["free_slots"], state["work_start"])
return {"candidate_energy_aware": result}
```

**Current note:** The integrated `energy_aware_node` passes `work_start` through as the state string, matching the current heuristic interface.

---

### 2.4 `src/orchestration/nodes/validate_candidates.py`

**Depends on:** Partner's `validate_schedule` (Phase 1)

#### `validate_candidates_node(state) -> dict`

1. Parse shared validation inputs:
   - `busy_blocks = state["busy_blocks"]`
   - `work_start = datetime.time.fromisoformat(state["work_start"])`
   - `work_end = datetime.time.fromisoformat(state["work_end"])`
   - `deadline_dt = datetime.datetime.fromisoformat(state["deadline"])` (or parse as date then add end-of-day time)

2. For each strategy:
   ```python
   strategies = {
       "deadline_first": state["candidate_deadline_first"],
       "min_fragmentation": state["candidate_min_fragmentation"],
       "energy_aware": state["candidate_energy_aware"],
   }
   ```

3. Run `validate_schedule(candidate, busy_blocks, work_start, work_end, deadline_dt)` for each

4. Return:
   ```python
   {"candidate_validations": {name: result for name, result in ...}}
   ```

---

### 2.5 `src/orchestration/nodes/generate_rationales.py`

**Depends on:** `call_llm_text` (Phase 1)

#### `generate_rationales_node(state) -> dict`

1. Build `subtasks_summary` from `state["subtasks"]`:
   ```python
   subtasks_summary = "\n".join(
       f"- {s['name']} ({s['duration_minutes']} min): {s['description']}"
       for s in state["subtasks"]
   )
   ```

2. For each strategy (`"deadline_first"`, `"min_fragmentation"`, `"energy_aware"`):
   a. Get candidate from corresponding state key
   b. Build `schedule_summary`:
      ```python
      schedule_summary = "\n".join(
          f"- {e['name']}: {e['start']} to {e['end']}"
          for e in candidate
      )
      ```
   c. Get validation: `state["candidate_validations"][strategy_name]`
   d. Format `RATIONALE_PROMPT` with all values including:
      - `violation_count = len(validation["violations"])`
      - `violation_summary` = "None" or comma-separated violation types
   e. Call `call_llm_text(prompt)` to get rationale text

3. Return:
   ```python
   {"candidate_rationales": {"deadline_first": r1, "min_fragmentation": r2, "energy_aware": r3}}
   ```

**Performance note:** This makes 3 sequential LLM calls. Could use `asyncio.gather` for parallelism later, but sequential is fine for MVP.

---

### 2.6 `src/orchestration/nodes/build_proposal.py`

**Depends on:** Nothing external (pure logic on state)

#### `build_proposal_node(state) -> dict`

1. Read all three candidates from state

2. Near-duplicate detection:
   - Sort each candidate's events by start time
   - Compare across all three: are all event start/end times identical?
   - Simple approach: serialize each sorted candidate as a list of `(start, end)` tuples, check equality
   - Set `candidates_identical = True` if all three match, else `False`

3. Return `{"candidates_identical": candidates_identical}`

---

## Phase 3: Graph Wiring & Final Nodes

---

### 3.1 `src/orchestration/graph.py` -- `build_graph()`

This is the core of the LangGraph orchestration. Wire all nodes and edges.

```python
def build_graph() -> StateGraph:
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

    # Entry point
    graph.set_entry_point("decompose_goal")

    # Linear edges
    graph.add_edge("decompose_goal", "fetch_events")

    # Fan-out: fetch_events -> 3 parallel heuristics
    # Use LangGraph's native fan-out (check version support)
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

    # Conditional edge after human_approval
    graph.add_conditional_edges("human_approval", _approval_decision)

    # Terminal edge
    graph.add_edge("write_events", END)

    # Compile with interrupt
    return graph.compile(interrupt_before=["human_approval"])
```

#### Key LangGraph considerations:
- **Fan-out/fan-in:** LangGraph supports this natively. The 3 heuristic nodes write to separate state keys (`candidate_deadline_first`, `candidate_min_fragmentation`, `candidate_energy_aware`) so there's no reducer conflict.
- **`interrupt_before`:** The graph pauses before `human_approval` executes, returning control to `app.py` which displays the proposal to the user.
- **Conditional edges:** `_approval_decision` returns either `"write_events"` or `END` based on `state["user_approved"]`.

---

### 3.2 `src/orchestration/graph.py` -- `_approval_decision(state)`

```python
def _approval_decision(state: AgentState) -> str:
    if state.get("user_approved") is True and state.get("selected_strategy"):
        return "write_events"
    return END
```

---

### 3.3 `src/orchestration/graph.py` -- `run_graph_until_approval(graph, user_inputs)`

1. Build initial state:
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
   ```

2. Invoke: `result = graph.invoke(initial_state)`
   - The graph runs all nodes up to `human_approval`, then pauses due to `interrupt_before`

3. Return the paused state

**Current note:** The integrated helper currently invokes the compiled graph and expects the paused state dict back at `interrupt_before=["human_approval"]`. It does not currently use a persisted checkpointer/thread-id flow.

---

### 3.4 `src/orchestration/graph.py` -- `resume_graph(graph, paused_state, approved)`

1. Copy and update state:
   ```python
   resumed_state = dict(paused_state)
   resumed_state["user_approved"] = approved
   if approved:
       selected_strategy = resumed_state.get("selected_strategy")
       # app.py currently sets selected_strategy before calling resume_graph.
       # resume_graph validates it and copies the matching candidate to final_schedule.
   ```

2. Execute the approval path:
   - `human_approval_node` populates `final_schedule`
   - `_approval_decision` routes to `write_events` if approved, or ends cleanly if rejected
   - `write_events_node` is called directly from the helper when approved

3. Return final state

**Current contract:** `resume_graph(graph, paused_state, approved)` still takes only `approved`; `app.py` sets `graph_state["selected_strategy"]` before calling it. This works in the current code. The remaining decision is whether to document that as canonical or refactor the helper to accept `selected_strategy` explicitly.

---

### 3.5 `src/orchestration/nodes/human_approval.py`

#### `human_approval_node(state) -> dict`

```python
STRATEGY_TO_STATE_KEY = {
    "deadline_first": "candidate_deadline_first",
    "min_fragmentation": "candidate_min_fragmentation",
    "energy_aware": "candidate_energy_aware",
}

def human_approval_node(state: AgentState) -> dict[str, Any]:
    if state.get("user_approved") is True and state.get("selected_strategy"):
        state_key = STRATEGY_TO_STATE_KEY[state["selected_strategy"]]
        return {"final_schedule": state[state_key]}
    return {}
```

---

### 3.6 `src/orchestration/nodes/write_events.py`

#### `write_events_node(state) -> dict`

1. Read `state["final_schedule"]`

2. Branch on `settings.CALENDAR_MODE`:
   - `"mock"`:
     ```python
     from src.calendar_api.mock_calendar import create_mock_event
     responses = []
     for event in final_schedule:
         start_dt = datetime.fromisoformat(event["start"])
         end_dt = datetime.fromisoformat(event["end"])
         resp = create_mock_event(event["name"], event["description"], start_dt, end_dt)
         responses.append(resp)
     ```
   - `"live"`:
     ```python
     from src.calendar_api.events import create_events_batch
     responses = create_events_batch(final_schedule)
     ```

3. Return `{"write_results": responses}`

---

## Dependency Chain Summary

```
Phase 1 (implemented; no dependencies):
  client.py  ←  no deps
  auth.py    ←  no deps
  events.py  ←  auth.py

Phase 2 (implemented after Phase 1):
  decompose_goal.py       ←  client.py (call_llm_json)
  fetch_events.py         ←  Partner's free_slots + mock_calendar
  schedule_candidates.py  ←  Partner's 3 heuristics
  validate_candidates.py  ←  Partner's validate_schedule
  generate_rationales.py  ←  client.py (call_llm_text)
  build_proposal.py       ←  no external deps (pure logic on state)

Phase 3 (implemented after Phase 2):
  graph.py                ←  all nodes from Phase 2
  human_approval.py       ←  no external deps
  write_events.py         ←  events.py or mock_calendar
```

---

## Testing Strategy

### Unit tests you own:
- `tests/test_llm_client.py` -- mock `_call_anthropic`, test retry logic, JSON parsing
- Node-level tests (can add to `tests/test_orchestration.py`):
  - Mock LLM calls for `decompose_goal_node`, `generate_rationales_node`
  - Mock calendar API for `fetch_events_node`
  - Use fixtures from `conftest.py` for state construction

### Integration tests:
- Full graph run in `CALENDAR_MODE=mock` with mocked LLM
- Test the interrupt/resume flow with `human_approval`
- Test both approval and rejection paths
- Current gap: no-op tests remain in validator/calendar API/validation-node areas; replace them before relying on the green suite as full coverage.

### What to mock:
- `_call_anthropic` -- always mock in tests, never hit real API
- `build_calendar_service` -- mock for calendar tests
- Partner's functions -- don't mock these, use their real implementations (they're pure functions)

---

## Common Pitfalls to Watch For

1. **LangGraph v1:** The project targets LangGraph v1+ (pinned `>=1.0.0,<2.0` in requirements.txt). Graph primitives (StateGraph, nodes, edges, interrupt) are unchanged from 0.x. The `create_react_agent` prebuilt was deprecated in favor of `langchain.agents.create_agent`, but we don't use it -- we build a custom graph. Fan-out/fan-in should work natively.

2. **Interrupt/resume model:** The current integrated helper uses `interrupt_before=["human_approval"]` for the initial graph run, then handles approval/write execution from the paused state in `resume_graph`. If future work needs persisted multi-session graph continuation, revisit a checkpointer/thread-id design.

3. **State key conflicts in fan-in:** The 3 heuristic nodes write to different keys, so no reducer is needed. But if LangGraph requires explicit reducer config, you may need to annotate `AgentState` fields.

4. **Timezone handling:** All ISO datetime strings should be timezone-aware (UTC). Use `datetime.timezone.utc` consistently. The mock calendar data uses `+00:00`.

5. **`resume_graph` signature:** The current contract is app-owned state mutation: `app.py` sets `selected_strategy` on the paused state, then calls `resume_graph(graph, paused_state, approved=True)`. Refactor to an explicit `selected_strategy` parameter only if the team wants a cleaner public interface.

6. **Thread ID for checkpointer:** Each graph run needs a unique thread ID for the checkpointer. Generate with `uuid4()` and store in Streamlit session state.

---

## Coordination with Partner

### Partner dependencies

These are now implemented on the integration branch:
- `compute_free_slots()` -- used by `fetch_events_node`
- `fetch_mock_busy_blocks()` -- used by `fetch_events_node` in mock mode
- The three heuristic functions -- used by `schedule_candidates.py`
- `validate_schedule()` -- used by `validate_candidates_node`
- Frontend/app flow -- calls `run_graph_until_approval()` and `resume_graph()`

### Remaining coordination
- Document or refactor the approval/resume contract.
- Run and record a full mock-mode app walkthrough.
- Replace remaining no-op test stubs.
- Decide whether live Google Calendar verification is required before merging to `main`.
