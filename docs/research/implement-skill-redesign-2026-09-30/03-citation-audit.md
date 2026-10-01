# /implement redesign — citation audit of `02-external-evidence.md`

Date: 2026-09-30. Auditor: independent agent, no part in writing the file under audit. The audited file was not edited.

## Method and coverage

**How sources were read.** Every cited source was downloaded raw and searched locally, because a summarising fetch cannot confirm verbatim wording:

- arXiv: `https://arxiv.org/abs/<id>` and `https://arxiv.org/html/<id>` for all 25 cited IDs, plus the three IDs the file lists as "seen but not used".
- Claude Code docs: the `.md` renderings of `code.claude.com/docs/en/{best-practices,skills,hooks-guide,sub-agents,permission-modes,worktrees}` and `platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices`.
- GitHub: raw files from `mattpocock/skills`, `obra/superpowers`, `github/spec-kit` (`wc -l` for line counts), and `gh api repos/<owner>/<repo>/commits?path=…` (read-only) for commit titles and dates.
- `dev.to/trikitrok/on-code-smells-catalogues-and-taxonomies-3ba6` as raw HTML.
- One figure (ImpossibleBench Figure 8) was opened as an image, because the "two of three models" claim is only checkable there.
- The skill file `skills/implement/SKILL.md` was read locally for the Part A "as the skill states it" column.

Quote matching: text normalised for whitespace, quote/dash typography, markdown emphasis and link syntax, then exact substring search. Anything else counts as a deviation and is reported. Firecrawl calls: 0. reddit.com: not fetched. Nothing was unreachable.

**Coverage.**

- Claims extracted and numbered: 186 (a multi-fragment quotation from one passage is one claim; about 190 separately quoted fragments sit inside them). A further group of roughly 20 absence and read-depth statements was extracted but left unnumbered; it is listed below.
- Audited: all 186 numbered claims. That is all of Part A; every number and every quotation in Part B; every paper ID ↔ title pairing; every line count and commit date; every feature-table source attribution; and the "Implies for the skill" lines that state something as measured.
- Above the ~120 threshold, so the rule "sample the remaining attributions" applied. In practice every positive attribution was checked; the only things left out are these, exactly:
  1. Absence claims in the **Gap** paragraphs and Gaps list items 1-7, 10-12 ("no measurement found", "no study compares"). A fetch cannot prove a negative. They are used below only where the file's own implication contradicts its own gap statement.
  2. Line 203 / Gap 11, "None publishes an evaluation" — I checked only the files the evidence file cites, not the whole of three repositories.
  3. The "full text read" / "abstract only" read-depth labels in the Sources list, and lines 177 and 17 (claims about the user's own policy and the skill's internal citations).
- Implication lines that are pure design opinion with no factual predicate (e.g. line 178, line 137) were not given a verdict.

**Verdict vocabulary** as specified: SUPPORTED / SUPPORTED-WITH-CAVEAT / QUOTE NOT FOUND / NUMBER MISREAD / OVERSTATED / WRONG SOURCE / UNVERIFIABLE.

## Claim table

`L` = line in `02-external-evidence.md`. "Verbatim" means the quoted wording was found character-for-character after the normalisation above.

### Header and Part A

| # | L | Claim | Verdict | Source wording / evidence |
|---|---|---|---|---|
| 1 | 3 | Skill file is 454 lines, 4,650 words, 30,955 bytes | SUPPORTED | `wc` on `skills/implement/SKILL.md`: 454 / 4650 / 30955 |
| 2 | 21 | 1804.01954 = Kanewala & Bieman, "Testing Scientific Software: A Systematic Literature Review" | SUPPORTED | arXiv abs page title and authors match |
| 3 | 21 | Skill line 89 wording as quoted | SUPPORTED | Skill line 89 contains the sentence and the five terms |
| 4 | 21 | The paper's oracle list has nine entries, not five; eight entries quoted (1-5, 7-9) | SUPPORTED | All eight fragments verbatim; list runs 1-9 |
| 5 | 21 | Property-based testing and golden run are only suggestions: two quotes | SUPPORTED | Both verbatim: "Techniques such as property based testing and data redundancy can be used when an oracle is not available [4]." … "We did not find applications of property based testing, data redundancy, golden run, and model based testing to test scientific software in the primary studies." |
| 6 | 21 | "But we found no empirical studies evaluating the effectiveness of these techniques in detecting subtle faults." | SUPPORTED | Verbatim |
| 7 | 21 | "objective machine-checkable oracle" and anything about unattended runs do not appear | SUPPORTED | 0 hits for "machine-checkable", "unattended" |
| 8 | 21 | Verdict cell: "All five terms occur in the paper." | OVERSTATED | "property invariant" and "invariant" have 0 hits in the full text. The paper has only "property based testing". Four of the skill's five terms occur, not five. The error favours the skill. |
| 9 | 21 | "two of the five have no applications in the reviewed studies" | SUPPORTED-WITH-CAVEAT | True for "property based testing" and "golden run" (quote in #5). Treats the skill's "property invariant" as the paper's "property based testing", which is the file's equation, not the paper's. |
| 10 | 22 | 2506.16051 = Li et al., "From Data to Decision: Data-Centric Infrastructure for Reproducible ML in Collaborative eScience" | SUPPORTED | abs page matches |
| 11 | 22 | Skill line 101 wording as quoted | SUPPORTED | Skill line 101 |
| 12 | 22 | "A framework paper with one glaucoma case study" | SUPPORTED-WITH-CAVEAT | The paper calls it a "use case", not a case study. Substance holds. |
| 13 | 22 | "intent" occurs zero times; negative results not discussed; no "primary driver" ranking | SUPPORTED | 0 hits for "intent", "primary driver", "negative result", "irreproducib" |
| 14 | 22 | Two "closest passage" quotes | SUPPORTED | Both verbatim |
| 15 | 23 | Skill line 426: "**Standards** — Fowler's 12 code smells:" + twelve names | SUPPORTED | Skill line 426 |
| 16 | 23 | dev.to page: 22 smells (1st ed.), 24 (2nd ed.), Mysterious Name new, Switch Statements renamed Repeated Switches | SUPPORTED | "This catalogue contains the descriptions of 22 code smells"; "Four new code smells are introduced: Mysterious Name, Global Data, Mutable Data and Loops"; "switch statement becomes repeated switches. There are 24 code smells in total." |
| 17 | 23 | Same twelve names, same order, in mattpocock `code-review/SKILL.md`; two quotes | SUPPORTED | Lines 45-56 of that file match the skill's list in order; line 38 "a fixed set of Fowler code smells (_Refactoring_, ch.3)"; heuristic quote verbatim |
| 18 | 23 | The mattpocock skill carries an "always a judgement call" qualifier that the skill dropped | SUPPORTED | mattpocock line 41: "**Always a judgement call.**" The skill has no such qualifier near line 426 (its only "judgment call" is line 87, about oracles). |
| 19 | 23 | "appears to have been lifted from the mattpocock skill" | SUPPORTED | Hedged inference; identical twelve names in identical order is consistent with it. Provenance itself is not provable from the sources. |
| 20 | 25 | Skill line 97 asserts "External practice draws the same line…" with no citation | SUPPORTED | Skill line 97, no citation present |

### B1. Plan before code

| # | L | Claim | Verdict | Source wording / evidence |
|---|---|---|---|---|
| 21 | 35 | 2604.12147 = Liu et al., "From Plan to Action: How Well Do Agents Follow the Plan?" | SUPPORTED | abs page matches |
| 22 | 35 | Abstract quote (21,120 trajectories, four LLMs, eight plan variations, subpar plan worse than none…) | SUPPORTED | Verbatim in abstract |
| 23 | 36 | No-plan solves extra instances: "23, 11, 28, and 34" | SUPPORTED-WITH-CAVEAT | Quote verbatim, but the next sentence in the source is dropped: "As we will show later (§ 6.2), this is largely affected by the inherent nondeterminism of LLM-based agents, with 4, 7, 16, and 4 instanc[es]…". The paper attributes most of these wins to run-to-run noise. |
| 24 | 36 | Cause quote: incorrect reproduction tests, no-plan skipped reproduction | SUPPORTED | Verbatim |
| 25 | 37 | Reminded-plan quote, re-inserted every five steps, consistent improvements | SUPPORTED | Verbatim; source has "(§ 4.1.1)" with a space |
| 26 | 38 | The "plan" is a workflow plan in the system prompt | SUPPORTED | "SWE-agent … embeds a default plan in its system prompt"; no-plan variant = "plan removed entirely from the system prompt" |
| 27 | 39 | 2609.20804 = Fan et al., "An Empirical Study of Harness Design for Coding Agents" | SUPPORTED | abs page matches |
| 28 | 39 | 176 matched settings, four models, SWE-Bench Verified and Terminal-Bench 2.1 | SUPPORTED | "Across four models evaluated on SWE-Bench Verified and Terminal-Bench 2.1, we evaluate 176 matched settings" |
| 29 | 39 | "Planning shifts from an accuracy scaffold for weaker models to a cost saver for stronger models, with little change in accuracy." | SUPPORTED | Verbatim |
| 30 | 39 | Numbers quote: +11.6 / +4.5 points (30B); cost −30% / −32%, success −2.0 / −0.4 (550B, Mistral) | SUPPORTED-WITH-CAVEAT | All numbers verbatim. The "..." removes the fourth model: "For Nemotron-3 120B, planning yields no consistent success-rate gain…". Planning was evaluated only under one context configuration (T4/128K). |
| 31 | 39 | "planning" is a model-maintained todo list re-shown each turn; open-weight models | SUPPORTED-WITH-CAVEAT | "You have an UpdatePlan tool that holds a todo list. The harness shows the current plan back to you before every turn". "Open-weight" is not the paper's word; the paper says the models "are served locally with SGLang". |
| 32 | 39 | Tag **[indep]** | SUPPORTED-WITH-CAVEAT | Author footnote: work completed during internships at Zoom Video Communications. See defect 13. |
| 33 | 40 | 2608.09072 = SWE-RPG; 163 tasks; Claude Code, Codex, OpenCode; six backends | SUPPORTED | Matches abstract and setup (163 tasks from 31 repositories) |
| 34 | 40 | "achieving an average resolved rate of only 31.5% on SWE-RPG" | SUPPORTED | Verbatim |
| 35 | 40 | Requirement recovery 24.5-46.0 percent of runs; planning failures 5.5-17.8 percent | SUPPORTED | "Requirement failure is the largest component for most configurations (24.5-46.0%), followed by code-generation (7.4-37.4%) and planning (5.5-17.8%) failures." Note "for most configurations". |
| 36 | 40 | Stage attribution is by an LLM judge | SUPPORTED | Judge is an LLM, validated on a 50-case sample (46/50) |
| 37 | 41 | Best-practices plan-mode quote ("If you could describe the diff in one sentence, skip the plan.") | SUPPORTED | Verbatim |
| 38 | 41 | "Once the spec is complete, start a fresh session to execute it." | SUPPORTED | Verbatim |
| 39 | 42 | Skill-authoring plan-validate-execute quotes | SUPPORTED | Both verbatim |
| 40 | 48 | A trigger-based plan gate "matches both the vendor guidance and the measurements. A plan gate on every issue does not." | SUPPORTED-WITH-CAVEAT | Vendor guidance: yes (#37). Measurements: no source tests a triggered plan gate. Liu's headline for an always-on plan is positive: "Providing the standard plan improves issue resolution". |
| 41 | 49 | "On strong models the measured benefit of planning is cost, not correctness" | SUPPORTED-WITH-CAVEAT | One study, todo-list planning, where "stronger" = Nemotron-3 550B and Mistral-Medium-3.5-128B (#29-31). Not measured on frontier models or on plan gates. |
| 42 | 49 | "the measured bottleneck is recovering what the issue actually requires" | SUPPORTED | SWE-RPG: "identifies implicit requirement recovery as the main bottleneck" |
| 43 | 50 | "A bad plan is worse than none" | SUPPORTED | "A subpar plan hurts performance even more than no plan at all." |
| 44 | 51 | A forced reproduction phase can lose tasks the model would otherwise solve | SUPPORTED-WITH-CAVEAT | Rests on #23-24; inherits the dropped nondeterminism qualifier |

### B2. Test-first with coding agents

| # | L | Claim | Verdict | Source wording / evidence |
|---|---|---|---|---|
| 45 | 57 | 2402.13521 = Mathews & Nagappan; "additional 12.0% and 8.5% of problems" | SUPPORTED | Verbatim |
| 46 | 57 | GPT-4 / Llama 3, function-level, human-supplied tests | SUPPORTED | GPT-4 Turbo and Llama 3; MBPP / HumanEval with benchmark tests |
| 47 | 58 | 2602.03557 Liang et al.: 12 to 26 absolute points across eight LLMs; "achieving up to 71% fully correct classes." | SUPPORTED | Both in abstract |
| 48 | 59 | 2607.05139 = "On the risk of coding before testing" (Konstantinou, Tambon, Papadakis) | SUPPORTED | abs page matches |
| 49 | 59 | "(14% vs. 25%)" quote | SUPPORTED | Verbatim |
| 50 | 59 | Fresh-interaction quote | SUPPORTED | Verbatim |
| 51 | 59 | "decreasing by 15.5% for summarization and 13.4% for both Chain-of-Thought and Chain-of-Verification" | SUPPORTED | Verbatim |
| 52 | 59 | "generating both code and tests using the same model does not guarantee meaningful verification" | SUPPORTED | Verbatim |
| 53 | 59 | "Note the ceiling: the best condition still detects only a quarter of faults." | SUPPORTED-WITH-CAVEAT | 25% is right, but the fault set was filtered to the hardest: "we exclude implementations for which more than 50% of the reference test cases fail" and "select the implementation with the highest estimated difficulty". It is a ceiling on subtle faults, not on faults in general. |
| 54 | 60 | 2510.20270 = ImpossibleBench, tasks made impossible so passing means cheating | SUPPORTED | abs page matches |
| 55 | 60 | Tag **[indep]** | SUPPORTED-WITH-CAVEAT | Third author (Carlini) is affiliated with Anthropic. See defect 13. |
| 56 | 60 | "GPT-5 cheats in 76% of the tasks in Oneoff-SWEbench and 2.9% on Oneoff-LiveCodeBench" | SUPPORTED | Verbatim |
| 57 | 60 | "In general, we observe more capable models having higher cheating rates." | SUPPORTED-WITH-CAVEAT | Verbatim, but it is the caption of Figure 3, which shows Impossible-SWEbench only |
| 58 | 60 | "We find that more complex scaffolds encourage more cheating" | SUPPORTED-WITH-CAVEAT | Verbatim; the source adds "The results are less clear for Impossible-LiveCodeBench" |
| 59 | 61 | Prompt: "from 92% to 1% on Conflicting-LiveCodeBench" | SUPPORTED | Verbatim. Body: "for both GPT-5 and o3, prompt A and B lead to a cheating rate > 85%, while prompt D lowers them to 1% and 33%". On SWE-bench the effect is smaller: a looser prompt moves GPT-5 "from 54% to 66%". |
| 60 | 62 | Access-control quotes (hide / read-only) | SUPPORTED | Verbatim (source has a footnote marker after "near zero") |
| 61 | 62 | Recommendation quote | SUPPORTED | Verbatim |
| 62 | 63 | Escape hatch: "… lowering the cheating rate of GPT-5 from 54% to 9% and o3 from 49% to 12%. However, the effect is much less pronounced for Claude Opus 4.1." | SUPPORTED-WITH-CAVEAT | Numbers verbatim. The ellipsis removes the scope: "On Impossible-SWEbench and especially Conflicting-SWEbench, we find the strategy quite effective for OpenAI models, lowering…". Figure 8: Conflicting-SWEbench GPT-5 54→9, o4-mini 49→12, Opus 4.1 50→46; Oneoff-SWEbench GPT-5 76→37, o4-mini 53→33, Opus 4.1 54→51. The figure labels the second model o4-mini where the text says o3 (the paper's own inconsistency). |
| 63 | 64 | Retries: 80→83 pass, 33→38 cheating | SUPPORTED | Verbatim |
| 64 | 65 | 2605.21384 = SpecBench (Weco AI), 30 systems-level tasks | SUPPORTED | "30 systems-level programming tasks" |
| 65 | 65 | Quotes: saturate visible tests; gap grows with complexity; "27 percentage points for every tenfold increase in lines of code" | SUPPORTED | Verbatim. It is the 90th-percentile bound; the body gives R²=0.21 for the fit. |
| 66 | 66 | "have one Claude write tests, then another write code to pass them." | SUPPORTED | Verbatim |
| 67 | 73 | "The measured mitigations for test tampering are environmental" | OVERSTATED | The same paper measures prompt wording as a mitigation, and as the largest one on one benchmark: "we show that prompt, test access and feedback loop all have significant effects on models' cheating propensity" and the 92%→1% figure the file itself quotes at line 61. Environmental controls are measured mitigations; they are not the only ones. |
| 68 | 74 | Escape hatch "reduced cheating in two of three models tested" | SUPPORTED-WITH-CAVEAT | Three models confirmed in Figure 8. All three dropped on the conflicting split (Opus 50→46); two dropped substantially, both OpenAI. On the one-off split the best result is still 37% cheating (GPT-5). |
| 69 | 75 | Visible tests passing is weak evidence on large diffs | SUPPORTED | #65 |

### B3. Mutation testing

| # | L | Claim | Verdict | Source wording / evidence |
|---|---|---|---|---|
| 70 | 81 | 2501.12862 = Meta ACH, "Mutation-Guided LLM-based Test Generation at Meta" | SUPPORTED | abs page matches |
| 71 | 81 | "ACH generates relatively few mutants…" | SUPPORTED | Verbatim |
| 72 | 81 | Scale quote: 10,795 classes, 7 platforms, 9,095 mutants, 571 tests, precision 0.79 / recall 0.47 rising to 0.95 / 0.96, 73% accepted, 36% privacy relevant | SUPPORTED | All numbers verbatim. In-quote typography differs: source has "pre-processing" and "test-a-thons", and the sentence begins "In total, ACH was applied…". |
| 73 | 81 | "25% of the mutants generated are trivially syntactically equivalent." and the "waste time" quote | SUPPORTED | Verbatim. It is 25% of the 9,095 mutants that build and pass (2,246). |
| 74 | 82 | 2506.02954 MUTGEN: "some test suites achieve 100% coverage but only 4% mutation score" | SUPPORTED | Verbatim; the body example is a single subject (id 81) |
| 75 | 82 | "tend to converge after the fourth iteration"; Llama-3.3, Java | SUPPORTED | Verbatim; Llama-3.3 70B on HumanEval-Java and LeetCode-Java |
| 76 | 83 | 2602.08146 AdverTest: 8.56% and 50.20% | SUPPORTED | Verbatim in abstract |
| 77 | 84 | superpowers `writing-good-tests.md` has a 13-line "The Mutation Check" section; quote; five mutation classes | SUPPORTED | Section spans lines 157-169 (13 lines); quote verbatim; five bullets |
| 78 | 90 | A small number of targeted mutants is how the one industrial deployment works | SUPPORTED | #71 |
| 79 | 92 | "Equivalent mutants are a real time sink (a quarter trivially equivalent at Meta)" | SUPPORTED-WITH-CAVEAT | The number is right (#73). The source's own assessment is the opposite of "real time sink" for its deployment: "Fortunately, as revealed in Section 5, the equivalent mutant problem is relatively unimportant for our use case." The trivially equivalent quarter is removed by simple pre-processing. |

### B4. Self-review vs independent review

| # | L | Claim | Verdict | Source wording / evidence |
|---|---|---|---|---|
| 80 | 99 | 2604.06996 = Pombal, Rei, Martins, self-preference bias in rubric-based evaluation | SUPPORTED | abs page matches |
| 81 | 99 | Tag **[indep]** | SUPPORTED-WITH-CAVEAT | Affiliations include Sword Health and TransPerfect alongside academic institutes. See defect 13. |
| 82 | 99 | ">50% more likely" quote | SUPPORTED | Verbatim in abstract |
| 83 | 99 | "In the worst case (GPT-5), the judge can be 20 times more likely…" is about code | SUPPORTED | Verbatim; preceded by "The LiveCodeBench part of Table 1 shows…" |
| 84 | 99 | "most severely on LiveCodeBench (GPT-5: 11.91)" | SUPPORTED | Verbatim |
| 85 | 99 | "ensembling multiple judges helps mitigate SPB, but without fully eliminating it." | SUPPORTED | Verbatim |
| 86 | 99 | Caveat: judging rubric satisfaction, not PR review; no session-vs-fresh split | SUPPORTED | Matches the paper's design |
| 87 | 100 | 2509.01494 = SWR-Bench; 1000 manually verified PRs, 500 with issues / 500 clean | SUPPORTED | "1000 manually verified pull requests"; Table 3: Change-PR 500, Clean-PR 500 |
| 88 | 100 | Low-precision quote, ">7 false positives", "precision scores below 10%" | SUPPORTED | Verbatim |
| 89 | 100 | "Best single-pass F1 is 19.38 percent" | SUPPORTED-WITH-CAVEAT | Matches the prose: "top-performing combination, PR-Review leveraged with Gemini-2.5-Pro, achieved an F1 score of only 19.38%". The paper's own Table 8 lists GPT-5 with PR-Review at F1 20.85 (P 14.69, R 35.93). |
| 90 | 100 | Five-run aggregation lifts the best model to 23.84 percent | SUPPORTED | "Gemini-2.5-Pro Self-Agg (n=5) achieves the highest F1 of 23.84%" |
| 91 | 100 | Recall from 38.35 percent (one change-action) to 8.88 percent (five or more) | SUPPORTED | Table 5: 38.35 / 24.46 / 16.07 / 11.76 / 8.88. One tool and model only ("using PR-Review with Gemini-2.5-Pro as a representative example"); the 5+ bucket is 22 PRs. |
| 92 | 100 | "Conclusion 4: ACR tools struggle to comprehensively review complex PRs." | SUPPORTED | Verbatim |
| 93 | 100 | Caveat: 2025 models, human-authored PRs, LLM-judged | SUPPORTED-WITH-CAVEAT | LLM-judged: yes ("~90% agreement" with humans). "Human-authored" is not stated in the paper; it is an inference from the PRs being mined from open-source GitHub projects. |
| 94 | 101 | 2603.23448 = c-CRAB; tools quote | SUPPORTED | Verbatim |
| 95 | 101 | "20.1% to 32.1% … 100%"; "97 out of the 234 tests … (41.5%)" | SUPPORTED | Verbatim. Table 5: Claude Code 32.1, Devin 24.8, PR-Agent 23.1, Codex 20.1. |
| 96 | 101 | The 100 percent for humans is by construction | SUPPORTED | Tests are derived from the human comments. "By construction" is the file's phrase, not the paper's; the paper says "This gap should be interpreted carefully." |
| 97 | 102 | 2608.27442 MCR-Bench abstract quote | SUPPORTED | Verbatim |
| 98 | 103 | 2603.25773 Zietsman: three quotes | SUPPORTED | All verbatim |
| 99 | 104 | Anthropic best-practices: three quotes on fresh-context review and reviewer false positives | SUPPORTED | All verbatim |
| 100 | 105 | superpowers `executing-plans`: two quotes | SUPPORTED | Both verbatim |
| 101 | 111 | Same-session self-review is "the weakest reviewer configuration in everything read" | SUPPORTED-WITH-CAVEAT | No cited source measures same-session self-review; the file's own Gap (L107) says so. It is a ranking by inference plus vendor guidance, not by measurement. |
| 102 | 112 | Independent reviewer catches "about a fifth to a third of what humans flag" | SUPPORTED | c-CRAB 20.1%-32.1% |
| 103 | 112 | "recall under 10 percent on multi-change PRs" | OVERSTATED | 8.88% applies only to PRs with five or more change-actions (22 PRs, one tool with one model). For two, three and four change-actions the same table gives 24.46%, 16.07% and 11.76%. "Multi-change" reads as "more than one". |
| 104 | 112 | "mostly false positives" | SUPPORTED | "low precision, indicative of a high false positive rate"; best-case precision well under 50% |
| 105 | 114 | "a different model family reduces shared bias more than a fresh context of the same model does" | OVERSTATED | No cited source compares the two. Pombal compares own vs family vs unrelated judges and, per the file's own caveat at L99, "does not separate same-session from fresh-context". The file's Gap (L107, L288) says no such comparison was found. Zietsman's cross-family experiment also cuts against it: the domain-opaque bug was missed by all four models from three families. |

### B5. Risk-tiered auto-merge

| # | L | Claim | Verdict | Source wording / evidence |
|---|---|---|---|---|
| 106 | 120 | 2605.30208 = Meta RADAR, "Automating Low-Risk Code Review at Meta"; funnel quote | SUPPORTED | Verbatim |
| 107 | 120 | "RADAR has reviewed 535K+ diffs and landed 331K+." | SUPPORTED | Verbatim |
| 108 | 120 | Revert rate about one third, production-incident rate about one fiftieth | SUPPORTED | "The revert rate for RADAR-reviewed diffs is 1/3 that of non-RADAR diffs, and the production incident (PI) rate is 1/50" |
| 109 | 120 | "While this is not a causal estimate" / "Because diffs are not randomly assigned…" | SUPPORTED | Both verbatim |
| 110 | 121 | DRS quote ("flagging 10% of diffs while catching 60% of PI-causing changes") | SUPPORTED | Verbatim |
| 111 | 122 | "For human-authored diffs, the default DRS threshold is P5…"; agent runbooks P20, P50 once allowlisted | SUPPORTED | Quote verbatim; "allowlisted RACER runbooks use a P50 threshold, while non-allowlisted sources use a stricter P20 threshold" |
| 112 | 123 | 60-day lookback quote | SUPPORTED | Verbatim |
| 113 | 124 | Hard-exclusion quotes (keyword "test"; blocklisted phrases and paths) | SUPPORTED | Both verbatim |
| 114 | 125 | Blanket AutoAccept for deterministic codemods | SUPPORTED | Verbatim |
| 115 | 126 | Deferred post-land human review | SUPPORTED | Verbatim |
| 116 | 127 | Organisational-context quote | SUPPORTED | Verbatim |
| 117 | 128 | 2605.22534: 9,799 human-reviewed agentic PRs, 717 inspected; 35.7 / 31.2 / 33.1 / 15.4 | SUPPORTED | "11,048 closed agentic pull requests, refined to 9,799 human-reviewed PRs, and manually inspected 717"; percentages verbatim |
| 118 | 129 | 2601.20109: 1,210 merged agent bug-fix PRs, SonarQube; two quotes | SUPPORTED | "1,210 merged agent-generated bug-fix PRs from Python repositories"; both quotes verbatim |
| 119 | 130 | Auto-mode classifier quote, attributed to best practices | SUPPORTED | Verbatim in `best-practices` |
| 120 | 136 | RADAR puts the risk decision outside the author | SUPPORTED | #106, #110 |
| 121 | 138 | "Meta starts at the safest 5 percent and widens on evidence." | OVERSTATED | P5 is the default for *human-authored* diffs (#111). For agent and bot diffs, which is the case the skill is about, the starting threshold is P20 ("non-allowlisted sources use a stricter P20 threshold"), P50 when allowlisted. "Widens on evidence" is supported (60-day track record; an org-wide move from P25 to P50). |
| 122 | 139 | "Test-infrastructure changes are excluded from auto-landing at Meta." | SUPPORTED-WITH-CAVEAT | The rule is narrower: a denylist on agent *runbook names* — "runbooks whose names contain certain keywords (e.g., "test") are excluded". It is not a rule on the paths or content of every diff. |

### B6. Long instruction files, adherence, compaction

| # | L | Claim | Verdict | Source wording / evidence |
|---|---|---|---|---|
| 123 | 145 | Skills doc size quotes ("Keep `SKILL.md` under 500 lines…"; "every line is a recurring token cost…") | SUPPORTED | Both verbatim |
| 124 | 145 | Compaction: first 5,000 tokens of each skill re-attached; shared 25,000-token budget; older skills can be dropped | SUPPORTED | Exact wording in `skills`: "[Auto-compaction] carries invoked skills forward within a token budget. When the conversation is summarized to free context, Claude Code re-attaches the most recent invocation of each skill after the summary, keeping the first 5,000 tokens of each. Re-attached skills share a combined budget of 25,000 tokens. Claude Code fills this budget starting from the most recently invoked skill, so older skills can be dropped entirely after compaction if you have invoked many in one session." The limit is per skill (5,000); the 25,000 is shared across skills. |
| 125 | 145 | Remedy quote (hooks; re-invoke after compaction) | SUPPORTED | Verbatim; link syntax simplified |
| 126 | 146 | Skill-authoring best practices: ten quoted fragments | SUPPORTED | All verbatim |
| 127 | 147 | Best-practices: three quotes (context fills up; "the file is probably too long"; "If you emphasize many lines…") | SUPPORTED-WITH-CAVEAT | All verbatim. The second and third are guidance about `CLAUDE.md`, not about skills. |
| 128 | 148 | 2608.11242 = "Lost in Compaction"; "retain only 17% of injected SCs on average…" | SUPPORTED | Verbatim in abstract |
| 129 | 148 | "Process SCs are consistently retained the least across all compactors." | SUPPORTED | Verbatim |
| 130 | 148 | "even the best result (Preference under gpt-oss (pi-mono), at 36%) loses nearly two-thirds of constraints." | SUPPORTED | Verbatim. It is the best per-constraint-type average among the open compactors, not the best single result in the paper (see #132). |
| 131 | 148 | Extractor "over 90% retention across all three scenarios"; "architectural separation rather than better compactor prompts" | SUPPORTED | Both verbatim |
| 132 | 148 | Caveat: "mostly open-weight compactors" | SUPPORTED-WITH-CAVEAT | Understates what the proprietary one did: "Commercial LLM-based compactors attain the highest retention rates but nevertheless fail in many cases. GPT-5.4-mini reaches a retention rate as high as 98%, yet drops to as low as 6.7%". The 17% average is driven by small and open compactors. |
| 133 | 149 | 2507.11538 IFScale (Distyl AI): 68% at 500 instructions; "near-perfect performance through 150 or more"; omission-error quote; keyword-inclusion, 2025 | SUPPORTED | All verbatim; the 150+ sentence is about "(gemini-2.5-pro, o3)" |
| 134 | 150 | 2602.11988 Gloaguen et al.: three quotes | SUPPORTED | All verbatim. Tag [indep]: authors are ETH Zurich and LogicStar.ai (defect 13). |
| 135 | 151 | 2601.20404 Lulla et al.: 10 repositories, 124 PRs; "(28.64%)" and "(16.58%)" | SUPPORTED | "We analyze 10 repositories and 124 pull requests". Inside the quotation the source has "(Δ 28.64%)" and "(Δ 16.58%)"; the Δ was dropped. |
| 136 | 158 | ~7,700 tokens at four bytes per token; the 5,000-token cut falls "near line 284, inside §4-TDD" | SUPPORTED-WITH-CAVEAT | Arithmetic holds (30,955/4 ≈ 7,740; byte 20,000 falls on line 281; §4-TDD spans lines 273-302). It is a byte heuristic, as the file says. |
| 137 | 158 | "Everything after that is gone from context after the first auto-compaction" | SUPPORTED-WITH-CAVEAT | The doc says what is re-attached ("keeping the first 5,000 tokens of each"), not that nothing else survives: the compaction summary may carry some of it, and the doc's remedy is to "re-invoke it after compaction to restore the full content". Conversely the skill can be dropped entirely if later skills exhaust the shared budget. |
| 138 | 159 | 454 lines is under the 500-line guidance | SUPPORTED | #1, #123 |
| 139 | 160 | "The vendor's own test for keeping a line is whether removing it changes behaviour." | SUPPORTED-WITH-CAVEAT | Source: "For each line, ask: "Would removing this cause Claude to make mistakes?" If not, cut it." That test is stated for `CLAUDE.md`, and it is about causing mistakes, not any behaviour change. |
| 140 | 161 | "The prior-art repos converged on the same device" (a durable checklist / ledger) | SUPPORTED-WITH-CAVEAT | Only superpowers has a ledger justified by compaction ("The ledger is what survives compaction."). spec-kit ticks `tasks.md`; mattpocock `implement` has no such device. |

### B7. Deterministic gates

| # | L | Claim | Verdict | Source wording / evidence |
|---|---|---|---|---|
| 141 | 167 | Hooks-guide opening quote | SUPPORTED | Verbatim |
| 142 | 167 | Event table: `PreToolUse`, `Stop`, `TaskCompleted` with quoted descriptions; `PreCompact`, `PostCompact` exist | SUPPORTED | Table rows verbatim: "Before a tool call executes. Can block it"; "When Claude finishes responding"; "When a task is being marked as completed"; "Before context compaction"; "After context compaction completes" |
| 143 | 167 | `SessionStart` + `compact` matcher quote | SUPPORTED | Verbatim |
| 144 | 168 | "Use hooks for actions that must happen every time with zero exceptions." | SUPPORTED | Verbatim in `best-practices` |
| 145 | 168 | Three further quotes (advisory vs deterministic; Stop hook as gate; "delete it or convert it to a hook") | SUPPORTED | All verbatim. The first and third are in the `CLAUDE.md` section. |
| 146 | 169 | Skill `hooks` field: "…keeps running for the rest of the session." | SUPPORTED | Verbatim in the frontmatter table |
| 147 | 170 | Cross-references to ImpossibleBench, Lost in Compaction, RADAR | SUPPORTED | #60, #131, #106, #113 |
| 148 | 171 | spec-kit commit titles and dates: #2901 (2026-06-25), #2713 (2026-05-26) | SUPPORTED | `gh api` history of `templates/commands/implement.md` shows both titles verbatim with those dates |
| 149 | 171 | Current text says "Emitting the block alone does not run the hook." | SUPPORTED | Verbatim (twice) in the current file |
| 150 | 171 | Recent history "is a series of fixes for the model not running them" | SUPPORTED | #2713, #2901 and #4456 ("report an unreadable extensions.yml instead of skipping hooks silently") are on this; the other 2026 commits are unrelated |
| 151 | 179 | Skill-scoped hooks last for the rest of the session, not the skill's duration | SUPPORTED | #146 |

### B8. Prior art and Claude Code features

| # | L | Claim | Verdict | Source wording / evidence |
|---|---|---|---|---|
| 152 | 187 | mattpocock `implement/SKILL.md`: 15 lines; `disable-model-invocation: true`; five sentences; four quoted; no branch/PR/merge/risk logic | SUPPORTED | `wc -l` 15; body is five sentences; all four quotes verbatim |
| 153 | 187 | Last touched 2026-07-08 ("refactor: unify planning skills into /to-spec + /to-tickets"); three commits | SUPPORTED | Three commits. Committer date 2026-07-08; author date is 2026-07-02. |
| 154 | 188 | `implement-spec/SKILL.md`: 40 lines; task graph; worktree per implementer; merger subagent; one `code-review` on the integration branch; quotes | SUPPORTED | `wc -l` 40; quotes verbatim; steps 5 and 7 |
| 155 | 188 | "Graduate implement-spec to engineering" 2026-09-24 | SUPPORTED | Confirmed; two further fix commits on the same day |
| 156 | 189 | `tdd/SKILL.md` 38 lines, `tests.md` 77, `mocking.md` 59; three anti-patterns; three loop rules; two quotes; no mutation step | SUPPORTED | Line counts match; structure and quotes verbatim; 0 hits for "mutat" |
| 157 | 189 | 2026-09-17 glossary-convention rename; wording edits in August | SUPPORTED | Committer date 2026-09-17 (author date 2026-08-15); four August commits |
| 158 | 190 | `code-review/SKILL.md` 87 lines; two axes as "**parallel sub-agents**…"; findings not merged across axes | SUPPORTED | Line 11 verbatim; line 76 "Do **not** merge or rerank findings" |
| 159 | 190 | August wording edits | SUPPORTED | Seven August commits |
| 160 | 191 | superpowers `executing-plans/SKILL.md` 373 lines; `task-start` 28; `task-done` 52; quotes; `Ruling:` ledger; "Common Rationalizations" table; four named stops incl. the merge/push/publish quote | SUPPORTED | All counts match; "Four things stop you, and only these: … a side effect outside this worktree that norms say you ask about first (a merge, a push to a shared branch, a publish); …" |
| 161 | 191 | Rewritten in "Release v6.4.1 … Native plan execution …" 2026-09-19 | SUPPORTED | Commit title and date match; that commit changes the file by +350 / −41 |
| 162 | 192 | `test-driven-development/SKILL.md` 330 lines; `writing-good-tests.md` 198; quotes; rationalization table; verification checklist | SUPPORTED | Counts match; quotes verbatim; sections "Common Rationalizations", "Verification Checklist" |
| 163 | 192 | 2026-07-24 refactors folding rebuttals into the table; v6.4.1 | SUPPORTED | Committer date 2026-07-24 (author date 2026-07-05) |
| 164 | 193 | `subagent-driven-development/SKILL.md` 568 lines; 3 prompt templates, 3 scripts; model-tiering quotes; `scripts/review-package`; ledger quote | SUPPORTED | Counts match; all quotes verbatim |
| 165 | 193 | 2026-07-24 "lifecycle restructure with resume-based fix loop, five-round breaker"; v6.3.0; v6.4.1 | SUPPORTED | Title verbatim; committer date 2026-07-24 (author 2026-07-15); v6.3.0 2026-08-12; v6.4.1 2026-09-19 |
| 166 | 194 | spec-kit `implement.md` 222 lines; scripts frontmatter (sh, ps, py); checklist-gate quote; about 40 lines of ignore rules; "Done When"; no branch/PR/merge logic | SUPPORTED | 222 lines; frontmatter lines 3-6; ignore block is lines 99-143; `## Done When` at line 217; 0 hits for branch / PR / merge |
| 167 | 194 | 2026-09-09 "report an unreadable extensions.yml instead of skipping hooks silently" | SUPPORTED | Commit #4456, 2026-09-09 |
| 168 | 195 | Lean preset: 22 lines; loads four files; "Halt on failure and report the issue"; added 2026-04-10, unchanged | SUPPORTED | 22 lines; one commit, 2026-04-10 |
| 169 | 196 | Anthropic `fix-issue` example: `disable-model-invocation: true`, eight numbered steps, first and last step quoted, "about a dozen" lines | SUPPORTED | Eight steps; quotes verbatim; the block is 15 lines with frontmatter |
| 170 | 200 | None of the three puts the whole pipeline in one file | SUPPORTED | Consistent with the files read (#152-168) |
| 171 | 201 | "None of them merges." | SUPPORTED-WITH-CAVEAT | None merges to the default branch. mattpocock `implement-spec` does merge: "merge its work to the integration branch with a **merger subagent**", and it can open a draft PR and mark it ready. |
| 172 | 201 | superpowers names a merge as one of four things that stop the run | SUPPORTED | #160; the merge is an example inside the third stop |
| 173 | 202 | mattpocock shrank `implement` to 15 lines; superpowers 373 and 568, the latter over the 500-line guidance | SUPPORTED | #152, #160, #164, #123 |
| 174 | 209 | Plan-mode quote, permission-modes doc | SUPPORTED | Verbatim |
| 175 | 210 | `context: fork` quote, skills doc | SUPPORTED | Verbatim |
| 176 | 211 | `background` quote incl. "Requires Claude Code v2.1.218 or later.", skills doc | SUPPORTED | Verbatim |
| 177 | 212 | `model` / `effort` quotes, skills doc; subagents take the same two fields | SUPPORTED | Verbatim; `sub-agents` frontmatter table has `model` and `effort` rows |
| 178 | 213 | `disallowed-tools` quote | SUPPORTED | Verbatim |
| 179 | 214 | `disable-model-invocation` quote | SUPPORTED | Verbatim |
| 180 | 216 | `${CLAUDE_SKILL_DIR}` quote | SUPPORTED | Verbatim |
| 181 | 217 | `--worktree` quote (worktrees doc); subagent `isolation` quote (sub-agents doc) | SUPPORTED | Both verbatim |
| 182 | 218 | Bundled `/code-review` quote (best practices) | SUPPORTED | Verbatim |
| 183 | 219 | Bundled `/verify` quote (skills doc) | SUPPORTED | Verbatim |
| 184 | 220 | `/batch` quote "split the change across 5 to 30 subagents. Each subagent works in its own worktree." attributed to "(skills doc)" | WRONG SOURCE | The wording is in `best-practices` ("Run [`/batch <instruction>`] to have Claude split the change across 5 to 30 subagents. Each subagent works in its own worktree."). The skills doc only names `/batch` in a list of bundled skills. The quote is genuine; the citation points at the wrong page. |
| 185 | 221 | `/goal` / Stop-hook quote (best practices) | SUPPORTED | Verbatim |
| 186 | 226 | "The shape that prior art and vendor guidance agree on: a short orchestrating skill, reference skills…, scripts for bookkeeping, a durable ledger…, and the merge decision left to gates outside the authoring session." | SUPPORTED-WITH-CAVEAT | A composite. No single source has this shape: the short orchestrator and reference skills are mattpocock; the scripts and ledger are superpowers, whose skills are 373 and 568 lines. The file's own L202 says "The two trajectories differ". |

Also checked, no separate row: the three "seen but not used" IDs at L279 resolve to papers matching their descriptions (2606.28438 "When AI Reviews Its Own Code: Recursive Self-Training Collapse in Code LLMs"; 2604.22891 "Quantifying and Mitigating Self-Preference Bias of LLM Judges"; 2606.07379 "Do Coding Agents Deceive Us? Detecting and Preventing Cheating via Capped Evaluation with Randomized Tests"). Gap 8 (L292) "ImpossibleBench reports cheating rising with capability" carries the caveat of #57 (a figure caption, SWE-bench variant only). Gap 9 (L293) is supported by #36 and #93.

## Defects, ordered by how much each would mislead a design decision

1. **#105, L114 — reviewer model family vs fresh context. OVERSTATED.** The file states as a finding that a different model family reduces shared bias more than a fresh context of the same model. No cited source compares those two conditions, the file's own Gap says none was found, and the one cross-family experiment it cites (Zietsman) had every family miss the opaque bug. A design that spends on a second model family instead of a fresh-context reviewer on the strength of this line has no evidence under it.

2. **#103, L112 — "recall under 10 percent on multi-change PRs". OVERSTATED.** The 8.88% is the five-or-more bucket (22 PRs, one tool, one model). Two to four change-actions sit at 24%, 16% and 12%. The conclusion "an independent reviewer is a weak gate" survives on the other numbers (20-32% of human findings, low precision), but the specific figure would make a reviewer look roughly twice as useless on ordinary PRs as the source says.

3. **#121, L138 — "Meta starts at the safest 5 percent". OVERSTATED.** P5 is the human-diff default. Agent-generated diffs, the case being designed for, start at P20 and move to P50 once allowlisted. The direction of the argument (start conservative, widen on a track record) holds; the anchor number is four times too strict for the relevant case.

4. **#67, L73 — "measured mitigations for test tampering are environmental". OVERSTATED.** ImpossibleBench measures prompt wording as a mitigation alongside test access and feedback loops, with the largest single effect on one benchmark (92%→1%), and the file quotes that number itself. A redesign that deletes the prompt-level instruction because "only environmental controls are measured" would be acting against the source.

5. **#62 and #68, L63 and L74 — escape hatch 54%→9%. SUPPORTED-WITH-CAVEAT.** The ellipsis removes "On Impossible-SWEbench and especially Conflicting-SWEbench … quite effective for OpenAI models". The result is one benchmark split and one vendor's models; on the one-off split GPT-5 still cheats in 37% of tasks, and Claude Opus 4.1 barely moves (50→46, 54→51). For a skill that runs on Claude this is close to a null result, not a 6x reduction.

6. **#132, L148 — Lost in Compaction. SUPPORTED-WITH-CAVEAT.** The 17% average and the "best result 36%" describe small and open compactors. The one commercial compactor tested retained up to 98% on one dataset and as little as 6.7% on another. The finding that compaction is unreliable stands; "compaction loses five sixths of constraints" does not transfer to a frontier compactor.

7. **#23 and #44, L36 and L51 — no-plan wins. SUPPORTED-WITH-CAVEAT.** The paper says the extra no-plan solves are "largely affected by the inherent nondeterminism of LLM-based agents". The argument for a non-TDD route rests on these counts plus one qualitative trace.

8. **#40 and #41, L48-49 — plan-gate implications. SUPPORTED-WITH-CAVEAT.** No source measures a trigger-based plan gate; Liu's headline for an always-on plan is positive; "planning buys cost, not correctness, on strong models" is one study of a todo-list tool on locally served models.

9. **#79, L92 — equivalent mutants as "a real time sink". SUPPORTED-WITH-CAVEAT.** The 25% is right; Meta's own judgement is that the problem is "relatively unimportant for our use case". The design point (allow an "equivalent, skipped" outcome) does not need the stronger framing.

10. **#53, L59 — "ceiling: a quarter of faults". SUPPORTED-WITH-CAVEAT.** The faults were pre-selected for difficulty.

11. **#122, L139 — test-infrastructure exclusion. SUPPORTED-WITH-CAVEAT.** It is a keyword denylist on runbook names, not a rule on diff paths.

12. **#89, L100 — "best single-pass F1 is 19.38". SUPPORTED-WITH-CAVEAT.** The paper's Table 8 has a 20.85. No design consequence.

13. **Independence tags (#32, #55, #81, #134). SUPPORTED-WITH-CAVEAT.** The file defines [vendor] as including "company-authored papers", then tags as [indep] four papers with company-affiliated authors: ImpossibleBench (Anthropic co-author), Pombal et al. (Sword Health, TransPerfect), Gloaguen et al. (LogicStar.ai), Fan et al. (internships at Zoom). ImpossibleBench matters most: it is the main source for B2 and evaluates Anthropic's models.

14. **#8, L21 — "All five terms occur in the paper". OVERSTATED.** "Property invariant" does not occur. The Part A verdict is therefore slightly too kind to the skill; the conclusion (PARTLY) stands or tightens.

15. **`CLAUDE.md` guidance applied to skills (#127, #139, #145). SUPPORTED-WITH-CAVEAT.** Three vendor quotes and the "test for keeping a line" come from the `CLAUDE.md` section of the best-practices page. The transfer to skills is reasonable but is the file's, not the vendor's.

16. **#137, L158 — "everything after that is gone". SUPPORTED-WITH-CAVEAT.** The doc specifies what is re-attached, not that the summary carries nothing; it can also be worse (skill dropped entirely).

17. **#171 and #186, L201 and L226 — prior-art generalisations. SUPPORTED-WITH-CAVEAT.** mattpocock's orchestrator does merge to an integration branch; the "agreed shape" is assembled from two repos that the file itself says took different trajectories.

18. **#184, L220 — `/batch` quote. WRONG SOURCE.** Genuine quote, cited to the skills doc, actually in best practices. No design consequence.

19. **In-quotation deviations, no change of meaning:** L81 ("preprocessing", "test-athons", sentence start trimmed), L151 (Δ dropped from both percentages), L37 (section-sign spacing), L62 (footnote marker), L145 and L211 (link syntax). Separately, L39 and L63 use "..." across wording that qualifies the claim (#30, #62), and L36 stops one sentence before the source's qualifier (#23); those are counted as caveats above, not as typography.

## Tally

186 numbered claims, all audited. **SUPPORTED: 151. SUPPORTED-WITH-CAVEAT: 29. OVERSTATED: 5** (#8, #67, #103, #105, #121). **WRONG SOURCE: 1** (#184). **QUOTE NOT FOUND: 0. NUMBER MISREAD: 0. UNVERIFIABLE: 0.** All 28 arXiv IDs resolve to the papers described, every quoted number is present in its source, and every quotation was found verbatim apart from the typography deviations listed. Where a number goes wrong it is in the condition attached to it, not the digits. The line counts, commit titles and commit dates for all three repositories are correct (dates are committer dates where author and committer dates differ). The defects are concentrated in the "Implies for the skill" blocks, where four of the five overstated claims sit and where qualifiers dropped at the quotation stage (benchmark split, model vendor, human vs agent diffs, bucket size) turn into general statements. Outside the 186, three groups of statements were not audited because they are absence claims or read-depth self-reports, as listed under coverage. Fowler's book was not read (the file under audit discloses the same limit); the smell counts were checked against the dev.to page the file cites.
