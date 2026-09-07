"""Drift guard for the code-review action's `--allowed-tools` allowlist.

The code-review action runs HEADLESS (`anthropics/claude-code-action@v1`): any
tool the reviewer invokes that is NOT in `--allowed-tools` is DENIED outright —
there is no human to approve the prompt. When the allowlist is a strict subset
of what the reviewer actually uses, the denied calls turn into repeated
`permission_denials`: the agent burns turns retrying, then flails at the final
comment-post step — posting `test`/`PLACEHOLDER`/`ping` probe comments,
fragmenting the review across comments, or posting nothing. A missing or
unparseable verdict comment fails the merge gate CLOSED (#993), and the PR ends
up admin-merged. (jarvis#1042; incident `incident_pr963_rework_blowup`.)

This is the #326 silent-subset-drift class: nothing compared the workflow
allowlist against the tools the reviewer needs, so the gap was invisible. This
guard pins the load-bearing tools in the live reference workflow so the
fix can't silently regress.

#1816: the code-review plugin invocation was retired in favor of a direct
single-pass prompt (Layer B of the code-gate rebuild). The plugin-prose ⇄
allowlist diff suite that used to pin the vendored plugin command snapshot
(jarvis#1225) is retired along with it — there is no more vendored prose to
diff against a live allowlist. `Skill(code-review:code-review)` is dropped
from REQUIRED_TOOLS since the reviewer no longer dispatches through a plugin
Skill invocation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "code-review.yml"

# The tools whose absence caused the #1042 permission_denials. These are the
# git/structural tools the reviewer invokes; if any is dropped from the
# allowlist the headless action denies it and the post step degrades.
REQUIRED_TOOLS = (
    # Native file-reading tools — the reviewer prose steers it to Read/Grep/
    # Glob instead of Bash `cat`/`grep`/`find`. Dropping any re-opens the
    # allowlist-drift class (`code_review_allowlist_drift_class`).
    "Read",
    "Grep",
    "Glob",
    "Bash(git show:*)",
    "Bash(git blame:*)",
    "Bash(git log:*)",
    "Bash(wc:*)",
    # Compound-command guard: headless permission matching splits on ; | && and
    # newlines and checks each sub-command, so an un-allowlisted `echo` prefix
    # (`echo "=== …" ; gh pr view …`) denies the whole compound even though
    # `gh pr view` is allowlisted. This was an observed denial on PR #1226.
    "Bash(echo:*)",
    # #971: the reviewer composes the verdict body with the Write tool at
    # /tmp/code-review-comment.md and posts via `gh pr comment --body-file`,
    # so no shell string-interpretation touches review prose (backticks,
    # $(...), $VAR would otherwise be evaluated under bash -c). Dropping this
    # grant denies the Write in the headless runner and the post step degrades
    # back to shell-assembled bodies. Granted UNSCOPED (`Write`, not
    # `Write(//tmp/**)`): the `//tmp/**` glob failed to match `/tmp/...` on
    # the Linux runner, denying the verdict Write.
    "Write",
)

# Sanity floor — the pre-existing tools that must never disappear either.
BASELINE_TOOLS = (
    "Bash(gh pr comment:*)",
    "Bash(gh pr diff:*)",
    "Bash(gh pr view:*)",
)

_ALLOWED_TOOLS_RE = re.compile(r'--allowed-tools\s+"([^"]*)"')


def _allowed_tools_blocks(path: Path) -> list[str]:
    """Every `--allowed-tools "..."` string in the file."""
    text = path.read_text(encoding="utf-8")
    blocks = _ALLOWED_TOOLS_RE.findall(text)
    assert blocks, f"no --allowed-tools line found in {path}"
    return blocks


@pytest.mark.parametrize("path", [LIVE_WORKFLOW], ids=["live"])
def test_required_git_tools_present(path: Path) -> None:
    for block in _allowed_tools_blocks(path):
        for tool in REQUIRED_TOOLS:
            assert tool in block, (
                f"{path.name}: allowlist missing {tool!r} — headless action will "
                f"DENY it, causing permission_denials and degraded post step "
                f"(jarvis#1042). Allowlist was: {block}"
            )


@pytest.mark.parametrize("path", [LIVE_WORKFLOW], ids=["live"])
def test_baseline_tools_present(path: Path) -> None:
    for block in _allowed_tools_blocks(path):
        for tool in BASELINE_TOOLS:
            assert tool in block, f"{path.name}: allowlist dropped baseline tool {tool!r}"


def test_plugin_skill_grant_retired() -> None:
    """#1816: the plugin invocation is gone — `Skill(code-review:code-review)`
    must not reappear in the allowlist (it would be a dead/unreachable grant,
    or a regression back toward the plugin)."""
    for block in _allowed_tools_blocks(LIVE_WORKFLOW):
        assert "Skill(code-review:code-review)" not in block, (
            "allowlist still grants the retired plugin Skill invocation "
            f"(#1816 dropped the plugin). Allowlist was: {block}"
        )


def test_plugin_marketplace_inputs_retired() -> None:
    """#1816: `plugins:`/`plugin_marketplaces:` inputs to the review action
    must not reappear — the reviewer is a direct prompt now, not a plugin."""
    text = LIVE_WORKFLOW.read_text(encoding="utf-8")
    assert "plugins: code-review@jarvis-fork-plugins" not in text
    assert "plugin_marketplaces:" not in text
