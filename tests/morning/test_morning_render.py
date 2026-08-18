"""Tests for morning_render (#1588).

render(digest_json) -> str is pure, snapshot-tested on a fixture digest built
from scripts.digest_schema (the same schema morning_engine.analyze() produces).
No I/O, no LLM — deterministic Python only, mirroring status_render.py's
contract.
"""

from __future__ import annotations

import io
import json

from scripts.digest_schema import Digest, Plan, PlanItem, SCHEMA_VERSION, Section, SectionProvenance
from scripts.morning_render import main, render


def _digest(**overrides) -> Digest:
    defaults = dict(
        schema_version=SCHEMA_VERSION,
        sections=[
            Section(
                name="repo_hygiene",
                items=[{"repo": "Osasuwu/jarvis", "open_milestones": 0}],
                reason=None,
                provenance=SectionProvenance(ran=True, ok=True, source="morning_gather"),
            ),
        ],
        plan=Plan(
            items=[
                PlanItem(
                    rank=1,
                    estimate="M",
                    text="ship the digest",
                    refs=["goal:ship-morning-digest"],
                    cites=["drift-1"],
                ),
                PlanItem(rank=2, estimate="S", text="review PR", refs=["task:task-1"], cites=[]),
                PlanItem(rank=3, estimate="L", text="deep refactor", refs=[], cites=[]),
            ],
            cut_line_after=2,
        ),
        origin={"gathered_at": "2026-08-18T09:00:00+00:00"},
    )
    defaults.update(overrides)
    return Digest(**defaults)


def test_render_is_pure_and_returns_a_string():
    digest = _digest()

    out1 = render(digest.to_dict())
    out2 = render(digest.to_dict())

    assert isinstance(out1, str)
    assert out1 == out2  # same input -> same output, no hidden state/I-O


def test_block_order_is_degradation_then_know_then_plan_then_evidence():
    degraded = _digest(
        sections=[
            Section(
                name="repo_hygiene",
                items=[{"repo": "Osasuwu/jarvis", "open_milestones": 2}],
                reason=None,
                provenance=SectionProvenance(ran=True, ok=False, source="morning_gather"),
            ),
        ]
    )

    out = render(degraded.to_dict())

    degradation_pos = out.find("Деградация")
    know_pos = out.find("Знать")
    plan_pos = out.find("План")
    evidence_pos = out.find("Гигиена репозиториев")

    assert -1 not in (degradation_pos, know_pos, plan_pos, evidence_pos)
    assert degradation_pos < know_pos < plan_pos < evidence_pos


def test_no_degradation_line_when_every_section_is_ok():
    out = render(_digest().to_dict())

    assert "Деградация" not in out


def test_every_plan_item_prints_its_smL_estimate():
    out = render(_digest().to_dict())

    assert "[M] ship the digest" in out
    assert "[S] review PR" in out
    assert "[L] deep refactor" in out


def test_cut_line_is_visible_after_cut_line_after_item():
    out = render(_digest().to_dict())

    lines = out.splitlines()
    idx_item2 = next(i for i, line in enumerate(lines) if "review PR" in line)
    idx_item3 = next(i for i, line in enumerate(lines) if "deep refactor" in line)
    idx_cut = next(i for i, line in enumerate(lines) if "cut-line" in line)

    assert idx_item2 < idx_cut < idx_item3


def test_cut_line_at_zero_appears_before_first_item():
    digest = _digest()
    digest.plan.cut_line_after = 0

    out = render(digest.to_dict())
    lines = out.splitlines()
    idx_cut = next(i for i, line in enumerate(lines) if "cut-line" in line)
    idx_item1 = next(i for i, line in enumerate(lines) if "ship the digest" in line)

    assert idx_cut < idx_item1


def test_evidence_sections_use_one_consistent_collapse_convention():
    digest = _digest(
        sections=[
            Section(
                name="repo_hygiene",
                items=[{"repo": "Osasuwu/jarvis", "open_milestones": 3}],
                reason=None,
                provenance=SectionProvenance(ran=True, ok=True, source="morning_gather"),
            ),
            Section(
                name="some_new_section",
                items=[{"x": 1}, {"x": 2}],
                reason=None,
                provenance=SectionProvenance(ran=True, ok=True, source="morning_gather"),
            ),
        ]
    )

    out = render(digest.to_dict())

    # Same fold marker used for both sections -> one convention, applied uniformly.
    assert out.count("<details>") == 2
    assert out.count("</details>") == 2
    assert out.count("<summary>") == 2


def test_cites_never_appear_in_rendered_text():
    out = render(_digest().to_dict())

    assert "drift-1" not in out


def test_repo_hygiene_with_no_problems_prints_as_one_line():
    digest = _digest(
        sections=[
            Section(
                name="repo_hygiene",
                items=[
                    {"repo": "Osasuwu/jarvis", "open_milestones": 0},
                    {"repo": "SergazyNarynov/redrobot", "open_milestones": 0},
                ],
                reason=None,
                provenance=SectionProvenance(ran=True, ok=True, source="morning_gather"),
            ),
        ]
    )

    out = render(digest.to_dict())
    lines = [line for line in out.splitlines() if "Гигиена репозиториев" in line]

    assert len(lines) == 1
    assert "<details>" not in out


def test_repo_hygiene_with_problems_lists_them_collapsed():
    digest = _digest(
        sections=[
            Section(
                name="repo_hygiene",
                items=[
                    {"repo": "Osasuwu/jarvis", "open_milestones": 3},
                    {"repo": "SergazyNarynov/redrobot", "open_milestones": 0},
                ],
                reason=None,
                provenance=SectionProvenance(ran=True, ok=True, source="morning_gather"),
            ),
        ]
    )

    out = render(digest.to_dict())

    assert "<details>" in out
    assert "Osasuwu/jarvis" in out
    assert "SergazyNarynov/redrobot" not in out  # only the repo with problems is listed


def test_empty_plan_renders_without_crashing():
    digest = _digest()
    digest.plan.items = []
    digest.plan.cut_line_after = None

    out = render(digest.to_dict())

    assert isinstance(out, str)
    assert "План" in out


# ============================================================================
# Test: CLI entry point (morning_digest MCP | python scripts/morning_render.py)
# ============================================================================
# The skill invokes this as a subprocess piping stdin -> stdout (see
# .claude-userlevel/skills/morning/SKILL.md Step 2). A missing/broken __main__
# is invisible to render()-level unit tests but leaves the skill's documented
# invocation silently printing nothing — caught by an E2E smoke, not unit
# tests, mirroring status_render.py's CLI contract.


def test_main_reads_stdin_and_prints_render(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_digest().to_dict())))

    rc = main([])

    assert rc == 0
    out = capsys.readouterr().out
    assert "[M] ship the digest" in out


def test_main_returns_2_on_invalid_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))

    rc = main([])

    assert rc == 2
    assert "invalid digest JSON" in capsys.readouterr().err
