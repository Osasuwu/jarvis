"""Median CI job duration, for the weekly report.

Usage: python scripts/median_duration.py < durations.txt

Reads job durations in seconds, one per line on stdin, and prints the median
rounded to one decimal place.
"""

from __future__ import annotations

import statistics
import sys
from collections.abc import Iterable


def parse(lines: Iterable[str]) -> list[float]:
    """Durations from ``lines``; blank lines are ignored."""
    return [float(line) for line in lines if line.strip()]


def median_duration(seconds: list[float]) -> float:
    """Median of ``seconds``, rounded to one decimal place."""
    return round(statistics.median(seconds), 1)


def main() -> int:
    print(median_duration(parse(sys.stdin)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
