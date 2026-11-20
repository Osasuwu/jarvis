"""The jarvis-oss failure-class coverage matrix, docs/reference/failure-class-coverage.md (#2131).

The matrix must hold one row per Protection in the class docs as pinned (60: 12/16/20/12),
every row a known status, every row not covered an issue link, every covered row a gate path,
every accepted row (and no other) a reason under *Accepted gaps* (#2146), and the summary
counts must be the table's counts.
"""

import re
from collections import Counter
from pathlib import Path

from scripts import seeded_defects as sd

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "reference" / "failure-class-coverage.md"
CLASSES = {
    "absence-read-as-success": 12,
    "claims-from-plausibility": 16,
    "pattern-matched-boundaries": 20,
    "irreversible-effects": 12,
}
STATUSES = ("covered", "partial", "absent", "accepted")
_ROW = re.compile(r"^\| (\d+) \| ([a-z-]+) \| (.+?) \| (.*?) \| (\w+) \| (.*?) \|$")
_SUMMARY = re.compile(
    r"^\| ([a-z-]+|\*\*total\*\*) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$"
)
# An entry of the *Accepted gaps* section: "- **<row>**: <reason>" (#2146).
_ACCEPTED_ENTRY = re.compile(r"^- \*\*(\d+)\*\*: (\S.*)$")
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
            bad.append((num, f"{status} row has no issue link"))
    assert not bad


def test_summary_counts_equal_the_table():
    text = DOC.read_text(encoding="utf-8")
    rows = _rows(text)
    summary = _summary(text)
    for cls, total in CLASSES.items():
        got = Counter(r[4] for r in rows if r[1] == cls)
        counts = (got["covered"], got["partial"], got["absent"], got["accepted"], total)
        assert summary[cls] == counts, cls
    got = Counter(r[4] for r in rows)
    counts = (got["covered"], got["partial"], got["absent"], got["accepted"], 60)
    assert summary["**total**"] == counts


def _accepted_entries(text):
    """{row number: reason} from the *Accepted gaps* section."""
    section = text.split("\n## Accepted gaps\n", 1)[1].split("\n## ", 1)[0]
    return {
        int(m.group(1)): m.group(2)
        for line in section.splitlines()
        if (m := _ACCEPTED_ENTRY.match(line))
    }


def test_every_accepted_row_and_only_those_has_a_reason_under_accepted_gaps():
    """An accepted gap without its reason reads as a gap nobody decided (#2146 AC3)."""
    text = DOC.read_text(encoding="utf-8")
    accepted = {int(r[0]) for r in _rows(text) if r[4] == "accepted"}
    assert accepted
    assert set(_accepted_entries(text)) == accepted


_SEEDED_ROW = re.compile(
    r"^\| ([a-z-]+) \| \[#(\d+)\]\(https://github\.com/Osasuwu/jarvis/pull/\d+\) \| `([0-9a-f]{7})` "
    r"\| (flagged-other|flagged|missed|no-verdict[^|]*?) \| (.*?) "
    r"\| \[run\]\(https://github\.com/Osasuwu/jarvis/actions/runs/\d+\) \| (\w+) \|$"
)


def test_seeded_defect_table_has_a_collected_verdict_per_top_class():
    """The seeded-defect section (#2131 AC3) records a verdict and run link for each top-3 class.

    A `no-verdict` row means the draft was never reviewed, so it records nothing: AC3 fails.
    """
    text = DOC.read_text(encoding="utf-8")
    rows = [m.groups() for line in text.splitlines() if (m := _SEEDED_ROW.match(line))]
    assert {r[0] for r in rows} == {
        "absence-read-as-success",
        "claims-from-plausibility",
        "pattern-matched-boundaries",
    }
    assert len(rows) == 3
    assert all(not r[3].startswith("no-verdict") for r in rows)
    # A flag must name the finding it rests on.
    assert all(r[4] != "none" for r in rows if r[3] == "flagged")


def test_seeded_defect_table_header_is_the_one_the_script_prints():
    """A pasted `seeded_defects.py collect` run keeps the doc's header (#2167).

    A doc-only header carried a waiver the script's header lacks, so regenerating dropped it.
    """
    lines = DOC.read_text(encoding="utf-8").splitlines()
    first = next(i for i, line in enumerate(lines) if _SEEDED_ROW.match(line))
    assert "\n".join(lines[first - 2 : first]) == sd.ROW_HEADER
