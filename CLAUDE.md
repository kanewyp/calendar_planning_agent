# CLAUDE.md

## Project Overview

Calendar Planning Agent is a Streamlit app that decomposes a natural-language goal into subtasks with Claude, finds free time on Google Calendar, produces three heuristic schedules, validates them against hard constraints, shows all options to the user, and writes only the approved events.

For current implementation status, known gaps, and next actions, read `docs/STATUS.md`. Keep current status there; do not duplicate long progress notes in this file.

## Quick Commands

```bash
# Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run in mock-calendar mode
CALENDAR_MODE=mock streamlit run src/app.py

# Test current baseline
.venv/bin/pytest -q
```

## Architecture Pointers

- `src/app.py` -- Streamlit entry point and session-state flow.
- `src/orchestration/state.py` -- shared `AgentState`, `Subtask`, `ProposedEvent`, and validation types.
- `src/orchestration/graph.py` -- graph construction plus `run_graph_until_approval()` / `resume_graph()`.
- `src/orchestration/nodes/` -- one graph node per step.
- `src/orchestration/heuristics/` -- pure scheduling strategies.
- `src/calendar_api/` -- mock/live calendar reads and add-only event creation.
- `src/validator/constraints.py` -- deterministic hard-constraint validation.
- `src/frontend/` -- Streamlit components.

Graph shape:

```text
decompose_goal -> fetch_events
  -> [deadline_first, min_fragmentation, energy_aware]
  -> validate_candidates -> generate_rationales -> build_proposal
  -> human_approval -> write_events or END
```

## Hard Rules

- Calendar writes are add-only. Never call Google Calendar `events().update()` or `events().delete()`.
- Never commit secrets: `.env`, `token.json`, `credentials.json`, OAuth tokens, or API keys.
- Heuristics and validator must stay pure Python: no LLM calls, no API calls, no side effects.
- All LLM calls go through `src/llm_client/client.py`.
- Mock mode (`CALENDAR_MODE=mock`) must keep working without Google credentials.
- No repair loop: validation violations are surfaced per candidate for user judgment.

## Current Caveats

- `.venv/bin/pytest -q` currently passes, but some passing tests are still no-op stubs. See `docs/STATUS.md`.
- The approval contract currently relies on `app.py` setting `graph_state["selected_strategy"]` before calling `resume_graph(...)`.
- `requirements.txt` and `pyproject.toml` currently disagree on LangGraph/LangChain version ranges.

## Deeper References

- `docs/STATUS.md` -- current source of truth for progress and next actions.
- `docs/ARCHITECTURE.md` -- stable graph, state, and module contracts.
- `docs/DEVELOPER_GUIDE.md` -- setup, testing, and local workflow.
- `PROGRAMMER_MANUAL.md` -- long-form detailed reference.
- `docs/archive/PROJECT_PLAN.md` -- original phased plan.
- `docs/archive/WILL_IMPLEMENTATION_GUIDE.md` -- historical Will implementation guide.
- `docs/archive/WILL_STATUS.md` and `docs/archive/KANE_STATUS.md` -- owner-specific historical/status notes.
