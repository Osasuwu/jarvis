"""#2226 — the fixing step in front of the scheduled CI reader's message.

The reader no longer sends a red run straight away: it queues it, an agent
diagnoses it under the affected repo's own rules, and ``report`` sends the one
message with what the agent did. These tests cover the deterministic half: which
run is queued, the message the user reads (asserted as literals), what is
written to the state and the log, and that a no-change outcome only reads GitHub.
The agent's judgement is a prompt (``docs/reference/scheduled-ci-fixer-prompt.md``)
and is not under test here.

Every test drives the real ``main`` / ``run`` with a fake ``gh`` and a fake
Telegram ``post``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts import scheduled_ci_fixer as fixer
from tests.scheduled_ci.test_scheduled_ci_reader import (
    ENV,
    NIGHTLY,
    TUE,
    WEEKLY,
    FakeGh,
    Telegram,
    go,
    row,
    seed,
    state_of,
)

MON = date(2026, 11, 16)
NIGHTLY_KEY = "o/r nightly.yml schedule"
WEEKLY_KEY = "o/r weekly.yml schedule"
CURSORS = {
    NIGHTLY_KEY: {"cursor": {"id": 1, "attempt": 1}, "red": None},
    WEEKLY_KEY: {"cursor": {"id": 10, "attempt": 1}, "red": None},
}
NIGHTLY_ALERT = (
    "Scheduled CI red: o/r nightly.yml\n\n"
    "2026-11-14 — new red run\n"
    "Failing jobs: unit\n"
    "https://github.com/o/r/actions/runs/2\n\n"
    "2026-11-15 — new failing jobs: slow\n"
    "Failing jobs: slow, unit\n"
    "https://github.com/o/r/actions/runs/3"
)
WEEKLY_ALERT = (
    "Scheduled CI red: o/r weekly.yml\n\n"
    "2026-11-15 — new red run\n"
    "Failing jobs: audit\n"
    "https://github.com/o/r/actions/runs/11"
)
NOT_DIAGNOSED = "Outcome: not diagnosed (the fixer session ended without a report)"


def sha_row(run_id, day, conclusion):
    return {**row(run_id, day, conclusion), "head_sha": f"sha{run_id}"}


def two_red_workflows():
    runs = {
        "nightly.yml": [
            sha_row(1, "2026-11-13", "success"),
            sha_row(2, "2026-11-14", "failure"),
            sha_row(3, "2026-11-15", "failure"),
        ],
        "weekly.yml": [sha_row(10, "2026-11-08", "success"), sha_row(11, "2026-11-15", "failure")],
    }
    jobs = {
        2: [("unit", "failure")],
        3: [("unit", "failure"), ("slow", "failure")],
        11: [("audit", "failure")],
    }
    return runs, jobs


class FixGh(FakeGh):
    """``FakeGh`` plus the two reads of the "nothing written" guard."""

    def __init__(self, runs=None, jobs=None, *, pulls=(), refs=(), guard_fails=False):
        super().__init__(runs, jobs)
        self.pulls, self.refs, self.guard_fails = list(pulls), list(refs), guard_fails
        self.args: list[list[str]] = []

    def __call__(self, repo, args):
        self.args.append(list(args))
        path = args[1]
        if "/pulls?" in path or "/git/matching-refs/" in path:
            self.calls.append(path)
            if self.guard_fails:
                return {"stdout": "", "stderr": "HTTP 502", "returncode": 1}
            found = self.pulls if "/pulls?" in path else self.refs
            return {"stdout": json.dumps(found), "stderr": "", "returncode": 0}
        return super().__call__(repo, args)


def root_of(tmp_path: Path, *, routine_host=True) -> Path:
    root = tmp_path / "repo"
    if not root.exists():
        (root / "config").mkdir(parents=True)
        (root / "config" / "scheduled-ci.conf").write_text(
            "o/r nightly.yml\no/r weekly.yml\n", encoding="utf-8"
        )
        if routine_host is not None:
            (root / "config" / "device.json").write_text(
                json.dumps({"routine_host": routine_host}), encoding="utf-8"
            )
    return root


def fx(tmp_path, argv, gh, tg, *, routine_host=True, today=TUE, state_dir=True):
    extra = ["--state-dir", str(tmp_path / "st")] if state_dir else []
    return fixer.main(
        [*argv, *extra],
        root=root_of(tmp_path, routine_host=routine_host),
        run_gh=gh,
        post=tg,
        today=today,
        environ=ENV,
        env_file=None,
    )


def started(tmp_path, **gh_kwargs):
    """Two red workflows read by ``start``: two items pending, nothing sent yet."""
    seed(tmp_path / "st", workflows=CURSORS)
    runs, jobs = two_red_workflows()
    gh, tg = FixGh(runs, jobs, **gh_kwargs), Telegram()
    assert fx(tmp_path, ["start"], gh, tg) == 0
    assert tg.texts == []
    return gh, tg


def pending(tmp_path) -> list[dict]:
    path = tmp_path / "st" / "pending.json"
    return json.loads(path.read_text(encoding="utf-8"))["items"] if path.is_file() else []


def log_lines(tmp_path) -> list[dict]:
    path = tmp_path / "st" / "log.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def files(tmp_path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted((tmp_path / "st").iterdir())}


# -- the reader's deferred mode ----------------------------------------------------


def test_deferred_reader_queues_the_newest_alerting_run_and_still_sends_the_summary(tmp_path):
    seed(tmp_path / "st", last_summary="2026-11-09", workflows=CURSORS)
    runs, jobs = two_red_workflows()
    # A red run whose jobs the streak already named: no alert, so not the run to handle.
    runs["nightly.yml"].append(sha_row(4, "2026-11-16", "failure"))
    jobs[4] = [("unit", "failure")]
    gh, tg = FixGh(runs, jobs), Telegram()
    assert go(tmp_path, gh, tg, watches=(NIGHTLY,), today=MON, defer=True) == 0

    assert tg.texts == [
        "Scheduled CI weekly summary: 2026-11-09..2026-11-15\n\no/r nightly.yml: 3 runs, 2 red"
    ]
    # Not committed: the cursor moves only when the item's message is sent.
    assert state_of(tmp_path / "st")["cursor"]["id"] == 1
    [item] = pending(tmp_path)
    assert item.pop("created").startswith("20")
    subject, _, body = NIGHTLY_ALERT.partition("\n\n")
    assert item == {
        "watch_key": NIGHTLY_KEY,
        "repo": "o/r",
        "workflow": "nightly.yml",
        "run_id": 3,
        "html_url": "https://github.com/o/r/actions/runs/3",
        "head_sha": "sha3",
        "failing_jobs": ["slow", "unit"],
        "subject": subject,
        "body": body,
        "state": {
            "cursor": {"id": 4, "attempt": 1},
            "red": {"jobs": ["unit"], "since": "2026-11-14", "named": ["slow", "unit"]},
        },
    }


def test_second_deferred_read_replaces_the_item_of_the_same_workflow_in_place(tmp_path):
    seed(tmp_path / "st", workflows=CURSORS)
    runs, jobs = two_red_workflows()
    assert go(tmp_path, FixGh(runs, jobs), Telegram(), watches=(NIGHTLY, WEEKLY), defer=True) == 0
    runs["nightly.yml"].append(sha_row(5, "2026-11-17", "failure"))
    jobs[5] = [("lint", "failure")]
    assert go(tmp_path, FixGh(runs, jobs), Telegram(), watches=(NIGHTLY, WEEKLY), defer=True) == 0
    assert [(i["watch_key"], i["run_id"]) for i in pending(tmp_path)] == [
        (NIGHTLY_KEY, 5),
        (WEEKLY_KEY, 11),
    ]


# -- next / report: one item after another (AC1–AC4) -------------------------------


def test_next_prints_none_without_items_and_the_oldest_item_otherwise(tmp_path, capsys):
    gh, tg = FixGh(), Telegram()
    assert fx(tmp_path, ["next"], gh, tg) == 0
    assert capsys.readouterr().out.strip() == "none"

    started(tmp_path)
    capsys.readouterr()
    assert fx(tmp_path, ["next"], gh, tg) == 0
    assert json.loads(capsys.readouterr().out) == {
        "watch_key": NIGHTLY_KEY,
        "repo": "o/r",
        "workflow": "nightly.yml",
        "run_id": 3,
        "html_url": "https://github.com/o/r/actions/runs/3",
        "head_sha": "sha3",
        "failing_jobs": ["slow", "unit"],
        "branch": "scheduled-ci-fix/3",
    }


def test_two_red_workflows_are_handled_one_after_another_each_with_its_own_message(
    tmp_path, capsys
):
    gh, tg = started(tmp_path)

    def next_run():
        capsys.readouterr()
        assert fx(tmp_path, ["next"], gh, tg) == 0
        out = capsys.readouterr().out.strip()
        return None if out == "none" else json.loads(out)["run_id"]

    assert next_run() == 3
    pr = "https://github.com/o/r/pull/77"
    assert fx(tmp_path, ["report", "--run", "3", "--outcome", "pr", "--pr-url", pr], gh, tg) == 0
    assert next_run() == 11
    argv = ["report", "--run", "11", "--outcome", "cause-not-found", "--diagnosis", "log is empty"]
    assert fx(tmp_path, argv, gh, tg) == 0
    assert next_run() is None
    assert tg.texts == [
        f"{NIGHTLY_ALERT}\n\nOutcome: PR opened — {pr}",
        f"{WEEKLY_ALERT}\n\nOutcome: cause not found\nlog is empty",
    ]


def test_report_pr_sends_the_link_commits_the_workflow_state_and_logs_the_outcome(tmp_path):
    gh, tg = started(tmp_path)
    pr = "https://github.com/o/r/pull/77"
    argv = ["report", "--run", "3", "--outcome", "pr", "--pr-url", pr, "--diagnosis", "stale pin"]
    assert fx(tmp_path, argv, gh, tg) == 0

    assert tg.texts == [f"{NIGHTLY_ALERT}\n\nOutcome: PR opened — {pr}\nstale pin"]
    assert state_of(tmp_path / "st") == {
        "cursor": {"id": 3, "attempt": 1},
        "red": {"jobs": ["slow", "unit"], "since": "2026-11-14", "named": ["slow", "unit"]},
    }
    assert state_of(tmp_path / "st", WEEKLY) == CURSORS[WEEKLY_KEY]  # its item is still pending
    assert [i["run_id"] for i in pending(tmp_path)] == [11]
    [entry] = log_lines(tmp_path)
    assert entry.pop("ts").startswith("20")
    assert entry == {
        "kind": "alert",
        "workflow": NIGHTLY_KEY,
        "result": "ok",
        "run_id": 3,
        "outcome": "pr",
        "pr_url": pr,
    }


NEEDS_PERSON = [
    "report",
    "--run",
    "3",
    "--outcome",
    "needs-person",
    "--rule",
    "AGENTS.md § Protected files: every write needs a person",
    "--diagnosis",
    "ci.yml pins a runner image that was removed.\nThe fix edits .github/workflows/ci.yml.",
]


def test_report_needs_person_sends_rule_and_diagnosis_and_only_reads_github(tmp_path):
    # A branch of another run that shares the prefix is not this item's branch.
    gh, tg = started(tmp_path, refs=[{"ref": "refs/heads/scheduled-ci-fix/31"}])
    before = len(gh.args)
    assert fx(tmp_path, NEEDS_PERSON, gh, tg) == 0

    assert tg.texts == [
        f"{NIGHTLY_ALERT}\n\n"
        "Outcome: needs a person — rule: AGENTS.md § Protected files: every write needs a person\n"
        "ci.yml pins a runner image that was removed.\n"
        "The fix edits .github/workflows/ci.yml."
    ]
    assert gh.args[before:] == [
        ["api", "repos/o/r/pulls?head=o:scheduled-ci-fix/3&state=all&per_page=1"],
        ["api", "repos/o/r/git/matching-refs/heads/scheduled-ci-fix/3"],
    ]
    assert [e["outcome"] for e in log_lines(tmp_path)] == ["needs-person"]
    assert "pr_url" not in log_lines(tmp_path)[0]


def test_report_already_fixed_says_so_with_its_diagnosis_and_only_reads_github(tmp_path):
    gh, tg = started(tmp_path)
    before = len(gh.args)
    diagnosis = "Runner image pin was removed.\nFixed by abc1234; scheduled run 9 is green."
    argv = ["report", "--run", "3", "--outcome", "already-fixed", "--diagnosis", diagnosis]
    assert fx(tmp_path, argv, gh, tg) == 0
    assert tg.texts == [
        f"{NIGHTLY_ALERT}\n\n"
        "Outcome: already fixed on the default branch\n"
        "Runner image pin was removed.\n"
        "Fixed by abc1234; scheduled run 9 is green."
    ]
    assert gh.args[before:] == [
        ["api", "repos/o/r/pulls?head=o:scheduled-ci-fix/3&state=all&per_page=1"],
        ["api", "repos/o/r/git/matching-refs/heads/scheduled-ci-fix/3"],
    ]
    assert [(e["run_id"], e["outcome"], e["result"]) for e in log_lines(tmp_path)] == [
        (3, "already-fixed", "ok")
    ]
    assert [i["run_id"] for i in pending(tmp_path)] == [11]
    assert state_of(tmp_path / "st")["cursor"]["id"] == 3


@pytest.mark.parametrize(
    "found",
    [
        {"pulls": [{"number": 5}]},
        {"refs": [{"ref": "refs/heads/scheduled-ci-fix/3"}]},
        {"guard_fails": True},
    ],
    ids=["pr-exists", "branch-exists", "github-unreadable"],
)
@pytest.mark.parametrize("outcome", ["needs-person", "cause-not-found", "already-fixed"])
def test_no_change_outcome_is_refused_when_the_fixer_branch_or_pr_exists(
    tmp_path, capsys, found, outcome
):
    gh, tg = started(tmp_path, **found)
    argv = ["report", "--run", "3", "--outcome", outcome, "--diagnosis", "d"]
    if outcome == "needs-person":
        argv += ["--rule", "r"]
    assert fx(tmp_path, argv, gh, tg) == 1
    err = capsys.readouterr().err
    if "guard_fails" in found:
        assert "scheduled_ci_fixer: FAILED — o/r nightly.yml: HTTP 502" in err
    else:
        assert "a PR or branch exists for a no-change outcome (scheduled-ci-fix/3)" in err
    assert tg.texts == []
    assert [i["run_id"] for i in pending(tmp_path)] == [3, 11]
    assert log_lines(tmp_path) == []


# -- no red run stays silent --------------------------------------------------------


def test_finish_sends_every_item_still_pending_as_not_diagnosed(tmp_path):
    gh, tg = started(tmp_path)
    assert fx(tmp_path, ["finish"], gh, tg) == 0
    assert tg.texts == [f"{NIGHTLY_ALERT}\n\n{NOT_DIAGNOSED}", f"{WEEKLY_ALERT}\n\n{NOT_DIAGNOSED}"]
    assert pending(tmp_path) == []
    assert state_of(tmp_path / "st")["cursor"]["id"] == 3
    assert state_of(tmp_path / "st", WEEKLY)["cursor"]["id"] == 11
    assert [(e["run_id"], e["outcome"]) for e in log_lines(tmp_path)] == [
        (3, "not-diagnosed"),
        (11, "not-diagnosed"),
    ]


def test_next_start_sends_the_leftovers_of_a_session_that_never_finished(tmp_path):
    gh, tg = started(tmp_path)  # the session dies here: no report, no finish
    assert fx(tmp_path, ["start"], gh, tg) == 0
    assert tg.texts == [f"{NIGHTLY_ALERT}\n\n{NOT_DIAGNOSED}", f"{WEEKLY_ALERT}\n\n{NOT_DIAGNOSED}"]
    # Their state is committed, so the second read finds nothing new to queue.
    assert pending(tmp_path) == []


def test_failed_send_exits_1_logs_failed_and_keeps_the_item(tmp_path, capsys):
    gh, _ = started(tmp_path)
    tg = Telegram({"ok": False, "description": "chat not found"})
    argv = ["report", "--run", "11", "--outcome", "cause-not-found", "--diagnosis", "d"]
    assert fx(tmp_path, argv, gh, tg) == 1
    assert "scheduled_ci_fixer: FAILED — telegram API refused: chat not found" in (
        capsys.readouterr().err
    )
    assert [i["run_id"] for i in pending(tmp_path)] == [3, 11]
    assert state_of(tmp_path / "st", WEEKLY) == CURSORS[WEEKLY_KEY]
    assert [(e["run_id"], e["result"]) for e in log_lines(tmp_path)] == [(11, "failed")]


def test_report_whose_send_failed_goes_out_at_finish_with_its_own_outcome(tmp_path):
    gh, _ = started(tmp_path)
    pr = "https://github.com/o/r/pull/77"
    argv = ["report", "--run", "3", "--outcome", "pr", "--pr-url", pr, "--diagnosis", "pin moved"]
    assert fx(tmp_path, argv, gh, Telegram({"ok": False, "description": "down"})) == 1
    tg = Telegram()
    assert fx(tmp_path, ["finish"], gh, tg) == 0
    assert tg.texts == [
        f"{NIGHTLY_ALERT}\n\nOutcome: PR opened — {pr}\npin moved",
        f"{WEEKLY_ALERT}\n\n{NOT_DIAGNOSED}",
    ]
    assert [
        (e["run_id"], e["outcome"], e["result"], e.get("pr_url")) for e in log_lines(tmp_path)
    ] == [
        (3, "pr", "failed", pr),
        (3, "pr", "ok", pr),
        (11, "not-diagnosed", "ok", None),
    ]
    assert pending(tmp_path) == []


@pytest.mark.parametrize(
    "found",
    [{}, {"pulls": [{"number": 5}]}, {"guard_fails": True}],
    ids=["send-failed", "guard-refused", "github-unreadable"],
)
def test_next_moves_past_an_item_whose_report_did_not_go_out(tmp_path, capsys, found):
    gh, _ = started(tmp_path, **found)
    argv = ["report", "--run", "3", "--outcome", "cause-not-found", "--diagnosis", "d"]
    assert fx(tmp_path, argv, gh, Telegram({"ok": False, "description": "down"})) == 1
    capsys.readouterr()
    tg = Telegram()
    assert fx(tmp_path, ["next"], gh, tg) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == 11
    argv = ["report", "--run", "11", "--outcome", "pr", "--pr-url", "https://github.com/o/r/pull/8"]
    assert fx(tmp_path, argv, gh, tg) == 0
    assert fx(tmp_path, ["next"], gh, tg) == 0
    assert capsys.readouterr().out.strip() == "none"
    # The item whose report was not sent is still owed a message: finish sends it,
    # as reported when only the send failed, as not diagnosed when the report was refused.
    assert fx(tmp_path, ["finish"], gh, tg) == 0
    owed = "Outcome: cause not found\nd" if not found else NOT_DIAGNOSED
    assert tg.texts == [
        f"{WEEKLY_ALERT}\n\nOutcome: PR opened — https://github.com/o/r/pull/8",
        f"{NIGHTLY_ALERT}\n\n{owed}",
    ]


# -- report refuses what it cannot stand behind -------------------------------------

LONG = "x" * 601


@pytest.mark.parametrize(
    ("argv", "reason"),
    [
        (["--run", "4", "--outcome", "cause-not-found", "--diagnosis", "d"], "no pending item"),
        (["--run", "3", "--outcome", "pr"], "pr needs --pr-url https://github.com/o/r/pull/<n>"),
        (
            ["--run", "3", "--outcome", "pr", "--pr-url", "https://github.com/o/other/pull/7"],
            "pr needs --pr-url https://github.com/o/r/pull/<n>",
        ),
        (
            [
                "--run",
                "3",
                "--outcome",
                "pr",
                "--pr-url",
                "https://github.com/o/r/pull/7",
                "--rule",
                "r",
            ],
            "--rule goes with needs-person only",
        ),
        (
            ["--run", "3", "--outcome", "needs-person", "--diagnosis", "d"],
            "needs-person needs --rule",
        ),
        (
            ["--run", "3", "--outcome", "needs-person", "--rule", "r"],
            "needs-person needs --diagnosis",
        ),
        (
            [
                "--run",
                "3",
                "--outcome",
                "needs-person",
                "--rule",
                "r",
                "--diagnosis",
                "d",
                "--pr-url",
                "https://github.com/o/r/pull/7",
            ],
            "--pr-url goes with pr only",
        ),
        (
            ["--run", "3", "--outcome", "cause-not-found", "--diagnosis", "d", "--rule", "r"],
            "--rule goes with needs-person only",
        ),
        (["--run", "3", "--outcome", "cause-not-found"], "cause-not-found needs --diagnosis"),
        (["--run", "3", "--outcome", "already-fixed"], "already-fixed needs --diagnosis"),
        (
            ["--run", "3", "--outcome", "already-fixed", "--diagnosis", "d", "--rule", "r"],
            "--rule goes with needs-person only",
        ),
        (
            [
                "--run",
                "3",
                "--outcome",
                "already-fixed",
                "--diagnosis",
                "d",
                "--pr-url",
                "https://github.com/o/r/pull/7",
            ],
            "--pr-url goes with pr only",
        ),
        (
            ["--run", "3", "--outcome", "cause-not-found", "--diagnosis", " \n "],
            "cause-not-found needs --diagnosis",
        ),
        (
            ["--run", "3", "--outcome", "cause-not-found", "--diagnosis", "a\nb\nc\nd"],
            "--diagnosis is over 3 lines",
        ),
        (
            ["--run", "3", "--outcome", "cause-not-found", "--diagnosis", LONG],
            "--diagnosis is over 600 characters",
        ),
        (
            ["--run", "3", "--outcome", "needs-person", "--diagnosis", "d", "--rule", "r" * 201],
            "--rule is over 200 characters",
        ),
        (
            ["--run", "3", "--outcome", "needs-person", "--diagnosis", "d", "--rule", "a\nb"],
            "--rule is more than one line",
        ),
    ],
)
def test_report_refusal_exits_2_sends_nothing_and_keeps_the_item(tmp_path, capsys, argv, reason):
    gh, tg = started(tmp_path)
    before = len(gh.args)
    assert fx(tmp_path, ["report", *argv], gh, tg) == 2
    assert f"scheduled_ci_fixer: refused — {reason}" in capsys.readouterr().err
    assert tg.texts == []
    assert gh.args[before:] == []
    assert [i["run_id"] for i in pending(tmp_path)] == [3, 11]
    assert log_lines(tmp_path) == []


def test_outcome_message_stays_within_telegrams_limit_and_keeps_the_outcome_whole(tmp_path):
    seed(tmp_path / "st", workflows=CURSORS)
    # A catch-up of 40 red nights, each naming a new 90-character job: over one message.
    runs = [sha_row(1, "2026-10-01", "success")]
    jobs = {}
    for n in range(2, 42):
        runs.append(
            sha_row(n, f"2026-10-{n:02d}" if n < 32 else f"2026-11-{n - 31:02d}", "failure")
        )
        jobs[n] = [(f"job-{n:02d}-" + "j" * 83, "failure")]
    gh, tg = FixGh({"nightly.yml": runs}, jobs), Telegram()
    assert fx(tmp_path, ["start"], gh, tg) == 0
    rule, diagnosis = "r" * 200, "\n".join(["d" * 198] * 3)
    argv = ["report", "--run", "41", "--outcome", "needs-person", "--rule", rule]
    assert fx(tmp_path, [*argv, "--diagnosis", diagnosis], gh, tg) == 0

    [text] = tg.texts
    assert 3000 < len(text) <= 4096
    assert text.endswith(f"\n\nOutcome: needs a person — rule: {rule}\n{diagnosis}")
    assert "https://github.com/o/r/actions/runs/41\n\nOutcome:" in text


# -- dry run and the host gate -------------------------------------------------------


def test_dry_run_report_and_finish_print_the_message_and_write_nothing(tmp_path, capsys):
    gh, tg = started(tmp_path)
    before = files(tmp_path)
    assert sorted(before) == ["pending.json", "state.json"]
    capsys.readouterr()
    (tmp_path / "repo" / "config" / "device.json").unlink()  # a dry run works off the routine host
    pr = "https://github.com/o/r/pull/77"
    argv = ["report", "--run", "3", "--outcome", "pr", "--pr-url", pr, "--dry-run"]
    assert fx(tmp_path, argv, gh, tg) == 0
    assert f"{NIGHTLY_ALERT}\n\nOutcome: PR opened — {pr}\n" in capsys.readouterr().out
    assert fx(tmp_path, ["finish", "--dry-run"], gh, tg) == 0
    out = capsys.readouterr().out
    assert f"{NIGHTLY_ALERT}\n\n{NOT_DIAGNOSED}\n" in out
    assert f"{WEEKLY_ALERT}\n\n{NOT_DIAGNOSED}\n" in out
    assert tg.texts == []
    assert files(tmp_path) == before


def test_dry_run_start_stores_only_the_pending_items(tmp_path, capsys):
    runs, jobs = two_red_workflows()
    gh, tg = FixGh(runs, jobs), Telegram()
    argv = ["start", "--dry-run", "--since", "2026-11-01"]
    assert fx(tmp_path, argv, gh, tg, routine_host=None) == 0
    assert tg.texts == []
    assert sorted(files(tmp_path)) == ["pending.json"]
    assert [i["run_id"] for i in pending(tmp_path)] == [3, 11]
    assert "scheduled_ci_fixer: 2 pending" in capsys.readouterr().out


def test_dry_run_without_an_explicit_state_dir_exits_2(tmp_path, capsys):
    gh, tg = FixGh(), Telegram()
    assert fx(tmp_path, ["finish", "--dry-run"], gh, tg, state_dir=False) == 2
    assert "--dry-run needs an explicit --state-dir" in capsys.readouterr().err


def test_since_is_refused_outside_a_dry_run(tmp_path, capsys):
    gh, tg = FixGh(), Telegram()
    assert fx(tmp_path, ["start", "--since", "2026-11-01"], gh, tg) == 2
    assert "--since needs --dry-run" in capsys.readouterr().err
    assert gh.args == []


@pytest.mark.parametrize("routine_host", [None, False])
def test_live_command_is_refused_off_the_routine_host(tmp_path, capsys, routine_host):
    runs, jobs = two_red_workflows()
    gh, tg = FixGh(runs, jobs), Telegram()
    assert fx(tmp_path, ["start"], gh, tg, routine_host=routine_host) == 1
    assert "refused: routines are host-only" in capsys.readouterr().err
    assert gh.args == [] and tg.texts == []
    assert not (tmp_path / "st").exists()
