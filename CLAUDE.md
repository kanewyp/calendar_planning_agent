# CLAUDE.md

## Project Overview

Calendar Planning Agent -- a Streamlit app that takes a natural-language goal, decomposes it into subtasks via Claude (Anthropic LLM), finds free time on Google Calendar, schedules subtasks across available slots using three heuristics, validates each against hard constraints, and presents all three options to the user. The user picks a strategy (or rejects all), and approved events are written to the calendar. Built on LangGraph for orchestration.

**Status:** Skeleton/scaffold. Most functions have `pass # TODO: implement` bodies with detailed step-by-step comments. All test bodies are also stubs.

## Tech Stack

- **Python 3.11+** (required)
- **Streamlit** -- frontend UI (intake form, schedule display, approval buttons)
- **LangGraph / LangChain Core** -- directed graph orchestration with human-in-the-loop pause
- **Anthropic SDK** -- LLM calls via `claude-sonnet-4-20250514`
- **Google Calendar API** -- OAuth 2.0 for event read/create (add-only, never update/delete)
- **Pydantic** -- validation
- **python-dotenv** -- env var loading
- **pytest / pytest-asyncio** -- testing

## Quick Commands

```bash
# Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run (mock calendar, no Google creds needed)
CALENDAR_MODE=mock streamlit run src/app.py

# Run tests
pytest -v

# Docker
docker compose up --build          # dev with live-reload
docker build -t calendar-agent .   # production image
```

## Project Structure

```
config/settings.py          -- Settings singleton, reads .env via dotenv
src/app.py                  -- Streamlit entry point, session state controller
src/frontend/
  intake_form.py            -- 5-field form -> UserInputs TypedDict
  schedule_display.py       -- Three-column strategy comparison (or collapsed view)
  approval_controls.py      -- Per-strategy "Pick this plan" + "Reject all" buttons
src/calendar_api/
  auth.py                   -- Google OAuth 2.0 flow + token caching
  events.py                 -- Fetch busy blocks + create events (ADD-ONLY)
  free_slots.py             -- Pure-logic free-slot computation
  mock_calendar.py          -- Hardcoded test data (CALENDAR_MODE=mock)
src/orchestration/
  state.py                  -- AgentState TypedDict + Subtask, ProposedEvent, Violation types
  graph.py                  -- LangGraph graph definition + run/resume helpers
  nodes/                    -- One file per graph node
    decompose_goal.py       -- LLM decomposes goal -> subtasks
    fetch_events.py         -- Fetches calendar + computes free slots
    schedule_candidates.py  -- Wraps 3 heuristic calls as graph nodes
    validate_candidates.py  -- Runs validator on all 3 candidates (no winner picked)
    generate_rationales.py  -- LLM writes one rationale per strategy
    build_proposal.py       -- Detects near-duplicates, packages for frontend
    human_approval.py       -- User picks a strategy or rejects; graph pauses here
    write_events.py         -- Writes approved events to calendar
  heuristics/
    deadline_first.py       -- Greedy earliest-slot assignment
    minimize_fragmentation.py -- Largest-slot-first assignment
    energy_aware.py         -- Heavy tasks in morning, light in afternoon
src/validator/
  constraints.py            -- 4 hard constraints: overlap, self-overlap, working hours, deadline
src/llm_client/
  client.py                 -- call_llm_json / call_llm_text with retry logic
tests/                      -- pytest tests (all stubs, mirror src modules)
infrastructure/             -- AWS CloudFormation + deploy script (placeholder)
```

## Graph Topology

```
START -> decompose_goal -> fetch_events
  -> [deadline_first, min_fragmentation, energy_aware] (parallel)
  -> validate_candidates (validator on all 3, no winner picked)
  -> generate_rationales (one LLM rationale per strategy)
  -> build_proposal (detect near-duplicates, package for UI)
  -> human_approval (PAUSE — user picks a strategy or rejects all)
      pick strategy -> write_events -> END
      reject all    -> END
```

## Key Data Types (src/orchestration/state.py)

- **AgentState** -- TypedDict (`total=False`) carrying all state through the graph
- **Subtask** -- `{name, description, duration_minutes}`
- **ProposedEvent** -- `{name, description, start (ISO), end (ISO)}`
- **Violation** -- `{event_name, violation_type, description}`
- **ValidationResult** -- `{passed: bool, violations: list[Violation]}`

## Environment Variables (.env)

See `.env.example`. Key vars:
- `ANTHROPIC_API_KEY` -- required for LLM calls
- `GOOGLE_CLIENT_SECRET_FILE` -- path to OAuth client secret JSON
- `CALENDAR_MODE` -- `mock` (default) or `live`
- `DEFAULT_WORK_START` / `DEFAULT_WORK_END` -- default 09:00 / 18:00

## Important Constraints

- **Add-only calendar writes** -- never call `events().update()` or `events().delete()`
- **Never commit secrets** -- `.env`, `token.json`, `credentials.json` are all in `.gitignore`
- **Heuristics are pure functions** -- no LLM or API calls, fully unit-testable
- **Validator is pure Python** -- no LLM involvement, deterministic constraint checking
- **LLM client uses `claude-sonnet-4-20250514`** with up to 2 retries on parse failure or API error
- **Mock mode** (`CALENDAR_MODE=mock`) enables full development without Google credentials
- **No repair loop** -- violations are surfaced per-candidate so the user judges tradeoffs

## Testing

```bash
pytest -v
```

- Tests use fixtures from `tests/conftest.py` (sample busy blocks, free slots, subtasks, schedules)
- LLM client tests should mock `_call_anthropic`, never make real API calls
- Calendar API tests use mock calendar, never real Google API
- `asyncio_mode = "auto"` is configured in `pyproject.toml`

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs `pytest -v` on Python 3.11 and 3.12 against `main` on push/PR. Uses `CALENDAR_MODE=mock`.

## Implementation Order (Two-Person Split)

See `docs/PROJECT_PLAN.md` for full details and `docs/WILL_IMPLEMENTATION_GUIDE.md` for Will's step-by-step guide.

### Phase 1 — Foundations (Parallel, No Cross-Dependencies)
- **Will:** `llm_client/client.py`, `calendar_api/auth.py`, `calendar_api/events.py`, `tests/test_llm_client.py`
- **Partner:** `validator/constraints.py`, `free_slots.py`, `mock_calendar.py`, 3 heuristics, `tests/test_validator.py`, `tests/test_calendar_api.py`

### Phase 2 — Graph Nodes & Frontend (Partially Parallel)
- **Will:** All 8 graph nodes (`decompose_goal`, `fetch_events`, `schedule_candidates`, `validate_candidates`, `generate_rationales`, `build_proposal`)
- **Partner:** `frontend/intake_form.py`, `frontend/schedule_display.py`

### Phase 3 — Graph Wiring & App Integration (Collaborative)
- **Will:** `graph.py` (build/run/resume), `human_approval`, `write_events`
- **Partner:** `approval_controls.py`, `app.py` (session state controller)

### Phase 4 — End-to-End Testing (Together)
- Full flow in `CALENDAR_MODE=mock`, edge cases, CI green on 3.11 & 3.12, Docker
