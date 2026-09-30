---
topic: reddit-reliability-as-evidence-source
tags: area:research-skill, research
source_provenance: /research invocation (topic supplied), arm A test run 2026-09-30; saved to scratchpad instead of docs/research/ by instruction
---

# Reddit as an evidence source for practitioner experience (2025-2026)

Classification: decision validation (use Reddit or not, with what safeguards) with a comparison component (HN / Stack Overflow / GitHub).

Channel tags used below: [Ch1 Users], [Ch2 Specialists], [Ch3 Data], [Ch4 Adversarial]. Every number traces to a source retrieved in this run (paper index abstract/passages, HN Algolia JSON, `gh issue view`, Firecrawl search excerpt or summary scrape). Anything not retrieved is marked **Prior**.

## Summary

Recommendation: keep Reddit, but only as a *lead generator*, never as standalone evidence — which is the posture the skill already has (snippet-only, `[snippet]` citation). Do not upgrade it to a fetched, quotable source, and do not drop it entirely. The measured share of machine-generated text on Reddit is low (roughly 1-3% overall, peaks of 6-9% in individual subreddit-months, through 2024; +2-3 pp differential rise in informational communities through Nov 2025), but those numbers are lower bounds because current detectors barely beat chance on short comments from modern models. The larger risk for an agent is not average prevalence but *targeting*: aged accounts and per-comment placement are sold commercially, and a single 13-word insertion on one frequently-retrieved UGC page was enough to get attacker content cited in 38-51% of deep-research reports in simulation. Neither AI-text detection nor account-age heuristics are usable safeguards; corroboration against a non-UGC, verifiable artifact is. No retrieved study measures bots or astroturfing in programming/technology subreddits specifically — that part of the question is answered only by anecdote and by non-tech cases, and is a stated gap. HN, Stack Overflow and GitHub are not clean alternatives: each has a documented, different failure mode.

## Key Findings

### (1) Measured prevalence of bot / AI-generated content on Reddit

- **Machine-generated text is "marginally present" overall, with peaks up to ~9% in specific communities and months.** Method: 51 large subreddits hand-picked from the top-1000 in 5 categories, Pushshift dumps Jan 2022 - Dec 2024, 38,074,021 comments + 4,073,586 submissions, a statistical MGT detector tuned to a "very conservative estimate". Peak comment shares by category: information-seeking 6.33% (r/askscience, 2023-07), social support 7.69%, identity 8.46%, discussion 1.28%, chit-chat 3.13%; submissions peak ~7%. MGT concentrates in technical-knowledge and social-support subreddits; about 2% of active users account for all detected MGT; level is stable after the Nov 2022 - Sep 2023 surge; MGT gets engagement comparable to human text. Limitation: no programming subreddit in the sample; single detector. [Ch3 — arXiv:2510.07226]
- **Reddit's AI-attribution rate moved from 1.31% to 2.45% (Jan 2022 - Jul 2024), while Medium went 1.77% -> 37.03% and Quora 2.06% -> 38.95%.** Method: 982,440 Reddit comments (2.4M posts across the three platforms), a trained detector (OSM-Det, accuracy 0.979 / F1 0.980 on its own benchmark of 12 LLMs), measured false-positive rate on Reddit 1.70%. Read honestly: Reddit's measured rate sits within ~0.8 pp of the detector's own false-positive rate, so this is "indistinguishable from near-zero by this instrument", not "2.45% is AI". The paper reports higher rates in technical fields (Technology, Software Development) and credits Reddit's resistance to subreddit culture, moderation and downvoting. [Ch3 — arXiv:2412.18148]
- **Through Nov 2025, AI-written posts rose only 2-3 pp more in informational communities than in hobby controls; comments show no differential rise.** Method: 26 informational vs 90 hobby control communities (151 total), up to 100 posts + 100 comments per community-month via Arctic Shift, windows Jan 2021 - Nov 2022 vs Jan 2024 - Nov 2025, 274,411 posts and 223,775 comments scored with Fast-DetectGPT and Binoculars, a difference-in-differences design that cancels detector false positives; texts under 200 chars excluded. [Ch3 — arXiv:2609.12447]
- **Those are lower bounds: the detectors are nearly blind on comments from current models.** Same paper's calibration: Fast-DetectGPT AUROC on posts 0.966 (GPT-4o) down to 0.875 (GLM-5.2), but on comments only GPT-4o is detectable (0.794), the others 0.664 / 0.585 / 0.552; Binoculars on comments 0.939 (GPT-4o), 0.850 (Claude Sonnet 4), 0.768 (DeepSeek-V3), 0.698 (GLM-5.2). The abstract's own hedge: humans still answer "as far as detection can tell". [Ch3 — arXiv:2609.12447]
- **Bot detection on Reddit is weak as a separate matter.** BotBuster reports F1 60.04 on a Reddit dataset. A census of declared/identified bots (3,389 bots, 18 types) finds bot numbers and activity peaked around COVID and declined before the 2023 API changes — but it covers self-identifying utility bots, not covert LLM accounts. Behaviour beats content for finding manipulation: on 12,064 Reddit users incl. 99 IRA-linked accounts, behaviour-based classifiers reach macro-F1 94.9% vs 91.2% for text embeddings; on Twitter, account-history features reach AUC 0.977 vs 0.830 content-only, and content features fall below chance under adversarial rewriting. [Ch3 — arXiv:2207.13658, arXiv:2607.23941, arXiv:2602.02838, arXiv:2606.26127]
- **Moderators confirm the detection gap qualitatively.** 15 interviews with moderators of subreddits that restrict AI content: enforcement relies on "time-intensive and inaccurate detection heuristics". [Ch3 — arXiv:2311.12702]
- **Human accusations of "AI slop" are not a usable signal either.** 25M HN + Reddit comments 2023-2026: pejorative AI-accusation share rose >10x on both platforms, but text features that actually separate AI from human prose do not predict which human text gets accused; accusations function as social gatekeeping. [Ch3 — arXiv:2606.12073]. Echoed by an HN commenter: no reliable "tell", em-dash heuristics produce false accusations. [Ch1 — HN 47300329]

### (2) Documented astroturfing / manipulation — and the tech-subreddit gap

- **No retrieved source measures astroturfing in programming or technology subreddits.** This is the weakest part of the report; everything below is adjacent evidence. [gap — all channels]
- **A commercial supply side exists.** The article behind HN 49877678, as quoted in the thread: REDCmts sells one Reddit comment for $9.99 and 100 for $699.99 from "real, aged accounts"; Soar describes accounts "aged and manually warmed" for weeks; Bazzly advertises automated replies to posts that look like someone shopping. [Ch1 — HN 49877678, quoting petervijeh.com]. Vendor self-descriptions, not audited volumes.
- **The one data analysis retrieved is inconclusive, and not about software.** 51,129 comments in six knife subreddits: the 5% most brand-heavy accounts wrote 11.3% of brand mentions in buying threads vs 7.9% expected by chance (one brand: 31% vs 8%), but those accounts average 4.5 years old across 66 subreddits, same as the comparison group — "the data shows concentration and not who paid for it". HN commenters add: results not statistically significant by the author's own admission, article appears LLM-drafted, and brand loyalty is not paid astroturfing. [Ch1 — petervijeh.com summary scrape; HN 49877678]
- **Documented covert-LLM manipulation on Reddit exists outside tech.** The discontinued r/ChangeMyView field experiment used undisclosed AI accounts that adopted fabricated identities in more than two thirds of comments. [Ch3 — arXiv:2606.05256]. Peptide vendors spammed the biohackers subreddit specifically to steer ChatGPT and Google AI answers. [Ch2 — 404 Media, search excerpt only]
- **Practitioner anecdote on tech specifically is split.** "Niche topics like linux feel somewhat safe from bots" while popular subs are bad (asksomeoneelse); AI coding agents are astroturfed, including from long-lived accounts with moderator support (asg172); one commenter suspects "I don't touch code anymore" comments on HN itself are bots (gwbas1c). Opinions, n=1 each. [Ch1 — HN 49877678]
- **The cheap vetting heuristics are defeated.** Thin / young account checks "no longer an indicator" because bot accounts build plausible histories in local and sports subreddits (nomel); the four indicators in the article are trivially engineered around (rithdmc); Reddit now lets users hide post history (ohm/zergrush); moderator bans of unfavourable opinions produce survivorship bias (nomilk); spotting the obvious cases breeds false confidence — toupee fallacy (DharmaPolice). [Ch1 — HN 49877678]
- **For an agent the relevant number is attack success, not prevalence.** WARP attack on deep-research agents (STORM, Co-STORM, OmniThink; simulated, no live content modified): 17-23% of retrieved URLs are UGC; a single UGC page is retrieved in up to 48% of queries in a topic cluster; one poisoned URL with ~13 words is retrieved in 57-76% of runs and mentioned in 38-51% of reports; appended to a full Reddit thread at <4% of retrieved content it still reaches 30-53%. Input/output anomaly filters do not reliably detect it. Gemini Deep Research cites UGC at 12.1% on the tested topics. [Ch3 — arXiv:2605.24245; Ch2 — 404 Media summary scrape of the same study, which adds "nearly half the citations in AI queries come from UGC" (journalist's paraphrase, not verified against the paper)]
- **Independent replication of the mechanism on product recommendations.** FORGE: across 12 LLMs a single polluted page yields fooled rates up to 27%, top-3 replacement 73.8%; reasoning does not help and "often generates spurious social proof"; a skepticism prompt can make it worse; credibility re-ranking removes about a sixth of fakes. [Ch3 — arXiv:2606.13610]

### (3) Does forum content carry knowledge not found in official docs?

- **Evidence is indirect and mostly about Stack Overflow, not Reddit.** Papers motivate mining SO on the grounds that official docs are "often lengthy, complex, or incomplete" and developers turn to SO; a user study with 30 Android developers evaluated summaries built from 3.6M SO posts. [Ch3 — arXiv:2509.05749, arXiv:2401.11361]
- **Pain-point studies find content docs do not cover.** 495 SO posts + 9,116 GitHub issues/PRs on federated-learning frameworks: environment setup, API breakage and high unresolved rates; 2,874 SO discussions on the OpenAI API. [Ch3 — arXiv:2607.19621, arXiv:2505.04084]
- **Researchers treat Reddit/HN as a legitimate practitioner-evidence corpus.** 1,154 Reddit + HN posts qualitatively coded on AI slop; 1,700+ Reddit posts thematically analysed; 437,317 threads from r/webdev, r/androiddev, r/iOSProgramming; the GitHub AI-slop study also draws on Reddit, mailing lists and blogs for practitioner accounts. That is revealed preference, not proof of unique knowledge. [Ch3 — arXiv:2603.27249, arXiv:2309.13684, arXiv:2304.07650, arXiv:2607.04003]
- **Counter-evidence (source conflict).** Blocking eight UGC domains (Reddit, YouTube, Facebook, Medium, Instagram, TikTok, Quora, Wikipedia) in Co-STORM over 176 queries dropped the rubric score only 4.30 -> 4.26 and information diversity 0.604 -> 0.585 — "negligible impact under these standard metrics" — while the same paper's abstract says dropping UGC "degrades the quality of generated reports". Both statements are in the paper; the queries are consumer topics (finance, antivirus, restaurants), not developer tooling, and the rubric is an LLM judge. [Ch3 — arXiv:2605.24245]
- Net: the claim "forums hold knowledge docs lack" is supported for SO/GitHub issues on software; for Reddit specifically it was not measured by anything retrieved here.

### (4) Hacker News, Stack Overflow, GitHub on the same risks

- **Hacker News — moderated by policy and by hand, not measured.** Guidelines now say not to post generated / AI-edited comments [Ch1 — HN 47340079]; a moderator states that as a general rule accounts posting generated comments get banned, that it is not hard and fast, and that it depends on users emailing reports; one user reports hitting "We're temporarily restricting Show HNs"; vote-ring detection is rumoured, not documented [Ch1 — HN 47300329]. No prevalence measurement for HN was found (one targeted paper search returned none). HN is also a promotion channel by design: at least 19% of AI developers in a 2,195-story sample promoted their own GitHub projects there, with measurable star/fork gains [Ch3 — arXiv:2506.12643]. Advantage for an agent: full comment trees via a public API, so claims can be read in context rather than as snippets.
- **Stack Overflow — explicit AI ban, but the supply of fresh answers is shrinking and the archive has its own defects.** SO banned ChatGPT answers six days after release and enforces a no-AI-content policy [Ch3 — arXiv:2307.09765; Ch1 — HN 48956949 excerpt]. Weekly posts fell 16% after ChatGPT relative to Russian/Chinese counterparts and math forums, growing over time [Ch3 — doi:10.1093/pnasnexus/pgae400, arXiv:2307.07367]; a second study finds significant declines in SO visits and questions while comparing against Reddit developer communities [Ch3 — doi:10.1038/s41598-024-61221-0, abstract only; body passages not retrievable]. Human SO answers beat ChatGPT answers by roughly 10% [Ch3 — arXiv:2307.09765]. Pre-AI defects: 58.4% of obsolete answers were probably already obsolete when posted and only 20.5% were ever updated [arXiv:1903.12282]; insecure answers had more views (36,508 vs 18,713) and higher score (14 vs 5) than secure ones, and 34% of posts by highly reputable users were insecure [arXiv:1901.01327]; 66% of 153 sampled code clones were outdated [arXiv:1806.07659]; 69 vulnerable C++ snippets propagated into 2,859 GitHub projects [arXiv:1910.01321]. So score and reputation are not correctness signals.
- **GitHub issues / discussions — the AI problem is inbound low-effort contributions, and maintainers cannot spot them by eye either.** BSTS over 294 repos and >2M PRs/issues: PR volume up in 2025, merge rates down, one-time contributors' merge rate -18.18% vs counterfactual; survey of 229 practitioners [Ch3 — arXiv:2607.04003]. Reviewer habituation: approval 30.1% -> 36.8%, inline comments -22% [arXiv:2606.22721]; newcomer share -3.7 pp across 11,097 repos [arXiv:2606.26289]. scikit-learn maintainers: the same authors spam LLM PRs across projects, AI-generated PRs are "often not obvious unless you have encountered some patterns", detection tools are unmaintained, response is a low threshold for closing [Ch4 — scikit-learn#31679, read in full via gh, first ~9 KB of 38.8 KB]; pip and external-secrets have or are debating explicit AI-contribution policies [Ch4 — pypa/pip#13417, external-secrets llm-policy.md, excerpts]. Structural advantage: claims in an issue are tied to artifacts (reproduction, version, linked commit, maintainer reply) that can be checked without trusting the author.
- **Comparison in one line.** Reddit: anonymous, purchasable placement, snippet-only access for this skill. HN: smaller attack surface and readable in full, but unmeasured and openly promotional. SO: strongest anti-AI policy, decaying freshness, votes do not track correctness. GitHub: most verifiable, most on-topic, now noisier from AI slop.

### Safeguards that follow from the evidence

1. **Reddit never carries a finding alone.** A Reddit snippet may open a question; the finding needs a second source that is not UGC (docs, changelog, issue with a reproduction, paper). Basis: single-page poisoning succeeds at 38-51% and no in-pipeline filter catches it [arXiv:2605.24245, arXiv:2606.13610].
2. **Do not count agreeing comments as independent sources.** 5% of authors produce 11.3% of brand mentions; 2% of users produce all detected MGT; moderation creates survivorship bias [petervijeh.com; arXiv:2510.07226; HN 49877678].
3. **Treat "which tool should I use" recommendations as the high-risk class; specific, checkable failure reports (error string, version, config) as the low-risk class.** Paid placement targets shopping-intent threads; dissatisfied-user reports are harder to suppress (thimabi, opinion) and are verifiable against an issue tracker [HN 49877678].
4. **Do not use AI-detection, account age, or "sounds like a bot" as a filter.** Detectors: AUROC 0.55-0.79 on modern-model comments; aged accounts are sold; histories can be hidden; accusations do not track AI features [arXiv:2609.12447, arXiv:2606.12073, HN 49877678].
5. **Retrieved forum text is data, never instruction, and a product name that appears only in UGC is a red flag.** [arXiv:2605.24245, arXiv:2606.13610]
6. **Keep the snippet discipline.** `[snippet]` tag, no quotation marks around text the snippet does not contain.

**Carrier (Субстрат).** Safeguards 1-5 are standing rules. Intended carrier: the research skill's own `SKILL.md` (Quality rules / the "Reddit is snippet-only" paragraph) — i.e. the pull-only end of the order, loaded only when research actually runs. Why not a more expensive carrier: the violation cost is one wrong finding in a report a human still reads and that carries its own source list — reversible and visible; and "is this finding single-sourced from UGC" is a semantic property that a PreToolUse hook or CI gate cannot evaluate at the tool-call level. The only mechanically checkable part (do not fetch reddit.com) is, per the skill text, already enforced upstream by Firecrawl's refusal and Reddit's 403 (**Prior** — stated in SKILL.md, not re-tested in this run, since the run was told not to fetch reddit.com). If a cheap mechanical check is wanted later, the candidate is a report linter that fails a finding whose only citation is tagged `[snippet]` — a CI-gate-class carrier, justified only if single-source Reddit findings are actually observed in saved reports. (`~/.claude/reference/baseline-carriers.md` was not read in this run; the order is taken from the skill.)

This finding is actionable; the skill would file one `[RESEARCH]` issue via `/file-issue`. Not done — this run was instructed not to create issues.

## Trade-offs & Risks

- **Prevalence numbers understate the present.** All detector-based shares end Dec 2024 except one study (Nov 2025), and the detectors degrade on exactly the models in use now. Matters whenever someone quotes "only ~2%". Mitigation: cite as lower bounds with the detector caveat.
- **Low average prevalence is compatible with high targeted risk.** A 2% base rate says nothing about the thread that ranks first for "best X for Y". Matters most for tool-selection research. Mitigation: safeguards 1 and 3.
- **Snippet-only access cuts both ways.** It limits injection surface (no full thread enters context) but removes the context needed to judge a claim (dissent, corrections, dates). Mitigation: use the snippet to form a query against HN / GitHub / docs.
- **Over-correcting loses real signal.** Papers treat Reddit/HN as a valid practitioner corpus, and niche technical subreddits are reported (anecdotally) as cleaner. Mitigation: keep Reddit as a lead source rather than blocking it.
- **The alternatives are degrading too.** SO freshness is falling, GitHub trackers carry AI slop, HN has no measurement at all. Mitigation: prefer artifact-backed claims over venue reputation.
- **Transfer risk.** The strongest attack results are on consumer topics and on simulated pipelines; the one astroturf dataset is knife subreddits. Developer-tool subreddits may differ in either direction.

## Alternatives

- **Drop Reddit entirely (domain blocklist).** Blocks the attack outright and cost only 0.04 rubric points in the one measurement available — but that measurement is on consumer queries with an LLM judge, and the same paper says quality degrades. Reasonable for product-recommendation questions; too blunt for "what breaks in practice" questions.
- **Fetch full Reddit threads and quote them.** Rejected: widens the injection surface the WARP study exploits, and per the skill text is technically blocked anyway (Prior, not re-tested).
- **Filter Reddit content with an AI-text detector or account-history check.** Rejected: detectors near chance on comments, account age is purchasable, history is hideable; behavioural signals work in papers but need platform-side data the agent does not have.
- **Shift Channel 1 weight to HN (Algolia) + GitHub issues, Reddit as tie-breaker/lead only.** This is effectively what the skill does now; the evidence supports keeping it.
- **Weight only negative, specific reports from Reddit.** Attractive heuristic from a practitioner comment; unvalidated, and competitor-driven negative astroturfing is not excluded by anything retrieved.

## Channel gaps

- **Channel 2 (Specialists): gap.** One search returned two results, both from the same outlet (404 Media); one was read via summary scrape, the other is excerpt-only. That is <2 independent specialist sources. The search budget (2-3 `firecrawl_search`) was exhausted, so no second angle was run. Proposed: waiver, or an extended search with a different domain list (e.g. engineering blogs of search/agent vendors, moderator write-ups).
- **Channel 4 (Adversarial): met for GitHub (3 sources, 1 read in full), not run for the non-GitHub half** — the skill's optional web query (`postmortem OR 'considered harmful'`) would have been a fourth `firecrawl_search`.
- **Channel 1 (Users): met** — one HN thread read in full via Algolia (388 nodes), three more HN threads via search (one with a large excerpt). No Reddit result surfaced in any search, so there are no `[snippet]` citations; per the skill this is not a gap.
- **Channel 3 (Data): met**, with the content gaps named above: nothing on programming subreddits specifically, nothing quantitative on HN, item (3) indirect.

## Sources

Paper URLs are the canonical arXiv/DOI addresses for IDs returned by the Firecrawl paper index; content was read through that index (abstracts, and body passages where noted), not fetched from arxiv.org.

1. Machines in the Crowd? Measuring the Footprint of Machine-Generated Text on Reddit — https://arxiv.org/abs/2510.07226 — prevalence, method, per-category peaks, 2% of users (abstract + passages)
2. Are We in the AI-Generated Text World Already? — https://arxiv.org/abs/2412.18148 — Reddit AAR 1.31% -> 2.45%, FPR 1.70%, Medium/Quora contrast (abstract + passages)
3. Informational Help-Seeking on Reddit Did Not Decline After ChatGPT — https://arxiv.org/abs/2609.12447 — diff-in-diff through Nov 2025, detector AUROC on comments (abstract + passages)
4. "That's AI Slop, You Bot!" — https://arxiv.org/abs/2606.12073 — accusations do not track AI features (abstract)
5. Mapping the Reddit Bot Ecosystem — https://arxiv.org/abs/2607.23941 — declared-bot census (abstract)
6. BotBuster — https://arxiv.org/abs/2207.13658 — Reddit bot-detection F1 60.04 (abstract)
7. Beyond Content: Behavioral Policies Reveal Actors in Information Operations — https://arxiv.org/abs/2602.02838 — behaviour vs text for IRA accounts on Reddit (abstract)
8. Account-History Features for Social Bot Detection in the Era of LLMs — https://arxiv.org/abs/2606.26127 — content features collapse under rewriting (abstract; Twitter data)
9. "There Has To Be a Lot That We're Missing": Moderating AI-Generated Content on Reddit — https://arxiv.org/abs/2311.12702 — moderator interviews (abstract; via related-papers walk)
10. How Far Did They Go? (r/ChangeMyView covert-LLM experiment) — https://arxiv.org/abs/2606.05256 — documented covert manipulation (abstract)
11. Deep-Research Agents Can Be Poisoned via User-Generated Content — https://arxiv.org/abs/2605.24245 — WARP attack rates, UGC share, blocking-defense table (abstract + passages)
12. One Polluted Page Is Enough (FORGE) — https://arxiv.org/abs/2606.13610 — fooled rates, failed defenses (abstract)
13. Large language models reduce public knowledge sharing on online Q&A platforms — https://doi.org/10.1093/pnasnexus/pgae400 (also https://arxiv.org/abs/2307.07367) — SO -16% weekly posts (abstract)
14. The consequences of generative AI for online knowledge communities — https://doi.org/10.1038/s41598-024-61221-0 — SO decline vs Reddit developer communities (abstract only; passage read returned nothing)
15. ChatGPT vs human answers on Stack Overflow — https://arxiv.org/abs/2307.09765 — human answers ~10% better, ban after six days (abstract)
16. Obsolete answers on Stack Overflow — https://arxiv.org/abs/1903.12282 — 58.4% / 20.5% (abstract)
17. Insecure answers on Stack Overflow — https://arxiv.org/abs/1901.01327 — views, score, reputation vs security (abstract)
18. Toxic code snippets on Stack Overflow — https://arxiv.org/abs/1806.07659 — 66% of 153 clones outdated (abstract)
19. Vulnerable C++ snippets from SO in GitHub — https://arxiv.org/abs/1910.01321 — 69 snippets, 2,859 projects (abstract)
20. SO-mining / documentation-gap motivation — https://arxiv.org/abs/2509.05749 and https://arxiv.org/abs/2401.11361 — docs incomplete, 30-developer study (abstracts)
21. FL framework pain points — https://arxiv.org/abs/2607.19621; OpenAI API discussions — https://arxiv.org/abs/2505.04084 — forum/issue content beyond docs (abstracts)
22. "An Endless Stream of AI Slop" — https://arxiv.org/abs/2603.27249; Reddit thematic studies — https://arxiv.org/abs/2309.13684, https://arxiv.org/abs/2304.07650 — Reddit/HN used as practitioner corpora (abstracts)
23. AI Slop is DDoSing Open Source — https://arxiv.org/abs/2607.04003 — GitHub PR volume/merge rates, survey of 229 (abstract)
24. Reviewer habituation — https://arxiv.org/abs/2606.22721; newcomer share — https://arxiv.org/abs/2606.26289; agent PRs — https://arxiv.org/abs/2601.00753, https://arxiv.org/abs/2509.14745 — GitHub-side effects (abstracts)
25. Social Media Reactions to Open Source Promotions (HN) — https://arxiv.org/abs/2506.12643 — 19% self-promotion on HN (abstract)
26. HN: Does Reddit have an astroturfing problem? What the data suggests — https://news.ycombinator.com/item?id=49877678 — 387-comment thread read in full via Algolia; vendor prices, heuristic failures, practitioner opinions
27. Does Reddit have an astroturfing problem? (Peter Vijeh) — https://www.petervijeh.com/projects/reddit-astroturf — knife-subreddit concentration numbers (summary scrape + page metadata)
28. HN guideline thread: Don't post generated/AI-edited comments — https://news.ycombinator.com/item?id=47340079 — HN policy (search excerpt)
29. Ask HN: Please restrict new accounts from posting — https://news.ycombinator.com/item?id=47300329 — moderator statement on bans, Show HN restriction, no reliable tell (large search excerpt, sliced)
30. HN: What AI did to stackoverflow in a graph — https://news.ycombinator.com/item?id=48956949 — SO AI policy (search excerpt)
31. 404 Media: It Is Trivially Easy to Use Reddit to Manipulate AI Search — https://www.404media.co/it-is-trivially-easy-to-use-reddit-to-manipulate-ai-search-research-suggests/ — journalist account of source 11 (summary scrape)
32. 404 Media: Companies Are Using Reddit to Manipulate ChatGPT and Google AI Search — https://www.404media.co/companies-are-using-reddit-to-manipulate-chatgpt-and-google-ai-search/ — peptide/biohackers case (search excerpt only)
33. scikit-learn#31679 — https://github.com/scikit-learn/scikit-learn/issues/31679 — maintainers on undetectable LLM PRs (gh, first ~9 KB of thread)
34. pypa/pip#13417 — https://github.com/pypa/pip/issues/13417 — AI PR policy debate (search excerpt)
35. external-secrets LLM usage policy — https://github.com/external-secrets/external-secrets/blob/8ccab0cfc8f78447d8b8f3976434995caefacf25/docs/contributing/llm-policy.md — policy text (search excerpt)

Surfaced but not read (titles only, HN Algolia hits — leads, not evidence): https://rmoff.net/2025/12/01/using-graph-analysis-with-neo4j-to-spot-astroturfing-on-reddit/ ; https://rushter.com/blog/astroturfing/ ; https://www.bendangelo.me/2026/02/02/llm-astroturfing-is-killing-reddit/ ; https://mentioned.to/research

## Confidence: 60/100

The prevalence picture and the agent-poisoning risk rest on three or more independent measured sources each, but the numbers are detector-limited lower bounds, nothing retrieved measures programming subreddits, the docs-vs-forum question is answered only indirectly, and the specialist channel has a single outlet.

## Run log

External tool calls, in order. Firecrawl tool names are prefixed `mcp__<connector-id>__` (the per-account connector id is left out). Order and arguments were checked against this run's transcript.

1. firecrawl_research_search_papers — "prevalence of AI-generated text on Reddit measurement study LLM-generated posts and comments" (k=5, from=2024-01-01)
2. firecrawl_research_search_papers — "Reddit bots astroturfing coordinated inauthentic behavior detection empirical prevalence" (k=5, from=2023-01-01)
3. firecrawl_research_search_papers — "developer forum knowledge not found in official API documentation Stack Overflow empirical study" (k=5)
4. firecrawl_research_search_papers — "Stack Overflow activity decline after ChatGPT and AI-generated answers quality empirical evaluation" (k=5, from=2023-01-01)
5. firecrawl_search — "AI-generated spam issues pull requests low-quality LLM slop maintainers ban" (categories=["developer"], limit=3) — FAILED: rate limit exceeded (19 req/min consumed)
6. curl (Bash) — https://hn.algolia.com/api/v1/search?query=reddit%20bots%20AI-generated%20astroturfing&tags=story&hitsPerPage=5
7. curl (Bash) — https://hn.algolia.com/api/v1/search?query=reddit%20astroturfing&tags=story&hitsPerPage=5
8. curl (Bash) — https://hn.algolia.com/api/v1/items/49877678
9. firecrawl_search — same query and arguments as #5 — FAILED: rate limit exceeded (26 req/min consumed)
10. firecrawl_research_search_papers — "AI-generated pull requests and issues on GitHub open source maintainers burden empirical study" (k=5, from=2024-06-01)
11. firecrawl_research_search_papers — "undisclosed promotion marketing accounts product recommendations Reddit subreddits LLM-powered bots persuasion experiment" (k=5, from=2024-01-01)
12. firecrawl_research_read_paper — arxiv:2510.07226 (k=5)
13. firecrawl_research_read_paper — arxiv:2609.12447 (k=5)
14. firecrawl_search — same query and arguments as #5 — FAILED: rate limit exceeded (27 req/min consumed)
15. curl (Bash) — https://hn.algolia.com/api/v1/search?query=reddit%20AI%20bots%20changemyview%20experiment&tags=story&hitsPerPage=5 — 0 hits
16. firecrawl_search — same query and arguments as #5 — succeeded
17. gh (Bash) — gh issue view 31679 --repo scikit-learn/scikit-learn --comments
18. firecrawl_search — "AI-generated answers comments bots astroturfing voting ring moderation policy real experience" (includeDomains=["news.ycombinator.com","stackoverflow.com","github.com"], limit=3) — succeeded; result 106,277 chars, written to tool-results file
19. firecrawl_research_search_papers — "Stack Overflow obsolete or incorrect answers prevalence; reliability of crowd-sourced programming answers; insecure code snippets" (k=5)
20. firecrawl_research_search_papers — "developer discussions on Reddit programming subreddits as data source for software engineering research: tool experience, undocumented knowledge" (k=5, from=2022-01-01)
21. firecrawl_search — "Reddit AI bots astroturfing marketing developer tools subreddits lessons learned" (includeDomains=["simonwillison.net","danluu.com","404media.co","pluralistic.net","lethain.com"], tbs="qdr:y", limit=3) — succeeded, 2 results
22. firecrawl_research_search_papers — "social bots prevalence on Reddit estimate share of bot accounts or bot-authored comments" (k=5, from=2022-01-01)
23. firecrawl_research_read_paper — arxiv:2412.18148 (k=4)
24. firecrawl_research_search_papers — "injecting promotional content into Reddit, Quora, Wikipedia to manipulate AI search engines and LLM product recommendations (generative engine optimization attack)" (k=5, from=2025-01-01)
25. firecrawl_research_search_papers — "Hacker News AI-generated comments or submissions prevalence measurement; bot or LLM accounts on Hacker News" (k=5, from=2024-01-01)
26. firecrawl_research_read_paper — pmcid:PMC11074245 (k=3) — returned 0 passages
27. firecrawl_scrape — https://www.404media.co/it-is-trivially-easy-to-use-reddit-to-manipulate-ai-search-research-suggests/ (formats=["summary"], onlyMainContent=true, maxAge=604800000)
28. firecrawl_scrape — https://www.petervijeh.com/projects/reddit-astroturf (formats=["summary"], onlyMainContent=true, maxAge=604800000)
29. firecrawl_research_read_paper — arxiv:2605.24245 (k=4)
30. firecrawl_research_related_papers — seed arxiv:2510.07226 (mode=similar, k=6)

Totals per tool (30 external calls):

| Tool | Calls | Note |
|---|---|---|
| firecrawl_search | 6 | 3 succeeded (1 developer-index, 2 includeDomains), 3 failed on rate limit |
| firecrawl_scrape | 2 | both summary format, both cache hits |
| firecrawl_research_search_papers | 11 | |
| firecrawl_research_read_paper | 5 | 1 returned no passages |
| firecrawl_research_related_papers | 1 | |
| curl to hn.algolia.com (Bash) | 4 | 3 search, 1 items |
| gh issue view (Bash) | 1 | |
| WebFetch | 0 | |
| WebSearch | 0 | |
| firecrawl_agent / firecrawl_agent_status | 0 | banned by the skill |
| reddit.com fetches | 0 | |

Local, non-external calls (not counted above): Read of SKILL.md x2 (second after a context reset); ToolSearch x2 to load Firecrawl tool schemas; Bash/python x2 slicing the saved 106 KB search result; Bash x3 reading this run's own transcript to verify this log; Write x1 for this file.
