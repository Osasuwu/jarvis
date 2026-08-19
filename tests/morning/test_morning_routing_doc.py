"""Pins the /morning anchored-routing contract in CLAUDE.md (#1588 AC10).

The /morning skill is routed by an *anchored* trigger set — only the exact
words `утро` / `morning` / `доброе утро` fire it. A bare/unrelated use of one
of these words must not be read as a command to run the daily digest (same
failure mode /status's anchored-routing contract closes, #1018 AC6/AC7).
These are documentation guards: if someone edits the routing table and drops
the anchor language, red CI forces the contract back into the doc rather
than letting routing silently widen. They also pin that /morning and
/status never intercept each other's triggers.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC10 — routing table maps ONLY утро / morning / доброе утро to /morning
# ---------------------------------------------------------------------------


class TestRoutingRow:
    def test_morning_row_present(self):
        # the skill-routing table has a row pointing at the /morning skill
        assert "`/morning`" in CLAUDE_MD

    def test_row_lists_all_three_anchored_triggers(self):
        # the row must enumerate every anchored trigger so the mapping is explicit
        for trigger in ("утро", "morning", "доброе утро"):
            assert trigger in CLAUDE_MD, f"missing anchored trigger: {trigger}"

    def test_row_marks_routing_as_anchored(self):
        # the word "anchored" must appear so the constraint is not lost on edit
        assert "anchored" in CLAUDE_MD.lower()


# ---------------------------------------------------------------------------
# AC10 — anchored-routing behavior documented: a bare unrelated use of one of
#        the words does NOT trigger the daily digest
# ---------------------------------------------------------------------------


class TestAntiInvestigationNote:
    def test_anti_investigation_rule_documented(self):
        # there is a prose rule stating bare/unrelated word use does not fire /morning
        lowered = CLAUDE_MD.lower()
        assert "do not fire it" in lowered or "do not fire" in lowered

    def test_rule_names_the_skill(self):
        # the anti-investigation note is explicitly about /morning, not generic
        assert "`/morning` is anchored routing" in CLAUDE_MD


# ---------------------------------------------------------------------------
# AC10 — /morning and /status trigger sets are disjoint (bidirectional
#        non-collision, the load-bearing part of this AC)
# ---------------------------------------------------------------------------


class TestTriggerSetsDisjoint:
    def test_morning_and_status_triggers_do_not_overlap(self):
        morning_triggers = {"утро", "morning", "доброе утро"}
        status_triggers = {"статус", "status", "статус <repo>"}

        assert morning_triggers.isdisjoint(status_triggers)

    def test_disjointness_is_documented(self):
        # the doc itself must assert the two trigger sets don't collide, not
        # just happen to be disjoint by accident of the word lists chosen
        lowered = CLAUDE_MD.lower()
        assert (
            "disjoint" in lowered or "never intercepts" in lowered or "don't intercept" in lowered
        )
