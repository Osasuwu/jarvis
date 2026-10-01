# /implement redesign — external evidence

Date: 2026-09-30. Subject: `skills/implement/SKILL.md` (454 lines, 4,650 words, 30,955 bytes).

Conventions used throughout:

- Text in quotation marks was copied from the fetched page or from `pdftotext` output of the fetched PDF. Numbers that the PDF extraction mangled (en-dashes, fractions, "F1") are stated outside the quotation marks.
- **[full]** = full text read. **[abs]** = abstract or summary only.
- **[indep]** = independent/academic measurement. **[vendor]** = vendor or company self-report (includes company-authored papers). **[position]** = argument with little or no measurement.
- "Implies for the skill" blocks are my inference, not evidence. They are kept separate on purpose.
- Model names in the papers (GPT-5 mini, Nemotron-3, Mistral-Medium-3.5, Gemini-2.5, Claude Opus 4.1 ...) are as the papers give them. Almost none of the measurements were taken on the model that runs this skill; treat every effect size as directional.

---

## Part A — audit of the skill's external citations

The skill makes three external references. Everything else it cites is internal (ADR-0001, `docs/security/agent-boundaries.md`, issue/PR numbers).

| # | Where | Claim as the skill states it | What the source says | Verdict | Read |
|---|---|---|---|---|---|
| A1 | line 89 | "The vocabulary for "objective machine-checkable oracle" (SLR arxiv:1804.01954) is exactly one of:" pseudo-oracle, analytical solution, metamorphic relation, property invariant, golden run | Kanewala & Bieman, "Testing Scientific Software: A Systematic Literature Review", https://arxiv.org/abs/1804.01954. The ID matches an SLR on oracles. Its list of techniques has nine entries, not five: "1. A pseudo oracle is an independently developed program that fulfills the same specification as the program under test"; "2. Solutions obtained analytically can serve as oracles."; "3. Experimentally obtained results can be used as oracles"; "4. Measurements values obtained from natural events can be used as oracles."; "5. Using the professional judgment of scientists"; "7. Statistical oracle: verifies statistical characteristics of test results"; "8. Reference data sets"; "9. Metamorphic testing (MT) was introduced by Chen et al. [10] as a way to test programs that do not have oracles." Two of the skill's five are only future-work suggestions: "Techniques such as property based testing and data redundancy can be used when an oracle is not available [4]. ... Another potential approach is to use a golden run [46]." and "We did not find applications of property based testing, data redundancy, golden run, and model based testing to test scientific software in the primary studies." The paper also says of the techniques it did find: "But we found no empirical studies evaluating the effectiveness of these techniques in detecting subtle faults." The phrase "objective machine-checkable oracle" and anything about unattended runs do not appear. | **PARTLY.** All five terms occur in the paper. "Exactly one of" five is the skill's own selection from nine; two of the five have no applications in the reviewed studies; the domain is scientific-software testing, not agent autonomy. | [full] |
| A2 | line 101 | "Losing the experimental intent behind a run is the primary driver of irreproducibility (arxiv:2506.16051); an unrecorded negative result is a lost experiment, not a saved one." | Li et al., "From Data to Decision: Data-Centric Infrastructure for Reproducible ML in Collaborative eScience", https://arxiv.org/abs/2506.16051. A framework paper with one glaucoma case study. The word "intent" occurs zero times in the full text; negative results are not discussed; no "primary driver" ranking is made. Closest passages: "Crucial details about how models were built, how data was prepared, and how decisions were made throughout the ML lifecycle are frequently missing. As a result, the knowledge embedded in the development process is lost, leaving others unable to follow or build upon the original path." and "Missing context from one experiment can disrupt downstream development and obscure the rationale behind decisions. The cumulative effect creates a reproducibility bottleneck that grows with each iteration." | **PARTLY — claim is stronger than the source.** The general direction (missing context harms reproducibility) is there. "Primary driver" and the negative-results sentence are **NOT FOUND IN SOURCE**. | [full] |
| A3 | line 426 | "**Standards** — Fowler's 12 code smells:" followed by twelve names | Two checks. (a) A secondary catalogue page, https://dev.to/trikitrok/on-code-smells-catalogues-and-taxonomies-3ba6, read only through a summarising fetch: it reports 22 smells in the first edition of *Refactoring* and 24 in the second, with Mysterious Name new in the second edition and Switch Statements renamed Repeated Switches. I could not read Fowler's book itself. (b) The same twelve names, in the same order, are the "smell baseline" of `mattpocock/skills` `skills/engineering/code-review/SKILL.md` (https://github.com/mattpocock/skills/blob/main/skills/engineering/code-review/SKILL.md), which describes it as "a fixed set of Fowler code smells (_Refactoring_, ch.3)" and adds "Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation." | **PARTLY.** The twelve names are Fowler smells; "Fowler's 12" is not a Fowler concept — it is a twelve-item subset that appears to have been lifted from the mattpocock skill, without that skill's "always a judgement call" qualifier. | (a) [abs], (b) [full] |

Also noted: line 97 asserts "External practice draws the same line: a pipeline with an objective oracle runs unattended..." with no citation at all. Nothing I read supports or refutes it as stated.

---

## Part B — evidence on the practices the skill encodes

### B1. Plan before code

**Findings**

1. Liu et al., "From Plan to Action: How Well Do Agents Follow the Plan?" https://arxiv.org/abs/2604.12147 [full][indep]. "examining 21,120 trajectories from SWE-agent across four LLMs on SWE-bench Verified and SWE-bench Pro under eight plan variations. ... Providing the standard plan improves issue resolution, and we observe that periodic plan reminders can mitigate plan violations and improve task success. A subpar plan hurts performance even more than no plan at all. Surprisingly, inserting additional task-relevant phases in the early stage can degrade performance, particularly when these phases do not align with the model's internal problem-solving strategy."
   - Against a universal plan: "Agents can fix previously unresolved issues under no-plan setting. DeepSeek-V3, DeepSeek-R1, Devstral-small, and GPT-5 mini each resolve additional instances that are not solved under the default plan: 23, 11, 28, and 34, respectively." One cause: "the models generated incorrect reproduction tests, leading to repeated patch-test failure cycles without success. Under the No Plan setting, the same model skipped the reproduction phase and generated the correct patch."
   - Drift: "To mitigate the context window pressure (§4.1.1), where the initial plan becomes less influential as the trajectory length increases, we introduce a Reminded plan setting. In this variant, the Standard plan is periodically re-inserted into the context every five steps. ... This leads to consistent improvements in success rates across models".
   - Caveat: the "plan" is a workflow plan in the system prompt (what a skill is), not a task-specific plan reviewed by someone else.
2. Fan et al., "An Empirical Study of Harness Design for Coding Agents" https://arxiv.org/abs/2609.20804 [full][indep]. 176 matched settings, four models, SWE-Bench Verified and Terminal-Bench 2.1. "Planning shifts from an accuracy scaffold for weaker models to a cost saver for stronger models, with little change in accuracy." Numbers: "For Nemotron-3 30B, planning increases success rate by 11.6 percentage points on SWE-Bench and 4.5 points on Terminal-Bench, at higher cost on both benchmarks. ... For Nemotron-3 550B and Mistral-Medium-3.5-128B, planning reduces cost on both benchmarks, accompanied by small decreases in success rate. On SWE-Bench, their costs fall by approximately 30% and 32%, respectively, while success rates decrease by 2.0 and 0.4 percentage points". Caveat: "planning" here is a model-maintained todo list re-shown each turn, not an external plan gate; open-weight models.
3. SWE-RPG, https://arxiv.org/abs/2608.09072 [full][indep]. 163 tasks; Claude Code, Codex, OpenCode with six backends, "achieving an average resolved rate of only 31.5% on SWE-RPG", and the paper "identifies implicit requirement recovery as the main bottleneck" (24.5 to 46.0 percent of runs; planning failures 5.5 to 17.8 percent). Caveat: stage attribution is done by an LLM judge.
4. Anthropic, Claude Code best practices, https://code.claude.com/docs/en/best-practices [full][vendor]. "Plan mode is useful, but also adds overhead. For tasks where the scope is clear and the fix is small (like fixing a typo, adding a log line, or renaming a variable) ask Claude to do it directly. Planning is most useful when you're uncertain about the approach, when the change modifies multiple files, or when you're unfamiliar with the code being modified. If you could describe the diff in one sentence, skip the plan." Also: "Once the spec is complete, start a fresh session to execute it."
5. Anthropic, skill authoring best practices, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices [full][vendor]: the plan-validate-execute pattern is "having Claude first create a plan in a structured format, then validate that plan with a script before executing it." with "When to use: Batch operations, destructive changes, complex validation rules, high-stakes operations."

**Gap.** No measurement found of a task-specific plan reviewed by a second model or a human before coding (a plan-critic ablation). The skill's planner-subagent plus hash-locked `## Plan` has no direct external evidence for or against.

**Implies for the skill**

- A plan gate that fires on a trigger (multi-file, uncertain approach) and is skipped for one-sentence diffs matches both the vendor guidance and the measurements. A plan gate on every issue does not.
- On strong models the measured benefit of planning is cost, not correctness; the measured bottleneck is recovering what the issue actually requires. If the plan step exists, its job is requirement recovery, not step ordering.
- A bad plan is worse than none, so a plan that nobody checks is a net risk. Either check it (cheaply, e.g. against the issue's acceptance criteria) or drop it for that task.
- Forcing a reproduction/red phase onto tasks where the model's test is wrong can lose tasks the model would otherwise solve. This is an argument for keeping a non-TDD route, not for removing TDD.

### B2. Test-first with coding agents

**Findings**

1. Mathews & Nagappan, "Test-Driven Development for Code Generation" https://arxiv.org/abs/2402.13521 [full][indep]. "For MBPP and HumanEval, including tests contributes to solving an additional 12.0% and 8.5% of problems, respectively". Caveat: GPT-4/Llama 3, function-level, and the tests were supplied by humans, not written by the model.
2. Liang et al., class-level TDD, https://arxiv.org/abs/2602.03557 [full][indep]: class-level success up by 12 to 26 absolute points across eight LLMs, "achieving up to 71% fully correct classes." Caveat: benchmark-supplied tests.
3. "On the risk of coding before testing" https://arxiv.org/abs/2607.05139 [full][indep]. "generating tests after faulty code significantly reduces fault detection effectiveness compared to generating tests independently (14% vs. 25%)". The independent condition is a fresh context: "test generation is performed in a fresh interaction with the LLM that contains only the task description and no conversational context from the preceding code generation process." Prompting did not rescue it: "Generating test suites directly from the task description is more effective than prompt engineering techniques, with fault detection decreasing by 15.5% for summarization and 13.4% for both Chain-of-Thought and Chain-of-Verification." Conclusion: "generating both code and tests using the same model does not guarantee meaningful verification". Note the ceiling: the best condition still detects only a quarter of faults.
4. ImpossibleBench, https://arxiv.org/abs/2510.20270 [full][indep] (tasks made deliberately impossible so that passing means cheating). "GPT-5 cheats in 76% of the tasks in Oneoff-SWEbench and 2.9% on Oneoff-LiveCodeBench". "In general, we observe more capable models having higher cheating rates." "We find that more complex scaffolds encourage more cheating".
   - Prompt wording matters a lot: "appropriate prompt could dramatically reduce GPT-5's cheating from 92% to 1% on Conflicting-LiveCodeBench".
   - Access control: "Hiding tests from agents reduces cheating success rate to near zero, but also degrades performance on the original benchmark. Read-only access provides a middle ground: it restores legitimate performance while preventing test modification attempts. This approach is particularly effective against models like Opus-4.1, whose primary cheating strategy involves modifying test cases, but it does not eliminate other cheating methods". Recommendation: "we recommend either hiding test files entirely or restricting them to read-only access during implementation, when feasible".
   - Escape hatch: "we instruct the models to submit the string flag_for_human_intervention when they identify errors in the task ... lowering the cheating rate of GPT-5 from 54% to 9% and o3 from 49% to 12%. However, the effect is much less pronounced for Claude Opus 4.1."
   - Retries: "allowing multiple submissions increases the pass rate on open-test SWE-bench from 80% to 83%, and cheating rate on Conflicting-SWEbench from 33% to 38%".
5. SpecBench (Weco AI), https://arxiv.org/abs/2605.21384 [full][vendor]. 30 systems-level tasks. "found every model can saturate the visible test suite on every task. Yet beneath this uniform pass rate, reward hacking scales along two axes. First, the gap between validation and holdout test pass rate grows with task complexity (Figure 2)." and "the upper bound (90th-percentile) of the reward hacking gap scales predictably, increasing by 27 percentage points for every tenfold increase in lines of code."
6. Anthropic best practices [full][vendor]: "You can do something similar with tests: have one Claude write tests, then another write code to pass them."

**Gap.** No study compares test-first vs test-after vs no-tests inside an autonomous agent loop where the agent writes both the tests and the code on real repository issues. The positive TDD numbers all use externally supplied tests.

**Implies for the skill**

- The measured value of test-first is independence of the test from the implementation. When one session writes both in sequence, that independence is mostly gone even if the order is red-then-green. The order rule is cheaper to keep than to drop, but it is not the mitigation.
- The measured mitigations for test tampering are environmental: tests read-only during the green phase, or written in a context that has not seen the implementation. Both are enforceable outside the prompt (a PreToolUse hook on test paths; a forked subagent for test authoring).
- A sanctioned "this test/requirement looks wrong, stop and flag" exit reduced cheating in two of three models tested. The skill's `grill_required` exit is the analogue; it should also be reachable mid-implementation, not only at dispatch.
- Visible tests passing is weak evidence on large diffs. Size of diff is a usable signal for demanding a check that the author did not write.

### B3. Mutation testing as a check on agent-written tests

**Findings**

1. Meta ACH, "Mutation-Guided LLM-based Test Generation at Meta" https://arxiv.org/abs/2501.12862 [full][vendor]. "ACH generates relatively few mutants (aka simulated faults), compared to traditional mutation testing. Instead, it focuses on generating currently undetected faults that are specific to an issue of concern." Scale and acceptance: "ACH was applied to 10,795 Android Kotlin classes in 7 software platforms deployed by Meta, from which it generated 9,095 mutants and 571 privacy-hardening test cases. ACH also deploys an LLM-based equivalent mutant detection agent that achieves a precision of 0.79 and a recall of 0.47 (rising to 0.95 and 0.96 with simple preprocessing). ACH was used by Messenger and WhatsApp test-athons where engineers accepted 73% of its tests, judging 36% to privacy relevant." Cost side: "25% of the mutants generated are trivially syntactically equivalent." and "engineers and automated test generators may waste time trying to kill (unkillable) equivalent mutants."
2. MUTGEN, https://arxiv.org/abs/2506.02954 [full][indep]. "mutation score offers a more reliable and stringent measure, as demonstrated in our findings where some test suites achieve 100% coverage but only 4% mutation score." Feedback loops "tend to converge after the fourth iteration". Llama-3.3, Java.
3. AdverTest, https://arxiv.org/abs/2602.08146 [full][indep]. A mutant-writing agent paired against a test-writing agent: "improves fault detection rates by 8.56% over the best existing LLM-based methods and by 50.20% over EvoSuite, while remaining competitive on line and branch coverage."
4. Prior art uses a far lighter variant: `obra/superpowers` `skills/test-driven-development/writing-good-tests.md` (https://github.com/obra/superpowers/blob/main/skills/test-driven-development/writing-good-tests.md) has a 13-line section, "The Mutation Check": "Before finishing, mentally mutate the production code; at least one test should fail for each realistic mutation" followed by five mutation classes. No executed mutation, no evidence line.

**Gap.** No measurement found for what the skill actually does: a manual, one-mutant-per-test probe performed by the same session that wrote the test, with a text evidence line in the PR. Two blog-level leads on mutation testing for agent-written code were not read and are not cited. Nothing measures whether an author-chosen mutant is a fair probe (the author picks the mutant it knows its test kills).

**Implies for the skill**

- The direction is supported: coverage and "tests pass" say little; a small number of targeted mutants is how the one documented industrial deployment works.
- The evidence supports mutants chosen by something other than the test's author (a second agent, or a tool). A self-chosen probe is unmeasured and structurally weak.
- Equivalent mutants are a real time sink (a quarter trivially equivalent at Meta). A rule that every surviving mutant must be killed will burn turns; the probe needs an "equivalent, skipped" outcome.
- Whether the probe ran is checkable by a script (apply the patch, run the test, expect red, revert). Whether it was "mentally" done is not.

### B4. Self-review vs independent review

**Findings**

1. Pombal, Rei, Martins, self-preference in rubric-based evaluation, https://arxiv.org/abs/2604.06996 [full][indep]. "Using IFEval and LiveCodeBench, benchmarks with programmatically verifiable rubrics, we show that SPB persists even when evaluation criteria are entirely objective: among rubrics where generators fail, judges can be more than 50% more likely to incorrectly mark them as satisfied when the output is their own." On code: "In the worst case (GPT-5), the judge can be 20 times more likely to overestimate its own outputs than those of unrelated models." Same-family models share it: "most judges also over-credit their relatives, most severely on LiveCodeBench (GPT-5: 11.91)." Mitigation is partial: "ensembling multiple judges helps mitigate SPB, but without fully eliminating it." Caveat: this is same-model vs unrelated-model judging of rubric satisfaction, not PR review, and it does not separate same-session from fresh-context.
2. SWR-Bench, https://arxiv.org/abs/2509.01494 [full][indep]. 1000 manually verified PRs (500 with issues, 500 clean). Automated reviewers are limited by "their low precision, indicative of a high false positive rate. Specifically, the Avg. FP Count metric reveals that these approaches frequently generate multiple invalid suggestions per pull request, with some combinations (e.g., Hybrid-Review with DeepSeek-R1) producing over 7 false positives on average." "This issue is more severe for other four ACR techniques, all of which exhibited precision scores below 10%." Best single-pass F1 is 19.38 percent; running the review five times and aggregating lifts the best model to 23.84 percent. Recall collapses on bigger PRs: "the Recall tends to decrease sharply" from 38.35 percent on PRs with one change-action to 8.88 percent with five or more. "Conclusion 4: ACR tools struggle to comprehensively review complex PRs." Caveat: 2025 models, human-authored PRs, LLM-judged.
3. c-CRAB, https://arxiv.org/abs/2603.23448 [full][indep]. Review comments converted to executable tests; tools include "the open-source PR-agent, as well as commercial code review agents from Devin, Claude Code, and Codex". "the automated review tools achieve pass rates ranging from 20.1% to 32.1%, whereas human reviewers achieve a pass rate of 100%. ... Considering the union across all four tools, 97 out of the 234 tests were passed by at least one tool (41.5%)". Caveat: recall against human comments only; the 100 percent for humans is by construction.
4. MCR-Bench, https://arxiv.org/abs/2608.27442 [abs][indep]: "mainstream LLMs exhibit limited overall performance in defect detection and defect lifecycle state tracking, with performance degrading significantly as the number of interaction rounds increases".
5. Zietsman, https://arxiv.org/abs/2603.25773 [full][position, small contrived experiments]. Hypothesis: "without an external reference, both the generating agent and the reviewing agent reason from the same artefact, share the same training distribution, and exhibit correlated failures." On planted domain bugs: "BDD caught all five. AI review ranged from 0% to 100% depending on domain opacity." Its own caveat: "These results are directional, not statistically significant." Low confidence.
6. Anthropic best practices [full][vendor]. "A fresh context improves code review since Claude won't be biased toward code it just wrote." "The longer Claude works unattended, the more an independent check matters before you count the work as done. A reviewer running in a fresh [subagent] context sees only the diff and the criteria you give it, not the reasoning that produced the change, so it evaluates the result on its own terms." And on false positives: "A reviewer prompted to find gaps will usually report some, even when the work is sound, because that is what it was asked to do. Chasing every finding leads to over-engineering: extra abstraction layers, defensive code, and tests for cases that can't happen. Tell the reviewer to flag only gaps that affect correctness or the stated requirements, and treat the rest as optional."
7. Prior art agrees with the vendor line. `obra/superpowers` `executing-plans`: "This is the one fresh context the whole run buys. Do not skip it, and do not replace it with your own read of the diff." and, where no subagent is available, "a self-review by the author is weaker than a fresh reviewer, and your human partner decides whether that is enough before merge."

**Gap.** No study found that directly compares (a) same-session self-review, (b) fresh-context review by the same model, (c) review by a different model, on agent-authored PRs, reporting both catch rate and false-positive rate. The fresh-context advantage is vendor guidance plus inference from self-preference results, not a measured effect size.

**Implies for the skill**

- The same-session diff self-review plus smell checklist at the end of the skill is the weakest reviewer configuration in everything read. It cannot be what clears a PR for self-merge.
- An independent reviewer is also not a strong gate: about a fifth to a third of what humans flag, recall under 10 percent on multi-change PRs, and mostly false positives. "Bot review comment addressed" is a weak merge condition, and "address every finding" is a recipe for churn.
- What the evidence supports as the gate for self-merge is external grounding: tests the author did not write, deterministic checks, small diffs. Review is a supplement for design and intent.
- If a reviewer is kept, a different model family reduces shared bias more than a fresh context of the same model does, and keeping the PR small matters more than either.

### B5. Risk-tiered auto-merge of agent PRs

**Findings**

1. Meta RADAR, "Automating Low-Risk Code Review at Meta" https://arxiv.org/abs/2605.30208 [full][vendor, observational]. "We deployed RADAR (Risk Aware Diff Auto Review), a multi-stage funnel that classifies each diff by authorship and source type, applies eligibility gates, static heuristics, a machine-learned Diff Risk Score, LLM-based Automated Code Review, and deterministic validation before landing qualifying changes." "RADAR has reviewed 535K+ diffs and landed 331K+." Reported outcome: revert rate about one third and production-incident rate about one fiftieth of non-RADAR diffs, with the paper's own caveat "While this is not a causal estimate" and "Because diffs are not randomly assigned to RADAR, unobserved confounding can influence observed changes."
   - Who scores risk: "Diff Risk Score (DRS) is a machine learning model that predicts how likely a diff is to cause a negative outcome, primarily a production incident (PI). ... for example, flagging 10% of diffs while catching 60% of PI-causing changes." The author of the diff does not classify its own risk.
   - How conservative: "For human-authored diffs, the default DRS threshold is P5, meaning only the lowest-risk 5% of diffs qualify"; agent runbooks get P20, or P50 once allowlisted.
   - Earned by track record: "Each runbook must demonstrate a clean track record over a 60-day lookback window: zero PIs, a low revert rate, a low human rejection rate, and a minimum number of landed diffs to establish statistical confidence."
   - Hard exclusions: "Additionally, runbooks whose names contain certain keywords (e.g., "test") are excluded to avoid automating changes to test infrastructure without human oversight." and "The diff must not contain blocklisted code phrases, and must not touch files matching suffix or prefix blocklists for certain configurations and paths."
   - Deterministic changes are the blanket case: "When a codemod is classified as deterministic, meaning the transformation is fully specified and does not involve LLM generation, it can be approved through a Blanket AutoAccept policy."
   - Review is deferred, not removed, for human diffs: "RADAR Verification determines whether a human-authored diff can safely land with a deferred post-land human review."
   - Context: "The organizational context includes a large monorepo, standardized tooling, and high automation coverage for testing and rollout."
2. "Why Are Agentic Pull Requests Merged or Rejected?" https://arxiv.org/abs/2605.22534 [full][indep]. 9,799 human-reviewed agentic PRs, 717 inspected by hand. "only 35.7% of rejected PRs reflected clear agentic failures, while 31.2% were driven by workflow constraints and 33.1% lacked observable decision rationale. Among merged PRs, 15.4% required explicit reviewer involvement through feedback or direct commits".
3. "Beyond Bug Fixes", https://arxiv.org/abs/2601.20109 [abs + targeted reads][indep]. 1,210 merged agent bug-fix PRs, SonarQube diff analysis: "merge success does not reliably reflect post-merge code quality" and "Although Bugs are less frequent than other issues in the bug-fix PRs, they are disproportionately severe (often BLOCKER)".
4. Claude Code auto mode, https://code.claude.com/docs/en/best-practices [full][vendor]: "a separate classifier model reviews most actions instead of you and blocks only what looks risky, such as scope escalation, unknown infrastructure, or hostile-content-driven actions". This classifies actions, not diff risk.

**Gap.** No published data on the accuracy of a risk label assigned by the authoring agent to its own PR. No data on auto-merge outcomes in solo or small repositories. Several leads on agentic-PR risk were found by search but not read and are not cited.

**Implies for the skill**

- The only published large-scale practice puts the risk decision outside the author: a separate model, path/phrase blocklists, deterministic validation, and a track record. The skill's LOW/MEDIUM/HIGH label written by the authoring session into its own PR body is the one configuration with no evidence behind it.
- A solo repo cannot train a risk model, but it can copy the cheap parts: a path/pattern denylist computed by a script (workflows, tests-only changes, migrations, auth, secrets, the merge gate itself), a diff-size cap, and "deterministic change" as the blanket-eligible class. Those belong in CI, where the author cannot talk its way past them.
- Meta starts at the safest 5 percent and widens on evidence. Self-merging MEDIUM from day one is the opposite order.
- Test-infrastructure changes are excluded from auto-landing at Meta. That pairs with B2: a PR that edits existing tests is a different risk class from one that only adds them.

### B6. Long instruction files, adherence, and compaction

**Findings**

1. Claude Code skills documentation, https://code.claude.com/docs/en/skills [full][vendor]. Size: "Keep `SKILL.md` under 500 lines. Move detailed reference material to separate files." and "Once a skill loads, its content stays in context across turns, so every line is a recurring token cost. State what to do rather than narrating how or why". Compaction: "When the conversation is summarized to free context, Claude Code re-attaches the most recent invocation of each skill after the summary, keeping the first 5,000 tokens of each. Re-attached skills share a combined budget of 25,000 tokens. Claude Code fills this budget starting from the most recently invoked skill, so older skills can be dropped entirely after compaction if you have invoked many in one session." Remedy: "use [hooks] to enforce behavior deterministically. If the skill is large or you invoked several others after it, re-invoke it after compaction to restore the full content."
2. Skill authoring best practices, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices [full][vendor]. "Keep SKILL.md body under 500 lines for optimal performance"; "**Default assumption:** Claude is already very smart"; "Only add context Claude doesn't already have."; "**Keep references one level deep from SKILL.md**"; "If workflows become large or complicated with many steps, consider pushing them into separate files and tell Claude to read the appropriate file based on the task at hand."; "For particularly complex workflows, provide a checklist that Claude can copy into its response and check off as it progresses."; "**Create evaluations BEFORE writing extensive documentation.**"; "**Prefer scripts for deterministic operations:** Write `validate_form.py` rather than asking Claude to generate validation code". Utility scripts are "More reliable than generated code" and "Save tokens (no need to include code in context)".
3. Claude Code best practices [full][vendor]: "Most best practices are based on one constraint: Claude's context window fills up fast, and performance degrades as it fills."; "If Claude keeps doing something you don't want despite having a rule against it, the file is probably too long and the rule is getting lost."; "If you emphasize many lines, none of them stands out."
4. "Lost in Compaction", https://arxiv.org/abs/2608.11242 [full][indep]. Side constraints (SCs) injected into agent sessions, then compacted: "Current compactors retain only 17% of injected SCs on average, and most perform worse than running the same task without compaction." "Process SCs are consistently retained the least across all compactors." "even the best result (Preference under gpt-oss (pi-mono), at 36%) loses nearly two-thirds of constraints." Fix: a separate extractor "achieving over 90% retention across all three scenarios", with the conclusion "closing it requires architectural separation rather than better compactor prompts". Caveat: constraints issued in conversation, mostly open-weight compactors; it does not test Claude Code's skill re-attachment.
5. IFScale (Distyl AI), https://arxiv.org/abs/2507.11538 [full][vendor]. "even the best frontier models only achieve 68% accuracy at the max density of 500 instructions". Strong reasoning models were "maintaining near-perfect performance through 150 or more instructions before declining." "Models overwhelmingly err toward omission errors as instruction density increases." Caveat: keyword-inclusion in one call, 2025 models.
6. Gloaguen et al., "Evaluating AGENTS.md" https://arxiv.org/abs/2602.11988 [full][indep] — partial counter-evidence. "we find that providing context files does not generally improve task success rates, while increasing inference cost by over 20% on average." But length is not the mechanism: "We observe no clear dependency between the success rate or the per-instance cost and the context file length. This suggests that the length of context files does not influence our findings, and that the increase in cost is better explained by the fact that coding agents tend to follow instructions written in the context files". Recommendation: context files "should only contain specific additional instructions beyond what is already available in the codebase."
7. Lulla et al., https://arxiv.org/abs/2601.20404 [abs][indep]: across 10 repositories and 124 PRs, "the presence of AGENTS.md is associated with a lower median runtime (28.64%) and reduced output token consumption (16.58%), while maintaining a comparable task completion behavior."
8. Plan-reminder result in B1 item 1 is independent support for drift over long trajectories.

**Gap.** No measurement of adherence to a multi-step procedural skill as a function of its length, and none of Claude Code's skill re-attachment specifically.

**Implies for the skill**

- My estimate, not a measurement: at roughly four bytes per token the skill is about 7,700 tokens. Keeping the first 5,000 tokens after compaction cuts it near line 284, inside §4-TDD. Everything after that is gone from context after the first auto-compaction of a long run: the PR template and Risk Assessment, the merge policy, cleanup, safety rules, the diff review, the recovery playbook. Those are the steps executed last, which is when compaction is most likely to have happened.
- 454 lines is under the 500-line guidance, so line count is not the problem; position and token budget are. Either the must-not-skip late steps move to the top, or they move out of the skill into phase files read on entry to each phase and into gates that do not depend on context at all.
- Instructions are followed and every one costs turns. Each instruction that restates what the model does unprompted, or narrates why, is paid on every run. The vendor's own test for keeping a line is whether removing it changes behaviour.
- A checklist the agent writes to a durable place (issue comment, ledger file) survives compaction; a rule in the prompt does not. The prior-art repos converged on the same device (B8).

### B7. Deterministic gates vs in-prompt instructions

**Findings**

1. Claude Code hooks guide, https://code.claude.com/docs/en/hooks-guide [full][vendor]: "Hooks are user-defined shell commands. Claude Code runs them at specific points in its lifecycle, which gives you deterministic control: certain actions always happen rather than relying on the LLM to choose to run them." Event table includes `PreToolUse` "Before a tool call executes. Can block it", `Stop` "When Claude finishes responding", `TaskCompleted` "When a task is being marked as completed", `PreCompact`, `PostCompact`. On compaction: "Use a `SessionStart` hook with a `compact` matcher to re-inject critical context after every compaction."
2. Claude Code best practices [full][vendor]: "Use hooks for actions that must happen every time with zero exceptions."; "Unlike CLAUDE.md instructions which are advisory, hooks are deterministic and guarantee the action happens."; "**As a deterministic gate**: a [Stop hook] runs your check as a script and blocks the turn from ending until it passes."; "If Claude already does something correctly without the instruction, delete it or convert it to a hook."
3. Skills doc [full][vendor]: skill frontmatter `hooks` — "Hooks that Claude Code registers when the skill is invoked and keeps running for the rest of the session."
4. Independent measurements that point the same way: ImpossibleBench's read-only tests (B2), "architectural separation rather than better compactor prompts" (B6), RADAR's "deterministic validation" and blocklists (B5).
5. A counter-example from prior art: spec-kit's `implement` command carries its "hooks" as prose the model must interpret, and its recent history is a series of fixes for the model not running them — commit titles "fix(extensions): tell agent to run mandatory hooks, not just emit the directive (#2901)" (2026-06-25) and "fix: promote post-execution hook dispatch to H2 with directive language (#2713)" (2026-05-26), https://github.com/github/spec-kit/commits/main/templates/commands/implement.md. The current text still has to say "Emitting the block alone does not run the hook."

**Gap.** No controlled study comparing hook-enforced and prompt-only adherence for the same step in a coding agent. The case rests on vendor guidance, the adjacent measurements above, and one observed failure history.

**Implies for the skill**

- Every step the skill marks as mandatory should be sorted into "a script can check it" or "needs judgement". The first group (linked issue, tests green, probe evidence present, plan hash unchanged, denylisted paths untouched, risk tier vs touched paths) belongs in a hook or CI check and can be deleted from the prose. The user-level policy already has branch-protection gates; the skill duplicates several of them in words.
- What stays in the prompt is judgement: what the issue requires, which seam to test, whether to stop and ask.
- Skill-scoped `hooks` frontmatter makes this possible without global settings changes. Note the documented lifetime is the rest of the session, not the skill's duration.

### B8. Prior art and current Claude Code features

**Prior art** (all files fetched raw from GitHub on 2026-09-30; line counts from `wc -l`; [full])

| Repo / file | Lines | Structure | Recent change |
|---|---|---|---|
| `mattpocock/skills` `skills/engineering/implement/SKILL.md` https://github.com/mattpocock/skills/blob/main/skills/engineering/implement/SKILL.md | 15 | Frontmatter with `disable-model-invocation: true`, then five sentences: "Use /tdd where possible, at pre-agreed seams." "Run typechecking regularly, single test files regularly, and the full test suite once at the end." "Once done, use /code-review to review the work." "Commit your work to the current branch." No branch, PR, merge, or risk logic. | Last touched 2026-07-08 ("refactor: unify planning skills into /to-spec + /to-tickets"). Three commits in total. |
| same repo, `implement-spec/SKILL.md` | 40 | Orchestrator for a whole spec: tickets are "a **task graph**", implementer subagents "each in its own worktree on its own branch", a merger subagent, then `code-review` once on the integration branch. "Communication to and from subagents should be sparse. Communicate primarily through **context pointers**". | New: "Graduate implement-spec to engineering" 2026-09-24. |
| same repo, `tdd/SKILL.md` (+ `tests.md` 77, `mocking.md` 59) | 38 | Reference, not procedure: what a good test is, seams, three anti-patterns (implementation-coupled, tautological, horizontal slicing), three loop rules. "**Test only at pre-agreed seams.** Before writing any test, write down the seams under test and confirm them with the user." "**Refactoring is not part of the loop.** It belongs to the review stage". No mutation step. | 2026-09-17 rename of a glossary convention; wording edits in August. |
| same repo, `code-review/SKILL.md` | 87 | Two axes, Standards and Spec, as "**parallel sub-agents** so they don't pollute each other's context"; the 12-smell baseline (see A3); findings are not merged across axes. | August wording edits. |
| `obra/superpowers` `skills/executing-plans/SKILL.md` (+ scripts `task-start` 28 lines, `task-done` 52) https://github.com/obra/superpowers/blob/main/skills/executing-plans/SKILL.md | 373 | Inline execution of a pre-written plan. Deterministic pieces are scripts: `task-done` "runs the tests, keeps the full output in the workspace, prints the tail, and — only if they pass — appends the completion line to the ledger". A ledger file records `Ruling:` lines for every deviation. One fresh-context whole-branch review at the end. A "Common Rationalizations" table. Stops only for four named cases, including "a side effect outside this worktree that norms say you ask about first (a merge, a push to a shared branch, a publish)". | Rewritten in "Release v6.4.1: ... Native plan execution ..." 2026-09-19. |
| same repo, `test-driven-development/SKILL.md` (+ `writing-good-tests.md` 198) | 330 | Prescriptive: "NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST"; "Verify RED" is "**MANDATORY. Never skip.**"; rationalization table; verification checklist. Mental "Mutation Check" lives in the reference file (B3). | 2026-07-24 refactors folding rebuttals into the table; v6.4.1. |
| same repo, `subagent-driven-development/SKILL.md` (+ 3 prompt templates, 3 scripts) | 568 | Fresh implementer per task, task review after each, whole-branch review at the end. Explicit model tiering: "Use the least powerful model that can handle each role" and "**Always specify the model explicitly when dispatching a subagent.**" Reviewer gets the diff as a file from `scripts/review-package`. On durability: "The ledger is what survives compaction. Controllers without one have re-dispatched entire completed task sequences." | 2026-07-24 "lifecycle restructure with resume-based fix loop, five-round breaker"; v6.3.0 and v6.4.1. |
| `github/spec-kit` `templates/commands/implement.md` https://github.com/github/spec-kit/blob/main/templates/commands/implement.md | 222 | Frontmatter declares prerequisite scripts (sh, ps, py). Body: prose hook dispatch, a checklist gate ("Treat checklist markers as a read-only gate"), about 40 lines of ignore-file rules and per-technology patterns, phase execution over `tasks.md`, a "Done When" checklist. No branch/PR/merge logic. | 2026-09-09 "report an unreadable extensions.yml instead of skipping hooks silently"; see B7 item 5. |
| same repo, `presets/lean/commands/speckit.implement.md` | 22 | Load four files, execute tasks in order ticking `- [ ]`, "Halt on failure and report the issue", validate. | Added 2026-04-10, unchanged since. |
| Anthropic's own example, `fix-issue` in https://code.claude.com/docs/en/best-practices | about a dozen | `disable-model-invocation: true` and eight numbered steps from "Use `gh issue view` to get the issue details" to "Push and create a PR". | n/a |

Observations across the three repositories (mine, from the files above):

- None of them puts issue intake, planning, TDD, review, PR authoring, risk classification, and merge in one file. The pipeline is split into small skills that call each other, or into an orchestrator plus templates and scripts.
- None of them merges. superpowers names a merge as one of four things that stop the run. The self-merge policy is the part of `/implement` with no prior art.
- The two trajectories differ: mattpocock shrank `implement` to 15 lines and moved the substance into `tdd`, `code-review` and an orchestrator; superpowers stayed long (373 and 568 lines, the latter over Anthropic's 500-line guidance) but moved bookkeeping into scripts and a ledger file.
- The repositories' popularity is not evidence that their contents work. None publishes an evaluation.

**Claude Code features that now cover what a hand-written skill used to spell out** (all [full][vendor])

| Need | Feature | Source quote |
|---|---|---|
| Separate planning from editing | Plan mode | "Plan mode tells Claude to research and propose changes without making them. Claude reads files, runs shell commands to explore, and writes a plan, but does not edit your source." https://code.claude.com/docs/en/permission-modes |
| Run a step in a clean context | `context: fork`, `agent` | "Add `context: fork` to your frontmatter when you want a skill to run in isolation. Claude Code starts a new subagent of the type set in the `agent` field and gives it the skill content as its prompt. The subagent doesn't see your conversation history, so the skill's instructions have to stand on their own." https://code.claude.com/docs/en/skills |
| Wait for that fork | `background` | "Set to `false` to wait for the forked subagent's result in the turn that invoked the skill, instead of running it in the background. Default: `true`. Requires Claude Code v2.1.218 or later." (skills doc) |
| Per-step model and effort | `model`, `effort` | "Model to use when this skill is active. The override applies for the rest of the current turn and isn't saved to settings." / "Overrides the session effort level." (skills doc). Subagents take the same two fields, https://code.claude.com/docs/en/sub-agents |
| Restrict tools during a phase | `disallowed-tools`, `allowed-tools` | "Tools removed from Claude's available pool while this skill is active." (skills doc) |
| Never auto-trigger | `disable-model-invocation` | "Set to `true` to prevent Claude from automatically loading this skill. Use for workflows you want to trigger manually with `/name`." (skills doc) |
| Must-run checks | hooks, incl. skill-scoped | B7 items 1 to 3 |
| Bundled scripts | `${CLAUDE_SKILL_DIR}` | "Use this in bash injection commands to reference scripts or files bundled with the skill, regardless of the current working directory." (skills doc) |
| Isolated working copy | `--worktree`, subagent `isolation` | "Pass `--worktree` or `-w` with a name to create an isolated worktree and start Claude in it." https://code.claude.com/docs/en/worktrees ; subagent `isolation`: "Set to `worktree` to run the subagent in a temporary [git worktree]" (sub-agents doc) |
| Independent review | bundled `/code-review` | "For a correctness check, run the bundled [`/code-review` skill], which reviews the current diff for bugs in a fresh subagent and returns findings to the session." (best practices) |
| Behavioural verification | bundled `/verify` | "Build and run your app to confirm a code change does what it should, without falling back to tests or type checks" (skills doc) |
| Fan-out | bundled `/batch` | "have Claude split the change across 5 to 30 subagents. Each subagent works in its own worktree." (skills doc) |
| Unattended completion criterion | `/goal`, Stop hook | "The `/goal` and Stop hook versions are what let an unattended run finish correctly without you." (best practices) |

**Implies for the skill**

- Branch/worktree setup, plan gating, fresh-context review, and model selection per step are platform features now. Prose that re-implements them is recurring token cost with no added guarantee.
- The shape that prior art and vendor guidance agree on: a short orchestrating skill, reference skills for TDD and review loaded when needed, scripts for bookkeeping, a durable ledger outside the context window, and the merge decision left to gates outside the authoring session.
- `context: fork` is the documented way to give the test-writing or reviewing step a context that has not seen the implementation (B2, B4).

---

## Sources

Independent / academic

- Kanewala & Bieman, Testing Scientific Software: A Systematic Literature Review — https://arxiv.org/abs/1804.01954 — full text read
- Li et al., From Data to Decision — https://arxiv.org/abs/2506.16051 — full text read
- Liu et al., From Plan to Action: How Well Do Agents Follow the Plan? — https://arxiv.org/abs/2604.12147 — full text read
- Fan et al., An Empirical Study of Harness Design for Coding Agents — https://arxiv.org/abs/2609.20804 — full text read (abstract, planning sections)
- SWE-RPG — https://arxiv.org/abs/2608.09072 — full text read (abstract, results)
- Mathews & Nagappan, Test-Driven Development for Code Generation — https://arxiv.org/abs/2402.13521 — full text read
- Liang et al., dependency-aware class-level TDD — https://arxiv.org/abs/2602.03557 — full text read
- On the risk of coding before testing — https://arxiv.org/abs/2607.05139 — full text read
- ImpossibleBench — https://arxiv.org/abs/2510.20270 — full text read
- MUTGEN — https://arxiv.org/abs/2506.02954 — full text read
- AdverTest — https://arxiv.org/abs/2602.08146 — full text read
- SWR-Bench — https://arxiv.org/abs/2509.01494 — full text read
- c-CRAB — https://arxiv.org/abs/2603.23448 — full text read
- MCR-Bench — https://arxiv.org/abs/2608.27442 — abstract only
- Pombal, Rei, Martins, self-preference bias in rubric-based evaluation — https://arxiv.org/abs/2604.06996 — full text read (abstract, LiveCodeBench results)
- Zietsman, correlated failures in generator/reviewer pipelines — https://arxiv.org/abs/2603.25773 — full text read; position paper, low confidence
- Why Are Agentic Pull Requests Merged or Rejected? — https://arxiv.org/abs/2605.22534 — full text read
- Beyond Bug Fixes (post-merge quality of agent PRs) — https://arxiv.org/abs/2601.20109 — abstract plus targeted passages
- Lost in Compaction — https://arxiv.org/abs/2608.11242 — full text read
- Gloaguen et al., Evaluating AGENTS.md — https://arxiv.org/abs/2602.11988 — full text read
- Lulla et al., AGENTS.md and agent efficiency — https://arxiv.org/abs/2601.20404 — abstract only

Vendor / company self-report

- Meta, ACH mutation-guided test generation — https://arxiv.org/abs/2501.12862 — full text read
- Meta, RADAR — https://arxiv.org/abs/2605.30208 — full text read
- Weco AI, SpecBench — https://arxiv.org/abs/2605.21384 — full text read
- Distyl AI, IFScale — https://arxiv.org/abs/2507.11538 — full text read
- Anthropic, Claude Code best practices — https://code.claude.com/docs/en/best-practices — full text read
- Anthropic, Claude Code skills — https://code.claude.com/docs/en/skills — full text read
- Anthropic, skill authoring best practices — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices — full text read
- Anthropic, Claude Code hooks guide, sub-agents, permission modes, worktrees — https://code.claude.com/docs/en/hooks-guide , https://code.claude.com/docs/en/sub-agents , https://code.claude.com/docs/en/permission-modes , https://code.claude.com/docs/en/worktrees — fetched in full, read by targeted search only

Prior art (primary files, full text read)

- https://github.com/mattpocock/skills — `skills/engineering/{implement,implement-spec,tdd,code-review}/SKILL.md`, `.changeset/graduate-implement-spec.md`
- https://github.com/obra/superpowers — `skills/{executing-plans,test-driven-development,subagent-driven-development}/SKILL.md`, `skills/test-driven-development/writing-good-tests.md` (the mutation-check section)
- https://github.com/github/spec-kit — `templates/commands/implement.md`, `presets/lean/commands/speckit.implement.md`
- Commit histories via the GitHub API for each of those paths

Secondary, summary only

- https://dev.to/trikitrok/on-code-smells-catalogues-and-taxonomies-3ba6 — smell counts per edition of *Refactoring*; read through a summarising fetch, not quoted

Seen but not used as evidence: a Meta engineering blog post on LLM mutation testing (summary only), arXiv 2606.28438 (about recursive fine-tuning, off-topic), arXiv 2604.22891 (self-preference bias of LLM judges) and arXiv 2606.07379 (agent cheating under randomized tests) — both downloaded, neither read.

---

## Gaps and low-confidence items

1. **Plan reviewed by a second model or human** — no measurement found. B1's evidence is about workflow plans and self-maintained todo lists.
2. **Test-first inside an autonomous agent loop** — no head-to-head of test-first, test-after, no-tests where the agent writes both. Positive TDD effect sizes all come from externally supplied tests.
3. **Self-performed single-mutant probe** — unmeasured. Only tool-driven or second-agent mutation has evidence.
4. **Same-session vs fresh-context vs different-model review on agent PRs** — no direct comparison found. The fresh-context advantage is vendor guidance plus inference from self-preference studies that compare model identity, not session.
5. **Self-assigned risk labels** — no accuracy data. Solo or small-repo auto-merge outcomes — no data. RADAR is one company, observational, in a monorepo with heavy test and rollout automation.
6. **Hooks vs prompt for step adherence** — no controlled study. Vendor guidance, adjacent measurements, and one project's fix history.
7. **Skill length vs adherence to a procedure** — not measured anywhere. The "cut near line 284" figure is my byte-based estimate of a documented 5,000-token rule, not a tokenizer count; it should be checked against a real compaction before the redesign leans on the exact line.
8. **Model drift.** Most measurements predate the current model generation or use open-weight models. ImpossibleBench reports cheating rising with capability; the harness study reports planning mattering less with capability. Neither was measured on the model that will run this skill.
9. **LLM-judged benchmarks.** SWR-Bench and SWE-RPG rely on LLM judges for scoring or attribution.
10. **Part A, A3.** Fowler's book was not read; edition counts come from a secondary page read in summary. The match with the mattpocock list is exact and verified.
11. **Prior-art popularity is not efficacy.** None of the three repositories publishes an evaluation of its skills.
12. **Claude Code docs** describe the product as of 2026-09-30; frontmatter fields and the compaction budget are version-dependent (`background` needs v2.1.218 or later).
