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


@dataclass
class SectionProvenance:
    """Where a section's data came from and whether the fetch succeeded.

    Distinguishes "attempted and failed" (ran=True, ok=False) from
    "ran cleanly, nothing to report" (ran=True, ok=True) — both are distinct
    from a section being wholly ABSENT from Digest.sections.
    """

    ran: bool = False
    ok: bool = False
    source: str = ""

    def to_dict(self) -> dict:
        return {"ran": self.ran, "ok": self.ok, "source": self.source}

    @classmethod
    def from_dict(cls, d: dict) -> "SectionProvenance":
        return cls(
            ran=d.get("ran", False),
            ok=d.get("ok", False),
            source=d.get("source", ""),
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
    origin: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
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
