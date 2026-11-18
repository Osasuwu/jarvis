"""#2225 — the morning reader of scheduled CI runs.

Scheduled runs (a nightly, a weekly scan) sit on no PR, so a red one was read by
nobody: redrobot's nightly stayed red for 16 nights. The reader sends a red run to
Telegram once, again when a job fails that the streak has not named yet (#2229),
and a Monday summary that doubles as its own heartbeat.

Every test drives the real ``run`` / ``main`` with a fake ``gh`` and a fake
Telegram ``post``; the message texts are the contract the user reads, so they
are asserted as literals.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.scheduled_ci_reader import Watch, main, parse_watch_conf, run

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_ALLOW_USER_ID": "42"}
NIGHTLY = Watch("o/r", "nightly.yml")
WEEKLY = Watch("o/r", "weekly.yml")
TUE = date(2026, 11, 17)


def row(run_id, day, conclusion, *, attempt=1, status="completed", event="schedule"):
    return {
        "id": run_id,
        "run_attempt": attempt,
        "event": event,
        "status": status,
        "conclusion": conclusion,
        "created_at": f"{day}T10:00:00Z",
        "html_url": f"https://github.com/o/r/actions/runs/{run_id}",
    }


class FakeGh:
    """``RunGhFn`` double: run lists per workflow file, job lists per run id."""

    def __init__(self, runs=None, jobs=None, fail=None):
        self.runs = runs or {}
        self.jobs = jobs or {}
        self.fail = fail or {}
        self.calls: list[str] = []

    def __call__(self, repo, args):
        assert args[0] == "api"
        path = args[1]
        self.calls.append(path)
        if "/actions/workflows/" in path:
            workflow = path.split("/actions/workflows/")[1].split("/")[0]
            if workflow in self.fail:
                return {"stdout": "", "stderr": self.fail[workflow], "returncode": 1}
            # GitHub lists newest first.
            newest_first = sorted(self.runs.get(workflow, []), key=lambda r: -r["id"])
            return {
                "stdout": json.dumps({"workflow_runs": newest_first}),
                "stderr": "",
                "returncode": 0,
            }
        run_id = int(path.split("/actions/runs/")[1].split("/")[0])
        jobs = [{"name": n, "conclusion": c} for n, c in self.jobs[run_id]]
        return {"stdout": json.dumps({"jobs": jobs}), "stderr": "", "returncode": 0}

    def job_calls(self):
        return [c for c in self.calls if "/jobs" in c]


class Telegram:
    def __init__(self, reply=None):
        self.reply = reply or {"ok": True}
        self.texts: list[str] = []

    def __call__(self, url, data):
        self.texts.append(json.loads(data)["text"])
        return self.reply


def seed(state_dir: Path, *, last_summary="2026-11-16", workflows=None) -> bytes:
    """A state file whose summary is already sent, so only alerts can go out."""
    state_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps({"last_summary": last_summary, "workflows": workflows or {}}).encode()
    (state_dir / "state.json").write_bytes(raw)
    return raw


def state_of(state_dir: Path, watch: Watch = NIGHTLY) -> dict:
    data = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    return data["workflows"][f"{watch.repo} {watch.workflow} {watch.event}"]


def go(tmp_path, gh, tg, *, watches=(NIGHTLY,), today=TUE, **kwargs):
    return run(
        list(watches), state_dir=tmp_path / "st", today=today, run_gh=gh, post=tg, env=ENV, **kwargs
    )


# -- first red run, then only a job the streak has not named yet (#2229) -------


def test_red_streak_sends_once_then_again_only_when_a_job_not_named_yet_fails(tmp_path):
    seed(tmp_path / "st")
    runs = [row(1, "2026-11-10", "success"), row(2, "2026-11-11", "failure")]
    jobs = {
        2: [("unit", "failure"), ("lint", "success"), ("docs", "skipped")],
        3: [("unit", "failure")],
        4: [("slow", "timed_out"), ("unit", "failure")],
        5: [("slow", "timed_out"), ("unit", "success")],
        6: [("unit", "failure"), ("slow", "timed_out")],
        7: [("e2e", "failure"), ("unit", "success")],
    }
    gh, tg = FakeGh({"nightly.yml": runs}, jobs), Telegram()

    # #2225 AC1: the latest scheduled run failed -> one message, failing jobs and the run link.
    assert go(tmp_path, gh, tg) == 0
    assert tg.texts == [
        "Scheduled CI red: o/r nightly.yml\n\n"
        "2026-11-11 — new red run\n"
        "Failing jobs: unit\n"
        "https://github.com/o/r/actions/runs/2"
    ]

    # #2225 AC2: next night, same failing jobs -> the run is handled, nothing is sent.
    runs.append(row(3, "2026-11-12", "failure"))
    assert go(tmp_path, gh, tg) == 0
    assert len(tg.texts) == 1
    assert state_of(tmp_path / "st")["cursor"]["id"] == 3

    # #2229 AC1: a second job fails for the first time -> a message naming it.
    runs.append(row(4, "2026-11-13", "failure"))
    assert go(tmp_path, gh, tg) == 0
    assert tg.texts[1:] == [
        "Scheduled CI red: o/r nightly.yml\n\n"
        "2026-11-13 — new failing jobs: slow\n"
        "Failing jobs: slow, unit\n"
        "https://github.com/o/r/actions/runs/4"
    ]

    # #2229 AC1: the set flips to slow alone and back to slow + unit. Each differs from
    # the night before, and every job in them was already named -> silence.
    runs.append(row(5, "2026-11-14", "failure"))
    assert go(tmp_path, gh, tg) == 0
    runs.append(row(6, "2026-11-15", "failure"))
    assert go(tmp_path, gh, tg) == 0
    assert len(tg.texts) == 2
    assert state_of(tmp_path / "st")["cursor"]["id"] == 6

    # #2229 AC2: later in the same streak a third job fails for the first time.
    runs.append(row(7, "2026-11-16", "failure"))
    assert go(tmp_path, gh, tg) == 0
    assert tg.texts[2:] == [
        "Scheduled CI red: o/r nightly.yml\n\n"
        "2026-11-16 — new failing jobs: e2e\n"
        "Failing jobs: e2e\n"
        "https://github.com/o/r/actions/runs/7"
    ]


def test_open_streak_written_by_the_reader_before_2229_is_carried_on(tmp_path):
    # Before #2229 an open streak was stored as {"jobs", "since"}: the last failing set.
    seed(
        tmp_path / "st",
        workflows={
            "o/r nightly.yml schedule": {
                "cursor": {"id": 2, "attempt": 1},
                "red": {"jobs": ["slow", "unit"], "since": "2026-11-12"},
            }
        },
    )
    runs = [row(2, "2026-11-12", "failure"), row(3, "2026-11-13", "failure")]
    jobs = {3: [("unit", "failure")], 4: [("lint", "failure"), ("slow", "failure")]}
    gh, tg = FakeGh({"nightly.yml": runs}, jobs), Telegram()

    # unit was in the stored set: it counts as named, so the smaller set is silent.
    assert go(tmp_path, gh, tg) == 0
    assert tg.texts == []
    assert state_of(tmp_path / "st")["cursor"]["id"] == 3

    # slow was in the stored set too and stays named; only lint is new.
    runs.append(row(4, "2026-11-14", "failure"))
    assert go(tmp_path, gh, tg) == 0
    assert tg.texts == [
        "Scheduled CI red: o/r nightly.yml\n\n"
        "2026-11-14 — new failing jobs: lint\n"
        "Failing jobs: lint, slow\n"
        "https://github.com/o/r/actions/runs/4"
    ]


def test_red_run_without_a_failed_job_is_named_by_its_conclusion(tmp_path):
    seed(tmp_path / "st")
    gh = FakeGh({"nightly.yml": [row(7, "2026-11-16", "startup_failure")]}, {7: []})
    tg = Telegram()
    assert go(tmp_path, gh, tg) == 0
    assert tg.texts == [
        "Scheduled CI red: o/r nightly.yml\n\n"
        "2026-11-16 — new red run\n"
        "Failing jobs: (no failed job: startup_failure)\n"
        "https://github.com/o/r/actions/runs/7"
    ]


def test_cancelled_run_keeps_the_streak_and_a_green_run_ends_it(tmp_path):
    seed(tmp_path / "st")
    runs = [row(1, "2026-11-13", "failure")]
    jobs = {n: [("unit", "failure")] for n in (1, 3, 5)}
    gh, tg = FakeGh({"nightly.yml": runs}, jobs), Telegram()
    go(tmp_path, gh, tg)
    assert len(tg.texts) == 1

    # cancelled is neither red nor green: the same streak goes on, silently.
    runs += [row(2, "2026-11-14", "cancelled"), row(3, "2026-11-15", "failure")]
    go(tmp_path, gh, tg)
    assert len(tg.texts) == 1
    assert state_of(tmp_path / "st")["cursor"]["id"] == 3

    # green closes it: the same failing job afterwards is a new red run.
    runs += [row(4, "2026-11-16", "success"), row(5, "2026-11-17", "failure")]
    go(tmp_path, gh, tg, today=date(2026, 11, 18))
    assert tg.texts[1:] == [
        "Scheduled CI red: o/r nightly.yml\n\n"
        "2026-11-17 — new red run\n"
        "Failing jobs: unit\n"
        "https://github.com/o/r/actions/runs/5"
    ]


# -- catching up ---------------------------------------------------------------


def test_host_off_for_three_days_catches_up_in_one_message(tmp_path):
    seed(
        tmp_path / "st",
        workflows={"o/r nightly.yml schedule": {"cursor": {"id": 1, "attempt": 1}, "red": None}},
    )
    runs = [
        row(1, "2026-11-13", "success"),
        row(2, "2026-11-14", "failure"),
        row(3, "2026-11-15", "failure"),
        row(4, "2026-11-16", "failure"),
    ]
    jobs = {2: [("unit", "failure")], 3: [("slow", "failure")], 4: [("slow", "failure")]}
    gh, tg = FakeGh({"nightly.yml": runs}, jobs), Telegram()
    assert go(tmp_path, gh, tg) == 0
    assert tg.texts == [
        "Scheduled CI red: o/r nightly.yml\n\n"
        "2026-11-14 — new red run\n"
        "Failing jobs: unit\n"
        "https://github.com/o/r/actions/runs/2\n\n"
        "2026-11-15 — new failing jobs: slow\n"
        "Failing jobs: slow\n"
        "https://github.com/o/r/actions/runs/3"
    ]
    assert state_of(tmp_path / "st")["cursor"]["id"] == 4


def test_catch_up_too_long_for_one_telegram_message_keeps_the_newest_alert(tmp_path):
    # Telegram refuses a text over 4096 characters. An unsent alert is retried, so an
    # oversized one would be rebuilt and refused every morning.
    seed(
        tmp_path / "st",
        workflows={"o/r nightly.yml schedule": {"cursor": {"id": 0, "attempt": 1}, "red": None}},
    )
    # five nights, a different job each: five alerts of about 1000 characters.
    names = {i: "abcde"[i - 1] * 1000 for i in range(1, 6)}
    runs = [row(i, f"2026-11-1{i + 1}", "failure") for i in range(1, 6)]
    jobs = {i: [(names[i], "failure")] for i in range(1, 6)}
    gh, tg = FakeGh({"nightly.yml": runs}, jobs), Telegram()
    assert go(tmp_path, gh, tg) == 0
    assert tg.texts == [
        "Scheduled CI red: o/r nightly.yml\n\n"
        "(4 earlier alerts left out: the message would be too long for Telegram)\n\n"
        f"2026-11-16 — new failing jobs: {names[5]}\n"
        f"Failing jobs: {names[5]}\n"
        "https://github.com/o/r/actions/runs/5"
    ]
    assert state_of(tmp_path / "st")["cursor"]["id"] == 5


def test_one_alert_too_long_for_telegram_is_cut_and_keeps_its_link(tmp_path):
    seed(tmp_path / "st")
    gh = FakeGh({"nightly.yml": [row(7, "2026-11-16", "failure")]}, {7: [("a" * 5000, "failure")]})
    tg = Telegram()
    assert go(tmp_path, gh, tg) == 0
    (text,) = tg.texts
    assert len(text) == 4096
    assert text.startswith(
        "Scheduled CI red: o/r nightly.yml\n\n2026-11-16 — new red run\nFailing jobs: aaaa"
    )
    assert text.endswith("aaaa…\nhttps://github.com/o/r/actions/runs/7")


def test_first_run_without_state_handles_only_the_newest_completed_run(tmp_path):
    seed(tmp_path / "st")
    runs = [
        row(1, "2026-11-14", "failure"),
        row(2, "2026-11-15", "failure"),
        row(3, "2026-11-16", "success"),
        row(4, "2026-11-17", None, status="in_progress"),
    ]
    gh, tg = FakeGh({"nightly.yml": runs}, {}), Telegram()
    assert go(tmp_path, gh, tg) == 0
    assert tg.texts == []
    assert gh.job_calls() == []  # old red runs are not replayed
    assert state_of(tmp_path / "st") == {"cursor": {"id": 3, "attempt": 1}, "red": None}


def test_unfinished_run_is_left_for_a_later_morning(tmp_path):
    cursor = {"o/r nightly.yml schedule": {"cursor": {"id": 1, "attempt": 1}, "red": None}}
    seed(tmp_path / "st", workflows=cursor)
    pending = row(2, "2026-11-15", None, status="in_progress")
    runs = [row(1, "2026-11-14", "success"), pending, row(3, "2026-11-16", "failure")]
    gh = FakeGh({"nightly.yml": runs}, {2: [("unit", "failure")], 3: [("unit", "failure")]})
    tg = Telegram()
    go(tmp_path, gh, tg)
    assert tg.texts == []
    assert state_of(tmp_path / "st")["cursor"]["id"] == 1  # run 3 is not skipped over run 2

    pending.update(status="completed", conclusion="failure")
    go(tmp_path, gh, tg)
    assert [t.splitlines()[2] for t in tg.texts] == ["2026-11-15 — new red run"]
    assert state_of(tmp_path / "st")["cursor"]["id"] == 3


def test_rerun_of_the_last_handled_run_is_read_again(tmp_path):
    seed(tmp_path / "st")
    red = row(2, "2026-11-16", "failure")
    runs = [red]
    gh = FakeGh({"nightly.yml": runs}, {2: [("unit", "failure")], 3: [("unit", "failure")]})
    tg = Telegram()
    go(tmp_path, gh, tg)
    assert len(tg.texts) == 1

    # someone re-ran the red run and it passed: the streak is over ...
    red.update(run_attempt=2, conclusion="success")
    go(tmp_path, gh, tg)
    assert state_of(tmp_path / "st") == {"cursor": {"id": 2, "attempt": 2}, "red": None}

    # ... so the same failing job the next night is a new red run.
    runs.append(row(3, "2026-11-17", "failure"))
    go(tmp_path, gh, tg, today=date(2026, 11, 18))
    assert [t.splitlines()[2] for t in tg.texts[1:]] == ["2026-11-17 — new red run"]


def test_cursor_older_than_the_page_prints_a_gap_line(tmp_path, capsys):
    seed(
        tmp_path / "st",
        workflows={"o/r nightly.yml schedule": {"cursor": {"id": 5, "attempt": 1}, "red": None}},
    )
    page = [row(100 + n, "2026-11-10", "success") for n in range(50)]
    go(tmp_path, FakeGh({"nightly.yml": page}), Telegram())
    assert "scheduled_ci_reader: GAP — o/r nightly.yml" in capsys.readouterr().out

    # a short page holds the whole history: nothing can be missing.
    seed(
        tmp_path / "st",
        workflows={"o/r nightly.yml schedule": {"cursor": {"id": 5, "attempt": 1}, "red": None}},
    )
    go(tmp_path, FakeGh({"nightly.yml": page[:10]}), Telegram())
    assert "GAP" not in capsys.readouterr().out


# -- AC4: the Monday summary ---------------------------------------------------


def test_monday_summary_is_sent_when_everything_is_green(tmp_path):
    seed(tmp_path / "st", last_summary="2026-11-09")
    nightly = [
        row(1, "2026-11-08", "success"),  # before the window
        row(2, "2026-11-09", "success"),
        row(3, "2026-11-12", "success"),
        row(4, "2026-11-15", "success"),
        row(5, "2026-11-16", "success"),  # the Monday itself: next week's
    ]
    gh = FakeGh({"nightly.yml": nightly, "weekly.yml": [row(9, "2026-11-10", "success")]})
    tg = Telegram()
    assert go(tmp_path, gh, tg, watches=(NIGHTLY, WEEKLY), today=date(2026, 11, 16)) == 0
    assert tg.texts == [
        "Scheduled CI weekly summary: 2026-11-09..2026-11-15\n\n"
        "o/r nightly.yml: 3 runs, 0 red\n"
        "o/r weekly.yml: 1 runs, 0 red"
    ]


def test_summary_missed_on_monday_goes_out_once_on_the_next_run(tmp_path):
    seed(
        tmp_path / "st",
        last_summary="2026-11-09",
        workflows={
            "o/r nightly.yml schedule": {
                "cursor": {"id": 4, "attempt": 1},
                "red": None,
            }
        },
    )
    nightly = [
        row(2, "2026-11-10", "failure"),
        row(3, "2026-11-11", "cancelled"),
        row(4, "2026-11-12", "success"),
    ]
    gh, tg = FakeGh({"nightly.yml": nightly}), Telegram()
    assert go(tmp_path, gh, tg, today=TUE) == 0
    assert tg.texts == [
        "Scheduled CI weekly summary: 2026-11-09..2026-11-15\n\no/r nightly.yml: 3 runs, 1 red"
    ]
    assert go(tmp_path, gh, tg, today=TUE) == 0
    assert len(tg.texts) == 1


# -- AC5: one config line per watched workflow ---------------------------------


def test_one_config_line_adds_one_watched_workflow():
    shipped = (REPO_ROOT / "config" / "scheduled-ci.conf").read_text(encoding="utf-8")
    watches = parse_watch_conf(shipped)
    assert Watch("SergazyNarynov/redrobot", "ci.yml", "schedule") in watches
    assert Watch("SergazyNarynov/redrobot", "security.yml", "schedule") in watches

    extended = parse_watch_conf(shipped + "\no/r extra.yml event=workflow_dispatch\n")
    assert extended == [*watches, Watch("o/r", "extra.yml", "workflow_dispatch")]


def test_config_line_without_a_workflow_file_is_rejected_with_its_line_number():
    with pytest.raises(ValueError, match="line 2: expected 'owner/repo workflow-file"):
        parse_watch_conf("# watch list\no/r\n")


def test_config_line_with_an_unknown_key_is_rejected():
    with pytest.raises(ValueError, match="line 1: unknown token 'branch=main'"):
        parse_watch_conf("o/r nightly.yml branch=main\n")


# -- AC6: failures are loud ----------------------------------------------------


def test_failed_send_exits_nonzero_with_failed_line_and_is_retried(tmp_path, capsys):
    before = seed(tmp_path / "st")
    gh = FakeGh({"nightly.yml": [row(2, "2026-11-16", "failure")]}, {2: [("unit", "failure")]})
    refused = Telegram({"ok": False, "description": "chat not found"})

    assert go(tmp_path, gh, refused) == 1
    assert (
        "scheduled_ci_reader: FAILED — telegram API refused: chat not found"
        in capsys.readouterr().err
    )
    # nothing is remembered as reported ...
    assert (tmp_path / "st" / "state.json").read_bytes() == before
    log = [json.loads(line) for line in (tmp_path / "st" / "log.jsonl").read_text().splitlines()]
    assert [(e["kind"], e["workflow"], e["result"]) for e in log] == [
        ("alert", "o/r nightly.yml schedule", "failed")
    ]

    # ... so the next run sends it.
    tg = Telegram()
    assert go(tmp_path, gh, tg) == 0
    assert [t.splitlines()[2] for t in tg.texts] == ["2026-11-16 — new red run"]
    log = [json.loads(line) for line in (tmp_path / "st" / "log.jsonl").read_text().splitlines()]
    assert [e["result"] for e in log] == ["failed", "ok"]


def test_failed_summary_send_exits_nonzero_and_is_retried(tmp_path, capsys):
    seed(tmp_path / "st", last_summary="2026-11-09")
    gh = FakeGh({"nightly.yml": [row(2, "2026-11-12", "success")]})
    assert go(tmp_path, gh, Telegram({"ok": False, "description": "bot was blocked"})) == 1
    assert "scheduled_ci_reader: FAILED — telegram API refused: bot was blocked" in (
        capsys.readouterr().err
    )
    tg = Telegram()
    assert go(tmp_path, gh, tg) == 0
    assert [t.splitlines()[0] for t in tg.texts] == [
        "Scheduled CI weekly summary: 2026-11-09..2026-11-15"
    ]


def test_failed_read_exits_nonzero_and_other_workflows_are_still_read(tmp_path, capsys):
    seed(tmp_path / "st", last_summary="2026-11-09")
    gh = FakeGh(
        {"weekly.yml": [row(9, "2026-11-10", "failure")]},
        {9: [("scan", "failure")]},
        fail={"nightly.yml": "HTTP 403: rate limit exceeded"},
    )
    tg = Telegram()
    assert go(tmp_path, gh, tg, watches=(NIGHTLY, WEEKLY)) == 1
    assert (
        "scheduled_ci_reader: FAILED — o/r nightly.yml: HTTP 403: rate limit exceeded"
        in capsys.readouterr().err
    )
    assert tg.texts == [
        "Scheduled CI red: o/r weekly.yml\n\n"
        "2026-11-10 — new red run\n"
        "Failing jobs: scan\n"
        "https://github.com/o/r/actions/runs/9",
        "Scheduled CI weekly summary: 2026-11-09..2026-11-15\n\n"
        "o/r nightly.yml: read failed\n"
        "o/r weekly.yml: 1 runs, 1 red",
    ]


# -- dry run and the host gate -------------------------------------------------


def write_root(tmp_path: Path, *, routine_host) -> Path:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "config" / "scheduled-ci.conf").write_text("o/r nightly.yml\n", encoding="utf-8")
    if routine_host is not None:
        (root / "config" / "device.json").write_text(
            json.dumps({"routine_host": routine_host}), encoding="utf-8"
        )
    return root


def run_main(tmp_path, argv, gh, tg, *, routine_host):
    return main(
        [*argv, "--state-dir", str(tmp_path / "st")],
        root=write_root(tmp_path, routine_host=routine_host),
        run_gh=gh,
        post=tg,
        today=TUE,
        environ=ENV,
        env_file=None,
    )


def test_dry_run_prints_the_messages_and_sends_and_writes_nothing(tmp_path, capsys):
    runs = [row(1, "2026-11-01", "failure"), row(2, "2026-11-16", "success")]
    gh, tg = FakeGh({"nightly.yml": runs}, {1: [("unit", "failure")]}), Telegram()
    # no device.json at all: a dry run needs no routine host.
    rc = run_main(tmp_path, ["--dry-run", "--since", "2026-10-31"], gh, tg, routine_host=None)
    out = capsys.readouterr().out
    assert rc == 0
    assert tg.texts == []
    assert not (tmp_path / "st").exists()
    # --since replays history a first run would skip.
    assert (
        "2026-11-01 — new red run\nFailing jobs: unit\nhttps://github.com/o/r/actions/runs/1" in out
    )
    assert "Scheduled CI weekly summary: 2026-11-09..2026-11-15" in out


def test_since_is_refused_outside_a_dry_run(tmp_path, capsys):
    gh, tg = FakeGh({"nightly.yml": []}), Telegram()
    assert run_main(tmp_path, ["--since", "2026-10-31"], gh, tg, routine_host=True) == 2
    assert "--since needs --dry-run" in capsys.readouterr().err
    assert gh.calls == []


def test_since_in_another_date_form_is_refused(tmp_path, capsys):
    # "20261031" parses as a date but compares wrong against "2026-10-31" as text.
    gh, tg = FakeGh({"nightly.yml": [row(1, "2026-11-01", "failure")]}), Telegram()
    rc = run_main(tmp_path, ["--dry-run", "--since", "20261031"], gh, tg, routine_host=None)
    assert rc == 2
    assert "--since is not a YYYY-MM-DD date" in capsys.readouterr().err
    assert gh.calls == []


@pytest.mark.parametrize("routine_host", [False, None])
def test_live_run_is_refused_off_the_routine_host(tmp_path, capsys, routine_host):
    gh, tg = FakeGh({"nightly.yml": [row(2, "2026-11-16", "failure")]}), Telegram()
    assert run_main(tmp_path, [], gh, tg, routine_host=routine_host) == 1
    assert "refused: routines are host-only" in capsys.readouterr().err
    assert gh.calls == []
    assert tg.texts == []


def test_live_run_on_the_routine_host_reads_and_sends(tmp_path):
    gh = FakeGh({"nightly.yml": [row(2, "2026-11-16", "failure")]}, {2: [("unit", "failure")]})
    tg = Telegram()
    assert run_main(tmp_path, [], gh, tg, routine_host=True) == 0
    assert [t.splitlines()[0] for t in tg.texts] == [
        "Scheduled CI red: o/r nightly.yml",
        "Scheduled CI weekly summary: 2026-11-09..2026-11-15",
    ]
