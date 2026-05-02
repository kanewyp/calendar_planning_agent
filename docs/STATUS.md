# Current Project Status

Last synced from `docs/sync-project-status`, branched from `integration/phase2-with-partner`.

## Baseline

The current integration baseline has the core mock-mode application flow implemented:

- LLM client wrappers in `src/llm_client/client.py`
- Google Calendar auth/events wrappers in `src/calendar_api/auth.py` and `src/calendar_api/events.py`
- Free-slot computation and mock calendar support in `src/calendar_api/`
- Deterministic validator in `src/validator/constraints.py`
- Three pure scheduling heuristics in `src/orchestration/heuristics/`
- Graph nodes in `src/orchestration/nodes/`
- Graph construction and run/resume helpers in `src/orchestration/graph.py`
- Streamlit UI components in `src/frontend/`
- App session-state flow in `src/app.py`

## Test Status

Current command:

```bash
.venv/bin/pytest -q
```

Current result:

```text
46 passed
```

Important caveat: the green suite is not full coverage yet. These areas still contain no-op `pass # TODO` tests:

- `tests/test_validator.py`
- `tests/test_calendar_api.py`
- `tests/test_orchestration.py::TestValidateCandidates`

## Known Gaps

- Replace the remaining no-op tests listed above.
- Run and record a full `CALENDAR_MODE=mock` Streamlit walkthrough:
  - intake form submit
  - candidate generation display
  - approve path writes mock events
  - reject path exits with no writes
- Verify live Google Calendar mode with real OAuth credentials, or explicitly defer it.
- Reconcile dependency metadata:
  - `requirements.txt` targets LangGraph 1.x / LangChain Core 0.3.x
  - `pyproject.toml` still lists LangGraph `<1.0` / LangChain Core 0.2.x
- Decide whether to keep or refactor the approval/resume contract.

## Approval Contract

Current behavior:

- `run_graph_until_approval(graph, user_inputs)` returns a paused state with all candidates, validations, rationales, and `candidates_identical`.
- In approve flow, `src/app.py` sets `graph_state["selected_strategy"] = strategy_name`.
- `resume_graph(graph, graph_state, approved=True)` validates `selected_strategy`, copies the selected candidate into `final_schedule`, and runs `write_events_node`.
- Reject flow calls `resume_graph(graph, graph_state, approved=False)` and exits without writes.

Open decision: document this app-owned state mutation as the canonical contract, or refactor `resume_graph` to accept `selected_strategy` explicitly.

## Non-Negotiable Constraints

- Calendar writes are add-only: never call `events().update()` or `events().delete()`.
- Never commit secrets: `.env`, `token.json`, `credentials.json`, OAuth tokens, or API keys.
- Heuristics and validator stay pure: no LLM/API calls or side effects.
- Mock mode must work without Google credentials.
- Tests must mock LLM and Google APIs.

## Historical References

- `docs/archive/PROJECT_PLAN.md` -- original two-person phased plan.
- `docs/archive/WILL_IMPLEMENTATION_GUIDE.md` -- Will's historical implementation guide.
- `docs/archive/WILL_STATUS.md` -- Will-specific status notes.
- `docs/archive/KANE_STATUS.md` -- Kane-specific status notes.
- `docs/ARCHITECTURE.md` -- stable graph, state, and module contracts.
- `docs/DEVELOPER_GUIDE.md` -- setup, testing, and local workflow.
- `PROGRAMMER_MANUAL.md` -- long-form detailed reference manual.
