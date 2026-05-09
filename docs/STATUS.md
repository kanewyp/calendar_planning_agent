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
118 passed
```

The previous no-op `pass # TODO` tests in `tests/test_validator.py`,
`tests/test_calendar_api.py`, and
`tests/test_orchestration.py::TestValidateCandidates` have been replaced with
assertive unit tests.

## Known Gaps

- Run and record a full `CALENDAR_MODE=mock` Streamlit walkthrough:
  - intake form submit
  - candidate generation display
  - approve path writes mock events
  - reject path exits with no writes
  - startup/import issue for `streamlit run src/app.py` has been fixed
- `CALENDAR_MODE=mock LLM_PROVIDER=mock` graph smoke test passes without live LLM or Google credentials.
- `CALENDAR_MODE=mock LLM_PROVIDER=vertex_ai` Streamlit approve-path smoke test passes with Google Cloud ADC and creates mock calendar events.
- Debug trace is captured in graph state and shown in Streamlit review/done views for local troubleshooting.
- Debug trace now includes structural tag summaries, strategy input/output order,
  chronological order inversion diagnostics, energy-aware profile metadata, and
  scheduled event time-of-day periods.
- Verify Gemini API or another API-key-based low-cost provider only if policy allows API keys.
- Verify live Google Calendar mode with real OAuth credentials, or explicitly defer it.
- One-off shell overrides now take precedence over `.env`, so commands like
  `CALENDAR_MODE=mock LLM_PROVIDER=mock streamlit run src/app.py` work even
  when `.env` is configured for a live provider.

## Debug Trace

Current behavior:

- `AgentState["debug_trace"]` accumulates compact per-node trace events.
- Trace events include node name, status, timestamp, summaries, and safe details.
- Decomposition trace records LLM provider/model and subtask summaries.
- Decomposition trace also surfaces parsed structural tags from subtask descriptions.
- Calendar, heuristic, validation, rationale, proposal, approval, and write nodes record compact counts and selected outputs.
- Schedule traces record strategy input/output ordering and chronological order
  inversion diagnostics; energy-aware traces also record energy levels and event
  period metadata.
- Streamlit review/done pages expose a "Debug trace" expander with a compact report and raw JSON.
- Full prompt/response bodies are not stored by default.
- LLM metadata now records the configured token budget. Decomposition defaults
  to `LLM_DECOMPOSITION_MAX_TOKENS=8192`, while rationale generation defaults
  to `LLM_RATIONALE_MAX_TOKENS=2048`.
- Provider responses that end because of `max_tokens`/`finish_reason=length`
  now fail with an explicit truncation message instead of surfacing only a
  downstream JSON parse error.
- Rationale generation now falls back to deterministic local explanations if
  the rationale LLM call fails. The debug trace records fallback counts and the
  first root-cause error so planning can still reach approval.
- Rationale prompts use compact schedule/subtask summaries. Provider
  `max_tokens` truncation is treated as non-retryable for rationale text, so a
  fallback is produced immediately instead of waiting through three failed
  attempts.
- Schedule traces now distinguish pure `dependency_order` from
  strategy-adjusted `expected_strategy_order`. Energy-aware event traces include
  task complexity, period energy score, and energy mismatch score.
- Multi-agent decomposition review is now captured as separate
  `decomposition_critic` and optional `revise_decomposition` trace steps. The
  critic can request one bounded revision before calendar fetching begins.
- Candidate schedules are now reviewed by multiple specialized reviewer prompts
  inside `review_candidates`. Reviewer recommendations, scores, and fallback
  status are stored in `AgentState["candidate_reviews"]` and surfaced in the
  Streamlit review UI.

## LLM Providers

Current behavior:

- All LLM calls go through `src/llm_client/client.py`.
- Supported providers are `anthropic`, `gemini`, `vertex_ai`, `openai_compatible`, and `mock`.
- `LLM_PROVIDER=gemini` uses Gemini's OpenAI-compatible Chat Completions endpoint.
- `LLM_PROVIDER=vertex_ai` uses Vertex AI's OpenAI-compatible Chat Completions endpoint with Google Cloud Application Default Credentials.
- `LLM_PROVIDER=mock` returns deterministic local responses for end-to-end mock walkthroughs.
- Goal decomposition uses the `decomposition` purpose; decomposition critique
  uses `decomposition_critic`; candidate comparison uses `candidate_review`;
  schedule explanations use `rationale`.

## Approval Contract

Current behavior:

- `run_graph_until_approval(graph, user_inputs)` returns a paused state with all candidates, validations, rationales, and `candidates_identical`.
- Approve flow calls `resume_graph(graph, graph_state, approved=True, selected_strategy=strategy_name)`.
- `resume_graph(...)` validates `selected_strategy`, records it in state, copies the selected candidate into `final_schedule`, and runs `write_events_node`.
- Reject flow calls `resume_graph(graph, graph_state, approved=False)` and exits without writes.

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
