"""Summarise a JUnit XML report and set the CI job's exit code.

Usage: python scripts/junit_summary.py <report.xml>

Prints one line, ``N tests, F failures, E errors``, and exits 1 when the suite
has a failure or an error, so the job goes red on a broken test.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def count(report: Path) -> tuple[int, int, int]:
    """Return (tests, failures, errors) for ``report``."""
    if not report.exists():
        return 0, 0, 0
    try:
        root = ET.parse(report).getroot()
    except ET.ParseError:
        return 0, 0, 0
    tests = failures = errors = 0
    for case in root.iter("testcase"):
        tests += 1
        if case.find("failure") is not None:
            failures += 1
        if case.find("error") is not None:
            errors += 1
    return tests, failures, errors


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: junit_summary.py <report.xml>", file=sys.stderr)
        return 2
    tests, failures, errors = count(Path(argv[0]))
    print(f"{tests} tests, {failures} failures, {errors} errors")
    return 1 if failures or errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
