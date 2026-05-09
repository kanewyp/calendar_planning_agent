# docs/LLM_INTEGRATION_TEST_TRACE.md

## LLM Integration Test Trace

### What This Suite Actually Tests

`tests/llm_integration/` contains **real LLM integration tests** — every test in this suite
sends a genuine prompt to the configured LLM provider (Vertex AI / Gemini 2.5 Flash by
default) and asserts structural properties of the response.

No mocks are used. A failing test means the LLM produced output that does not meet the
pipeline's contracts.

Contrast with `tests/pipeline_unit/`, which patches out all LLM calls and tests
orchestration logic only:

| Suite | LLM called? | Speed | What fails if it fails |
|-------|-------------|-------|------------------------|
| `tests/pipeline_unit/` | No (mocked) | ~1 s | Pipeline routing / parsing logic |
| `tests/llm_integration/` | **Yes (real)** | ~90–120 s | Prompt quality, model compliance, API auth |

---

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| Google Application Default Credentials | Service-account key at `google_credential.json` **or** `gcloud auth application-default login` |
| `LLM_PROVIDER=vertex_ai` (or `gemini`, `anthropic`) | Set in `.env`; do **not** set `LLM_PROVIDER=mock` |
| `GOOGLE_APPLICATION_CREDENTIALS=google_credential.json` | Set in `.env` or as an env-var override |
| `VERTEX_PROJECT_ID` | Must match the service-account's project |

The credential guard in `tests/llm_integration/conftest.py` auto-skips the suite if ADC
cannot be refreshed, so these tests are safe to collect in CI without credentials — they
simply skip.

---

### Run Commands

```bash
# Full integration suite (99 tests, ~90–120 s, requires credentials)
CALENDAR_MODE=mock .venv/bin/pytest tests/llm_integration/ -v -m integration

# Skip integration tests (safe in CI / no-credentials environments)
CALENDAR_MODE=mock .venv/bin/pytest tests/ -q
# (integration tests are not included unless -m integration is passed)

# Programmatic + pipeline-unit only (218 tests, ~2 s, no credentials)
CALENDAR_MODE=mock .venv/bin/pytest tests/ -q --ignore=tests/llm_integration
```

---

### Assertion Design

Because LLM output is non-deterministic, all assertions are **structural**:

| Assertion type | Example |
|----------------|---------|
| Shape | `"subtasks" in result`, `isinstance(result, list)` |
| Count bounds | `3 <= len(subtasks) <= 12` |
| Type correctness | `isinstance(duration_minutes, int)` |
| Hard limits | `duration_minutes <= max_session_minutes` |
| Tag presence | `any("[group:" in d for d in descriptions)` |
| Severity calibration | No `"critical"` issues for the prompt's worked-example plan |
| Distinctness | All three rationale strings are different |
| Length bound | Rationale ≤ 180 words (3× the prompt's 60-word target, allowing LLM drift) |
| Error-signal absence | No `"Traceback"` / `"LLM provider request failed"` / mock fallback text |
| Revision correctness | Original vague task name no longer present after revision |

Exact string matching is intentionally avoided — it would make the suite brittle to
prompt wording changes and harmless model variation.

---

### Session-Scoped Fixtures — API Call Count

Each test file uses a `scope="session"` fixture so the real LLM is called **once per
scenario**, not once per test. All tests in a file share that single response.

| Fixture | LLM calls | Tests that reuse it |
|---------|-----------|---------------------|
| `real_decomposition_sql` | 1 | T-D01–T-D15 (15 tests) |
| `real_decomposition_talk` | 1 | T-D16–T-D30 (15 tests) |
| `real_critic_good` | 1 | T-C01–T-C12 (12 tests) |
| `real_critic_flawed_mega` | 1 | T-C13–T-C21 (9 tests) |
| `real_critic_flawed_groups` | 1 | T-C22–T-C29 (8 tests) |
| `real_rationales` | 3 (one per strategy) | T-R01–T-R25 (25 tests) |
| `real_revision` | 1 | T-V01–T-V15 (15 tests) |
| **Total** | **9** | **99 tests** |

---

### Execution Summary

**Run date:** 2026-05-09
**Branch:** `test/unit-test`
**Command:** `CALENDAR_MODE=mock .venv/bin/pytest tests/llm_integration/ -v -m integration`
**Provider:** `vertex_ai` — `google/gemini-2.5-flash`
**Python:** 3.13.5 | **pytest:** 8.4.2 | **Duration:** ~113 s

| Result | Count |
|--------|-------|
| Passed | 99 |
| Failed | 0 |
| **Total collected** | **99** |

---

### Full Test Results

#### `test_decompose_real.py` — decompose_goal_node with real LLM

Two goals. Fixtures: `real_decomposition_sql` (T-D01–T-D15) and `real_decomposition_talk` (T-D16–T-D30).

**Goal A:** `"Learn SQL basics in one week"` | max_session: 90 min
**Goal B:** `"Write and deliver a 10-minute conference talk on machine learning"` | max_session: 90 min

| ID | Test Function | Result |
|----|---------------|--------|
| T-D01 | test_d01_sql_result_has_subtasks_key | PASS |
| T-D02 | test_d02_sql_subtasks_is_nonempty_list | PASS |
| T-D03 | test_d03_sql_subtask_count_in_range | PASS |
| T-D04 | test_d04_sql_all_names_nonempty_strings | PASS |
| T-D05 | test_d05_sql_all_descriptions_are_strings | PASS |
| T-D06 | test_d06_sql_durations_valid | PASS |
| T-D07 | test_d07_sql_at_least_one_group_tag | PASS |
| T-D08 | test_d08_sql_at_least_one_complexity_tag | PASS |
| T-D09 | test_d09_sql_at_least_one_shuffle_tag | PASS |
| T-D10 | test_d10_sql_all_task_names_unique | PASS |
| T-D11 | test_d11_sql_at_least_two_distinct_groups | PASS |
| T-D12 | test_d12_sql_complexity_values_valid | PASS |
| T-D13 | test_d13_sql_at_least_one_nontrivial_task | PASS |
| T-D14 | test_d14_sql_total_duration_is_positive | PASS |
| T-D15 | test_d15_sql_no_empty_descriptions | PASS |
| T-D16 | test_d16_talk_result_has_subtasks_key | PASS |
| T-D17 | test_d17_talk_subtasks_is_nonempty_list | PASS |
| T-D18 | test_d18_talk_subtask_count_in_range | PASS |
| T-D19 | test_d19_talk_all_names_nonempty_strings | PASS |
| T-D20 | test_d20_talk_all_descriptions_are_strings | PASS |
| T-D21 | test_d21_talk_durations_valid | PASS |
| T-D22 | test_d22_talk_at_least_one_group_tag | PASS |
| T-D23 | test_d23_talk_at_least_one_complexity_tag | PASS |
| T-D24 | test_d24_talk_at_least_one_shuffle_tag | PASS |
| T-D25 | test_d25_talk_all_task_names_unique | PASS |
| T-D26 | test_d26_talk_at_least_two_distinct_groups | PASS |
| T-D27 | test_d27_talk_complexity_values_valid | PASS |
| T-D28 | test_d28_talk_at_least_one_nontrivial_task | PASS |
| T-D29 | test_d29_talk_total_duration_is_positive | PASS |
| T-D30 | test_d30_talk_no_empty_descriptions | PASS |

**30/30 PASS**

---

#### `test_critic_real.py` — decomposition_critic_node with real LLM

Three scenarios, each with its own fixture.

**Good path:** `"Learn Python basics in 2 weeks"` using the prompt's own 9-task worked-example plan.
**Flawed A:** single vague task `"Do everything"` for `"Write a research paper on climate change"`.
**Flawed B:** design → implement → backend → test → submit, all in one `shuffle:yes` group.

| ID | Test Function | Result |
|----|---------------|--------|
| T-C01 | test_c01_good_has_passed_key | PASS |
| T-C02 | test_c02_good_passed_is_bool | PASS |
| T-C03 | test_c03_good_has_issues_key | PASS |
| T-C04 | test_c04_good_issues_is_list | PASS |
| T-C05 | test_c05_good_has_revision_instruction_key | PASS |
| T-C06 | test_c06_good_revision_instruction_is_string | PASS |
| T-C07 | test_c07_good_issues_are_advisory_only | PASS |
| T-C08 | test_c08_good_each_issue_has_severity | PASS |
| T-C09 | test_c09_good_each_issue_has_subtask | PASS |
| T-C10 | test_c10_good_each_issue_has_issue_field | PASS |
| T-C11 | test_c11_good_each_issue_has_suggestion | PASS |
| T-C12 | test_c12_good_revision_instruction_not_excessively_long | PASS |
| T-C13 | test_c13_mega_has_passed_key | PASS |
| T-C14 | test_c14_mega_has_issues_key | PASS |
| T-C15 | test_c15_mega_has_revision_instruction_key | PASS |
| T-C16 | test_c16_mega_critic_flags_vague_task | PASS |
| T-C17 | test_c17_mega_issues_nonempty | PASS |
| T-C18 | test_c18_mega_revision_instruction_nonempty | PASS |
| T-C19 | test_c19_mega_each_issue_has_all_fields | PASS |
| T-C20 | test_c20_mega_issue_descriptions_nonempty | PASS |
| T-C21 | test_c21_mega_suggestion_fields_are_strings | PASS |
| T-C22 | test_c22_groups_has_passed_key | PASS |
| T-C23 | test_c23_groups_has_issues_key | PASS |
| T-C24 | test_c24_groups_has_revision_instruction_key | PASS |
| T-C25 | test_c25_groups_critic_flags_bad_ordering | PASS |
| T-C26 | test_c26_groups_issues_nonempty | PASS |
| T-C27 | test_c27_groups_each_issue_has_all_fields | PASS |
| T-C28 | test_c28_groups_passed_is_false | PASS |
| T-C29 | test_c29_groups_revision_instruction_nonempty | PASS |

**29/29 PASS**

---

#### `test_rationale_real.py` — generate_rationales_node with real LLM

Goal: `"Learn SQL basics in one week"` with hardcoded `SIMPLE_SUBTASKS` and three pre-built
candidate schedules. One fixture (`real_rationales`) makes 3 LLM calls (one per strategy).

| ID | Test Function | Result |
|----|---------------|--------|
| T-R01 | test_r01_result_has_rationales_key | PASS |
| T-R02 | test_r02_rationales_value_is_dict | PASS |
| T-R03 | test_r03_all_three_strategy_keys_present | PASS |
| T-R04 | test_r04_deadline_first_rationale_nonempty | PASS |
| T-R05 | test_r05_min_fragmentation_rationale_nonempty | PASS |
| T-R06 | test_r06_energy_aware_rationale_nonempty | PASS |
| T-R07 | test_r07_all_three_rationales_are_distinct | PASS |
| T-R08 | test_r08_rationales_within_word_limit | PASS |
| T-R09 | test_r09_each_rationale_has_multiple_words | PASS |
| T-R10 | test_r10_no_traceback_in_rationales | PASS |
| T-R11 | test_r11_no_provider_error_in_rationales | PASS |
| T-R12 | test_r12_no_rationale_matches_mock_fallback | PASS |
| T-R13 | test_r13_no_rationale_starts_with_error | PASS |
| T-R14 | test_r14_no_rationale_is_json_blob | PASS |
| T-R15 | test_r15_no_rationale_is_only_whitespace | PASS |
| T-R16 | test_r16_deadline_first_contains_sentence_end | PASS |
| T-R17 | test_r17_min_fragmentation_contains_sentence_end | PASS |
| T-R18 | test_r18_energy_aware_contains_sentence_end | PASS |
| T-R19 | test_r19_each_rationale_under_2000_chars | PASS |
| T-R20 | test_r20_combined_rationales_under_6000_chars | PASS |
| T-R21 | test_r21_rationale_dict_has_exactly_three_keys | PASS |
| T-R22 | test_r22_rationale_dict_keys_match_expected_set | PASS |
| T-R23 | test_r23_result_has_debug_trace_key | PASS |
| T-R24 | test_r24_deadline_first_word_count_at_least_10 | PASS |
| T-R25 | test_r25_energy_aware_word_count_at_least_10 | PASS |

**25/25 PASS**

---

#### `test_revision_real.py` — revise_decomposition_node with real LLM

Input: single vague task `"Do everything"` + hardcoded critic issues and revision instruction.
One fixture (`real_revision`) makes 1 LLM call shared by all 15 tests.

| ID | Test Function | Result |
|----|---------------|--------|
| T-V01 | test_v01_revision_result_has_subtasks_key | PASS |
| T-V02 | test_v02_revised_subtasks_is_nonempty_list | PASS |
| T-V03 | test_v03_revised_subtask_count_in_range | PASS |
| T-V04 | test_v04_revised_count_greater_than_original | PASS |
| T-V05 | test_v05_revised_all_names_nonempty | PASS |
| T-V06 | test_v06_revised_all_descriptions_are_strings | PASS |
| T-V07 | test_v07_revised_durations_valid | PASS |
| T-V08 | test_v08_revised_at_least_one_group_tag | PASS |
| T-V09 | test_v09_revised_at_least_one_complexity_tag | PASS |
| T-V10 | test_v10_vague_task_name_not_in_revised_output | PASS |
| T-V11 | test_v11_result_has_decomposition_revised_key | PASS |
| T-V12 | test_v12_decomposition_revised_is_true | PASS |
| T-V13 | test_v13_result_has_revision_count_key | PASS |
| T-V14 | test_v14_revision_count_is_at_least_one | PASS |
| T-V15 | test_v15_revised_task_names_are_unique | PASS |

**15/15 PASS**

---

### Distribution & Coverage

| File | Tests | Source module under test | Fixtures / LLM calls |
|------|-------|--------------------------|----------------------|
| test_decompose_real.py (T-D01–T-D30) | 30 | nodes/decompose_goal.py | 2 fixtures / 2 calls |
| test_critic_real.py (T-C01–T-C29) | 29 | nodes/decomposition_review.py | 3 fixtures / 3 calls |
| test_rationale_real.py (T-R01–T-R25) | 25 | nodes/generate_rationales.py | 1 fixture / 3 calls |
| test_revision_real.py (T-V01–T-V15) | 15 | nodes/decomposition_review.py | 1 fixture / 1 call |
| **Total** | **99** | | **7 fixtures / 9 calls** |

---

### What Is NOT Tested Here

| Concern | Not covered because |
|---------|---------------------|
| Exact LLM wording | Non-deterministic by design; exact strings would make the suite brittle |
| LLM latency / cost | Not tracked here; monitor via provider dashboards |
| Concurrent calls | Session-scoped fixtures run sequentially; concurrency is a deployment concern |
| `write_events` end-to-end | Calendar writes require live credentials; tested in programmatic suite with mocks |

---

*Last run: 2026-05-09 — 99/99 PASS, 0 failures, ~113 s.*
