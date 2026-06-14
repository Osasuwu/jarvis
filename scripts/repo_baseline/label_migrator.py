"""LabelMigrator — pure planner from clean schema + actual snapshot → plan.

Four migration behaviors (all tested through the public ``plan()`` method):

* **Rename** — an actual label maps to a clean label under a different name.
  Emits ``gh label edit --name`` (rename preserves issue/PR associations).
* **Collision merge** — multiple actual labels map to the same clean label.
  Emits a merge action.
* **Orphan** — actual label has no mapping and no match in the clean schema.
  Flagged confirm-required, never auto-executed.
* **Add** — clean label missing from the actual set.

Routine (post-migration) mode is **additive-only**: no renames, no merges,
no orphan detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from repo_baseline.label_schema import CleanLabel


@dataclass(frozen=True)
class ActualLabel:
    """A label as found in a repo snapshot."""

    name: str
    color: str = ""
    description: str = ""


# ── Plan action types ────────────────────────────────────────────────


@dataclass(frozen=True)
class RenameAction:
    """Rename an actual label in place to match the clean name."""

    old_name: str
    new_name: str


@dataclass(frozen=True)
class MergeAction:
    """Consolidate multiple source labels into a single target."""

    source_names: list[str]
    target_name: str


@dataclass(frozen=True)
class AddAction:
    """Create a clean label that does not yet exist on the repo."""

    label_name: str


@dataclass(frozen=True)
class OrphanLabel:
    """Label in the actual set that has no mapping to the clean schema.

    These are **never auto-executed** — the owner must confirm each one.
    """

    name: str
    reason: str = "No mapping to clean schema"


@dataclass(frozen=True)
class LabelPlan:
    """Complete migration plan produced by the LabelMigrator."""

    renames: list[RenameAction] = field(default_factory=list)
    merges: list[MergeAction] = field(default_factory=list)
    adds: list[AddAction] = field(default_factory=list)
    orphans: list[OrphanLabel] = field(default_factory=list)

    @property
    def has_actions(self) -> bool:
        """True when the plan contains at least one action."""
        return bool(self.renames or self.merges or self.adds or self.orphans)


# ── Migrator ─────────────────────────────────────────────────────────


class LabelMigrator:
    """Pure planner: clean schema + mapping + actual snapshot → LabelPlan.

    Parameters
    ----------
    clean_schema:
        Iterable of CleanLabel — the desired canonical label set.
    mapping:
        Optional dict mapping *actual* label names → *clean* label names.
        Only labels present in the mapping are candidates for rename/merge.
        Actual labels not in the mapping and not matching a clean name are
        flagged as orphans.
    """

    def __init__(
        self,
        clean_schema: list[CleanLabel],
        mapping: dict[str, str] | None = None,
    ):
        self._clean_by_name = {lb.name: lb for lb in clean_schema}
        self._clean_names: set[str] = set(self._clean_by_name.keys())
        self._mapping: dict[str, str] = mapping or {}

    # ── Public API ────────────────────────────────────────────────────

    def plan(
        self,
        actual: list[ActualLabel],
        *,
        routine: bool = False,
    ) -> LabelPlan:
        """Produce a LabelPlan reconciling *actual* labels toward the schema.

        Parameters
        ----------
        actual:
            Labels currently present on the repo (from a snapshot).
        routine:
            When True, emit *only* AddActions for clean labels not yet
            present.  No renames, merges, or orphan detection.
        """
        if routine:
            return self._plan_routine(actual)
        return self._plan_migration(actual)

    # ── Internal: migration mode ──────────────────────────────────────

    def _plan_migration(
        self, actual: list[ActualLabel]
    ) -> LabelPlan:
        actual_by_name = {a.name: a for a in actual}
        actual_names = set(actual_by_name.keys())

        # Already match a clean label — no action needed.
        already_clean = actual_names & self._clean_names

        # Labels that have an explicit mapping entry.
        mapped = actual_names & set(self._mapping.keys())

        # Labels present in actual but not in clean schema and not mapped.
        orphan_names = actual_names - self._clean_names - mapped

        # Group mapped labels by their target clean name.
        target_to_sources: dict[str, list[str]] = {}
        for actual_name in mapped:
            target = self._mapping[actual_name]
            target_to_sources.setdefault(target, []).append(actual_name)

        renames: list[RenameAction] = []
        merges: list[MergeAction] = []
        for target, sources in target_to_sources.items():
            if len(sources) == 1:
                # Single source → rename (or no-op if already the same).
                src = sources[0]
                if src != target:
                    renames.append(RenameAction(old_name=src, new_name=target))
            else:
                # Multiple sources → merge into target.
                merges.append(
                    MergeAction(source_names=sorted(sources), target_name=target)
                )

        # Clean labels not yet present and not already targeted by a
        # rename/merge.
        targeted = already_clean | set(target_to_sources.keys())
        adds = [
            AddAction(label_name=name)
            for name in sorted(self._clean_names - targeted)
        ]

        orphans = [
            OrphanLabel(name=name)
            for name in sorted(orphan_names)
        ]

        return LabelPlan(
            renames=renames, merges=merges, adds=adds, orphans=orphans
        )

    # ── Internal: routine (additive-only) mode ────────────────────────

    def _plan_routine(
        self, actual: list[ActualLabel]
    ) -> LabelPlan:
        actual_names = {a.name for a in actual}
        missing = self._clean_names - actual_names
        adds = [AddAction(label_name=name) for name in sorted(missing)]
        return LabelPlan(adds=adds)
