# Citation audit — arm-a-report.md

Audited: `scratchpad\arm-a-report.md`, sections Summary, Key Findings (1)-(4), Safeguards, Sources. Run log, Channel gaps, Carrier paragraph, front matter, Trade-offs and Alternatives were not audited and not used as evidence.

Audit date: 2026-09-30. Every cited source was re-fetched independently (arXiv abs + HTML/PDF body, HN Algolia items API, `gh issue view`, DOI content negotiation, page scrapes). reddit.com was not fetched.

## How sources were read

| Source type | How | Depth |
|---|---|---|
| arXiv (31 IDs) | `arxiv.org/abs/<id>` for title/abstract; `arxiv.org/html/<id>` or PDF (`pdftotext`) for body | Body read for 2510.07226, 2412.18148, 2609.12447, 2605.24245 (v1 and v2), 2606.05256 (PDF), 2207.13658, 2307.07367, 2307.09765, 2311.12702, 2607.23941, 2602.02838, 2607.04003, 2606.22721, 2606.26289, 1901.01327 and others with HTML. **Abstract only** (no arXiv HTML available; the claims checked are all abstract-level): 2606.12073, 2606.26127, 1903.12282, 1806.07659, 1910.01321, 2509.05749, 2304.07650. 2606.13610 checked against abstract (all report claims are verbatim abstract content). |
| HN (4 threads) | `hn.algolia.com/api/v1/items/<id>`, full comment tree, searched by author and regex | Full |
| petervijeh.com | raw HTML + stripped text | Full |
| 404 Media (2 URLs) | firecrawl scrape | Article 1 full; article 2 headline + intro (rest paywalled) |
| GitHub | `gh issue view --comments` + `--json body`; policy file via gh api | Full |
| DOIs (2) | `doi.org` CSL-JSON (title, journal, abstract) | Abstract |

## arXiv version note (affects bullets 2.7 and 3.4)

The report cites `arXiv:2605.24245` without a version. v1 (22 May 2026) and v2 (3 Sep 2026) differ. The report mixes both:

| Report text | v1 | v2 (current) |
|---|---|---|
| "a single UGC page is retrieved in up to 48% of queries in a topic cluster" | verbatim ("within a topic cluster, individual UGC pages are retrieved in up to 48% of queries") | absent |
| "negligible impact under these standard metrics" | verbatim ("Table 15 shows that blocking UGC has negligible impact under these standard metrics") | replaced by "Measured quality changes are small" |
| "retrieved in 57-76% of runs" | not in abstract (Table: exposure 60.6 / 76.2 / 57.4) | abstract, verbatim range |
| "degrades the quality of generated reports" | abstract says "degrades output quality" | abstract, verbatim |

Each quoted phrase exists in some version, so these rows are rated SUPPORTED, but no single version of the paper contains all four.

## Claim table

Verdicts: SUPPORTED / PARTIAL / UNSUPPORTED / UNCHECKABLE. One row = one atomic claim.

### Summary

| # | Bullet | Claim (report wording) | Source | Verdict | Note |
|---|---|---|---|---|---|
| Sum.1 | Summary | MGT share "roughly 1-3% overall" | arXiv:2412.18148 | SUPPORTED | 1.31% -> 2.45% |
| Sum.2 | Summary | "peaks of 6-9% in individual subreddit-months, through 2024" | arXiv:2510.07226 | SUPPORTED | 6.33 / 7.69 / 8.46; data to Dec 2024 |
| Sum.3 | Summary | "+2-3 pp differential rise in informational communities through Nov 2025" | arXiv:2609.12447 | SUPPORTED | Posts only; the same paper finds no rise in comments (the finding bullet says so, the Summary does not) |
| Sum.4 | Summary | "those numbers are lower bounds because current detectors barely beat chance on short comments from modern models" | arXiv:2609.12447 | PARTIAL | See list below. Calibration covers two detectors, not the ones that produced the 1-3% / 6-9% numbers; "barely beat chance" holds for Fast-DetectGPT on 3 of 4 models only |
| Sum.5 | Summary | "aged accounts and per-comment placement are sold commercially" | petervijeh.com | SUPPORTED | Vendor self-descriptions quoted in the article |
| Sum.6 | Summary | "a single 13-word insertion on one frequently-retrieved UGC page was enough to get attacker content cited in 38-51% of deep-research reports in simulation" | arXiv:2605.24245 | SUPPORTED | Matches v2 abstract wording. Body of both versions defines 38-51% as mention rate *conditional on exposure*; unconditional 1-URL mention is 30.7 / 37.1 / 21.7% (Table "SERP-snippet attack results") |

### (1) Measured prevalence

| # | Bullet | Claim (report wording) | Source | Verdict | Note |
|---|---|---|---|---|---|
| 1.1a | 1.1 | MGT "marginally present" | arXiv:2510.07226 | SUPPORTED | verbatim |
| 1.1b | 1.1 | peaks up to ~9% | arXiv:2510.07226 | SUPPORTED | abstract "up to 9%"; table max 8.46 |
| 1.1c | 1.1 | 51 large subreddits | arXiv:2510.07226 | SUPPORTED | |
| 1.1d | 1.1 | hand-picked from the top-1000 | arXiv:2510.07226 | SUPPORTED | |
| 1.1e | 1.1 | 5 categories | arXiv:2510.07226 | SUPPORTED | |
| 1.1f | 1.1 | Pushshift dumps Jan 2022 - Dec 2024 | arXiv:2510.07226 | SUPPORTED | |
| 1.1g | 1.1 | 38,074,021 comments | arXiv:2510.07226 | SUPPORTED | |
| 1.1h | 1.1 | 4,073,586 submissions | arXiv:2510.07226 | SUPPORTED | |
| 1.1i | 1.1 | statistical MGT detector | arXiv:2510.07226 | SUPPORTED | "state-of-the-art statistical method" |
| 1.1j | 1.1 | "very conservative estimate" | arXiv:2510.07226 | SUPPORTED | verbatim |
| 1.1k | 1.1 | information-seeking 6.33% (r/askscience, 2023-07) | arXiv:2510.07226 | SUPPORTED | |
| 1.1l | 1.1 | social support 7.69% | arXiv:2510.07226 | SUPPORTED | |
| 1.1m | 1.1 | identity 8.46% | arXiv:2510.07226 | SUPPORTED | |
| 1.1n | 1.1 | discussion 1.28% | arXiv:2510.07226 | SUPPORTED | r/politics, Sep 2023 |
| 1.1o | 1.1 | chit-chat 3.13% | arXiv:2510.07226 | SUPPORTED | |
| 1.1p | 1.1 | submissions peak ~7% | arXiv:2510.07226 | SUPPORTED | |
| 1.1q | 1.1 | MGT concentrates in technical-knowledge and social-support subreddits | arXiv:2510.07226 | SUPPORTED | abstract: "more prevalent in subreddits focused on technical knowledge and social support" |
| 1.1r | 1.1 | about 2% of active users account for all detected MGT | arXiv:2510.07226 | SUPPORTED | |
| 1.1s | 1.1 | stable after the Nov 2022 - Sep 2023 surge | arXiv:2510.07226 | SUPPORTED | |
| 1.1t | 1.1 | MGT gets engagement comparable to human text | arXiv:2510.07226 | SUPPORTED | |
| 1.1u | 1.1 | "Limitation: no programming subreddit in the sample" | arXiv:2510.07226 | UNSUPPORTED | **Contradicted.** Appendix A.1 sample list includes r/learnprogramming, r/technology, r/techsupport. See list below |
| 1.1v | 1.1 | single detector | arXiv:2510.07226 | SUPPORTED | |
| 1.2a | 1.2 | Reddit AI-attribution rate 1.31% -> 2.45% | arXiv:2412.18148 | SUPPORTED | |
| 1.2b | 1.2 | Jan 2022 - Jul 2024 | arXiv:2412.18148 | SUPPORTED | |
| 1.2c | 1.2 | Medium 1.77% -> 37.03% | arXiv:2412.18148 | SUPPORTED | |
| 1.2d | 1.2 | Quora 2.06% -> 38.95% | arXiv:2412.18148 | SUPPORTED | |
| 1.2e | 1.2 | 982,440 Reddit comments | arXiv:2412.18148 | SUPPORTED | |
| 1.2f | 1.2 | 2.4M posts across the three platforms | arXiv:2412.18148 | SUPPORTED | |
| 1.2g | 1.2 | OSM-Det accuracy 0.979 / F1 0.980 | arXiv:2412.18148 | SUPPORTED | |
| 1.2h | 1.2 | benchmark of 12 LLMs | arXiv:2412.18148 | SUPPORTED | |
| 1.2i | 1.2 | false-positive rate on Reddit 1.70% | arXiv:2412.18148 | SUPPORTED | |
| 1.2j | 1.2 | "The paper reports higher rates in technical fields (Technology, Software Development)" | arXiv:2412.18148 | PARTIAL | Finding is for Medium topics, not Reddit. See list below |
| 1.2k | 1.2 | credits Reddit's resistance to subreddit culture, moderation and downvoting | arXiv:2412.18148 | SUPPORTED | |
| 1.3a | 1.3 | AI-written posts rose only 2-3 pp more in informational communities than in hobby controls | arXiv:2609.12447 | SUPPORTED | abstract, near-verbatim |
| 1.3b | 1.3 | comments show no differential rise | arXiv:2609.12447 | SUPPORTED | |
| 1.3c | 1.3 | through Nov 2025 | arXiv:2609.12447 | SUPPORTED | |
| 1.3d | 1.3 | 26 informational vs 90 hobby control communities | arXiv:2609.12447 | SUPPORTED | |
| 1.3e | 1.3 | 151 total | arXiv:2609.12447 | SUPPORTED | |
| 1.3f | 1.3 | up to 100 posts + 100 comments per community-month via Arctic Shift | arXiv:2609.12447 | SUPPORTED | |
| 1.3g | 1.3 | windows Jan 2021 - Nov 2022 vs Jan 2024 - Nov 2025 | arXiv:2609.12447 | SUPPORTED | |
| 1.3h | 1.3 | 274,411 posts | arXiv:2609.12447 | SUPPORTED | |
| 1.3i | 1.3 | 223,775 comments | arXiv:2609.12447 | SUPPORTED | |
| 1.3j | 1.3 | scored with Fast-DetectGPT and Binoculars | arXiv:2609.12447 | SUPPORTED | |
| 1.3k | 1.3 | difference-in-differences design that cancels detector false positives | arXiv:2609.12447 | SUPPORTED | |
| 1.3l | 1.3 | texts under 200 chars excluded | arXiv:2609.12447 | SUPPORTED | |
| 1.4a | 1.4 | "Those are lower bounds: the detectors are nearly blind on comments from current models" | arXiv:2609.12447 | SUPPORTED | Paper: comment analysis "bounds only machine-generated text that some detector can see; answers written with the least detectable models are invisible to both detectors". "Nearly blind" is accurate for Fast-DetectGPT (3 of 4 models) and for DeepSeek-V3 / GLM-5.2 on both detectors; it overstates Binoculars on GPT-4o (0.939) and Claude Sonnet 4 (0.850), which the paper says it "can detect". The paper's statement is about 2609.12447's own numbers; extension to the 2510/2412 numbers is the report's inference |
| 1.4b | 1.4 | Fast-DetectGPT AUROC on posts 0.966 (GPT-4o) | arXiv:2609.12447 | SUPPORTED | |
| 1.4c | 1.4 | down to 0.875 (GLM-5.2) | arXiv:2609.12447 | SUPPORTED | |
| 1.4d | 1.4 | on comments only GPT-4o is detectable (0.794) | arXiv:2609.12447 | SUPPORTED | |
| 1.4e | 1.4 | the others 0.664 / 0.585 / 0.552 | arXiv:2609.12447 | SUPPORTED | |
| 1.4f | 1.4 | Binoculars on comments 0.939 (GPT-4o) | arXiv:2609.12447 | SUPPORTED | |
| 1.4g | 1.4 | 0.850 (Claude Sonnet 4) | arXiv:2609.12447 | SUPPORTED | |
| 1.4h | 1.4 | 0.768 (DeepSeek-V3) | arXiv:2609.12447 | SUPPORTED | |
| 1.4i | 1.4 | 0.698 (GLM-5.2) | arXiv:2609.12447 | SUPPORTED | |
| 1.4j | 1.4 | abstract hedge: "as far as detection can tell" | arXiv:2609.12447 | SUPPORTED | verbatim |
| 1.5a | 1.5 | BotBuster reports F1 60.04 on a Reddit dataset | arXiv:2207.13658 | SUPPORTED | |
| 1.5b | 1.5 | census of 3,389 bots | arXiv:2607.23941 | SUPPORTED | |
| 1.5c | 1.5 | 18 types | arXiv:2607.23941 | SUPPORTED | |
| 1.5d | 1.5 | bot numbers and activity peaked around COVID and declined before the 2023 API changes | arXiv:2607.23941 | SUPPORTED | |
| 1.5e | 1.5 | "covers self-identifying utility bots, not covert LLM accounts" | arXiv:2607.23941 | SUPPORTED | Substance holds (overt, identified bots). "Self-identifying" is slightly off: the paper's bots are "identified" (incl. by users), and types span content, behaviour and infrastructure roles, not only utility |
| 1.5f | 1.5 | 12,064 Reddit users | arXiv:2602.02838 | SUPPORTED | |
| 1.5g | 1.5 | incl. 99 IRA-linked accounts | arXiv:2602.02838 | SUPPORTED | |
| 1.5h | 1.5 | behaviour-based macro-F1 94.9% vs 91.2% for text embeddings | arXiv:2602.02838 | SUPPORTED | abstract: "median macro-F1" |
| 1.5i | 1.5 | Twitter: account-history AUC 0.977 vs 0.830 content-only | arXiv:2606.26127 | SUPPORTED | |
| 1.5j | 1.5 | "content features fall below chance under adversarial rewriting" | arXiv:2606.26127 | PARTIAL | Rewriting gives 0.842 -> 0.785; below chance (0.466) only under direct feature perturbation. See list below |
| 1.6a | 1.6 | 15 interviews | arXiv:2311.12702 | SUPPORTED | |
| 1.6b | 1.6 | with moderators of subreddits that restrict AI content | arXiv:2311.12702 | SUPPORTED | |
| 1.6c | 1.6 | "time-intensive and inaccurate detection heuristics" | arXiv:2311.12702 | SUPPORTED | verbatim |
| 1.7a | 1.7 | 25M HN + Reddit comments 2023-2026 | arXiv:2606.12073 | SUPPORTED | abstract only |
| 1.7b | 1.7 | pejorative AI-accusation share rose >10x on both platforms | arXiv:2606.12073 | SUPPORTED | "pejorative-label share of accusations rose more than tenfold on both platforms" |
| 1.7c | 1.7 | text features that separate AI from human prose do not predict which human text gets accused | arXiv:2606.12073 | SUPPORTED | |
| 1.7d | 1.7 | accusations function as social gatekeeping | arXiv:2606.12073 | SUPPORTED | |
| 1.7e | 1.7 | HN commenter: no reliable "tell", em-dash heuristics produce false accusations | HN 47300329 | SUPPORTED | vel0city, comment 47301040 |

### (2) Astroturfing / manipulation

| # | Bullet | Claim (report wording) | Source | Verdict | Note |
|---|---|---|---|---|---|
| 2.2a | 2.2 | REDCmts sells one Reddit comment for $9.99 | petervijeh.com / HN 49877678 | SUPPORTED | |
| 2.2b | 2.2 | 100 for $699.99 | petervijeh.com / HN 49877678 | SUPPORTED | |
| 2.2c | 2.2 | from "real, aged accounts" | petervijeh.com / HN 49877678 | SUPPORTED | verbatim |
| 2.2d | 2.2 | Soar: accounts "aged and manually warmed" for weeks | petervijeh.com | SUPPORTED | verbatim |
| 2.2e | 2.2 | Bazzly advertises automated replies to posts that look like someone shopping | petervijeh.com | SUPPORTED | |
| 2.2f | 2.2 | "as quoted in the thread" | HN 49877678 | SUPPORTED | neilv, comment 49877905, quotes the passage |
| 2.3a | 2.3 | 51,129 comments | petervijeh.com | SUPPORTED | |
| 2.3b | 2.3 | six knife subreddits | petervijeh.com | SUPPORTED | |
| 2.3c | 2.3 | the 5% most brand-heavy accounts | petervijeh.com | SUPPORTED | 49 of 987 authors with 10+ comments |
| 2.3d | 2.3 | wrote 11.3% of brand mentions in buying threads | petervijeh.com | SUPPORTED | |
| 2.3e | 2.3 | vs 7.9% expected by chance | petervijeh.com | SUPPORTED | |
| 2.3f | 2.3 | one brand: 31% vs 8% | petervijeh.com | SUPPORTED | 31.2% vs 8.0% |
| 2.3g | 2.3 | "those accounts average 4.5 years old across 66 subreddits, same as the comparison group" | petervijeh.com | SUPPORTED | Matches the page meta description ("4.5 years old and spread over 66 subreddits, the same as a comparison group"). Article body: 4.5 years is the *median* and equals controls; subreddit spread is 66 vs **47** for controls, i.e. not the same. Ambiguity is inherited from the page's own description |
| 2.3h | 2.3 | "the data shows concentration and not who paid for it" | petervijeh.com | SUPPORTED | verbatim, in page meta description only (not in body text) |
| 2.3i | 2.3 | HN: results not statistically significant by the author's own admission | HN 49877678 | SUPPORTED | socializer, 49878228 |
| 2.3j | 2.3 | HN: article appears LLM-drafted | HN 49877678 | SUPPORTED | socializer 49878228, jerry80 49881972. The article itself states "drafted with AI from my outline" |
| 2.3k | 2.3 | HN: brand loyalty is not paid astroturfing | HN 49877678 | SUPPORTED | socializer 49878228 |
| 2.4a | 2.4 | discontinued r/ChangeMyView field experiment used undisclosed AI accounts | arXiv:2606.05256 | SUPPORTED | |
| 2.4b | 2.4 | "adopted fabricated identities in more than two thirds of comments" | arXiv:2606.05256 | PARTIAL | Two-thirds is targeting OR adoption; adoption alone 42.9%. See list below |
| 2.4c | 2.4 | peptide vendors spammed the biohackers subreddit to steer ChatGPT and Google AI answers | 404 Media (article 2) | SUPPORTED | intro text |
| 2.5a | 2.5 | "Niche topics like linux feel somewhat safe from bots" while popular subs are bad (asksomeoneelse) | HN 49877678 | SUPPORTED | 49878148 |
| 2.5b | 2.5 | AI coding agents are astroturfed (asg172) | HN 49877678 | SUPPORTED | 49877895; sarcastic, by implication |
| 2.5c | 2.5 | "including from long-lived accounts with moderator support" (asg172) | HN 49877678 | PARTIAL | General statement about Reddit astroturfing, not about AI coding agents. See list below |
| 2.5d | 2.5 | one commenter suspects "I don't touch code anymore" comments on HN are bots (gwbas1c) | HN 49877678 | SUPPORTED | 49878810 |
| 2.6a | 2.6 | thin/young account checks "no longer an indicator"; bot accounts build histories in local and sports subreddits (nomel) | HN 49877678 | SUPPORTED | 49885833 |
| 2.6b | 2.6 | the four indicators in the article are trivially engineered around (rithdmc) | HN 49877678 | SUPPORTED | 49878097 |
| 2.6c | 2.6 | Reddit lets users hide post history (ohm/zergrush) | HN 49877678 | SUPPORTED | 49879068, 49887149 |
| 2.6d | 2.6 | moderator bans of unfavourable opinions produce survivorship bias (nomilk) | HN 49877678 | SUPPORTED | 49888226; "survivorship bias" is the report's label |
| 2.6e | 2.6 | toupee fallacy (DharmaPolice) | HN 49877678 | SUPPORTED | 49878574. Same comment also says account age "is the only thing that will be difficult to replicate at scale", which cuts against the bullet's heading |
| 2.7a | 2.7 | WARP attack on STORM, Co-STORM, OmniThink | arXiv:2605.24245 | SUPPORTED | |
| 2.7b | 2.7 | simulated, no live content modified | arXiv:2605.24245 | SUPPORTED | |
| 2.7c | 2.7 | 17-23% of retrieved URLs are UGC | arXiv:2605.24245 | SUPPORTED | |
| 2.7d | 2.7 | a single UGC page is retrieved in up to 48% of queries in a topic cluster | arXiv:2605.24245 | SUPPORTED | v1 only (see version note) |
| 2.7e | 2.7 | one poisoned URL with ~13 words | arXiv:2605.24245 | SUPPORTED | |
| 2.7f | 2.7 | retrieved in 57-76% of runs | arXiv:2605.24245 | SUPPORTED | v2 abstract |
| 2.7g | 2.7 | mentioned in 38-51% of reports | arXiv:2605.24245 | SUPPORTED | v2 abstract says "cited in 38-51% of the generated reports". Body (both versions): "38-51% mention rates conditional on exposure"; unconditional mention 30.7 / 37.1 / 21.7% |
| 2.7h | 2.7 | "appended to a full Reddit thread at <4% of retrieved content it still reaches 30-53%" | arXiv:2605.24245 | PARTIAL | Different, stronger attack (3-URL, ~130 words) and conditional on exposure. See list below |
| 2.7i | 2.7 | input/output anomaly filters do not reliably detect it | arXiv:2605.24245 | SUPPORTED | |
| 2.7j | 2.7 | Gemini Deep Research cites UGC at 12.1% on the tested topics | arXiv:2605.24245 | SUPPORTED | 623 of 5,157 citations |
| 2.7k | 2.7 | 404 Media "adds 'nearly half the citations in AI queries come from UGC'" | 404 Media (article 1) | UNSUPPORTED | Quoted phrase is not in the article; article says roughly half of *queries* and nearly a *quarter* of citations. See list below |
| 2.8a | 2.8 | FORGE: across 12 LLMs | arXiv:2606.13610 | SUPPORTED | |
| 2.8b | 2.8 | a single polluted page yields fooled rates up to 27% | arXiv:2606.13610 | SUPPORTED | |
| 2.8c | 2.8 | top-3 replacement 73.8% | arXiv:2606.13610 | SUPPORTED | |
| 2.8d | 2.8 | reasoning does not help | arXiv:2606.13610 | SUPPORTED | |
| 2.8e | 2.8 | "often generates spurious social proof" | arXiv:2606.13610 | SUPPORTED | verbatim |
| 2.8f | 2.8 | a skepticism prompt can make it worse | arXiv:2606.13610 | SUPPORTED | |
| 2.8g | 2.8 | credibility re-ranking removes about a sixth of fakes | arXiv:2606.13610 | SUPPORTED | |

### (3) Forum knowledge vs official docs

| # | Bullet | Claim (report wording) | Source | Verdict | Note |
|---|---|---|---|---|---|
| 3.1a | 3.1 | official docs are "often lengthy, complex, or incomplete" | arXiv:2509.05749 | SUPPORTED | verbatim |
| 3.1b | 3.1 | developers turn to SO | arXiv:2509.05749, 2401.11361 | SUPPORTED | |
| 3.1c | 3.1 | user study with 30 Android developers | arXiv:2509.05749 | SUPPORTED | |
| 3.1d | 3.1 | summaries built from 3.6M SO posts | arXiv:2509.05749 | SUPPORTED | |
| 3.2a | 3.2 | 495 SO posts | arXiv:2607.19621 | SUPPORTED | |
| 3.2b | 3.2 | 9,116 GitHub issues/PRs on federated-learning frameworks | arXiv:2607.19621 | SUPPORTED | |
| 3.2c | 3.2 | environment setup, API breakage and high unresolved rates | arXiv:2607.19621 | SUPPORTED | |
| 3.2d | 3.2 | 2,874 SO discussions on the OpenAI API | arXiv:2505.04084 | SUPPORTED | |
| 3.3a | 3.3 | 1,154 Reddit + HN posts qualitatively coded on AI slop | arXiv:2603.27249 | SUPPORTED | |
| 3.3b | 3.3 | 1,700+ Reddit posts thematically analysed | arXiv:2309.13684 | SUPPORTED | |
| 3.3c | 3.3 | 437,317 threads | arXiv:2304.07650 | SUPPORTED | abstract only |
| 3.3d | 3.3 | from r/webdev, r/androiddev, r/iOSProgramming | arXiv:2304.07650 | SUPPORTED | |
| 3.3e | 3.3 | GitHub AI-slop study also draws on Reddit, mailing lists and blogs | arXiv:2607.04003 | SUPPORTED | |
| 3.4a | 3.4 | blocking eight UGC domains (Reddit, YouTube, Facebook, Medium, Instagram, TikTok, Quora, Wikipedia) | arXiv:2605.24245 | SUPPORTED | |
| 3.4b | 3.4 | in Co-STORM | arXiv:2605.24245 | SUPPORTED | |
| 3.4c | 3.4 | over 176 queries | arXiv:2605.24245 | SUPPORTED | |
| 3.4d | 3.4 | rubric score 4.30 -> 4.26 | arXiv:2605.24245 | SUPPORTED | |
| 3.4e | 3.4 | information diversity 0.604 -> 0.585 | arXiv:2605.24245 | SUPPORTED | |
| 3.4f | 3.4 | "negligible impact under these standard metrics" | arXiv:2605.24245 | SUPPORTED | v1 only; v2: "Measured quality changes are small". Both versions add "These metrics, however, have limited sensitivity to source composition", omitted by the report |
| 3.4g | 3.4 | abstract says dropping UGC "degrades the quality of generated reports" | arXiv:2605.24245 | SUPPORTED | v2 abstract only; v1: "degrades output quality". The two verbatim quotes in this bullet come from different versions |
| 3.4h | 3.4 | queries are consumer topics (finance, antivirus, restaurants) | arXiv:2605.24245 | SUPPORTED | |
| 3.4i | 3.4 | the rubric is an LLM judge | arXiv:2605.24245 | SUPPORTED | Prometheus-7B-v2.0 |

### (4) HN, Stack Overflow, GitHub

| # | Bullet | Claim (report wording) | Source | Verdict | Note |
|---|---|---|---|---|---|
| 4.1a | 4.1 | HN guidelines say not to post generated / AI-edited comments | HN 47340079 | SUPPORTED | thread title + linked guideline |
| 4.1b | 4.1 | moderator: as a general rule accounts posting generated comments get banned; not hard and fast; depends on users emailing reports | HN 47300329 | SUPPORTED | tomhow, 47303552 |
| 4.1c | 4.1 | one user reports hitting "We're temporarily restricting Show HNs" | HN 47300329 | SUPPORTED | jhyolm, 47387833 |
| 4.1d | 4.1 | vote-ring detection is rumoured, not documented | HN 47300329 | SUPPORTED | AnimalMuppet, 47302816 |
| 4.1e | 4.1 | at least 19% of AI developers promoted their own GitHub projects on HN | arXiv:2506.12643 | SUPPORTED | |
| 4.1f | 4.1 | 2,195-story sample | arXiv:2506.12643 | SUPPORTED | |
| 4.1g | 4.1 | measurable star/fork gains | arXiv:2506.12643 | SUPPORTED | |
| 4.2a | 4.2 | SO banned ChatGPT answers six days after release | arXiv:2307.09765 | SUPPORTED | |
| 4.2b | 4.2 | SO enforces a no-AI-content policy | HN 48956949 | SUPPORTED | zahlman, 48973600 |
| 4.2c | 4.2 | "Weekly posts fell 16% after ChatGPT" [doi:10.1093/pnasnexus/pgae400, arXiv:2307.07367] | PNAS Nexus DOI + arXiv preprint | PARTIAL | 16% is the preprint's figure; the cited published version says 25%. See list below |
| 4.2d | 4.2 | relative to Russian/Chinese counterparts and math forums | both | SUPPORTED | |
| 4.2e | 4.2 | growing over time | arXiv:2307.07367 | SUPPORTED | "This effect increases in magnitude over time" (preprint abstract) |
| 4.2f | 4.2 | second study: significant declines in SO visits and questions, compared against Reddit developer communities | doi:10.1038/s41598-024-61221-0 | SUPPORTED | Abstract also says Reddit developer communities show "no evidence of decline" |
| 4.2g | 4.2 | human SO answers beat ChatGPT answers by roughly 10% | arXiv:2307.09765 | SUPPORTED | "by 10% on the overall score" |
| 4.2h | 4.2 | 58.4% of obsolete answers probably already obsolete when posted | arXiv:1903.12282 | SUPPORTED | abstract only |
| 4.2i | 4.2 | only 20.5% were ever updated | arXiv:1903.12282 | SUPPORTED | abstract only |
| 4.2j | 4.2 | insecure answers had more views (36,508 vs 18,713) | arXiv:1901.01327 | SUPPORTED | |
| 4.2k | 4.2 | and higher score (14 vs 5) | arXiv:1901.01327 | SUPPORTED | |
| 4.2l | 4.2 | 34% of posts by highly reputable users were insecure | arXiv:1901.01327 | SUPPORTED | |
| 4.2m | 4.2 | 66% of 153 sampled code clones were outdated | arXiv:1806.07659 | SUPPORTED | abstract only |
| 4.2n | 4.2 | 69 vulnerable C++ snippets | arXiv:1910.01321 | SUPPORTED | abstract only |
| 4.2o | 4.2 | propagated into 2,859 GitHub projects | arXiv:1910.01321 | SUPPORTED | abstract only |
| 4.3a | 4.3 | BSTS | arXiv:2607.04003 | SUPPORTED | |
| 4.3b | 4.3 | 294 repos | arXiv:2607.04003 | SUPPORTED | |
| 4.3c | 4.3 | >2M PRs/issues | arXiv:2607.04003 | SUPPORTED | |
| 4.3d | 4.3 | PR volume up in 2025, merge rates down | arXiv:2607.04003 | SUPPORTED | |
| 4.3e | 4.3 | one-time contributors' merge rate -18.18% vs counterfactual | arXiv:2607.04003 | SUPPORTED | |
| 4.3f | 4.3 | survey of 229 practitioners | arXiv:2607.04003 | SUPPORTED | |
| 4.3g | 4.3 | approval 30.1% -> 36.8% | arXiv:2606.22721 | SUPPORTED | |
| 4.3h | 4.3 | inline comments -22% | arXiv:2606.22721 | SUPPORTED | |
| 4.3i | 4.3 | newcomer share -3.7 pp | arXiv:2606.26289 | SUPPORTED | |
| 4.3j | 4.3 | across 11,097 repos | arXiv:2606.26289 | SUPPORTED | |
| 4.3k | 4.3 | scikit-learn maintainers: the same authors spam LLM PRs across projects | scikit-learn#31679 | SUPPORTED | |
| 4.3l | 4.3 | AI-generated PRs are "often not obvious unless you have encountered some patterns" | scikit-learn#31679 | SUPPORTED | verbatim |
| 4.3m | 4.3 | "detection tools are unmaintained" | scikit-learn#31679 | PARTIAL | One of two tools; the other is described as new and active. See list below |
| 4.3n | 4.3 | "response is a low threshold for closing" | scikit-learn#31679 | PARTIAL | One member's proposal, not an adopted response. See list below |
| 4.3o | 4.3 | pip is debating an explicit AI-contribution policy | pypa/pip#13417 | SUPPORTED | |
| 4.3p | 4.3 | external-secrets has an explicit AI-contribution policy | external-secrets llm-policy.md | SUPPORTED | |

### Safeguards

| # | Bullet | Claim (report wording) | Source | Verdict | Note |
|---|---|---|---|---|---|
| S1a | Safeguard 1 | single-page poisoning succeeds at 38-51% | arXiv:2605.24245 | SUPPORTED | Same conditional-on-exposure caveat as 2.7g. FORGE's single-page figure is "up to 27%" |
| S1b | Safeguard 1 | "no in-pipeline filter catches it" | arXiv:2605.24245, 2606.13610 | PARTIAL | Source-level UGC blocking does block it. See list below |
| S2a | Safeguard 2 | 5% of authors produce 11.3% of brand mentions | petervijeh.com | SUPPORTED | Scope: the 5% most brand-heavy of authors with 10+ comments; buying-thread mentions; chance baseline 7.9% |
| S2b | Safeguard 2 | 2% of users produce all detected MGT | arXiv:2510.07226 | SUPPORTED | |
| S2c | Safeguard 2 | moderation creates survivorship bias | HN 49877678 | SUPPORTED | nomilk, opinion |
| S3a | Safeguard 3 | paid placement targets shopping-intent threads | petervijeh.com / HN 49877678 | SUPPORTED | Bazzly's self-description; one vendor |
| S3b | Safeguard 3 | dissatisfied-user reports are harder to suppress (thimabi, opinion) | HN 49877678 | SUPPORTED | 49878349 |
| S4a | Safeguard 4 | "Detectors: AUROC 0.55-0.79 on modern-model comments" | arXiv:2609.12447 | PARTIAL | Fast-DetectGPT only; Binoculars 0.698-0.939. See list below |
| S4b | Safeguard 4 | aged accounts are sold | petervijeh.com | SUPPORTED | |
| S4c | Safeguard 4 | histories can be hidden | HN 49877678 | SUPPORTED | |
| S4d | Safeguard 4 | accusations do not track AI features | arXiv:2606.12073 | SUPPORTED | |

## Totals per verdict (atomic claims, Summary + Findings + Safeguards)

| Verdict | Count |
|---|---|
| SUPPORTED | 184 |
| PARTIAL | 11 |
| UNSUPPORTED | 2 |
| UNCHECKABLE | 0 |
| **Total** | **197** |

By section (SUPPORTED / PARTIAL / UNSUPPORTED): Summary 5 / 1 / 0; Part 1 70 / 2 / 1; Part 2 43 / 3 / 1; Part 3 22 / 0 / 0; Part 4 35 / 3 / 0; Safeguards 9 / 2 / 0.

Three PARTIAL rows share one root defect (detector strength: Sum.4, S4a; and 1.4a is rated SUPPORTED with the same caveat). Some SUPPORTED rows carry a caveat in the Note column (most notes are only locators such as comment IDs or "verbatim"); the caveats that matter for interpretation are 1.4a (detector-blindness heading), Sum.6 / 2.7g / S1a (conditional-on-exposure figure), 2.7d / 3.4f / 3.4g (version mixing), 2.3g (66 vs 47 subreddits).

Sources-list annotations (35 entries, counted separately, see next table): 33 consistent with the source, 2 PARTIAL (entries 8 and 13, same defects as 1.5j and 4.2c).

## Sources list: existence and annotation check

| # | Entry | Exists / title matches | Annotation vs source |
|---|---|---|---|
| 1 | arXiv:2510.07226 | yes | consistent |
| 2 | arXiv:2412.18148 | yes | consistent |
| 3 | arXiv:2609.12447 | yes | consistent |
| 4 | arXiv:2606.12073 | yes | consistent |
| 5 | arXiv:2607.23941 | yes | "declared-bot census": paper says "identified bots" |
| 6 | arXiv:2207.13658 | yes | consistent |
| 7 | arXiv:2602.02838 | yes | consistent |
| 8 | arXiv:2606.26127 | yes | **PARTIAL** — "content features collapse under rewriting": rewriting gives 0.842 -> 0.785; collapse (0.466) is under direct feature perturbation |
| 9 | arXiv:2311.12702 | yes | consistent |
| 10 | arXiv:2606.05256 | yes (full title: "How Far Did They Go? The Persuasive Tactics of Covert LLM Agents in a Discontinued Field Experiment") | consistent |
| 11 | arXiv:2605.24245 | yes | consistent (two versions, see note) |
| 12 | arXiv:2606.13610 | yes | consistent |
| 13 | doi:10.1093/pnasnexus/pgae400 + arXiv:2307.07367 | both yes; DOI title matches; arXiv preprint has a different title ("Are Large Language Models a Threat to Digital Public Goods? Evidence from Activity on Stack Overflow") | **PARTIAL** — "SO -16% weekly posts (abstract)": the abstract of the titled/DOI paper says 25%; 16% is the preprint abstract |
| 14 | doi:10.1038/s41598-024-61221-0 | yes, title matches | consistent |
| 15 | arXiv:2307.09765 | yes (real title: "Are We Ready to Embrace Generative AI for Software Q&A?"; report gives a descriptive label) | consistent |
| 16 | arXiv:1903.12282 | yes ("An Empirical Study of Obsolete Answers on Stack Overflow") | consistent |
| 17 | arXiv:1901.01327 | yes ("How Reliable is the Crowdsourced Knowledge of Security Implementation?") | consistent |
| 18 | arXiv:1806.07659 | yes ("Toxic Code Snippets on Stack Overflow") | consistent |
| 19 | arXiv:1910.01321 | yes ("An Empirical Study of C++ Vulnerabilities in Crowd-Sourced Code Examples") | consistent |
| 20 | arXiv:2509.05749, 2401.11361 | both yes | consistent |
| 21 | arXiv:2607.19621, 2505.04084 | both yes | "forum/issue content beyond docs" is the report's interpretation; abstracts say pain points and "shortcomings in tooling, documentation, and debugging support" |
| 22 | arXiv:2603.27249, 2309.13684, 2304.07650 | all yes | consistent |
| 23 | arXiv:2607.04003 | yes | consistent |
| 24 | arXiv:2606.22721, 2606.26289, 2601.00753, 2509.14745 | all yes | consistent; 2601.00753 and 2509.14745 are never cited in any finding |
| 25 | arXiv:2506.12643 | yes | consistent |
| 26 | HN 49877678 | yes, title matches | "387-comment thread": confirmed (387 comments) |
| 27 | petervijeh.com | yes | consistent |
| 28 | HN 47340079 | yes, title matches | consistent |
| 29 | HN 47300329 | yes, title matches | consistent |
| 30 | HN 48956949 | yes, title matches | consistent |
| 31 | 404 Media article 1 | yes, title matches | consistent as a description; the quote taken from it (2.7k) is not in it |
| 32 | 404 Media article 2 | yes, title matches | consistent |
| 33 | scikit-learn#31679 | yes | "maintainers on undetectable LLM PRs": thread says "often not obvious", not undetectable |
| 34 | pypa/pip#13417 | yes | consistent |
| 35 | external-secrets llm-policy.md (pinned commit) | yes | consistent |

Existence confirmed: 35 of 35 entries (every URL / ID in them: 31 arXiv IDs, 2 DOIs, 4 HN items, 2 GitHub issues, 1 GitHub file, 1 blog page, 2 404 Media articles). Could not be confirmed: 0. The four "Surfaced but not read" URLs at the end of the list were not fetched; the report itself labels them "leads, not evidence" and no finding relies on them.

## Every non-SUPPORTED claim, side by side

### UNSUPPORTED

**1.1u — arXiv:2510.07226**
- Report: "Limitation: no programming subreddit in the sample"
- Source (Appendix A.1, list of the 51 selected subreddits): "Information Seeking. r/worldnews, r/DIY, r/askscience, r/personalfinance, r/technology, r/history, r/CryptoCurrency, r/nutrition, r/learnprogramming, r/explainlikeimfive, r/health, r/techsupport, r/writing."
- The sample contains r/learnprogramming, r/technology and r/techsupport. The paper does not print a per-subreddit figure for them in the text (category peaks only), but they are in the measured sample, and the abstract says MGT is "more prevalent in subreddits focused on technical knowledge and social support". The claimed limitation is the opposite of what the paper says and feeds the report's "tech-subreddit gap" framing (Summary, 2.1).

**2.7k — 404 Media, "It Is Trivially Easy to Use Reddit to Manipulate AI Search, Research Suggests" (Jason Koebler, 15 Jun 2026)**
- Report: 404 Media "adds "nearly half the citations in AI queries come from UGC" (journalist's paraphrase, not verified against the paper)"
- Source: "cite user-generated content from sites like Reddit or Wikipedia in roughly half of all queries, and that nearly a quarter of all citations come from user-generated websites"
- The phrase in quotation marks does not appear in the article. It merges two different figures (half of queries; a quarter of citations) into one that the article does not state. The underlying paper puts UGC at 17-23% of retrieved URLs.

### PARTIAL

**Sum.4 — arXiv:2609.12447**
- Report: "those numbers are lower bounds because current detectors barely beat chance on short comments from modern models"
- Source: Fast-DetectGPT "does not reliably detect machine-generated comments. GPT-4o replies remain detectable (AUROC 0.794...), while replies from the other three LLMs sit almost on top of the human distribution, with AUROCs of 0.664, 0.585 and 0.552"; "Binoculars can detect comments from GPT-4o (AUROC 0.939) and Claude Sonnet 4 (0.850), still cannot see DeepSeek-V3 or GLM-5.2 (0.768, 0.698)".
- Changed: strength and scope. "Barely beat chance" fits one detector on three models. "Those numbers" includes the 1-3% and 6-9% figures, which come from different detectors (a statistical detector in 2510.07226, OSM-Det in 2412.18148) that 2609.12447 did not calibrate, and the +2-3 pp figure, which is measured on *posts*, where the same calibration gives AUROC 0.875-0.966. No source uses the words "lower bound"; 2510.07226 says "very conservative estimate" and 2609.12447 says its comment analysis "bounds only machine-generated text that some detector can see".

**1.2j — arXiv:2412.18148**
- Report (in a bullet about Reddit): "The paper reports higher rates in technical fields (Technology, Software Development)"
- Source: "(3) Technology-related topics drive higher AARs on Medium. Topics like "Technology" and "Software Development" show the highest AARs"; "the AAR for "Technology" and "Software Development" remains consistently higher than other topics ... on Medium".
- Changed: population. The topic analysis is for Medium; the paper reports no topic breakdown for Reddit.

**1.5j — arXiv:2606.26127 (also Sources entry 8)**
- Report: "content features fall below chance under adversarial rewriting"; Sources: "content features collapse under rewriting"
- Source: "In the first [setting], we rewrite the text of bot tweets to match human surface statistics ...; the content classifier's ROC-AUC degrades from 0.842 to 0.785 ... In the second, more aggressive setting we directly perturb the content feature values toward the human distribution; the content classifier falls below chance (AUC 0.466)".
- Changed: condition. Under rewriting the drop is 0.842 -> 0.785; below-chance is under direct feature-value perturbation, not rewriting.

**2.4b — arXiv:2606.05256**
- Report: undisclosed AI accounts "adopted fabricated identities in more than two thirds of comments"
- Source: abstract "Identity targeting or adoption appears in over two-thirds of comments"; body table: "Identity targeting (comments) 707 46.1", "Identity adoption (comments) 657 42.9".
- Changed: number/scope. Two-thirds (67.2%) is targeting OR adoption; adoption alone is 42.9%.

**2.5c — HN 49877678, asg172 (49877895)**
- Report: "AI coding agents are astroturfed, including from long-lived accounts with moderator support (asg172)"
- Source: "Of course, AI coding agents, which the author works on, would also never be astroturfed on Reddit! You know, astroturfing on Reddit also comes from long time accounts with moderator support."
- Changed: scope. The second sentence is about Reddit astroturfing in general; the report attaches it to AI coding agents. The first sentence is sarcasm without evidence.

**2.7h — arXiv:2605.24245**
- Report: "one poisoned URL with ~13 words is retrieved in 57-76% of runs and mentioned in 38-51% of reports; appended to a full Reddit thread at <4% of retrieved content it still reaches 30-53%"
- Source (v1): "In the full-content setting, where the poisoned text is appended to a complete Reddit thread and constitutes less than 4% of retrieved content, conditional mention rates remain 30-53%". Table caption: "Full-content attack results (3-URL). Poisoned text (~130 words) is appended to full Reddit threads"; unconditional "Mentioned (%) 18.8 / 30.7 / 18.3"; "Ment. | exp (%) 52.5 / 40.6 / 29.7". v2 abstract: "A more aggressive attack (poisoning an entire subreddit) achieves 30-53% citation rates even when the poison is only 0.5-4% of the retrieved content".
- Changed: scope. "It still" presents this as the same one-URL 13-word payload; the source experiment is 3 URLs with ~130 words, and 30-53% is conditional on exposure (unconditional 18-31%). Mitigating: v1's own summary sentence is equally loose about the payload.

**4.2c — doi:10.1093/pnasnexus/pgae400 and arXiv:2307.07367 (also Sources entry 13)**
- Report: "Weekly posts fell 16% after ChatGPT relative to Russian/Chinese counterparts and math forums, growing over time"; Sources: "Large language models reduce public knowledge sharing on online Q&A platforms ... SO -16% weekly posts (abstract)"
- Source, arXiv preprint abstract (Jul 2023): "A difference-in-differences model estimates a 16% decrease in weekly posts on Stack Overflow. This effect increases in magnitude over time".
- Source, PNAS Nexus abstract (Sep 2024, the DOI and title the report cites first): "Within 6 months of ChatGPT's release, activity on Stack Overflow decreased by 25% relative to its Russian and Chinese counterparts ... and to similar forums for mathematics ... We interpret this estimate as a lower bound".
- Changed: number. 16% is the preprint's estimate; the published paper cited by DOI and title reports 25%.

**4.3m — scikit-learn#31679**
- Report: "detection tools are unmaintained"
- Source: "What I just found is AI Watchdog GitHub Action. Unfortunately, it doesn't look like it's getting updated ... I also found Codect: AI-Generated Code Detection which is not a GitHub Action, and also very new, but seems people are working on it still."
- Changed: scope. One tool looks unmaintained; the other is described as new and actively worked on.

**4.3n — scikit-learn#31679**
- Report: "response is a low threshold for closing"
- Source (lucyleeow, member): "I would supporting having a low threshold for closing and blocking users that submit low quality PRs and issues."
- Changed: strength. One member's stated preference in an open discussion, presented as the project's response.

**S1b — arXiv:2605.24245, arXiv:2606.13610**
- Report: "single-page poisoning succeeds at 38-51% and no in-pipeline filter catches it"
- Source (2605.24245 v2 abstract): "Dropping UGC from retrieved content blocks the attack but degrades the quality of generated reports. We show that lightweight anomaly detection on inputs and outputs does not reliably identify poisoned content". (2606.13610): "None of the four defenses is adequate ... credibility re-ranking helps every model but removes only a sixth of the fakes".
- Changed: strength. "Does not reliably identify" became "no filter catches it", and source-level UGC filtering, which the paper says blocks the attack, is left out (the report's own bullet 3.4 discusses it).

**S4a — arXiv:2609.12447**
- Report: "Detectors: AUROC 0.55-0.79 on modern-model comments"
- Source: Fast-DetectGPT on comments 0.794 / 0.664 / 0.585 / 0.552; Binoculars on comments 0.939 / 0.850 / 0.768 / 0.698.
- Changed: scope. The range is one detector's; the second detector in the same paper (and in the report's own bullet 1.4) reaches 0.70-0.94.

## Sources listed but never used

- arXiv:2601.00753 ("Early-Stage Prediction of Review Effort in AI-Generated Pull Requests") and arXiv:2509.14745 ("On the Use of Agentic Coding: An Empirical Study of Pull Requests on GitHub"), both in Sources entry 24, are cited in no finding.
- All other Sources entries are cited at least once.

## Claims with no source (not in the verdict totals)

| Bullet | Statement | Comment |
|---|---|---|
| 1.2 | "Read honestly: Reddit's measured rate sits within ~0.8 pp of the detector's own false-positive rate, so this is "indistinguishable from near-zero by this instrument"" | Report's inference. Arithmetic is right (2.45 - 1.70 = 0.75). The quoted phrase is the report's own, not the paper's; the paper treats the rate as real low adoption |
| 2.1 | "No retrieved source measures astroturfing in programming or technology subreddits." | Absence claim. Not contradicted for astroturfing. For AI-generated text it is contradicted by the report's own source 1 (see 1.1u) |
| 2.8 | "Independent replication" | Report's characterisation; FORGE is a different team and benchmark, not a replication of WARP |
| 3.2 | "Pain-point studies find content docs do not cover." | Interpretation. 2607.19621 says "shortcomings in tooling, documentation, and debugging support"; 2505.04084 makes no docs comparison |
| 3.3 | "That is revealed preference, not proof of unique knowledge." | Report's inference |
| 3.5 | "Net: ... supported for SO/GitHub issues on software; for Reddit specifically it was not measured by anything retrieved here." | Synthesis |
| 4.1 | "No prevalence measurement for HN was found"; "Advantage for an agent: full comment trees via a public API" | Absence claim / own statement |
| 4.2 | "So score and reputation are not correctness signals." | Inference from 1901.01327 |
| 4.3 | "maintainers cannot spot them by eye either"; "Structural advantage: claims in an issue are tied to artifacts ..." | First is stronger than "often not obvious"; second is the report's own |
| 4.4 | "Comparison in one line." | Synthesis |
| Safeguards 5-6 | normative rules | No factual claim |

## Does the Summary say anything the findings do not back?

- "lower bounds because current detectors barely beat chance": stronger than finding 1.4, which itself lists Binoculars at 0.850 and 0.939 (Sum.4).
- "+2-3 pp differential rise": finding 1.3 adds that comments show no rise; the Summary drops that.
- "cited in 38-51% of deep-research reports": finding 2.7 says "mentioned", Summary says "cited". The v2 abstract says "cited in 38-51%"; the body's cited-conditional-on-exposure rates are 100 / 72.5 / 60% and 38-51% is the mention rate. Both report wordings omit "conditional on exposure".
- "No retrieved study measures bots or astroturfing in programming/technology subreddits specifically": backed by 2.1 as written, and narrowly defensible for bots/astroturfing. It rests partly on 1.1's false limitation: the report's own source 1 measures machine-generated text in a sample that includes r/learnprogramming, r/technology and r/techsupport.
- The remaining Summary sentences (commercial supply, safeguards, "HN, Stack Overflow and GitHub are not clean alternatives") are backed by findings 2.2, Safeguards, and Part 4. HN's "documented failure mode" in Part 4 is a promotion-channel study plus the absence of measurement.

## Coverage statement

All bullets in Summary, Key Findings (1)-(4) and Safeguards were checked; none was sampled or skipped. Limits on depth: seven arXiv papers and FORGE were checked against abstracts only (listed in "How sources were read"; every claim attributed to them is abstract-level); 404 Media article 2 was readable only to the paywall (the one claim taken from it is in the visible intro).
