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

## Preserving Rules Through Compaction (#1204)

**Problem**: Prohibiting rules and standing orders ("don't touch X", "never do Y") die during compaction because they're part of the session history, not the persistent system state.

**Solution**: Three-phase approach

### Phase 1: Capture Rules in PreCompact Hook

`scripts/pre-compact-backup.py` now extracts prohibiting rules from CLAUDE.md:

```python
def _extract_prohibiting_rules(cwd: str | None) -> list[str]:
    """Extract prohibiting rules from CLAUDE.md files for snapshot preservation."""
```

Looks for lines containing keywords:
- "do not", "don't", "never", "prohibit", "forbidden", "must not"
- "standing order", "aligned plan"
- "autonomy: no", "autonomous: no"

Rules are included in the session snapshot stored to Supabase/local:

```markdown
## Prohibiting Rules & Standing Orders

The following rules must be preserved and re-injected after compaction.
These are not summarizable; preserve them verbatim.

- Do not merge PRs without approval.
- Never bypass pre-commit hooks.
```

### Phase 2: Re-Inject Rules on Resume

`scripts/session-context.py` (SessionStart `compact` matcher) reads the snapshot and prepends a recovery section. The prohibiting rules are preserved verbatim.

### Phase 3: Re-Emphasize in Context

When session-context.py emits the recovery section, the rules appear in Claude's context **before** the LLM-generated summary. This ensures they're re-established as standing orders before processing resumes.

## Testing Compaction Resilience

To verify rules survive compaction:

1. **Write rules to CLAUDE.md**:
   ```markdown
   ## Prohibiting Rules
   - Do not delete production data without confirmation.
   - Never bypass the review gate.
   ```

2. **Trigger compaction**:
   ```bash
   /compact focus on the task at hand
   ```

3. **Verify snapshot contains rules**:
   ```bash
   # Check local fallback
   cat ~/.claude/session-snapshots/<session_id>.md | grep "Prohibiting Rules"
   
   # Or query Supabase (if logged in)
   SELECT content FROM memories WHERE name = 'session_snapshot_<session_id>'
   ```

4. **Resume session** and check that rules appear in context

## Related

- **Phase 1**: #278 — PreCompact hook + snapshot capture (shipped 2026-04-21)
- **Phase 2**: #279 — session-context recovery injection (shipped 2026-04-21)
- **Phase 3**: #280 — /end Supabase-authoritative (shipped 2026-04-21)
- **Extension**: #1204 — preserving prohibiting rules through compaction
