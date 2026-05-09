# =============================================================================
# tests/pipeline_unit/test_structural_tags.py — T87–T99
# =============================================================================
# Tests for the pure helpers in src/orchestration/heuristics/_structural.py.
# No mocking required — all functions are deterministic pure Python.
#
# Functions under test:
#   tag_map, group_id, seq_id, shuffle_allowed, complexity_score,
#   has_any_structural_tags, safe_structural_shuffle
# =============================================================================

from __future__ import annotations

import pytest

from src.orchestration.heuristics._structural import (
    COMPLEXITY_SCORE,
    complexity_score,
    group_id,
    has_any_structural_tags,
    safe_structural_shuffle,
    seq_id,
    shuffle_allowed,
    tag_map,
)
from tests.pipeline_unit.conftest import subtask, tagged_subtask


# =============================================================================
# T87–T99
# =============================================================================


class TestTagMap:

    # T87
    def test_parses_all_four_tag_types(self):
        """T87: tag_map extracts group, seq, shuffle, and complexity from one subtask."""
        task = subtask(
            "Design the schema",
            "[group:alpha] [seq:2] [shuffle:yes] [complexity:high] Full ER diagram.",
            90,
        )
        result = tag_map(task)
        assert result == {
            "group": "alpha",
            "seq": "2",
            "shuffle": "yes",
            "complexity": "high",
        }

    # T88
    def test_empty_when_no_tags(self):
        """T88: plain description with no [key:value] tokens returns empty dict."""
        task = subtask("Task A", "Do some work without any bracketed tags here.", 30)
        assert tag_map(task) == {}

    # T89
    def test_last_duplicate_key_wins(self):
        """T89: when the same key appears twice the last value overwrites the first."""
        task = subtask(
            "Task A",
            "[group:first] Some text [group:second] more text.",
            30,
        )
        assert tag_map(task)["group"] == "second"


class TestGroupId:

    # T90
    def test_returns_default_when_no_group_tag(self):
        """T90: group_id() returns 'default' for an untagged subtask."""
        task = subtask("Task A", "No tags here.", 30)
        assert group_id(task) == "default"

    def test_returns_correct_group_when_tagged(self):
        """T90 companion: group_id() returns the exact group value."""
        task = subtask("Task A", "[group:phase2] Description.", 45)
        assert group_id(task) == "phase2"


class TestSeqId:

    # T91
    def test_seq_id_parses_integer_and_returns_none_when_absent(self):
        """T91: seq_id() returns int when present, None when absent."""
        with_seq = subtask("Task A", "[seq:3] Some description.", 30)
        without_seq = subtask("Task B", "[group:g] [shuffle:no] [complexity:low] Desc.", 30)

        assert seq_id(with_seq) == 3
        assert seq_id(without_seq) is None


class TestShuffleAllowed:

    # T92
    def test_yes_true_1_all_truthy_and_no_is_false(self):
        """T92: shuffle:yes / true / 1 return True; no or absent returns False."""
        yes_task = subtask("T", "[shuffle:yes] desc", 30)
        true_task = subtask("T", "[shuffle:true] desc", 30)
        one_task = subtask("T", "[shuffle:1] desc", 30)
        no_task = subtask("T", "[shuffle:no] desc", 30)
        absent_task = subtask("T", "no shuffle tag at all", 30)

        assert shuffle_allowed(yes_task) is True
        assert shuffle_allowed(true_task) is True
        assert shuffle_allowed(one_task) is True
        assert shuffle_allowed(no_task) is False
        assert shuffle_allowed(absent_task) is False


class TestComplexityScore:

    # T93
    def test_explicit_tag_overrides_duration(self):
        """T93: [complexity:low] wins over 120-minute duration-based fallback."""
        task = subtask("Task A", "[complexity:low] Description.", 120)
        assert complexity_score(task) == 1  # low → 1, not 3 from duration

    # T94
    def test_duration_fallback_bands(self):
        """T94: without complexity tag, duration drives the score via three bands."""
        # ≥90min → 3 (high)
        high_dur = subtask("T", "No tag here.", 90)
        # ≥60min but <90min → 2 (medium)
        med_dur = subtask("T", "No tag here.", 89)
        # <60min → 1 (low)
        low_dur = subtask("T", "No tag here.", 59)

        assert complexity_score(high_dur) == 3
        assert complexity_score(med_dur) == 2
        assert complexity_score(low_dur) == 1


class TestHasAnyStructuralTags:

    # T95
    def test_true_when_one_task_is_tagged(self):
        """T95: returns True even if only one task in the list has a tag."""
        tasks = [
            subtask("Task A", "Plain description.", 30),
            subtask("Task B", "Also plain.", 45),
            subtask("Task C", "[group:g] Tagged one.", 60),
        ]
        assert has_any_structural_tags(tasks) is True

    # T96
    def test_false_when_all_tasks_are_plain(self):
        """T96: returns False when no task carries any [key:value] tag."""
        tasks = [
            subtask("Task A", "Plain description.", 30),
            subtask("Task B", "No brackets here.", 45),
        ]
        assert has_any_structural_tags(tasks) is False


class TestSafeStructuralShuffle:

    # T97
    def test_preserves_group_order_reorders_within_shufflable_run(self):
        """T97: alpha group runs before beta group; within alpha, longer tasks go first."""
        tasks = [
            tagged_subtask("Alpha-Short", "alpha", "yes", "low", 30),
            tagged_subtask("Alpha-Long", "alpha", "yes", "high", 60),
            tagged_subtask("Beta-Only", "beta", "yes", "medium", 45),
        ]
        result = safe_structural_shuffle(tasks, run_sort_key=lambda s: s["duration_minutes"])

        names = [t["name"] for t in result]
        # Alpha group appears before Beta group
        assert names.index("Beta-Only") > max(
            names.index("Alpha-Short"), names.index("Alpha-Long")
        )
        # Within alpha group, longer task (60min) is first after desc sort
        alpha_names = [n for n in names if "Alpha" in n]
        assert alpha_names == ["Alpha-Long", "Alpha-Short"], (
            "Within shufflable run, longer task should come first (sort DESC)."
        )

    # T98
    def test_seq_prevents_reorder(self):
        """T98: [seq:N] tasks are hard-locked by sequence even with large duration differences."""
        tasks = [
            tagged_subtask("Seq1", "g", "no", "medium", 30, seq=1),
            tagged_subtask("Seq2", "g", "no", "medium", 90, seq=2),
            tagged_subtask("Seq3", "g", "no", "medium", 60, seq=3),
        ]
        result = safe_structural_shuffle(tasks, run_sort_key=lambda s: s["duration_minutes"])

        names = [t["name"] for t in result]
        assert names == ["Seq1", "Seq2", "Seq3"], (
            "Seq-tagged tasks must not be reordered regardless of duration sort."
        )

    # T99
    def test_only_shufflable_runs_are_reordered(self):
        """T99: non-shufflable tasks stay in place; only contiguous shuffle:yes runs move."""
        tasks = [
            tagged_subtask("Fixed-First", "g", "no", "low", 30),    # shuffle:no → fixed
            tagged_subtask("ShufLong", "g", "yes", "high", 90),      # shuffle:yes run →
            tagged_subtask("ShufShort", "g", "yes", "low", 60),      #   sorted DESC: Long before Short
            tagged_subtask("Fixed-Last", "g", "no", "medium", 45),  # shuffle:no → fixed
        ]
        result = safe_structural_shuffle(tasks, run_sort_key=lambda s: s["duration_minutes"])

        names = [t["name"] for t in result]
        assert names == ["Fixed-First", "ShufLong", "ShufShort", "Fixed-Last"], (
            "Non-shufflable tasks stay in original positions; shuffle run sorted DESC by duration."
        )
