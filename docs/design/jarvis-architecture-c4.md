# Jarvis Architecture — C4 Views (revised 2026-04-28)

Four views: Context (system in environment), Container (runtime + storage), Component (17 capabilities in 5 layers + cross-cutting), Event-substrate dataflow (the load-bearing edge: `everything → C17`). Companion to [`jarvis-v2-redesign.md`](jarvis-v2-redesign.md). Reflects L3 concrete adoptions folded in 2026-04-27/28 — see [`jarvis-build-vs-buy.md`](jarvis-build-vs-buy.md).

Rendered SVGs alongside each block: [c4-1.svg](c4-1.svg) Context · [c4-2.svg](c4-2.svg) Container · [c4-3.svg](c4-3.svg) Component · [c4-4.svg](c4-4.svg) Event dataflow. Re-render: `npx -p @mermaid-js/mermaid-cli mmdc -i jarvis-architecture-c4.md -o c4.svg` (writes `c4-1.svg`…`c4-4.svg`).

## C4 Level 1 — Context

![Context diagram](c4-1.svg)

```mermaid
C4Context
  title Jarvis in its environment

  Person(owner, "Owner", "Solo developer; sole user; strategic stakeholder")

  System(jarvis, "Jarvis", "Personal AI agent for software project work — Claude Code-native + Supabase substrate")

  System_Ext(claude_api, "Anthropic Claude", "LLM inference — Max subscription for interactive + scheduled; API for cloud-side paths only")
  System_Ext(other_llm, "OpenAI / Gemini", "Different-provider review for high-leverage changes (~25% PRs steady-state)")
  System_Ext(supabase, "Supabase Postgres", "pgvector + pg_cron — memory facts/episodes, OTel GenAI events, decision_queue, goals, credentials")
  System_Ext(voyage, "VoyageAI", "Embeddings (memory recall, goal embeddings, fact promotion)")
  System_Ext(github, "GitHub", "Repos, Actions, issues, PRs — event_driven_perception via Actions → Supabase")
  System_Ext(hibp, "HaveIBeenPwned", "Weekly credential breach probes")
  System_Ext(plugin_eco, "Anthropic plugins ecosystem", "claude-plugins-official + skills repos — fork base for C16, install targets for C12/C9")

  Rel(owner, jarvis, "Interactive sessions, queue approvals, batched briefs")
  Rel(jarvis, claude_api, "Inference (subscription primary)")
  Rel(jarvis, other_llm, "High-leverage review")
  Rel(jarvis, supabase, "Memory + events + cost ledger + queues")
  Rel(jarvis, voyage, "Embedding lookups")
  Rel(jarvis, github, "PR/issue/CI events; gh actions")
  Rel(jarvis, hibp, "Periodic credential probe")
  Rel(jarvis, plugin_eco, "Plugin install / fork base / skill scaffolds")
```

## C4 Level 2 — Container

![Container diagram](c4-2.svg)

```mermaid
flowchart TB
    owner((Owner))

    subgraph SURFACE[Claude Code surface]
        direction TB
        claude_code[Claude Code interactive<br/>native tools + MCP + plugins]
        hooks[Hooks layer<br/>PreToolUse / PostToolUse / SessionStart / Stop<br/>6-outcome gate: ALLOW/LOG/EXPLAIN/QUEUE/DEFER/BLOCK]
        subagents[Subagents<br/>isolation:worktree + HEAD-shift detector<br/>+ diff-outside-scope post-gate]
        scheduled[Scheduled tasks Routines<br/>reflection / autonomous loop / HIBP / cost reconciliation<br/>TaskCreated hook + --resume]
    end

    subgraph PLUGINS[Plugins]
        direction TB
        plugin_review[Code Review plugin fork<br/>5 reviewers + verifier<br/>+ diff-coherence / cross-device / smoke-test]
        plugin_misc[Other Anthropic plugins<br/>session-report / hookify / claude-md-management<br/>/ mcp-server-dev / pr-review-toolkit]
    end

    subgraph MCPS[MCP servers]
        direction TB
        mcp_memory[mcp-memory MCP<br/>imports pgvector, litellm.cost_calculator,<br/>crepes, prometheus-eval, traceloop-sdk<br/>uses pg_bitemporal SQL]
        mcp_plan[Plan MCP — LangGraph carveout<br/>PostgresStore + checkpointer]
        mcp_research[Research MCPs<br/>GPT Researcher + sequential-thinking<br/>+ firecrawl + context7]
    end

    subgraph STORAGE[Supabase storage]
        direction TB
        pg[(Postgres + pgvector + pg_cron<br/>memory_facts pg_bitemporal +<br/>memory_episodes + events OTel GenAI +<br/>materialized projections +<br/>decision_queue + goals + credentials)]
        cloud_tasks[Supabase scheduled tasks<br/>execute_sql + REFRESH MATERIALIZED VIEW]
    end

    subgraph EXT[External services]
        direction LR
        claude_api[Anthropic Claude<br/>Max sub primary]
        other_llm[OpenAI / Gemini<br/>different-provider]
        voyage[VoyageAI<br/>embeddings]
        github[GitHub<br/>repos + Actions]
        hibp[HaveIBeenPwned]
    end

    owner -->|CLI| claude_code
    claude_code --> hooks
    claude_code --> subagents
    claude_code --> plugin_review
    claude_code --> plugin_misc
    claude_code --> mcp_memory
    claude_code --> mcp_plan
    claude_code --> mcp_research
    claude_code --> claude_api

    scheduled --> claude_api
    scheduled --> mcp_memory
    scheduled --> other_llm
    scheduled --> hibp

    mcp_memory --> pg
    mcp_memory --> voyage
    mcp_plan --> pg
    mcp_research --> voyage

    hooks --> pg
    subagents --> pg
    plugin_review --> pg
    cloud_tasks --> pg
    github --> pg
```

## C4 Level 3 — Component

![Component diagram](c4-3.svg)

```mermaid
flowchart TB
    subgraph IDENT[Identity Layer]
        direction LR
        c1[C1 Identity<br/>SOUL.md + CLAUDE.md<br/>M3 protected]
        c2[C2 Goals<br/>active strategic context<br/>goal_slug FK + VoyageAI embeddings]
    end

    subgraph COG[Cognition Layer]
        direction LR
        c3[C3 Memory<br/>C3-F facts pg_bitemporal +<br/>C3-E episodes append-only<br/>pgvector RRF hybrid search]
        c4[C4 Reasoning<br/>plans on LangGraph PostgresStore MCP<br/>Magentic ledger schema<br/>sequential-thinking on novel]
        c5[C5 Reflection<br/>synth + stale-challenge + calibrator<br/>crepes Mondrian CP + netcal +<br/>prometheus-eval prompts]
        c6[C6 Decision gating<br/>single canonical gate<br/>6 outcomes incl. DEFER<br/>decision_queue table]
    end

    subgraph ACT[Action Layer]
        direction LR
        c7[C7 Execution<br/>native + MCP +<br/>PostToolUse duration_ms]
        c8[C8 Sub-orchestration<br/>worktree + HEAD-shift / diff-outside-scope<br/>Magentic ledger handoff +<br/>TTL+heartbeat lock]
        c9[C9 Tool / env<br/>MCP OAuth 2.1 + RFC 8707<br/>mcp-builder scaffold]
        c10[C10 Research<br/>GPT Researcher MCP primary +<br/>STORM deep-dive + firecrawl + context7]
    end

    subgraph IFACE[Interface Layer]
        direction LR
        c11[C11 Perception<br/>GHA → events<br/>YAML noise filter +<br/>signal_dropped audit]
        c12[C12 Communication<br/>CLI + session-report plugin +<br/>claude-md-management +<br/>c12_send_intent gate]
    end

    subgraph CROSS[Cross-cutting]
        direction LR
        c13[C13 Budget<br/>litellm.cost_calculator lib<br/>tokonomics + tiktoken<br/>declarative router]
        c14[C14 Security<br/>Sprint 1 + HIBP +<br/>Supabase RLS + principal verify]
        c15[C15 Self-improve<br/>M0-M3 tiers<br/>4 safeguard layers]
        c16[C16 Verification<br/>Code Review plugin fork +<br/>diff-coherence + cross-device + smoke-test]
        c17[(C17 Observability<br/>single canonical events<br/>OTel GenAI semconv +<br/>materialized projections pg_cron)]
    end

    c11 --> c17
    c6 --> c17
    c5 --> c17
    c5 --> c3
    c6 --> c3
    c6 --> c2
    c4 --> c10
    c4 --> c17
    c8 --> c17
    c7 --> c17
    c16 --> c17
    c16 --> c5
    c13 --> c17
    c14 --> c17
    c15 --> c16
    c15 --> c5
    c12 --> c6
    c1 --> c6
    c2 --> c5
```

## C4 Level 4 — Event-substrate dataflow

The single load-bearing edge of the architecture: every cap reads from / writes to C17 events. This view shows ordering, projection refresh, and the reflection mutation arm.

![Event dataflow](c4-4.svg)

```mermaid
sequenceDiagram
    autonumber
    participant CC as Claude Code session
    participant Hook as PreToolUse hook / C6 gate
    participant Tool as Tool exec / C7
    participant SA as Subagent / C8
    participant Pg as Supabase events / C17
    participant MV as Materialized projections / pg_cron
    participant C5h as Reflection handlers / C5
    participant C3w as Memory write fn / C3
    participant C13r as Budget views / C13
    participant C16r as Reviewer / C16

    CC->>Hook: tool_call action target payload
    Hook->>Hook: classify with state probes - git, convergence, harness
    Hook->>Pg: emit decision_made event - auto, no manual record_decision

    alt outcome ALLOW or LOG_AND_PROCEED or EXPLAIN
        Hook-->>CC: PROCEED
        CC->>Tool: invoke
        Tool->>Pg: emit tool_call event - OTel GenAI semconv with duration_ms, cost_usd, model
    else outcome DEFER per v2.1.89
        Hook-->>CC: pause then resume after async state probe
    else outcome QUEUE or BLOCK
        Hook->>Pg: emit gated event - queue_id or block_reason
        Hook-->>CC: hold
    end

    par Subagent activity
        SA->>Pg: emit events with trace_id - parent-event linkage, Magentic ledger handoff
    and Projection refresh
        Note over Pg, MV: pg_cron hourly REFRESH MATERIALIZED VIEW CONCURRENTLY
        Pg->>MV: events_cost_by_day_mv
        Pg->>MV: decisions_by_trace_mv
        Pg->>MV: last_run_by_actor_mv
    end

    Note over Pg, C5h: pg LISTEN/NOTIFY on outcome_recorded, owner_correction, anomaly_flagged, recall_failed
    Pg-->>C5h: trigger handler - synthesizer or stale-challenge or calibrator
    C5h->>C5h: pattern extraction with crepes Mondrian CP for sparse classes
    C5h->>C3w: candidate fact - auto-write if confidence above class threshold, else queue
    C5h->>Pg: emit judgment_made or mutation_proposed or stale_challenge_fired

    MV-->>C13r: cap-proximity reads
    C13r-->>Hook: enrich state probe with budget context

    Note over Pg, C16r: PR opened - reviewer pipeline reads events by trace_id
    C16r->>Pg: read claimed_files vs git diff - subagent fabrication detection
    C16r->>Pg: emit reviewer FP/FN labels feeding C5 calibrator

    Note over Pg: Single canonical events table. OTel GenAI columns verbatim. trace_id via contextvars + uuid. Best-effort write semantics - NOTIFY plus row insert. Recall and write never block on event-row failure.
```

## Reading guide

- **Identity layer** is owner-authored axioms — the alignment substrate. Never auto-mutated (M3). Drift detection delegated to `claude-md-management` plugin (C12).
- **Cognition layer** is what Jarvis *thinks with*. C3 is the durable substrate (bi-temporal facts + episodic events); C4 sequences work on a LangGraph-backed plan store; C5 is the active loop that mutates C3 from C17 events with class-conditional calibration; C6 is the act/ask classifier consulted before every tool call.
- **Action layer** is what Jarvis *does*. C7/C8/C9 are the runtime; C10 is the external info-gathering arm with GPT Researcher as primary engine.
- **Interface layer** is the boundary with the owner — C11 ingests with a YAML noise filter; C12 communicates out via CLI + Anthropic plugins.
- **Cross-cutting** layer wraps everything: C17 is the substrate every event passes through; C13/C14/C16/C15 are governance/safety/quality/evolution functions that consume and gate.

The single most load-bearing edge is **everything → C17** (visualized in Level 4): substrate-as-source-of-truth means audit, reflection, calibration, cost, and review all share the same data. Materialized projections per hot read path (per Q1 reframe — Honeycomb / Greptime "Observability 2.0" guidance) prevent read-amplification on long streams.

## What changed vs prior C4 (2026-04-27)

- **Level 1**: added Anthropic plugins ecosystem as an external system (fork-source + install-target).
- **Level 2**: switched from `C4Container` DSL to `flowchart TB` with subgraph zoning (cleaner auto-layout, less arrow overlap). Split MCP layer into 3 distinct MCPs (memory, plan/LangGraph carveout, research bundle) + plugin layer (forked code-review + installed plugins). pg now explicitly shows pg_bitemporal column shape, OTel GenAI semconv columns, materialized projections, decision_queue.
- **Level 3**: switched from `C4Component` DSL to `flowchart TB` with layer subgraphs. Every component description now carries the concrete L3 adoption (lib name / SQL file / plugin URL) instead of generic "current pattern" language. C6 gate enum expanded to 6 outcomes; C8 worktree gates explicit; C15 stacks 4 safeguard layers; C16 fork-base named; C17 names projection set.
- **Level 4 (new)**: event-substrate dataflow sequence — visualizes the load-bearing edge, including DEFER outcome, parallel projection refresh, LISTEN/NOTIFY trigger to C5, and best-effort write semantics from C3-Q2.
