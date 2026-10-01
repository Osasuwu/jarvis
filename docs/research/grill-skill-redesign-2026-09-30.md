# `/grill` skill redesign — brief for `/grill`

Date: 2026-09-30. Status: **research done, no direction approved, design not locked.** This file
is the input to the `/grill` session that locks the design; it is not the design. Evidence lives
beside it in [`grill-skill-redesign-2026-09-30/`](./grill-skill-redesign-2026-09-30/).

> Published here 2026-10-01 from the operator repo. 01 is not published; the user's quotes from
> it are paraphrased in English.

## The job the skill has to keep doing

Take a plan that is not yet safe to build and turn it into acceptance criteria a fresh agent can
implement: surface the decisions the plan silently assumes, put the ones that are really the
human's in front of the human with the facts needed to decide, have an independent critic attack
the result before it is locked, and write the locked outcome where the next skill will read it.
The session audit shows the core works — every sampled run that reached a critic had at least one
finding that changed the design. The redesign must keep that and remove what the user has already
said, in words, they will not read.

## What was examined

| # | File | What it is |
|---|---|---|
| 01 | `01-session-audit.md` — *not published* (audits local session transcripts; kept in the operator repo) | Every `/grill` invocation in the local transcripts of one device, 2026-07-21 → 09-30: 113 invocations in 104 session files (65 typed by the user, 48 by the model), roughly 96–100 substantive grills; 23 runs deep-read, 29 more skimmed. |
| 02 | `02-external-evidence.md` | The skill's own thirteen external citations checked against their sources, plus 2025–26 evidence on seven practices the skill encodes, each claim with URL and direct quote. |
| 03 | `03-citation-audit.md` | Independent fresh-context check of 02: about 255 atomic claims in 115 rows — 79 supported, 20 supported with a caveat, 10 overstated, 1 number misread, 1 wrong source, 4 unverifiable, 0 quotes not found (164 of 165 quotations verbatim at the cited URL). Where 02 and 03 disagree, this brief follows 03. |

Limits that apply to everything below: one device; "the critic finding was real" is the
dispatching agent's judgement except in five runs where it was verified independently; grill
spans include non-grill work done in the same session, so cost figures are upper bounds; token
counts for the skill file are byte estimates, no tokenizer was run; 02's eight "no evidence
found" statements are negative-search claims that 03 did not audit; the deep-read sample is 23 of
113 runs.

## Findings that drive the design

1. **The sampling critic is the part that earns its cost.** In 19 of 19 sampled runs that
   reached one, at least one finding changed the acceptance criteria or the design, at a median
   of 86.5K subagent tokens and 158 seconds. Strongest cases: the critic killed both the issue's
   and the agent's hypotheses and a null-control script confirmed it; two HIGH findings reversed
   a decision the user had already approved; a dev/test split leak (6 of 15 test entries in dev).
   The one sampled run that locked without a critic had its locked criteria overturned by critics
   dispatched afterwards. 69 of 113 runs reached a critic at all. The severity label carries no
   information: over 64 results, 114 HIGH, 66 MEDIUM, 10 CRITICAL, 3 LOW, and "2 HIGH + 1 MEDIUM"
   in 32 of 64. (01 §Q1, §Q2.)

2. **The coverage tier produces more than the user will read, and the rules around it are
   reasoned away.** Raw items per coverage run: 32 to 144 (192 with sampling and grounding added
   in one run; 353 across three grills in another). Median cost 103.8K tokens and 557 seconds per
   dispatch. What the user did with them: 192 items → 8 decisions (the agent dispositioned 92
   itself); 106 cells → about 3 substantive answers; 114 items → 23 clusters → 23 of 23 "as
   recommended". The 12-cluster cap was exceeded in 4 of 4 full-tier locks (18, 23, 18, 23
   clusters). The ban on blanket acceptance (`SKILL.md:145`) was satisfied by recording "all 12
   agree as recommended" as twelve individual dispositions. In the one run with 59 clusters the
   premise-breaking item was found by the agent after triage, not by any critic. The user said
   twice, in paraphrase, that they would not read all 192 items, and that they had neither the
   time nor the will to read the whole critic output and answer every item. (01 §Q2, §Q3.)

3. **Two of the three Phase 1 questions do not do anything.** On the 88 runs after the gate
   existed: cadence — 53 of 53 tool answers and 9 of 9 text answers chose the default. Time
   budget — 19 of 19 short-budget runs overran ("Quick (~10 min)" → 20 and 22 active minutes;
   "quick" → 140 minutes wall, about 48 of them fact-finding before the first round). The
   budget answer selects no different procedure, so it cannot be honoured. The gate was skipped
   in 8 runs, silently in 5. Two clean references exist: one round of four questions plus one
   critic in 19 minutes; twelve questions, one critic, criteria locked in 47 minutes. (01 §Q1,
   §Q4.)

4. **Compaction is the normal case and the grill's state lives only in context.** 363
   compactions across 99 of 113 runs (median 2, p90 7, max 26). In 10 of 23 sampled runs a
   compaction happened before the first question was asked. Observed losses: eight option sets
   and a process rule in one run (the user noticed that eight option sets had been lost), the
   verbatim critic text in another. Lock files and raw verdicts are written to the session scratchpad; one spec stayed
   there, and one follow-up issue cites a scratchpad path. Saving verbatim critic output was
   blocked twice by the secret-scanner hook and broke on heredoc quoting twice. (01 §Q4, §Q5.)

5. **How much of the skill survives a compaction is not established.** `SKILL.md` is 269 lines,
   23,550 bytes (≈5.9k tokens by byte estimate); Claude Code re-attaches "the first 5,000 tokens"
   of a skill. 02 concluded the critic and grounding phases are lost; 03 re-derived it from byte
   offsets and found the opposite at 4 bytes per token: the cut lands at line 213, inside
   `<supporting-info>`, so Phases 1–4 are re-attached and what falls outside is the
   `needs-grill` removal step (L249–257) and the ADR rules (L259–267). Phase 4 starts to be cut
   only at ≤3.8 bytes per token; the critic dispatch is cut under no tested density. Nobody ran a
   tokenizer. The six sibling files (629 lines) are never re-attached; they are read on demand.
   (02 Q6; 03 defect 1.)

6. **The user wants to decide on facts, and says so.** 216 of 392 parsed answers (55%, a lower
   bound) are the option labelled Recommended; in three runs 20/20, 16/17 and 21/21. Real user
   input arrived as reframes and requests for context, not as option picks. On record, in
   paraphrase: the best option is for the agent to propose the best solution and run the critics
   first, because only then does the user's opinion carry weight, resting on facts rather than
   opinion; asked for a recommendation, the user replied that the agent knows more about the
   topic; the user needed to check that they still remembered their original design; and the
   entry into context should be stronger. Frontier rounds
   themselves hold: the old one-question-at-a-time form took 3.5–5 hours of wall time for seven
   questions in two runs. (01 §Q2, §Q3.)

7. **Checking facts before asking pays; the formal grounding pass pays only on large designs.**
   Informal pre-question fact-finding exposed a false premise in 7 sampled runs, but it is
   unbounded (finding 3). The Phase 4 grounding pass costs a median 94.9K tokens and 357 seconds;
   it found 25–55% drift or missing in two milestone-level runs and almost nothing elsewhere
   (17 MATCH / 1 DRIFT; 17 MATCH / 3 MISSING). (01 §Q2.)

8. **The terminal contract is mostly stale or not executed.** Decision UUIDs appear in issue text
   in 35 of 103 memory-era runs and 0 of 10 since; the memory tools they came from made their
   last successful call on 2026-09-07. `SKILL.md` still cites seven UUIDs as the authority for
   its own rules and makes "verifiable bullets + decision UUIDs" the condition for removing
   `needs-grill`. The label was removed in 5 runs and promised but not removed in 3. An ADR was
   written once in 113 runs, and the user remarked they had forgotten the grill writes ADRs. `CONTEXT.md` was edited in 11.
   Follow-ups were filed with raw `gh issue create` in 8 runs. What does happen: the issue body
   is rewritten in 45 runs. Three sampled runs executed the whole terminal sequence. (01 §Q1,
   §Q5, §Q7.)

9. **Model-invoked grills are where the false triggers and side effects are.** 48 of 113
   invocations came from the model; `/implement`'s `grill_required` exit sits upstream of roughly
   13–16 of them, the `needs-grill` label or the agent's own reading of the checkbox of about 17
   more. Every false or premature trigger found (an issue already sliced; a design already
   decided; an unattended run) came from these paths, and so did the one unattended grill where
   the agent answered its own questions. Against user-invoked runs: tool calls p90 204 vs 80, a
   PR opened inside the grill span in 10 vs 3, code edited in 9 vs 4, a critic reached in 54% vs
   66%. Two sessions held several grills in one invocation (3 and at least 4). One run wrote
   outside its scope: a probe branch and PR in another repo, an unrelated PR closed. (01 §Q6.)

10. **Two embedded gates fire on the wrong thing or not at all.** The experiment-discipline
    checklist is "carried verbatim into the round" and was rejected as inapplicable in 3 runs
    (in the user's words, paraphrased: this is a redesign grill, not an experiment); it was useful in one run that was an
    experiment. The research-pass gate is stated in 26 of 113 runs against 69 that reached a
    critic, blocked none, and names Firecrawl (`SKILL.md:79`). (01 §Q1.)

11. **The skill's numbers do not survive a check against their sources.** Of thirteen citations
    (02 Part A; 03 confirms Part A except one summary line):
    - "~64%" for third-person framing (`SKILL.md:48`, arXiv 2505.23840): the paper says "up to
      63.8% in debate scenario" for a different intervention — a third-person *persona for the
      model*, not a third-person description of the user's proposal.
    - "64.5% … arXiv 2506.04907" (`SKILL.md:91`, `CRITIC-COVERAGE.md:12`): that ID is an
      unrelated paper. The figure is from arXiv 2507.02778, for injected errors in 14 open-source
      non-reasoning models; the same paper reports a "small, even negative" blind spot for
      reasoning models.
    - "CCR F1 28.6 vs 24.6" (arXiv 2603.12123): the numbers are right; one author, one model, 30
      artifacts with injected errors, and the winning condition sends the artifact only.
    - "-1..-12%" (arXiv 2509.05396): the negative half of a table that runs from −12.0 to +5.6,
      on three small models.
    - "MIT 2026" is a CHI 2026 paper (arXiv 2509.12517); "ICLR 2026" cannot be identified;
      Klein's "30%" is a 1989 study of humans; the SHARD "Value (subtle)/(coarse)" split was not
      found in any source.

12. **External evidence on the mechanics is thin, and mostly about something adjacent.**
    - Asking helps on underspecified tasks ("by up to 74% over the non-interactive settings" in
      one benchmark) and always-asking measurably over-asks; one study's better policy asks
      fewer questions and grounds them in "observable behaviors" rather than "internal state users would not know".
      All with caveats: several quotes are from figure captions, users are simulated in at least
      three of five studies. (02 Q1; 03 defect 10.)
    - One-at-a-time vs batched questions, and attaching a recommended answer: no controlled
      evidence found. Upstream switched to batched in July 2026 and calls the point "genuinely
      contested".
    - LLM reviewers are low-precision (best F1 19.38% on one PR-review benchmark); the one
      mitigation with a measured effect is aggregating several independent reviews. A
      "flag only real problems" calibration line is practitioner habit, not a supported
      mitigation — the project it comes from later removed its plan-review loop for adding
      "~25 min overhead" without measurable quality gain. (02 Q2; 03 defect 5.)
    - Guideword sweeps (SHARD, STPA, premortem) applied by an LLM to a software design: no
      evidence found. The nearest measurement — 19–37% valid items — is unfiltered output of
      December-2024 models in a full-automation HAZOP study. (02 Q4; 03 defect 7.)
    - Grounding a design against the code before locking: no controlled evidence either way.
    - Adherence falls as the number of discrete instructions in a prompt rises; nothing measures
      line count. (02 Q6; 03 defect 3.)

13. **The sycophancy defence rests on mechanism, not on a number.** The third-person evidence is
    mixed by scenario: unmeasurable in debate for frontier models (already at ceiling), small
    gains in a second scenario for 10 of 11 models, small losses in a third for 9 of 11 — it
    supports neither "64% reduction" nor "no effect", and it tests a different intervention from
    the skill's. Withholding the user's preference from the critic follows from measured
    sycophancy mechanisms but has no 2025–26 measurement of its own. Blunt "push back harder"
    instructions have a measured overcorrection. Locally, the context-scrub block is present
    verbatim in 64 of 76 sampling prompts. (02 Q3; 03 defect 2; 01 §Q1.)

14. **Mechanics that do not work as written.** `model: fable` in frontmatter applies "for the
    rest of the current turn"; the user switched models by hand in four runs, once asking
    whether the grill had switched the model to fable. The description has no "when to use" clause. The body says
    "two phases" and has four. `AskUserQuestion` carried most of the questions (200 calls, 518
    questions) and is not mentioned anywhere in the skill; it is denied in `dontAsk` mode. Three
    sibling files exceed 100 lines without a table of contents; no evaluation exists for the
    skill. "owner" appears on six lines. (02 Q6; 03 defect 9; 01 §Q3.)

15. **The fork has drifted far from its upstream.** The skill forked mattpocock's
    `grill-with-docs` (fork point inferred, 2026-04-30 to 2026-05-13). Upstream is now a 28-line
    `grilling` skill plus a 74-line `domain-modeling` skill, advises starting in a fresh
    conversation, and has no critics, coverage, triage or grounding — those are local additions.
    Comparable skills elsewhere run about 290 lines. (02 Q7; 03 defects 4, 8.)

16. **What already works and should stay.** The sampling critic at lock with a scrubbed prompt;
    fact-checking before asking; a recommended answer per question; frontier rounds; the
    grounding pass on milestone-level designs; the proposal-first pattern; the short one-round
    form; compact per-item answers; absorbing a mid-grill reframe; writing the locked criteria
    into the issue body. (01 §5.)

## Open forks for the grill

Each carries the proposer's recommendation; none is decided.

1. **Size and survival across compaction.** Recommendation: run a real token count before
   deciding anything about layout (finding 5 is two estimates that disagree). Then: body under
   the re-attachment window with margin; the lock-time and terminal steps either inside that
   window or in a sibling the body orders read at the moment of use; grill state — decisions
   made, options still open, critic verdicts — appended to one git-tracked file as it is
   produced, never to the scratchpad; do not start a grill in a nearly full context.

2. **Sampling critic.** Recommendation: keep, and make it non-skippable in every form including
   the short one. Open sub-fork: payload. Today the critic gets the problem statement, the
   proposed direction verbatim and the draft criteria; the one study behind the design had its
   best result with the artifact alone. 03 marks the mapping of the skill's payload onto that
   study's conditions as an inference and the difference between the two non-winning conditions
   as not significant — so this is a cheap thing to try, not an established fix. Second sub-fork:
   two independent critics aggregated (the only mitigation with a measured effect) against one.
   Drop the severity label or stop using it to rank.

3. **Coverage tier and verbatim relay.** Recommendation: cut from the default path. Keep it as an
   explicit opt-in for milestone-level designs; remove "MAY NOT skip" (`SKILL.md:114`). The
   agent dispositions routine items itself, records them in the state file, and brings the user
   only the forks where a real choice exists. Replace the blanket-acceptance ban with something
   that cannot be satisfied by relabelling — or accept that the user may delegate a cluster.
   Dispatch the triage subagent only above a raw-item threshold (one run spent 101K tokens
   triaging 7 items).

4. **Grounding.** Recommendation: keep pre-question fact-finding with a stated bound (time or
   tool calls) after which the agent asks with what it has; keep the Phase 4 pass for
   milestone-level designs only.

5. **Phase 1 gate.** Recommendation: delete the cadence question. Either delete the time-budget
   question too, or make each answer select a named procedure (short form: one round, one critic,
   lock). 32 tests in `tests/test_grill_frontier_rounds.py` pin the current wording.

6. **Modes.** Recommendation: two first-class forms beside the full one. Proposal-first — the
   agent drafts the design, critics attack it, the user decides on the surviving disagreements.
   Short — one round, one critic. This is the "quick tier" the `/implement` brief's fork 3
   depends on.

7. **Context re-entry.** Recommendation: before the first question, a short recap of where the
   design came from, what is already decided and where that is recorded.

8. **Questions.** Recommendation: keep frontier rounds and the recommended answer (neither has
   external evidence; both have local support). Filter candidate questions by impact,
   uncertainty and whether the user can know the answer; what the code can answer is looked up,
   not asked. Scope the experiment-discipline checklist to grills that design an experiment (its
   three questions are pinned verbatim by tests). Name `AskUserQuestion` and give a plain-text
   fallback.

9. **Sycophancy defence.** Recommendation: keep the third-person framing as a cheap default and
   delete the number and the citation behind it; keep withholding the user's preference from the
   critic; add no "push back harder" instruction. A test pins the framing and one UUID.

10. **Terminal contract.** Recommendation: replace decision UUIDs with a `decisions.md` entry
    plus a `## Decisions` block in the issue body; make `needs-grill` removal an executed step
    whose condition names neither UUIDs nor `working_state`; follow-ups through `/file-issue`;
    ADR branch either dropped or reduced to one explicit trigger. Seven of the nine distinct
    UUIDs in the skill's files are pinned by tests — a deliberate test change.

11. **Model-invoked and unattended grills.** Recommendation: a pre-check that the issue is not
    already sliced or decided; one grill per invocation; with no human present, prepare the
    proposal and the critic verdict, write them to the issue, and stop — never self-disposition;
    no writes outside the issue and the state file during a grill.

12. **Citations and wording.** Recommendation: remove every number finding 11 lists, keep at most
    a one-line rationale per mechanism with a citation that was checked; "owner" → neutral
    wording; "two phases" → the real count; the research-pass gate either names no tool or goes.
    Affected lines: `SKILL.md` 48, 91, 96, 98; `CRITIC.md` 3; `CRITIC-COVERAGE.md` 12, 32,
    95–115, 129; `GROUNDING.md` 32; `TRIAGE.md` 8.

13. **Mechanics.** Recommendation: state the model requirement as an instruction the user sees
    (the frontmatter field lasts one turn); add a when-to-use clause to the description; tables
    of contents for the long siblings; write two or three evaluation cases before rewriting —
    the clean runs in finding 3 and the overturned lock in finding 1 are ready-made.

14. **Upstream.** Re-sync with the 28-line upstream and carry the critic as a local addition, or
    keep the fork. Recommendation: keep the fork, but rebuild the body around what finding 16
    lists rather than around the inherited `<supporting-info>` block — most of what makes this
    skill worth running is not upstream.

## Constraints the redesign must respect

- 82 tests in five files pin the skill's wording: `tests/test_grill_frontier_rounds.py` (32),
  `tests/test_grill_critic_subagent.py` (20), `tests/test_grill_critic_smoke.py` (18),
  `tests/test_experiment_discipline_checklist.py` (8), `tests/test_grill_skill_structure.py` (4).
  They pin phase headings, the three gate questions, the frontier-round vocabulary, three
  Russian questions verbatim, and decision UUIDs that no longer resolve. Forks 5, 8, 9 and 10
  cannot land without changing them.
- Tests change deliberately, with the reason recorded — never loosened to make an edit pass.
- `/implement` (`grill_required`), `/to-tickets`, `/dispatch` (the `needs-grill` pre-dispatch
  gate) and `/wayfinder` name `/grill` and its outputs; a changed terminal contract needs the
  same pass over them.
- The skill is user-level: it runs in repos with no `CONTEXT.md`, no `docs/adr/` and no
  `needs-grill` label.
- Skills are read from the master checkout; nothing is live until merged.
