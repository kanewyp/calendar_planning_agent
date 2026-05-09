# Troubleshooting

Common failures and the smallest fix that resolves them. If a symptom
is not covered here, check the in-app **Debug trace** expander
(review / done page) or run the pytest suite to localize the regression.

## Setup and Imports

### `ModuleNotFoundError: No module named 'src.…'`

Streamlit was launched outside the project root, or `.venv` is not
activated.

```bash
cd calendar_planning_agent
source .venv/bin/activate
streamlit run src/app.py
```

If imports still fail, reinstall in editable mode:

```bash
pip install -e .
```

### `streamlit: command not found`

`pip install -r requirements.txt` did not run inside `.venv`. Activate
the venv first, then reinstall.

### Wrong Python version

Project targets Python ≥ 3.11. Confirm with `python --version`. If
older, recreate the venv with an explicit interpreter:

```bash
python3.11 -m venv .venv
```

## LLM Provider Errors

### `LLM JSON response was truncated at max_tokens before valid JSON could be completed`

The decomposition output exceeded the configured budget. Raise it
above the value reported in the error:

```bash
LLM_DECOMPOSITION_MAX_TOKENS=12288 streamlit run src/app.py
```

Default is 8192. Same pattern for rationale: `LLM_RATIONALE_MAX_TOKENS`,
default 2048.

### `LLM text response was truncated at max_tokens` during rationale generation

Rationale generation now falls back to a deterministic local
explanation, so planning still reaches approval. To eliminate the
fallback path, raise `LLM_RATIONALE_MAX_TOKENS`.

### `google.auth.exceptions.DefaultCredentialsError`

`LLM_PROVIDER=vertex_ai` requires Google Application Default
Credentials.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project <gcp-project-id>
```

If running headless, set
`GOOGLE_APPLICATION_CREDENTIALS=/abs/path/to/service-account.json`.
Service-account JSON files must **never** be committed — see
`.gitignore` patterns for the exact filenames blocked.

### `429 RESOURCE_EXHAUSTED` / quota errors

Either provider quota is depleted or the request burst exceeded the
per-minute limit. Retry after a delay, or switch
`LLM_PROVIDER=mock` for local development.

### Provider returns valid response but `_parse_json` fails

Inspect the offending payload via the debug trace. Most common cause is
a model that wraps JSON in markdown fences; the client already strips
fences, so a remaining failure usually means the schema changed. File
an issue with the redacted prompt and response.

## Google Calendar Errors

### Browser does not open during OAuth

Run the auth step in a desktop session, or copy the printed URL into a
browser manually. The token is cached in `token.json` (gitignored).

### `403 Forbidden` when reading calendar

The OAuth scope did not include calendar read. Delete `token.json` and
re-authenticate so the scopes are re-requested.

### Live writes appear missing

Confirm `GOOGLE_CALENDAR_ID` matches the calendar you are inspecting.
The default is `primary`. Agent-created events are tagged
`[CALENDAR_AGENT]` in the description; filter by that to find them.

### Mock mode dates look wrong

`src/calendar_api/mock_calendar.py` builds busy blocks relative to
`datetime.now()` per weekday pattern. If your system clock is wrong,
mock blocks land on unexpected dates.

## Streamlit Runtime

### Port 8501 already in use

Either kill the previous process or choose a new port:

```bash
streamlit run src/app.py --server.port 8502
```

### App reloads partial state on rerun

Streamlit reruns the entire script on every interaction. Long-running
graph state is held in `st.session_state` keyed by phase
(`intake`/`running`/`review`/`done`). If state appears to reset,
verify the phase is being preserved (see `src/app.py`).

### Selected strategy reverts after approval

Check that `graph_state["selected_strategy"]` is set in `src/app.py`
before `resume_graph(...)`. The approval contract relies on this.

## Test Failures

### `tests/llm_integration/` or `tests/pipeline_unit/` mostly skipped

Both suites call the real LLM and auto-skip when
`LLM_PROVIDER=mock`. Expected without ADC credentials. Either set up
ADC or stick to the programmatic suite:

```bash
CALENDAR_MODE=mock LLM_PROVIDER=mock .venv/bin/pytest -q tests/programmatic/
```

### Tests pass locally but fail in CI

Confirm CI sets `CALENDAR_MODE=mock` and `LLM_PROVIDER=mock`. The
no-credentials CI run must restrict to `tests/programmatic/` —
`tests/pipeline_unit/` and `tests/llm_integration/` need ADC.

### Pipeline tests are very slow

`tests/pipeline_unit/` runs ~3–4 minutes against real Vertex AI by
design. If you only want a quick smoke check, drop `LLM_PROVIDER` to
`mock` and accept the auto-skip behavior.

## Timezone / Working Hours

### Events scheduled outside working hours

`OUT_OF_HOURS` violations show in the validation panel. Confirm
`DEFAULT_WORK_START` / `DEFAULT_WORK_END` and `APP_TIMEZONE` env vars
match the user's expectation. Mock data uses `APP_TIMEZONE`.

### Mock calendar shows wrong day

Mock blocks follow weekday patterns relative to today, in
`APP_TIMEZONE`. Set `APP_TIMEZONE=Asia/Taipei` if testing from Taiwan.

## Debug Trace

When a candidate looks wrong, expand **Debug trace** in the review or
done view. The compact report includes:

- LLM provider/model + token budget per call
- subtask structural tags
- per-strategy input vs scheduled order
- chronological-order inversion diagnostics
- energy-aware period and complexity scores
- validator violation counts
- approval decision

Paste the compact report into an issue when reporting bugs.
