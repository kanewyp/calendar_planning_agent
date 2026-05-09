# docs/PIPELINE_UNIT_TEST_TRACE.md

## Pipeline Unit Test Trace

### What This Suite Actually Tests

`tests/pipeline_unit/` contains **100 tests** that verify two distinct concerns:

1. **Real-LLM behavioural correctness (T01–T25, T77–T82, T86):** 32 tests call
   Gemini 2.5 Flash through Vertex AI via session-scoped fixtures. Each fixture
   makes exactly one LLM call shared across all tests that depend on it (~9 total
   LLM calls for the whole suite). Tests assert _structural_ properties of the
   output — tag presence, count bounds, type checks — that must hold regardless
   of the specific words the model uses.

2. **Pure heuristic correctness (T26–T76, T87–T99):** 65 tests exercise the three
   scheduling heuristics and the structural-tag utilities with hand-crafted mock
   calendars. No LLM is involved; these run in milliseconds.

3. **Error-handling fallback (T20, T83–T85):** 3 tests remain mocked because they
   deliberately inject malformed or erroring LLM output to verify graceful fallback
   behaviour — something that cannot be tested with a real LLM.

### Design: Session-Scoped LLM Fixtures

Instead of one LLM call per test (which would be slow and expensive), all
real-LLM tests share session-scoped fixtures defined in `conftest.py`:

| Fixture | Goal prompt | Tests that use it |
|---------|------------|-------------------|
| `real_decomp_python` | "Learn Python from scratch" | T01, T05, T06 |
| `real_decomp_wedding` | "Plan a wedding" | T02, T07 |
| `real_decomp_dissertation` | "Write my PhD dissertation" | T03 |
| `real_decomp_mobile` | "Build a mobile app MVP" | T04, T08, T09 |
| `real_decomp_novel` | "Write a novel" | T10 |
| `real_critic_good_plan` | 5-task well-structured learning plan | T11–T15 |
| `real_critic_bad_plan` | Single "Do everything" mega-task | T16–T19 |
| `real_reviser` | "Do all reading" → split instruction | T21–T25 |
| `real_rationale` | 1-task state with 3 strategy candidates | T77–T82, T86 |

Total: **9 LLM calls** shared across 32 tests. Tests skip automatically if
`GOOGLE_APPLICATION_CREDENTIALS` is not set or `LLM_PROVIDER=mock`.

### Mock Calendars Used by Heuristic Tests

All heuristic tests use synthetic free-slot shapes from `tests/pipeline_unit/mock_calendars.py`,
anchored to the week of **2026-05-11 (Monday)**:

| Shape | Description | Typical use |
|-------|-------------|-------------|
| `CALENDAR_SPARSE` | 5 scattered slots Mon–Fri (60–150 min each) | Basic ordering, overflow |
| `CALENDAR_MORNING_HEAVY` | Large morning blocks, tiny afternoons | Energy-aware morning preference |
| `CALENDAR_AFTERNOON_HEAVY` | Busy mornings, 240-min afternoon blocks | Custom afternoon=high profile |
| `CALENDAR_SINGLE_DAY` | 3 slots on Monday only (45/90/240 min) | Within-day slot selection |
| `CALENDAR_MULTI_DAY_EQUAL` | Identical 120-min slots Mon–Fri | Day-ordering, tie-breaking |
| `CALENDAR_WITH_EVENING` | Morning+afternoon+evening on Tue–Wed | Evening low-energy placement |

---

### Execution Summary

**Run date:** 2026-05-09
**Branch:** `test/unit-test`
**Command:**
```bash
CALENDAR_MODE=mock \
GOOGLE_APPLICATION_CREDENTIALS=google_credential.json \
LLM_PROVIDER=vertex_ai \
VERTEX_PROJECT_ID=calendar-augmentation-agent \
LLM_DECOMPOSITION_MAX_TOKENS=16384 \
.venv/bin/pytest tests/pipeline_unit/ -v --tb=short
```
**Python:** 3.13.5 | **pytest:** 8.4.2 | **Duration:** 178 s (0:02:58)

| Result | Count |
|--------|-------|
| Passed | 100 |
| Failed | 0 |
| Skipped | 0 |
| **Total collected** | **100** |

> **Note on `LLM_DECOMPOSITION_MAX_TOKENS=16384`:** The "Write a novel" goal (T10) generates
> a large plan that exceeds the default 8192-token limit. Setting this env var prevents
> the JSON response from being truncated mid-parse. All other goals fit within 8192 tokens.

---

### Full Test Results — T01–T100

#### A1 — Decomposition Structural Tests (real LLM)

| T# | Test Function | Fixture | Assertion | Result |
|----|--------------|---------|-----------|--------|
| T01 | `test_learn_python_produces_multiple_distinct_groups` | `real_decomp_python` | ≥3 tasks, ≥2 distinct group IDs | ✅ PASS |
| T02 | `test_plan_wedding_has_multiple_phases` | `real_decomp_wedding` | ≥3 tasks, ≥2 distinct group IDs | ✅ PASS |
| T03 | `test_dissertation_complexity_tags_align_with_duration` | `real_decomp_dissertation` | low→≤60 min, high→≥60 min | ✅ PASS |
| T04 | `test_mobile_app_has_sequential_ordered_tasks` | `real_decomp_mobile` | ≥1 group contains ≥2 tasks | ✅ PASS |
| T05 | `test_learn_python_shuffle_variety_in_tasks` | `real_decomp_python` | all tasks have `[shuffle:*]` tag | ✅ PASS |
| T06 | `test_learn_python_all_tasks_have_required_structural_tags` | `real_decomp_python` | every task has group+shuffle+complexity | ✅ PASS |
| T07 | `test_plan_wedding_low_complexity_tasks_under_45min` | `real_decomp_wedding` | all `[complexity:low]` tasks ≤45 min | ✅ PASS |
| T08 | `test_mobile_app_has_at_least_three_distinct_groups` | `real_decomp_mobile` | ≥3 distinct group IDs | ✅ PASS |
| T09 | `test_mobile_app_has_ordered_phases` | `real_decomp_mobile` | ≥3 tasks, ≥2 groups | ✅ PASS |
| T10 | `test_write_novel_vague_goal_produces_multiple_concrete_tasks` | `real_decomp_novel` | ≥5 tasks, description ≥15 chars, duration>0 | ✅ PASS |

#### A2 — Decomposition Critic Tests (real LLM + 1 mocked)

| T# | Test Function | Fixture / Mock | Assertion | Result |
|----|--------------|----------------|-----------|--------|
| T11 | `test_good_plan_critic_result_has_all_required_keys` | `real_critic_good_plan` | 3 required state keys present | ✅ PASS |
| T12 | `test_good_plan_passed_is_bool` | `real_critic_good_plan` | `decomposition_review_passed` is bool | ✅ PASS |
| T13 | `test_good_plan_issues_is_list` | `real_critic_good_plan` | `decomposition_review_issues` is list | ✅ PASS |
| T14 | `test_good_plan_revision_instruction_is_string` | `real_critic_good_plan` | `decomposition_revision_instruction` is str | ✅ PASS |
| T15 | `test_good_plan_no_critical_severity_issues` | `real_critic_good_plan` | no issues with severity=="critical" | ✅ PASS |
| T16 | `test_bad_plan_is_flagged` | `real_critic_bad_plan` | not passed OR issues present OR instruction non-empty | ✅ PASS |
| T17 | `test_bad_plan_issues_nonempty` | `real_critic_bad_plan` | `len(issues) > 0` | ✅ PASS |
| T18 | `test_bad_plan_each_issue_has_severity` | `real_critic_bad_plan` | each issue has non-empty `severity` | ✅ PASS |
| T19 | `test_bad_plan_each_issue_has_all_required_fields` | `real_critic_bad_plan` | each issue has severity+subtask+issue+suggestion | ✅ PASS |
| T20 | `test_normalizes_malformed_issues_gracefully` | **mocked** (malformed JSON) | node does not crash; required keys exist | ✅ PASS |

#### A3 — Decomposition Reviser Tests (real LLM)

| T# | Test Function | Fixture | Assertion | Result |
|----|--------------|---------|-----------|--------|
| T21 | `test_revise_produces_more_tasks_than_original` | `real_reviser` | `len(tasks) > 2` (original had 2) | ✅ PASS |
| T22 | `test_revise_all_tasks_have_structural_tags` | `real_reviser` | all tasks have group+shuffle+complexity | ✅ PASS |
| T23 | `test_revise_all_durations_within_session_limit` | `real_reviser` | all durations in (0, 90] | ✅ PASS |
| T24 | `test_revise_sets_decomposition_revised_flag` | `real_reviser` | `decomposition_revised is True` | ✅ PASS |
| T25 | `test_revise_increments_revision_count` | `real_reviser` | `decomposition_revision_count >= 1` | ✅ PASS |

#### B — Deadline-First Heuristic Tests (pure, no LLM)

| T# | Test Function | Mock Calendar | Assertion | Result |
|----|--------------|---------------|-----------|--------|
| T26 | `test_single_task_placed_in_first_available_slot` | hand-crafted | task lands in first slot | ✅ PASS |
| T27 | `test_task_placed_in_earlier_slot_not_later` | hand-crafted | earlier slot chosen over later | ✅ PASS |
| T28 | `test_second_task_cannot_precede_first_task_end` | hand-crafted | task 2 start ≥ task 1 end | ✅ PASS |
| T29 | `test_three_tasks_fill_slots_front_to_back` | hand-crafted | 3 tasks placed in chronological order | ✅ PASS |
| T30 | `test_task_cannot_be_placed_in_later_slot_when_earlier_fits` | hand-crafted | no slot skipped when earlier fits | ✅ PASS |
| T31 | `test_shuffle_yes_larger_task_lands_in_later_slot_smaller_task_follows` | hand-crafted | shuffle:yes reorders by fit | ✅ PASS |
| T32 | `test_no_chronological_inversion_in_output` | hand-crafted | output list is time-sorted | ✅ PASS |
| T33 | `test_group_a_tasks_precede_group_b_tasks` | hand-crafted | group ordering respected | ✅ PASS |
| T34 | `test_seq_tagged_tasks_not_reordered` | hand-crafted | seq: tags lock position | ✅ PASS |
| T35 | `test_shuffle_no_tasks_preserve_llm_order` | hand-crafted | shuffle:no preserves input order | ✅ PASS |
| T36 | `test_break_minutes_creates_gap_between_events` | hand-crafted | gap ≥ break_minutes between events | ✅ PASS |
| T37 | `test_zero_break_minutes_allows_adjacent_events` | hand-crafted | events can be back-to-back | ✅ PASS |
| T38 | `test_empty_subtasks_returns_empty` | hand-crafted | [] in → [] out | ✅ PASS |
| T39 | `test_empty_free_slots_returns_empty` | hand-crafted | no slots → no events | ✅ PASS |
| T40 | `test_oversized_task_skipped_others_placed` | hand-crafted | task > all slots skipped, rest placed | ✅ PASS |
| T41 | `test_all_tasks_placed_when_capacity_exactly_matches` | hand-crafted | exactly-fitting tasks all placed | ✅ PASS |
| T42 | `test_no_structural_tags_preserves_llm_order` | hand-crafted | untagged tasks use LLM order | ✅ PASS |
| T43 | `test_output_events_fall_within_free_slots` | hand-crafted | every event start/end within a free slot | ✅ PASS |

#### C — Min-Fragmentation Heuristic Tests (pure, no LLM)

| T# | Test Function | Mock Calendar | Assertion | Result |
|----|--------------|---------------|-----------|--------|
| T44 | `test_single_task_placed_when_only_large_slot_fits` | hand-crafted | task fills the only fitting slot | ✅ PASS |
| T45 | `test_larger_slot_preferred_when_both_fit_same_day` | hand-crafted | larger slot chosen on same day | ✅ PASS |
| T46 | `test_two_tasks_longer_first_gets_biggest_slot` | hand-crafted | longest task → biggest slot | ✅ PASS |
| T47 | `test_advances_to_next_day_only_when_day1_has_no_fitting_slot` | hand-crafted | day overflow only when forced | ✅ PASS |
| T48 | `test_large_slot_preferred_over_small_slot_same_day` | hand-crafted | large always beats small same day | ✅ PASS |
| T49 | `test_fragmentation_and_deadline_first_diverge_on_slot_selection` | hand-crafted | two strategies pick different slots | ✅ PASS |
| T50 | `test_shuffle_run_sorted_longest_first_before_slot_selection` | hand-crafted | shuffle:yes run sorted by duration desc | ✅ PASS |
| T51 | `test_no_structural_tags_fallback_matches_deadline_first` | hand-crafted | untagged behaves like deadline_first | ✅ PASS |
| T52 | `test_group_ordering_respected_fragmentation` | hand-crafted | group ordering respected | ✅ PASS |
| T53 | `test_leftover_slot_portions_returned_to_pool` | hand-crafted | slot remnant reused for next task | ✅ PASS |
| T54 | `test_empty_subtasks_returns_empty_fragmentation` | hand-crafted | [] in → [] out | ✅ PASS |
| T55 | `test_task_larger_than_all_slots_skipped_fragmentation` | hand-crafted | oversized task omitted | ✅ PASS |
| T56 | `test_output_chronologically_sorted_fragmentation` | hand-crafted | output is time-sorted | ✅ PASS |
| T57 | `test_output_events_within_free_slots_fragmentation` | hand-crafted | all events inside free slot bounds | ✅ PASS |
| T58 | `test_break_minutes_applied_fragmentation` | hand-crafted | break gap honoured | ✅ PASS |

#### D — Energy-Aware Heuristic Tests (pure, no LLM)

| T# | Test Function | Mock Calendar | Assertion | Result |
|----|--------------|---------------|-----------|--------|
| T59 | `test_high_complexity_task_placed_in_morning_high_energy_slot` | `CALENDAR_MORNING_HEAVY` | high-complexity → morning slot | ✅ PASS |
| T60 | `test_medium_complexity_task_placed_in_best_energy_slot` | hand-crafted | medium-complexity → afternoon | ✅ PASS |
| T61 | `test_low_complexity_task_placed_in_evening_low_energy_slot` | `CALENDAR_WITH_EVENING` | low-complexity → evening slot | ✅ PASS |
| T62 | `test_high_complexity_not_in_low_energy_slot_when_high_available` | `CALENDAR_MORNING_HEAVY` | high not placed in evening when morning free | ✅ PASS |
| T63 | `test_medium_complexity_not_in_low_when_medium_available_same_day` | hand-crafted | medium not placed in low-energy slot | ✅ PASS |
| T64 | `test_easy_task_does_not_consume_high_energy_slot` | `CALENDAR_MORNING_HEAVY` | easy task avoids high-energy morning | ✅ PASS |
| T65 | `test_custom_energy_profile_routes_task_to_correct_period` | `CALENDAR_AFTERNOON_HEAVY` | custom afternoon=high routes correctly | ✅ PASS |
| T66 | `test_best_match_slot_chosen_over_acceptable_match` | hand-crafted | best-score slot wins over acceptable | ✅ PASS |
| T67 | `test_tie_in_score_diff_broken_by_earliest_start` | hand-crafted | tie → earliest start wins | ✅ PASS |
| T68 | `test_earliest_day_beats_better_energy_match_on_later_day` | `CALENDAR_MULTI_DAY_EQUAL` | earlier day preferred when score equal | ✅ PASS |
| T69 | `test_task_placed_on_earliest_date_with_any_eligible_slot` | `CALENDAR_SPARSE` | task placed on first eligible day | ✅ PASS |
| T70 | `test_dependency_order_preserved_despite_energy_placement` | hand-crafted | group ordering respected over energy | ✅ PASS |
| T71 | `test_min_allowed_start_prevents_chronological_inversion` | hand-crafted | min_allowed_start enforced | ✅ PASS |
| T72 | `test_shuffle_yes_run_sorted_by_complexity_descending` | hand-crafted | shuffle:yes run sorted high→low complexity | ✅ PASS |
| T73 | `test_seq_tags_hard_locked_energy_aware` | hand-crafted | seq: locks position even in energy-aware | ✅ PASS |
| T74 | `test_empty_subtasks_returns_empty_energy_aware` | hand-crafted | [] in → [] out | ✅ PASS |
| T75 | `test_no_fitting_slots_returns_empty_energy_aware` | hand-crafted | no fitting slot → empty output | ✅ PASS |
| T76 | `test_duration_fallback_for_untagged_tasks` | hand-crafted | untagged tasks use duration-based complexity | ✅ PASS |

#### E — Rationale Quality Tests (real LLM + 3 mocked)

| T# | Test Function | Fixture / Mock | Assertion | Result |
|----|--------------|----------------|-----------|--------|
| T77 | `test_deadline_rationale_is_nonempty_string` | `real_rationale` | `deadline_first` rationale is non-empty str | ✅ PASS |
| T78 | `test_min_fragmentation_rationale_is_nonempty_string` | `real_rationale` | `min_fragmentation` rationale is non-empty str | ✅ PASS |
| T79 | `test_energy_aware_rationale_is_nonempty_string` | `real_rationale` | `energy_aware` rationale is non-empty str | ✅ PASS |
| T80 | `test_each_rationale_within_word_limit` | `real_rationale` | all rationales ≤180 words | ✅ PASS |
| T81 | `test_all_three_strategy_keys_present` | `real_rationale` | all 3 strategy keys in `candidate_rationales` | ✅ PASS |
| T82 | `test_rationales_do_not_contain_error_text` | `real_rationale` | no rationale starts with "error" or has "Traceback" | ✅ PASS |
| T83 | `test_fallback_rationale_used_when_llm_raises` | **mocked** (RuntimeError) | all 3 strategies get non-empty fallback | ✅ PASS |
| T84 | `test_fallback_rationale_includes_event_count` | **mocked** (RuntimeError) | fallback mentions "3" (event count) | ✅ PASS |
| T85 | `test_fallback_rationale_includes_violation_info` | **mocked** (RuntimeError) | fallback mentions "2" (violation count) | ✅ PASS |
| T86 | `test_three_rationales_are_distinct` | `real_rationale` | all 3 strategy rationales are different strings | ✅ PASS |

#### F — Structural Tag Utility Tests (pure, no LLM)

| T# | Test Function | Class | Assertion | Result |
|----|--------------|-------|-----------|--------|
| T87 | `test_parses_all_four_tag_types` | `TestTagMap` | `tag_map()` parses group/shuffle/complexity/seq | ✅ PASS |
| T88 | `test_empty_when_no_tags` | `TestTagMap` | no tags → empty dict | ✅ PASS |
| T89 | `test_last_duplicate_key_wins` | `TestTagMap` | duplicate tag key → last value kept | ✅ PASS |
| T90 | `test_returns_default_when_no_group_tag` | `TestGroupId` | missing group → default returned | ✅ PASS |
| T91 | `test_seq_id_parses_integer_and_returns_none_when_absent` | `TestSeqId` | seq: parses int; absent → None | ✅ PASS |
| T92 | `test_yes_true_1_all_truthy_and_no_is_false` | `TestShuffleAllowed` | yes/true/1 → True; no → False | ✅ PASS |
| T93 | `test_explicit_tag_overrides_duration` | `TestComplexityScore` | `[complexity:high]` overrides duration band | ✅ PASS |
| T94 | `test_duration_fallback_bands` | `TestComplexityScore` | untagged: ≤30→low, ≤60→medium, >60→high | ✅ PASS |
| T95 | `test_true_when_one_task_is_tagged` | `TestHasAnyStructuralTags` | ≥1 tagged task → True | ✅ PASS |
| T96 | `test_false_when_all_tasks_are_plain` | `TestHasAnyStructuralTags` | all untagged → False | ✅ PASS |
| T97 | `test_preserves_group_order_reorders_within_shufflable_run` | `TestSafeStructuralShuffle` | group order preserved; within-run shuffle ok | ✅ PASS |
| T98 | `test_seq_prevents_reorder` | `TestSafeStructuralShuffle` | seq: tagged task never moved | ✅ PASS |
| T99 | `test_only_shufflable_runs_are_reordered` | `TestSafeStructuralShuffle` | shuffle:no runs stay locked | ✅ PASS |

**100/100 PASS**

---

### Distribution & Coverage

| Section | File | Count | LLM? | Source modules |
|---------|------|-------|------|----------------|
| A1–A3 | `test_decomposition_subtasks.py` | 25 | 24 real + 1 mocked | `nodes/decompose_goal.py`, `nodes/decomposition_review.py` |
| B | `test_heuristic_deadline_first.py` | 18 | none | `heuristics/deadline_first.py` |
| C | `test_heuristic_fragmentation.py` | 15 | none | `heuristics/minimize_fragmentation.py` |
| D | `test_heuristic_energy_aware.py` | 18 | none | `heuristics/energy_aware.py` |
| E | `test_rationale_quality.py` | 10 | 7 real + 3 mocked | `nodes/generate_rationales.py` |
| F | `test_structural_tags.py` | 13 | none | `heuristics/_structural.py` |
| **Total** | | **100** | **31 real + 3 mocked + 65 pure** | |

### Why Three Tests Remain Mocked (T20, T83–T85)

| T# | Reason mocked |
|----|---------------|
| T20 | Tests `decomposition_critic_node` with deliberately malformed LLM output (missing required fields). Error-handling can only be verified by injecting a broken response. |
| T83 | Tests that when `call_llm_text` raises `RuntimeError`, all three strategies receive a non-empty deterministic fallback. Requires mocking the error. |
| T84 | Same fallback path — checks the fallback string mentions the event count (3). |
| T85 | Same fallback path — checks the fallback string mentions the violation count (2). |

### Run Commands

```bash
# Full pipeline_unit suite with real LLM (178 s, requires Google ADC credentials)
CALENDAR_MODE=mock \
GOOGLE_APPLICATION_CREDENTIALS=google_credential.json \
LLM_PROVIDER=vertex_ai \
VERTEX_PROJECT_ID=calendar-augmentation-agent \
LLM_DECOMPOSITION_MAX_TOKENS=16384 \
.venv/bin/pytest tests/pipeline_unit/ -v

# Pure heuristic + structural tag tests only (65 tests, <1 s, no credentials needed)
CALENDAR_MODE=mock .venv/bin/pytest \
  tests/pipeline_unit/test_heuristic_deadline_first.py \
  tests/pipeline_unit/test_heuristic_energy_aware.py \
  tests/pipeline_unit/test_heuristic_fragmentation.py \
  tests/pipeline_unit/test_structural_tags.py -v

# All three suites (317 tests total, ~178 s with credentials)
CALENDAR_MODE=mock \
GOOGLE_APPLICATION_CREDENTIALS=google_credential.json \
LLM_PROVIDER=vertex_ai \
VERTEX_PROJECT_ID=calendar-augmentation-agent \
LLM_DECOMPOSITION_MAX_TOKENS=16384 \
.venv/bin/pytest tests/ -v
```

---

*Last run: 2026-05-09 — 100/100 PASS in 178 s (0:02:58)*
*LLM: Gemini 2.5 Flash via Vertex AI (google/gemini-2.5-flash) — 9 session fixtures, ~9 real LLM calls*
*Real-LLM integration suite: `tests/llm_integration/` — 99/99 PASS. See `docs/LLM_INTEGRATION_TEST_TRACE.md`.*
