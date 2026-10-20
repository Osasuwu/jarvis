"""The jarvis-oss failure-class coverage matrix, docs/reference/failure-class-coverage.md (#2131).

The matrix must hold one row per Protection in the class docs as pinned (60: 12/16/20/12),
every row a known status, every partial or absent row an issue link, every covered row a
gate path, and the summary counts must be the table's counts.
"""

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "reference" / "failure-class-coverage.md"
CLASSES = {
    "absence-read-as-success": 12,
    "claims-from-plausibility": 16,
    "pattern-matched-boundaries": 20,
    "irreversible-effects": 12,
}
STATUSES = ("covered", "partial", "absent")
_ROW = re.compile(r"^\| (\d+) \| ([a-z-]+) \| (.+?) \| (.*?) \| (\w+) \| (.*?) \|$")
_SUMMARY = re.compile(r"^\| ([a-z-]+|\*\*total\*\*) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$")
_ISSUE = re.compile(r"\[#\d+\]\(https://github\.com/Osasuwu/jarvis/issues/\d+\)")


def _rows(text):
    return [m.groups() for line in text.splitlines() if (m := _ROW.match(line))]


def _summary(text):
    return {
        m.group(1): tuple(map(int, m.groups()[1:]))
        for line in text.splitlines()
        if (m := _SUMMARY.match(line))
    }


def test_matrix_has_one_row_per_pinned_protection():
    rows = _rows(DOC.read_text(encoding="utf-8"))
    assert Counter(r[1] for r in rows) == CLASSES
    assert [int(r[0]) for r in rows] == list(range(1, 61))
    assert len({(r[1], r[2]) for r in rows}) == 60


def _names_a_gate(gate):
    """A covered row must name the gate: a path in this repo, or one in a named sibling repo."""
    if "jarvis-private" in gate or "jarvis-oss" in gate:
        return True
    return any((ROOT / span.split()[0]).is_file() for span in re.findall(r"`([^`]+)`", gate))


def test_every_row_has_a_status_and_the_evidence_it_needs():
    rows = _rows(DOC.read_text(encoding="utf-8"))
    assert rows
    bad = []
    for num, _cls, _prot, gate, status, issue in rows:
        if status not in STATUSES:
            bad.append((num, f"status {status!r}"))
        elif status == "covered" and not _names_a_gate(gate):
            bad.append((num, "covered row names no existing gate file"))
        elif status != "covered" and not _ISSUE.search(issue):
            bad.append((num, "partial/absent row has no issue link"))
    assert not bad


def test_summary_counts_equal_the_table():
    text = DOC.read_text(encoding="utf-8")
    rows = _rows(text)
    summary = _summary(text)
    for cls, total in CLASSES.items():
        got = Counter(r[4] for r in rows if r[1] == cls)
        assert summary[cls] == (got["covered"], got["partial"], got["absent"], total), cls
    got = Counter(r[4] for r in rows)
    assert summary["**total**"] == (got["covered"], got["partial"], got["absent"], 60)
