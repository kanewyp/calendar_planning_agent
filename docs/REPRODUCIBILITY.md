# Reproducibility

Goals: every test, walkthrough, and benchmark in this repo should be
reproducible from a clean checkout in finite time. This document
records the determinism rules, version pins, and environment that
make that possible.

## Determinism Rules

### Heuristics and validator are pure

`src/orchestration/heuristics/` and `src/validator/constraints.py`
contain no LLM calls, no API calls, no Streamlit calls, no random
number generators, and no `datetime.now()` reads. Inputs in →
identical outputs out, every time, on every machine.

### LLM temperature is fixed at 0

All planning calls use `temperature=0.0`. This is the strongest
practical determinism contract a hosted LLM offers; identical
prompts to the same model version usually return identical
completions. Schedule structure stays stable; rationale prose may
shift slightly between provider deployments.

### Mock LLM provider is fully deterministic

`LLM_PROVIDER=mock` produces hand-crafted JSON for decomposition,
critic, candidate review, and rationale calls. Output is byte-for-byte
identical across runs. **Use mock for any reproducibility-critical
test.** Real-LLM tests live exclusively in `tests/llm_integration/`
and are gated by the `integration` pytest marker.

### Mock calendar is date-relative but seedable

`src/calendar_api/mock_calendar.py` builds busy blocks from a
weekday pattern relative to "today", in `APP_TIMEZONE`. To pin
results to a specific date, set the system clock or freeze time in
tests via `freezegun` (when needed). Test fixtures already do this
where date stability matters.

### No global RNG state

The codebase does not call `random.seed`, `numpy.random.seed`, or
similar. There are no RNG-dependent paths. If you add one, seed it
explicitly and document the seed here.

## Version Pinning

### Python

- Required: Python 3.11 or newer.
- Tested: 3.11, 3.12.

### Library versions

`requirements.txt` pins major/minor ranges, not exact patches:

```text
streamlit>=1.32.0,<2.0
langgraph>=1.0.0,<2.0
langchain-core>=0.3.0,<1.0
anthropic>=0.30.0,<1.0
google-api-python-client>=2.100.0,<3.0
google-auth-httplib2>=0.2.0,<1.0
google-auth-oauthlib>=1.2.0,<2.0
python-dotenv>=1.0.0,<2.0
pydantic>=2.5.0,<3.0
pytest>=8.0.0,<9.0
pytest-asyncio>=0.23.0,<1.0
```

Note that `requirements.txt` and `pyproject.toml` currently disagree
on the LangGraph / LangChain ranges; align them before publishing
benchmark results. See `docs/STATUS.md`.

### Snapshot for an exact rebuild

To reproduce the exact dependency tree of a paper / report:

```bash
.venv/bin/pip freeze > requirements.lock.txt
```

Commit `requirements.lock.txt` alongside the artifact, then on the
target machine:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock.txt
```

`requirements.lock.txt` is intentionally not committed by default —
it is a per-experiment artifact, not a project-level pin.

### LLM model versions

Defaults: `google/gemini-2.5-flash` for both decomposition and
rationale. Provider model strings are fully overridable via
`LLM_DECOMPOSITION_MODEL` and `LLM_RATIONALE_MODEL`. When reporting
results, always record the exact model identifier in use — providers
silently roll point releases.

## Environment Snapshot

Recommended snapshot to attach to any experiment:

```bash
python --version > env.txt
pip freeze >> env.txt
echo "LLM_PROVIDER=$LLM_PROVIDER" >> env.txt
echo "LLM_DECOMPOSITION_MODEL=$LLM_DECOMPOSITION_MODEL" >> env.txt
echo "LLM_RATIONALE_MODEL=$LLM_RATIONALE_MODEL" >> env.txt
echo "CALENDAR_MODE=$CALENDAR_MODE" >> env.txt
echo "APP_TIMEZONE=$APP_TIMEZONE" >> env.txt
git rev-parse HEAD >> env.txt
```

Together with the goal text and busy-block fixture, `env.txt` is
sufficient to reproduce a planning run.

## Reproducing a Bad Run

When a candidate looks wrong:

1. Open the **Debug trace** expander in the review or done view.
2. Copy the compact report — it includes provider/model, structural
   tags, scheduled order, validation results, and approval state.
3. Note the goal text, deadline, working hours, and timezone.
4. Re-run with the same env vars to confirm the bug reproduces.
5. Switch to `LLM_PROVIDER=mock` to bisect: if the bug disappears,
   it is provider-side; if it persists, it is a heuristic or
   validator bug — both of which are pure and easy to bisect.

## Test Reproducibility

Only `tests/programmatic/` is deterministic by construction:

- All LLM calls are monkey-patched to return fixture JSON.
- All Google Calendar service calls are mocked.
- Heuristics and validator are pure.
- Working-directory state is not used (tests do not write files).

Run order should not matter; if you find a test whose pass/fail
depends on order, treat it as a bug.

```bash
CALENDAR_MODE=mock LLM_PROVIDER=mock \
  .venv/bin/pytest -q tests/programmatic/ -p no:randomly
```

(`pytest-randomly` is not in the dependency set; if added later,
keep `-p no:randomly` for benchmark-quality runs and remove it for
ordinary CI.)

`tests/pipeline_unit/` and `tests/llm_integration/` are **not**
deterministic — both call the real LLM. Their conftests auto-skip
when `LLM_PROVIDER=mock`, so they cannot be used as deterministic
regression tests. They assert structural properties (schema, length,
presence of keywords) rather than exact text, so re-runs are stable
in shape but variable in wording.

For paper-grade repeatability, restrict claims to the programmatic
suite plus a single recorded debug-trace run with the env snapshot
attached.
