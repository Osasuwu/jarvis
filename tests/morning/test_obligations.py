"""Tests for obligations pure-function module (#1592, #1593).

Verifies: registry parsing with clear errors, evaluate() pure function,
cadence calculation (daily/weekly/monthly), catch-up policy (single vs all),
ack event handling, section rendering including ack-source-unavailable path,
evidence-probe support (ProbeResult, probe injection, probe failure handling,
citation mandatory enforcement, section provenance marking).

Tests are direct — nothing goes through the morning digest engine.
"""

from __future__ import annotations

import textwrap
from datetime import date, timedelta
from pathlib import Path

import pytest

from obligations import (
    AckEvent,
    ObligationEntry,
    ObligationStatus,
    ProbeResult,
    evaluate,
    load_registry,
    render_section,
)

# ============================================================================
# Fixture helpers
# ============================================================================

_DAILY = ObligationEntry(
    id="daily-sweep",
    label="Daily sweep",
    cadence_unit="daily",
    cadence_every=1,
    catch_up="single",
)

_WEEKLY = ObligationEntry(
    id="weekly-cleanup",
    label="Weekly cleanup",
    cadence_unit="weekly",
    cadence_every=1,
    catch_up="single",
)

_MONTHLY = ObligationEntry(
    id="monthly-sweep",
    label="Monthly sweep",
    cadence_unit="monthly",
    cadence_every=1,
    catch_up="all",
)

_NOW = date(2026, 8, 19)


def _ack(obligation_id: str, done_on: date) -> AckEvent:
    return AckEvent(obligation_id=obligation_id, date=done_on)


def _entry_with_probe(probe_name: str = "test-probe") -> ObligationEntry:
    return ObligationEntry(
        id="probe-entry",
        label="Probe entry",
        cadence_unit="weekly",
        cadence_every=1,
        catch_up="single",
        probe_name=probe_name,
    )


# ============================================================================
# AC: Registry parsing — versioned file, clear errors on broken records
# ============================================================================


class TestRegistryParsing:
    def test_parse_valid_yaml(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "worktree-cleanup"
                    label: "Worktree cleanup"
                    cadence:
                      unit: "weekly"
                      every: 1
                    catch_up: "single"
            """),
            encoding="utf-8",
        )
        entries = load_registry(registry_file)
        assert len(entries) == 1
        assert entries[0].id == "worktree-cleanup"
        assert entries[0].label == "Worktree cleanup"
        assert entries[0].cadence_unit == "weekly"
        assert entries[0].cadence_every == 1
        assert entries[0].catch_up == "single"

    def test_malformed_root_raises_clear_error(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text("- just a list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_registry(registry_file)

    def test_missing_id_raises_error(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - label: "No id here"
                    cadence:
                      unit: "daily"
            """),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="missing required field 'id'"):
            load_registry(registry_file)

    def test_missing_label_raises_error(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    cadence:
                      unit: "daily"
            """),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="missing required field 'label'"):
            load_registry(registry_file)

    def test_invalid_cadence_unit_raises_error(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    label: "X"
                    cadence:
                      unit: "hourly"
            """),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="cadence.unit"):
            load_registry(registry_file)

    def test_invalid_catch_up_raises_error(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    label: "X"
                    cadence:
                      unit: "daily"
                    catch_up: "maybe"
            """),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="catch_up"):
            load_registry(registry_file)

    def test_zero_every_raises_error(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    label: "X"
                    cadence:
                      unit: "daily"
                      every: 0
            """),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="cadence.every"):
            load_registry(registry_file)

    def test_negative_every_raises_error(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    label: "X"
                    cadence:
                      unit: "daily"
                      every: -1
            """),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="cadence.every"):
            load_registry(registry_file)

    def test_every_defaults_to_one(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    label: "X"
                    cadence:
                      unit: "weekly"
            """),
            encoding="utf-8",
        )
        entries = load_registry(registry_file)
        assert entries[0].cadence_every == 1

    def test_catch_up_defaults_to_single(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    label: "X"
                    cadence:
                      unit: "daily"
            """),
            encoding="utf-8",
        )
        entries = load_registry(registry_file)
        assert entries[0].catch_up == "single"

    def test_load_registry_does_not_mutate_entries(self, tmp_path: Path):
        """No code path adds or removes registry entries automatically."""
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "a"
                    label: "A"
                    cadence:
                      unit: "daily"
            """),
            encoding="utf-8",
        )
        entries = load_registry(registry_file)
        # Mutate the returned list
        entries.append(ObligationEntry("injected", "Injected", "daily", 1, "single"))
        # Reload — must not see the injected entry
        fresh = load_registry(registry_file)
        assert len(fresh) == 1
        assert fresh[0].id == "a"

    def test_entry_with_probe_parses_probe_name(self, tmp_path: Path):
        """AC: Registry entry can carry a probe description."""
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    label: "X"
                    cadence:
                      unit: "weekly"
                    probe: "worktree-probe"
            """),
            encoding="utf-8",
        )
        entries = load_registry(registry_file)
        assert entries[0].probe_name == "worktree-probe"

    def test_entry_without_probe_has_none_probe_name(self, tmp_path: Path):
        """AC: Entry without probe continues to work by ack — probe_name is None."""
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    label: "X"
                    cadence:
                      unit: "weekly"
            """),
            encoding="utf-8",
        )
        entries = load_registry(registry_file)
        assert entries[0].probe_name is None

    def test_non_string_probe_raises_error(self, tmp_path: Path):
        registry_file = tmp_path / "obligations.yaml"
        registry_file.write_text(
            textwrap.dedent("""\
                schema_version: "v1"
                entries:
                  - id: "x"
                    label: "X"
                    cadence:
                      unit: "daily"
                    probe: 42
            """),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="probe"):
            load_registry(registry_file)


# ============================================================================
# AC: ProbeResult — evidence carrier, citation mandatory
# ============================================================================


class TestProbeResult:
    def test_valid_probe_result_accepted(self):
        """AC: Fired probe returns verdict together with citation of found evidence."""
        r = ProbeResult(citation="git log shows commit abc123 on 2026-08-18")
        assert r.citation == "git log shows commit abc123 on 2026-08-18"

    def test_empty_citation_is_rejected(self):
        """AC: Verdict without citation is impossible — rejected, not silently accepted."""
        with pytest.raises(ValueError, match="citation"):
            ProbeResult(citation="")

    def test_whitespace_only_citation_is_rejected(self):
        """AC: Whitespace-only citation also rejected — not a disputable verdict."""
        with pytest.raises(ValueError, match="citation"):
            ProbeResult(citation="   ")

    def test_none_citation_is_rejected(self):
        """AC: None citation rejected at construction time."""
        with pytest.raises((ValueError, TypeError)):
            ProbeResult(citation=None)  # type: ignore[arg-type]


# ============================================================================
# AC: evaluate() — pure function, tested directly
# ============================================================================


class TestEvaluatePureFunction:
    def test_returns_one_status_per_entry(self):
        result = evaluate([_DAILY, _WEEKLY], [], _NOW)
        assert len(result) == 2

    def test_empty_registry_returns_empty(self):
        result = evaluate([], [], _NOW)
        assert result == []

    def test_returns_obligation_status_instances(self):
        result = evaluate([_DAILY], [], _NOW)
        assert isinstance(result[0], ObligationStatus)

    def test_no_ack_gives_unknown_status(self):
        """Entry without execution trace and without ack → 'unknown', never 'overdue'."""
        result = evaluate([_DAILY], [], _NOW)
        assert result[0].status == "unknown"

    def test_unknown_has_no_last_done(self):
        result = evaluate([_DAILY], [], _NOW)
        assert result[0].last_done is None

    def test_unknown_has_no_next_due(self):
        result = evaluate([_DAILY], [], _NOW)
        assert result[0].next_due is None

    def test_overdue_impossible_without_observed_date(self):
        """'overdue' status requires an observed last_done date."""
        # Even if obligation is very old with no ack → unknown, not overdue
        result = evaluate([_MONTHLY], [], date(2020, 1, 1))
        assert result[0].status == "unknown"
        assert result[0].status != "overdue"


# ============================================================================
# AC: Cadence calculation — daily, weekly, monthly
# ============================================================================


class TestCadenceCalculation:
    def test_daily_ok_within_period(self):
        # Done today → ok
        acks = [_ack("daily-sweep", _NOW)]
        result = evaluate([_DAILY], acks, _NOW)
        assert result[0].status == "ok"

    def test_daily_ok_done_yesterday(self):
        # Done yesterday → still within 1-day period
        done = date(2026, 8, 18)  # 1 day ago from _NOW
        acks = [_ack("daily-sweep", done)]
        result = evaluate([_DAILY], acks, _NOW)
        # next_due = done + 1 day = 2026-08-19 = _NOW, so not overdue
        assert result[0].status == "ok"

    def test_daily_overdue_after_one_day(self):
        # Done 2 days ago → overdue
        done = date(2026, 8, 17)  # 2 days ago
        acks = [_ack("daily-sweep", done)]
        result = evaluate([_DAILY], acks, _NOW)
        assert result[0].status == "overdue"

    def test_weekly_ok_within_period(self):
        # Done 6 days ago → still within 7-day period
        done = date(2026, 8, 13)  # 6 days ago
        acks = [_ack("weekly-cleanup", done)]
        result = evaluate([_WEEKLY], acks, _NOW)
        assert result[0].status == "ok"

    def test_weekly_overdue_after_period(self):
        # Done 8 days ago → overdue
        done = date(2026, 8, 11)  # 8 days ago
        acks = [_ack("weekly-cleanup", done)]
        result = evaluate([_WEEKLY], acks, _NOW)
        assert result[0].status == "overdue"

    def test_monthly_ok_within_period(self):
        # Done 15 days ago → ok (period = 30 days)
        done = date(2026, 8, 4)  # 15 days ago
        acks = [_ack("monthly-sweep", done)]
        result = evaluate([_MONTHLY], acks, _NOW)
        assert result[0].status == "ok"

    def test_monthly_overdue_after_period(self):
        # Done 31 days ago → overdue
        done = date(2026, 7, 19)  # 31 days ago
        acks = [_ack("monthly-sweep", done)]
        result = evaluate([_MONTHLY], acks, _NOW)
        assert result[0].status == "overdue"

    def test_biweekly_cadence_respected(self):
        # every=2 weekly = 14-day period
        biweekly = ObligationEntry("bi", "Biweekly", "weekly", 2, "single")
        done = date(2026, 8, 6)  # 13 days ago — still within 14-day period
        acks = [_ack("bi", done)]
        result = evaluate([biweekly], acks, _NOW)
        assert result[0].status == "ok"

    def test_next_due_computed_correctly(self):
        done = date(2026, 8, 12)  # 7 days ago
        acks = [_ack("weekly-cleanup", done)]
        result = evaluate([_WEEKLY], acks, _NOW)
        expected_next = date(2026, 8, 19)  # done + 7 days = _NOW
        assert result[0].next_due == expected_next

    def test_last_done_reflects_ack_date(self):
        done = date(2026, 8, 10)
        acks = [_ack("daily-sweep", done)]
        result = evaluate([_DAILY], acks, _NOW)
        assert result[0].last_done == done


# ============================================================================
# AC: Catch-up policy — per-entry property
# ============================================================================


class TestCatchUpPolicy:
    """
    AC: with the same gap, daily (single) doesn't generate a stack of copies,
    and rare (all) doesn't disappear silently.
    """

    def test_single_policy_caps_missed_periods_at_one(self):
        # Daily single: missed 14 days → missed_periods = 1, not 14
        done = date(2026, 8, 5)  # 14 days ago
        acks = [_ack("daily-sweep", done)]
        result = evaluate([_DAILY], acks, _NOW)
        assert result[0].status == "overdue"
        assert result[0].missed_periods == 1  # capped — no stacking

    def test_all_policy_tracks_actual_missed_periods(self):
        # Monthly all: missed 60 days (~2 months) → missed_periods = 2
        done = date(2026, 6, 20)  # 60 days ago
        acks = [_ack("monthly-sweep", done)]
        result = evaluate([_MONTHLY], acks, _NOW)
        assert result[0].status == "overdue"
        assert result[0].missed_periods == 2  # tracks actual count — doesn't disappear

    def test_all_policy_rare_entry_still_overdue_after_long_gap(self):
        # Monthly all: missed 91 days → still shows as overdue (doesn't disappear)
        done = date(2026, 5, 20)  # ~91 days ago
        acks = [_ack("monthly-sweep", done)]
        result = evaluate([_MONTHLY], acks, _NOW)
        assert result[0].status == "overdue"
        assert result[0].missed_periods >= 3

    def test_single_ok_entry_has_missed_periods_zero(self):
        done = date(2026, 8, 18)  # 1 day ago — ok for daily
        acks = [_ack("daily-sweep", done)]
        result = evaluate([_DAILY], acks, _NOW)
        assert result[0].status == "ok"
        assert result[0].missed_periods == 0

    def test_unknown_has_missed_periods_zero(self):
        result = evaluate([_MONTHLY], [], _NOW)
        assert result[0].status == "unknown"
        assert result[0].missed_periods == 0


# ============================================================================
# AC: Ack events — set last_done and change status
# ============================================================================


class TestAckEvents:
    def test_ack_changes_status_from_unknown_to_ok(self):
        done = date(2026, 8, 18)
        acks = [_ack("daily-sweep", done)]
        result = evaluate([_DAILY], acks, _NOW)
        assert result[0].status == "ok"
        assert result[0].last_done == done

    def test_ack_changes_overdue_to_ok(self):
        # First make it overdue, then ack it today
        old_done = date(2026, 8, 1)  # overdue
        recent_done = date(2026, 8, 18)  # current
        acks = [_ack("daily-sweep", old_done), _ack("daily-sweep", recent_done)]
        result = evaluate([_DAILY], acks, _NOW)
        assert result[0].status == "ok"

    def test_latest_ack_is_used_as_last_done(self):
        # Multiple acks — latest wins
        acks = [
            _ack("daily-sweep", date(2026, 8, 10)),
            _ack("daily-sweep", date(2026, 8, 18)),  # latest
            _ack("daily-sweep", date(2026, 8, 5)),
        ]
        result = evaluate([_DAILY], acks, _NOW)
        assert result[0].last_done == date(2026, 8, 18)

    def test_ack_for_other_obligation_does_not_affect_entry(self):
        # Ack for weekly doesn't affect daily
        acks = [_ack("weekly-cleanup", date(2026, 8, 18))]
        result = evaluate([_DAILY, _WEEKLY], acks, _NOW)
        daily_status = next(s for s in result if s.id == "daily-sweep")
        assert daily_status.status == "unknown"


# ============================================================================
# AC: Evidence-probe — injectable callables, no network
# ============================================================================


class TestEvaluateWithProbes:
    """AC: probes tested with injectable callables, without network access.
    AC: evaluate with probes tested directly, not through the digest engine.
    """

    def test_probe_fires_gives_ok_status(self):
        """AC: Fired probe returns verdict — status is 'ok'."""
        entry = _entry_with_probe()
        probe_fn = lambda: ProbeResult(citation="git log: commit abc123 2026-08-18")
        result = evaluate([entry], [], _NOW, probes={"test-probe": probe_fn})
        assert result[0].status == "ok"

    def test_probe_fires_citation_stored_in_status(self):
        """AC: Fired probe returns verdict together with citation of found evidence."""
        entry = _entry_with_probe()
        citation = "found 3 worktrees removed in git log 2026-08-18"
        probe_fn = lambda: ProbeResult(citation=citation)
        result = evaluate([entry], [], _NOW, probes={"test-probe": probe_fn})
        assert result[0].probe_citation == citation

    def test_probe_sets_last_done_to_now(self):
        """Probe-confirmed entry sets last_done to now (the verification moment)."""
        entry = _entry_with_probe()
        probe_fn = lambda: ProbeResult(citation="confirmed")
        result = evaluate([entry], [], _NOW, probes={"test-probe": probe_fn})
        assert result[0].last_done == _NOW

    def test_probe_failure_raises_gives_unknown(self):
        """AC: Failed probe gives 'unknown', not 'overdue'."""
        entry = _entry_with_probe()

        def failing_probe() -> ProbeResult:
            raise RuntimeError("connection failed")

        result = evaluate([entry], [], _NOW, probes={"test-probe": failing_probe})
        assert result[0].status == "unknown"

    def test_probe_failure_sets_probe_failed_flag(self):
        """AC: Failed probe is marked in section provenance (probe_failed=True)."""
        entry = _entry_with_probe()

        def failing_probe() -> ProbeResult:
            raise ConnectionError("network unreachable")

        result = evaluate([entry], [], _NOW, probes={"test-probe": failing_probe})
        assert result[0].probe_failed is True

    def test_probe_failure_never_overdue(self):
        """AC: Failed probe → 'unknown', never 'overdue' — even with old acks."""
        entry = _entry_with_probe()
        old_ack = _ack("probe-entry", date(2026, 8, 1))  # would be overdue if ack-only

        def failing_probe() -> ProbeResult:
            raise OSError("timeout")

        result = evaluate([entry], [old_ack], _NOW, probes={"test-probe": failing_probe})
        assert result[0].status == "unknown"
        assert result[0].status != "overdue"
        assert result[0].probe_failed is True

    def test_probe_returning_none_treated_as_failure(self):
        """Non-ProbeResult return value is treated as probe failure."""
        entry = _entry_with_probe()
        probe_fn = lambda: None  # type: ignore[return-value]
        result = evaluate([entry], [], _NOW, probes={"test-probe": probe_fn})
        assert result[0].status == "unknown"
        assert result[0].probe_failed is True

    def test_verdict_without_citation_rejected_not_silently_accepted(self):
        """AC: Verdict without citation is impossible — rejected, not silently accepted.

        A probe returning ProbeResult('') raises ValueError in __post_init__,
        which is caught by evaluate() and treated as probe failure → 'unknown'.
        The empty-citation result is never propagated silently.
        """
        entry = _entry_with_probe()

        def probe_with_empty_citation() -> ProbeResult:
            return ProbeResult(citation="")  # raises ValueError in __post_init__

        result = evaluate([entry], [], _NOW, probes={"test-probe": probe_with_empty_citation})
        # The ValueError is caught → probe failure → "unknown", not "ok" or "overdue"
        assert result[0].status == "unknown"
        assert result[0].probe_failed is True
        assert result[0].probe_citation is None

    def test_entry_without_probe_uses_ack_only(self):
        """AC: Entry without probe continues to work via ack — probe_name=None."""
        entry = ObligationEntry("x", "X", "daily", 1, "single")  # no probe_name
        acks = [_ack("x", date(2026, 8, 18))]
        result = evaluate([entry], acks, _NOW)
        assert result[0].status == "ok"
        assert result[0].probe_citation is None
        assert result[0].probe_failed is False

    def test_probe_name_not_in_probes_dict_falls_back_to_acks(self):
        """If probe_name is configured but not in the probes dict, use ack logic."""
        entry = _entry_with_probe("missing-probe")
        acks = [_ack("probe-entry", date(2026, 8, 18))]
        result = evaluate([entry], acks, _NOW, probes={})  # probe not provided
        assert result[0].status == "ok"  # ack-only fallback
        assert result[0].probe_citation is None

    def test_probe_not_in_dict_without_ack_gives_unknown(self):
        """Entry with probe_name not in probes dict and no ack → 'unknown'."""
        entry = _entry_with_probe("missing-probe")
        result = evaluate([entry], [], _NOW, probes={})
        assert result[0].status == "unknown"

    def test_probe_with_none_probes_kwarg_uses_ack(self):
        """probes=None (default) → ack-only logic for all entries."""
        entry = _entry_with_probe()
        acks = [_ack("probe-entry", date(2026, 8, 18))]
        result = evaluate([entry], acks, _NOW, probes=None)
        assert result[0].status == "ok"

    def test_multiple_entries_mixed_probe_and_ack(self):
        """Mixed registry: probe entry and ack-only entry evaluated together."""
        probe_entry = _entry_with_probe()
        ack_entry = ObligationEntry("ack-only", "Ack Only", "daily", 1, "single")
        acks = [_ack("ack-only", date(2026, 8, 18))]
        citation = "CI job #999 passed 2026-08-19"
        probes = {"test-probe": lambda: ProbeResult(citation=citation)}
        result = evaluate([probe_entry, ack_entry], acks, _NOW, probes=probes)
        probe_status = next(s for s in result if s.id == "probe-entry")
        ack_status = next(s for s in result if s.id == "ack-only")
        assert probe_status.status == "ok"
        assert probe_status.probe_citation == citation
        assert ack_status.status == "ok"
        assert ack_status.probe_citation is None


# ============================================================================
# AC: Section rendering — overdue, probe citations, probe failures
# ============================================================================


class TestSectionRendering:
    def test_overdue_entry_shown_in_section(self):
        status = ObligationStatus(
            id="x",
            label="Weekly sweep",
            status="overdue",
            last_done=date(2026, 8, 5),
            next_due=date(2026, 8, 12),
            missed_periods=1,
        )
        text = render_section([status])
        assert "Weekly sweep" in text
        assert "2026-08-05" in text

    def test_ok_entry_without_probe_not_shown(self):
        status = ObligationStatus(
            id="x",
            label="Timely thing",
            status="ok",
            last_done=date(2026, 8, 18),
            next_due=date(2026, 8, 19),
            missed_periods=0,
        )
        text = render_section([status])
        assert "Timely thing" not in text

    def test_unknown_entry_without_probe_not_shown(self):
        status = ObligationStatus(
            id="x",
            label="Never done",
            status="unknown",
            last_done=None,
            next_due=None,
            missed_periods=0,
        )
        text = render_section([status])
        assert "Never done" not in text

    def test_section_all_ok_message_when_no_issues(self):
        status = ObligationStatus(
            id="x",
            label="All good",
            status="ok",
            last_done=date(2026, 8, 18),
            next_due=date(2026, 8, 19),
            missed_periods=0,
        )
        text = render_section([status])
        # Should indicate all is fine, not be empty blank
        assert text.strip()

    def test_section_empty_with_reason_when_source_unavailable(self):
        """AC: When ack source unavailable, section prints empty with reason."""
        text = render_section([], ack_source_error="connection timeout")
        assert "connection timeout" in text
        # Must not be blank — must print the reason
        assert text.strip()

    def test_ack_source_none_is_not_unavailable(self):
        """No error and no statuses → all-ok case, not an error."""
        text = render_section([], ack_source_error=None)
        # Should not claim source unavailable when error is None
        assert "недоступно" not in text

    def test_multiple_overdue_entries_all_shown(self):
        statuses = [
            ObligationStatus("a", "A", "overdue", date(2026, 8, 1), date(2026, 8, 8), 1),
            ObligationStatus("b", "B", "overdue", date(2026, 7, 1), date(2026, 7, 8), 3),
        ]
        text = render_section(statuses)
        assert "A" in text
        assert "B" in text

    def test_probe_citation_visible_in_output(self):
        """AC: Evidence citation is visible in output next to the record."""
        citation = "git log: commit abc123 removed 5 worktrees 2026-08-18"
        status = ObligationStatus(
            id="x",
            label="Worktree cleanup",
            status="ok",
            last_done=_NOW,
            next_due=_NOW + timedelta(days=7),
            missed_periods=0,
            probe_citation=citation,
        )
        text = render_section([status])
        assert citation in text
        assert "Worktree cleanup" in text

    def test_probe_failure_marked_in_section_provenance(self):
        """AC: Failed probe is marked in section provenance (visible in output)."""
        status = ObligationStatus(
            id="x",
            label="Probe Obligation",
            status="unknown",
            last_done=None,
            next_due=None,
            missed_periods=0,
            probe_failed=True,
        )
        text = render_section([status])
        # Section must mention that probe failed — not silently empty
        lower = text.lower()
        assert "проба" in lower or "probe" in lower or "не удалась" in lower
        assert "Probe Obligation" in text

    def test_probe_failure_shown_separately_from_overdue(self):
        """Probe failures and overdue entries appear as distinct groups."""
        overdue_status = ObligationStatus(
            "a", "Overdue thing", "overdue", date(2026, 8, 1), date(2026, 8, 8), 1
        )
        failed_probe_status = ObligationStatus(
            "b", "Probe thing", "unknown", None, None, 0, probe_failed=True
        )
        text = render_section([overdue_status, failed_probe_status])
        assert "Overdue thing" in text
        assert "Probe thing" in text

    def test_probe_confirmed_section_shows_label_and_citation(self):
        """Probe-confirmed ok entry shows both label and citation together."""
        citation = "CI run #42 passed at 2026-08-19T06:00:00Z"
        status = ObligationStatus(
            id="ci",
            label="CI health check",
            status="ok",
            last_done=_NOW,
            next_due=_NOW + timedelta(days=7),
            missed_periods=0,
            probe_citation=citation,
        )
        text = render_section([status])
        assert "CI health check" in text
        assert citation in text
