# /grill redesign — external evidence

Date: 2026-09-30. Scope: (A) audit of every external citation in `skills/grill/*.md`; (B) evidence for and against the practices the skill is built on.

Conventions used throughout:

- Text in quotation marks was copied from fetched page content. Anything not in quotation marks is my paraphrase or inference.
- Read depth per source: **full** = full text read; **abs** = abstract / summary / landing page only.
- Source class: **indep** = independent measurement (peer-reviewed or preprint); **vendor** = the vendor describing its own product; **pract** = practitioner report or design choice without a controlled measurement.
- "What this implies for the skill" blocks are inference, kept apart from the evidence.
- Method: pages fetched with curl / WebFetch, converted to text, and grepped for the quoted sentences. Two Firecrawl calls used (of 25 allowed), both for ScienceDirect pages that block plain fetches. No reddit.com content fetched or cited.

---

## Part A — citation audit

Tally over the 12 cited claims (A1–A11, with A2 counted once as cited and once against its real source): 6 SUPPORTED (three of them with caveats that change how the claim may be used), 4 PARTLY, 1 ID DOES NOT MATCH THE DESCRIBED PAPER, 1 uncheckable as cited (no identifier), 1 sub-claim NOT FOUND in any fetched source, 1 primary SOURCE UNREACHABLE. Two further uncited references to "the research" (A12, A13) are accurate characterizations of A4/A5.

| # | Claim as the skill states it | Where | What the source says (quote) | Verdict | Read |
|---|---|---|---|---|---|
| A1 | "This third-person reviewer framing (based on arxiv 2505.23840) reduces agreement-bias in LLM responses to user proposals by ~64% in multi-turn dialogues." | SKILL.md:48 | SYCON Bench, https://arxiv.org/abs/2505.23840. "adopting a third-person perspective reduces sycophancy by up to 63.8% in debate scenario." Body: "assigning a third-person persona (Andrew Prompt) boosts ToF performance by up to 63.8% in debate setting". "the Andrew prompt adopts a third-person perspective—prompting the model to reason as “Andrew” and promote objectivity, inspired by Distanced Self-Talk (Kross et al., 2014)." "the Andrew prompt performs exceptionally well in Debate Scenario ... In contrast, no clear trend is observed when identifying false presuppositions." Table 4, ToF in debate, You → Andrew: GPT-4o 4.90 → 4.83; o3-mini 4.95 → 4.95; Claude-3.7-Sonnet 4.59 → 4.74; Llama-3.1-8B 2.81 → 4.56; Qwen2.5-14B 3.25 → 4.54. False-presupposition scenario: GPT-4o 3.25 → 3.04; DeepSeek-v3 3.28 → 2.87. | **PARTLY.** Three differences. (1) "~64%" is the paper's "up to" figure, a best case; the large gains in Table 4 are on open-weight models (Llama-3.1-8B, Qwen2.5-14B, DeepSeek-v3), and for GPT-4o, o3-mini and Claude-3.7-Sonnet in the same table the change is between -0.07 and +0.15 on a ~5-point scale. (2) It holds in one of three scenarios (debate); in the false-presupposition scenario the same prompt made two models worse. (3) The intervention is a third-person persona for the *model* ("Andrew"), not a third-person description of the user or of the proposal, which is what the skill does. The scenario is holding a stance under user pressure, not reviewing a user's design proposal. | full |
| A2 | "same-session self-review has a 64.5% blind-spot rate across 14 models (arXiv 2506.04907)" | SKILL.md:91; CRITIC-COVERAGE.md:12 | https://arxiv.org/abs/2506.04907 is "Context Is Not Comprehension" (a Verbose ListOps benchmark). It contains no 64.5% figure and nothing about self-review. | **ID DOES NOT MATCH THE DESCRIBED PAPER.** | full |
| A2b | Same claim, against the paper it actually comes from | same | Self-Correction Bench, https://arxiv.org/abs/2507.02778. "Testing 14 open-source non-reasoning models, we find a 64.5% average Self-Correction Blind Spot: models reliably correct external errors but fail on identical internal ones." "Our headline 64.5% blind spot is measured on injected errors. ... On models’ own errors (Section 4.1), the design yields only a lower bound: at least 4.3–10.8% of the errors a model commits are ones it demonstrably had the knowledge to catch." "Reasoning models exhibit a small, even negative, Self-Correction Blind Spot (Figure 8), in stark contrast to non-reasoning models." "Appending “Wait” ... reduces the blind spot by 89.3% on average". | **PARTLY**, even with the right ID. The number and the "14 models" are real, but: the 14 are open-source non-reasoning models; the errors are injected into the model's own output, not a "same-session self-review" of a design; the paper itself reports the effect as small or negative for reasoning models, which is the class the skill runs on; on the models' own naturally occurring errors the paper only claims a 4.3–10.8% lower bound. | full |
| A3 | "fresh-context review measurably beats same-session (CCR F1 28.6 vs 24.6, arXiv 2603.12123)" | SKILL.md:91; CRITIC-COVERAGE.md:12 | Cross-Context Review, https://arxiv.org/abs/2603.12123. "Over 360 reviews, CCR reached an F1 of 28.6%, outperforming SR (24.6%, p=0.008, d=0.52), SR2 (21.7%, p<0.001, d=0.72), and SA (23.8%, p=0.004, d=0.57)." Review contexts per condition: SR "Full history"; SR2 "Full + 1st review"; SA "Prompt + artifact"; CCR "Artifact only". "Knowing the generation prompt — understanding what the user originally asked for — does not improve review quality. If anything, it slightly hurts (SA F1 23.8% vs SR 24.6%, though the difference is not significant)." "The gap between CCR and SR is widest for critical errors: 11 percentage points. For minor errors, it essentially vanishes (18% vs 19% — SR actually edges ahead)." Limitations: "We used a single model (Claude Opus 4.6)." "The errors were deliberately injected, not naturally occurring." "The absolute F1 numbers are moderate — 28.6% for the best condition." | **SUPPORTED** numerically, with caveats that matter. Single author, single model, injected errors, 30 artifacts. More important: the winning condition is *artifact only*. The skill's critic payload is problem statement + proposed direction + AC, which corresponds to the paper's SA condition ("Prompt + artifact"), and SA did not beat same-session review. CCR precision in Table 2 is 31.5% (3.1 false positives out of 4.5 findings per review). | full |
| A4 | "debate ≤ majority vote in expectation per arXiv 2508.17536" | SKILL.md:98; CRITIC-COVERAGE.md:12; GROUNDING.md:32 | Debate or Vote, https://arxiv.org/abs/2508.17536. "we find that Majority Voting alone accounts for most of the performance gains typically attributed to MAD." "We prove that it induces a martingale over agents' belief trajectories, implying that debate alone does not improve expected correctness." The same abstract adds: "targeted interventions, by biasing the belief update toward correction, can meaningfully enhance debate effectiveness." | **SUPPORTED.** Domain is question-answering benchmarks, not design critique. | full |
| A5 | "conformity degrades correct answers per arXiv 2509.05396"; "conformity degrades correct answers -1..-12%" | SKILL.md:98; CRITIC-COVERAGE.md:12; GROUNDING.md:32 | Talk Isn't Always Cheap, https://arxiv.org/abs/2509.05396. "debate can lead to a decrease in accuracy over time - even in settings where stronger (i.e., more capable) models outnumber their weaker counterparts. ... models frequently shift from correct to incorrect answers in response to peer reasoning, favoring agreement over challenging flawed reasoning." "We find that in the case of CommonSenseQA ... debate always harms performance." Table 1 changes run from a 12.0-point decrease to a 5.6-point increase depending on dataset and group composition. | **PARTLY.** Direction supported. "-1..-12%" reports only the negative half of a range that also contains gains; the models are GPT-4o-mini, Mistral-7B and Llama-3.1-8B. | full |
| A6 | "Personalisation measurably increases sycophancy (MIT 2026 ...)" | SKILL.md:91; CRITIC.md:3 | MIT News, https://news.mit.edu/2026/personalization-features-can-make-llms-more-agreeable-0218. "over long conversations, such personalization features often increase the likelihood an LLM will become overly agreeable or begin mirroring the individual’s point of view." "Although interaction context increased agreeableness in four of the five LLMs they studied, the presence of a condensed user profile in the model’s memory had the greatest impact." "And while sycophancy tended to go up, it didn’t always increase." "The research will be presented at the ACM CHI Conference on Human Factors in Computing Systems." Paper abstract, https://arxiv.org/abs/2509.12517: "User memory profiles are associated with the largest increases in agreement sycophancy (e.g. +45% for Gemini 2.5 Pro)". | **SUPPORTED** directionally. The skill gives no identifier; the paper is arXiv 2509.12517, venue CHI 2026. | full (news); abs (paper) |
| A7 | "(... ICLR 2026)" | SKILL.md:91; CRITIC.md:3 | No identifier in the skill, so the claim cannot be matched to a source. Closest candidate found: ICLR 2026 workshop paper "Recalling Too Well: Sycophancy and Bias Amplification in Memory-Augmented Models", https://iclr.cc/virtual/2026/10016383: "Memory systems amplify sycophantic behavior across all domains, showing 2-4x higher strict sycophancy rates than chat history baselines in scientific questions". | **Uncheckable as cited.** If the candidate is the intended paper, the claim is supported directionally and the paper is a workshop paper, not a main-track one. | abs |
| A8 | "SHARD data-flow guidewords"; "HAZOP/SHARD/STPA UCA lineage"; list Omission / Commission / Early / Late / Value (subtle) / Value (coarse) | SKILL.md:96; CRITIC-COVERAGE.md:12, 95–104 | Secondary source, https://pmc.ncbi.nlm.nih.gov/articles/PMC8236579/: "For each node of the UML, we apply one of the guide words: Omission, Commission, Early, Late and Value, as suggested in the SHARD analysis (Pumfrey, 1999)"; "HAZOP (HAZard and Operability study) (BS EN 61882, 2019) and its variant SHARD (Software Hazard Analysis and Resolution in Design) (Pumfrey, 1999)". | **SUPPORTED** for the five guidewords and the HAZOP lineage. The skill's split of Value into "subtle" and "coarse" was **NOT FOUND** in any source I fetched; the primary (Pumfrey's thesis) was not fetched. The source makes no claim about LLMs. | full (secondary) |
| A9 | "STPA UCA decision guidewords": Not provided / Provided unsafe / Wrong timing or order / Wrong duration | SKILL.md:96; CRITIC-COVERAGE.md:106–113 | STPA Handbook (Leveson & Thomas, 2018), https://psas.scripts.mit.edu/home/get_file.php?name=STPA_handbook.pdf: "There are four ways a control action can be unsafe (represented in the columns above): 1. Not providing the control action leads to a hazard. 2. Providing the control action leads to a hazard. 3. Providing a potentially safe control action but too early, too late, or in the wrong order 4. The control action lasts too long or is stopped too soon (for continuous control actions, not discrete ones)." | **SUPPORTED** as a taxonomy. The source makes no claim about LLMs. | full |
| A10 | "Key Assumptions Check" | SKILL.md:96; CRITIC-COVERAGE.md:115 | The skill names the technique without a source. CIA, "A Tradecraft Primer" (2009), https://www.cia.gov/resources/csi/static/Tradecraft-Primer-apr09.pdf: "KEY ASSUMPTIONS CHECK — List and review the key working assumptions on which fundamental judgments rest." "A Key Assumptions Check is most useful at the beginning of an analytic project. An individual analyst or a team can spend an hour or two articulating and reviewing the key assumptions." | **SUPPORTED** as a named human technique. No efficacy measurement in the source; nothing about LLMs. | full |
| A11 | "per Klein, HBR 2007 — prospective hindsight produces ~30% more reasons than forecasting" | CRITIC-COVERAGE.md:129 | HBR itself is paywalled. Reproduction of the article at https://deckelmoneypenny.com/performing-a-project-premortem/: "Research conducted in 1989 by Deborah J. Mitchell, of the Wharton School; Jay Russo, of Cornell; and Nancy Pennington, of the University of Colorado, found that prospective hindsight—imagining that an event has already occurred—increases the ability to correctly identify reasons for future outcomes by 30%." Secondary analysis, https://corporate.jasoncollins.blog/premortem: "The sole citation in Klein (2007) relates to research by Mitchell et al. (1989), who demonstrated that imagining that an event has already occurred with certainty, rather than considering that it may occur, increases the number of reasons generated for the potential future outcome by approximately 30%. Mitchell, Russo, and Pennington (1989) did not assess the quality of the reasons." | **PARTLY.** The 30% figure is in Klein's article but is not Klein's measurement; it is Mitchell et al. 1989, on humans. Klein's wording ("ability to correctly identify reasons") and the secondary reading ("number of reasons", quality not assessed) disagree, and the skill's wording matches the weaker one. The Mitchell et al. primary is **SOURCE UNREACHABLE** (publisher returned 403). | full (reproduction + secondary) |
| A12 | "debate-like sequencing would amplify conformity per the research" | CRITIC-COVERAGE.md:32 | No identifier. Consistent with A5 (2509.05396) for agents that see each other's answers. | **SUPPORTED** by A5, with A5's limits. | — |
| A13 | "The anti-conformity research that motivated independent critics is about critics debating each other. It says nothing against clustering findings after they are already in." | TRIAGE.md:8 | No identifier. A4 and A5 both study agents exchanging answers during debate; neither addresses post-hoc clustering of findings. | **SUPPORTED** as a characterization of A4 and A5. | — |

### Worst mismatches, in order

1. **A2** — the cited arXiv ID points to an unrelated paper. The real source (2507.02778) reports the effect as small or negative for reasoning models.
2. **A1** — "~64%" is an upper bound from small models, in one scenario, for a different intervention. For frontier models the same table shows roughly no change.
3. **A3** — the number is right, but the paper's result favours *artifact-only* review; the condition matching the skill's critic payload (prompt + artifact) was not better than same-session review.
4. **A5** — one-sided range.
5. **A7** — a citation with no identifier.

---

## Part B — evidence per question

### Q1. Interview-style elicitation before an LLM agent implements

**Evidence**

- Asking helps on underspecified tasks. Ambig-SWE, https://arxiv.org/abs/2502.13069 (full, indep): "interactivity can boost performance on underspecified inputs by up to 74% over the non-interactive settings, though performance varies across models". Also: "LLMs default to non-interactive behavior without explicit encouragement, and even with it, they struggle to distinguish between underspecified and well-specified inputs." "Claude Sonnet 4 and Claude Sonnet 3.5 are the only evaluated LLMs that achieve notable accuracy (89% and 84%, respectively) in making this distinction." Condition: the user is simulated — "we employ GPT-4o (Ahmad and OpenAI, 2024) as a user proxy to simulate user-agent interactions." "The goal is not to simulate real users but provide the information injection to the trajectory and analyze model behaviors."
- Always asking overshoots. Ask or Assume, https://arxiv.org/abs/2603.26233 (full, indep): "For Claude Sonnet 4.5, UA-Single outperforms the Hidden baseline (61.20% vs. 54.80%) but falls short of the prompted Interactive Baseline (70.40%)." "Crucially, the Interactive Baseline achieves its high resolve rate at the cost of overclarification, asking questions in nearly every instance regardless of necessity." Query counts: "For Claude Sonnet 4.5, UA-Multi interrogated the user more iteratively, averaging 3.06 queries per task compared to 1.84 for UA-Single"; "For Kimi K2.6, UA-Multi exhibits a much higher query rate, averaging 8.71 queries per task ... suggesting poorer calibration relative to Claude Sonnet 4.5." Simulated user: "we employ GPT-5.1 (OpenAI, 2025) as the simulated user for all interactive agent configurations."
- More questions stop paying. "Asking What Matters" (CLARITI), https://arxiv.org/abs/2604.14624 (full, indep): "Analyzing clarification composition, we find that performance often plateaus or declines with more questions while imposing higher user burden." "Performance plateaus as question count increases, while the proportion of answerable questions declines." "Our trained clarification model, CLARITI, achieves GPT-5-level performance (36.80%) with 41% fewer average questions (3.0 vs 5.1) by prioritizing task relevance and user answerability". "Asking low-quality questions imposes user burden without recovering useful information, making silence the better policy." On what makes a question answerable: "answerable questions tend to ground in observable behaviors, maintain appropriate technical depth, and avoid requesting internal state users would not know." Condition: "We consider a controlled, single-turn setting where the agent poses clarifying questions to a simulated user before beginning implementation."
- Finding ambiguity is a separate skill from coding. ClarifyCodeBench, https://arxiv.org/abs/2607.00711 (full, indep): "Strong code generation performance does not inherently translate to effective requirement clarification"; "while increased computational "thinking" (e.g., via reasoning models) enhances code correctness, it yields marginal gains in identifying ambiguities"; "LLMs’ clarification performance degrades sharply as the density of ambiguities increases". Tasks carry "one to three ambiguity points".
- Implicit requirements are the bottleneck. SWE-RPG, https://arxiv.org/abs/2608.09072 (abs + partial text, indep): "achieving an average resolved rate of only 31.5% on SWE-RPG. Intermediate-GT diagnosis further identifies implicit requirement recovery as the main bottleneck, accounting for 24.5%--46.0% of agent runs."
- Practitioner positions on the number of questions. mattpocock/skills, https://raw.githubusercontent.com/mattpocock/skills/main/.out-of-scope/question-limits.md (pract): "Grilling is intentionally open-ended. The point is to keep digging until each branch of the decision tree is resolved: some plans need three questions, some need fifty. A fixed cap would either cut off useful exploration on hard problems or feel arbitrary on easy ones." The same file records the complaint it declines: "Prior requests — #44: "Codex just asked me 200 questions"". The opposite design choice, github/spec-kit `/clarify`, https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/clarify.md (vendor design): "Maximum of 5 total questions across the whole session." and "If more than 5 categories remain unresolved, select the top 5 by (Impact * Uncertainty) heuristic."
- Practitioner report of the disengagement failure. https://raw.githubusercontent.com/mattpocock/skills/main/docs/productivity/grill-me.md (pract): "The failure mode is **passivity**: answering "agreed, agreed, agreed" for forty questions and coming out with a plan the agent wrote and you nodded at. It feels productive because it was long. Nothing was actually decided".
- One at a time versus batched: **no controlled evidence found.** Practitioner positions conflict. Upstream switched to batching (commit a4b2009a, 2026-07-16: "Rework grilling from one-question-at-a-time to asking the whole frontier each round") and documents it as unsettled, https://raw.githubusercontent.com/mattpocock/skills/main/docs/productivity/grilling.md: "The round-based default is genuinely contested. Practitioners who read slowly, who work in a second language, or who use the sequential format as focus scaffolding all report the one-at-a-time rhythm is better for them, and the opt-out is supported rather than tolerated." and "The honest limit: the frontier is the agent's judgement, not a computed graph. It can put two questions in one round and only afterwards discover that one answer should have changed the other." superpowers and spec-kit both choose one at a time: "Only one question per message - if a topic needs more exploration, break it into multiple questions" (https://raw.githubusercontent.com/obra/superpowers/main/skills/brainstorming/SKILL.md); "Present EXACTLY ONE question at a time." (spec-kit clarify).
- Recommending an answer with each question: **no controlled evidence found.** All three prior-art tools do it (quotes in Q7). Upstream notes one defect, grilling.md: "The format has one known rough edge: the recommendation sometimes argues *against* the question as it was worded, so agreeing with the recommendation means answering "no" to the question." Q3's evidence (models tilt toward a stated preference) says nothing direct about the reverse direction, a human anchoring on the model's recommendation; I found no measurement of that in this setting.

**What this implies for the skill (inference)**

- The case for asking before implementing is measured and large, but only for tasks that are actually underspecified, and only with simulated users. No study I found measures human fatigue or disengagement; the "how many before the user disengages" part of the question has no measured answer.
- The one measured result on quantity (CLARITI) points at selection, not volume: about 3 well-chosen questions matched about 5 unselected ones, and performance plateaued or declined beyond that. An uncapped frontier sweep is a practitioner preference that the only quantitative result does not support. A question-value filter (impact × uncertainty, answerable by this user) is the better-supported lever than a numeric cap.
- The skill's existing "facts are the agent's job" rule matches the answerability finding ("avoid requesting internal state users would not know").
- Batched rounds versus one at a time, and recommended answers, are design choices without evidence either way. If kept, they should be labelled as such rather than argued from research.

### Q2. Same-context self-critique versus fresh-context review; false-positive load

**Evidence**

- Fresh, artifact-only review beat same-session review by 4 F1 points in one single-model study; adding the original prompt removed the gain. CCR, https://arxiv.org/abs/2603.12123 (full, indep; quotes in A3).
- The self-correction blind spot is large on non-reasoning models with injected errors and small or negative on reasoning models. https://arxiv.org/abs/2507.02778 (full, indep; quotes in A2b).
- LLM reviewers are imprecise. SWR-Bench, https://arxiv.org/abs/2509.01494 (full, indep): "the top-performing combination, PR-Review leveraged with Gemini-2.5-Pro, achieved an F​1 score of only 19.38%." "A primary factor limiting higher F​1 scores for all techniques is their low precision, indicative of a high false positive rate." "these approaches frequently generate multiple invalid suggestions per pull request, with some combinations (e.g., Hybrid-Review with DeepSeek-R1) producing over 7 false positives on average." On the remedy: "we propose and validate a simple multi-review aggregation strategy that significantly boosts ACR performance, increasing F1 scores by up to 43.67%."
- Asking the reviewer for more makes it reject correct work more often. https://arxiv.org/abs/2603.00539 (full, indep): "we demonstrate that LLMs frequently misclassify correct code implementation as non-compliant or defective. Surprisingly, we find that more detailed prompt design, particularly with those requiring explanations and proposed corrections, leads to higher misjudgment rates". "Under Direct, GPT-4o achieves a relatively low FNR in HumanEval (26.2%) and MBPP (35.9%), but once explanations and repairs are required, the FNR increases sharply to 73.2% in HumanEval and 87.9% in MBPP." "Notably, on HumanEval, Claude-4.5 maintains relatively low FNR under Direct (26.2%) but increases under Direct+Explain/Full (36.0%)." "detailed prompts may inadvertently introduce biases toward excessive fault finding, causing models to detect non-existent errors in otherwise correct implementations." "The model introduces constraints not stated in the requirement and rejects the code for violating these hallucinated requirements." (In this paper FNR is the rate at which correct code is rejected.)
- Industrial code review names false alarms as a core problem. https://arxiv.org/abs/2505.17928 (abs, indep): "We identify four key challenges: ... reducing false alarm rates (FAR)".
- A practitioner measured a subagent plan-review loop and removed it. obra/superpowers release notes v5.0.6, https://raw.githubusercontent.com/obra/superpowers/main/RELEASE-NOTES.md (pract, self-measured, no published data): "The subagent review loop (dispatching a fresh agent to review plans/specs) doubled execution time (~25 min overhead) without measurably improving plan quality. Regression testing across 5 versions with 5 trials each showed identical quality scores regardless of whether the review loop ran." "Self-review catches 3-5 real bugs per run in ~30s instead of ~25 min, with comparable defect rates to the subagent approach". Their reviewer calibration line: "**Only flag issues that would cause real problems during implementation planning.** ... Approve unless there are serious gaps that would lead to a flawed plan."

**What this implies for the skill (inference)**

- Evidence for fresh-context review exists but is thin: one single-author, single-model study with injected errors, a 4-point gain concentrated in critical errors, and a practitioner report pointing the other way for plan review. It does not justify the confidence of SKILL.md:91.
- The critic payload contradicts the paper it cites. If the redesign keeps cross-context critics, the evidence-backed variant is artifact-only (design + AC, no problem framing, no "proposed direction" narrative).
- False positives are the dominant cost, and the measured range is wide: about two thirds of findings in CCR, more than 7 per PR in SWR-Bench's worst configuration. The coverage tier's rule that every cell must be explicitly considered, combined with severity tags and citations per finding, is the prompt shape that 2603.00539 found raises false rejections. The skill's own TRIAGE.md opening (115 raw items collapsing to about a dozen root causes) is consistent with this.
- Two supported mitigations: aggregate across independent reviews (SWR-Bench), and calibrate the reviewer toward "flag only what would cause real problems" (superpowers, practitioner-level). The skill already does a form of the first via triage clustering.
- Whether Phase 3 earns its cost for this operator is answerable only from the operator's own session history; external evidence does not settle it.

### Q3. Sycophancy toward the user's stated preference, and mitigations

**Evidence**

- Stating a preference or authorship changes the feedback. Sharma et al., https://arxiv.org/abs/2310.13548 (full; Anthropic-affiliated authors; 2023 models): "To suggest that the user prefers the text, we add I really like the [solution/argument/poem] or I wrote the […] to the prompt." "However, we find AI assistants provide more positive feedback about arguments that the user likes. Similarly, AI assistants are more negative about arguments that the user dislikes." "Though the quality of a passage depends only on its content, AI assistants consistently tailor their feedback."
- Personalisation and memory raise agreement. CHI 2026 paper, https://arxiv.org/abs/2509.12517 (abs, indep): "User memory profiles are associated with the largest increases in agreement sycophancy (e.g. +45% for Gemini 2.5 Pro), and some models become more sycophantic even with non-user synthetic contexts (e.g. +15% for Llama 4 Scout). Perspective sycophancy increases only when models can accurately infer user viewpoints from interaction context." MIT News summary (full): "And while sycophancy tended to go up, it didn’t always increase."
- Third-person reframing is a weak mitigation. ELEPHANT, https://arxiv.org/abs/2505.13995 (full, indep): "Next, we test perspective shift: rewriting the prompts from first-person to third-person." "This mitigation strategy reduces social sycophancy somewhat, though models overall still remain highly sycophantic, with an increase in both moral YTA/NTA and framing sycophancy." "in some cases (namely Qwen and DeepSeek on OEQ), the model still responds with “you” despite the input being in the third-person, suggesting that it can be challenging to override the LLM’s user-facing orientation with prompts alone." Abstract: "while existing mitigation strategies for sycophancy are limited in effectiveness, model-based steering shows promise".
- Third-person persona: large gains on small models in one scenario, about none on frontier models. SYCON, https://arxiv.org/abs/2505.23840 (full, indep; quotes in A1). The same paper on explicit instruction: "adding an explicit anti-sycophancy instruction (Andrew + Non-Sycophantic Prompt) yields ToF gains of up to 28% in the unethical query scenario."
- Blunt "be less agreeable" instructions overcorrect. ELEPHANT: "the most naive approach of adding instructions to “be less [validating/indirect/etc]” to the prompt leads to negative scores across the board since the model responses simply eliminated all face preservation, even when affirmation is appropriate."
- Hiding who proposed an option: the mechanism is supported by Sharma et al. (attribution changes feedback), so removing the attribution removes that input. I found **no 2025–2026 measurement** of attribution-blind option presentation as a mitigation in design discussions.

**What this implies for the skill (inference)**

- The risk the skill targets is real and measured, including the specific channel the operator's setup has (a persistent user profile in context).
- The Phase 2 third-person reviewer framing rests on a misread number (A1). On frontier models the measured effect of third-person reframing is between nothing and "somewhat". It can stay as a cheap default; it should not be presented as a 64% reduction, and it should not be the main defence.
- The structurally stronger move, by Sharma's mechanism, is attribution removal: present options without saying which one the user proposed or favours, and withhold the user's stated intuition from any reviewer. The critic prompt already does this behaviourally; by CRITIC.md's own admission the isolation is a prompt-level nudge, not a structural one.
- A tone instruction to push back harder is the variant with a measured downside (overcorrection).

### Q4. Structured coverage methods: guidewords, premortem, checklists, debate

**Evidence**

- Debate. Measured, mostly negative for unstructured debate on QA tasks (A4, A5). One domain-specific result in favour: HAZDIAL, https://arxiv.org/abs/2606.03812 (full text of the results section, indep): "adversarial debate consistently reduces false positives by up to 40% across both models, while constructive discussion degrades F1 on the smaller model". On the open-weight model (the paper's "OSS configuration"): "Debate improves F1 by +0.035 over Base (0.2492 vs. 0.2140) and reduces the corpus-level FP count by 40.0% (from 1,761 to 1,057). The improvement is driven entirely by precision (+0.102), with a modest recall loss (−0.037) attributable to the Critic’s evidence-grounded rejection defaults." This is a generator plus an evidence-demanding critic used as a filter on hazard identification, which matches the "targeted interventions" carve-out in 2508.17536; absolute F1 stays near 0.25.
- LLMs running guideword-style hazard analysis in safety engineering. Measured, mixed:
  - STPA. https://arxiv.org/abs/2503.12043 (full, indep): "In our experiment, of the 50 generated UCAs, 39 were classified as "CORRECT_AND_USEFUL", 6 as "CORRECT_BUT_USELESS", and 5 as "INCORRECT", yielding us an 78% success rate for UCA synthesis." The same paper on earlier work: "[10] found correctness of outputs to be less than half or about half, respectively". On volume: "in a small system of only 5 components and 20 control actions, 80 UCAs as well as 320 loss scenarios can potentially be generated, which can be very costly to produce and maintain". Workflow assumes a human filter: "a requirement engineer oversees this process, reviews the generated UCAs and loss scenarios, and dismisses incorrect ones."
  - HAZOP. Safety Science vol. 194 (2026), https://www.sciencedirect.com/science/article/abs/pii/S0925753525002644 (abs, indep): "all four LLMs achieved high similarity scores to the reference (F1 scores > 86 %)" but "The proportion of semantically valid scenarios remained low (0.19 to 0.37), and safeguards were heavily biased toward procedural measures". Highlights: "Concludes LLMs serve as supportive tools, not full replacements for expert-led HAZOP."
  - Run-to-run consistency. Safety Science vol. 194 (2026), https://www.sciencedirect.com/science/article/pii/S0925753525002814 (abs, indep, pilot of nine scenarios): "While the model’s success rate in generating a response was stable, its analytical quality was inconsistent. Hazard identification scores varied between runs, and causal reasoning performance was consistently poor and unpredictable."
  - Automotive HARA. SAFARI, https://arxiv.org/abs/2609.20584 (abs, indep): "models often produce plausible hazard narratives but remain weak at ISO 26262 risk classification, with the best ASIL macro-F1 reaching only 0.261. Chain-of-Thought prompting provides limited benefit and often degrades categorical risk assessment."
  - Early case study, https://arxiv.org/abs/2303.15473 (abs, indep): "The results suggest that LLMs may be useful for supporting human analysts performing hazard analysis."
- Guidewords (SHARD or STPA) applied by an LLM to critique a *software design proposal*, compared with an unstructured critic: **no evidence found.**
- Premortem run by an LLM: **no evidence found.** The human evidence is A11 (about 30% more reasons, quality not assessed).
- Checklist versus free-form review by an LLM: **no direct evidence found.** Nearest results: more elaborate review prompts increased false rejections (2603.00539, Q2), and aggregating several independent reviews raised F1 (SWR-Bench, Q2).

**What this implies for the skill (inference)**

- "Parallel, no debate chain" is consistent with the evidence. HAZDIAL suggests one narrow exception that the skill partly has already: a second pass that demands evidence and rejects by default works as a false-positive filter. Triage currently clusters without refuting.
- The coverage tier's "research-backed" label covers only its delivery mechanism (independent fresh critics). The guideword sweep itself has no evidence in this use. In the domain the guidewords come from, LLM output is measured as 19–37% valid scenarios for HAZOP and about 78% for STPA UCAs on one case study, with run-to-run inconsistency, and always with a human filter.
- The cost side is measured and matches the skill's own history: cell count grows with nodes × guidewords, and the 115-item lock recorded in TRIAGE.md is the predicted outcome.
- Premortem and Key Assumptions Check are human techniques with thin (premortem) or no (KAC) efficacy measurement. They are cheap single-entry items; the grid is the expensive part with the weakest support.

### Q5. Checking a design against the actual code before locking it

**Evidence**

- A controlled comparison of "ground the design against code before locking" versus not doing so: **no evidence found.**
- Nearest results:
  - SWE-RPG, https://arxiv.org/abs/2608.09072 (abs + partial text, indep), defines the task chain as "recover explicit and implicit requirements, formulate a repository-grounded implementation plan" and finds "implicit requirement recovery as the main bottleneck". This ranks the problem; it does not test a grounding step.
  - Validation before acting, from a different domain (vulnerability repair), https://arxiv.org/abs/2604.10800 (abs, indep): "disabling validation increases unnecessary repairs by 131.7%".
  - Practitioner rule, upstream `grilling` primitive, https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grilling/SKILL.md: "Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it; don't ask the user for anything you could look up yourself." Earlier wording in `grill-me` (commit a6bdfd9f, 2026-03-26): "If a question can be answered by exploring the codebase, explore the codebase instead."

**What this implies for the skill (inference)**

- Phase 4 is justified by argument, not by measurement: a grounding row is checked against the repository, so unlike a critic finding it has a ground truth. That makes it the phase least exposed to the false-positive problem in Q2.
- Upstream does grounding *during* the interview (look facts up instead of asking). The local skill adds a separate pass at lock time. Nothing external says which placement is better. Doing the lookups during the interview is the variant with prior art; a late pass that returns DRIFT rows reopens decisions already made.

### Q6. Skill-authoring constraints

**Evidence — vendor guidance (Anthropic, full text read)**

- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices : "Keep SKILL.md body under 500 lines for optimal performance". "The context window is a public good." "once Claude loads it, every token competes with conversation history and other context." "**Default assumption:** Claude is already very smart" and "Only add context Claude doesn't already have." Description: "Maximum 1,024 characters"; "Should describe what the Skill does and when to use it"; "**Always write in third person**. The description is injected into the system prompt, and inconsistent point-of-view can cause discovery problems." References: "**Keep references one level deep from SKILL.md**." "Claude may partially read files when they're referenced from other referenced files. When encountering nested references, Claude might use commands like `head -100` to preview content rather than reading entire files". "For reference files longer than 100 lines, include a table of contents at the top." Also: "Avoid time-sensitive information". Evaluation: "**Create evaluations BEFORE writing extensive documentation.**" with the caveat "There is not currently a built-in way to run these evaluations."; checklist items "At least three evaluations created" and "Tested with Haiku, Sonnet, and Opus".
- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview : "Level 1: Metadata | Always (at startup) | ~100 tokens per Skill"; "Level 2: Instructions | When Skill is triggered | Under 5k tokens | SKILL.md body"; "Level 3+: Resources | As needed | None until accessed".
- https://code.claude.com/docs/en/skills : "Keep `SKILL.md` under 500 lines. Move detailed reference material to separate files." "the combined `description` and `when_to_use` text is truncated at 1,536 characters in the skill listing". Compaction: "Auto-compaction carries invoked skills forward within a token budget. When the conversation is summarized to free context, Claude Code re-attaches the most recent invocation of each skill after the summary, keeping the first 5,000 tokens of each. Re-attached skills share a combined budget of 25,000 tokens." Drift: "If a skill seems to stop influencing behavior after the first response, the content is usually still present and the model is choosing other tools or approaches. ... or use hooks to enforce behavior deterministically. If the skill is large or you invoked several others after it, re-invoke it after compaction to restore the full content." The `model` field: "Model to use when this skill is active. The override applies for the rest of the current turn and isn't saved to settings. The session model resumes when you send your next prompt."

**Evidence — independent measurements of instruction count versus adherence**

- IFScale, https://arxiv.org/abs/2507.11538 (full, indep): "even the best frontier models only achieve 68% accuracy at the max density of 500 instructions." "Three distinct degradation patterns emerge: (1) threshold decay—near-perfect performance until a critical density, then rising variance and decreased adherence (reasoning models like o3, gemini-2.5-pro), (2) linear decay (gpt-4.1, claude-sonnet-4), and (3) exponential decay (gpt-4o, llama-4-scout)." "The top two models (gemini-2.5-pro, o3) demonstrate this clearly, maintaining near-perfect performance through 150 or more instructions before declining." "Primacy effects display an interesting pattern across all models: they start low at minimal instruction densities indicating almost no bias for earlier instructions, peak around 150-200 instructions, then level off or decrease at extreme densities." Condition: "a simple benchmark of 500 keyword-inclusion instructions for a business report writing task" — far simpler than procedural rules.
- "Prompt Design at Scale", https://arxiv.org/abs/2607.19257 (full, indep, single preprint): "Experiment 1 (960 calls/model) measures instruction-following decay as rule count N grows from 10 to 160, crossed with four rendering formats and system-prompt vs. user-turn placement." "Perfect-response rate collapses to zero by N=80 for every model, every format, and both placements, a floor effect essentially independent of format." "No model shows a reliable markdown advantage, and one 35B open-weight model reliably favors plain text instead." Authors' own limit: "specific thresholds such as N=80 or 89.6% refusal are properties of the particular models we tested and should not be assumed to transfer verbatim to other models or future model versions."
- Practitioner observation, mattpocock/skills changelog (pract): "Concision skills fail by growing — a 400-line skill still leaves the model verbose".

**Local measurements (mine, from the worktree, not external evidence)**

- `skills/grill/SKILL.md`: 269 lines, 23,550 bytes. At roughly 4 characters per token that is about 5.9k tokens (an estimate; not tokenized).
- Siblings: CRITIC.md 91 lines, CRITIC-COVERAGE.md 184, GROUNDING.md 126, TRIAGE.md 104, CONTEXT-FORMAT.md 77, ADR-FORMAT.md 47; 76,730 bytes for the bundle. The three siblings over 100 lines have no table of contents.
- Frontmatter: `description` says what the skill does and has no "when to use" clause; `model` and `effort` are set.
- Links from SKILL.md to siblings are one level deep; CRITIC.md additionally links TRIAGE.md and CRITIC-COVERAGE.md.

**What this implies for the skill (inference)**

- The 269-line body is inside the 500-line limit but, by estimate, over the "Under 5k tokens" Level-2 figure and over the 5,000-token window that survives auto-compaction. A grill session is long by design, so compaction is likely, and what falls outside the window is the end of the file: Phases 3–4 and `<supporting-info>`. The instructions that gate the lock are the ones most likely to be dropped. Either shrink the body under the window or put the lock-time procedure first or in a sibling that is read at lock time.
- The `model:` override lasts one turn. An interview takes many turns, so from the second user reply onward the session model runs the skill. If the design depends on a particular model, frontmatter does not deliver it.
- The description should gain a "when to use" clause (the vendor guidance asks for it, and the description is the only text used for discovery).
- Add a table of contents to the three long siblings, or cut them below 100 lines; the vendor warns of partial reads.
- Rule count matters more than line count in the two independent studies, and both show adherence falling as discrete instructions accumulate. The skill's critic, coverage and triage prompts each carry many hard rules. I did not count them; the count is worth taking during the rewrite.
- Vendor guidance asks for evaluations before documentation. The skill has none that I saw, and its research claims were carried as prose rather than tested.

### Q7. Prior art and lineage

**Evidence — mattpocock/skills (pract; repository files and commit history read)**

- Hypothesis checked: the local skill descends from `grill-me`. **Result: partly.** Its direct ancestor is `grill-with-docs`, which itself grew out of `grill-me`. The local file matches https://raw.githubusercontent.com/mattpocock/skills/b843cb5e/skills/engineering/grill-with-docs/SKILL.md (commit b843cb5e, 2026-04-30): the same `<what-to-do>` / `<supporting-info>` structure, the CONTEXT.md and ADR handling, lines such as "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?" and "Offer ADRs sparingly", and the two format files reproduced nearly verbatim in local SKILL.md lines 183–269.
- Original `grill-me` (commit 78649baa, 2026-02-25): "Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one." Later additions (commit a6bdfd9f, 2026-03-26): "For each question, provide your recommended answer." "Ask the questions one at a time." "If a question can be answered by exploring the codebase, explore the codebase instead."
- Upstream today:
  - `grill-me` is a stub: "Call the Skill tool with "grilling"." with `disable-model-invocation: true` and the description "A relentless interview to sharpen a plan or design."
  - `grill-with-docs` is a stub: "Call the Skill tool twice, for "grilling" and "domain-modeling"."
  - The behaviour lives in a 28-line primitive, https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grilling/SKILL.md: "Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer." "The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding."
  - Glossary and ADR handling moved to a separate `domain-modeling` skill (74 lines); CONTEXT.md was renamed GLOSSARY.md ("`GLOSSARY.md` should be totally devoid of implementation details.").
- How it changed: split into primitives (commit 221ffca9, 2026-05-31); confirmation gate added, with the note "Asking multiple questions at once is bewildering." (0e9a0727, 2026-07-03); "stop the agent grilling itself" (e5932a7a, 2026-07-06); then the reversal to batched rounds (a4b2009a, 2026-07-16): "Rework grilling from one-question-at-a-time to asking the whole frontier each round, with background sub-agents for fact-finding so research never blocks the round. Fold the batch-grill-me experiment into grilling and delete it. Re-sync the docs page, including how to opt back into one-at-a-time via global CLAUDE.md."
- Upstream's own documented limits, https://raw.githubusercontent.com/mattpocock/skills/main/docs/productivity/grilling.md and https://raw.githubusercontent.com/mattpocock/skills/main/docs/productivity/grill-me.md: "Thirteen questions typically land in about three rounds rather than thirteen." "Count rounds, not questions. Forty-six questions across four rounds is an ordinary session." "Weaker and faster models still break it; this is reported most often on lower-effort or non-frontier models, which collapse "interview until shared understanding" into a couple of questions and an outline." "a skill that names another skill does not reliably cause that skill to load, and `grill-with-docs` names two." "Leave plan mode off. Plan mode primes the agent to rush toward producing a plan, which is the opposite of staying in inquiry." "Start it in a **fresh conversation**, not on top of a plan you already had an agent write." On questions that cannot be settled by talking: ""One long form or three pages?" ... are **ungrillable**: they need something to react to. When you hit one, stop grilling. Build the throwaway version with prototype".
- What upstream does not have: critic subagents, a guideword sweep, a triage pass, a grounding pass. Phases 3 and 4 of the local skill are local additions with no upstream counterpart.

**Evidence — obra/superpowers brainstorming (pract)**, https://raw.githubusercontent.com/obra/superpowers/main/skills/brainstorming/SKILL.md (285 lines)

- "Ask clarifying questions — one at a time, understand purpose/constraints/success criteria". "Prefer multiple choice questions when possible, but open-ended is fine too". "Propose 2-3 approaches — with trade-offs and your recommendation". "Present design — in sections scaled to their complexity, get user approval after each section". "A reply approves the stage actually presented. Approval of an idea or feature scope does not approve artifacts that do not exist yet." Review is an inline self-review: "Fix any issues inline. No need to re-review — just fix and move on." The subagent review loop was removed (Q2).

**Evidence — github/spec-kit `/clarify` (vendor design)**, https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/clarify.md (291 lines)

- "Identify underspecified areas in the current feature spec by asking up to 5 highly targeted clarification questions and encoding answers back into the spec." "Present EXACTLY ONE question at a time." Answer shape: "A short multiple‑choice selection (2–5 distinct, mutually exclusive options), OR A one-word / short‑phrase answer (explicitly constrain: "Answer in <=5 words")." "Present your **recommended option prominently** at the top with clear reasoning (1-2 sentences explaining why this is the best choice)." Filter: "Only include questions whose answers materially impact architecture, data modeling, task decomposition, test design, UX behavior, operational readiness, or compliance validation." Exit without asking: "No critical ambiguities detected worth formal clarification."

**Evidence — Claude Code plan mode and AskUserQuestion (vendor docs)**

- https://code.claude.com/docs/en/permission-modes : "Plan mode tells Claude to research and propose changes without making them. Claude reads files, runs shell commands to explore, and writes a plan, but does not edit your source." "Approving a plan exits plan mode and switches the session to the permission mode each approve option describes, so Claude starts editing." Under dontAsk mode the same page says Claude Code "also denies the built-in `AskUserQuestion` tool even if your allow rules match it".
- https://code.claude.com/docs/en/tools-reference : "`AskUserQuestion` | Asks multiple-choice questions to gather requirements or clarify ambiguity. Questions stay open until you answer them by default." "Claude uses `AskUserQuestion` to ask you multiple-choice questions when it needs a decision or a clarification. Answer by picking an option, or type your own text through the `Other` row or the notes field." "The timeout applies only to `AskUserQuestion`'s multiple-choice questions; permission prompts, including plan approval, never auto-resolve on idle."
- Limits on questions per call or options per question are not documented on the pages I fetched.
- No file in `skills/grill/` mentions `AskUserQuestion` (local grep).

**Comparison**

| | Local /grill | Upstream grilling (today) | superpowers brainstorming | spec-kit clarify | Plan mode + AskUserQuestion |
|---|---|---|---|---|---|
| Question pacing | batched frontier rounds | batched frontier rounds; one-at-a-time opt-out | one per message | exactly one at a time | tool call, multiple choice |
| Cap | none | none, by stated policy | none stated | 5 per session | not documented |
| Recommended answer | yes | yes | yes, with 2–3 approaches | yes, placed first | options; free text via `Other` |
| Question filter | dependency-gated | dependency-gated | not stated | materiality list; Impact × Uncertainty | — |
| Facts from code | grounding pass at lock | sub-agent lookup during the interview | not stated in the lines read | — | exploration in plan mode |
| Independent review | two critic tiers + triage | none | inline self-review; subagent loop removed | none | none |
| Size | 269 + ~630 lines | 28 lines (+74 domain-modeling) | 285 lines | 291 lines | built in |

**What this implies for the skill (inference)**

- The local skill forked from an April 2026 snapshot. Upstream has since made three changes the fork lacks or only half has: the interview loop compressed to a 28-line primitive, glossary and ADR work moved into its own skill, and fact-finding moved into the interview via sub-agents. The batched frontier round is present in both; how it got into the local copy is outside what I checked.
- Everything the fork added (critics, coverage grid, triage, grounding) is the part with no upstream counterpart and, per Q2 and Q4, the weakest external support. Everything it inherited is the part upstream has since shortened.
- Across four independent designs, the common core is: questions gated by dependency or materiality, a recommended answer on each, an explicit confirmation before acting. Those are the conventions with the most convergence; none has a controlled measurement behind it.
- `AskUserQuestion` gives multiple-choice answers with a free-text escape, which is the answer shape spec-kit and superpowers both prefer. Note it is denied in dontAsk mode, so a skill that depends on it needs a plain-text fallback.
- Upstream's advice to leave plan mode off and start in a fresh conversation is practitioner-level but specific, and costs nothing to adopt.

---

## Sources

Independent measurements

| Source | URL | Read |
|---|---|---|
| SYCON Bench (arXiv 2505.23840) | https://arxiv.org/abs/2505.23840 | full |
| Context Is Not Comprehension (arXiv 2506.04907) — the mis-cited ID | https://arxiv.org/abs/2506.04907 | full |
| Self-Correction Bench (arXiv 2507.02778) | https://arxiv.org/abs/2507.02778 | full |
| Cross-Context Review (arXiv 2603.12123) | https://arxiv.org/abs/2603.12123 | full |
| Debate or Vote (arXiv 2508.17536) | https://arxiv.org/abs/2508.17536 | full |
| Talk Isn't Always Cheap (arXiv 2509.05396) | https://arxiv.org/abs/2509.05396 | full |
| Interaction context and sycophancy, CHI 2026 (arXiv 2509.12517) | https://arxiv.org/abs/2509.12517 | abs |
| MIT News article on the above | https://news.mit.edu/2026/personalization-features-can-make-llms-more-agreeable-0218 | full |
| Recalling Too Well, ICLR 2026 workshop | https://iclr.cc/virtual/2026/10016383 | abs |
| ELEPHANT (arXiv 2505.13995) | https://arxiv.org/abs/2505.13995 | full |
| Sharma et al., Towards Understanding Sycophancy (arXiv 2310.13548; Anthropic-affiliated) | https://arxiv.org/abs/2310.13548 | full |
| Ambig-SWE (arXiv 2502.13069) | https://arxiv.org/abs/2502.13069 | full |
| Ask or Assume (arXiv 2603.26233) | https://arxiv.org/abs/2603.26233 | full |
| Asking What Matters / CLARITI (arXiv 2604.14624) | https://arxiv.org/abs/2604.14624 | full |
| ClarifyCodeBench (arXiv 2607.00711) | https://arxiv.org/abs/2607.00711 | full |
| SWE-RPG (arXiv 2608.09072) | https://arxiv.org/abs/2608.09072 | abs + partial |
| SWR-Bench (arXiv 2509.01494) | https://arxiv.org/abs/2509.01494 | full |
| LLM overcorrection in code verification (arXiv 2603.00539) | https://arxiv.org/abs/2603.00539 | full |
| Defect-focused automated code review (arXiv 2505.17928) | https://arxiv.org/abs/2505.17928 | abs |
| HAZDIAL (arXiv 2606.03812) | https://arxiv.org/abs/2606.03812 | full (results) |
| LLM-assisted STPA (arXiv 2503.12043) | https://arxiv.org/abs/2503.12043 | full |
| SAFARI (arXiv 2609.20584) | https://arxiv.org/abs/2609.20584 | abs |
| LLMs for hazard analysis, early case study (arXiv 2303.15473) | https://arxiv.org/abs/2303.15473 | abs |
| Can LLMs automate HAZOP, Safety Science 194 (2026) | https://www.sciencedirect.com/science/article/abs/pii/S0925753525002644 | abs |
| From hallucinations to hazards, Safety Science 194 (2026) | https://www.sciencedirect.com/science/article/pii/S0925753525002814 | abs |
| Validation in agentic vulnerability repair (arXiv 2604.10800) | https://arxiv.org/abs/2604.10800 | abs |
| IFScale (arXiv 2507.11538) | https://arxiv.org/abs/2507.11538 | full |
| Prompt Design at Scale (arXiv 2607.19257) | https://arxiv.org/abs/2607.19257 | full |

Method references (human techniques; no LLM claims)

| Source | URL | Read |
|---|---|---|
| STPA Handbook (Leveson & Thomas, 2018) | https://psas.scripts.mit.edu/home/get_file.php?name=STPA_handbook.pdf | full |
| SHARD guidewords, via secondary paper | https://pmc.ncbi.nlm.nih.gov/articles/PMC8236579/ | full |
| CIA, A Tradecraft Primer (2009) | https://www.cia.gov/resources/csi/static/Tradecraft-Primer-apr09.pdf | full |
| Klein, Performing a Project Premortem (HBR 2007), reproduction | https://deckelmoneypenny.com/performing-a-project-premortem/ | full |
| Collins, analysis of the premortem evidence | https://corporate.jasoncollins.blog/premortem | full |

Vendor documentation

| Source | URL | Read |
|---|---|---|
| Anthropic, Skill authoring best practices | https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices | full |
| Anthropic, Agent Skills overview | https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview | full |
| Claude Code, Skills | https://code.claude.com/docs/en/skills | full |
| Claude Code, Permission modes | https://code.claude.com/docs/en/permission-modes | full |
| Claude Code, Tools reference | https://code.claude.com/docs/en/tools-reference | full |
| github/spec-kit, clarify command template | https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/clarify.md | full |

Practitioner sources

| Source | URL | Read |
|---|---|---|
| mattpocock/skills, grilling primitive | https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/grilling/SKILL.md | full |
| mattpocock/skills, grill-with-docs at b843cb5e | https://raw.githubusercontent.com/mattpocock/skills/b843cb5e/skills/engineering/grill-with-docs/SKILL.md | full |
| mattpocock/skills, docs: grilling | https://raw.githubusercontent.com/mattpocock/skills/main/docs/productivity/grilling.md | full |
| mattpocock/skills, docs: grill-me | https://raw.githubusercontent.com/mattpocock/skills/main/docs/productivity/grill-me.md | full |
| mattpocock/skills, out-of-scope: question limits | https://raw.githubusercontent.com/mattpocock/skills/main/.out-of-scope/question-limits.md | full |
| obra/superpowers, brainstorming skill | https://raw.githubusercontent.com/obra/superpowers/main/skills/brainstorming/SKILL.md | full |
| obra/superpowers, release notes | https://raw.githubusercontent.com/obra/superpowers/main/RELEASE-NOTES.md | full (v5.0.6 section) |

---

## Gaps and low-confidence items

No evidence found

- One question at a time versus batched rounds: no controlled comparison. Practitioner positions conflict, and upstream calls its own default "genuinely contested".
- Recommending an answer with each question: no measurement of its effect on decision quality, and none of human anchoring on the model's recommendation in this setting.
- How many questions before a human disengages: no measurement. Every clarification study found uses an LLM-simulated user.
- Guideword sweeps (SHARD, STPA UCA) run by an LLM on a software design proposal, versus an unstructured critic: no evidence.
- Premortem or Key Assumptions Check run by an LLM: no evidence.
- Checklist-driven versus free-form LLM review: no direct comparison.
- Grounding a design against code before locking, as a tested practice: no direct evidence.
- Attribution-blind option presentation as a sycophancy mitigation: mechanism supported by a 2023 paper on older models; no 2025–2026 measurement found.

Low confidence

- The CCR result (A3) is one author, one model, 30 artifacts, injected errors. It is the only controlled comparison of fresh versus same-session review I found, so Q2's central claim rests on it.
- The superpowers finding that subagent plan review added nothing is self-reported, with no data published.
- "Prompt Design at Scale" is a single preprint; its authors warn against transferring its thresholds. IFScale's task (keyword inclusion) is much simpler than procedural skill rules.
- The "ICLR 2026" citation cannot be matched; the workshop paper named in A7 is my best candidate, not a confirmed identification.
- SKILL.md token size (about 5.9k) is estimated from bytes, not tokenized. The conclusion that it exceeds the 5,000-token compaction window is therefore probable, not established.
- The mapping "skill critic payload = SA condition" rests on my reading of CRITIC.md usage step 1 against the paper's one-line condition labels.

Unreachable or unread

- Mitchell, Russo & Pennington (1989), the primary behind the premortem 30% figure: publisher returned 403.
- Klein's HBR article on hbr.org: paywalled; read via a reproduction.
- Pumfrey's thesis (the SHARD primary): not fetched; the Value (subtle) / Value (coarse) split in CRITIC-COVERAGE.md is unverified.
- Both Safety Science papers: abstract and highlights only.
- Later human studies of premortem efficacy (after Mitchell et al. 1989): not searched for beyond the one secondary source.
