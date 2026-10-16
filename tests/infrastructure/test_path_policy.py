"""agents/path_policy.py: the one glob dialect and bucket verdict behind every path reader (#2067)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from agents import path_policy

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "agents" / "path_policy.py"
REPO = "Osasuwu/jarvis"


# -- dialect ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "glob"),
    [
        ("supabase", "supabase/**"),
        ("supabase/migrations/001.sql", "supabase/**"),
        ("docs/a/b/c/guide.md", "docs/**/guide.md"),
        ("docs/guide.md", "docs/**/guide.md"),
        ("docs/a/b/x.md", "docs/**/*.md"),
        ("agents/sub/x.py", "agents/*.py"),
        ("AGENTS.md", "AGENTS.md"),
    ],
)
def test_a_glob_matches_what_the_dialect_says(path, glob):
    assert path_policy.matched_paths([path], [glob]) == (path,)


@pytest.mark.parametrize(
    ("path", "glob"),
    [
        ("supabase2/x.sql", "supabase/**"),
        ("other/supabase/x.sql", "supabase/**"),
        ("docs/guide.txt", "docs/**/guide.md"),
        ("src/docs/a/guide.md", "docs/**/guide.md"),
        ("README.md", "AGENTS.md"),
    ],
)
def test_a_glob_does_not_match_outside_what_the_dialect_says(path, glob):
    assert path_policy.matched_paths([path], [glob]) == ()


@pytest.mark.parametrize(
    "path", ["agents.md", "Supabase/x.sql", "SUPABASE", ".\\AGENTS.md", "./supabase/x.sql"]
)
def test_case_backslashes_and_a_leading_dot_slash_do_not_dodge_a_glob(path):
    assert path_policy.matched_paths([path], ["AGENTS.md", "supabase/**"]) == (path,)


def test_matches_come_back_as_the_callers_strings_in_input_order():
    paths = ["z/b.py", ".\\Z\\a.py", "y.py", "z/c.py"]
    assert path_policy.matched_paths(paths, ["z/**"]) == ("z/b.py", ".\\Z\\a.py", "z/c.py")


def test_no_globs_match_nothing():
    assert path_policy.matched_paths(["a.py"], []) == ()


# -- bucket verdict -----------------------------------------------------------------------------

BUCKETS = {
    "hitl": ["AGENTS.md"],
    "guarded": ["supabase/**", "AGENTS.md"],
    "machinery": [".github/**"],
    "gate": [".github/scripts/code_gate_verdict.py"],
    "_comment": ["src/**"],
}


def test_hitl_wins_over_guarded_and_names_its_matches():
    verdict = path_policy.classify_buckets(["supabase/x.sql", "AGENTS.md"], BUCKETS)
    assert (verdict.afk_class, verdict.afk_bucket, verdict.afk_matched) == (
        3,
        "hitl",
        ("AGENTS.md",),
    )


def test_a_guarded_match_is_class_2():
    verdict = path_policy.classify_buckets(["src/a.py", "supabase/x.sql"], BUCKETS)
    assert (verdict.afk_class, verdict.afk_bucket, verdict.afk_matched) == (
        2,
        "guarded",
        ("supabase/x.sql",),
    )


def test_no_bucket_match_is_low_with_no_class():
    verdict = path_policy.classify_buckets(["src/a.py"], BUCKETS)
    assert verdict == path_policy.PathVerdict(
        afk_class=None,
        afk_bucket=None,
        afk_matched=(),
        risk_floor="LOW",
        risk_matched=(),
        machinery=False,
        hitl=False,
        gate=False,
    )


def test_a_machinery_only_match_floors_risk_without_an_afk_class():
    verdict = path_policy.classify_buckets([".github/workflows/x.yml", "src/a.py"], BUCKETS)
    assert (verdict.afk_class, verdict.risk_floor, verdict.risk_matched, verdict.machinery) == (
        None,
        "HIGH",
        (".github/workflows/x.yml",),
        True,
    )


def test_a_bucket_name_the_policy_does_not_know_still_floors_risk():
    verdict = path_policy.classify_buckets(["infra/x.tf"], {"future": ["infra/**"]})
    assert (verdict.risk_floor, verdict.risk_matched) == ("HIGH", ("infra/x.tf",))


def test_the_gate_flag_is_set_only_by_the_gate_bucket():
    gate = path_policy.classify_buckets([".github/scripts/code_gate_verdict.py"], BUCKETS)
    other = path_policy.classify_buckets([".github/scripts/other.py"], BUCKETS)
    assert (gate.gate, other.gate) == (True, False)


def test_the_hitl_flag_is_set_by_a_hitl_match():
    assert path_policy.classify_buckets(["AGENTS.md"], BUCKETS).hitl is True


def test_an_underscore_key_is_never_a_bucket():
    assert path_policy.classify_buckets(["src/a.py"], BUCKETS).risk_floor == "LOW"


# -- policy file --------------------------------------------------------------------------------


def _policy(tmp_path, data):
    target = tmp_path / "protected-paths.json"
    target.write_text(json.dumps(data) if not isinstance(data, str) else data, "utf-8")
    return path_policy.load_policy(target)


def test_a_repos_buckets_are_read_without_underscore_keys(tmp_path):
    policy = _policy(tmp_path, {"_comment": "x", REPO: {"_c": "y", "hitl": ["a"], "gate": []}})
    assert policy.buckets(REPO) == {"hitl": ("a",), "gate": ()}


def test_classify_reads_the_repos_own_entry(tmp_path):
    policy = _policy(tmp_path, {REPO: {"guarded": ["x/**"]}, "other/repo": {"hitl": ["y"]}})
    verdict = policy.classify(REPO, ["x/a.py", "y"])
    assert (verdict.afk_class, verdict.afk_matched) == (2, ("x/a.py",))


def test_an_unknown_repo_raises_naming_it(tmp_path):
    policy = _policy(tmp_path, {REPO: {"hitl": []}})
    with pytest.raises(path_policy.UnknownRepoError, match="other/repo"):
        policy.buckets("other/repo")


def test_a_flat_list_entry_raises_the_legacy_schema_error(tmp_path):
    policy = _policy(tmp_path, {REPO: ["AGENTS.md"]})
    with pytest.raises(path_policy.LegacySchemaError) as info:
        policy.buckets(REPO)
    assert str(info.value) == (
        "config/protected-paths.json: 'Osasuwu/jarvis' uses the legacy flat-list schema "
        "(pre-#1708) — expected a {'hitl': [...], 'guarded': [...]} object"
    )


@pytest.mark.parametrize("bucket", [".github/**", [[".github/**"]], [1], None])
def test_a_bucket_that_is_not_a_list_of_globs_raises(tmp_path, bucket):
    policy = _policy(tmp_path, {REPO: {"machinery": bucket}})
    with pytest.raises(path_policy.MalformedBucketError, match="machinery"):
        policy.buckets(REPO)


def test_a_malformed_foreign_entry_does_not_change_another_repos_answer(tmp_path):
    policy = _policy(tmp_path, {REPO: {"hitl": ["a"]}, "other/repo": ["legacy"]})
    assert policy.buckets(REPO) == {"hitl": ("a",)}


def test_a_corrupt_file_raises_the_json_error_unchanged(tmp_path):
    with pytest.raises(json.JSONDecodeError):
        _policy(tmp_path, "{")


def test_a_file_that_is_not_an_object_raises_type_error(tmp_path):
    with pytest.raises(TypeError, match="JSON object"):
        _policy(tmp_path, ["a"])


def test_a_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        path_policy.load_policy(tmp_path / "absent.json")


# -- loadability --------------------------------------------------------------------------------

STDLIB_ALLOWED = {"__future__", "collections.abc", "dataclasses", "fnmatch", "json", "pathlib"}


def test_the_module_imports_only_the_stdlib_allow_list():
    """It must load by file path under `python -I` (code_gate_verdict): no agents, no PyYAML."""
    tree = ast.parse(MODULE.read_text("utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add("." * node.level + (node.module or ""))
    assert imported - STDLIB_ALLOWED == set()
