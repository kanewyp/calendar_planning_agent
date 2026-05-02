# Developer Guide

This is the concise day-to-day guide. For architecture, read `docs/ARCHITECTURE.md`. For current progress and gaps, read `docs/STATUS.md`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Mock mode is the default development path and does not require Google credentials:

```bash
CALENDAR_MODE=mock streamlit run src/app.py
```

## Test

Current baseline:

```bash
.venv/bin/pytest -q
```

The suite currently passes, but do not treat it as complete coverage until remaining no-op tests are replaced. See `docs/STATUS.md`.

Useful targeted runs:

```bash
.venv/bin/pytest -q tests/test_llm_client.py
.venv/bin/pytest -q tests/test_orchestration.py
.venv/bin/pytest -q tests/test_frontend.py
.venv/bin/pytest -q tests/test_validator.py tests/test_calendar_api.py
```

## Local App Smoke Test

Run:

```bash
CALENDAR_MODE=mock streamlit run src/app.py
```

Walkthrough to record:

1. Submit intake form.
2. Confirm all candidate schedules render.
3. Approve one strategy and confirm mock events are created.
4. Restart and reject all, confirming no writes.

## Environment Variables

Key values from `.env.example`:

- `ANTHROPIC_API_KEY`
- `GOOGLE_CLIENT_SECRET_FILE`
- `CALENDAR_MODE`
- `DEFAULT_WORK_START`
- `DEFAULT_WORK_END`

Use `CALENDAR_MODE=mock` unless explicitly testing live Google Calendar behavior.

## Testing Rules

- Mock LLM calls through `_call_anthropic`.
- Mock Google Calendar service calls in tests.
- Do not require live credentials for unit tests.
- Keep heuristics and validator pure and easy to unit-test.
- When adding state fields, update `src/orchestration/state.py` first.

## Development Priorities

Current high-value work:

1. Replace no-op tests in:
   - `tests/test_validator.py`
   - `tests/test_calendar_api.py`
   - `tests/test_orchestration.py::TestValidateCandidates`
2. Run and document the full mock-mode app walkthrough.
3. Decide whether to keep or refactor the approval/resume contract.
4. Reconcile dependency version ranges between `requirements.txt` and `pyproject.toml`.
5. Verify live Google Calendar mode or explicitly defer it.

## Safety Checklist

Before committing:

```bash
.venv/bin/pytest -q
git status --short
```

Also check:

- No `.env`, `token.json`, `credentials.json`, OAuth token, or API key is staged.
- No Google Calendar update/delete operation has been added.
- Mock mode still works.
- Any new LLM or Google API path is tested with mocks.

## Reference Docs

- `AGENTS.md` / `CLAUDE.md` -- concise AI entrypoints.
- `docs/STATUS.md` -- current project status.
- `docs/ARCHITECTURE.md` -- system contracts and graph design.
- `PROGRAMMER_MANUAL.md` -- long-form detailed reference.
- `docs/archive/PROJECT_PLAN.md` and `docs/archive/WILL_IMPLEMENTATION_GUIDE.md` -- historical planning/implementation notes.
