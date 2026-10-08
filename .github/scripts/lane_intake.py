"""Intake gate for the AFK lane: decide, before the worker starts, whether to dispatch.

Runs from the `intake` job of `.github/workflows/agent-dispatch.yml` on an
`agent:dispatch` label event (decisions D6, D8, D9 in docs/decisions/2026-Q4.md).
The label is a human's go signal, but the issue body is attacker-reachable text
the worker will follow, so the gate binds the signal to the exact body the human
saw and refuses anything already claimed, finished or blocked.

On a refusal it leaves exactly one issue comment naming the rule and the worker
does not start. On a pass it removes `agent:dispatch` and sets
`status:in-progress`. Either way it writes `pass=true|false` to `GITHUB_OUTPUT`.
The lane never applies a class label itself: `afk:1-auto` / `afk:2-plan` come
from a human or an interactive skill.

An `afk:2-plan` issue is dispatched only when its `## Plan` section verifies
(`agents.plan_lock.verify_lock`, D5) and only in a host that sets
`LANE_CLASS2_AFK=true` — class 2 runs AFK in the lane's home repo until the
N-run gate passes (D17), so every other host is refused before the plan is read.

A label applied by the bot itself (`osasuwu-bot` or any `*[bot]` login, or a sender the event
did not name) is refused first (AP6): the lane never dispatches its own output.

Rules run in a fixed order and the first failure is the only one reported.

Stdlib plus `agents/plan_lock.py`, itself stdlib-only: the job needs no
dependency install, only a sparse checkout of `.github/scripts` and `agents`.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.plan_lock import MalformedPlanError, verify_lock  # noqa: E402

DISPATCH = "agent:dispatch"
IN_PROGRESS = "status:in-progress"
CLASS_LABELS = ("afk:1-auto", "afk:2-plan")
PLAN_CLASS = "afk:2-plan"
HUMAN_ONLY = "afk:3-human"
NEEDS_HUMAN = "needs-human"
IN_FLIGHT = (IN_PROGRESS, "status:review", "status:rework-in-progress")
# The machine user the lane's own writes come from (D1); any edit of the body by it
# after a human wrote it means the lane rewrote its own input.
DEFAULT_BOT_LOGIN = "osasuwu-bot"

FACTS_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      userContentEdits(first: 100) { nodes { editor { login } } }
      closedByPullRequestsReferences(first: 5, includeClosedPrs: false) { nodes { number } }
    }
  }
}
"""


def _bot_labelled(facts, payload_body, bot, class2_host):
    # The label is a human's go signal (D1, AP6): an issue the bot creates or edits enters
    # the lane only after a human labels it. A missing sender is unknown, not human.
    sender = facts.get("label_sender") or ""
    if not sender:
        return (
            "labeller-unknown",
            f"the `{DISPATCH}` labeller is unknown; a human re-applies `{DISPATCH}`",
        )
    if sender.casefold() == bot.casefold() or sender.endswith("[bot]"):
        return (
            "bot-labelled",
            f"`{DISPATCH}` was applied by `{sender}`, not a human; a human removes and"
            " re-applies it",
        )


def _body_changed(facts, payload_body, bot, class2_host):
    if (facts["body"] or "") != (payload_body or ""):
        return (
            "body-changed",
            "issue body changed after `agent:dispatch` was applied; re-apply the label to"
            " dispatch the current body",
        )


def _bot_edited(facts, payload_body, bot, class2_host):
    if bot in facts["editors"]:
        return "bot-edited", f"issue body carries an edit by `{bot}`"


def _unclassified(facts, payload_body, bot, class2_host):
    labels = facts["labels"]
    if any(name in labels for name in CLASS_LABELS):
        return None
    if HUMAN_ONLY in labels:
        return (
            "unclassified",
            f"labelled `{HUMAN_ONLY}`, which is never dispatched; it needs `afk:1-auto` or"
            " `afk:2-plan`",
        )
    return "unclassified", "no `afk:1-auto` or `afk:2-plan` label; classify the issue first"


def _class2_host(facts, payload_body, bot, class2_host):
    if PLAN_CLASS in facts["labels"] and not class2_host:
        return (
            "class2-host",
            f"`{PLAN_CLASS}` runs AFK only in the lane's home repo until the N-run gate passes;"
            " this host does not set `LANE_CLASS2_AFK`",
        )


def _plan_lock(facts, payload_body, bot, class2_host):
    if PLAN_CLASS not in facts["labels"]:
        return None
    try:
        intact = verify_lock(facts["body"] or "")
    except MalformedPlanError as exc:
        if exc.reason == "missing_heading":
            return (
                "plan-missing",
                "no `## Plan` section; publish one with `python -m agents.plan_lock publish`",
            )
        return (
            "plan-malformed",
            f"the `## Plan` section is malformed ({exc.reason}); publish it with"
            " `python -m agents.plan_lock publish`",
        )
    if not intact:
        return (
            "plan-edited",
            "the `## Plan` lock does not match its steps: the plan was edited after the critic"
            " panel; re-run the panel and republish",
        )


def _closed(facts, payload_body, bot, class2_host):
    if facts["state"] != "open":
        return "closed", "issue is closed"


def _claimed_by_pr(facts, payload_body, bot, class2_host):
    if facts["closing_prs"]:
        return "claimed-by-pr", f"open PR #{facts['closing_prs'][0]} already closes this issue"


def _needs_human(facts, payload_body, bot, class2_host):
    # Set by the escalation job (lane_escalation.py) when a run ends without a PR; the human
    # clears it, then re-applies `agent:dispatch`.
    if NEEDS_HUMAN in facts["labels"]:
        return (
            NEEDS_HUMAN,
            f"a human decides first: remove `{NEEDS_HUMAN}`, then re-apply `agent:dispatch`",
        )


def _in_flight(facts, payload_body, bot, class2_host):
    for name in IN_FLIGHT:
        if name in facts["labels"]:
            return "in-flight-status", f"issue carries `{name}`"


def _blocked(facts, payload_body, bot, class2_host):
    # A missing summary is unknown, not zero: fail closed.
    if facts.get("blocked_by", 1) != 0:
        return "blocked", "issue has an open blocker"


RULES = (
    _bot_labelled,
    _body_changed,
    _bot_edited,
    _unclassified,
    _class2_host,
    _plan_lock,
    _closed,
    _claimed_by_pr,
    _needs_human,
    _in_flight,
    _blocked,
)


def check(facts, payload_body, bot=DEFAULT_BOT_LOGIN, class2_host=False):
    """Return None to dispatch, else `(rule_name, message)` for the first rule that fails."""
    for rule in RULES:
        refusal = rule(facts, payload_body, bot, class2_host)
        if refusal:
            return refusal
    return None


def _request(method, path, body=None):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def fetch_facts(repo, number):
    """Read the issue as it is now, not as the `labeled` event described it."""
    issue = _request("GET", f"repos/{repo}/issues/{number}")
    owner, name = repo.split("/", 1)
    data = _request(
        "POST",
        "graphql",
        {"query": FACTS_QUERY, "variables": {"owner": owner, "name": name, "number": int(number)}},
    )
    if data.get("errors"):
        raise RuntimeError(f"GraphQL lookup failed: {data['errors']}")
    node = data["data"]["repository"]["issue"]
    summary = issue.get("issue_dependencies_summary") or {}
    facts = {
        "body": issue.get("body"),
        "state": issue["state"],
        "labels": [label["name"] for label in issue.get("labels", [])],
        "editors": [
            (edit.get("editor") or {}).get("login") for edit in node["userContentEdits"]["nodes"]
        ],
        "closing_prs": [pr["number"] for pr in node["closedByPullRequestsReferences"]["nodes"]],
    }
    if "blocked_by" in summary:
        facts["blocked_by"] = summary["blocked_by"]
    return facts


def _remove_label(repo, number, name):
    try:
        _request("DELETE", f"repos/{repo}/issues/{number}/labels/{urllib.parse.quote(name)}")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    number = os.environ["ISSUE_NUMBER"]
    bot = os.environ.get("LANE_BOT_LOGIN") or DEFAULT_BOT_LOGIN
    class2_host = os.environ.get("LANE_CLASS2_AFK") == "true"
    facts = fetch_facts(repo, number)
    # Who applied the label comes from the event, not from the issue's current state.
    facts["label_sender"] = os.environ.get("LABEL_SENDER", "")
    refusal = check(facts, os.environ.get("PAYLOAD_BODY"), bot, class2_host=class2_host)
    if refusal:
        rule, message = refusal
        _request(
            "POST",
            f"repos/{repo}/issues/{number}/comments",
            {"body": f"Lane intake refused dispatch: `{rule}`. {message}."},
        )
    else:
        _request("POST", f"repos/{repo}/issues/{number}/labels", {"labels": [IN_PROGRESS]})
        _remove_label(repo, number, DISPATCH)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write(f"pass={'false' if refusal else 'true'}\n")
    print(f"#{number}: {'refused ' + refusal[0] if refusal else 'dispatched'}")


if __name__ == "__main__":
    main()
