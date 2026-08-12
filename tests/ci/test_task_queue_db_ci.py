"""Meta-test pinning the DB-gated task_queue issue_number CI wiring (#1085 S1-3).

Follows the #326 convention set by tests/ci/test_global_task_db_ci.py and
tests/ci/test_pgvector_db_ci.py: a DB-gated test file that silently stops
being run in CI (job renamed, REQUIRE_DB dropped, bootstrap desynced from the
real migration) goes green for the wrong reason — nobody notices the
partial-unique-index CAS stopped being exercised against real Postgres. This
meta-test pins the wiring so that regression is caught in CI, not discovered
after a collision ships broken.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "pytest.yml"
BOOTSTRAP_SQL = REPO_ROOT / "tests" / "ci" / "task_queue_schema_bootstrap.sql"

CANONICAL_JOB_NAME = "pytest-db-task-queue"
DB_TEST_FILE = "tests/reactive_core/test_task_queue_issue_number_db.py"
REAL_MIGRATION = "supabase/migrations/20260811163000_add_task_queue_issue_number.sql"


def _load_workflow() -> dict:
    with WORKFLOW_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _job() -> dict:
    wf = _load_workflow()
    assert CANONICAL_JOB_NAME in wf["jobs"], (
        f"workflow must define the canonical {CANONICAL_JOB_NAME!r} job — "
        "renaming it without updating this test silently drops the DB-gated "
        "issue_number CAS coverage (#1085 S1-3)."
    )
    return wf["jobs"][CANONICAL_JOB_NAME]


class TestWorkflowConfigIntegrity:
    """Pin the load-bearing pieces of the pytest-db-task-queue job."""

    def test_has_postgres_service(self) -> None:
        services = _job().get("services", {})
        assert "postgres" in services, "pytest-db-task-queue must run a postgres service"
        image = str(services["postgres"].get("image", ""))
        assert image.startswith("postgres"), f"expected a postgres image, got {image!r}"

    def test_database_url_set(self) -> None:
        env = _job().get("env", {})
        assert "DATABASE_URL" in env, (
            "DATABASE_URL must be set on the job — without it the issue_number "
            "CAS tests skip instead of run."
        )

    def test_bootstrap_applies_real_migration(self) -> None:
        """The job must apply the REAL migration, not a re-implementation, so
        the tests exercise the actual partial unique index."""
        steps = _job().get("steps", [])
        run_text = "\n".join(str(s.get("run", "")) for s in steps)
        assert re.search(r"-f\s+" + re.escape(REAL_MIGRATION), run_text), (
            f"bootstrap must apply {REAL_MIGRATION} via `psql -f` — applying a "
            "hand-rolled index copy (or merely naming the file) would let the "
            "constraint drift from production silently."
        )
        assert re.search(r"-f\s+\S*task_queue_schema_bootstrap\.sql", run_text), (
            "bootstrap must seed the pre-#1085 task_queue table + roles via "
            "`psql -f tests/ci/task_queue_schema_bootstrap.sql` before the migration."
        )
        boot_pos = run_text.index("task_queue_schema_bootstrap.sql")
        mig_pos = run_text.index(REAL_MIGRATION)
        assert boot_pos < mig_pos, (
            "task_queue_schema_bootstrap.sql must be applied BEFORE "
            f"{REAL_MIGRATION} — the migration's `alter table ... add column` / "
            "`create unique index` target a table the bootstrap creates."
        )

    def test_require_db_enforced(self) -> None:
        """REQUIRE_DB=1 must be set on the *same* step that runs the CAS test
        file — a job-level or unrelated-step REQUIRE_DB would satisfy a loose
        check while the pytest invocation ran without it."""
        steps = _job().get("steps", [])
        require_db_on_test_step = any(
            DB_TEST_FILE in str(s.get("run", ""))
            and str(s.get("env", {}).get("REQUIRE_DB", "")).strip() not in ("", "0")
            for s in steps
        )
        assert require_db_on_test_step, (
            "the step that runs the issue_number CAS test file must itself set "
            "REQUIRE_DB so a future change that drops the Postgres service fails "
            "CI loudly instead of reverting to silent skip."
        )

    def test_targets_db_test_file(self) -> None:
        steps = _job().get("steps", [])
        run_text = "\n".join(str(s.get("run", "")) for s in steps)
        assert DB_TEST_FILE in run_text, f"the DB job must invoke pytest on {DB_TEST_FILE}."

    def test_bootstrap_sql_exists(self) -> None:
        assert BOOTSTRAP_SQL.is_file(), (
            "tests/ci/task_queue_schema_bootstrap.sql must exist — the workflow "
            "psql -f step references it."
        )

    def test_real_migration_exists(self) -> None:
        migration_path = REPO_ROOT / REAL_MIGRATION
        assert migration_path.is_file(), (
            f"{REAL_MIGRATION} must exist — the workflow psql -f step references it."
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
