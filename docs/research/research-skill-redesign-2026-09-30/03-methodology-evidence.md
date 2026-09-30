# Evidence scan: what makes LLM-agent web research accurate (vs cargo cult)

Scan date 2026-09-30. Every claim below is tagged with URL + retrieved date, or marked
"prior, unverified" if not fetched this run. Evidence grades: **[measured]** = benchmark/study
with numbers, **[vendor]** = engineering report from a lab shipping the product (internal evals,
not independently reproducible), **[practitioner]** = single-author blog/opinion, **[abstract-only]**
= arXiv abstract read via search tool, full paper not opened this run.

---

## Q1. Architecture: orchestrator+parallel subagents vs single agent

**Supports fan-out, bounded:**
- Anthropic, "How we built our multi-agent research system", https://www.anthropic.com/engineering/multi-agent-research-system, published 2025-06-13, retrieved 2026-09-30. **[vendor, internal eval]** Opus-lead + Sonnet-subagents beat single-agent Opus by 90.2% on their internal eval, "especially for breadth-first queries." Token usage alone explains ~80% of BrowseComp variance; tokens+tool-calls+model choice explain 95%. Cost: ~4x tokens/query vs chat, ~15x for multi-agent. Explicit anti-fit: "domains that require all agents to share the same context or involve many dependencies between agents are not a good fit." Effort-scaling embedded in prompts: 1 agent/3-10 calls (simple), 2-4 subagents/10-15 calls (comparison), 10+ subagents (complex/breadth-first).
- LangChain, "Open Deep Research", https://www.langchain.com/blog/open-deep-research, 2025-07-16, retrieved 2026-09-30 (full text). **[vendor]** Multi-agent only for the *research* phase, isolated by independent sub-topic; single-shot report writing (parallel section-writing produced disjoint reports — same failure Cognition describes). Supervisor decides fan-out vs single-thread per request via heuristics, not a fixed rule. Concrete example: single agent interleaving 3 topics wastes tokens and researches each topic *less deeply*; per-topic isolation fixed this in their own evals.
- arXiv 2601.11327 (Jan 2026) — restricted-communication small subagents can beat a larger single model; gain driven by orchestrator capacity. **[abstract-only]**

**Disconfirms / bounds it hard:**
- Cognition (Walden Yan), "Don't Build Multi-Agents", https://cognition.ai/blog/dont-build-multi-agents, published 2025-06-12, retrieved 2026-09-30 (full text). **[practitioner]** Two principles: share full context/traces, not summaries; "actions carry implicit decisions" — parallel subagents with un-shared decisions produce incompatible outputs (their own Flappy-Bird example). States Claude Code's subagents "never do work in parallel... usually only tasked with answering a question, not writing any code" specifically because of this. Multi-agent *collaboration* (agents talking to reach consensus) called fragile as of 2025 — explicitly the opposite conclusion from Anthropic's research-system post, and about a different task class (coding/interdependent decisions vs. independent-topic research).
- arXiv 2512.08296 (Dec 2025) "Towards a Science of Scaling Agent Systems" — 260 configs, 6 benchmarks: MAS relative gain ranges **+80.8% to −70.0%** vs single agent depending on task decomposability; diminishing returns once single-agent baseline is already strong; tasks without centralized verification propagate errors worse. **[measured, abstract-only]**
- arXiv 2606.13003 (Jun 2026) "The Illusion of Multi-Agent Advantage" — auto-generated MAS *underperform* self-consistency CoT, including on BrowseComp-Plus, at up to 10x cost; only expert-hand-architected MAS (explicit decomposition/isolation/parallelization) wins. **[measured, abstract-only]** — directly says the *generic* fan-out ritual is often net-negative; the win requires task-specific design, not a default multi-agent stance.
- arXiv 2604.02460 (Apr 2026) — single-agent matches/beats MAS on multi-hop reasoning at equal thinking-token budgets; benchmark artifacts inflate reported MAS gains. **[measured, abstract-only]**
- arXiv 2606.30524 (Jun 2026) — single agent achieves comparable quality at 86% fewer tokens, 2x speed; planning (not agent count) is the bottleneck; a human-guided plan beats automatic fan-out. **[measured, abstract-only]**
- arXiv 2608.24306 (Aug 2026) "Who is the Agent to Blame?" — in AI-Q, **84.7% of final-report errors originate at the orchestrator** (~31% hallucination, rest citation mistakes), not the per-topic subagents, which make few mistakes. This says the fragile link is exactly the synthesis/orchestrator step Anthropic's design also isolates least. **[measured, abstract-only]**
- arXiv 2605.16616 MLReplicate — token budget did **not** predict quality across a 38x input-token spread; "workflow design matters more than scale of compute" — in tension with Anthropic's "80% of variance is tokens" framing. **[measured, abstract-only]**

**Isolation / independent replication (the specific mechanism, not just "fan out"):**
- arXiv 2608.23045 (Aug 2026) "From Inertia to Objectivity" — **inertia bias**: a model is measurably worse at judging the outcome of its *own* prior search action than a fresh context is. Context isolation specifically at webpage-triage and final-answer-validation steps gave competitive GAIA/BrowseComp results at 33% lower token cost. **[measured, abstract-only]** — this is real, specific evidence for "verify from a fresh context," distinct from generic multi-agent fan-out.
- arXiv 2605.00914 (May 2026) — isolated self-correction beat homogeneous multi-agent debate on 7-8B models: debate showed sycophantic conformity up to 85.5%, consensus collapse (oracle gap up to 32.3pp), and cost 2.1-3.4x tokens for equal/lower accuracy than isolated correction. **[measured, abstract-only]**
- arXiv 2609.31563 (Sep 2026) — P(at least one agent correct) rises 5-20pts with team size, but plurality voting realizes almost none of that; revision gain is the same with 1 peer as with 29; shared-model bias accounts for ~87% of squared error in estimation tasks, so pure averaging within one model family cuts error only ~6%. Mixing model families helps more than adding same-family agents. **[measured, abstract-only]** — strong, specific disconfirmation of "more parallel agents/replicas = more accurate" unless they're heterogeneous and unless the aggregation mechanism (not just generation) is designed for it.

**Verdict:** Fan-out is real but narrow: it helps for breadth-first/independently-decomposable topics, hurts on interdependent/sequential tasks, and the orchestrator/synthesis step (not the subagents) is where most final-report errors originate — so isolating subagents from each other is evidenced (inertia-bias/fresh-context effect), but isolating subagent *conclusions* from each other without a verification-and-aggregation step designed for heterogeneity is not shown to help and sometimes measurably hurts (voting/debate lines above). A `/research` skill run by a single Claude Code session with sub-agent Tasks is closer to Anthropic's "comparison"/breadth tier (2-4 parallel, per-topic-isolated) than to full autonomous multi-agent-with-debate — that tier has the best support.

---

## Q2. Planning, question decomposition, pre-registered falsifiers, stopping rules

**Research briefs / decomposition — well supported:**
- LangChain post (above): explicit "Scope" phase (clarify + brief-generation) precedes research; brief is "north star," referenced throughout; subagents get an isolated sub-topic, not the full brief. **[vendor]**
- Anthropic post (above): each subagent needs "an objective, an output format, guidance on tools/sources, clear task boundaries"; vague briefs caused duplicated searches and coverage gaps in their own evals. **[vendor]**

**Stopping rules / saturation — well supported, several independent measured studies converge:**
- arXiv 2608.01913 (Aug 2026) — accuracy tracks *cumulative retrieval recall*, not number of searches or context consumed; useful evidence arrives early, then a long low-yield tail; best agents issue far fewer redundant queries. Recommends evidence-sufficiency stopping over query-count or token-count limits. **[measured, abstract-only]**
- arXiv 2608.02009 (Aug 2026) HALT — stop when cumulative evidence supports each *required claim*, not when the generator reports confidence. **[measured, abstract-only]**
- arXiv 2608.15191 (Aug 2026) RAAC — majority of iterations add nothing; a novelty/coverage controller cut ~14 search calls with **+3% average accuracy (up to +10%)** — stopping earlier-but-smarter beat searching longer. **[measured, abstract-only]**
- arXiv 2602.03304 (Feb 2026) — both over-search and under-search are pervasive failure modes, not just one direction. **[measured, abstract-only]**
- arXiv 2604.24978 "Don't Stop Early" — outline + reflection + explicit evidence-sufficiency criteria reduces *premature* stopping (the opposite failure). **[measured, abstract-only]**
- arXiv 2606.00198 BAGEN — agents are systematically over-optimistic about remaining budget; early-stop policies saved 28-64% tokens specifically on trajectories that were going to fail anyway. **[measured, abstract-only]**

**Pre-registered "what would change my mind" / explicit falsifiers:**
- No direct hit on pre-registration-of-falsifiers for research agents specifically. Closest, and it's disconfirming of the *absence* of this practice: arXiv 2604.02485 (Apr 2026) "Failing to Falsify" — prompting models to actively consider counterexamples before concluding raised rule-discovery from **42% to 56%**. **[measured, abstract-only]** arXiv 2602.14270 (Feb 2026, N=557) — default LLM behavior *suppresses* falsification and inflates confidence in a Wason-task analog, similarly to sycophantic prompting; forcing unbiased/adversarial sampling gave 5x more discoveries. **[measured, abstract-only]** This is evidence *for* an explicit falsification step, but it is evidence from abstract rule-discovery tasks, not from research-report writing specifically — treat as suggestive, not proven for this exact use case. **Unknown**: whether writing "what would change my mind" *before* searching (pre-registration, as opposed to a post-hoc red-team pass — see Q4) has been tested at all; nothing retrieved either way.

**Verdict:** Brief-first + isolated sub-topic scoping is well supported by two independent vendor systems. Evidence-sufficiency/coverage-based stopping is the best-evidenced planning idea in the whole scan — five converging measured papers, all pointing the same direction (stop on cumulative-evidence-for-each-claim, not on query count, token count, or self-reported confidence). Pre-registered falsifiers specifically are untested; the adjacent counterexample-prompting literature supports the general idea but doesn't validate the pre-registration ritual as implemented in any skill.

---

## Q3. Grounding and verification

**Citation hallucination rates — heavily measured, converges on "single digit to double digit percent, verifier-dependent":**
- arXiv 2604.03173 (Apr 2026) — 3-13% of citation URLs fabricated outright, 5-18% non-resolving, across 10 models/agents; deep-research agents hallucinate URLs at *higher* rates than plain search-augmented LLMs; a URL-liveness re-fetch check in a self-correction loop cut non-resolving URLs **6-79x, to under 1%**. **[measured, abstract-only]** — strongest single piece of evidence for a mandatory re-fetch/liveness check.
- arXiv 2509.04499 (Sep 2025) DeepTRACE — citation accuracy only 40-80%; many statements unsupported by the report's own cited sources; reports one-sided and overconfident specifically on debate-style queries. **[measured, abstract-only]**
- arXiv 2607.20527 (Jul 2026) — unsupported-citation rate measured at ~3% to ~18% *depending only on verifier strictness*, not on the generator; verifiers disagree with each other (negative-specific agreement 0.27-0.30). **[measured, abstract-only]** — important caveat: any single-pass citation-verification number is itself unreliable unless the verifier's strictness is fixed/disclosed.
- arXiv 2605.06635 "Cited but Not Verified: Parsing and Evaluating Source Attribution in LLM Deep Research Agents" — even the strongest frontier models keep link-validity >94% and topical relevance >80%, but factual accuracy against the cited source is only **39-77%**. Critically: **Fact-Check accuracy drops ~42% on average as tool calls scale from 2 to 150** — "more retrieval does not produce more accurate citations." **[measured, abstract-only]** — this directly disconfirms "more searching/scraping = more grounded"; it's evidence that a *small, bounded* search budget with a verification pass beats a large unbounded one on citation accuracy specifically.
- arXiv 2608.28643 CLAIMWRITER — replacing a deep-research pipeline's report-writer with a claim-level, source-linked writer (extract source facts → map to outline → draft per source-linked claim) cut hallucination **2.6-4.5x** and improved necessary-fact recall 1.2-1.7x versus the same pipeline's default writer, at comparable overall quality. **[measured, abstract-only]** — concrete, positive evidence for claim-level (not paragraph-level) citation attribution as a generation-time discipline, not just a post-hoc check.
- Separate **CitationAgent** pass after the research loop: Anthropic post (above). **[vendor]** — architecturally the same idea as the papers above (separate verification pass), independently arrived at.

**Confabulation / consensus, closed-book baseline (context for how bad it is without any grounding):** 2603.07287, 2603.03299 (11.4-56.8% fabricated, but multi-model consensus of >3 LLMs → 95.6% accuracy), 2602.06718 GhostCite (14.23-94.93%), 2609.14988 (10.2-98.4% depending on model), 2604.16407 (web-enabled essays *still* 9.2% hallucinated refs — web access does not zero this out), 2602.05930 (100 fabricated citations found across 53 real NeurIPS 2025 papers — this is a human-authored-paper problem too, not unique to agents). All **[measured, abstract-only]**.

**Misleading-document injection (relevant to "verify a specific claim by re-fetching"):**
- arXiv 2607.20891 MisKnow-Agent — a single injected misleading document raised false-conclusion adoption from 0% to **54.7%**; authority cues and presentation style drove adoption, search rank and having more documents didn't; agents kept adopting a flagged document even after cross-model verification flagged it. **[measured, abstract-only]** — disconfirms "cross-model verification" as a sufficient safeguard on its own; flagging isn't the same as not using the flagged content.

**Verdict:** This is the best-evidenced cluster in the whole scan. Converging, independently measured findings: (1) citation hallucination is real and sizable (3-18%+ depending on verifier), (2) a separate verification/re-fetch pass measurably helps (6-79x reduction in one study), (3) claim-level attribution at generation time beats post-hoc paragraph citation, (4) bigger search budgets do not reliably improve citation accuracy and can hurt it. The one important caution: verifier strictness itself is uncalibrated across studies, so a skill that claims "citation-verified" needs to say what standard was applied.

---

## Q4. Adversarial / disconfirmation search and confirmation bias

**Confirmation bias in search is real and measured:**
- arXiv 2605.01302 (May 2026) — relevance-maximizing retrieval returns "sycophantic evidence" for a biased query — the search step itself, not just the generation step, mirrors the asker's framing. **[measured, abstract-only]**
- arXiv 2603.16138 "Answer Bubbles" (Mar 2026) — search integration reduces hedging by up to 60% (more confident answers) while social-media and negatively-framed sources are systematically underrepresented in what gets retrieved. **[measured, abstract-only]** — direct evidence of anchoring toward confident, mainstream-leaning sources.
- arXiv 2604.25931 — anchored confabulation (prior partial answer anchors and biases subsequent search/generation). **[abstract-only]**
- arXiv 2602.14270 (above, Q2) — default LLM behavior on a Wason-style task suppressed disconfirming search and inflated confidence "like sycophantic prompting"; explicit unbiased sampling gave 5x more discoveries. **[measured, abstract-only]**

**Does an explicit "argue the opposite"/red-team/debate pass help? Evidence is mostly negative or mixed — this is the single biggest "attractive but unsupported" finding in the whole scan:**
- arXiv 2502.08788 — multi-agent debate often fails to beat plain CoT/self-consistency. **[measured, abstract-only]**
- arXiv 2609.35875 — debate ties or loses to self-consistency at 3.4x the token cost; **persona prompting (e.g., "argue as a skeptic") reduces accuracy**; almost all of whatever benefit exists comes from the *first* exchange, not sustained debate. **[measured, abstract-only]** — directly disconfirms the "assign a persona to argue the opposite" pattern specifically.
- arXiv 2510.20963 — competitive/adversarial debate degenerates into "cheap talk" (non-informative rhetoric) rather than substantive disagreement. **[measured, abstract-only]**
- arXiv 2509.05396 — debate can *decrease* accuracy outright. **[measured, abstract-only]**
- arXiv 2606.02866 (Jun 2026) — nuanced and load-bearing: naive debate **degrades generation by −1.6 to −15.5 pp** because critics hallucinate their own feedback; self-verification using the same tools as the generator also fails. But a *separate critic with code-execution grounding*, combined with evidence-gated generation, beat single-agent by **+5.3pp**, and error-detection (as opposed to generation) improved **+27.4pp F1**. **[measured, abstract-only]** — the pattern that works is not "argue the opposite in text," it's "a separately-grounded critic checking specific claims via execution/re-fetch," which is really the same mechanism as Q3's verification pass, not a debate/adversarial dialectic.
- arXiv 2604.02485, 2602.14270 (Q2, above) — by contrast, *counterexample-seeking* (as opposed to argumentative debate) does measurably help discovery. The distinction that emerges across this cluster: "seek disconfirming evidence for a specific claim" helps; "have an agent argue the opposing position rhetorically" mostly doesn't and sometimes hurts.

**Verdict:** Confirmation bias in agentic search is real and well evidenced (search retrieval itself, not just generation, mirrors the asker's framing and underrepresents dissenting sources). But the fashionable fix — a red-team/devil's-advocate/debate sub-agent — is *not* supported by the debate literature; several studies show it's neutral-to-harmful and expensive. What is supported is a narrower, execution/evidence-grounded critic checking specific claims, plus deliberately seeking counterexamples/disconfirming *evidence* (not rhetorical opposition) for load-bearing claims.

---

## Q5. Source quality, channel weighting, forum vs paper value

**SEO/content-farm bias — vendor-confirmed and independently measured:**
- Anthropic post (above): human testers found early agents "consistently chose SEO-optimized content farms over authoritative but less highly-ranked sources like academic PDFs or personal blogs"; fixed with prompted source-quality heuristics, not a rigid whitelist. **[vendor]**
- arXiv 2605.23684 (May 2026) — ~16% of cited sources in major AI search products are themselves AI-generated. **[measured, abstract-only]**
- arXiv 2602.16136 "Retrieval Collapses" (Feb 2026) — 67% pool contamination → >80% exposure to bad sources while apparent accuracy looks stable — i.e., degraded source quality can be invisible in aggregate metrics. **[measured, abstract-only]**
- arXiv 2512.09483 — LLM-based search engines are not measurably better than traditional search at credibility discrimination. **[measured, abstract-only]**
- arXiv 2606.16821 SearchGEO — a manipulated-endorsement attack succeeds 0% of the time against Claude-Sonnet-4.6 but 31.4% against Gemini-3-Flash in their test — source-quality robustness is model-dependent, not a solved problem in general. **[measured, abstract-only]**

**Reddit/HN/forum value vs official docs/papers for engineering decisions:**
- arXiv 2601.08036 AutoDoc (published venue unclear, retrieved via paper search 2026-09-30) — API docs generated by mining Stack Overflow were up to 77.7% more accurate and surfaced 34.4% of knowledge that official docs never covered. **[measured, abstract-only]** — concrete, positive evidence that community/forum content adds real, non-redundant information beyond official docs for engineering questions, not just "color."
- arXiv 2402.08801 — ChatGPT/LLaMA "challenge but do not outperform" human expertise on Stack Overflow-style questions in some domains; SO posting activity has been declining since LLM adoption (so the corpus itself may be thinning going forward). **[measured, abstract-only]**
- No paper found that directly tests "mandatory N-channel checklist" as a research-agent design (Reddit+HN+blogs+papers all required every run) vs. flexible/heuristic channel selection. This specific practice is untested in the literature retrieved.
- Indirect evidence against rigid mandatory checklists as a general skill pattern: arXiv 2608.11888 "Agent Skills Can Be Harmful" (Aug 2026) — of 307 skill-induced failures studied, "excessive verification" (67 cases) and heavy mandatory pipelines (30 cases) were themselves failure categories: "skills often turn validation checklists and construction recipes into mandatory work" that adds cost without proportionate benefit. **[measured, abstract-only]** Anthropic's own skill-authoring guidance (see Q9) explicitly favors "heuristics rather than rigid rules" for exactly this kind of judgment call. **[vendor]**

**Verdict:** Preferring primary/authoritative over SEO content is well evidenced as a real problem and a real (heuristic, not rule-based) fix. Community/forum content has genuine, measured incremental value over official docs for engineering questions — this is a legitimate reason to include a "users" channel. But no evidence supports a *fixed, mandatory* N-channel checklist as the mechanism; the closest evidence (skill-failure taxonomy + Anthropic's own guidance) says mandatory checklists tend toward box-ticking/excess work. The right level of support is: channel *diversity as a heuristic prompt*, not a hard gate that blocks completion.

---

## Q6. Confidence scoring

**Self-reported confidence is poorly calibrated — multiple converging results:**
- arXiv 2607.20526 ConfidenceBench (Jul 2026) — best model Brier score 0.103 vs a naive baseline of 0.1875; but several models scored *worse* than the naive baseline. **[measured, abstract-only]**
- arXiv 2604.01457, 2603.25052 — verbalized confidence is largely detached from actual accuracy; reasoning-and-verbalizing-confidence-simultaneously makes miscalibration *worse* (the act of narrating confidence while reasoning degrades the confidence signal itself). **[measured, abstract-only]** — directly relevant to a skill that asks the model to both write the report and, in the same pass, emit "Confidence: N/100."
- 2410.09724 (prior, unverified — from training knowledge, not refetched this run) — RLHF training is a known contributor to overconfidence generally.
- **Disconfirming the disconfirmation** (calibration is not hopeless, just not free): arXiv 2412.14737 — well-calibrated verbalized scores are achievable with specific prompting methods. arXiv 2605.12446 — *decoupling* confidence estimation from the generation pass (i.e., a separate call whose only job is to estimate confidence) improves calibration versus asking the generator to self-report inline. **[measured, abstract-only]**

**The specific finding most relevant to redesigning the skill's "## Confidence: N/100":**
- arXiv 2606.29034 "The strength of clinical evidence is recoverable from language model representations but not from their stated grades" — a linear probe on internal activations recovers the true evidence grade with median AUROC 71.8 across 22 models; the grade the model *states* when asked falls to chance, 25-27 points below what's recoverable from its own representations. **[measured, abstract-only]** — this is the sharpest single piece of evidence in the scan against verbalized/stated confidence or evidence-grade scores: the model "knows" more about evidence strength internally than it says out loud, and what it says is not trustworthy even though a better signal exists (just not one a black-box skill can access).

**Better alternatives — mixed but more supported than a single scalar:**
- Per-claim evidence labels / GRADE-like schemes: arXiv 2605.27710 DeepSciVerify (two-stage claim-citation verification, abstract-level reasoning + selective escalation to full text) reached 86.7 Micro-F1, +4.5pts over abstract-only baselines, resolving 67% of cases without needing full-text retrieval — evidence that *structured, per-claim* verification with escalation beats a single flat judgment. **[measured, abstract-only]** arXiv 2609.22111 ReAgent and arXiv 2604.13120 AgentForge (Q7 below) both support claim-level, execution-checked verification over a global confidence figure. arXiv 2609.04442 GRACE — classifies claims as Grounded/Refuted/Boundary and routes only high-uncertainty "boundary" claims to expert review (a "Return on Attention" triage), rather than emitting one number for the whole report. **[measured, abstract-only]**
- Listing falsifiers as an alternative to a confidence number: no direct measurement found; supported only indirectly by the Q2/Q4 counterexample-seeking literature (2604.02485, 2602.14270) — those measure *discovery* rate, not calibration of a stated confidence, so this remains a plausible but untested idea for report-level confidence specifically.

**Verdict:** A single self-reported "Confidence: N/100" is close to the least-supported practice in the current skill — multiple studies show verbalized confidence is weakly-to-not correlated with accuracy, and the single most targeted study found stated evidence-grades are at chance even when the true grade is recoverable from the model's own internals. Per-claim structured labels (grounded/refuted/boundary, or graded with escalation) are measurably better than a flat score, though no paper tests a GRADE-style scheme against a Claude-generated research report specifically — the support is by analogy from adjacent claim-verification systems, not a direct test of "does labeling top-level report confidence this way help."

---

## Q7. Experiment-in-the-loop (execution/reproduction as verification)

**When it helps — well evidenced, and it's a stronger, more consistently positive result than the debate/adversarial literature in Q4:**
- arXiv 2511.05524 EviBound — gating claims on machine-checkable execution evidence (approval gate pre-execution + verification gate post-execution against a queryable run ID) took hallucinated "task complete" claims from **100% (8/8) with prompting alone, to 25% with verification-only, to 0% with dual gates**, at only ~8.3% execution overhead. **[measured, abstract-only]** — one of the cleanest before/after numbers in the whole scan.
- arXiv 2604.13120 AgentForge — mandatory sandboxed execution before any code change propagates improved SWE-bench-Lite resolution by 26-28 points over single-agent baselines with no execution gate. **[measured, abstract-only]**
- arXiv 2606.02866 (Q4, above) — the debate/critic pattern that actually worked required code-execution grounding, not text argument; this is really the same "verify by running it" finding surfacing again.
- arXiv 2609.22111 ReAgent — static (does the doc match the repo?) + dynamic (re-run experiments) auditing catches inconsistencies neither catches alone, including "experiments that reproduce reported numbers while deviating from the claimed methodology" — i.e., execution alone is not sufficient without also checking methodology consistency. **[measured, abstract-only]**
- arXiv 2604.04074 FactReview — execution-based claim verification for peer review: removing execution evidence changed 17.0% of claim verdicts, more than removing any other single evidence source, and cut reviewer time 58% while raising claim coverage 87%→99%. **[measured, abstract-only]**

**Failure modes — also well evidenced, this is a genuinely two-sided result, not just a win:**
- arXiv 2509.08713 (Sep 2025) — four recurring failure modes in AI-scientist-style systems: inappropriate benchmark selection, data leakage, metric misuse, post-hoc selection bias. **[measured, abstract-only]**
- arXiv 2608.26753 (Aug 2026) — "methodological hallucinations": silently shrunk datasets/budgets, oracle/lookup substitutions standing in for real computation, conclusions drawn from resource-limited settings presented as general. **[measured, abstract-only]**
- arXiv 2601.03315 (Jan 2026) — 3 of 4 automated replication attempts failed outright; implementation drift and "overexcitement" (declaring success prematurely) were the dominant causes. **[measured, abstract-only]**
- arXiv 2605.16616 MLReplicate — 59% of auto-accepted papers in their pipeline had fabricated or unsupported claims even though they passed automated review; token budget didn't predict quality. **[measured, abstract-only]**
- arXiv 2603.27646 PRBench — best agent hit 34% on paper-reproduction tasks, **zero** full end-to-end successes. **[measured, abstract-only]**

**Trigger and bounding rules found in the literature (this answers the task's explicit ask directly):**
- EviBound's own bounding rule: retries are capped, "typically 1-2 attempts," explicitly to avoid unbounded loops. **[measured, abstract-only]**
- FactReview's bounding rule: execution runs under "a fixed repair budget." **[measured, abstract-only]**
- General pattern across the positive results above: execution is gated to a *specific, falsifiable claim* (does this code run, does this benchmark number reproduce, does this API call actually succeed) with a hard retry/budget cap — never used as open-ended "let's also try running some things." The failure-mode papers (2601.03315, 2605.16616, 2603.27646) are precisely the cases where execution was open-ended/exploratory rather than gated to verifying one claim.
- No paper specifies a trigger *threshold* for "when is a claim important enough to warrant execution" — that judgment call is unaddressed in the literature; it's a heuristic gap the skill would have to set itself, e.g. only for claims where execution is cheap (single command, seconds) and the claim is decision-critical (e.g., "this API call works this way", "this benchmark number is X").

**Verdict:** Empirical/execution-grounded checking is the single most consistently positive intervention in this entire scan when it is (a) gated to a specific, falsifiable claim, and (b) bounded by a small fixed retry/repair budget. It reliably beats both pure reading and pure debate for the claims it can reach. It reliably fails when used exploratory/open-ended (AI-scientist-style), where post-hoc selection bias and premature success-declaration dominate. For a `/research` skill that mostly answers "which tool/library/approach," the actionable version is narrow: when a claim is a checkable technical fact (an API behaves this way, a flag does this, a number reproduces) and checking it costs one bounded command, run it and cite the execution result instead of citing prose about it; do not spin up exploratory benchmarking.

---

## Q8. Known failure-mode taxonomies (2025-2026)

- arXiv 2512.01948 (Dec 2025) FINDER/DEFT — 14 distinct failure modes in deep-research agents; the paper's summary judgment is that DRAs specifically struggle with "evidence integration, verification, and reasoning-resilient planning" — not raw retrieval. **[measured, abstract-only]**
- arXiv 2601.22984 PING — separate taxonomy. **[abstract-only, not detailed]**
- arXiv 2601.15808 DeepVerifier — 5 categories / 13 subcategories of verification failure; also reports rubric-guided inference-time verification improving accuracy 8-11% on GAIA/XBench subsets, so it's both a taxonomy and a partial fix. **[measured, abstract-only]**
- arXiv 2607.05775 (Jul 2026) — failures compound *nonlinearly* with task length, and additional scaffolding does not consistently improve reliability as tasks get longer — i.e., bolting more process onto a long research task doesn't reliably help past some point. **[measured, abstract-only]** — relevant caution against an ever-growing checklist-style skill.
- Cross-referenced from Q1/Q3/Q4/Q7: orchestrator-step errors dominate final-report mistakes (2608.24306); citation/URL issues are the largest measured single failure class (2604.03173, 2605.06635); misleading-document adoption (2607.20891); inertia bias in self-judged search (2608.23045).

**Verdict:** No single canonical 2025-2026 taxonomy dominates; several independent groups converge on the same three clusters — verification/citation failures, orchestration/synthesis errors, and reasoning/planning breakdown over long horizons — which is itself decent corroboration (independent-origin convergence) even though each individual taxonomy paper is abstract-only here.

---

## Q9. Durable skill design

**Anthropic's current authoring guidance (vendor, but this is literally the platform the skill runs on, so treat as closer to spec than opinion):**
- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices, no visible pub date, retrieved 2026-09-30, full text read. **[vendor guidance, not measured]**
  - "**Avoid time-sensitive information** — don't include information that will become outdated"; use an explicit "Old patterns" section instead of deleting/rewriting history in place.
  - No "voodoo constants": "If you don't know the right value, how will Claude determine it?" — any hard-coded numeric threshold needs a stated justification or a script that computes it, not a bare magic number.
  - Prefer heuristics/text guidance when "multiple approaches are valid or context-dependent"; prefer exact scripts/low freedom only when "operations are fragile and error-prone, consistency is critical, a specific sequence must be followed."
  - Keep SKILL.md under 500 lines; reference files one level deep; domain-organized, loaded only when needed (progressive disclosure).
  - MCP tool references must use fully-qualified `ServerName:tool_name` and should not assume a tool is installed.
  - "Avoid offering too many options" — default + escape hatch, not an exhaustive menu.
  - Build evaluations first: run the task without the skill, document actual failures, write minimal instructions targeting those failures, iterate with a fresh "Claude B" instance as the test subject.
- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills, published 2025-10-16, updated 2025-12-18, retrieved 2026-09-30 (excerpt). **[vendor]** Progressive disclosure is explicitly named "the core design principle": metadata always loaded, full SKILL.md loaded only when relevant, linked reference files loaded only as needed.

**Practitioner evidence that stale/bloated skills are a real, observed failure (not hypothetical):**
- https://buildtolaunch.substack.com/p/claude-skills-not-working-fix, retrieved 2026-09-30 (search excerpt only, not full text). **[practitioner]** Describes skills "breaking without telling you" as skill counts climb into the hundreds — i.e., staleness/bloat compounds with the number of skills in play, not just the size of one skill.
- LinkedIn (Hanna Huffman), excerpt only, retrieved 2026-09-30. **[practitioner, single anecdote]** "I had 48 Claude skills at one point... prune AI skills before they go stale" — anecdotal but consistent with the Substack post.
- A Facebook post surfaced in search claiming every toggled-on skill loads its *full* SKILL.md into every conversation — this **contradicts** Anthropic's own progressive-disclosure documentation above; flagged as low-quality/likely-wrong and not used as evidence.

**Measured evidence on skill effectiveness and failure (this is the most important, least "vendor-marketing" evidence for Q9):**
- arXiv 2608.23067 (Aug 2026) "Signal or Noise?" — skill injection **reduced** mean Pass@2 by 1.3-4.2% and increased token cost 72-394%, with gains in only 17-36% of tested pairs; skill rankings/effectiveness transferred poorly across different models; **anti-pattern rules (what not to do) outperformed example-heavy content**. **[measured, abstract-only]** — direct evidence that skills are not a free win and that concise negative/heuristic guidance beats verbose worked examples, which supports "concise is key" and cuts against padding a skill with elaborate examples.
- arXiv 2608.11888 (Aug 2026) "Agent Skills Can Be Harmful" — catalogued 307 skill-induced failures; the two largest categories were **excessive verification (67 cases)** and heavy mandatory pipelines (30 cases): skills "often turn validation checklists and construction recipes into mandatory work" disproportionate to the task. **[measured, abstract-only]** — directly relevant to the current skill's mandatory 4-channel intake and multi-step output pipeline; this is measured evidence that exactly this shape of design is a documented failure pattern class, not just a style preference.
- arXiv 2607.01456 — over 99% of real-world SKILL.md files sampled had at least one identifiable "skill smell." **[measured, abstract-only]**
- arXiv 2604.04323, 2605.23657 — skill benefits are fragile and model/framework-dependent (what helps on one model/harness doesn't reliably transfer). **[measured, abstract-only]**
- arXiv 2504.06188 — skill impact depends heavily on whether it bundles runnable code/artifacts vs. prose-only instructions. **[measured, abstract-only]**
- arXiv 2601.04748 — skill-selection accuracy drops once the library of available skills passes a size threshold (relevant to the "hundreds of skills" staleness reports above — corroborates from a different angle: a measured mechanism, not just anecdote).

**Verdict:** Converges cleanly: Anthropic's own guidance ("avoid time-sensitive info," "no voodoo constants," concise, heuristic-over-rigid) is independently corroborated by measured studies showing (a) verbose/example-heavy skills underperform concise anti-pattern rules, (b) mandatory-checklist/excessive-verification designs are a documented, named failure category, and (c) skill effectiveness doesn't transfer across models — so hard-coding today's tool names/params/measured numbers is doubly wrong: it goes stale, and even while fresh it's the less-effective content shape.

---

## Gap analysis: current `/research` SKILL.md (v6.0.0) against this evidence

**What it already gets right (evidenced):**
- Pipeline step "Search → Analyze → Output" with a synthesis/analysis step separate from raw search — consistent with every architecture cited (LangChain's clean-then-return, Anthropic's per-subagent synthesis).
- "3+ independent sources for non-trivial claims" and explicit contradiction-listing — directionally right, though the evidence (Q1 voting/consensus literature) says the *independence* (cross-model/cross-family, not just cross-URL) matters more than the count; 3 same-origin sources add little (Q5 retrieval-collapse / common-origin risk is real but this skill has no mechanism to detect shared origin).
- Grounding rule ("every finding must trace to a URL this run actually retrieved; unfetched claims labeled priors or omitted") — this is exactly the discipline Q3's evidence says works, and it's already present.
- Budget caps (2-3 searches, ≤2 scrapes) — consistent with Q3's finding that more scraping doesn't improve citation accuracy and can hurt it (2605.06635's 42% accuracy drop as tool calls scale 2→150). This cap is better-supported by the evidence than it might look at first glance.
- Preference for "official docs/primary sources/maintainer threads/benchmarks with methodology" over SEO/listicles — matches Anthropic's own documented fix for the SEO-content-farm failure mode.

**Unsupported ritual (the skill does this, but the evidence doesn't back the specific mechanism):**
- **Single scalar "Confidence: N/100"** — this is the most clearly unsupported element in the skill. Verbalized/self-reported confidence is repeatedly shown uncorrelated with accuracy, and the sharpest paper found stated evidence-grades at chance even when the true grade was recoverable from the model internally. Per-claim labels (supported/contested/unknown) or an explicit falsifier list are better-evidenced alternatives, though even those are not validated for this exact report-writing use case — they're supported by analogy, not direct test.
- **Mandatory 4-channel intake with "owner waiver" to skip** — the mandatory-checklist pattern is a named, measured failure category (2608.11888: excessive-verification / heavy-pipeline failures). The underlying instinct (forum content has value, Q5) is evidenced; the rigid gate mechanism is not, and Anthropic's own guidance explicitly prefers heuristics over rigid rules for exactly this kind of judgment call.
- Hard-coded vendor tool names, credit costs, and byte-size measurements ("measured against the live connector on 2026-07-30") embedded directly in the method file — this is precisely what Anthropic's authoring guidance calls out as "time-sensitive information" to avoid, and it's a stronger, more specific version of that warning than a hypothetical: these numbers are already a snapshot of one connector on one date, will drift, and mix volatile tooling into what should be a stable method. No countervailing evidence found for keeping vendor-specific constants inline in a method doc.
- Raw `gh issue create` inside the skill's Output step — conflicts with this operator's own `/file-issue` routing rule (not an external-evidence question, but worth flagging since it's a concrete gap against a stated project rule, not just "ritual").

**Missing (evidence says these matter, skill has nothing for them):**
- No effort-scaling / fan-out rule keyed to query type (Anthropic's simple/comparison/complex tiers, or even a lighter version) — the skill treats "discovery" and "topic" modes uniformly rather than scaling search depth to decomposability, despite this being one of the more consistently supported ideas (Q1, Q2).
- No evidence-sufficiency-based stopping rule — the skill's stopping condition is really just "the fixed budget is exhausted," not "the required claims are now each supported," which is the specific pattern that 5 independent papers in Q2 show working (and Anthropic's own early failure mode was literally "continuing when already had sufficient results" / "scouring endlessly for nonexistent sources" — both symptoms of the exact stopping-rule gap here).
- No separate citation/URL-liveness verification pass — Q3's single strongest intervention (6-79x reduction in bad URLs) has no analog in the current pipeline; the skill relies on the initial fetch being right rather than re-checking.
- No claim-level structure in the output template — findings are bullet points with a `[source]` tag, not atomic claims each individually gradeable/verifiable, which is what the better-evidenced Q3/Q6 alternatives are built on.
- No execution-in-the-loop option at all for checkable technical claims (Q7's best-evidenced, most positive intervention in this scan) — for a skill that frequently answers "does tool/library X do Y," a bounded one-command execution check is directly applicable and currently entirely absent.
- No source-independence/common-origin check — nothing catches "these 3 sources are all restating the same original post," which Q5's retrieval-collapse evidence says can make source quality look fine in aggregate while actually being thin.
- No adversarial-evidence-seeking step for load-bearing claims — Q4 evidence disconfirms the fashionable "red-team persona" version of this, but does support a narrower "actively search for disconfirming evidence on this specific claim" step, which the skill doesn't have in either form.
