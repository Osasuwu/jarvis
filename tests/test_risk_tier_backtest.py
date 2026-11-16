"""scripts/risk_tier_backtest.py — the planned risk tier of a merged PR (#2199).

Expected tiers are literals worked out from the planned inputs in the decision of PR #2197
(docs/decisions/2026-Q4.md, "Three risk tiers ..."). The protected list is a literal written to
a temp checkout; plan_review.yaml is the real one, its thresholds overridden per variant.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root / "scripts"))

import risk_tier_backtest as bt  # noqa: E402
from agents import path_policy  # noqa: E402
from agents.plan_review_config import load_plan_review_config  # noqa: E402

REPO = "Osasuwu/jarvis"
PROTECTED = {
    REPO: {
        "hitl": ["AGENTS.md"],
        "guarded": ["supabase/**", "agents/path_policy.py"],
        "machinery": [".github/**", "uv.lock"],
    }
}


@pytest.fixture
def host(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "protected-paths.json").write_text(json.dumps(PROTECTED), "utf-8")
    shutil.copy(_root / "config" / "plan_review.yaml", tmp_path / "config" / "plan_review.yaml")
    return tmp_path


def _run(host, files, changed=None, blobs=None):
    buckets = path_policy.load_policy(host / "config" / "protected-paths.json").buckets(REPO)
    config = load_plan_review_config(host / "config" / "plan_review.yaml")
    pr = {
        "number": 1,
        "title": "t",
        "mergedAt": "2026-11-15T11:23:47Z",
        "changedFiles": len(files or []) if changed is None else changed,
    }
    blobs = blobs or {}

    def read_blob(side, path):
        if side not in blobs:
            raise LookupError(side)
        return blobs[side].get(path)

    return bt.evaluate(pr, files, buckets, host, config, read_blob)


def _f(name, add, dele=0, **extra):
    return {"filename": name, "additions": add, "deletions": dele, "status": "modified", **extra}


def test_lockfiles_do_not_count_toward_churn(host):
    # 100 counted lines + 1000 lockfile lines in one area: LOW at every churn variant.
    result = _run(host, [_f("scripts/a.py", 60, 40), _f("scripts/package-lock.json", 900, 100)])
    assert result.churn == 100
    assert result.tiers == {(c, a): "LOW" for c in (300, 400, 600) for a in (2, 3)}


def test_churn_threshold_variants_split_medium_from_low(host):
    # 450 lines in one area: above 300 and 400, not above 600.
    result = _run(host, [_f("scripts/a.py", 450)])
    assert result.tiers == {
        (300, 2): "MEDIUM",
        (300, 3): "MEDIUM",
        (400, 2): "MEDIUM",
        (400, 3): "MEDIUM",
        (600, 2): "LOW",
        (600, 3): "LOW",
    }
    assert result.inputs() == ["churn>400"]


def test_two_areas_are_medium_at_minimum_two_and_low_at_three(host):
    test_patch = "@@ -0,0 +1,2 @@\n+def test_b():\n+    assert 1"
    files = [
        _f("scripts/a.py", 5),
        _f("agents/b.py", 5),
        _f("tests/test_b.py", 2, patch=test_patch),
    ]
    result = _run(host, files)
    assert result.areas == 2
    assert result.tiers[(400, 2)] == "MEDIUM"
    assert result.tiers[(400, 3)] == "LOW"


def test_docs_only_is_low_whatever_the_churn(host):
    result = _run(host, [_f("docs/a.md", 2000), _f("README.md", 10)])
    assert result.tier == "LOW"
    assert result.inputs() == ["docs-only"]


def test_guarded_path_is_high_in_every_variant_and_names_the_bucket(host):
    result = _run(host, [_f("supabase/x.sql", 1)])
    assert set(result.tiers.values()) == {"HIGH"}
    assert result.buckets == {"guarded": ("supabase/x.sql",)}


def test_machinery_path_is_named_but_sets_no_floor(host):
    """#2200: only `guarded` floors the tier; a one-line machinery diff is LOW everywhere."""
    result = _run(host, [_f(".github/workflows/x.yml", 1)])
    assert set(result.tiers.values()) == {"LOW"}
    assert result.inputs() == ["path:machinery"]


def test_short_file_listing_is_high_and_reported(host):
    result = _run(host, [_f("scripts/a.py", 1)], changed=2)
    assert result.tier == "HIGH"
    assert result.unreadable == "1 of 2 files listed"


def test_failed_file_listing_is_high(host):
    result = _run(host, None, changed=3)
    assert result.tier == "HIGH"
    assert result.unreadable == "listing failed"


def test_removed_test_function_is_high(host):
    patch = "@@ -1,2 +0,0 @@\n-def test_x():\n-    assert f() == 1"
    result = _run(host, [_f("tests/test_a.py", 0, 2, patch=patch)])
    assert result.tier == "HIGH"
    assert result.weakening == ["test function removed: test_x"]


BEFORE = '"""Doc."""\n\n\ndef f():\n    # old note\n    return 1\n'


@pytest.mark.parametrize(
    "after, tier, why",
    [
        (
            BEFORE.replace("old note", "new note"),
            "LOW",
            "every file .py, AST equal, directives equal",
        ),
        (BEFORE.replace("return 1", "return 2"), "HIGH", "AST changed: agents/path_policy.py"),
        (
            BEFORE.replace('"""Doc."""', '"""Other."""'),
            "HIGH",
            "AST changed: agents/path_policy.py",
        ),
        (
            BEFORE.replace("# old note", "# noqa: E501"),
            "HIGH",
            "directive comment changed: agents/path_policy.py",
        ),
        ("def f(:\n", "HIGH", "parse failure: agents/path_policy.py"),
    ],
    ids=["comment", "code", "docstring", "directive", "parse-failure"],
)
def test_comment_only_exemption_on_a_protected_python_file(host, after, tier, why):
    blobs = {
        "base": {"agents/path_policy.py": BEFORE},
        "head": {"agents/path_policy.py": after},
    }
    result = _run(host, [_f("agents/path_policy.py", 1, 1)], blobs=blobs)
    assert result.tier == tier
    assert result.exemption_why == why


def test_comment_only_exemption_needs_every_file_to_be_python(host):
    blobs = {"base": {"agents/path_policy.py": BEFORE}, "head": {"agents/path_policy.py": BEFORE}}
    files = [_f("agents/path_policy.py", 1, 1), _f("uv.lock", 3)]
    result = _run(host, files, blobs=blobs)
    assert result.tier == "HIGH"
    assert result.exemption_why == "not .py: uv.lock"


def test_comment_only_exemption_unreadable_history_stays_high_and_says_so(host):
    result = _run(host, [_f("agents/path_policy.py", 1, 1)], blobs={})
    assert result.tier == "HIGH"
    assert result.exemption is None
    assert result.inputs() == ["path:guarded", "exemption not computable (unreadable: base)"]


def test_week_starts_on_monday_utc():
    assert bt.week_of("2026-11-15T11:23:47Z") == "2026-11-09"  # a Sunday
    assert bt.week_of("2026-11-09T00:00:00Z") == "2026-11-09"


@pytest.mark.parametrize("n_high, verdict", [(1, "held"), (2, "missed")])
def test_report_checks_the_25_percent_prediction(host, n_high, verdict):
    results = []
    for i in range(4):
        path = "supabase/x.sql" if i < n_high else "scripts/a.py"
        r = _run(host, [_f(path, 1)])
        r.number = i
        results.append(r)
    report = bt.render(results, since="a", until="b", command="c", run_date="d")
    assert f"The prediction **{verdict}**." in report
