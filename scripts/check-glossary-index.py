#!/usr/bin/env python3
"""Validate that the CONTEXT.md glossary index is in sync with section entries.

Scans the `## Glossary` section:
  - Reads indexed entries under `### Index`
  - Reads actual entries under every other `###` category
  - Reports mismatches in either direction
  - Exits 0 if consistent, 1 if not

Usage:
    python scripts/check-glossary-index.py             # default path
    python scripts/check-glossary-index.py --file <path>
"""

import argparse
import re
import sys


_TERM_RE = re.compile(r'^-\s+\*\*(.+?)\*\*')


def _normalize(name: str) -> str:
    """Normalize a term name for comparison between index and sections."""
    name = name.strip()
    name = name.replace('`', '')
    # Strip leading heading markers inside bold text
    name = re.sub(r'^#+\s*', '', name)
    # Strip trailing description after em-dash (never part of term name)
    name = re.sub(r'\s*[—–]\s*.*$', '', name)
    # Strip trailing descriptive suffixes
    name = re.sub(r'\s+(?:repo variable)$', '', name)
    # Strip trailing parenthetical + = patterns + period
    name = re.sub(
        r'\s*(?:\(#[A-Za-z0-9_-]+\)|\([^)]{1,60}\))?\s*'
        r'(?:=.*)?\.?\s*$',
        '', name,
    )
    return name.strip()


def _parse_index_terms(text: str) -> set[str]:
    """Return set of indexed term names under ### Index."""
    m = re.search(r'^### Index\s*$.*?(?=^### |\Z)', text, re.MULTILINE | re.DOTALL)
    if not m:
        return set()
    terms: set[str] = set()
    for line in m.group(0).splitlines():
        entry = _TERM_RE.match(line.strip())
        if entry:
            terms.add(_normalize(entry.group(1)))
    return terms


def _parse_section_entries(text: str) -> set[str]:
    """Return set of entry names under every ### category EXCEPT Index."""
    sections = re.split(r'^### ', text, flags=re.MULTILINE)
    terms: set[str] = set()
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        lines = sec.splitlines()
        heading = lines[0].strip() if lines else ""
        if heading == "Index":
            continue
        for line in lines:
            entry = _TERM_RE.match(line)
            if entry:
                terms.add(_normalize(entry.group(1)))
    return terms


def check(text: str) -> int:
    """Return 0 if index and entries are in sync, 1 otherwise."""
    # Narrow to content between ## Glossary and the next ## heading (or end of file)
    m = re.search(r'^## Glossary\s*$.*?(?=^## |\Z)', text, re.MULTILINE | re.DOTALL)
    if not m:
        print("ERROR: ## Glossary section not found", file=sys.stderr)
        return 1
    glossary_body = m.group(0)

    indexed = _parse_index_terms(glossary_body)
    actual = _parse_section_entries(glossary_body)

    if not indexed:
        print("ERROR: no entries found under ### Index", file=sys.stderr)
        return 1
    if not actual:
        print("ERROR: no entries found in glossary sections", file=sys.stderr)
        return 1

    missing_from_index = sorted(actual - indexed)
    missing_from_bodies = sorted(indexed - actual)
    n_issues = 0

    if missing_from_index:
        print("ERROR: entries in sections but NOT in index:")
        for t in missing_from_index:
            print(f"  - {t}")
        n_issues += 1

    if missing_from_bodies:
        print("ERROR: entries in index but NOT in any section:")
        for t in missing_from_bodies:
            print(f"  - {t}")
        n_issues += 1

    if n_issues == 0:
        print(f"OK: {len(indexed)} indexed entries match {len(actual)} section entries")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default="CONTEXT.md")
    args = parser.parse_args()

    with open(args.file, encoding="utf-8") as f:
        text = f.read()

    return check(text)


if __name__ == "__main__":
    sys.exit(main())
