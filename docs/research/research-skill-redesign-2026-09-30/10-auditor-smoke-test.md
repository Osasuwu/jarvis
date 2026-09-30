# Auditor smoke test — /research v7

Date: 2026-09-30. Question tested: can a fresh-context subagent that is given only the
two-sentence prompt from `skills/research/SKILL.md` ("Read `<skill dir>/AUDITOR.md` and follow
it. Draft: `<path>`.") carry out the audit as designed?

This is a test of whether the instructions are followable cold. It is not a measurement of
the skill's error rate: one seeded draft, six claims, one source, n=2 runs.

## The seeded draft

A v7-format draft on "Should a small team start a new LLM feature with an agent framework?",
one source (`https://www.anthropic.com/engineering/building-effective-agents`, 212 195 bytes
by `curl`), proposed `status: answered`, both sub-questions proposed `answered`,
`Open questions: None.` Six claims, five of them planted:

| Claim | Label | What was planted | Expected |
|---|---|---|---|
| C1 | quoted | nothing — quote is on the page, claim matches it | SUPPORTED |
| C2 | quoted | real quote ("often trade latency and cost…"), claim overstated to "always cost more and are slower than a single call" | PARTIAL, narrowed |
| C3 | quoted | fabricated quote ("we recommend LangGraph as the default starting point for most teams") | UNSUPPORTED, removed |
| C4 | inference | rests on C1 and the fabricated C3; the Summary's recommendation rests on C4 | UNSUPPORTED, removed, Summary repaired |
| C5 | prior | unfetched statement about Hacker News | UNCHECKABLE |
| C6 | snippet | text that is in fact verbatim on the page | SUPPORTED, relabelled `quoted` |

## Result

| | Run 1 | Run 2 (after the fix below) |
|---|---|---|
| C1–C6 verdicts | all six as expected | all six as expected |
| C3, C4 removed; `[C4]` gone from the Summary | yes | yes |
| C2 rewritten to the quote, ID kept | yes | yes |
| C6 relabelled `snippet` → `quoted` | yes | yes |
| Q2 status | `answered` → `answered with a gap` | same |
| Label verdict | author's `answered` → `open` | same |
| `## Audit` appended, frontmatter `status`/`audit` set | yes | yes |
| Claims added by the auditor | none | none |
| `## Open questions` | **left as `None.`** | two lines: main question, Q2 |
| `check_artifact.py` | exit 0 (checker as it was then) | exit 0 |
| Cost | ~78.6k tokens, 11 tool calls, 108 s | ~78.5k tokens, 9 tool calls, 94 s |

Both runs fetched the page text with `curl` rather than a model-mediated fetch, reported that
the word "LangGraph" does not occur on the page, and — without adding it as a claim — named
the passage that actually answers the question ("We suggest that developers start by using
LLM APIs directly…", under "When and how to use frameworks"), which points the opposite way
from the fabricated C3. Both noted that the Sources entry says "read in full" while a quote
attributed to that source is not in it.

## Defect found and fixed

Run 1 ended with label verdict `open` next to `Open questions: None.` The auditor saw the
contradiction and said so, but `AUDITOR.md` gave it no right to touch that section, and the
checker passed the file. The `open` branch of the skill writes its issue comment from that
section, so the report would have said "still open" without saying what.

Fix, in the same change: `## Open questions` is the one section the auditor adds lines to
(what is missing, what would settle it — not claims, no IDs); `check_artifact.py` rejects
`status: open` with a missing, empty or `None` section (`open-without-open-question`), with
tests. The run-1 output now fails the checker; run 2, started from the same seeded draft
after the fix, passes.

## Quote check (added after runs 1 and 2)

`check_artifact.py --quotes` fetches each cited page over plain HTTP and looks for the quote
of every `quoted` claim; it does not read the audit table. Run by hand on the files above:

| File | Result | Exit |
|---|---|---|
| seeded draft, before any audit | `C3: NOT FOUND`; 3 quoted claims: 2 found, 1 NOT FOUND | 1 |
| run 1 output | 3 quoted claims: 3 found | 0 |
| run 2 output | 3 quoted claims: 3 found | 0 |

So a seeded draft with a hand-typed "all SUPPORTED" table would still be reported for C3.

Run 3: a third cold auditor, same two-sentence prompt, same seeded draft, `AUDITOR.md` now
with the quote-check step. Same six verdicts as runs 1 and 2; it ran both checks and wrote
`Quote check: … 3 quoted claim(s): 3 found, 0 NOT FOUND, 0 unfetchable, 0 no source` under
the table. 85.9k tokens, 89 s. Re-running both checks on its output by hand gives the same.

Not exercised: the branch where the quote check reports `NOT FOUND` on a claim the auditor
kept. In all three runs the auditor removed the fabricated claim before the check ran.

## What this does not show

- Nothing about drafts whose defects are subtler than a fabricated quote or an "always" for
  an "often" — a rounded number, a dropped condition, a v1/v2 mismatch.
- Nothing about sources that `curl` cannot read (PDF, JS-rendered, blocked): the one source
  here is plain HTML. Share of cited URLs readable by plain HTTP is jarvis#1940.
- Nothing about the orchestrator's half: whether a real run builds the ledger, runs the
  disconfirming searches, dispatches the auditor with the bare prompt and leaves the file
  alone afterwards. The first real `/research` run is that test.
- The author of the seeded draft also wrote the expectations; the auditor was blind to both.
