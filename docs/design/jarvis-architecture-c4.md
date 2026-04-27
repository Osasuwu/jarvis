# Jarvis Architecture — C4 Views

Three views: Context (system in its environment), Container (runtime + storage), Component (capabilities). Companion to [jarvis-v2-redesign.md](jarvis-v2-redesign.md).

Rendered SVGs alongside each block: [c4-1.svg](c4-1.svg) Context · [c4-2.svg](c4-2.svg) Container · [c4-3.svg](c4-3.svg) Component. Re-render: `npx -p @mermaid-js/mermaid-cli mmdc -i jarvis-architecture-c4.md -o c4.svg` (writes `c4-1.svg`, `c4-2.svg`, `c4-3.svg`).

## C4 Level 1 — Context

![Context diagram](c4-1.svg)

```mermaid
C4Context
  title Jarvis in its environment

  Person(owner, "Owner", "Solo developer; sole user; strategic stakeholder")

  System(jarvis, "Jarvis", "Personal AI agent for software project work")

  System_Ext(claude_api, "Anthropic Claude", "LLM inference — subscription (Max) for interactive + scheduled tasks; API for cloud-side paths")
  System_Ext(other_llm, "OpenAI / Gemini", "Different-provider review for high-leverage changes")
  System_Ext(supabase, "Supabase", "Postgres — memory facts/episodes, events, goals, credentials")
  System_Ext(voyage, "VoyageAI", "Embeddings (memory recall)")
  System_Ext(github, "GitHub", "Repos, Actions, issues, PRs")
  System_Ext(hibp, "HaveIBeenPwned", "Credential breach probes")

  Rel(owner, jarvis, "Interactive sessions, queue approvals, batched briefs")
  Rel(jarvis, claude_api, "Inference")
  Rel(jarvis, other_llm, "High-leverage review")
  Rel(jarvis, supabase, "Memory + events + cost ledger")
  Rel(jarvis, voyage, "Embedding lookups")
  Rel(jarvis, github, "PR/issue/CI events; gh actions")
  Rel(jarvis, hibp, "Periodic credential probe")
```

## C4 Level 2 — Container

![Container diagram](c4-2.svg)

```mermaid
C4Container
  title Jarvis runtime + storage

  Person(owner, "Owner")

  System_Boundary(jarvis_sys, "Jarvis") {
    Container(claude_code, "Claude Code (interactive)", "Native tools + MCP", "Owner-driven sessions; primary execution")
    Container(scheduled, "Scheduled tasks", "Claude Code via Max", "Reflection handlers, autonomous loop, periodic probes")
    Container(hooks, "Hooks layer", "PreToolUse / session-context / secret-scanner / protected-files", "Gate + audit per tool call")
    Container(subagents, "Subagents", "Worktree-isolated dispatch", "Parallel narrow work")
    Container(mcp_memory, "mcp-memory server", "Python MCP", "Memory + goals + decisions + credentials API")

    ContainerDb(pg, "Supabase Postgres", "Postgres + pgvector", "memory_facts (bi-temporal) + memory_episodes (append-only) + events (canonical observability + cost ledger) + goals + credential_registry")

    Container(cloud_tasks, "Supabase scheduled tasks", "execute_sql via canonical fns", "Cloud-side periodic jobs")
  }

  System_Ext(claude_api, "Anthropic Claude")
  System_Ext(other_llm, "OpenAI / Gemini")
  System_Ext(github, "GitHub")
  System_Ext(voyage, "VoyageAI")

  Rel(owner, claude_code, "CLI")
  Rel(claude_code, hooks, "Every tool call")
  Rel(claude_code, mcp_memory, "memory_*, goal_*, decision_*")
  Rel(claude_code, subagents, "Delegate narrow work")
  Rel(claude_code, claude_api, "Inference")

  Rel(scheduled, claude_api, "Inference (subscription)")
  Rel(scheduled, mcp_memory, "Memory ops")
  Rel(scheduled, other_llm, "High-leverage review")

  Rel(mcp_memory, pg, "Reads/writes via canonical Postgres fns")
  Rel(mcp_memory, voyage, "Embeddings on memory writes")

  Rel(cloud_tasks, pg, "execute_sql via canonical fns")

  Rel(github, pg, "Action signals → events table (event_driven_perception)")
  Rel(hooks, pg, "Hook firings + denials → events")
  Rel(subagents, pg, "Subagent activity (trace propagation) → events")
```

## C4 Level 3 — Component

![Component diagram](c4-3.svg)

```mermaid
C4Component
  title Jarvis capabilities (17 in 5 layers)

  Container_Boundary(ident, "Identity Layer") {
    Component(c1, "C1 Identity & values", "SOUL + CLAUDE.md, owner-authored")
    Component(c2, "C2 Goals & priorities", "Active strategic context, ranks work")
  }

  Container_Boundary(cog, "Cognition Layer") {
    Component(c3, "C3 Memory", "C3-F facts (bi-temporal) + C3-E episodes")
    Component(c4, "C4 Reasoning & planning", "Plans as events; templates")
    Component(c5, "C5 Reflection / learning", "Synthesize new + challenge stale")
    Component(c6, "C6 Decision gating", "Single canonical gate")
  }

  Container_Boundary(act, "Action Layer") {
    Component(c7, "C7 Execution", "Native tools + MCP")
    Component(c8, "C8 Sub-orchestration", "Worktree isolation gates")
    Component(c9, "C9 Tool / env interface", "MCP + filesystem + shell")
    Component(c10, "C10 Research", "External info gathering")
  }

  Container_Boundary(iface, "Interface Layer") {
    Component(c11, "C11 Perception", "External signals → events")
    Component(c12, "C12 Communication", "CLI + briefs + critical alerts")
  }

  Container_Boundary(cross, "Cross-cutting") {
    Component(c13, "C13 Budget / cost", "Per-service caps + model router")
    Component(c14, "C14 Security & privacy", "Hooks + audit + rotation")
    Component(c15, "C15 Self-improvement", "M0–M3 modification tiers")
    Component(c16, "C16 Verification / QA", "Specialized reviewers")
    Component(c17, "C17 Observability", "Canonical events substrate")
  }

  Rel(c11, c17, "emits external events")
  Rel(c6, c17, "emits decision events")
  Rel(c5, c17, "reads events for reflection")
  Rel(c5, c3, "writes mutations (synthesis + supersession)")
  Rel(c6, c3, "narrow recall (act/ask context)")
  Rel(c6, c2, "consults active goals")
  Rel(c4, c10, "research feeds reasoning")
  Rel(c4, c17, "plan events")
  Rel(c8, c17, "subagent activity (trace_id)")
  Rel(c16, c17, "reads PR + subagent events")
  Rel(c16, c5, "FP/FN labels feed calibration")
  Rel(c13, c17, "reads cost events; emits cap-state")
  Rel(c14, c17, "hook fires + denials")
  Rel(c15, c16, "reviewed by (with bootstrap protection)")
  Rel(c15, c5, "improvement candidates from reflection")
  Rel(c12, c6, "owner approval → decision events")
  Rel(c1, c6, "values shape default behaviour")
  Rel(c2, c5, "goal-driven stale-challenge triggers")
```

## Reading guide

- **Identity layer** is owner-authored axioms — the alignment substrate. Never auto-mutated (M3).
- **Cognition layer** is what Jarvis *thinks with*. C3 is the durable substrate; C4 sequences work; C5 is the active loop that mutates C3 from C17 events; C6 is the act/ask classifier consulted before every tool call.
- **Action layer** is what Jarvis *does*. C7/C8/C9 are the runtime; C10 is the external info-gathering arm.
- **Interface layer** is the boundary with the owner — C11 ingests, C12 communicates out.
- **Cross-cutting** layer wraps everything: C17 is the substrate every event passes through; C13/C14/C16/C15 are governance/safety/quality/evolution functions that consume and gate.

The single most load-bearing edge is **everything → C17**: substrate-as-source-of-truth means audit, reflection, calibration, cost, and review all share the same data.
