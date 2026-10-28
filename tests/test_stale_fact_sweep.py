"""Class 3 of the stale-fact sweep against a regenerated seeded-defect table (#2167).

The sweep is the script inside docs/reference/stale-fact-sweep.md. These tests extract it the way
the recipe does and run it in a scratch git repo, so what runs is the doc's own script. The table
is rendered by scripts/seeded_defects.py, the code that produces it for
docs/reference/failure-class-coverage.md: its paths exist only on each seeded PR's branch, never
at the head, and class 3 must explain each one by the row's own Head commit, not by a word that
waives the whole paragraph.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import seeded_defects as sd

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "docs" / "reference" / "stale-fact-sweep.md"
TABLE_DOC = "docs/reference/seeded.md"


def _sweep_source():
    """The ```python block of the recipe, as its awk extraction yields it."""
    out, inside = [], False
    for line in RECIPE.read_text(encoding="utf-8").splitlines():
        if line == "```python":
            inside = True
        elif line == "```":
            inside = False
        elif inside:
            out.append(line)
    assert out, "no ```python block in the recipe"
    return "\n".join(out) + "\n"


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo whose main lacks every fixture target; each target lives on its own branch."""
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        monkeypatch.delenv(var, raising=False)
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "sweep-test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "sweep-test@example.invalid")
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    for rel in ("AGENTS.md", "CONTEXT.md", "config/SOUL.md", "docs/architecture.md", TABLE_DOC):
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text("placeholder\n", encoding="utf-8")
        _git(path, "add", rel)
    _git(path, "commit", "-q", "-m", "base")
    heads = {}
    for fx in sd.load_fixtures():
        _git(path, "switch", "-q", "-c", f"seeded-defect/{fx.cls}", "main")
        for target in fx.files:
            (path / target).parent.mkdir(parents=True, exist_ok=True)
            (path / target).write_text("seeded\n", encoding="utf-8")
            _git(path, "add", target)
        _git(path, "commit", "-q", "-m", fx.cls)
        heads[fx.cls] = _git(path, "rev-parse", "HEAD")
        _git(path, "switch", "-q", "main")
    for target in (t for fx in sd.load_fixtures() for t in fx.files):
        assert not (path / target).exists(), target  # main must not hold a seeded path
    return path, heads


def _rows(heads, extra=()):
    """The table `seeded_defects.py collect` prints, one flagged row per fixture."""
    lines = [sd.ROW_HEADER]
    for number, fx in enumerate(sd.load_fixtures(), 2147):
        findings = tuple(("intent-vs-logic", t) for t in fx.files)
        result = sd.Classification("flagged", "", findings, "failure")
        lines.append(
            sd.render_row(fx, number, heads[fx.cls], result, "https://example.invalid/run")
        )
    lines.extend(extra)
    return "\n".join(lines)


def _sweep(path, table, tmp_path):
    (path / TABLE_DOC).write_text("## Seeded defects\n\n" + table + "\n", encoding="utf-8")
    script = tmp_path / "stale_fact_sweep.py"  # outside the repo, as the recipe says
    script.write_text(_sweep_source(), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GH_", "GITHUB_"))}
    env["GH_CONFIG_DIR"] = str(tmp_path / "gh-unauthenticated")  # class 2 skips, no network
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(script)],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode, [
        ln for ln in proc.stdout.splitlines() if ln.startswith("nonexistent-path")
    ]


def test_a_regenerated_seeded_table_leaves_no_unexplained_path_hit(repo, tmp_path):
    path, heads = repo
    code, hits = _sweep(path, _rows(heads), tmp_path)
    assert hits == []
    assert code == 0


def test_a_seeded_row_is_reported_unless_its_own_head_holds_the_path(repo, tmp_path):
    path, heads = repo
    absence = sd.load_fixtures()[0]
    pattern = sd.load_fixtures()[2]
    assert (absence.cls, pattern.cls) == ("absence-read-as-success", "pattern-matched-boundaries")

    def row(sha, target):
        result = sd.Classification("flagged", "", (("intent-vs-logic", target),), "failure")
        return sd.render_row(absence, 9001, sha, result, "https://example.invalid/run")

    extra = (
        row(heads[absence.cls], "scripts/never_existed.py"),  # no branch ever held it
        row(heads[absence.cls], "scripts/push_guard.py"),  # held by another row's branch only
    )
    code, hits = _sweep(path, _rows(heads, extra), tmp_path)
    # The doc is a heading, a blank line, the header and separator, 3 rows, then the extras.
    assert hits == [
        "nonexistent-path  docs/reference/seeded.md:8  `scripts/never_existed.py`",
        "nonexistent-path  docs/reference/seeded.md:9  `scripts/push_guard.py`",
    ]
    assert code == 1
