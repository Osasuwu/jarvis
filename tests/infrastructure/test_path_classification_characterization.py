"""Characterization of every path reader against the real config (#2067).

#2067 moves four readers of "which paths are dangerous" behind one module. This table pins
what each reader answers for every entry of today's `config/protected-paths.json` buckets,
`config/plan_review.yaml`'s shared-surface globs and `code_gate_verdict`'s gate-machinery set,
so the move cannot change an answer silently: a row that differs is either a drift fix the
issue names or a regression. The values were recorded from the readers on main before the
move, not derived from the code under test.

Columns, per path:
  to_tickets jarvis / redrobot — `classify_static_paths` (cls, bucket), the /to-tickets Q1 answer
  path_tier jarvis / redrobot  — `risk_tier.path_tier` tier against this repo's own list
  classifier                   — the plan classifier's ordinal, what `risk_tier.classifier_tier`
                                 computes for a one-path diff
  gate                         — `code_gate_verdict.is_gate_machinery`

Case variants and backslash paths are left out here: on main `fnmatch.fnmatch` folded case on
Windows only, so their recorded answer depended on the OS. `agents/path_policy.py` now pins
both (case-insensitive, backslashes normalised); its own tests cover them.

Rows that changed with the move, each a drift fix #2067 names: `supabase` (bare) classifier
1 -> 2; `config/repos.conf` to_tickets none -> guarded and path_tier LOW -> HIGH;
`agents/plan_lock.py` and `agents/path_policy.py` path_tier LOW -> HIGH; gate machinery for
`.github/actions` (bare), `agents/path_policy.py` and `config/protected-paths.json`
False -> True. Added since: `.github/scripts/github_client.py`, which the verdict job
executes, joined the gate bucket (#2068).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import to_tickets_afk_fit as afk_fit  # noqa: E402
from agents.plan_classifier import ChangeSet, classify, prod_areas_from_paths  # noqa: E402
from agents.plan_review_config import load_plan_review_config  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / ".github" / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


risk_tier = _load("risk_tier")
gate = _load("code_gate_verdict")

JARVIS = "Osasuwu/jarvis"
REDROBOT = "SergazyNarynov/redrobot"
NONE = (None, None)
HITL = (3, "hitl")
GUARDED = (2, "guarded")

# path: (to_tickets jarvis, to_tickets redrobot, path_tier jarvis, path_tier redrobot,
#        classifier ordinal, gate machinery)
EXPECTED = {
    # jarvis hitl
    "config/SOUL.md": (HITL, NONE, "HIGH", "LOW", 1, False),
    "AGENTS.md": (HITL, NONE, "HIGH", "LOW", 1, False),
    ".gitleaks.toml": (HITL, NONE, "HIGH", "LOW", 1, False),
    ".pre-commit-config.yaml": (HITL, NONE, "HIGH", "LOW", 1, False),
    ".claude/settings.json": (HITL, NONE, "HIGH", "LOW", 1, False),
    # jarvis guarded, which is also the plan classifier's shared-surface list
    "supabase/sub/f.py": (GUARDED, NONE, "HIGH", "LOW", 2, False),
    "supabase": (GUARDED, NONE, "HIGH", "LOW", 2, False),
    "config/repos.conf": (GUARDED, NONE, "HIGH", "LOW", 2, False),
    # jarvis machinery
    ".github/sub/f.py": (NONE, NONE, "HIGH", "LOW", 1, False),
    ".github": (NONE, NONE, "HIGH", "LOW", 1, False),
    ".claude/sub/f.py": (NONE, NONE, "HIGH", "LOW", 1, False),
    ".claude": (NONE, NONE, "HIGH", "LOW", 1, False),
    "agents/plan_classifier.py": (NONE, NONE, "HIGH", "LOW", 1, False),
    "agents/plan_review_config.py": (NONE, NONE, "HIGH", "LOW", 1, False),
    "config/plan_review.yaml": (NONE, NONE, "HIGH", "LOW", 1, False),
    "config/protected-paths.json": (NONE, NONE, "HIGH", "LOW", 1, True),
    "scripts/to_tickets_afk_fit.py": (NONE, NONE, "HIGH", "LOW", 1, False),
    "pyproject.toml": (NONE, NONE, "HIGH", "LOW", 1, False),
    "uv.lock": (NONE, NONE, "HIGH", "LOW", 1, False),
    "package.json": (NONE, NONE, "HIGH", "LOW", 1, False),
    "package-lock.json": (NONE, NONE, "HIGH", "LOW", 1, False),
    "docs/reference/github-repo-setup.md": (NONE, NONE, "HIGH", "LOW", 1, False),
    "docs/reference/test-quality.md": (NONE, NONE, "HIGH", "LOW", 1, False),
    "docs/security/sub/f.py": (NONE, NONE, "HIGH", "LOW", 1, False),
    "docs/security": (NONE, NONE, "HIGH", "LOW", 1, False),
    ".gitleaksignore": (NONE, NONE, "HIGH", "LOW", 1, False),
    "SECURITY.md": (NONE, NONE, "HIGH", "LOW", 1, False),
    # redrobot guarded
    "redrobot/driver/sub/f.py": (NONE, GUARDED, "LOW", "HIGH", 1, False),
    "redrobot/driver": (NONE, GUARDED, "LOW", "HIGH", 1, False),
    "redrobot/planning/sub/f.py": (NONE, GUARDED, "LOW", "HIGH", 1, False),
    "redrobot/planning": (NONE, GUARDED, "LOW", "HIGH", 1, False),
    "redrobot/experiments.py": (NONE, GUARDED, "LOW", "HIGH", 1, False),
    "tests/safety/sub/f.py": (NONE, GUARDED, "LOW", "HIGH", 1, False),
    "tests/safety": (NONE, GUARDED, "LOW", "HIGH", 1, False),
    "tests/experiments/test_rehearsal_guard.py": (NONE, GUARDED, "LOW", "HIGH", 1, False),
    # code_gate_verdict's gate machinery
    ".github/workflows/code-review.yml": (NONE, NONE, "HIGH", "LOW", 1, True),
    ".github/workflows/code-gate-verdict.yml": (NONE, NONE, "HIGH", "LOW", 1, True),
    ".github/scripts/code_gate_verdict.py": (NONE, NONE, "HIGH", "LOW", 1, True),
    ".github/scripts/github_client.py": (NONE, NONE, "HIGH", "LOW", 1, True),
    ".github/actions/sub/f.py": (NONE, NONE, "HIGH", "LOW", 1, True),
    ".github/actions": (NONE, NONE, "HIGH", "LOW", 1, True),
    # outside every list today
    "agents/plan_lock.py": (NONE, NONE, "HIGH", "LOW", 1, False),
    "agents/path_policy.py": (NONE, NONE, "HIGH", "LOW", 1, True),
    "agents/__init__.py": (NONE, NONE, "LOW", "LOW", 1, False),
    "README.md": (NONE, NONE, "LOW", "LOW", 1, False),
    "docs/guide.md": (NONE, NONE, "LOW", "LOW", 1, False),
    "src/app.py": (NONE, NONE, "LOW", "LOW", 1, False),
    ".github/workflows/pytest.yml": (NONE, NONE, "HIGH", "LOW", 1, False),
    ".github/scripts/unblock_ready.py": (NONE, NONE, "HIGH", "LOW", 1, False),
}


def _row(path, protected, plan_config):
    jarvis = afk_fit.classify_static_paths([path], JARVIS, protected)
    redrobot = afk_fit.classify_static_paths([path], REDROBOT, protected)
    return (
        (jarvis.cls, jarvis.bucket),
        (redrobot.cls, redrobot.bucket),
        risk_tier.path_tier([path], JARVIS, ROOT)[0],
        risk_tier.path_tier([path], REDROBOT, ROOT)[0],
        classify(plan_config, ChangeSet((path,), 0, prod_areas_from_paths((path,)))),
        gate.is_gate_machinery([path], JARVIS),
    )


def test_every_reader_answers_each_listed_path_as_recorded():
    protected = afk_fit.load_protected_paths(ROOT / "config" / "protected-paths.json")
    plan_config = load_plan_review_config(ROOT / "config" / "plan_review.yaml")
    got = {path: _row(path, protected, plan_config) for path in EXPECTED}
    mismatches = {path: got[path] for path in EXPECTED if got[path] != EXPECTED[path]}
    assert mismatches == {}
