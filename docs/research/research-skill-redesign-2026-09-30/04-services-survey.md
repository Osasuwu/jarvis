# External deep-research services vs hand-orchestrated `/research` — evidence scan

Retrieved: 2026-09-30 (all URLs below fetched in this run unless marked otherwise).
Scope: evidence scan, not advocacy. Every row carries its evidence level:

- **[page]** — page body retrieved and read (scrape / WebFetch / API JSON / paper full text)
- **[snippet]** — only a search-result snippet or search-engine summary of the page was seen
- **[vendor]** — the source is the party selling the thing (self-reported)
- **[live]** — measured by a live request in this run
- **prior, unverified** — from model memory, not retrieved

Nothing here was run end-to-end: no service was called with a real research query, so cost/latency/quality figures are *reported*, not measured by me.

---

## 0. Bottom line (with its own disconfirming evidence)

The evidence does not support replacing hand-orchestration wholesale with a third-party deep-research service. It supports **hybrid**: keep orchestration in Claude Code, add (a) a mandatory per-claim citation/URL verification pass, and (b) optionally one cheap fixed-price search/research endpoint as an *extra source-finder*, not as the synthesizer. And there is now a fourth option the brief did not list: Claude Code ships a **first-party bundled `/deep-research` workflow** with claim-level cross-checking — the hand-written skill competes with that more directly than with Perplexity.

For:
- Commercial single-agent deep-research products were the *worst* family on citation association in the one independent multi-system table retrieved (LiveResearchBench), and deep-research agents fabricate URLs ~2x as often as plain search-augmented models (arxiv 2604.03173).
- Open multi-agent orchestrations with an explicit citation step scored *best* on citations (Open Deep Research, Deerflow+ at ~77 vs 25–52 for commercial DR).
- Vendor churn is real and fast: OpenAI's deep-research API models lived ~13 months; Firecrawl's deep-research endpoint was deprecated; LangChain's open_deep_research is archived; Perplexity's API had a billed no-search failure mode for months.
- Every headline quality number for a service is vendor-self-reported and judge-dependent (DRACO scores move 10–25 points with the judge; BrowseComp has no independent evaluator).

Against (disconfirming):
- DRACO (Feb 2026): Perplexity's harness on Opus 4.6 scored 70.5% vs 59.8% for the *same model* with plain web search + code execution — a ~11-point harness uplift. A tuned harness is worth something.
- Dr. Bench (Jan 2026): "contemporary DRAs substantially outperform conventional tool-augmented models in complex task scenarios."
- Services are cheaper per report ($0.005–$2.50) than an Opus-driven hand-orchestrated run (third-party estimate $1–3).
- LiveResearchBench's evidence is 2025-era models (Claude 4 / 4.1, o3); it may not transfer to 2026 models.
- No benchmark retrieved measures "well-prompted Claude Code + Firecrawl" as such. The closest proxies are DRACO's "Claude + web search + code execution" rows and LiveResearchBench's "single-agent + web search" rows.

---

## 1. Comparison table

Cost = per typical report, as reported. "Claim-level citations" = does the output tie individual claims to sources (not just a bibliography).

| Option | How it plugs into Claude Code | Cost / report | Latency | Claim-level citations | Independent quality evidence | Status / churn |
|---|---|---|---|---|---|---|
| **Claude Code bundled `/deep-research` workflow** | Built in. `/deep-research <question>`; runs as a background dynamic workflow of subagents. Requires the WebSearch tool. | Not published. Token-billed against plan; "Large workflow" warning fires at >25 agents or >1.5M projected tokens; default size guideline `medium` (<10 agents) | Not published | Yes by design: "votes on each claim… claims that didn't survive cross-checking filtered out"; unverifiable claims listed as unverified | None retrieved | Active (docs reference versions up to v2.1.271) |
| **Hand-written skill (status quo)** | Skill + Firecrawl MCP + paper search | Third-party estimate for a comparable pipeline: $1–3 at Opus 4.7 rates | — | Whatever the skill enforces | Proxy only: DRACO bare Opus 4.6 + search 59.8% (Gemini-3-Pro judge) | You own it |
| **Perplexity Sonar Deep Research** | Official MCP (`perplexityai/modelcontextprotocol`, `perplexity_research` tool) or HTTP API | $0.41–$1.32 per query (third party); token + citation-token + reasoning-token + $5/1k searches | DRACO paper: 245 s avg | Inline numbered citations; DRACO citation-quality sub-score 64.6%; LiveResearchBench citation association 36.6 | DRACO 70.5% (own benchmark); LiveResearchBench 83.5/67.4/65.5/36.6 | **Reliability problems**: no-search responses still billed (from 2026-03-07), empty citations arrays on async (2026-06), timeouts |
| **OpenAI deep research API** | HTTP API | Historical: o3 up to ~$30/call, o4-mini ~$1 | DRACO: o3 1808 s | Inline URL annotations | DRACO o3 52.1%, o4-mini 41.9%; LiveResearchBench citation association 25.6 / 27.2 (worst) | **Shut down 2026-07-23**; replacement is a general model `gpt-5.6-sol`, not a deep-research model |
| **Gemini Deep Research / Max** | HTTP (Interactions API, `background: true`, poll). No official MCP found | ~$1–3 (third party); $2/M in, $12/M out | Minutes (async) | Yes (cited report) | DRACO 59.0%; LiveResearchBench 62.1/63.0/75.8/52.1; **highest URL hallucination: 13.3% hallucinated, 18.5% non-resolving** (2.5-pro DR) | Still "preview" (`deep-research-preview-04-2026`) |
| **Parallel Task API** | HTTP API; hosted search MCP (`parallel-web/search-mcp`, no key) | $0.005 (Lite) – $2.40 (Ultra8x), fixed per run | Median 45 s – ~8 min; p90 1.5–11 min | "Basis": per-field citations + confidence | Only vendor-run BrowseComp / DeepSearchQA; third party reports much lower DeepSearchQA | Active; $5/mo free credits |
| **Exa (Deep Search / Answer / Agent)** | Remote MCP `https://mcp.exa.ai/mcp`; HTTP | $0.012–$0.50 per request by effort tier | Not retrieved | Answer endpoint returns citations | None independent retrieved | Active (MCP repo pushed 2026-09-29) |
| **Tavily Research** | Official MCP (`tavily-ai/tavily-mcp`); HTTP | `mini` ≈ $0.03–$0.88; `pro` ≈ $0.12–$2.00 | Not retrieved | Sources list; claim-level not verified | None independent retrieved | Active; acquired by Nebius [snippet] |
| **You.com Research API** | HTTP | $0.012 (lite) – $0.45 (exhaustive) per request; frontier $1.2–2+ | <10 s – <300 s; frontier up to 12,000 s | Yes (vendor) | Vendor "#1 DeepSearchQA 83.67%"; competitor scored it 52.9% on DRACO | Active; prices inconsistent across sources |
| **Firecrawl** | Already installed MCP | `/agent`: 5 free runs/day, dynamic pricing | — | — | None | **Deep-research endpoint deprecated 2026-02-02** in favour of Search; `/agent` replaces `/extract` |
| **Jina DeepSearch** | HTTP (OpenAI-compatible) | Token-priced | — | — | None | Owned by Elastic; pricing page reported 404 (Sept 2026) — unverified |
| **Kagi** | Official remote MCP `https://mcp.kagi.com/mcp` (Search + Extract only) | Not retrieved | — | Search results, no synthesis | None | No deep-research API in docs |
| **Linkup / Valyu** | HTTP | Linkup $0.25–$2.50/run; Valyu $0.10 / $0.50 / $2.50 | Valyu heavy "up to a few hours" | Not verified | Valyu self-reports 72.7% DRACO | Newer entrants; the Reddit thread promoting Valyu reads as vendor-seeded |
| **GPT-Researcher (OSS)** | Local Python / its own MCP | Your LLM + search keys | Minutes | Yes | Lacuna paper: 5.24/10 RACE, **0.290 citation precision** | Active (pushed 2026-09-26, 29.8k stars) |
| **LangChain open_deep_research (OSS)** | Local | Your keys | — | Yes, dedicated citation step | LiveResearchBench best average (73.6), citation association 76.9 (with GPT-5) | **Archived** (last push 2026-08-10) |
| **Stanford STORM (OSS)** | Local | Your keys | — | Yes | Not retrieved | Stale: last push 2025-09-30 |
| **dzhng/deep-research (OSS)** | Local | Your keys | — | Minimal | None | Last push 2026-04-11 |
| **bytedance/deer-flow (OSS)** | Local | Your keys | — | Yes | Deerflow+ (GPT-5) citation association 77.0 | Very active; repositioned as a general "SuperAgent harness" |
| **claude.ai Research mode** | **Chat UI only** — not callable from Claude Code | Included in paid plans | "several minutes" | Yes | None retrieved | Active |
| **Community Claude Code skills** | Drop-in skill | Your tokens | — | Varies | None (self-claims only) | 199-biotechnologies skill 1,155 stars, last push 2026-04-11; largely superseded by the bundled workflow |

---

## 2. Q1 — Pluggable options: findings with sources

### 2.1 Anthropic-native (the option the brief under-weighted)

- **Claude Code ships `/deep-research` as a bundled dynamic workflow.** [page] https://code.claude.com/docs/en/workflows (no page date shown; text references Claude Code versions up to v2.1.271). Verbatim: "`/deep-research <question>` — Fans out web searches on a question across several angles, fetches and cross-checks the sources it finds, votes on each claim, and returns a cited report with claims that didn't survive cross-checking filtered out. Requires the WebSearch tool to be available". Also: "When the verifier agents can't check a claim, such as after a rate limit or API error, the report lists that claim as unverified instead of counting it as refuted." "`/deep-research` runs only when you invoke it."
  - Availability: "Dynamic workflows are available on all paid plans, with Anthropic API access, and on Amazon Bedrock, Google Cloud's Agent Platform, and Microsoft Foundry. On Pro, turn them on from the Dynamic workflows row in `/config`."
  - Cost guardrails: "A workflow spawns many agents, so a single run can use meaningfully more tokens than working through the same task in conversation." Warning at >25 agents or >1.5M projected tokens. Size guideline default `medium` = fewer than 10 agents (`small` on Pro).
  - Runtime limits: no mid-run user input; up to 16 concurrent agents; 1,000 agents per run; `Date.now()` / `Math.random()` throw inside scripts so relaunches are deterministic in structure.
  - Customisation: a run's script can be saved to `.claude/workflows/` or `~/.claude/workflows/` and edited; "If you already have an orchestrator built another way, such as a folder of subagent prompts or a skill that fans work out, you can point Claude at it and ask for a workflow that does the same thing."
  - Implication (my inference, not from the page): it depends on the built-in WebSearch tool, so it inherits that tool's reach. Whether it can use Firecrawl / Arctic Shift / paper search is not stated — a saved, edited copy could, since workflow agents use the session's tools and permission rules.
  - Corroboration: [page] https://paddo.dev/blog/three-ways-deep-research-claude/ (published 2025-12-18, updated Apr and Jun 2026): "Claude Code now ships a first-party `deep-research` skill… adversarially verifies claims, and synthesizes a cited report." Same post: own pipeline cost "$0.20-0.60 per research in December… closer to $1-3" at Opus 4.7 rates; cites Anthropic's multi-agent research system "90.2% improvement over single-agent Opus on internal research evals" (vendor-internal eval, relayed by a third party).
  - Changelog mention [snippet] https://www.gradually.ai/en/changelogs/claude-code/ ("September 2026"): "improved /deep-research reliability on long research briefs by removing unused required fields from the scope step's output."
- **Claude API web search tool.** [page] https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool (no date shown): "$10 per 1,000 searches, plus standard token costs"; "Citations are always enabled for web search" with `url`, `title`, `cited_text` (up to 150 chars), `encrypted_index`; versions `web_search_20250305`, `web_search_20260209` (dynamic filtering via code execution), `web_search_20260318` (response inclusion control). This is mechanically enforced claim-to-span citation — stronger than prompt-enforced citation.
- **claude.ai Research mode.** [snippet] https://support.claude.com/en/articles/11088861-use-research-on-claude: paid plans (Pro/Max/Team/Enterprise) on web, desktop, mobile; "most reports take several minutes". Chat-UI feature; no evidence of an API or Claude Code entry point.

### 2.2 Commercial APIs

- **Perplexity Sonar Deep Research.** Pricing: [snippet] https://docs.perplexity.ai/docs/getting-started/pricing; [page, third party] https://www.cloudzero.com/blog/perplexity-api-pricing/ (2026): $2/M in, $8/M out, $2/M citation tokens, $3/M reasoning tokens, $5/1k searches; "a single query can cost $0.41–$1.32"; "this is where most billing surprises happen". MCP: `perplexityai/modelcontextprotocol` [live GitHub API] 2,546 stars, pushed 2026-09-25.
- **OpenAI.** [page] https://developers.openai.com/api/docs/deprecations: `o3-deep-research` and `o4-mini-deep-research` shut down **2026-07-23**, recommended replacement `gpt-5.6-sol`. [page] https://community.openai.com/t/deprecation-notice-upcoming-model-shutdowns-in-2026/1379553 (2026-04-22). A dedicated successor deep-research API model was not found; [snippet] Wikipedia "ChatGPT Deep Research" says the ChatGPT product moved to a GPT-5.2-based model in Feb 2026 (product, not API).
- **Gemini Deep Research.** [page] https://ai.google.dev/gemini-api/docs/deep-research: agent `deep-research-preview-04-2026`, Interactions API, `background: true`. Pricing [page] https://ai.google.dev/gemini-api/docs/pricing and https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing ($2/M in, $12/M out); "$1-$3 per typical task" is third party (https://www.therundown.ai/tools/gemini-deep-research-agent).
- **Parallel.** [page, vendor] https://parallel.ai/products/task and https://parallel.ai/articles/the-fastest-deep-research-apis-for-ai-agents-in-2026: nine processors $0.005–$2.40/run, median 45 s – 8 min. Free tier [page] https://parallel.ai/blog/free-tier-parallel.
- **Exa.** [page] https://exa.ai/pricing. MCP URL via https://pydantic.dev/docs/ai/harness/exa-search/. Repo `exa-labs/exa-mcp-server` 5,065 stars, pushed 2026-09-29 [live].
- **Tavily.** [page] https://docs.tavily.com/documentation/api-credits: $0.008/credit; Research `pro` 15–250 credits, `mini` 4–110. Repo `tavily-ai/tavily-mcp` 2,416 stars, pushed 2026-09-29 [live].
- **You.com.** [page, vendor] https://you.com/resources/research-api-by-you-com and https://you.com/resources/deep-research-api ("verified 2026-09-04" per page).
- **Firecrawl.** [page] https://www.firecrawl.dev/blog/deep-research-api: "Note (Updated on 2nd feb 2026): This API is being deprecated in favor of our new Search API." https://www.firecrawl.dev/agent.
- **Kagi.** [page] https://kagi.com/api/docs (MCP install line); [page] https://help.kagi.com/kagi/api/overview.html: "The MCP server currently only supports the new Search and Extract APIs"; pricing deferred to kagi.com/api/pricing (not retrieved).
- **Added:** Linkup, Valyu [page, third party] https://www.edenai.co/post/best-deep-research-apis.

### 2.3 Open-source runners — maintenance status [live GitHub API, 2026-09-30]

| Repo | Stars | Last push | Note |
|---|---|---|---|
| assafelovic/gpt-researcher | 29,829 | 2026-09-26 | active |
| langchain-ai/open_deep_research | 12,681 | 2026-08-10 | **archived** |
| stanford-oval/storm | 31,541 | 2025-09-30 | stale one year |
| dzhng/deep-research | 19,746 | 2026-04-11 | slow |
| bytedance/deer-flow | 83,257 | 2026-09-30 | active; now a general agent harness |
| jina-ai/node-DeepResearch | 5,234 | 2026-05-01 | slow |
| MiroMindAI/MiroThinker | 8,431 | 2026-07-06 | top of MiroEval (own benchmark) |
| NVIDIA-AI-Blueprints/aiq | 878 | 2026-09-29 | active |
| HKUDS/Auto-Deep-Research | 1,747 | 2025-10-16 | stale |
| 199-biotechnologies/claude-deep-research-skill | 1,155 | 2026-04-11 | community Claude Code skill |
| jkudish/librarium | 133 | 2026-09-15 | fans one query out to many research APIs |

Dropped as dead or irrelevant for this decision: OpenAI deep-research API (shut down), Firecrawl deep-research endpoint (deprecated), open_deep_research (archived), STORM and Auto-Deep-Research (stale), claude.ai Research mode (not callable).

---

## 3. Q2 — Independent quality evidence

### 3.1 The only independent multi-system table retrieved: LiveResearchBench
[page, full text] arxiv:2510.14240 v5 (2026-04-18), Salesforce / UW / Stanford. Columns: Presentation / Fact & logic consistency / Coverage / Citation association.

| System | Pres. | Consist. | Cover. | Citation assoc. |
|---|---|---|---|---|
| *Single agent + web search* | | | | |
| GPT-5 | 71.6 | 68.3 | 83.4 | 67.6 |
| Claude 4 Sonnet | 81.9 | 67.3 | 49.2 | 37.9 |
| Claude 4.1 Opus | 81.6 | 67.5 | 50.8 | 35.6 |
| Gemini 2.5 Pro | 51.9 | 76.5 | 73.1 | 38.5 |
| Perplexity Sonar Reasoning Pro | 79.6 | 71.9 | 46.7 | 50.1 |
| *Single-agent deep research (commercial)* | | | | |
| OpenAI o3 deep research | 71.3 | 64.2 | 85.0 | **25.6** |
| OpenAI o4-mini deep research | 74.3 | 62.3 | 78.6 | **27.2** |
| Perplexity Sonar Deep Research | 83.5 | 67.4 | 65.5 | 36.6 |
| Gemini Deep Research | 62.1 | 63.0 | 75.8 | 52.1 |
| Grok-4 deep research | 69.1 | 57.4 | 86.3 | 49.5 |
| *Multi-agent* | | | | |
| Open Deep Research (GPT-5) | 81.0 | 71.3 | 65.3 | **76.9** |
| Deerflow+ (GPT-5) | 78.8 | 69.9 | 61.6 | **77.0** |
| Manus | 75.0 | 63.1 | 73.3 | 45.6 |

Quotes: "Open Deep Research achieves the highest average (73.6), followed by GPT-5 (72.7)"; "single-agent deep research models perform worst on Citation Association, primarily because many key statements remain uncited and URLs are often mismatched"; "Most systems are deep searchers, not deep researchers"; multi-agent systems win on citation through "explicit steps for aligning sub-agent outputs with citations or dedicated citation agents".

Reading for this decision: commercial deep-research products buy **coverage** (75–86) and lose on **citation association** (25–52). Claude 4-era single agents with web search had the mirror-image weakness — good presentation, poor coverage (49–51) and poor citation association (36–38). So a bare Claude + search loop is not good either; what worked was an explicit citation-alignment step.
Caveat: all 2025-era models.

### 3.2 DRACO — vendor benchmark, but it contains the closest "same model, harness vs no harness" comparison
[page] https://leaderboard.steel.dev/leaderboards/draco/ ("updated Sep 4, 2026"); paper arxiv:2602.11685 (Feb 2026, Perplexity-authored; 100 tasks, 10 domains).

- Paper rows (Gemini-3-Pro judge): Perplexity Deep Research (Opus 4.6) 70.5%; Perplexity DR (Opus 4.5) 67.2%; **Claude Opus 4.6 + web search + code execution (not a DR agent) 59.8%**; Gemini Deep Research 59.0%; OpenAI DR o3 52.1%; Claude Opus 4.5 + search 46.7%; OpenAI DR o4-mini 41.9%.
- Later self-evals (Anthropic's Opus 4.6 judge): Claude Opus 5 88.6% (effort scaling 83.2 → 88.6, ~980k-token budget), Opus 4.8 80.4%, Opus 4.7 77.7%.
- Judge dependence: "Opus 4.8 scores 80.4% under Anthropic's Opus 4.6 judge and 58.8% under OpenRouter's Gemini 3.1 Pro Preview judge"; "judge choice shifts absolute scores 10–25 points"; "Vendor self-reported… each regime favors its originator"; the original judge model is "now unavailable" — the paper's numbers cannot be reproduced.
- [snippet] Perplexity DR (Opus 4.6) sub-scores: factual accuracy 67.9%, citation quality 64.6%; 245 s latency, 778,711 average input tokens; OpenAI o3 DR 1,808 s.

### 3.3 Citation accuracy / hallucinated citations
- [page, full text] arxiv:2604.03173 (Apr 2026), DRBench table — % non-resolving / % hallucinated URLs: claude-3-7-sonnet-search 8.5 / 3.2; openai-deepresearch 10.1 / 3.5; gemini-2.5-pro-search 5.9 / 4.8; gpt-4o-search-preview 8.8 / 8.8; **gemini-2.5-pro-deepresearch 18.5 / 13.3**. Pooled: deep-research agents 10.7% hallucinated vs 4.8% for search-augmented models. An agentic URL-health self-check cut non-resolving citations to under 1% (GPT-5.1 16.0% → 0.6%; Claude Sonnet 4.5 4.9% → 0.8%). "Tool-based mitigation thus requires not just tool access but competent tool use."
- [abstract] arxiv:2605.06635 "Cited but Not Verified" (May 2026): link validity >94%, relevance >80%, factual accuracy only 39–77%; "Fact Check accuracy drops by approximately 42% on average across two frontier models as tool calls scale from 2 to 150… more retrieval does not produce more accurate citations."
- [abstract] arxiv:2509.04499 DeepTRACE (Sept 2025): citation accuracy 40–80% across systems; one-sided on debate queries.
- [abstract] arxiv:2607.20527: verifier strictness alone moves the measured unsupported-citation rate from ~3% to ~18% on identical outputs.
- [abstract] arxiv:2604.03159 (Apr 2026): search-enabled frontier models produce fully correct BibTeX in 50.9% of entries; "Separating search from revision yields larger gains".
- [abstract] arxiv:2608.24306 (Aug 2026): "84.7% of final-report errors in AI-Q originate at the orchestrator, roughly 31% of them hallucinations" — the orchestration layer, not retrieval, is where reports go wrong.

### 3.4 Other benchmarks — status
- **BrowseComp**: [snippet] https://leaderboard.steel.dev/leaderboards/browsecomp/ and https://benchlm.ai/benchmarks/browsecomp (Sept 2026): top scores 91–92%; "there is no official leaderboard and no independent evaluator: every published BrowseComp figure is self-reported by the lab that produced it".
- **ResearchRubrics** (Scale AI, ICLR 2026): [snippet] https://scale.com/research/researchrubrics; arxiv:2511.07685 — "Leading agents like Gemini's Deep Research and OpenAI's Deep Research achieve under 68% average compliance".
- **DeepResearch Bench**: [snippet] leaderboard repo https://github.com/Ayanami0730/deep_research_bench; evaluator being switched to GPT-5.5 / GPT-5.4-mini after the previous Gemini-2.5-Pro judge was deprecated. A vendor page (https://cellcog.ai/compare/best-deep-research-ai, July 2026) claims CellCog 55.78, Google 49.98, OpenAI 47.84, Perplexity 43.05, xAI 41.22 — self-serving, not verified on the leaderboard.
- **DeepResearch Bench II** [abstract] arxiv:2601.08536: "even the strongest models satisfy fewer than 50% of the rubrics".
- **Dr. Bench** [page, conclusion only] arxiv:2510.02190 v2 (2026-01-29): DRAs "substantially outperform conventional tool-augmented models"; weaknesses: non-convergent retrieval paths, excessive tokens and latency.
- **MiroEval** arxiv:2603.28407, **DREAM** arxiv:2602.18940, **DR3-Eval** arxiv:2604.14683 — abstract level only.
- **Search-time contamination** [abstract] arxiv:2606.05241 (2026-06-03): agents finding benchmark answers online "is widespread and can inflate performance by up to 4%" across six public benchmarks.

### 3.5 Vendor claims vs independent results
See section 6 (contradictions). Pattern: every vendor is #1 on the benchmark it chose or wrote; the two independent academic tables (LiveResearchBench, arxiv 2604.03173) both place commercial deep-research agents *below* simpler configurations on citation integrity.

---

## 4. Q3 — Reddit, HN, X access for agents

### 4.1 Official Reddit API
- [page] https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy (date not captured): "Approval is required: You must request access and get explicit approval before accessing any Reddit data through our API". "This prohibits registering multiple accounts or submitting multiple requests for the same use case." Applies to "bots, AI agents, or non-human operated accounts". "Any research that uses Reddit data collected outside of the RFR Program is in violation of this policy." No scraping or AI training "without express written approval".
- Primary evidence of how approval goes in practice — r/redditdev posts retrieved via Arctic Shift [live]:
  - 2026-04-13, post `1sk68gk`: a Master's student asking for hourly read-only metadata got "cannot grant approval because the submission is not in compliance with Reddit's Responsible Builder Policy and/or lacks necessary details." Top reply (score 6): "they have barley been accepting keys by the looks of this subreddit ever since they made the policy". Other replies point to Arctic Shift.
  - 2026-08-16, `1vpjycu` / `1vpsxr6`: "Data API access request keeps getting rejected with a generic reason — what am I missing? (personal read-only …)".
  - 2026-07-11 `1uthbbh`, 2026-09-08 `1wb0rsj`, 2026-09-10 `1wcihzj`: more rejections; 2026-06-10 `1u1ycgw`: commercial request unanswered since April.
  - AutoModerator on these threads links the policy announcement `r/redditdev/comments/1oug31u` and says: use Devvit, or submit a request if the use case is unsupported.
- Third-party summaries [snippet, vendors selling alternatives]: self-serve app creation closed Nov 2025; free tier 100 QPM per OAuth client if approved; unauthenticated requests 403 (https://www.redditapis.com/blogs/reddit-data-api-2026, https://octolens.com/blog/reddit-api-pricing, https://redditorshop.com/blog/the-end-of-the-self-serve-reddit-api-why-you-can-t-create-an-api-key-in-2026).

**Answer:** a personal, read-only, low-volume script can no longer self-serve an OAuth app; it needs an approval ticket, and the visible track record for exactly that use case is generic rejections.

### 4.2 Licensed vendors and legal posture
- [snippet] Reddit has licensing deals with Google and OpenAI; other search engines were blocked in robots.txt from July 2024 (https://alternativeto.net/news/2024/7/reddit-now-blocking-search-engines-and-ai-bots-from-showing-its-results-except-for-google).
- Reddit sued Perplexity, SerpApi, Oxylabs and AWM Proxy in Oct 2025 (https://searchengineland.com/reddit-sues-perplexity-serpapi-scraping-google-463681). [snippet] https://www.mediapost.com/publications/article/416950/reddit-can-proceed-with-scraping-claims-against-pe.html (2026-08-03): court let DMCA anti-circumvention claims proceed.
- [snippet] Parallel's own Search API example passes `reddit.com` in `exclude_domains`.
- No retrieved page shows any research API returning full Reddit thread text. Routing Reddit through Perplexity is both unverified and the subject of live litigation.

### 4.3 Arctic Shift and PullPush
- **Arctic Shift** [live, 2026-09-30 ~10:35 UTC]: newest post in r/ClaudeAI 10:33:12Z, newest comment 10:35:17Z — lag of seconds to minutes. Returned full post bodies and comment lists for every thread tried, no auth. Repo `ArthurHeitmann/arctic_shift` 1,578 stars, pushed 2026-09-12. Third party (https://think-pol.com/blogs/reddit-archive-api): "best-maintained free option… community-run with no uptime SLA"; bulk dumps lag weeks (a redditor in April 2026: "Latest monthly is 2026_03").
  - Observed gaps: removed posts come back as `[removed]`; two of three title searches returned `data: null` (search endpoint is less reliable than ID lookup).
- **PullPush** [live]: newest comment 09:42:37Z (lag ~0.9 h), but 2 of 3 requests returned HTTP 429, and it held only 4 comments for a test thread. Third party claims ingestion froze in May 2025 (https://think-pol.com/blogs/pullpush-alternative) — contradicted by the live test, but completeness is clearly worse.
- Legal posture: both collect Reddit data outside the Responsible Builder Policy. No takedown evidence retrieved. Risk to a reader is availability (single-maintainer service Reddit could shut off), not something retrieved evidence quantifies.

### 4.4 Reddit MCP servers [live GitHub API]
`jordanburke/reddit-mcp-server` (279 stars, pushed 2026-09-27), `Hawstein/mcp-server-reddit` (184, 2026-06-10), `adhikasp/mcp-reddit` (425, stale since 2025-05-11), `omar16100/reddit-mcp-server` (app-only OAuth), `redditapis/redditapis-mcp` (front-end for a paid proxy). The maintained ones need Reddit OAuth credentials — i.e. they sit behind the same approval gate — or a paid third-party proxy. They add convenience, not access.

### 4.5 Ranking by robustness
1. **Search for discovery + Arctic Shift by ID for content.** Firecrawl search with `includeDomains: ["reddit.com"]` (caller-verified) returns URLs and snippets; Arctic Shift `/api/posts/ids` and `/api/comments/tree` returns the full thread. Real-time, no auth, works today. Weakness: one volunteer-run service with no SLA, outside Reddit's policy.
2. **PullPush as fallback** for the same IDs. Alive but rate-limited and incomplete.
3. **Search snippets only** when both archives fail — label the evidence as snippet-level.
4. **Official OAuth API via approval ticket.** The only policy-compliant route and the most stable if granted, but obtaining it is the unreliable step. Worth filing once (one request per use case is allowed); not worth designing around.
5. **Reddit MCP servers** — only after (4), or with a paid proxy.
6. **Deep-research vendors as a Reddit channel** — unverified and legally contested.

### 4.6 Hacker News and X
- **HN Algolia** [live]: `https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=1` returned a story indexed at 2026-09-30T10:34:14Z. Real-time, no auth, full comment trees via `/items/<id>`. Most robust of the three.
- **X** [snippet] https://docs.x.com/x-api/getting-started/pricing and https://postproxy.dev/blog/x-api-pricing-2026/: pay-per-use only for new signups — $0.005 per post read, $0.010 per user profile; legacy Basic/Pro tiers retired during 2026. Official page not read directly.
- **Discord**: not researched.

---

## 5. Q4 — Failure reports

**Vendor churn**
- OpenAI deep-research API models: released June 2025, deprecation announced 2026-04-22, shut down 2026-07-23 (~13 months). Replacement is a general model. Developer reaction [page] https://community.openai.com/t/o4-mini-deep-research-o3-deep-research-deprecation/1379560 (2026-04-23): "how can we even have the same quality deep research… I couldn't find any code examples."
- Firecrawl deep-research endpoint deprecated 2026-02-02.
- LangChain open_deep_research archived; STORM unmaintained for a year.
- Benchmark judges themselves churn: DRACO's original judge is unavailable; DeepResearch Bench is replacing its deprecated judge.

**Reliability and billing**
- Perplexity forum [snippet]: https://community.perplexity.ai/t/sonar-deep-research-intermittently-fails-to-activate-web-search-via-the-api/4264 (from 2026-03-07 the model intermittently answers "Real-time web search is not available"); https://community.perplexity.ai/t/sonar-deep-research-async-returns-empty-citations-search-results-despite-num-search-queries-10-full-content-no-source-attribution-2026-06-13/5401 (full report, empty citations array); https://github.com/perplexityai/modelcontextprotocol/issues/83 (`perplexity_research` fetch failure).
- Reddit [live via Arctic Shift] r/AI_Agents post `1s7rteo` (2026-03-30), a Claude Code overnight-batch user: "~16% of calls affected since march 7 and you still get billed"; "citation tokens push real cost 5-20x higher". Low engagement and promotes a competitor (Valyu) — treat as weak on its own; the forum threads corroborate the bug.

**Cost blowups**
- [page] https://x.com/ArtificialAnlys/status/1940896348364210647 (mid-2025): o3 deep research "up to ~$30 per API call"; 10 queries cost $100.
- [page] https://til.simonwillison.net/llms/o4-mini-deep-research (Oct 2025): one o4-mini run = 60,506 input / 22,883 output tokens, 77 searches, about $1.10.
- Token-billed services have no per-report ceiling; Parallel, Exa, You.com and Tavily's credit bands are the fixed or bounded ones.

**Fabricated or mis-attributed citations** — section 3.3. LiveResearchBench also notes Manus producing "fictional or non-existent links".

**Source laundering and poisoning**
- [page, abstract] arxiv:2605.24245 (2026-05-22, rev. 2026-09-03): "Poisoning a single URL with as few as 13 words can be sufficient for the attacker's content to be retrieved in 57-76% of the agent executions for a given topic and cited in 38-51% of the generated reports"; poisoning a subreddit gives "30-53% citation rates even when the poison is only 0.5-4% of the retrieved content". Targets: Reddit and Wikipedia.
- [page, abstract] arxiv:2607.20891 (2026-07-23): on DeerFlow, WebThinker and Gemini Deep Research, "introducing one misleading document increases the mean FCAR from 0% in the no-injection control to 54.7%."
- These apply equally to a hand-orchestrated pipeline that reads Reddit. Adding Reddit as a source raises this exposure; it argues for treating Reddit as practitioner testimony to corroborate, never as a sole source.

**Non-reproducibility**
- [snippet] arxiv:2604.14683 DR3-Eval: live-web benchmarks are "difficult to reproduce and prone to evaluation ambiguity".
- DRACO scores differing 10–25 points by judge; arxiv:2607.20527 showing a 3% → 18% swing from verifier strictness alone.
- No practitioner post-mortem of "same query, different report" was retrieved.

---

## 6. Contradictions between sources

1. **Parallel on DeepSearchQA**: vendor says Pro 83%, Ultra4x 86% (parallel.ai); Eden AI reports Pro 62%, Ultra 68.5%, Ultra2x 72.6%.
2. **You.com**: vendor claims #1 on DeepSearchQA at 83.67%; Valyu scored it 52.9% on DRACO. Prices differ between the two You.com pages (frontier $1,200 vs >$2,000 per 1k) and Eden AI (lite $6.50 vs $12; exhaustive $300 vs $450).
3. **DRACO scores are judge-dependent**: Opus 4.8 is 80.4% or 58.8% depending on judge.
4. **Harness value**: DRACO shows a tuned harness adds ~11 points over the same model with plain tools; LiveResearchBench shows commercial harnesses *worst* on citation association; Dr. Bench says DRAs "substantially outperform" tool-augmented models. Different metrics, different model generations — not reconcilable from what was retrieved.
5. **OpenAI replacement model**: official deprecations page says `gpt-5.6-sol`; the April community post says "5.4-Pro". The page was probably updated after the post.
6. **Tavily Research pricing**: official docs publish credit ranges; Eden AI says they are "not published".
7. **PullPush**: think-pol says ingestion has been frozen since May 2025; my live request returned a comment from 2026-09-30 09:42Z. think-pol sells a competing product.
8. **Arctic Shift freshness**: "lags four to six weeks" applies to bulk dumps; the API was real-time in the live test.
9. **Claude Code command name**: official docs say `/deep-research` (workflow); paddo.dev calls it a "skill"; mindstudio.ai describes `/deep`. The official docs settle it: bundled *workflow*, `/deep-research`.
10. **Deep-research cost**: $0.005 (Parallel Lite) to $30 (o3) per report for nominally the same product category.

---

## 7. Could not verify

- Any service's real output quality on *this user's* engineering questions — nothing was run end-to-end.
- Quality, cost and latency of the bundled Claude Code `/deep-research` workflow: no independent evaluation or published figures found. Whether it can use non-WebSearch tools (Firecrawl, paper search, Arctic Shift) without editing a saved copy.
- How "well-prompted Claude Code + search tools" compares with dedicated services on 2026 models under an independent judge. Only proxies exist.
- Whether any vendor (Perplexity, Exa, Tavily, Parallel, You.com, Gemini, OpenAI) returns full Reddit thread text.
- Perplexity bug status today: forum threads seen at snippet level only; not confirmed fixed or open.
- Perplexity official per-token prices (official page seen at snippet level; figures are from third parties).
- Whether OpenAI offers any deep-research-specific API path after 2026-07-23.
- Dr. Bench per-system numbers (only the conclusion was retrieved).
- DeepResearch Bench current leaderboard (only a vendor's summary of it); BrowseComp-Plus; Mind2Web 2.
- Reddit official free-tier limit (100 QPM) and the Nov 2025 cut-off date — third-party vendors only; the policy page's date was not captured.
- Any takedown or legal action against Arctic Shift or PullPush.
- Jina DeepSearch current pricing and status; Kagi API pricing; X API pricing on the official page; Discord access.
- Anthropic's "90.2% improvement" multi-agent figure — relayed by a third-party blog; original not retrieved.
- Tavily's acquisition by Nebius — headline-level snippet only.
- prior, unverified: Pushshift's 2023 shutdown as precedent for archive services being cut off.
