"""Read the orchestrator dispatch ledger and report the 2026-11-18 revisit count (#2115).

The ledger is a GitHub issue (Osasuwu/jarvis#2115) on which the orchestrator session adds
one comment row per dispatch. Its fourth acceptance criterion asks, on or after
2026-11-18, how many of the user's issues the orchestrator brought to merge
(`merged-unedited` + `edited`), and for the revisit outcome: retire the AFK lane at 10 or
more, otherwise reopen the freeze decision (`docs/decisions/2026-Q4.md`, "2026-10-17 —
AFK lane frozen; orchestrator session dispatches", D4 and its predicts).

The rows were written by hand over many runs, so their shape varies: five-column tables,
run tables with a session column, prose lines with several dispatches, the PR before the
issue, PRs as URLs. Most rows say `merged` without saying whether the user edited the PR.
So the rows supply only the set of issues and PRs they name; GitHub supplies the rest:

- every reference in the rows is read — `owner/repo#N`, a github.com issue or pull URL,
  `repo#N` or `repo #N` for a repo the ledger names in full somewhere, and a bare `#N`,
  which means the repo of the last reference before it on the line (else the ledger's);
- GitHub says which of them are pull requests. A PR is attributed to an issue the rows
  name when its title or body links that issue after a keyword (`Closes`, `Fixes`,
  `Resolves`, `Refs`, `Part of`), as every orchestrator PR does — not by where the two sit
  in a row, which the free-form rows do not keep consistent;
- a merged PR is `edited` when any non-merge commit on it was made by a person: its
  message carries no agent `Co-Authored-By:` trailer (Claude or Jarvis) and its author is
  not a `*[bot]` login. Agent and user share one login here, so the login cannot tell them
  apart; the trailer can. A commit list that cannot be read is `edited` (fail-closed).

"The user's issues" are the issues the given login authored (D3: authorship filters out
collaborators' and external issues).

Usage (needs `gh` signed in):

    python scripts/dispatch_ledger.py report --ledger Osasuwu/jarvis#2115 --user <login>

It prints a Markdown report for the AC4 comment: counts, the verdict, one line per issue
with a PR, and the merged PRs it could not attribute. It writes nothing to GitHub.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

# Fixed by the 2026-10-17 freeze decision (predicts: ">=10 of the user's issues to merge").
RETIRE_AT = 10
VERDICT_RETIRE = "retire the lane"
VERDICT_REOPEN = "reopen the freeze decision"

MERGED_UNEDITED, EDITED, CLOSED, OPEN = "merged-unedited", "edited", "closed", "open"
OUTCOMES = (MERGED_UNEDITED, EDITED, CLOSED, OPEN)
MERGED = (MERGED_UNEDITED, EDITED)

# One reference: a github.com issue/pull URL, or `owner/repo#N`, `repo#N`, `repo #N`, `#N`.
_TOKEN = re.compile(
    r"github\.com/(?P<uo>[A-Za-z0-9-]+)/(?P<ur>[A-Za-z0-9_.-]+)/(?:issues|pull)/(?P<un>\d+)"
    r"|(?<![\w/#])(?:(?P<o>[A-Za-z0-9-]+)/)?(?P<r>[A-Za-z0-9_.-]+)?(?P<sp>[ \t]+)?#(?P<n>\d+)\b"
)
_LINK = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?|part of)\b:?[ \t]+", re.I)
_AGENT_TRAILER = re.compile(r"^co-authored-by:.*\b(claude|jarvis)\b", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True, order=True)
class Ref:
    repo: str  # owner/repo
    number: int

    def __str__(self):
        return f"{self.repo}#{self.number}"


def known_repos(texts):
    """Short repo name → `owner/repo`, from every full reference or URL in `texts`."""
    owners = {}
    for text in texts:
        for m in _TOKEN.finditer(text or ""):
            owner, name = (m["uo"], m["ur"]) if m["un"] else (m["o"], m["r"])
            if owner and name:
                owners.setdefault(name.casefold(), f"{owner}/{name}")
    return owners


def _ref(m, context_repo, owners):
    """The `Ref` one token match names, or None when its repo cannot be told."""
    if m["un"]:
        return Ref(f"{m['uo']}/{m['ur']}", int(m["un"]))
    number = int(m["n"])
    if m["o"] and m["r"]:
        return Ref(f"{m['o']}/{m['r']}", number)
    if m["r"]:
        full = owners.get(m["r"].casefold())
        if full:
            return Ref(full, number)
        if not m["sp"]:
            return None  # `word#N` for a repo the ledger never names in full
        # `PR #3270`, `Closes #12`: the word is prose, the ref is bare
    return Ref(context_repo, number)


def line_refs(line, default_repo, owners):
    """Every reference on one line, in order. A bare `#N` takes the repo of the last
    reference before it on the line (`like-current-song #281+#289`), else `default_repo`."""
    refs, context = [], default_repo
    for m in _TOKEN.finditer(line):
        ref = _ref(m, context, owners)
        if ref:
            refs.append(ref)
            context = ref.repo
    return refs


def ledger_refs(bodies, ledger_repo):
    """Every distinct reference in the ledger's comment bodies, in first-seen order."""
    owners = known_repos(bodies)
    seen = {}
    for body in bodies:
        for line in (body or "").splitlines():
            for ref in line_refs(line, ledger_repo, owners):
                seen.setdefault(ref, None)
    return list(seen)


def linked_refs(text, pr_repo, owners):
    """The references a PR's title/body links after a keyword (`Closes #12`,
    `Refs Osasuwu/jarvis#5`). A bare `#N` is the PR's own repo; a ref merely mentioned
    (`follow-up #9`) is not a link."""
    found = set()
    for m in _LINK.finditer(text or ""):
        token = _TOKEN.match(text, m.end())
        ref = _ref(token, pr_repo, owners) if token else None
        if ref:
            found.add(ref)
    return found


def human_commits(commits):
    """One line per commit a person made on a PR; empty means the PR is unedited.

    `commits` is the REST list of the PR's commits. Merge commits (an "Update branch"
    merge of the base) are not edits. A commit counts as the agent's when its message
    carries a `Co-Authored-By:` trailer naming Claude or Jarvis, or its author is a
    `*[bot]` login. An empty list is an edit too: a PR with no readable commits cannot be
    shown unedited.
    """
    if not commits:
        return ["no commits readable; cannot show the PR is unedited"]
    found = []
    for commit in commits:
        if len(commit.get("parents") or []) > 1:
            continue
        login = (commit.get("author") or {}).get("login") or ""
        message = (commit.get("commit") or {}).get("message") or ""
        if login.endswith("[bot]") or _AGENT_TRAILER.search(message):
            continue
        headline = message.splitlines()[0] if message else ""
        found.append(f"{(commit.get('sha') or '')[:7]} by {login or 'unlinked'}: {headline}")
    return found


def issue_outcome(prs):
    """An issue's outcome from its attributed PRs: [(state, merged, human_commit_lines)]."""
    merged = [touches for _, was_merged, touches in prs if was_merged]
    if merged:
        return EDITED if any(merged) else MERGED_UNEDITED
    return OPEN if any(state == "open" for state, _, _ in prs) else CLOSED


def verdict(count):
    return VERDICT_RETIRE if count >= RETIRE_AT else VERDICT_REOPEN


def _gh_json(args):
    out = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        stdin=subprocess.DEVNULL,
    ).stdout
    return json.loads(out)


def gh_api(path):
    """GET `path`; a list endpoint is read in full (`--paginate --slurp`, pages flattened)."""
    if path.endswith(("/comments", "/commits")):
        pages = _gh_json(["api", f"{path}?per_page=100", "--paginate", "--slurp"])
        return [item for page in pages for item in page]
    return _gh_json(["api", path])


def _fetch_all(api, paths, workers):
    """{path: answer} for each path; one that cannot be read (a bare `#N` the rows meant
    for another repo, a 404) is None."""

    def one(path):
        try:
            return api(path)
        except (subprocess.CalledProcessError, ValueError):
            return None

    paths = list(dict.fromkeys(paths))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(paths, pool.map(one, paths), strict=True))


@dataclass
class IssueRow:
    issue: Ref
    author: str
    outcome: str
    prs: list[str]
    touches: list[str]


@dataclass
class Report:
    rows: list[IssueRow]  # issues the rows name that have at least one attributed PR
    unattributed: list[Ref]  # merged PRs the rows name that link none of those issues
    unreadable: int  # references GitHub did not answer for


def build_report(ledger, api=gh_api, workers=8):
    comments = api(f"repos/{ledger.repo}/issues/{ledger.number}/comments")
    bodies = [c.get("body") or "" for c in comments]
    refs = [r for r in ledger_refs(bodies, ledger.repo) if r != ledger]
    items = _fetch_all(api, [f"repos/{r.repo}/issues/{r.number}" for r in refs], workers)
    item = {r: items[f"repos/{r.repo}/issues/{r.number}"] for r in refs}
    issues = [r for r in refs if item[r] is not None and "pull_request" not in item[r]]
    pr_refs = [r for r in refs if item[r] is not None and "pull_request" in item[r]]
    pulls = _fetch_all(api, [f"repos/{r.repo}/pulls/{r.number}" for r in pr_refs], workers)
    pr = {r: pulls[f"repos/{r.repo}/pulls/{r.number}"] or {} for r in pr_refs}
    merged = [r for r in pr_refs if pr[r].get("merged_at")]
    commits = _fetch_all(api, [f"repos/{r.repo}/pulls/{r.number}/commits" for r in merged], workers)

    owners = known_repos(bodies)
    issue_set = set(issues)
    prs_of = {r: [] for r in issues}
    unattributed = []
    for r in pr_refs:
        text = f"{pr[r].get('title') or ''}\n{pr[r].get('body') or ''}"
        targets = linked_refs(text, r.repo, owners) & issue_set
        for issue in sorted(targets):
            prs_of[issue].append(r)
        if not targets and r in merged:
            unattributed.append(r)

    rows = []
    for issue in issues:
        if not prs_of[issue]:
            continue
        states, touches = [], []
        for r in prs_of[issue]:
            was_merged = r in merged
            path = f"repos/{r.repo}/pulls/{r.number}/commits"
            lines = human_commits(commits[path] or []) if was_merged else []
            states.append((pr[r].get("state"), was_merged, lines))
            touches.extend(f"{r}: {line}" for line in lines)
        author = (item[issue].get("user") or {}).get("login") or ""
        prs = [str(r) for r in prs_of[issue]]
        rows.append(IssueRow(issue, author, issue_outcome(states), prs, touches))
    unreadable = sum(item[r] is None for r in refs)
    return Report(rows, unattributed, unreadable)


def render(report, user):
    mine = [r for r in report.rows if r.author.casefold() == user.casefold()]
    count = sum(r.outcome in MERGED for r in mine)
    out = [
        f"**Issues authored by {user} with an orchestrator PR: {len(mine)}** "
        f"(all authors: {len(report.rows)})",
        "",
        "| outcome | issues |",
        "|---|---|",
        *(f"| {o} | {sum(r.outcome == o for r in mine)} |" for o in OUTCOMES),
        "",
        f"Brought to merge (`merged-unedited` + `edited`): **{count}** "
        f"(threshold {RETIRE_AT}) → **{verdict(count)}**",
        "",
        "| issue | author | PR | outcome | human commits |",
        "|---|---|---|---|---|",
    ]
    for r in report.rows:
        touches = "<br>".join(t.replace("|", "\\|") for t in r.touches) or "—"
        out.append(f"| {r.issue} | {r.author} | {', '.join(r.prs)} | {r.outcome} | {touches} |")
    if report.unattributed:
        out += [
            "",
            "Merged PRs the rows name that link none of the rows' issues:",
            *(f"- {ref}" for ref in report.unattributed),
        ]
    out += ["", f"References GitHub did not answer for: {report.unreadable}"]
    return "\n".join(out)


def parse_ref(text):
    match = re.fullmatch(r"([\w.-]+/[\w.-]+)#(\d+)", (text or "").strip())
    if not match:
        raise argparse.ArgumentTypeError(f"expected owner/repo#N, got {text!r}")
    return Ref(match.group(1), int(match.group(2)))


def main(argv=None, api=gh_api):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="print the AC4 revisit report")
    report.add_argument("--ledger", type=parse_ref, required=True, help="owner/repo#N")
    report.add_argument("--user", required=True, help="login whose issues count")
    args = parser.parse_args(argv)
    print(render(build_report(args.ledger, api), args.user))
    return 0


if __name__ == "__main__":
    sys.exit(main())
