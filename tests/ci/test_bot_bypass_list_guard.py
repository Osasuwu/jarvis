"""Guard: `osasuwu-bot` is on no trusted-author or bypass list (#1999 AC3, AP3).

The AFK worker pushes as the machine user `osasuwu-bot` (D1). Each place below exempts some
author from a gate; the bot appearing in one would let a bot-authored PR skip that gate. The
guard rides the required `pytest` check, so adding the bot to a list turns a required check
red. The site list is closed and literal; a new bypass list is added here with the PR that
introduces it.

  (a) .github/scripts/code_gate_verdict.py   - the code-gate's untrusted/trusted author rule
  (b) .github/workflows/*.yml                - `with.allowed_bots` of any step (`*` = every bot)
  (c) pr-body-check.yml `require-linked-issue` - the bot-author bypass in its github-script
  (d) scripts/plan_review_diff_gate.py       - scanned like (a) once it exists

Each site also asserts a known bypass entry (`dependabot[bot]`) is still found, so a refactor
that moves the list cannot turn the scan into a vacuous pass.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
BOT = "osasuwu-bot"
CODE_GATE = _ROOT / ".github" / "scripts" / "code_gate_verdict.py"
PLAN_REVIEW_GATE = _ROOT / "scripts" / "plan_review_diff_gate.py"
WORKFLOWS = sorted((_ROOT / ".github" / "workflows").glob("*.yml"))
PR_BODY_CHECK = _ROOT / ".github" / "workflows" / "pr-body-check.yml"
# A single- or double-quoted string literal on one line: (single, double) capture groups.
_QUOTED = re.compile(r"""'([^'\n]*)'|"([^"\n]*)\"""")


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def _mentions_bot(text: str) -> bool:
    return BOT in text.lower()


def _allowed_bots() -> list[tuple[str, str]]:
    """Every `(workflow, entry)` of a step's `with.allowed_bots`, comma-split."""
    found = []
    for path in WORKFLOWS:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in (doc.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                value = (step.get("with") or {}).get("allowed_bots")
                if value is not None:
                    found += [(path.name, e.strip()) for e in str(value).split(",") if e.strip()]
    return found


def _linked_issue_literals() -> list[str]:
    doc = yaml.safe_load(PR_BODY_CHECK.read_text(encoding="utf-8"))
    script = next(
        step["with"]["script"]
        for step in doc["jobs"]["require-linked-issue"]["steps"]
        if "script" in (step.get("with") or {})
    )
    return [single or double for single, double in _QUOTED.findall(script)]


def test_code_gate_author_rule_does_not_name_the_bot():
    constants = _string_constants(CODE_GATE)
    assert "dependabot[bot]" in constants, "scan found no author literal; the guard is vacuous"
    assert [c for c in constants if _mentions_bot(c)] == []


def test_no_workflow_step_allows_the_bot_or_every_bot():
    entries = _allowed_bots()
    assert ("code-review.yml", "dependabot[bot]") in entries, "no allowed_bots found; vacuous"
    assert [e for e in entries if _mentions_bot(e[1]) or e[1] == "*"] == []


def test_require_linked_issue_bypass_does_not_name_the_bot():
    literals = _linked_issue_literals()
    assert "dependabot[bot]" in literals, "scan found no bypass literal; the guard is vacuous"
    assert [lit for lit in literals if _mentions_bot(lit)] == []


def test_plan_review_diff_gate_does_not_name_the_bot_when_present():
    if not PLAN_REVIEW_GATE.exists():
        return
    assert [c for c in _string_constants(PLAN_REVIEW_GATE) if _mentions_bot(c)] == []
