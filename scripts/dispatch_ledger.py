"""Read the orchestrator dispatch ledger and report the 2026-11-18 revisit count (#2115).

The ledger is a GitHub issue (Osasuwu/jarvis#2115) on which the orchestrator session adds
one comment row per dispatch. Its fourth acceptance criterion asks, on or after
2026-11-18, how many of the user's issues the orchestrator brought to merge
(`merged-unedited` + `edited`), and for the revisit outcome: retire the AFK lane at 10 or
more, otherwise reopen the freeze decision (`docs/decisions/2026-Q4.md`, "2026-10-17 —
AFK lane frozen; orchestrator session dispatches", D4 and its predicts).

The rows were written by hand over many runs, so their shape varies: five-column tables,
run tables with a session column, prose lines like `owner/repo#N → owner/repo#M merged`.
Most rows say `merged` without saying whether the user edited the PR. So the rows only
supply the issue → PR pairs; GitHub supplies the rest:

- per line, the first issue reference is the dispatched issue (in a table row, the refs of
  the first cell), and the later references are candidate PRs;
- a candidate counts as the issue's PR only when GitHub says it is a pull request and its
  title or body names the issue — a later reference to some other issue or PR in the
  outcome text is dropped and listed;
- a merged PR is `edited` when any non-merge commit on it was made by a person: its
  message carries no agent `Co-Authored-By:` trailer (Claude or Jarvis) and its author is
  not a `*[bot]` login. Agent and user share one login here, so the login cannot tell them
  apart; the trailer can. A commit list that cannot be read is `edited` (fail-closed).

"The user's issues" are the issues the given login authored (D3: authorship filters out
collaborators' and external issues).

Usage (needs `gh` signed in):

    python scripts/dispatch_ledger.py report --ledger Osasuwu/jarvis#2115 --user <login>

It prints a Markdown report for the AC4 comment: counts, the verdict, one line per
dispatched issue, and the references it could not attribute. It writes nothing to GitHub.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field

# Fixed by the 2026-10-17 freeze decision (predicts: ">=10 of the user's issues to merge").
RETIRE_AT = 10
VERDICT_RETIRE = "retire the lane"
VERDICT_REOPEN = "reopen the freeze decision"

MERGED_UNEDITED, EDITED, CLOSED, OPEN, NO_PR = (
    "merged-unedited",
    "edited",
    "closed",
    "open",
    "no-pr",
)
MERGED = (MERGED_UNEDITED, EDITED)

# `owner/repo#N`, `repo#N` or `#N`, not inside a word or a path.
_REF = re.compile(r"(?<![\w/#])(?:([A-Za-z0-9-]+)/)?([A-Za-z0-9_.-]+)?#(\d+)\b")
_AGENT_TRAILER = re.compile(r"^co-authored-by:.*\b(claude|jarvis)\b", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True, order=True)
class Ref:
    repo: str  # owner/repo
    number: int

    def __str__(self):
        return f"{self.repo}#{self.number}"


@dataclass
class Dispatch:
    issue: Ref
    candidates: list[Ref] = field(default_factory=list)


def _raw_refs(text):
    return [(m.group(1), m.group(2), int(m.group(3))) for m in _REF.finditer(text)]


def known_repos(bodies):
    """Short repo name → owner, from every full `owner/repo#N` in the ledger."""
    owners = {}
    for body in bodies:
        for owner, name, _ in _raw_refs(body):
            if owner and name:
                owners.setdefault(name.casefold(), f"{owner}/{name}")
    return owners


def _resolve(raw, context_repo, owners):
    owner, name, number = raw
    if owner and name:
        return Ref(f"{owner}/{name}", number)
    if name:
        full = owners.get(name.casefold())
        return Ref(full, number) if full else None
    return Ref(context_repo, number) if context_repo else None


def parse_line(line, ledger_repo, owners):
    """The dispatch one ledger line records, or None when it names no issue.

    Table row or prose, the first reference is the issue (every row shape in the ledger
    puts it first). A bare `#N` there means the ledger's own repo; a later bare ref means
    the issue's repo, as the rows write PRs (`PR #3270` beside
    `SergazyNarynov/redrobot#3154`).
    """
    raw = _raw_refs(line)
    resolved = [_resolve(x, ledger_repo, owners) for x in raw]
    start = next((i for i, ref in enumerate(resolved) if ref), None)
    if start is None:
        return None
    issue = resolved[start]
    tail = [_resolve(x, issue.repo, owners) for x in raw[start + 1 :]]
    return Dispatch(issue, [r for r in tail if r and r != issue])


def parse_ledger(bodies, ledger_repo):
    """Every dispatch in the ledger's comment bodies, merged per issue, in first-seen order."""
    owners = known_repos(bodies)
    merged = {}
    for body in bodies:
        for line in (body or "").splitlines():
            dispatch = parse_line(line, ledger_repo, owners)
            if dispatch is None:
                continue
            seen = merged.setdefault(dispatch.issue, Dispatch(dispatch.issue))
            for ref in dispatch.candidates:
                if ref not in seen.candidates:
                    seen.candidates.append(ref)
    return list(merged.values())


def names_issue(text, issue, pr_repo):
    """True when a PR's title or body names `issue`: `owner/repo#N`, its URL, or `#N` in-repo."""
    text = text or ""
    owner, name = issue.repo.split("/", 1)
    full = rf"(?<![\w/]){re.escape(owner)}/{re.escape(name)}#{issue.number}\b"
    url = rf"github\.com/{re.escape(owner)}/{re.escape(name)}/issues/{issue.number}\b"
    if re.search(full, text, re.IGNORECASE) or re.search(url, text, re.IGNORECASE):
        return True
    same_repo = pr_repo.casefold() == issue.repo.casefold()
    return same_repo and re.search(rf"(?<![\w/#])#{issue.number}\b", text) is not None


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
    merged = [touches for state, was_merged, touches in prs if was_merged]
    if merged:
        return EDITED if any(merged) else MERGED_UNEDITED
    if any(state == "open" for state, _, _ in prs):
        return OPEN
    return CLOSED if prs else NO_PR


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


@dataclass
class IssueRow:
    issue: Ref
    author: str
    outcome: str
    prs: list[str]
    touches: list[str]


def build_report(ledger, api=gh_api):
    """(rows, dropped) for the ledger `Ref`: one row per dispatched issue, and the
    candidate references that were not attributed, each with the reason."""
    comments = api(f"repos/{ledger.repo}/issues/{ledger.number}/comments")
    bodies = [c.get("body") or "" for c in comments]
    cache = {}

    def get(path):
        # A ref the rows got wrong (a bare `#N` meant for another repo) reads as None.
        if path not in cache:
            try:
                cache[path] = api(path)
            except (subprocess.CalledProcessError, ValueError):
                cache[path] = None
        return cache[path]

    rows, dropped = [], []
    for dispatch in parse_ledger(bodies, ledger.repo):
        if dispatch.issue == ledger:
            continue
        issue = get(f"repos/{dispatch.issue.repo}/issues/{dispatch.issue.number}")
        if issue is None:
            dropped.append((dispatch.issue, "named as the issue, but not readable on GitHub"))
            continue
        if "pull_request" in issue:
            dropped.append((dispatch.issue, "named as the issue, but it is a pull request"))
            continue
        prs, pr_names, touches = [], [], []
        for ref in dispatch.candidates:
            item = get(f"repos/{ref.repo}/issues/{ref.number}")
            if item is None:
                dropped.append((ref, f"in the row of {dispatch.issue}, not readable on GitHub"))
                continue
            if "pull_request" not in item:
                continue  # another issue named in the outcome text
            pr = get(f"repos/{ref.repo}/pulls/{ref.number}") or {}
            text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
            if not names_issue(text, dispatch.issue, ref.repo):
                dropped.append((ref, f"in the row of {dispatch.issue}, but does not name it"))
                continue
            merged = bool(pr.get("merged_at"))
            commits = get(f"repos/{ref.repo}/pulls/{ref.number}/commits") if merged else None
            lines = human_commits(commits or []) if merged else []
            prs.append((pr.get("state"), merged, lines))
            pr_names.append(str(ref))
            touches.extend(f"{ref}: {line}" for line in lines)
        author = (issue.get("user") or {}).get("login") or ""
        rows.append(IssueRow(dispatch.issue, author, issue_outcome(prs), pr_names, touches))
    return rows, dropped


def render(rows, dropped, user):
    mine = [r for r in rows if r.author.casefold() == user.casefold()]
    count = sum(r.outcome in MERGED for r in mine)
    by = {
        o: sum(r.outcome == o for r in mine) for o in (MERGED_UNEDITED, EDITED, CLOSED, OPEN, NO_PR)
    }
    out = [
        f"**Dispatched issues authored by {user}: {len(mine)}** (all dispatched: {len(rows)})",
        "",
        "| outcome | issues |",
        "|---|---|",
        *(f"| {o} | {n} |" for o, n in by.items()),
        "",
        f"Brought to merge (`merged-unedited` + `edited`): **{count}** "
        f"(threshold {RETIRE_AT}) → **{verdict(count)}**",
        "",
        "| issue | author | PR | outcome | human commits |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        prs = ", ".join(r.prs) or "—"
        touches = "<br>".join(t.replace("|", "\\|") for t in r.touches) or "—"
        out.append(f"| {r.issue} | {r.author} | {prs} | {r.outcome} | {touches} |")
    if dropped:
        out += ["", "Not attributed:", *(f"- {ref} — {why}" for ref, why in dropped)]
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
    rows, dropped = build_report(args.ledger, api)
    print(render(rows, dropped, args.user))
    return 0


if __name__ == "__main__":
    sys.exit(main())
