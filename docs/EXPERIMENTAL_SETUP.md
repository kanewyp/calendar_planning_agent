# Experimental Setup

Step-by-step instructions for reproducing the test results and
walkthroughs reported elsewhere in the project. Pair this document
with `docs/REPRODUCIBILITY.md` (determinism rules) and
`docs/PERFORMANCE.md` (cost / latency model).

> Test counts in this document assume the `test/unit-test` branch
> has been merged into the working branch. Pre-merge baselines
> still report 118 passing tests via the legacy `tests/` layout.

## 0. Prerequisites

- Python 3.11+
- macOS / Linux (Windows works via WSL but is not the tested target)
- (Optional) `gcloud` CLI for Vertex AI integration tests
- (Optional) Google OAuth desktop client for live Calendar mode

## 1. Clean Checkout

```bash
git clone https://github.com/kanewyp/calendar_planning_agent.git
cd calendar_planning_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

No real keys are needed for the fast suite or mock-mode walkthrough.

## 2. Three Test Tiers

The repository ships three independently runnable pytest suites,
each pinned to a different point on the cost / coverage tradeoff.

### 2.1 Programmatic unit tests — `tests/programmatic/`

Coverage: every module in `src/`. LLM and Google Calendar calls are
monkey-patched. No credentials, no network.

```bash
CALENDAR_MODE=mock .venv/bin/pytest -q tests/programmatic/
```

Expected: **118 passing** in ~1 s. Use this suite as the inner CI
loop.

### 2.2 Pipeline unit tests — `tests/pipeline_unit/`

**Despite the name, this suite calls the real LLM.** The conftest
auto-skips every test when `LLM_PROVIDER=mock`, so it must run with
`LLM_PROVIDER=vertex_ai` and Google ADC credentials present.
Coverage: structural assertions on subtask shape, rationale quality,
and structural-tag handling end-to-end through the pipeline.
Numbered T01–T99 to map 1:1 onto `docs/PIPELINE_UNIT_TEST_TRACE.md`.

```bash
CALENDAR_MODE=mock LLM_PROVIDER=vertex_ai \
  .venv/bin/pytest -q tests/pipeline_unit/
```

Expected: **100 passing** in ~3–4 min with real Vertex AI calls.
Without credentials it reports `69 passed, 31 skipped in 0.4 s` —
the skipped tests are the LLM-touching ones.

### 2.3 LLM integration tests — `tests/llm_integration/`

Coverage: the four LLM-calling nodes — `decompose_goal`,
`decomposition_critic`, `review_candidates`, `generate_rationales` —
against a real provider. Asserts structural properties, not exact
text.

```bash
CALENDAR_MODE=mock LLM_PROVIDER=vertex_ai \
  .venv/bin/pytest tests/llm_integration/ -v -m integration -s
```

Expected: **99 passing** in ~110 s with Vertex AI ADC credentials.
Auto-skips when credentials are absent.

### 2.4 Combined runs

| Goal | Command | Expected |
|------|---------|----------|
| No-credentials inner loop | `CALENDAR_MODE=mock LLM_PROVIDER=mock .venv/bin/pytest -q tests/programmatic/` | 118 passing in <1 s |
| All real-LLM tests | `CALENDAR_MODE=mock LLM_PROVIDER=vertex_ai .venv/bin/pytest -q tests/` | 317 passing in ~4–5 min |
| Pre-PR safe default | `CALENDAR_MODE=mock LLM_PROVIDER=mock .venv/bin/pytest -q tests/programmatic/ tests/pipeline_unit/` | 118 + (69 passed, 31 skipped) |

Use the third command when no ADC credentials are available — the
pipeline_unit skip behavior is by design and counts as a passing run
for the purposes of CI.

## 3. Credentials Setup

### 3.1 Vertex AI for the LLM integration suite

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project <gcp-project-id>
```

Then in `.env`:

```dotenv
LLM_PROVIDER=vertex_ai
VERTEX_PROJECT_ID=<gcp-project-id>
VERTEX_LOCATION=global
LLM_DECOMPOSITION_MODEL=google/gemini-2.5-flash
LLM_RATIONALE_MODEL=google/gemini-2.5-flash
```

The integration suite reads `GOOGLE_APPLICATION_CREDENTIALS` if set;
otherwise it falls back to the `gcloud` ADC cache. Service-account
JSON files **must not** be committed (see `.gitignore`).

### 3.2 Google Calendar for live mode

Download an OAuth desktop client JSON from
`console.cloud.google.com → APIs & Services → Credentials`. Save it
as `credentials.json` in the project root. First run opens a browser
for consent and writes `token.json`. Both files are gitignored.

```dotenv
CALENDAR_MODE=live
GOOGLE_CLIENT_SECRET_FILE=credentials.json
GOOGLE_CALENDAR_ID=primary
```

## 4. Streamlit Walkthrough

### 4.1 Fully offline

```bash
CALENDAR_MODE=mock LLM_PROVIDER=mock streamlit run src/app.py
```

Expected: app at `http://localhost:8501`, three candidates render in
< 5 s, no network traffic.

### 4.2 Mock calendar + real LLM

```bash
CALENDAR_MODE=mock LLM_PROVIDER=vertex_ai streamlit run src/app.py
```

Expected: ~7 s end-to-end, real subtask decomposition, mock writes
on approval.

### 4.3 Live Google Calendar + real LLM

```bash
CALENDAR_MODE=live LLM_PROVIDER=vertex_ai streamlit run src/app.py
```

Expected: real Calendar read, agent-tagged events created on
approval. Use a test calendar; the agent does not delete events.

## 5. Mock Calendar Fixture

`demo_busy_blocks_may_2026.ics` mirrors the busy-block weekday pattern
in `src/calendar_api/mock_calendar.py`. Open it in a calendar
application to see the working week the mock simulates.

## 6. Recording a Run

For any reportable experiment:

1. Capture the env snapshot (see `docs/REPRODUCIBILITY.md`).
2. Save the goal, deadline, working hours, and timezone.
3. Approve a candidate and copy the **Debug trace** compact report.
4. Save Streamlit screenshots if reporting UX.

The compact debug report is sufficient to reconstruct provider /
model / token-budget / structural-tag / order-inversion state.

## 7. Known Gotchas

- The legacy single-folder `tests/` layout (pre `test/unit-test`
  merge) reports 118 passing — that is the same set of tests, not
  a different total.
- `requirements.txt` and `pyproject.toml` disagree on LangGraph /
  LangChain ranges; lock both before benchmarking. See
  `docs/STATUS.md`.
- Vertex AI quota errors surface as `429 RESOURCE_EXHAUSTED`. Re-run
  after a delay or fall back to `LLM_PROVIDER=mock`.
- `APP_TIMEZONE` affects mock busy-block dates. Set it consistently
  across runs you want to compare.

## 8. Cross-References

- `docs/STATUS.md` — current state, gaps, and next actions.
- `docs/REPRODUCIBILITY.md` — determinism rules and version pinning.
- `docs/PERFORMANCE.md` — cost and latency profile.
- `docs/TROUBLESHOOTING.md` — common failures.
- `docs/PIPELINE_UNIT_TEST_TRACE.md` (post-merge) — pipeline test
  inventory.
- `docs/LLM_INTEGRATION_TEST_TRACE.md` (post-merge) — integration
  test inventory and assertion design.
