# `/research` skill redesign — brief for `/grill`

Date: 2026-09-30. Status: **direction approved, design not locked.** This file is the input to
the `/grill` session that locks the design; it is not the design. Evidence lives beside it in
[`research-skill-redesign-2026-09-30/`](./research-skill-redesign-2026-09-30/).

> Published here 2026-10-01. The text below is unchanged except for this note and the table
> under *What was examined* (01 and 02 marked *not published*, 09 and 10 added). The design was
> locked through `/grill` on 2026-09-30 and implemented as `/research` v7 in the private operator
> repo, which holds the skill source (jarvis#1923); "this repo" in the text means that repo.
> Files 01 and 02 are raw audits of local session transcripts and of reports in private repos;
> they stay there. The findings below state what they found.

## The job the skill has to keep doing

Get the agent out of the bubble of its own internal information and its own uncertainty before
a decision is made. Stated goal for the redesign: a skill that then stays unchanged for a long
time.

## What was examined

| # | File | What it is |
|---|---|---|
| 01 | `01-session-audit.md` — *not published* | Every `/research` execution found in local transcripts (25 runs, 2026-07-27 onward): tools, errors, budget, where the report was saved, what the user said next |
| 02 | `02-report-audit.md` — *not published* | 63 existing reports classified; 13 deep-read; 23 claim groups fetched and checked against their sources |
| 03 | `03-methodology-evidence.md` | External evidence on what makes agent web research accurate |
| 04 | `04-services-survey.md` | Third-party research services and the bundled `deep-research` workflow |
| 05–08 | `05…08-test-*.md` | Head-to-head on one question: own skill vs bundled `deep-research`, each report with an independent claim-by-claim citation audit |
| 09 | `09-critic-verdict-raw.md` | The cross-context critic's verdict at the design lock |
| 10 | `10-auditor-smoke-test.md` | Cold runs of the v7 auditor on a seeded draft |

Files 05 and 07 are test outputs with known defects (listed in 06 and 08). They are evidence
about the two methods, not reports to cite.

## Findings that drive the design

1. **The skill's recurring defect is unsupported quotation and misread numbers, not thin
   coverage.** Historical sample: a sentence in quotation marks attributed to three Reddit
   threads that contains it in none (02, item 6). Test run: one merged quote, one false
   "limitation" of a paper, one misread statistic — 13 defects in 197 audited claims (06).
2. **A fresh-context citation audit finds them.** Each audit cost ~90–110k tokens. External
   evidence agrees on the mechanism: most final-report errors originate at the orchestrator's
   synthesis step, and a fresh context judges a prior step better than the context that took it
   (03, Q1).
3. **The bundled `deep-research` workflow is not a replacement.** ~7.09M tokens vs ~119k for
   near-equal audited accuracy (96.4% vs 93.4%, n=1, different auditors). Its verification cut
   kept 25 of 110 extracted claims and left two of four sub-questions unanswered. Web-only, no
   `docs/research/` artifact. Its strength is worth borrowing: one isolated reader per source,
   every claim carried with a direct quote — zero fabricated quotes (07, 08).
4. **The tool layer is what breaks the skill.** Three tool-surface changes in two months
   (WebSearch → Firecrawl connector 08-03; `firecrawl_research_search_github` gone by 09-05;
   `firecrawl_extract`, `context7` gone), plus `firecrawl_agent` broken and Reddit refused.
   Firecrawl was never compared against an alternative; it is there because it was installed.
   The `deep-research` arm ran on built-in `WebSearch`/`WebFetch` alone and still found the key
   papers. Firecrawl plan: 1000 credits/month; 334 spent on the day of the test session
   (monthly use: Jul 74, Aug 175, Sep 429).
5. **The current budget contradicts the current protocol.** "2–3 searches + ≤2 scrapes" cannot
   close four mandatory channels; 13 of the 26 audited rows are over budget and 6 within (01), and in the test run
   one channel ended with a single outlet. No rate-limit guidance (limit hit three times). The
   "bare search ≈ 1 KB" figure is wrong — one returned 106 KB.
6. **Reports are not reliably saved where the consumers look.** Several runs wrote only to the
   scratchpad or to memory (01), while `/grill`, `/to-spec` and `/improve-codebase-architecture`
   look for `docs/research/<topic-slug>-*.md` within 60 days.
7. **Scope collapses to the local case.** At least one run answered a narrower question than
   the one asked and was corrected by the user afterwards (01, run 3).

## Approved direction (user, 2026-09-30)

Own skill stays the default research mechanism. It borrows from `deep-research`:
per-source extraction with a direct quote per claim, and an independent citation-audit pass in
a fresh context after the report is written. `deep-research` stays a manual tool for rare
high-stakes questions and is not wired into the skill. Reddit is not a source.

## Open forks for the grill

Each carries the proposer's recommendation; none is decided.

1. **Four channels: mandatory gate or coverage table?** Recommendation: coverage table — the
   report states per channel what was found or why it is empty; an empty channel is a stated
   limitation, not a block. This revisits decision `6fd2df1d-defc-440d-ba30-71880409e533`
   (jarvis#691) and the tests that pin it. Looked up 2026-09-30: in this repo the channels are
   referenced only by `skills/research/SKILL.md` and `tests/test_research_skill_structure.py`;
   no consumer skill depends on them.
2. **Confidence: one `N/100` or per-claim labels?** Recommendation: per-claim labels
   (verified against source / single source / inference / prior), no scalar. Looked up
   2026-09-30: in this repo nothing reads the scalar — the only occurrence outside this
   evidence base is the report template in `skills/research/SKILL.md`; no skill, test or
   workflow parses it. Verbalized confidence emitted while reasoning is poorly calibrated
   (03, arXiv 2604.01457, 2603.25052 — abstracts only).
3. **Tool binding.** Recommendation: `SKILL.md` names capabilities (web search, read a page,
   paper search, issue search) and holds the method; a pull-only reference file maps each
   capability to the current tool with the date it was measured. Built-in `WebSearch`/`WebFetch`
   is the floor that always exists; Firecrawl is an accelerator when connected. Sub-fork: is a
   backend comparison (Firecrawl vs built-in only, same skill, 2–3 past questions) worth running
   before locking?
4. **Audit pass: always, or gated by stakes?** Recommendation: always for reports saved to
   `docs/research/`; skipped only for an explicitly quick lookup. Cost ≈ one extra report.
5. **Local experiment step.** Recommendation: allowed only when sources contradict each other
   or competing options are cheaply testable; bounded (time box, no side effects outside the
   scratchpad), result labelled as own measurement with the command that produced it.
6. **Stopping rule.** Recommendation: sufficiency-based (each sub-question has an answer or a
   stated gap) with a hard ceiling, replacing the fixed per-tool budget.
7. **Scope guard.** Recommendation: the question and its sub-questions are written down before
   the first search and the report answers them in that order.

## Constraints the redesign must respect

- Artifact path `docs/research/<topic-slug>-<date>.md` — the research-pass gate in three
  consumer skills depends on it.
- `tests/test_research_skill_structure.py` pins the 4-channel headings, the decision UUID and
  the "memory recall does not substitute" sentence; `tests/test_end_working_state_rmw.py`
  requires `working_state` or `research-pass` in the file. Tests change deliberately, with the
  reason recorded — never loosened to make an edit pass.
- `needs-research` label contract.
- Skills are read on each device from the master checkout: nothing is live until merged.
