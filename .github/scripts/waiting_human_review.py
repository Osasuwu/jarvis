"""The `waiting-human-review` check: red while a human look is owed, and the bot cannot lift it.

Runs from `.github/workflows/waiting-human-review.yml` on every PR event that can change the
hold (#1892, #1999 AP5). A hold is a pending review request, or, for the solo developer who
cannot request a review from themselves, the `waiting-human-review` label.

Since the AFK worker writes as machine user `osasuwu-bot` (D1) with `write` access, it can
remove the label or a review request. A hold the bot released is therefore not a release:
the script puts the label back and stays red. Only a later release by a human clears it.
"Not a human" is the bot login, any `*[bot]` login, and a login the event did not name.

Stdlib only; the workflow runs this file from the base ref so a PR cannot rewrite its own gate.
API calls go through the shared client `github_client.py` beside this script (#2068), loaded
by file path at import from the same base-ref checkout.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path


def _load_client():
    """`github_client.py` beside this script, shared through `sys.modules` so that
    `ListingTruncated` is one class within the process."""
    name = "_jarvis_github_client"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().with_name("github_client.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)  # a half-built module must not be handed out next time
        raise
    return module


github_client = _load_client()

LABEL = "waiting-human-review"
DEFAULT_BOT_LOGIN = "osasuwu-bot"
EVENT_PAGES = 10


def is_non_human(login, bot):
    """The bot, any `*[bot]` login, or a missing one: an actor that cannot release a hold."""
    login = (login or "").casefold()
    return not login or login == bot.casefold() or login.endswith("[bot]")


def _is_release(action, label_name):
    return action == "review_request_removed" or (action == "unlabeled" and label_name == LABEL)


def _bot_released(issue_events, event, bot):
    """Whether the hold was last released by a non-human actor."""
    if _is_release(event.get("action"), (event.get("label") or {}).get("name")):
        return is_non_human((event.get("sender") or {}).get("login"), bot)
    for item in reversed(issue_events):
        if _is_release(item.get("event"), (item.get("label") or {}).get("name")):
            return is_non_human((item.get("actor") or {}).get("login"), bot)
    return False


def decide(pr, issue_events, event, bot=DEFAULT_BOT_LOGIN):
    """Return `(red, reason, reapply)` for a PR, its issue events (oldest first) and the event."""
    if pr.get("requested_reviewers") or pr.get("requested_teams"):
        return True, "review-requested", False
    if any(label["name"] == LABEL for label in pr.get("labels") or []):
        return True, "label", False
    if _bot_released(issue_events, event, bot):
        return True, "bot-released", True
    return False, "clear", False


def _issue_events(api, repo, number):
    """Every issue event of the PR, oldest first. A history past the page cap is
    unreadable: `ListingTruncated`, a RuntimeError."""
    return github_client.paged(api, f"repos/{repo}/issues/{number}/events", max_pages=EVENT_PAGES)


def _make_client(token):
    return github_client.Client(token, user_agent="waiting-human-review")


def main(make_client=None):
    repo = os.environ["GITHUB_REPOSITORY"]
    number = os.environ["PR_NUMBER"]
    bot = os.environ.get("LANE_BOT_LOGIN") or DEFAULT_BOT_LOGIN
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as fh:
        event = json.load(fh)
    api = (make_client or _make_client)(os.environ["GITHUB_TOKEN"])
    # Re-fetch rather than trust the payload: a review_submitted payload's
    # pull_request is a snapshot that may predate GitHub clearing the reviewer.
    try:
        pr = api("GET", f"repos/{repo}/pulls/{number}")
        events = _issue_events(api, repo, number)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"::error::cannot read the hold state of #{number}: {exc}")
        return 1
    red, reason, reapply = decide(pr, events, event, bot)
    if reapply:
        try:
            api("POST", f"repos/{repo}/issues/{number}/labels", {"labels": [LABEL]})
        except (OSError, ValueError) as exc:
            print(f"::error::could not re-apply `{LABEL}` after a non-human release: {exc}")
    messages = {
        "review-requested": "A review has been requested and is still pending — a human look is"
        " owed.",
        "label": f"The `{LABEL}` label is present — a human look is owed.",
        "bot-released": f"The hold was released by a non-human actor; `{LABEL}` is back on the PR."
        " A human removes it to release the hold.",
    }
    if red:
        print(f"::error::{messages[reason]}")
        return 1
    print("No pending review request and no waiting-human-review label — check passes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
