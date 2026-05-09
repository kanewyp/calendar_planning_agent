# docs/PIPELINE_UNIT_TEST_TRACE.md

## Pipeline Unit Test Trace

### What This Suite Actually Tests

`tests/pipeline_unit/` contains **pipeline unit tests** — not LLM evaluation tests.

Every test in this suite runs in under 2 seconds total because **no real LLM is called**.
All calls to `call_llm_json` and `call_llm_text` are intercepted at the module boundary
using `unittest.mock.patch`, replaced with hardcoded return values. For example:

```python
with patch("src.orchestration.nodes.generate_rationales.call_llm_text",
           side_effect=["Rationale A.", "Rationale B.", "Rationale C."]):
    result = generate_rationales_node(state)
assert "Rationale A." in result["candidate_rationales"]["deadline_first"]
```

This means these tests prove **pipeline correctness** — that the orchestration code
correctly routes, stores, parses, and formats whatever string an LLM returns — not that
the LLM produces good strings.

### What Is NOT Tested Here

| Concern | Not tested because |
|---------|-------------------|
| Does Claude decompose goals sensibly? | No real LLM call is made |
| Do complexity tags reflect real task difficulty? | Mock returns pre-written tags |
| Are rationales actually readable and relevant? | Mock returns pre-written strings |
| Does the prompt elicit well-structured JSON? | Prompt is never sent anywhere |
| Is the LLM output non-deterministic / hallucinated? | Mocked output is always identical |

To test those concerns you need the **LLM integration suite** in `tests/llm_integration/`.
See `docs/LLM_INTEGRATION_TEST_TRACE.md` for its full inventory and design rationale.

```bash
CALENDAR_MODE=mock .venv/bin/pytest tests/llm_integration/ -v -m integration -s
```

### Suite Naming — Why "Pipeline Unit"

| Rejected name | Reason |
|---------------|--------|
| `LLM_BEHAVIOR_TEST_TRACE.md` | Implies the LLM itself is under test — it is not |
| `LLM_OUTPUT_VALIDATION_TRACE.md` | Same problem; the mock produces the output, not the LLM |
| `FUNCTIONAL_TEST_TRACE.md` | Functional testing implies end-to-end; this is unit-level |
| **`PIPELINE_UNIT_TEST_TRACE.md`** ✓ | Accurate: tests the pipeline logic with mocked LLM-shaped inputs |

---

### Execution Summary

**Run date:** 2026-05-01
**Branch:** `test/unit-test`
**Command:** `CALENDAR_MODE=mock .venv/bin/pytest tests/pipeline_unit/ -v`
**Python:** 3.13.5 | **pytest:** 8.4.2 | **Duration:** ~1 s

| Result | Count |
|--------|-------|
| Passed | 100 |
| Failed | 0 |
| **Total collected** | **100** |

> 99 labelled tests (T01–T99) + 1 companion assertion in T90 = 100 collected items.

#### One Post-Run Fix (T29)

T29 expected three 30-min tasks to land in three separate 60-min slots. The scheduler
correctly packs them back-to-back in the first slot instead. Fix: changed task duration
to 60 min so each exactly fills one slot. All runs after the fix: 100/100.

---

### Design Assumptions Fixed Before Writing (8 total)

| # | Test | Issue | Fix |
|---|------|-------|-----|
| 1 | T29 | 30-min tasks expected in separate slots; algorithm packs back-to-back | Changed to 60-min tasks |
| 2 | T31 | Task B expected at 09:00 but `min_allowed_start` advances to 12:30 | Assert B.start == 12:30 |
| 3 | T45 | Untagged task expected to use largest slot; fallback uses earliest | Added structural tags |
| 4 | T48 | Same as T45 | Same fix |
| 5 | T49 | Expected strategies to diverge; both use earliest-slot without tags | Added structural tags |
| 6 | T60 | Two sub-scenarios counted as separate tests (would exceed 99) | Merged into one function |
| 7 | T64 | High-complexity task not guaranteed first without `shuffle:yes` | Set both tasks `shuffle:yes` |
| 8 | T68 | Evening slot captured task via `energy_scores.get(period, 2)` default | Specified all 3 energy periods; excluded evening slots |

---

### Full Test Results — T01–T99

| T# | File | Class | Test Function | Result |
|----|------|-------|---------------|--------|
| T01 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_learn_python_env_and_first_program_in_separate_groups | PASS |
| T02 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_plan_wedding_venue_before_invitations_in_different_groups | PASS |
| T03 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_dissertation_complexity_tags_match_duration_bands | PASS |
| T04 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_mobile_app_seq_tags_used_for_ordered_steps | PASS |
| T05 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_learn_react_shuffle_yes_only_for_genuine_peers | PASS |
| T06 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_study_for_exam_all_tasks_have_required_structural_tags | PASS |
| T07 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_conference_no_low_complexity_task_over_45_min | PASS |
| T08 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_startup_phases_appear_in_logical_sequence | PASS |
| T09 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_etl_pipeline_phases_in_separate_groups | PASS |
| T10 | test_decomposition_subtasks.py | TestGoalSubtaskFixtures | test_write_novel_vague_goal_produces_multiple_concrete_tasks | PASS |
| T11 | test_decomposition_subtasks.py | TestDecompositionCritic | test_passes_well_structured_plan | PASS |
| T12 | test_decomposition_subtasks.py | TestDecompositionCritic | test_flags_oversized_vague_task | PASS |
| T13 | test_decomposition_subtasks.py | TestDecompositionCritic | test_flags_missing_prerequisite | PASS |
| T14 | test_decomposition_subtasks.py | TestDecompositionCritic | test_flags_unrealistic_duration_for_complexity | PASS |
| T15 | test_decomposition_subtasks.py | TestDecompositionCritic | test_flags_prerequisite_tasks_wrongly_in_same_group | PASS |
| T16 | test_decomposition_subtasks.py | TestDecompositionCritic | test_flags_tasks_too_abstract_to_calendar | PASS |
| T17 | test_decomposition_subtasks.py | TestDecompositionCritic | test_flags_missing_delivery_or_review_phase | PASS |
| T18 | test_decomposition_subtasks.py | TestDecompositionCritic | test_passes_borderline_decomposition_without_false_positives | PASS |
| T19 | test_decomposition_subtasks.py | TestDecompositionCritic | test_result_always_has_required_fields | PASS |
| T20 | test_decomposition_subtasks.py | TestDecompositionCritic | test_normalizes_malformed_issues_gracefully | PASS |
| T21 | test_decomposition_subtasks.py | TestDecompositionReviser | test_revise_splits_oversized_task_into_two | PASS |
| T22 | test_decomposition_subtasks.py | TestDecompositionReviser | test_revise_inserts_missing_prerequisite_before_dependent | PASS |
| T23 | test_decomposition_subtasks.py | TestDecompositionReviser | test_revise_corrects_group_assignment_for_dependent_tasks | PASS |
| T24 | test_decomposition_subtasks.py | TestDecompositionReviser | test_revised_output_all_tasks_have_structural_tags | PASS |
| T25 | test_decomposition_subtasks.py | TestDecompositionReviser | test_revise_preserves_tasks_not_mentioned_in_critique | PASS |
| T26 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_single_task_placed_in_first_available_slot | PASS |
| T27 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_task_placed_in_earlier_slot_not_later | PASS |
| T28 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_second_task_cannot_precede_first_task_end | PASS |
| T29 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_three_tasks_fill_slots_front_to_back | PASS |
| T30 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_task_cannot_be_placed_in_later_slot_when_earlier_fits | PASS |
| T31 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_shuffle_yes_larger_task_lands_in_later_slot_smaller_task_follows | PASS |
| T32 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_no_chronological_inversion_in_output | PASS |
| T33 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_group_a_tasks_precede_group_b_tasks | PASS |
| T34 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_seq_tagged_tasks_not_reordered | PASS |
| T35 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_shuffle_no_tasks_preserve_llm_order | PASS |
| T36 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_break_minutes_creates_gap_between_events | PASS |
| T37 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_zero_break_minutes_allows_adjacent_events | PASS |
| T38 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_empty_subtasks_returns_empty | PASS |
| T39 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_empty_free_slots_returns_empty | PASS |
| T40 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_oversized_task_skipped_others_placed | PASS |
| T41 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_all_tasks_placed_when_capacity_exactly_matches | PASS |
| T42 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_no_structural_tags_preserves_llm_order | PASS |
| T43 | test_heuristic_deadline_first.py | TestDeadlineFirst | test_output_events_fall_within_free_slots | PASS |
| T44 | test_heuristic_fragmentation.py | TestMinFragmentation | test_single_task_placed_when_only_large_slot_fits | PASS |
| T45 | test_heuristic_fragmentation.py | TestMinFragmentation | test_larger_slot_preferred_when_both_fit_same_day | PASS |
| T46 | test_heuristic_fragmentation.py | TestMinFragmentation | test_two_tasks_longer_first_gets_biggest_slot | PASS |
| T47 | test_heuristic_fragmentation.py | TestMinFragmentation | test_advances_to_next_day_only_when_day1_has_no_fitting_slot | PASS |
| T48 | test_heuristic_fragmentation.py | TestMinFragmentation | test_large_slot_preferred_over_small_slot_same_day | PASS |
| T49 | test_heuristic_fragmentation.py | TestMinFragmentation | test_fragmentation_and_deadline_first_diverge_on_slot_selection | PASS |
| T50 | test_heuristic_fragmentation.py | TestMinFragmentation | test_shuffle_run_sorted_longest_first_before_slot_selection | PASS |
| T51 | test_heuristic_fragmentation.py | TestMinFragmentation | test_no_structural_tags_fallback_matches_deadline_first | PASS |
| T52 | test_heuristic_fragmentation.py | TestMinFragmentation | test_group_ordering_respected_fragmentation | PASS |
| T53 | test_heuristic_fragmentation.py | TestMinFragmentation | test_leftover_slot_portions_returned_to_pool | PASS |
| T54 | test_heuristic_fragmentation.py | TestMinFragmentation | test_empty_subtasks_returns_empty_fragmentation | PASS |
| T55 | test_heuristic_fragmentation.py | TestMinFragmentation | test_task_larger_than_all_slots_skipped_fragmentation | PASS |
| T56 | test_heuristic_fragmentation.py | TestMinFragmentation | test_output_chronologically_sorted_fragmentation | PASS |
| T57 | test_heuristic_fragmentation.py | TestMinFragmentation | test_output_events_within_free_slots_fragmentation | PASS |
| T58 | test_heuristic_fragmentation.py | TestMinFragmentation | test_break_minutes_applied_fragmentation | PASS |
| T59 | test_heuristic_energy_aware.py | TestEnergyAware | test_high_complexity_task_placed_in_morning_high_energy_slot | PASS |
| T60 | test_heuristic_energy_aware.py | TestEnergyAware | test_medium_complexity_task_placed_in_best_energy_slot | PASS |
| T61 | test_heuristic_energy_aware.py | TestEnergyAware | test_low_complexity_task_placed_in_evening_low_energy_slot | PASS |
| T62 | test_heuristic_energy_aware.py | TestEnergyAware | test_high_complexity_not_in_low_energy_slot_when_high_available | PASS |
| T63 | test_heuristic_energy_aware.py | TestEnergyAware | test_medium_complexity_not_in_low_when_medium_available_same_day | PASS |
| T64 | test_heuristic_energy_aware.py | TestEnergyAware | test_easy_task_does_not_consume_high_energy_slot | PASS |
| T65 | test_heuristic_energy_aware.py | TestEnergyAware | test_custom_energy_profile_routes_task_to_correct_period | PASS |
| T66 | test_heuristic_energy_aware.py | TestEnergyAware | test_best_match_slot_chosen_over_acceptable_match | PASS |
| T67 | test_heuristic_energy_aware.py | TestEnergyAware | test_tie_in_score_diff_broken_by_earliest_start | PASS |
| T68 | test_heuristic_energy_aware.py | TestEnergyAware | test_earliest_day_beats_better_energy_match_on_later_day | PASS |
| T69 | test_heuristic_energy_aware.py | TestEnergyAware | test_task_placed_on_earliest_date_with_any_eligible_slot | PASS |
| T70 | test_heuristic_energy_aware.py | TestEnergyAware | test_dependency_order_preserved_despite_energy_placement | PASS |
| T71 | test_heuristic_energy_aware.py | TestEnergyAware | test_min_allowed_start_prevents_chronological_inversion | PASS |
| T72 | test_heuristic_energy_aware.py | TestEnergyAware | test_shuffle_yes_run_sorted_by_complexity_descending | PASS |
| T73 | test_heuristic_energy_aware.py | TestEnergyAware | test_seq_tags_hard_locked_energy_aware | PASS |
| T74 | test_heuristic_energy_aware.py | TestEnergyAware | test_empty_subtasks_returns_empty_energy_aware | PASS |
| T75 | test_heuristic_energy_aware.py | TestEnergyAware | test_no_fitting_slots_returns_empty_energy_aware | PASS |
| T76 | test_heuristic_energy_aware.py | TestEnergyAware | test_duration_fallback_for_untagged_tasks | PASS |
| T77 | test_rationale_quality.py | TestRationaleQuality | test_deadline_rationale_contains_deadline_keywords | PASS |
| T78 | test_rationale_quality.py | TestRationaleQuality | test_fragmentation_rationale_contains_fragmentation_keywords | PASS |
| T79 | test_rationale_quality.py | TestRationaleQuality | test_energy_rationale_contains_energy_keywords | PASS |
| T80 | test_rationale_quality.py | TestRationaleQuality | test_each_rationale_within_word_limit | PASS |
| T81 | test_rationale_quality.py | TestRationaleQuality | test_rationale_mentions_violations_when_violations_exist | PASS |
| T82 | test_rationale_quality.py | TestRationaleQuality | test_rationale_does_not_inject_violation_text_when_passed | PASS |
| T83 | test_rationale_quality.py | TestRationaleQuality | test_fallback_rationale_used_when_llm_raises | PASS |
| T84 | test_rationale_quality.py | TestRationaleQuality | test_fallback_rationale_includes_event_count | PASS |
| T85 | test_rationale_quality.py | TestRationaleQuality | test_fallback_rationale_includes_violation_info | PASS |
| T86 | test_rationale_quality.py | TestRationaleQuality | test_three_rationales_are_distinct_from_each_other | PASS |
| T87 | test_structural_tags.py | TestTagMap | test_parses_all_four_tag_types | PASS |
| T88 | test_structural_tags.py | TestTagMap | test_empty_when_no_tags | PASS |
| T89 | test_structural_tags.py | TestTagMap | test_last_duplicate_key_wins | PASS |
| T90 | test_structural_tags.py | TestGroupId | test_returns_default_when_no_group_tag | PASS |
| T91 | test_structural_tags.py | TestSeqId | test_seq_id_parses_integer_and_returns_none_when_absent | PASS |
| T92 | test_structural_tags.py | TestShuffleAllowed | test_yes_true_1_all_truthy_and_no_is_false | PASS |
| T93 | test_structural_tags.py | TestComplexityScore | test_explicit_tag_overrides_duration | PASS |
| T94 | test_structural_tags.py | TestComplexityScore | test_duration_fallback_bands | PASS |
| T95 | test_structural_tags.py | TestHasAnyStructuralTags | test_true_when_one_task_is_tagged | PASS |
| T96 | test_structural_tags.py | TestHasAnyStructuralTags | test_false_when_all_tasks_are_plain | PASS |
| T97 | test_structural_tags.py | TestSafeStructuralShuffle | test_preserves_group_order_reorders_within_shufflable_run | PASS |
| T98 | test_structural_tags.py | TestSafeStructuralShuffle | test_seq_prevents_reorder | PASS |
| T99 | test_structural_tags.py | TestSafeStructuralShuffle | test_only_shufflable_runs_are_reordered | PASS |

**99/99 PASS**

---

### Distribution & Coverage

| File | Count | Source module under test |
|------|-------|--------------------------|
| test_decomposition_subtasks.py (T01–T25) | 25 | nodes/decompose_goal.py, nodes/decomposition_review.py |
| test_heuristic_deadline_first.py (T26–T43) | 18 | heuristics/deadline_first.py |
| test_heuristic_fragmentation.py (T44–T58) | 15 | heuristics/minimize_fragmentation.py |
| test_heuristic_energy_aware.py (T59–T76) | 18 | heuristics/energy_aware.py |
| test_rationale_quality.py (T77–T86) | 10 | nodes/generate_rationales.py |
| test_structural_tags.py (T87–T99) | 13 | heuristics/_structural.py |

### Run Commands

```bash
# This suite (no credentials needed, completes in ~1 s)
CALENDAR_MODE=mock .venv/bin/pytest tests/pipeline_unit/ -v

# All non-integration suites (218 tests, ~2 s)
CALENDAR_MODE=mock .venv/bin/pytest tests/ -q --ignore=tests/llm_integration

# Full suite including real LLM calls (243 tests, ~65 s, requires Google ADC credentials)
CALENDAR_MODE=mock .venv/bin/pytest tests/ -q -m integration
```

---

*Last run: 2026-05-09 — 100/100 collected, 99/99 labelled PASS, 0 failures, ~1 s.*
*Real LLM evaluation: `tests/llm_integration/` — 25/25 PASS, ~65 s. See `docs/LLM_INTEGRATION_TEST_TRACE.md`.*
