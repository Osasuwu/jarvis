# Jarvis Threat Model

Date: 2026-04-15
Scope: Full system including multi-agent future (Federation & Delegation pillar)

## Data Classification

| Level | Definition | Examples | Storage rules |
|-------|-----------|----------|---------------|
| **Secret** | Raw credentials, API keys, tokens | `SUPABASE_KEY`, `VOYAGE_API_KEY`, SSH keys | `.env` only. Never in memory, git, issues, logs |
| **Sensitive** | Personal data, private notes, financial | Obsidian vault, Telegram messages, credential metadata | Supabase (encrypted at rest), local files. Never in public repos |
| **Internal** | Project decisions, architecture, working state | Memories, goals, outcomes, working state | Supabase, git (private repos OK, public repos OK if no sensitive data) |
| **Public** | Open source code, docs, issues | GitHub repo, PR descriptions, README | Anywhere |

## Attack Surface

### 1. MCP Servers (7 active)

See `docs/security/mcp-audit.md` for per-server analysis. Summary:

| Vector | Risk | Current mitigation |
|--------|------|--------------------|
| Secret exfiltration via GitHub writes | High | PreToolUse secret scanner (12 patterns) |
| Secret exfiltration via bash | High | PreToolUse bash danger scanner (8 patterns) |
| Secret exfiltration via memory_store | Medium | **Sprint 2: #159** |
| Prompt injection via firecrawl/web | Medium | Claude instruction hierarchy |
| Prompt injection via GitHub issues | Medium | AFK lane intake (#2005): worker refused unless the issue body equals the `labeled` payload body and carries no `osasuwu-bot` edit (D9); refused when unclassified, closed, claimed by a PR, in flight or blocked (D8). Worker without a write token (D4) is committed but not yet enforced (#1966) |
| Bot releases a merge hold (AP5, #1999) | High | The worker is `osasuwu-bot` with write access, so it can remove `waiting-human-review` or a review request. `waiting-human-review` (run from the base ref by `.github/scripts/waiting_human_review.py`) treats a release by the bot or any `*[bot]` actor as no release: it re-applies the label and stays red until a human removes it |
| Bot dispatches itself (AP6, #1999) | High | Intake refuses `agent:dispatch` applied by the bot, a `*[bot]` login or an unknown labeller (`bot-labelled`, `labeller-unknown`); only a human's label starts a run |
| Bot added to a trusted/bypass author list (#1999) | High | `tests/ci/test_bot_bypass_list_guard.py` under the required `pytest` check: no `osasuwu-bot` in the code-gate author rule, in any `allowed_bots`, or in the `require-linked-issue` bypass; `allowed_bots: "*"` also fails |
| N-run gate counts bot-edited-by-human or bot-commented runs as clean (#1999) | Medium | `lane_ledger.py` `merged-unedited` means `human-touched: no`: no non-bot commit, comment or non-approving review; `lane_ledger.py touched <owner/repo#N>` lists the touches |
| Data corruption via memory writes | Medium | Soft delete with 30-day retention (#160) |
| Obsidian vault data exposure | Low | Local only, no network |

### 2. Subagents (current + Federation & Delegation pillar)

| Vector | Risk | Current mitigation |
|--------|------|--------------------|
| Agent writes secret to memory | Medium | **Sprint 2: #159** |
| Agent modifies protected files | Medium | **Sprint 2: #162** |
| Agent corrupts git state (wrong branch, conflict) | Medium | **Sprint 2: #163** |
| Agent scope creep (edits unrelated files) | Low | AGENTS.md rules (soft) |
| Agent-to-agent data poisoning | Low | Not yet addressed (Federation & Delegation pillar) |
| Agent infinite loop / resource waste | Low | Token budget awareness in AGENTS.md |

### 3. External Integrations

| Vector | Risk | Current mitigation |
|--------|------|--------------------|
| Compromised dependency (supply chain) | Medium | Gitleaks CI, Dependabot (partial) |
| GitHub token over-privilege | Low | Copilot-managed token scope |
| Supabase API key exposure | High | Secret scanner, .env exclusion |
| Voyage AI API key exposure | Medium | Secret scanner |

### 4. Local Environment

| Vector | Risk | Current mitigation |
|--------|------|--------------------|
| .env file read by agent | High | `permissions.deny` globs in `~/.claude/settings.json` (`Read`/`Edit` on `**/.env*`) — a Read deny also blocks Edit |
| Home directory dotfile access | Medium | `permissions.deny` globs on `~/.ssh/**`, `~/.aws/**`, `~/.gnupg/**`, `**/id_rsa*`, `**/*.pem` |
| Cross-device config divergence | Low | ~~Portable .mcp.json (no hardcoded paths)~~ — no longer applies; MCP servers are registered per-device by hand now (`claude mcp add --scope user`), not via a portable repo file (#1801) |

## Data Flow

```
User ──→ Claude Code ──→ MCP Servers ──→ External APIs
              │                              │
              ├── Subagents                   ├── Supabase (memory, goals, events)
              │     └── same MCP access       ├── GitHub (issues, PRs, code)
              │                               ├── Voyage AI (embeddings)
              ├── Hooks (PreToolUse)           └── Firecrawl (web scraping)
              │     └── secret-scanner.py
              │
              └── Git (local repo ──→ GitHub remote)
```

Key flows to protect:
1. **Any write path to public GitHub** — secrets must not leak via issues, PRs, commits, comments
2. **Any write to Supabase memory** — secrets must not be stored in memory content
3. **Agent output → agent input** — one agent's output becomes context for another; poisoned output propagates
4. **Web content → Claude context** — scraped pages may contain adversarial instructions

## Risk Matrix

| Threat | Likelihood | Impact | Risk | Status |
|--------|-----------|--------|------|--------|
| Secret leaked in GitHub PR/issue | Low | Critical | High | Mitigated (scanner) |
| Secret leaked in bash command | Low | Critical | High | Mitigated (scanner) |
| Secret stored in Supabase memory | Low | High | Medium | Mitigated (scanner #159) |
| Agent deletes important memory | Medium | Medium | Medium | Mitigated (soft delete #160) |
| Agent modifies protected config | Low | High | Medium | Mitigated (boundaries #162) |
| Agent breaks git state | Medium | Low | Medium | Mitigated (rollback #163) |
| Prompt injection via web scrape | Low | Medium | Low | Accepted (Claude instruction hierarchy) |
| Supply chain attack via dependency | Low | High | Medium | Partial (Dependabot) |
| Prompt injection via GitHub issue | Low | Medium | Low | Partial (intake gate #2005; no-token worker D4 pending #1966) |
| Agent-to-agent poisoning | Low | Medium | Low | Deferred (Federation & Delegation pillar) |

## Mitigations Summary

### Preventive (stop it from happening)
- [x] Secret scanner on GitHub writes (PreToolUse hook)
- [x] Secret scanner on bash commands (PreToolUse hook)
- [x] Secret scanner on memory_store (#159)
- [x] Protected file write blocking (#162)
- [x] Secret scanner on file writes — Edit/Write/NotebookEdit (#1418)
- [x] `permissions.deny` globs for credential paths (settings.json)
- [x] Gitleaks pre-commit hook + CI workflow
- [x] Credential registry with CHECK constraint (no values stored)

### Detective (know when it happened)
- [x] Gitleaks CI on PRs
- [x] Audit trail for agent actions (#161)
- [ ] Dependabot alerts (partially configured)

### Corrective (undo damage)
- [x] Soft delete for memory with 30-day retention (#160)
- [x] Rollback strategy for agent work (#163)
- [x] Git history (revert commits)

### Accepted Risks

Jarvis serves one principal per instance: each operator hosts their own. A host repo can still
have collaborators, and their issues, PRs and comments reach the agent as data, never as the
principal's instructions. So no risk below is accepted "because there is only one person" — that
reason changes meaning silently when a collaborator appears. Each one names the condition it rests
on and whether the condition holds on a host repo with collaborators (#2126).

- **Prompt injection via web**: Claude's instruction hierarchy (system > user > tool output) is the defense. No additional mitigation planned unless incidents occur.
  - *Condition:* none on headcount; the attacker is whoever controls the page.
  - *With collaborators:* holds unchanged.
- **Prompt injection via GitHub issues**: the AFK lane intake gate narrows it (see Attack Surface); until the no-token worker (D4, #1966) lands, a body the human labelled and approved is still trusted input.
  - *Condition:* the human who applies `agent:dispatch` is the principal. Intake refuses a bot or an unknown labeller, but accepts any other login that can label.
  - *With collaborators:* holds on jarvis, where the principal is the only human collaborator (checked 2026-10-21). It does not hold on a host where collaborators can label: their label would make their own issue body trusted input. The lane is frozen (decision 2026-10-17; `agent-dispatch.yml` disabled) and no other host has adopted it; labellers other than the principal are parked with #2107. Outside the lane, the orchestrator dispatches only issues the principal selected, and reads collaborators' comments on them as data (decision 2026-10-17, D3).
- **No per-person isolation in the Supabase store**: RLS is enabled, but no policy tells one person from another. Policies are written per key role (anon, authenticated), the service role bypasses them, and the only row-level narrowing is a `sandcastle:` provenance prefix on anon writes to `task_outcomes` and `events_canonical`, which marks the writing pipeline, not a person.
  - *Condition:* one principal per instance — the project's URL and keys are held only by that principal's own sessions, devices and machine identities.
  - *With collaborators:* holds while none of them holds a key. Being a collaborator grants no key: collaborators reach the agent through GitHub content, which is data. An injected instruction to read or write the store belongs to the prompt-injection risks above; per-person RLS would not stop it, since the agent's own key is allowed. The condition breaks as soon as a second person holds a key: a shared instance, or a key stored as an Actions secret in a repo where someone other than the principal has write access (write access can push a workflow that reads the repo's secrets). Per-person RLS policies are needed from then on.
- **Agent-to-agent poisoning**: Deferred to Federation & Delegation pillar when multi-agent architecture is designed.
  - *Condition:* the agents whose outputs feed each other run inside this principal's instance.
  - *With collaborators:* holds for that scope. A collaborator's own agent writing to a shared host repo is not covered by this deferral: its issues, PRs and comments arrive as GitHub content, so they are data and fall under the prompt-injection risks above.
