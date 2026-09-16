"""Meta-test: the "Check substantive diff" step in code-review.yml.

Regressions pinned here:

1. **Zero-match crash.** `grep -c` prints "0" AND exits 1 when nothing matches.
   The old `... | grep -cE '^[+-][^+-]' || echo 0` then APPENDED a second "0",
   making LINES the two-line string "0\n0". `echo "lines=$LINES" >> $GITHUB_OUTPUT`
   wrote a malformed second line → `##[error]Invalid format '0'` → the step and
   the whole `review` check failed. Hit by any PR touching only extensions absent
   from the glob (first observed on an all-`.sql` migration-reconciliation PR).

2. **`.sql` coverage gap.** Schema/migration PRs are code and must be reviewed;
   `.sql` was missing from the substantive-diff glob, so a pure-.sql PR was
   classified as "no code" and skipped review entirely.

3. **Docs-only deadlock (#1897).** A blanket `'*.md'` glob made every docs-only
   PR report `has_code=true`. The reviewer correctly declines pure documentation
   (posts nothing, by design), and the #1434 positive-evidence gate then reads
   `has_code=true` + zero comments as a silent no-review and fails closed --
   forever, since re-running never changes the reviewer's correct decision.
   Fixed by defining "is there something to review" as ONE pathspec list
   (`CODE_PATHSPECS`, job-level env) consumed both by this step's bash and by
   the Layer B reviewer's own skip criteria (via the `codedef` step output) --
   markdown coverage is by path (behavior-carrying files only), never by
   blanket extension.

Config dimension asserts the YAML; logic dimension reimplements the count→output
formatting and the pathspec-matching semantics, and proves the docs-only /
behavior-carrying-markdown / mixed-diff classifications the #1897 fix depends on.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "code-review.yml"

DIFF_STEP_ID = "diff"
CODEDEF_STEP_ID = "codedef"
REVIEW_STEP_ID = "review"


def _load_job() -> dict:
    spec = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return spec["jobs"]["code-gate"]


def _load_steps() -> list[dict]:
    return _load_job()["steps"]


def _step(step_id: str) -> dict:
    steps = _load_steps()
    step = next((s for s in steps if s.get("id") == step_id), None)
    assert step is not None, f"Step with id='{step_id}' not found in code-gate job"
    return step


def _diff_step() -> dict:
    return _step(DIFF_STEP_ID)


def _codedef_step() -> dict:
    return _step(CODEDEF_STEP_ID)


def _review_step() -> dict:
    return _step(REVIEW_STEP_ID)


def _diff_globs() -> list[str]:
    """The single source of truth for "is there something to review" (#1897 AC4).

    Lives as one job-level env value (`CODE_PATHSPECS`), read by the `diff`
    step's bash directly and by the Layer B reviewer's prompt via the
    `codedef` step's output -- never duplicated as a second literal list (see
    test_no_second_pathspec_list_in_diff_step / _in_codedef_step below).
    """
    env = _load_job().get("env", {})
    pathspecs = env.get("CODE_PATHSPECS")
    assert pathspecs, "CODE_PATHSPECS missing from code-gate job env"
    return pathspecs.split()


# --- Config dimension: pin the YAML ---


def test_diff_step_exists():
    assert _diff_step() is not None


def test_codedef_step_exists():
    step = _codedef_step()
    assert step is not None
    assert "if" not in step, (
        "codedef must run unconditionally (including on workflow_dispatch) so "
        "the review prompt always has a pathspecs value to interpolate"
    )


def test_sql_in_substantive_diff_glob():
    globs = _diff_globs()
    assert "*.sql" in globs, (
        "schema/migration (.sql) PRs must count as substantive code so they get "
        f"reviewed, not silently skipped; glob was: {globs}"
    )


def test_blanket_md_glob_dropped():
    globs = _diff_globs()
    assert "*.md" not in globs, (
        "blanket '*.md' must not gate has_code -- it routes every docs-only PR "
        f"into the #1434 positive-evidence deadlock (#1897); glob was: {globs}"
    )


def test_common_code_extensions_still_covered():
    globs = _diff_globs()
    for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.yaml", "*.yml", "*.json", "*.sh", "*.ps1", "*.sql"):
        assert ext in globs, f"{ext} dropped from substantive-diff glob: {globs}"


def test_behavior_carrying_markdown_pathspecs_present():
    globs = _diff_globs()
    for path in (
        "CLAUDE.md",
        "*/CLAUDE.md",
        "AGENTS.md",
        "*/AGENTS.md",
        "SOUL.md",
        "*/SOUL.md",
        ".claude/agents/*.md",
        ".claude-userlevel/skills/*.md",
    ):
        assert path in globs, (
            f"{path} missing from CODE_PATHSPECS -- behavior-carrying markdown "
            f"must stay reviewed by path, not by blanket extension (#1897 AC3); "
            f"glob was: {globs}"
        )


def test_ps1_in_substantive_diff_glob():
    globs = _diff_globs()
    assert "*.ps1" in globs, (
        "PowerShell (.ps1) PRs must count as substantive code so they get "
        f"reviewed, not silently skipped (#1816 AC3); glob was: {globs}"
    )


def test_no_double_zero_echo_pattern():
    """The `|| echo 0` doubling bug must not come back.

    On zero matches grep already prints "0"; appending another via `echo 0`
    corrupts $GITHUB_OUTPUT. The fix uses `|| true` + a `${LINES:-0}` guard.
    """
    run = _diff_step()["run"]
    # Strip comment lines — the fix documents the old `|| echo 0` bug in prose.
    code = "\n".join(ln for ln in run.splitlines() if not ln.lstrip().startswith("#"))
    assert "|| echo 0" not in code, (
        "`grep -c ... || echo 0` reintroduces the 'Invalid format 0' crash on "
        "zero matches (grep -c already emits '0' and exits 1). Use `|| true`."
    )
    assert "grep -cE" in code and "|| true" in code, (
        "expected `grep -cE ... || true` to mask grep's exit-1-on-zero-matches"
    )


def test_set_f_brackets_git_diff():
    """Without `set -f`, the shell glob-expands each pathspec against the

    checked-out working tree before git ever sees it (e.g. `*.py` could
    expand to real filenames present in CWD), silently corrupting `has_code`.
    """
    run = _diff_step()["run"]
    code = "\n".join(ln for ln in run.splitlines() if not ln.lstrip().startswith("#"))
    set_f_idx = code.find("set -f")
    diff_idx = code.find("git diff")
    set_plus_f_idx = code.find("set +f", diff_idx if diff_idx != -1 else 0)
    assert set_f_idx != -1, "`set -f` missing before the git diff invocation"
    assert diff_idx != -1, "no `git diff` invocation found in the diff step"
    assert set_plus_f_idx != -1, "`set +f` missing after the git diff invocation"
    assert set_f_idx < diff_idx < set_plus_f_idx, (
        "`set -f`/`set +f` must bracket the `git diff -- $CODE_PATHSPECS` line"
    )


def test_no_second_pathspec_list_in_diff_step():
    run = _diff_step()["run"]
    code = "\n".join(ln for ln in run.splitlines() if not ln.lstrip().startswith("#"))
    assert re.search(r"'\*\.[a-z0-9]+'|'CLAUDE\.md'", code) is None, (
        "the diff step must consume $CODE_PATHSPECS, not carry its own "
        "hand-written pathspec list -- a second copy can silently drift from "
        "CODE_PATHSPECS (#1897 AC4)"
    )
    assert "$CODE_PATHSPECS" in code, "diff step must reference $CODE_PATHSPECS"


def test_no_second_pathspec_list_in_codedef_step():
    run = _codedef_step()["run"]
    assert "$CODE_PATHSPECS" in run, "codedef step must re-export $CODE_PATHSPECS"
    assert re.search(r"'\*\.[a-z0-9]+'|'CLAUDE\.md'", run) is None, (
        "codedef must not carry its own hand-written pathspec list either"
    )


def test_review_prompt_derives_skip_criteria_from_codedef():
    prompt = _review_step()["with"]["prompt"]
    assert "steps.codedef.outputs.pathspecs" in prompt, (
        "the reviewer's skip criteria must read the same pathspec definition "
        "the has_code gate uses ($CODE_PATHSPECS via the codedef step output), "
        "not a second hand-written description (#1897 AC4)"
    )


# --- Logic dimension: reimplement count → output formatting + pathspec matching ---


def _matches_pathspecs(path: str, pathspecs: list[str]) -> bool:
    """Model git's non-magic pathspec matching: bare '*' crosses '/'.

    fnmatch's '*' already matches '/' and the empty string, reproducing git's
    wildmatch semantics for a pattern with no `:(glob)`/`:(literal)` magic
    (empirically verified against a scratch git repo for #1897).
    """
    return any(fnmatch.fnmatchcase(path, spec) for spec in pathspecs)


def _is_code_path(path: str) -> bool:
    return _matches_pathspecs(path, _diff_globs())


def _format_output(match_count: int) -> tuple[str, str]:
    """Model the fixed bash: LINES is always a single clean token, HAS derived.

    Mirrors:
        LINES=$(... | grep -cE ... || true); LINES=${LINES:-0}
        HAS=$( [ "$LINES" -gt 0 ] && echo true || echo false )
    """
    lines_value = str(match_count)  # grep -c always emits exactly one integer line
    assert "\n" not in lines_value, "LINES must be a single line for $GITHUB_OUTPUT"
    has = "true" if match_count > 0 else "false"
    return lines_value, has


def test_zero_matches_is_single_clean_line():
    lines_value, has = _format_output(0)
    assert lines_value == "0"
    assert has == "false"
    # The historical bug produced "0\n0"; assert we never emit an embedded newline.
    assert "\n" not in f"lines={lines_value}"


def test_positive_matches_flag_has_code():
    lines_value, has = _format_output(7)
    assert lines_value == "7"
    assert has == "true"


def test_sql_path_is_code():
    assert _is_code_path("supabase/migrations/20260415082814_create_credential_registry.sql")
    assert _is_code_path("mcp-memory/schema.sql")


def test_ps1_path_is_code():
    assert _is_code_path("scripts/install.ps1")


def test_non_code_path_is_not_code():
    assert not _is_code_path("docs/notes.txt")
    assert not _is_code_path("Dockerfile")


def test_docs_only_paths_are_not_code():
    for path in (
        "docs/decisions/2026-Q3.md",
        "docs/reference/ci-guard-meta-tests.md",
        ".claude/session-snapshots/de927bb9-93db-4254-8ddc-0705dd01eba4.md",
        "README.md",
        "CONTEXT.md",
    ):
        assert not _is_code_path(path), f"{path} wrongly classified as code (#1897 AC1)"

    lines_value, has = _format_output(0)
    assert has == "false"


def test_behavior_carrying_markdown_is_code():
    for path in (
        "CLAUDE.md",
        "AGENTS.md",
        "config/SOUL.md",
        ".claude/agents/planner.md",
        ".claude-userlevel/skills/grill/SKILL.md",
        ".claude-userlevel/skills/grill/CRITIC.md",
    ):
        assert _is_code_path(path), f"{path} must count as code (behavior-carrying markdown, #1897 AC3)"


def test_markdown_negative_controls_not_falsely_matched():
    # '*/CLAUDE.md' requires a real '/' boundary and the exact trailing
    # segment -- a same-suffix filename must not slip through.
    assert not _is_code_path("XCLAUDE.md")
    assert not _is_code_path("docs/CLAUDE-notes.md")


def test_mixed_docs_and_code_diff_has_code_true():
    for paths in (
        ["docs/notes.md", "agents/plan_lock.py"],
        ["docs/notes.md", ".claude/agents/planner.md"],
    ):
        matches = sum(1 for p in paths if _is_code_path(p))
        assert matches > 0, f"mixed diff wrongly classified as no-code (#1897 AC2): {paths}"
