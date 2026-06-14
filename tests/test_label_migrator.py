"""Tests for the LabelMigrator pure planner.

Covers all four migration behaviors + routine mode through the public
``plan()`` interface (schema + snapshot in → plan out).
"""

from __future__ import annotations

from repo_baseline.label_migrator import (
    ActualLabel,
    AddAction,
    LabelMigrator,
    MergeAction,
    OrphanLabel,
    RenameAction,
)
from repo_baseline.label_schema import CleanLabel, CLEAN_LABELS


# ── Fixture helpers ──────────────────────────────────────────────────


def _schema(*names: str) -> list[CleanLabel]:
    """Build a minimal clean schema from the canonical set."""
    by_name = {lb.name: lb for lb in CLEAN_LABELS}
    return [by_name[n] for n in names]


def _actual(*names: str) -> list[ActualLabel]:
    """Build an actual-label snapshot from names alone."""
    return [ActualLabel(name=n) for n in names]


# ── Rename behaviour ─────────────────────────────────────────────────


class TestRename:
    def test_single_rename_via_mapping(self):
        """Actual label mapped to a clean label with different name → rename."""
        migrator = LabelMigrator(
            clean_schema=_schema("area:quality"),
            mapping={"area:ci-quality": "area:quality"},
        )
        plan = migrator.plan(_actual("area:ci-quality"))
        assert plan.renames == [
            RenameAction(old_name="area:ci-quality", new_name="area:quality")
        ]
        assert plan.merges == []
        assert plan.adds == []
        assert plan.orphans == []

    def test_rename_preserves_identity(self):
        """Plan emits rename, never delete+create (no AddAction for renamed)."""
        migrator = LabelMigrator(
            clean_schema=_schema("needs-research"),
            mapping={"needs-investigation": "needs-research"},
        )
        plan = migrator.plan(_actual("needs-investigation"))
        assert len(plan.renames) == 1
        # The clean label "needs-research" should NOT appear as an add
        # since it's already the target of the rename.
        added_names = {a.label_name for a in plan.adds}
        assert "needs-research" not in added_names

    def test_already_matching_no_rename(self):
        """Actual label already matching clean name → no action."""
        migrator = LabelMigrator(
            clean_schema=_schema("priority:high"),
            mapping={},
        )
        plan = migrator.plan(_actual("priority:high"))
        assert plan.renames == []
        assert plan.merges == []
        assert plan.adds == []
        assert plan.orphans == []


# ── Collision-on-target → merge ──────────────────────────────────────


class TestMerge:
    def test_two_labels_collide_into_one_target(self):
        """Two actual labels mapping to the same clean label → merge."""
        migrator = LabelMigrator(
            clean_schema=_schema("area:quality"),
            mapping={
                "test-audit": "area:quality",
                "area:ci-quality": "area:quality",
            },
        )
        plan = migrator.plan(_actual("test-audit", "area:ci-quality"))
        assert plan.merges == [
            MergeAction(
                source_names=["area:ci-quality", "test-audit"],
                target_name="area:quality",
            )
        ]
        assert plan.renames == []
        # area:quality already targeted by the merge → not in adds.
        added_names = {a.label_name for a in plan.adds}
        assert "area:quality" not in added_names

    def test_many_to_one_consolidation(self):
        """Three-or-more sources → single merge set."""
        migrator = LabelMigrator(
            clean_schema=_schema("area:quality"),
            mapping={
                "quality-old": "area:quality",
                "qa-old": "area:quality",
                "test-audit": "area:quality",
            },
        )
        plan = migrator.plan(
            _actual("quality-old", "qa-old", "test-audit")
        )
        assert len(plan.merges) == 1
        merge = plan.merges[0]
        assert merge.target_name == "area:quality"
        assert sorted(merge.source_names) == [
            "qa-old",
            "quality-old",
            "test-audit",
        ]
        assert plan.renames == []

    def test_mix_rename_and_merge(self):
        """One rename + one merge coexist when mapping cardinalities differ."""
        migrator = LabelMigrator(
            clean_schema=_schema("area:quality", "needs-research"),
            mapping={
                # Single source → rename
                "old-research": "needs-research",
                # Multiple sources → merge
                "qa-legacy": "area:quality",
                "test-audit": "area:quality",
            },
        )
        plan = migrator.plan(
            _actual("old-research", "qa-legacy", "test-audit")
        )
        assert len(plan.renames) == 1
        assert plan.renames[0] == RenameAction(
            old_name="old-research", new_name="needs-research"
        )
        assert len(plan.merges) == 1
        assert plan.merges[0].target_name == "area:quality"
        assert len(plan.merges[0].source_names) == 2


# ── Orphan detection (confirm-required) ──────────────────────────────


class TestOrphan:
    def test_unmapped_actual_label_flagged(self):
        """Actual label not in clean schema and not mapped → orphan."""
        migrator = LabelMigrator(
            clean_schema=_schema("task"),
            mapping={},
        )
        plan = migrator.plan(_actual("task", "some-adhoc-label"))
        assert len(plan.orphans) == 1
        assert plan.orphans[0] == OrphanLabel(name="some-adhoc-label")
        # "task" is already clean → no orphan.
        assert plan.renames == []
        assert plan.merges == []

    def test_multiple_orphans_listed(self):
        """Multiple unmapped labels → all flagged."""
        migrator = LabelMigrator(
            clean_schema=_schema("task", "draft"),
            mapping={},
        )
        plan = migrator.plan(_actual("task", "adhoc-1", "adhoc-2"))
        assert len(plan.orphans) == 2
        orphan_names = {o.name for o in plan.orphans}
        assert orphan_names == {"adhoc-1", "adhoc-2"}

    def test_mapped_label_not_orphan(self):
        """Mapped label is NOT flagged as orphan even if not in clean."""
        migrator = LabelMigrator(
            clean_schema=_schema("priority:high"),
            mapping={"urgent": "priority:high"},
        )
        plan = migrator.plan(_actual("urgent"))
        # "urgent" has a mapping → no orphan; becomes a rename.
        assert plan.orphans == []
        assert len(plan.renames) == 1

    def test_no_orphans_when_all_mapped(self):
        """All actual labels accounted for → zero orphans."""
        migrator = LabelMigrator(
            clean_schema=_schema("priority:high", "task"),
            mapping={
                "urgent": "priority:high",
                "chore": "task",
            },
        )
        plan = migrator.plan(_actual("urgent", "chore"))
        assert plan.orphans == []


# ── Add behaviour ────────────────────────────────────────────────────


class TestAdd:
    def test_missing_clean_labels_added(self):
        """Clean labels not in actual set → AddAction."""
        migrator = LabelMigrator(
            clean_schema=_schema("priority:high", "task", "draft"),
            mapping={},
        )
        plan = migrator.plan(_actual("priority:high"))
        added_names = {a.label_name for a in plan.adds}
        assert added_names == {"draft", "task"}
        assert "priority:high" not in added_names

    def test_no_adds_when_schema_complete(self):
        """All clean labels present → no adds."""
        migrator = LabelMigrator(
            clean_schema=_schema("task", "draft"),
            mapping={},
        )
        plan = migrator.plan(_actual("task", "draft"))
        assert plan.adds == []


# ── Routine (additive-only) mode ─────────────────────────────────────


class TestRoutine:
    def test_additive_only(self):
        """Routine mode only produces adds — no renames/merges/orphans."""
        migrator = LabelMigrator(
            clean_schema=_schema("priority:high", "task"),
            mapping={"urgent": "priority:high"},  # ignored in routine
        )
        plan = migrator.plan(
            _actual("urgent", "task"),
            routine=True,
        )
        # "priority:high" is missing from actual but has a mapping → still
        # emitted as an add (routine ignores mapping).
        assert len(plan.adds) == 1
        assert plan.adds[0].label_name == "priority:high"
        assert plan.renames == []
        assert plan.merges == []
        assert plan.orphans == []

    def test_routine_idempotent_when_complete(self):
        """Routine on an already-converged repo → empty plan."""
        migrator = LabelMigrator(
            clean_schema=_schema("task", "draft"),
            mapping={},
        )
        plan = migrator.plan(_actual("task", "draft"), routine=True)
        assert plan.has_actions is False

    def test_routine_ignores_ad_hoc_labels(self):
        """Ad-hoc labels in routine mode are silently accepted."""
        migrator = LabelMigrator(
            clean_schema=_schema("task"),
            mapping={},
        )
        plan = migrator.plan(
            _actual("task", "some-adhoc-label"),
            routine=True,
        )
        # "some-adhoc-label" is not in clean schema but should NOT be
        # flagged as orphan in routine mode.
        assert plan.orphans == []
        assert plan.renames == []
        assert plan.merges == []
        assert plan.adds == []


# ── Integration: full cycle ──────────────────────────────────────────


class TestIntegration:
    def test_complex_migration_scenario(self):
        """Multiple behaviours in one plan."""
        migrator = LabelMigrator(
            clean_schema=_schema(
                "priority:high",
                "priority:medium",
                "task",
                "epic",
                "draft",
                "status:ready",
                "status:in-progress",
                "area:quality",
                "needs-research",
            ),
            mapping={
                "urgent": "priority:high",
                "chore": "task",
                "wip": "status:in-progress",
                "qa-flag": "area:quality",
                "test-quality": "area:quality",
            },
        )
        plan = migrator.plan(
            _actual(
                "urgent",
                "chore",
                "wip",
                "qa-flag",
                "test-quality",
                "status:ready",
                "ad-hoc-label",
            )
        )
        # 3 renames (urgent→high, chore→task, wip→in-progress)
        assert len(plan.renames) == 3
        rename_targets = {r.new_name for r in plan.renames}
        assert rename_targets == {"priority:high", "task", "status:in-progress"}

        # 1 merge (qa-flag + test-quality → area:quality)
        assert len(plan.merges) == 1
        assert plan.merges[0].target_name == "area:quality"
        assert sorted(plan.merges[0].source_names) == [
            "qa-flag",
            "test-quality",
        ]

        # Adds for clean labels not present and not targeted.
        added_names = {a.label_name for a in plan.adds}
        assert "priority:medium" in added_names
        assert "epic" in added_names
        assert "draft" in added_names
        assert "needs-research" in added_names
        # Already in actual:
        assert "status:ready" not in added_names
        # Targeted by rename/merge:
        assert "priority:high" not in added_names
        assert "task" not in added_names
        assert "status:in-progress" not in added_names
        assert "area:quality" not in added_names

        # 1 orphan
        assert len(plan.orphans) == 1
        assert plan.orphans[0].name == "ad-hoc-label"

    def test_already_converged_is_noop(self):
        """When actual matches clean schema exactly → empty plan."""
        migrator = LabelMigrator(
            clean_schema=_schema("task", "epic", "draft"),
            mapping={},
        )
        plan = migrator.plan(_actual("task", "epic", "draft"))
        assert plan.has_actions is False

    def test_adds_only_when_nothing_to_migrate(self):
        """Plan with no mapping and partial actual → only adds."""
        migrator = LabelMigrator(
            clean_schema=_schema("task", "epic", "draft"),
            mapping={},
        )
        plan = migrator.plan(_actual("task"))
        assert plan.adds == [
            AddAction(label_name="draft"),
            AddAction(label_name="epic"),
        ]
        assert plan.renames == []
        assert plan.merges == []
        assert plan.orphans == []
