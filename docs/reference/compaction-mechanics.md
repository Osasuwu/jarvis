# Claude Code Compaction Mechanics & Resilience

**Related**: #1204 (preserving prohibiting rules through compaction)

## How Auto-Compaction Works

Claude Code auto-compacts long sessions automatically as you approach the context window limit. When compaction triggers:

1. **Summary generation**: Claude is instructed to summarize the session preserving:
   - Your requests and intent
   - Key technical concepts
   - Files examined or modified (with code snippets)
   - Errors and how they were fixed
   - Pending tasks
   - Current work

2. **What is discarded**: Full tool outputs, intermediate reasoning, and verbose action logs

3. **Token cost**: The summary typically costs ~12% of pre-compaction tokens

4. **Extended thinking**: As of Claude Code v2.1.198+, summarization inherits your session's extended thinking configuration

### Trigger Thresholds

- **Default behavior**: Auto-compact when approaching context window limit
  - Sonnet 5: ~967K tokens (of 1M window)
  - Opus 4.8+ (200K mode): at 200K boundary
  - Opus 4.6 (without extended): at 200K
  - Others: at model's native context limit

- **Configuration**:
  - `/autocompact 500k` — sets threshold in settings (persistent)
  - `--autocompact 500k` — CLI flag (this session only)
  - `CLAUDE_CODE_AUTO_COMPACT_WINDOW=500000` — env var (takes precedence)
  - Valid range: 100K–1M tokens

## What Survives Compaction

| Mechanism | After Compaction | Restored How |
|-----------|------------------|--------------|
| System prompt & output style | ✅ Unchanged | Built-in (never summarized) |
| Project CLAUDE.md | ✅ Re-read | Auto-loaded from disk |
| Project AGENTS.md (native read, no CLAUDE.md) | ❓ Undocumented | The memory docs state the guarantee for CLAUDE.md only; unverified for natively-read AGENTS.md (#1955) |
| User-level rules (unscoped) | ✅ Re-read | Auto-loaded from disk |
| MEMORY.md (auto-memory) | ✅ Re-injected | Auto-loaded from disk |
| SessionStart `compact` matcher | ✅ Re-executed | Hook system (post-compaction) |
| Invoked skill bodies | ✅ Re-injected | Capped at 5K/skill, 25K total |
| Path-scoped rules | ❌ Lost | Until file in that dir read again |
| Nested CLAUDE.md (subdirs) | ❌ Lost | Until file in that dir read again |
| Skill index listing | ❌ Lost | Only skills you invoked are re-injected |

## PreCompact Hook Limitations

The PreCompact hook runs **before** compaction and can:
- ✅ Block compaction entirely (exit code 2 or `{"decision": "block"}`)
- ✅ Log/monitor that compaction is starting
- ✅ Capture pre-compaction state for later recovery

But it **cannot**:
- ❌ Inject custom instructions into the summary prompt
- ❌ Inject context into the compaction summary
- ❌ Modify how the summary is generated
- ❌ Persist data across the compaction boundary (compaction = context reset)

### PreCompact Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/current/working/directory",
  "permission_mode": "default",
  "hook_event_name": "PreCompact",
  "hook_event_source": "manual"  // or "auto"
}
```

## Preserving Rules Through Compaction (#1204, superseded)

**Problem**: Prohibiting rules and standing orders ("don't touch X", "never do Y") die during compaction because they're part of the session history, not the persistent system state.

**Original solution (#1204/#1536, removed)**: `pre-compact-backup.py` used to keyword-scan CLAUDE.md files and re-inject a "Prohibiting Rules & Standing Orders" section into the snapshot. This duplicated a more reliable mechanism that had shipped five days earlier (#1417/#1418, see below) and was removed as dead weight (2026-08-25).

**Current solution**: root `AGENTS.md` is read natively by Claude Code (>= v2.1.277) because the repo has no `CLAUDE.md` (#1955; until then it rode a bare `@AGENTS.md` line in a project `CLAUDE.md` shim, #1417/#1418, rebuilt by #1791). Project instruction files are assembled into the prompt at launch and are never subject to compaction's summarization or the hook's own best-effort extraction. **Open question:** the Claude Code memory docs promise re-read-after-`/compact` for project-root `CLAUDE.md`, and do not say whether a natively-read `AGENTS.md` takes the same path; #1955 did not verify it. If a rule is observed to vanish after compaction, that is the first suspect. This is strictly more reliable than the old keyword-scan-into-snapshot approach: no heuristic matching, no dependency on the PreCompact hook running, no risk of the recovery payload's size budget dropping the section.

Rules that need to survive compaction belong in `AGENTS.md` (or another bare-`@import`ed file), not in prose elsewhere.

## Context layering is one-directional

A repo file may cite user-level (`~/.claude/CLAUDE.md`, a `~/.claude/reference/*` doc); user-level
must never point back at a repo's own `CONTEXT.md` or other repo-local file. User-level content
loads in every repo a session touches, so a pointer into one repo's `CONTEXT.md` doesn't just
dangle when that repo isn't the current one — it misdirects the session into the wrong repo's
domain model. This is why the citation convention (a repo's tooling internals stay in that repo's
`CONTEXT.md`, referenced only as a qualified pointer like "jarvis `CONTEXT.md` → *X*") reads as
guidance to repo authors, not as user-level linking *into* a specific repo.

## Related

- **Phase 1**: #278 — PreCompact hook + snapshot capture (shipped 2026-04-21)
- **Phase 2**: #279 — session-context recovery injection (shipped 2026-04-21)
- **Phase 3**: #280 — /end Supabase-authoritative (shipped 2026-04-21)
- **Superseded**: #1204/#1536 — prohibiting-rules extraction into snapshot (removed 2026-08-25 in favor of #1417/#1418's bare `@import`)
