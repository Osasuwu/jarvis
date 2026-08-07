"""Meta-test for .github/workflows/schema-drift-check.yml (#326).

The pattern this test enforces — **every CI guard ships with a co-located
fixture test that proves it blocks what it should** — is the response to
two distinct failure modes, both already hit in production:

  PR #289 pointed the guard at `supabase/schema.sql`, the canonical file
  is `mcp-memory/schema.sql`. The guard silently passed for a full sprint
  on PRs that should have been blocked.

  `require-paired-migration` was later added to branch protection's
  `required_status_checks` while the workflow still had a trigger-level
  `on.pull_request.paths` filter. Any PR that didn't touch schema/migration
  paths never triggered the workflow at all, so no check-run was ever
  created for that context — GitHub then leaves such PRs permanently
  `mergeable_state: blocked` ("Expected — Waiting for status to be
  reported"), since a required context must report *something* to clear.
  Caught on PR #1440, which touched neither path.

Two dimensions covered here; both are required for a guard to be trusted:

1. **Config check** — the workflow must trigger on `pull_request`
   unconditionally, with NO trigger-level `paths:` filter, precisely
   because it's a required check: gating belongs entirely in the job's
   own JS logic (which already no-ops gracefully via `core.info(...);
   return;` when schema.sql is unchanged), never at the trigger level.
2. **Logic check** — three scenarios (schema+migration, schema-only,
   unrelated change) asserted against a pure-Python reimplementation
   of the workflow's JS decision rule.

The logic reimplementation is intentionally a parallel copy rather than
an import — the workflow runs github-script (JS) on GitHub's runners.
Drift between `_decide()` and the workflow is still possible; the config
check anchors the invariant that actually gates merges now (unconditional
trigger), which is the exact class of bug that motivated #326.

Convention for future guards: `.github/workflows/X-guard.yml` =>
`tests/ci/test_X_guard.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "schema-drift-check.yml"

CANONICAL_SCHEMA_PATH = "mcp-memory/schema.sql"
MIGRATIONS_PREFIX = "supabase/migrations/"


# -- Config check ------------------------------------------------------------


def _load_workflow() -> dict:
    with WORKFLOW_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestWorkflowConfigIntegrity:
    """Anchor the load-bearing invariant: the guard's trigger is unconditional.

    `require-paired-migration` is a required branch-protection check. A
    required check that only *sometimes* runs (trigger-level `paths:`
    filter) leaves non-matching PRs stuck `mergeable_state: blocked`
    forever, because GitHub never sees a check-run for that context to
    clear the "waiting for status" state. The job's own JS logic already
    no-ops gracefully for irrelevant PRs — that's where gating belongs.
    """

    def test_workflow_file_exists(self):
        assert WORKFLOW_PATH.exists(), (
            f"Expected guard workflow at {WORKFLOW_PATH.relative_to(REPO_ROOT)}"
        )

    def test_triggers_on_pull_request(self):
        wf = _load_workflow()
        # PyYAML parses the `on:` key as the Python boolean `True` (YAML 1.1
        # treats the literal `on` as a synonym for true). Accept either key
        # so the test survives either yaml-lib behavior.
        triggers = wf.get("on") or wf.get(True)
        assert triggers is not None, "Workflow must declare `on:` triggers"
        assert "pull_request" in triggers, "Guard must run on pull_request events"

    def test_no_trigger_level_paths_filter(self):
        """Regression test: a required check must fire on every PR.

        Caught live on PR #1440 — `require-paired-migration` was made a
        required context while this workflow still filtered on
        `mcp-memory/schema.sql` / `supabase/migrations/**` at the trigger
        level. PRs touching neither path never got a check-run for that
        context and sat `mergeable_state: blocked` indefinitely. Any
        `paths:` key under `on.pull_request` reintroduces that regression.
        """
        wf = _load_workflow()
        triggers = wf.get("on") or wf.get(True)
        pr_filter = triggers["pull_request"]
        assert not pr_filter or "paths" not in pr_filter, (
            "schema-drift-check.yml must NOT filter its pull_request trigger "
            "by `paths:` — it backs a required status check, so it must "
            "produce a check-run for every PR. Move any path-based gating "
            "into the job's own script logic instead."
        )


# -- Logic check -------------------------------------------------------------


def _decide(files: list[dict]) -> str:
    """Pure-Python reimplementation of the guard's JS decision rule.

    Mirrors .github/workflows/schema-drift-check.yml github-script body.
    Returns one of: "skip", "fail", "pass".

    Keep this function in sync with the workflow. The config tests above
    lock down the `paths:` filter; this function locks down the decision
    logic. If the workflow changes its logic, update this function and
    add a corresponding scenario.
    """
    schema_changed = any(
        f["filename"] == CANONICAL_SCHEMA_PATH
        and f["status"] in ("modified", "added", "changed")
        for f in files
    )
    if not schema_changed:
        return "skip"

    migration_added = any(
        f["filename"].startswith(MIGRATIONS_PREFIX) and f["status"] == "added"
        for f in files
    )
    return "pass" if migration_added else "fail"


class TestGuardLogic:
    """Scenarios: the guard must block what it claims to block."""

    def test_skips_when_schema_unchanged(self):
        files = [{"filename": "README.md", "status": "modified"}]
        assert _decide(files) == "skip"

    def test_blocks_schema_edit_without_migration(self):
        """The exact failure mode from #284 — schema edited, no migration,
        broken in prod. Guard must FAIL this PR."""
        files = [{"filename": CANONICAL_SCHEMA_PATH, "status": "modified"}]
        assert _decide(files) == "fail"

    def test_passes_with_paired_migration(self):
        files = [
            {"filename": CANONICAL_SCHEMA_PATH, "status": "modified"},
            {"filename": "supabase/migrations/20260424_add_thing.sql", "status": "added"},
        ]
        assert _decide(files) == "pass"

    def test_blocks_schema_added_without_migration(self):
        """Edge case: brand-new schema file — still needs a migration."""
        files = [{"filename": CANONICAL_SCHEMA_PATH, "status": "added"}]
        assert _decide(files) == "fail"

    def test_modified_migration_alone_does_not_pass(self):
        """Modifying an existing migration (without schema change) is skip-territory —
        the guard only fires on schema changes. This locks down current behavior."""
        files = [{"filename": "supabase/migrations/20260101_old.sql", "status": "modified"}]
        assert _decide(files) == "skip"

    @pytest.mark.parametrize(
        "files,expected",
        [
            ([], "skip"),
            ([{"filename": "docs/notes.md", "status": "added"}], "skip"),
            (
                [
                    {"filename": "docs/notes.md", "status": "added"},
                    {"filename": CANONICAL_SCHEMA_PATH, "status": "modified"},
                ],
                "fail",
            ),
            (
                [
                    {"filename": CANONICAL_SCHEMA_PATH, "status": "modified"},
                    {"filename": "supabase/migrations/new.sql", "status": "added"},
                    {"filename": "other.py", "status": "modified"},
                ],
                "pass",
            ),
        ],
    )
    def test_mixed_file_sets(self, files, expected):
        assert _decide(files) == expected
