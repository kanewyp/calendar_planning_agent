# Developer Guide

This is the concise day-to-day guide. For architecture, read `docs/ARCHITECTURE.md`. For current progress and gaps, read `docs/STATUS.md`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Mock calendar mode does not require Google credentials. Use `LLM_PROVIDER=mock`
for a fully local walkthrough that also skips paid/hosted LLM calls:

```bash
CALENDAR_MODE=mock LLM_PROVIDER=mock streamlit run src/app.py
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
CALENDAR_MODE=mock LLM_PROVIDER=mock streamlit run src/app.py
```

Walkthrough to record:

1. Submit intake form.
2. Confirm all candidate schedules render.
3. Approve one strategy and confirm mock events are created.
4. Restart and reject all, confirming no writes.

## Environment Variables

Key values from `.env.example`:

- `LLM_PROVIDER` -- `anthropic`, `gemini`, `vertex_ai`, `openai_compatible`, or `mock`
- `LLM_API_KEY` -- generic key for Gemini/OpenAI-compatible providers
- `GEMINI_API_KEY` -- optional Gemini-specific key
- `VERTEX_PROJECT_ID` -- Google Cloud project for Vertex AI
- `VERTEX_LOCATION` -- Vertex AI location, defaults to `global`
- `ANTHROPIC_API_KEY` -- legacy Anthropic-specific key
- `LLM_BASE_URL` -- required for `LLM_PROVIDER=openai_compatible`
- `LLM_DECOMPOSITION_MODEL`
- `LLM_RATIONALE_MODEL`
- `GOOGLE_CLIENT_SECRET_FILE`
- `CALENDAR_MODE`
- `DEFAULT_WORK_START`
- `DEFAULT_WORK_END`

Use `CALENDAR_MODE=mock` unless explicitly testing live Google Calendar behavior.
Use `LLM_PROVIDER=mock` unless explicitly testing a live LLM provider.

Gemini example:

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=<your Gemini API key>
LLM_DECOMPOSITION_MODEL=gemini-2.5-flash
LLM_RATIONALE_MODEL=gemini-2.5-flash
```

Vertex AI example using Google Cloud credits:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project <your-google-cloud-project-id>
```

```dotenv
LLM_PROVIDER=vertex_ai
VERTEX_PROJECT_ID=<your-google-cloud-project-id>
VERTEX_LOCATION=global
LLM_DECOMPOSITION_MODEL=google/gemini-2.5-flash
LLM_RATIONALE_MODEL=google/gemini-2.5-flash
```

Smoke test with Vertex AI and mock calendar:

```bash
CALENDAR_MODE=mock LLM_PROVIDER=vertex_ai streamlit run src/app.py
```

OpenAI-compatible example for Groq/OpenRouter-style endpoints:

```dotenv
LLM_PROVIDER=openai_compatible
LLM_API_KEY=<provider key>
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_DECOMPOSITION_MODEL=<provider model>
LLM_RATIONALE_MODEL=<provider model>
```

## Testing Rules

- Mock LLM calls through `_call_llm`, `_call_anthropic`, or `_post_json`.
- Mock Google Calendar service calls in tests.
- Do not require live credentials for unit tests.
- Keep heuristics and validator pure and easy to unit-test.
- When adding state fields, update `src/orchestration/state.py` first.

## Development Priorities

Current high-value work:

1. Run and document the full mock-mode app walkthrough.
2. Verify Gemini or another low-cost live LLM provider.
3. Verify live Google Calendar mode or explicitly defer it.

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
