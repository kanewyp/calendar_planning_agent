# Performance and Optimization

This document describes the cost / latency choices made by the
Calendar Planning Agent and the tunables that affect them. Numbers
quoted are wall-clock times measured on the developer machine
(macOS, M-series); use them as orders of magnitude, not benchmarks.

## End-to-End Cost Profile

Per planning request the agent makes a small, bounded number of LLM
calls:

| Call | Purpose | Default model | Default `max_tokens` |
|------|---------|---------------|----------------------|
| Decomposition | Goal → subtasks JSON | `google/gemini-2.5-flash` | 8192 |
| Decomposition critic | Validate / revise subtasks | same | 8192 |
| Candidate review (×3) | Review per heuristic candidate | same | 2048 |
| Rationale (×3) | Human-readable explanation | `google/gemini-2.5-flash` | 2048 |

Worst case: 1 decomposition + 1 critic + 1 revision + 3 reviews +
3 rationales = **9 LLM calls** per request. The critic is permitted
exactly one revision round, so growth is bounded.

Calendar API: **1 read** (free-busy / events list) per request.
Writes occur only after user approval, one event per accepted
subtask. Add-only by design.

## Tunables

All tunables live in `config/settings.py` and are overridable via
environment variables.

### Token budgets

| Variable | Default | When to raise |
|----------|---------|---------------|
| `LLM_DECOMPOSITION_MAX_TOKENS` | 8192 | Long goals, many subtasks, structural tags push JSON past budget |
| `LLM_RATIONALE_MAX_TOKENS` | 2048 | Wordy rationales truncated mid-sentence |

Truncation is treated as a hard error for JSON purposes (decomposition,
critic, candidate review) and triggers a deterministic fallback for
text purposes (rationale).

### Retry policy

`MAX_RETRIES = 2` in `src/llm_client/client.py`. Retries fire on
JSON parse failure or transient provider errors only; truncation is
non-retryable for rationales (wastes budget on the same failure mode).

### Temperature

Default `0.0` for all calls. Determinism is more valuable than
diversity here — schedule rationales benefit from being stable
across runs.

### Provider switching

`LLM_PROVIDER=mock` short-circuits all calls to deterministic local
responses, dropping wall-clock from ~10 s to < 100 ms per request.
Use it during local UI work and pipeline testing.

## Latency Breakdown (mock calendar, Vertex AI)

Approximate share of a single planning run:

```
decompose_goal             ~1.5 s
decomposition_critic       ~1.0 s
fetch_events (mock)         <50 ms
3 × heuristics (pure Py)    <50 ms
validate_candidates         <10 ms
review_candidates (3 calls) ~2.5 s  (parallelizable; not currently parallel)
generate_rationales (3)    ~2.0 s
build_proposal              <10 ms
human_approval              user
write_events (mock)         <50 ms
```

Total non-blocking (excluding user wait): **~7 s**. The two slowest
nodes are `review_candidates` and `generate_rationales`, both
parallelizable across the three candidates — see "Future
optimizations" below.

## Heuristic Complexity

All three strategies are pure Python and bounded by the number of
free slots `f` and subtasks `n`:

| Heuristic | Time complexity | Memory |
|-----------|-----------------|--------|
| `deadline_first` | O(n × f) greedy fit | O(n + f) |
| `min_fragmentation` | O(n log n + n × f) sort + fit | O(n + f) |
| `energy_aware` | O(n × f) with period scoring | O(n + f) |

Validator is O((n + b) log (n + b)) where `b` is busy-block count,
dominated by the chronological sort.

## Validator Cost

Deterministic and pure. Per candidate:

- 1 chronological sort of busy ∪ proposed events
- Linear scans for OVERLAP / SELF_OVERLAP
- Per-event boundary check for OUT_OF_HOURS / DEADLINE_EXCEEDED

Three candidates × small `n` → milliseconds.

## Caching

Currently **none**. The system is stateless per request. Caching is
deliberately deferred because:

- Goal text is unique per request → low hit rate.
- Calendar state changes between runs → stale-cache risk.
- Mock provider already handles the offline-development case.

If a session-scoped cache is added later, the natural seam is
`_call_llm` in `src/llm_client/client.py` keyed by
`(provider, model, prompt, purpose, max_tokens)`.

## Prompt-Cache Awareness (Anthropic)

When `LLM_PROVIDER=anthropic`, the client passes long system prompts
unchanged across decomposition + rationale calls so providers that
support prompt caching (Claude 3.5+ / Claude 4.x) can reuse prefix
tokens. No explicit cache control headers are set yet — adding
`cache_control: {type: "ephemeral"}` is a low-risk follow-up if
Anthropic becomes the primary provider.

## Test Suite Cost

| Suite | Wall-clock | Real LLM calls | Cost driver |
|-------|-----------|----------------|-------------|
| `tests/programmatic/` | < 1 s | 0 (all mocked) | none |
| `tests/pipeline_unit/` | ~3–4 min | ~100 | full pipeline per test |
| `tests/llm_integration/` | ~110 s | ~99 | one LLM call per test |

`tests/pipeline_unit/` is the most expensive single suite — every
test re-runs decomposition through rationale generation. Treat it as
a nightly / pre-PR check, not an inner CI loop. The suite auto-skips
on `LLM_PROVIDER=mock` so cost-conscious CI runs simply omit ADC.

## Future Optimizations

Ranked by expected impact:

1. **Parallelize the 3 candidate reviews and 3 rationale calls.**
   Each triple is independent; running them concurrently roughly
   halves total latency. Implementation: replace the sequential
   loops in `src/orchestration/nodes/review_candidates.py` and
   `generate_rationales.py` with `asyncio.gather` or
   `concurrent.futures`. Same change cuts pipeline_unit wall-clock
   roughly in half.
2. **Streaming rationale UI.** Emit partial rationale text to
   Streamlit as it arrives instead of waiting for completion.
3. **Anthropic prompt caching headers** — see above.
4. **Subtask deduplication** before review. If the critic produces
   identical subtasks across revision rounds, skip the second review
   pass.
5. **Mock-fixture variant of pipeline_unit.** The real-LLM suite
   covers structural assertions that could equally well run against
   recorded fixtures. A parallel `tests/pipeline_unit_mock/` would
   give offline coverage without skipping.

None of these are required for correctness; they are listed as
explicit deferred work.

## Profiling Notes

For ad-hoc profiling during development:

```bash
CALENDAR_MODE=mock LLM_PROVIDER=mock \
  python -m cProfile -s cumulative -o profile.out \
  -m streamlit run src/app.py
```

The mock provider keeps cProfile output focused on Python-side hot
paths instead of network latency.
