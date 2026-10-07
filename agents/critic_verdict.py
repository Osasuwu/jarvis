"""Critic verdict schema, fail-closed resolution, and consensus (#1686).

Each objection carries either a ``resolution`` or ``blocking: True`` plus a
``rationale`` — an objection that is neither resolved nor a rationalized
blocker is malformed input, not a valid disposition (AC6). An absent or
schema-invalid verdict, after exactly one re-run, is treated as an
unresolved blocking objection: fail-closed, never fail-open (AC7).
Consensus requires zero unresolved objections after at most one revision
cycle (AC8).

An objection that cites a locked or rejected decision carries ``source_path``
and a verbatim ``source_quote`` (#1984); the objection is rejected when the
quote is not a substring of that file, so a critic cannot invent a
constraint and attribute it to a record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class InvalidVerdictError(Exception):
    """Raised when a raw verdict/objection payload does not match the schema."""


@dataclass(frozen=True)
class Objection:
    description: str
    resolution: str | None = None
    blocking: bool = False
    rationale: str | None = None
    source_path: str | None = None
    source_quote: str | None = None

    def is_unresolved(self) -> bool:
        return self.blocking and self.resolution is None


@dataclass(frozen=True)
class Verdict:
    critic: str
    objections: tuple[Objection, ...] = field(default_factory=tuple)

    def has_unresolved_blocking(self) -> bool:
        return any(o.is_unresolved() for o in self.objections)


def validate_objection(raw: dict) -> Objection:
    description = raw.get("description")
    if not description:
        raise InvalidVerdictError("objection missing 'description'")

    resolution = raw.get("resolution")
    blocking = bool(raw.get("blocking", False))
    rationale = raw.get("rationale")

    if resolution is None and not blocking:
        raise InvalidVerdictError(
            "objection must carry either 'resolution' or 'blocking'+'rationale'"
        )
    if blocking and resolution is None and not rationale:
        raise InvalidVerdictError("blocking objection missing 'rationale'")

    source_path = raw.get("source_path")
    source_quote = raw.get("source_quote")
    if source_path is not None or source_quote is not None:
        _check_source_quote(source_path, source_quote)

    return Objection(
        description=description,
        resolution=resolution,
        blocking=blocking,
        rationale=rationale,
        source_path=source_path,
        source_quote=source_quote,
    )


def _check_source_quote(source_path: object, source_quote: object) -> None:
    """Reject a decision citation whose quote is not verbatim in its file.

    Both fields are required together. A relative ``source_path`` resolves
    against the current working directory (the repo root for the callers).
    Line endings are normalized on both sides; nothing else is.
    """
    if not isinstance(source_path, str) or not source_path.strip():
        raise InvalidVerdictError("objection citing a decision missing 'source_path'")
    if not isinstance(source_quote, str) or not source_quote.strip():
        raise InvalidVerdictError("objection citing a decision missing 'source_quote'")
    try:
        # Text mode reads with universal newlines, so the file side is LF.
        text = Path(source_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InvalidVerdictError(f"source_path {source_path!r} is not readable: {exc}") from exc
    quote = source_quote.replace("\r\n", "\n").replace("\r", "\n")
    if quote not in text:
        raise InvalidVerdictError(
            f"source_quote is not a verbatim substring of source_path {source_path!r}"
        )


def validate_verdict(raw: dict) -> Verdict:
    critic = raw.get("critic")
    if not critic:
        raise InvalidVerdictError("verdict missing 'critic'")

    objections_raw = raw.get("objections", [])
    objections = tuple(validate_objection(o) for o in objections_raw)
    return Verdict(critic=critic, objections=objections)


def _forced_unresolved_verdict(reason: str) -> Verdict:
    return Verdict(
        critic="unknown",
        objections=(
            Objection(
                description=f"verdict resolution failed: {reason}",
                blocking=True,
                rationale=reason,
            ),
        ),
    )


def resolve_verdict(raw: dict | None, *, retried: bool) -> Verdict | None:
    """Resolve a raw verdict payload per AC7's fail-closed rule.

    Returns ``None`` when the payload is missing/invalid and a re-run has
    not yet been attempted — the caller should re-run once. After a retry,
    a still-missing or still-invalid payload is forced into an unresolved
    blocking verdict rather than silently passing.
    """
    if raw is None:
        return _forced_unresolved_verdict("no verdict returned") if retried else None

    try:
        return validate_verdict(raw)
    except InvalidVerdictError as exc:
        return _forced_unresolved_verdict(f"schema-invalid verdict: {exc}") if retried else None


def consensus_reached(verdicts: list[Verdict], *, revisions: int) -> bool:
    if revisions > 1:
        return False
    return not any(v.has_unresolved_blocking() for v in verdicts)


def planner_actor(run_id: str) -> str:
    """Actor stamp for planner-role recorded decisions (AC3)."""
    return f"planner:{run_id}"
