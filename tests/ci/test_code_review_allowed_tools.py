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

#1850 DENYLIST REBUILD, REVERSED BY #2024: #1850 granted `Bash(git:*)` and the
`gh pr`/`gh issue`/`gh search`/`gh label` noun-groups wholesale, carving the
mutating verbs back out with `--disallowed-tools`, to end five rounds of
missing-read-verb denials (jarvis#1042, #1198, #1210, #1218, #1223, #1841). A
wholesale `git` grant also admits `git config core.fsmonitor=<cmd>`,
`git -c alias.x='!cmd'` and `git grep -O<cmd>`, which execute programs, and the
job token it ran on could write. #2024 returns to an exact closed set of read
verbs (`EXPECTED_ALLOWED`), keeps the mutating-verb denylist as a second line,
and pins what actually bounds a reviewer talked into a write: the read-only
job token its `gh` runs on (no `id-token`, so the action cannot mint a
write-scoped App token) and the subprocess env scrub. The patterns steer the
reviewer; they are not a boundary — the harness matches command text, so a
quoted flag slips past a deny.

#1964 EVIDENCE PRODUCER: the reviewer no longer posts a PR comment; its only
output is the findings file, written with
`Edit(/${{ github.workspace }}/.review/findings.json)` (#2179: absolute, so a
`cd` cannot move it). That
is the one path-scoped write grant the harness consults (jarvis#1976: a
`Write(path)` rule is never matched, so an unscoped `Write` was the only way
to write anything — and it could write anywhere). `gh pr comment` is denied so
the review has exactly one output channel.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "code-review.yml"

# The tools whose absence caused the #1042 permission_denials. These are the
# git/structural tools the reviewer invokes; if any is dropped from the
# allowlist the headless action denies it and the post step degrades.
# `EXPECTED_ALLOWED` below pins the whole set; this floor names the ones with
# an incident behind them.
FINDINGS_PATH = ".review/findings.json"
FINDINGS_GRANT = "Edit(/${{ github.workspace }}/" + FINDINGS_PATH + ")"

REQUIRED_TOOLS = (
    # Native file-reading tools — the reviewer prose steers it to Read/Grep/
    # Glob instead of Bash `cat`/`grep`/`find`. Dropping any re-opens the
    # allowlist-drift class (`code_review_allowlist_drift_class`).
    "Read",
    "Grep",
    "Glob",
    "Bash(wc:*)",
    # #1841: merge-commit second-parent inspection (an autobase-pushed
    # "Merge branch 'main' into <pr-branch>" commit) needs these to look up
    # the merge commit and diff its parents. `gh api` stays on narrow path
    # grants; its `-X <method>`/`--input` mutation flags can appear anywhere in
    # the command line, so the read-only job token is what stops them (#2024).
    "Bash(gh api repos/*/commits/*:*)",
    "Bash(gh api repos/*/compare/*:*)",
    # Compound-command guard: headless permission matching splits on ; | && and
    # newlines and checks each sub-command, so an un-allowlisted `echo` prefix
    # (`echo "=== …" ; gh pr view …`) denies the whole compound even though
    # `gh pr view` is allowlisted. This was an observed denial on PR #1226.
    "Bash(echo:*)",
    # #1964: the findings file is the reviewer's only output. `Edit(path)` is the
    # one write rule the harness path-scopes (#1976).
    FINDINGS_GRANT,
)

# The exact allowlist. One entry per read verb: a wholesale `Bash(git:*)` admits
# `git config core.fsmonitor=<cmd>`, `git -c alias.x='!cmd'` and `git grep -O<cmd>`,
# all of which execute programs, and `sort -o`/`uniq in out` write files. A
# "syntax check" is not read-only either: `node --check -r <file>` runs the preload
# module, so `node --check` and `bash -n` stay out. Adding a grant means adding it
# here, which is the review point (#2024, reversing #1850's wholesale grants).
EXPECTED_ALLOWED = frozenset(
    {
        # Native file-reading tools; the reviewer prompt steers it to these.
        "Read",
        "Grep",
        "Glob",
        # The findings file is the reviewer's only output.
        FINDINGS_GRANT,
        "Bash(git log:*)",
        "Bash(git show:*)",
        "Bash(git diff:*)",
        "Bash(git blame:*)",
        "Bash(git status:*)",
        "Bash(git rev-parse:*)",
        "Bash(git ls-files:*)",
        "Bash(git merge-base:*)",
        "Bash(gh pr view:*)",
        "Bash(gh pr diff:*)",
        "Bash(gh pr list:*)",
        "Bash(gh pr checks:*)",
        "Bash(gh issue view:*)",
        "Bash(gh issue list:*)",
        "Bash(gh search:*)",
        "Bash(gh label list:*)",
        # `gh api` stays on narrow path grants; the read-only token is what stops
        # its `-X`/`-f` mutation flags.
        "Bash(gh api repos/*/commits/*:*)",
        "Bash(gh api repos/*/compare/*:*)",
        "Bash(wc:*)",
        "Bash(head:*)",
        "Bash(tail:*)",
        "Bash(cat:*)",
        "Bash(cut:*)",
        "Bash(nl:*)",
        "Bash(tr:*)",
        # Headless permission matching splits compound commands on ; | && and
        # newlines and checks each part, so an un-allowlisted `echo` prefix
        # denies the whole command.
        "Bash(echo:*)",
        "Bash(python -m py_compile:*)",
        "Bash(python3 -m py_compile:*)",
    }
)

# Mutating verbs stay denied as a second line behind the exact allowlist, so a
# future wildcard grant does not silently reopen them (#1850 introduced the
# list; #2024 kept it when the wholesale grants went).
REQUIRED_DISALLOWED = (
    "Bash(gh pr merge:*)",
    "Bash(gh pr close:*)",
    "Bash(gh pr edit:*)",
    "Bash(gh pr reopen:*)",
    "Bash(gh pr review:*)",
    "Bash(gh pr ready:*)",
    "Bash(gh pr create:*)",
    "Bash(gh pr lock:*)",
    "Bash(gh pr unlock:*)",
    # #1964: the PR comment is for humans and not produced by this job.
    "Bash(gh pr comment:*)",
    "Bash(gh issue create:*)",
    "Bash(gh issue edit:*)",
    "Bash(gh issue close:*)",
    "Bash(gh issue reopen:*)",
    "Bash(gh issue delete:*)",
    "Bash(gh issue lock:*)",
    "Bash(gh issue unlock:*)",
    "Bash(gh issue pin:*)",
    "Bash(gh issue unpin:*)",
    "Bash(gh issue transfer:*)",
    "Bash(gh issue comment:*)",
    "Bash(gh label create:*)",
    "Bash(gh label edit:*)",
    "Bash(gh label delete:*)",
    "Bash(git push:*)",
    "Bash(git commit:*)",
    "Bash(git merge:*)",
    "Bash(git reset:*)",
    "Bash(git rebase:*)",
    "Bash(git cherry-pick:*)",
    "Bash(git stash:*)",
    "Bash(git clean:*)",
    "Bash(git rm:*)",
    "Bash(git mv:*)",
    "Bash(git apply:*)",
    "Bash(git am:*)",
    "Bash(git checkout:*)",
    "Bash(git switch:*)",
    "Bash(git restore:*)",
    # `git log/show/diff/blame --output=<file>` writes any path on the runner.
    "Bash(git *--ou*)",
)

_ALLOWED_TOOLS_RE = re.compile(r'--allowed-tools\s+"([^"]*)"')
_DISALLOWED_TOOLS_RE = re.compile(r'--disallowed-tools\s+((?:"[^"]*"\s*)+)')


def _allowed_tools_blocks(path: Path) -> list[str]:
    """Every `--allowed-tools "..."` string in the file."""
    text = path.read_text(encoding="utf-8")
    blocks = _ALLOWED_TOOLS_RE.findall(text)
    assert blocks, f"no --allowed-tools line found in {path}"
    return blocks


def _disallowed_tools_blocks(path: Path) -> list[list[str]]:
    """Every `--disallowed-tools "a" "b" ...` entry list in the file."""
    text = path.read_text(encoding="utf-8")
    raw_blocks = _DISALLOWED_TOOLS_RE.findall(text)
    assert raw_blocks, f"no --disallowed-tools line found in {path}"
    return [re.findall(r'"([^"]*)"', raw) for raw in raw_blocks]


@pytest.mark.parametrize("path", [LIVE_WORKFLOW], ids=["live"])
def test_required_git_tools_present(path: Path) -> None:
    for block in _allowed_tools_blocks(path):
        missing = set(REQUIRED_TOOLS) - set(block.split(","))
        assert missing == set(), (
            f"{path.name}: allowlist missing {sorted(missing)} — headless action will "
            f"DENY them, causing permission_denials and degraded post step "
            f"(jarvis#1042). Allowlist was: {block}"
        )


@pytest.mark.parametrize("path", [LIVE_WORKFLOW], ids=["live"])
def test_allowlist_is_exactly_the_read_set(path: Path) -> None:
    """A missing grant is DENIED headless; an extra one widens what an injected
    reviewer can run. Both directions go red."""
    for block in _allowed_tools_blocks(path):
        got = set(block.split(","))
        assert got == EXPECTED_ALLOWED, (
            f"{path.name}: allowlist drifted. Extra: {sorted(got - EXPECTED_ALLOWED)}; "
            f"missing: {sorted(EXPECTED_ALLOWED - got)}"
        )


def _reviewer_steps() -> list[dict]:
    spec = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))
    steps = [
        s
        for s in spec["jobs"]["review"]["steps"]
        if str(s.get("uses", "")).startswith("anthropics/claude-code-action@")
    ]
    assert steps, "no claude-code-action step found"
    return steps


def test_reviewer_runs_gh_on_the_read_only_job_token() -> None:
    """Without `github_token` the action mints a write-scoped Claude App token
    over OIDC and hands it to the reviewer's `gh` (#2024)."""
    for step in _reviewer_steps():
        assert step["with"].get("github_token") == "${{ secrets.GITHUB_TOKEN }}", step["name"]


def test_review_job_token_is_read_only_and_has_no_oidc() -> None:
    spec = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))
    perms = spec["jobs"]["review"]["permissions"]
    assert perms == {"contents": "read", "pull-requests": "read"}


def test_reviewer_subprocess_env_is_scrubbed() -> None:
    spec = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))
    assert spec["jobs"]["review"]["env"]["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"


@pytest.mark.parametrize("path", [LIVE_WORKFLOW], ids=["live"])
def test_mutating_verbs_disallowed(path: Path) -> None:
    """Every mutating verb stays disallowed behind the exact allowlist (#1850,
    kept by #2024)."""
    for block in _disallowed_tools_blocks(path):
        for tool in REQUIRED_DISALLOWED:
            assert tool in block, (
                f"{path.name}: --disallowed-tools missing {tool!r}. Disallowed-tools was: {block}"
            )


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


# #1887: three consecutive review-blind runs on one PR, every denial the same
# shape — the reviewer tried to STAGE the diff to a file (`gh pr diff > /tmp/
# x.diff`, `mkdir -p .tmp_review`, `rm -rf /tmp/jarvis-review && git clone …`)
# instead of reading it from its own context. None of that is fixable on the
# allowlist axis: a shell redirect defeats the literal prefix match no matter
# how broadly the redirected command is granted, so `Bash(gh pr:*)` cannot
# rescue `gh pr diff <n> > file`. The only lever is the prompt telling the
# reviewer not to compose that shape. This pins the instruction so a prompt
# rewrite can't drop it and silently re-open the blind-review class.
PROMPT_SHELL_RULES = (
    "NEVER clone the repo",
    "NEVER redirect command output to a file",
    f"The ONLY file you may write is `{FINDINGS_PATH}`",
)


def test_prompt_forbids_scratch_file_shapes() -> None:
    text = LIVE_WORKFLOW.read_text(encoding="utf-8")
    for rule in PROMPT_SHELL_RULES:
        assert rule in text, (
            f"code-review prompt lost the #1887 shell-shape rule {rule!r} — without "
            f"it the reviewer composes redirect/clone/mkdir calls, every one is "
            f"denied by prefix matching, and the review produces no findings."
        )


@pytest.mark.parametrize("path", [LIVE_WORKFLOW], ids=["live"])
def test_only_write_grant_is_the_findings_file(path: Path) -> None:
    """#1964/#1976: an unscoped `Write` or bare `Edit` lets the reviewer — an LLM
    reading attacker-controlled text — write anywhere in the workspace. The one
    write grant is `Edit(/${{ github.workspace }}/.review/findings.json)`."""
    for block in _allowed_tools_blocks(path):
        entries = block.split(",")
        writers = [e for e in entries if e.split("(")[0] in ("Write", "Edit", "MultiEdit")]
        assert writers == [FINDINGS_GRANT], (
            f"{path.name}: write-capable grants must be exactly [{FINDINGS_GRANT!r}], got {writers}"
        )


# #2179: where an `Edit(path)` rule points, transcribed from the "Read and Edit
# rules" table of code.claude.com/docs/en/permissions.md. A `--allowed-tools` rule
# is a CLI-flag rule, so `/path` anchors at the primary working directory; `./path`
# and a bare `path` anchor at the shell's CURRENT directory, which moves with `cd`.
# `cd` is in Claude Code's built-in read-only set, so the allowlist cannot stop the
# reviewer from moving: the grant has to name the file wherever the shell is.
RUNNER_WORKSPACE = "/home/runner/work/jarvis/jarvis"
# The directories reviewers had `cd`'d into when their findings Edit was denied
# (like-current-song runs 40812042388, 40811579521, 40817051631), plus the root.
REVIEWER_CWDS = (
    RUNNER_WORKSPACE,
    f"{RUNNER_WORKSPACE}/.pr-head",
    f"{RUNNER_WORKSPACE}/android/app/src/main/kotlin",
)


def _edit_rule_target(rule: str, *, primary_wd: str, cwd: str) -> str:
    """The absolute path an `Edit(<pattern>)` CLI-flag rule names (permissions.md)."""
    m = re.fullmatch(r"Edit\((.+)\)", rule)
    assert m, f"not an Edit(path) rule: {rule!r}"
    pattern = m.group(1)
    if pattern.startswith("//"):
        return pattern[1:]
    if pattern.startswith("~/"):
        raise AssertionError(f"{rule!r} is home-relative; the runner's home is not the workspace")
    if pattern.startswith("/"):
        return primary_wd + pattern
    return f"{cwd}/{pattern.removeprefix('./')}"


def _rendered_findings_grant() -> str:
    """The workflow's findings grant as the runner sees it, with `github.workspace`
    substituted (the step's `with:` inputs are expanded before the action runs)."""
    grants = {
        e
        for block in _allowed_tools_blocks(LIVE_WORKFLOW)
        for e in block.split(",")
        if e.startswith("Edit(")
    }
    assert len(grants) == 1, f"expected one findings grant across the review steps, got {grants}"
    return grants.pop().replace("${{ github.workspace }}", RUNNER_WORKSPACE)


@pytest.mark.parametrize("cwd", REVIEWER_CWDS, ids=["root", "pr-head", "subdir"])
def test_findings_grant_still_names_the_seeded_file_after_a_cd(cwd: str) -> None:
    """The job seeds $FINDINGS relative to the workspace; the reviewer's grant must
    point at that file whichever directory its shell has moved to (#2179). A
    cwd-relative `./` grant pointed at `<cwd>/.review/findings.json` after a `cd`,
    the Edit was denied, and verify-verdict went red on the placeholder."""
    # The action launches Claude Code in the workspace; pass a different primary
    # directory so a grant that leans on it, not on the workspace, also goes red.
    target = _edit_rule_target(_rendered_findings_grant(), primary_wd="/elsewhere", cwd=cwd)
    assert target == f"{RUNNER_WORKSPACE}/{FINDINGS_PATH}"


def test_findings_path_in_job_env_matches_the_edit_grant() -> None:
    """The job seeds, validates and uploads $FINDINGS; the reviewer may edit only
    the granted path. Two artifacts that must agree (#1964)."""
    spec = yaml.safe_load(LIVE_WORKFLOW.read_text(encoding="utf-8"))
    assert spec["jobs"]["review"]["env"]["FINDINGS"] == FINDINGS_PATH
