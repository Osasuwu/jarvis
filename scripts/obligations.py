"""Recurring obligations registry and evaluate() pure function (#1592).

Public interface:
    load_registry(path) -> list[ObligationEntry]
    evaluate(registry, acks, now) -> list[ObligationStatus]
    render_section(statuses, ack_source_error=None) -> str

The registry is a versioned YAML file in the repository. Entries are
added and removed exclusively by humans via PR — no code path mutates
the file. evaluate() is a pure function with zero I/O.

Catch-up policy (per entry):
    "single" — cap missed_periods at 1; high-frequency obligations (daily,
               weekly) should not accumulate a stack of copies when skipped.
    "all"    — track actual missed_periods; rare obligations (monthly,
               quarterly) must not disappear silently after a long gap.

Status rules:
    "unknown"  — no ack and no evidence trace; the system never invents history.
    "ok"       — last_done is observed AND now ≤ last_done + cadence.
    "overdue"  — last_done is observed AND now > last_done + cadence.
    "overdue" is IMPOSSIBLE without an observed last_done date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Optional

import yaml

# ceiling: monthly≈30d, quarterly≈91d — good enough for obligation tracking;
# switch to calendar-aware arithmetic if sub-week precision matters.
_CADENCE_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 91,
}

_VALID_UNITS = tuple(_CADENCE_DAYS)
_VALID_CATCH_UP = ("single", "all")


# ============================================================================
# Data types
# ============================================================================


@dataclass
class ObligationEntry:
    """Parsed registry entry."""

    id: str
    label: str
    cadence_unit: str
    cadence_every: int
    catch_up: Literal["single", "all"]


@dataclass
class AckEvent:
    """Explicit 'done' mark, giving a date to entries without machine traces."""

    obligation_id: str
    date: date


@dataclass
class ObligationStatus:
    """Result of evaluate() for a single registry entry."""

    id: str
    label: str
    status: Literal["ok", "overdue", "unknown"]
    last_done: Optional[date]
    next_due: Optional[date]
    missed_periods: int


# ============================================================================
# Registry loading
# ============================================================================


def load_registry(path: Path | str) -> list[ObligationEntry]:
    """Parse obligations registry YAML; raise ValueError on any broken entry.

    Never adds or removes entries — returns a fresh list every call.
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        raise ValueError(
            f"obligations registry must be a YAML mapping, got {type(raw).__name__}"
        )

    entries_raw = raw.get("entries", [])
    if not isinstance(entries_raw, list):
        raise ValueError("'entries' must be a list")

    result: list[ObligationEntry] = []
    for idx, item in enumerate(entries_raw):
        _validate_entry(item, idx)
        result.append(
            ObligationEntry(
                id=item["id"],
                label=item["label"],
                cadence_unit=item["cadence"]["unit"],
                cadence_every=int(item["cadence"].get("every", 1)),
                catch_up=item.get("catch_up", "single"),
            )
        )
    return result


def _validate_entry(item: object, idx: int) -> None:
    prefix = f"entry[{idx}]"
    if not isinstance(item, dict):
        raise ValueError(f"{prefix}: must be a mapping, got {type(item).__name__}")
    for req in ("id", "label", "cadence"):
        if req not in item:
            raise ValueError(f"{prefix}: missing required field '{req}'")
    cadence = item["cadence"]
    if not isinstance(cadence, dict):
        raise ValueError(f"{prefix}.cadence: must be a mapping, got {type(cadence).__name__}")
    if "unit" not in cadence:
        raise ValueError(f"{prefix}.cadence: missing 'unit'")
    unit = cadence["unit"]
    if unit not in _VALID_UNITS:
        raise ValueError(
            f"{prefix}.cadence.unit: must be one of {_VALID_UNITS}, got {unit!r}"
        )
    catch_up = item.get("catch_up", "single")
    if catch_up not in _VALID_CATCH_UP:
        raise ValueError(
            f"{prefix}.catch_up: must be one of {_VALID_CATCH_UP}, got {catch_up!r}"
        )
    if "every" in cadence:
        every = cadence["every"]
        if not isinstance(every, int) or isinstance(every, bool) or every < 1:
            raise ValueError(
                f"{prefix}.cadence.every: must be a positive integer, got {every!r}"
            )


# ============================================================================
# Pure evaluation
# ============================================================================


def _period_days(entry: ObligationEntry) -> int:
    return _CADENCE_DAYS[entry.cadence_unit] * entry.cadence_every


def evaluate(
    registry: list[ObligationEntry],
    acks: list[AckEvent],
    now: date,
) -> list[ObligationStatus]:
    """Compute status for each obligation entry.

    Pure function — no I/O, no side effects. Returns one ObligationStatus per
    registry entry in the same order.

    Args:
        registry: parsed obligation entries (from load_registry or in-memory fixtures).
        acks: observed 'done' events; multiple acks for one obligation are allowed.
        now: the current date, injected so tests can control time.

    Returns:
        List of ObligationStatus, one per entry.
    """
    # Build ack index: obligation_id → sorted list of ack dates
    ack_index: dict[str, list[date]] = {}
    for ack in acks:
        ack_index.setdefault(ack.obligation_id, []).append(ack.date)
    for dates in ack_index.values():
        dates.sort()

    result: list[ObligationStatus] = []
    for entry in registry:
        ack_dates = ack_index.get(entry.id, [])
        last_done: date | None = ack_dates[-1] if ack_dates else None

        if last_done is None:
            # No observed date → "unknown"; never claim "overdue" without evidence
            result.append(
                ObligationStatus(
                    id=entry.id,
                    label=entry.label,
                    status="unknown",
                    last_done=None,
                    next_due=None,
                    missed_periods=0,
                )
            )
            continue

        period = _period_days(entry)
        next_due = last_done + timedelta(days=period)

        if now <= next_due:
            result.append(
                ObligationStatus(
                    id=entry.id,
                    label=entry.label,
                    status="ok",
                    last_done=last_done,
                    next_due=next_due,
                    missed_periods=0,
                )
            )
        else:
            days_overdue = (now - next_due).days
            # How many full periods have elapsed since next_due
            missed = 1 + (days_overdue // period)
            if entry.catch_up == "single":
                missed = 1  # cap — high-frequency obligations must not stack
            result.append(
                ObligationStatus(
                    id=entry.id,
                    label=entry.label,
                    status="overdue",
                    last_done=last_done,
                    next_due=next_due,
                    missed_periods=missed,
                )
            )

    return result


# ============================================================================
# Section rendering
# ============================================================================


def render_section(
    statuses: list[ObligationStatus],
    ack_source_error: str | None = None,
) -> str:
    """Render the obligations section for the morning digest.

    Shows only overdue entries. Unknown and ok entries are omitted — the section
    is a list of things that need attention, not a full audit.

    Args:
        statuses: output of evaluate().
        ack_source_error: when set, the ack source could not be reached; print
            empty section with the reason instead of potentially misleading data.

    Returns:
        Section text string. Never empty — either lists overdue entries, reports
        all-ok, or explains source unavailability.
    """
    if ack_source_error is not None:
        return f"Обязательства: (недоступно — {ack_source_error})"

    overdue = [s for s in statuses if s.status == "overdue"]
    if not overdue:
        return "Обязательства: всё своевременно"

    lines = ["Обязательства (просрочено):"]
    for status in overdue:
        last = status.last_done.isoformat() if status.last_done else "неизвестно"
        lines.append(f"  • {status.label} — последнее: {last}")
    return "\n".join(lines)
