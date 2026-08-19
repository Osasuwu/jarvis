"""Morning digest schema (v2).

Envelope for the `morning` daily-digest capability. Deliberately separate from
`status_gather.py` / `status_engine.py` — sections are generalized (the engine
declares names, this schema does not enumerate them) so a new section never
requires a schema change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

SCHEMA_VERSION = 2

VALID_ESTIMATES = {"S", "M", "L"}


class AbsenceKind:
    """Two distinct kinds of source absence — must not be conflated.

    NOT_CONNECTED: stable state — detector not wired up or feature blocked.
      Contributes a known limitation to the lead line; does NOT raise
      degradation_level.
    FAILED: event — source was expected to run and returned an error.
      Raises degradation_level and appears as a failure in the lead line.
    """

    NOT_CONNECTED = "not_connected"
    FAILED = "failed"


@dataclass
class SectionProvenance:
    """Where a section's data came from and whether the fetch succeeded.

    Distinguishes "attempted and failed" (ran=True, ok=False) from
    "ran cleanly, nothing to report" (ran=True, ok=True) — both are distinct
    from a section being wholly ABSENT from Digest.sections.

    absence_kind (AbsenceKind constant) records WHICH kind of not-ok this is
    when ok=False: NOT_CONNECTED (stable, known limitation) or FAILED (event,
    raises degradation). None means the section ran successfully.
    """

    ran: bool = False
    ok: bool = False
    source: str = ""
    input_rows: int = 0
    absence_reason: str | None = None
    absence_kind: str | None = None

    def to_dict(self) -> dict:
        return {
            "ran": self.ran,
            "ok": self.ok,
            "source": self.source,
            "input_rows": self.input_rows,
            "absence_reason": self.absence_reason,
            "absence_kind": self.absence_kind,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionProvenance":
        return cls(
            ran=d.get("ran", False),
            ok=d.get("ok", False),
            source=d.get("source", ""),
            input_rows=d.get("input_rows", 0),
            absence_reason=d.get("absence_reason"),
            absence_kind=d.get("absence_kind"),
        )


@dataclass
class Section:
    """A generalized digest section. The engine names sections; the schema
    does not enumerate them — adding a new section requires no schema change.
    """

    name: str
    items: list[dict] = field(default_factory=list)
    reason: str | None = None
    provenance: SectionProvenance = field(default_factory=SectionProvenance)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "items": self.items,
            "reason": self.reason,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Section":
        return cls(
            name=d["name"],
            items=d.get("items", []),
            reason=d.get("reason"),
            provenance=SectionProvenance.from_dict(d.get("provenance", {})),
        )


@dataclass
class PlanItem:
    rank: int
    estimate: str
    text: str
    refs: list[str] = field(default_factory=list)
    cites: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.estimate not in VALID_ESTIMATES:
            raise ValueError(
                f"invalid estimate {self.estimate!r}, must be one of {sorted(VALID_ESTIMATES)}"
            )

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "estimate": self.estimate,
            "text": self.text,
            "refs": self.refs,
            "cites": self.cites,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlanItem":
        return cls(
            rank=d["rank"],
            estimate=d["estimate"],
            text=d["text"],
            refs=d.get("refs", []),
            cites=d.get("cites", []),
        )


def fold_provenance(sections: list["Section"]) -> dict:
    """Explicit fold from per-section provenances to a digest-level summary.

    Returns:
      degradation_level: count of FAILED sections (NOT_CONNECTED not counted).
      failures: section names that ran but returned ok=False (absence_kind != NOT_CONNECTED).
      known_limitations: section names not connected / detector not wired up.

    Calling this as an explicit operation (not deriving it inline in the render)
    guarantees no per-section stamp is lost silently — the contract that was
    violated by the #1576 form where only the first stamp survived.
    """
    failures = []
    known_limitations = []
    for s in sections:
        prov = s.provenance
        if prov.ok:
            continue
        if prov.absence_kind == AbsenceKind.NOT_CONNECTED:
            known_limitations.append(s.name)
        else:
            failures.append(s.name)
    return {
        "degradation_level": len(failures),
        "failures": failures,
        "known_limitations": known_limitations,
    }


@dataclass
class Plan:
    items: list[PlanItem] = field(default_factory=list)
    cut_line_after: int | None = None

    def to_dict(self) -> dict:
        return {
            "items": [i.to_dict() for i in self.items],
            "cut_line_after": self.cut_line_after,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Plan":
        return cls(
            items=[PlanItem.from_dict(i) for i in d.get("items", [])],
            cut_line_after=d.get("cut_line_after"),
        )


@dataclass
class Digest:
    schema_version: int
    sections: list[Section] = field(default_factory=list)
    plan: Plan = field(default_factory=Plan)
    degradation: dict = field(default_factory=dict)
    origin: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "degradation": self.degradation,
            "sections": [s.to_dict() for s in self.sections],
            "plan": self.plan.to_dict(),
            "origin": self.origin,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Digest":
        return cls(
            schema_version=d["schema_version"],
            sections=[Section.from_dict(s) for s in d.get("sections", [])],
            plan=Plan.from_dict(d.get("plan", {})),
            degradation=d.get("degradation", {}),
            origin=d.get("origin", {}),
        )

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def deserialize(cls, raw: str) -> "Digest":
        return cls.from_dict(json.loads(raw))

    def section(self, name: str) -> Section | None:
        for s in self.sections:
            if s.name == name:
                return s
        return None
