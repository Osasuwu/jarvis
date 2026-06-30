# User-level CLAUDE.md

Process and protocol rules that apply across every project. Loaded into every Claude Code session as user-level memory.

**Source of truth:** `<jarvis-repo>/.claude-userlevel/CLAUDE.md`. The live file at `~/.claude/CLAUDE.md` is a mirror — `install.ps1 -Apply` propagates from source. Never edit the mirror; edits drift on next install.

Project-specific rules live in `<repo>/CLAUDE.md`. SOUL.md (`~/.claude/SOUL.md`) holds identity/personality; this file holds process.

## Memory & decision protocol

Skills consume this section instead of restating it. Three load-bearing rules: **recall before deciding**, **brief-mode UUIDs**, and the **`record_decision` contract**.

This is the **Tier 1** layer (soft prompt rule). Backstops:

- **Tier 2 — hooks.** Mechanical enforcement that can't be skipped (e.g. `PreToolUse` on `record_decision` blocks calls with empty `memories_used`).
- **Tier 3 — skill-specific gates.** Things that genuinely belong to one skill (e.g. `/grill`'s completeness gate, `/implement`'s already-done audit). Stay in the skill file.

If the empty-`memories_used` rate rises after centralising here, the relevant rule escalates Tier 1 → Tier 2 (issue #532 tracks this).

### 1. Recall before deciding

Before any non-trivial decision, save, or skill invocation, consult memory. Three passes — run in parallel where possible:

- **Always-load gates** — memories **tagged `always_load`**, surfaced by the SessionStart hook (`session-context.py` → `_query_always_load`, a `tags @> ['always_load']` query). There is **no `always_load` parameter** on `memory_list`/`memory_recall` — the gate is tag-based, not a query flag. Flipping the tag on a memory requires `record_decision` (trigger #4 below). Surface unconditionally; these are session-wide rules that bind every skill. (Mechanism detail: memory `always_load_tag_mechanism`.)
- **Topic recall with skill name** — `memory_recall(query="<skill-name> <topic + entities>", type=decision/feedback, brief=true, limit=10–15)`. **The literal skill name MUST appear in the query** so skill-specific contract memories (e.g. `grill_me_record_decision_gate`) surface every invocation. Skill contracts are not always_load — they ride on this recall.
- **Outcomes for the area** — `outcome_list(scope=<area>, severity≥medium, since=90d)` when the work touches a known-failure region. 2+ failures cluster → surface in the first turn before acting.

For mid-task branch shifts (entering a new sub-area of a design tree), re-run topic recall with sub-area-specific entities. Goal: keep `memories_used` populated with sub-area UUIDs at decision time, not generic top-level recall.

If args are short or meta (≤5 words, or entity names dominate), a second pass with entities expanded — don't lean on a narrow query.

### 2. Brief-mode → UUID map

`memory_recall(brief=true, ...)` returns `name=<slug>` AND `id=<uuid>` per hit. Parse both into a local `name → uuid` map at recall time.

**Every later `record_decision` call passes UUIDs in `memories_used`, not names.** The schema demands UUIDs; slugs drift. Per #325 audit: of 33 historical `decision_made` episodes, 12 stored names not UUIDs — every one was a broken FK in the outcome→memory join.

### 3. record_decision contract

When a resolution is architectural / cadence-defining / between named alternatives / has consequences past this session — emit `mcp__memory__record_decision` **immediately on resolution** (not batched at end).

Pass:

- `decision` — one line, the resolved answer (not the question).
- `rationale` — one paragraph, the *why* the user gave (not just what was chosen).
- `alternatives_considered` — every option discussed, each with one-clause rejection reason. Empty list is rare; "none discussed" is itself a flag.
- `reversibility` — `reversible | hard | irreversible`. Be honest; this gates downstream caution.
- `confidence` — `0.0–1.0`. If <0.6, flag the uncertainty in-line, don't bury it.
- `memories_used` — UUIDs (not names) from the recall map. Empty list valid only when nothing in memory informed the choice (rare; the rationale should note it).
- `actor` — `session:<short-slug>` so the trail is recoverable.
- `project` — scope to the project being designed for.

Capture the returned episode UUID. Maintain a running `decision_uuids[]` per session for handoff to downstream skills.

#### Trigger list — emit when ANY of these hold

1. **Issue implementation** — always, even if reversible. Outcome attribution needs the basis.
2. **`reversibility ∈ {hard, irreversible}`** — destructive DB ops, force-pushed history, published API changes.
3. **`confidence < 0.7`** — uncertain calls deserve recorded rationale so `/reflect` can classify failures as reasoning vs execution.
4. **Policy / schema / tag / config change** — `always_load` tags, protected-file edits, skill add/remove, hook config, schema migrations, installer manifest. Reversible but affects future sessions.
5. **Architectural direction picked** — resolved "chose X over Y" after discussion, even if reversible. The rationale matters more than the bit set.

Rule of thumb: "I just made a call that will outlive this session" → emit. "I just clarified my own thinking" → skip. When unsure, emit — one tool call vs. a `/reflect` blind spot.

#### Post-hoc marker

If a decision is recorded after-the-fact (catching up on a missed call, e.g. during `/end` reconciliation), encode `:post-hoc` into the `actor` field — `actor="session:<id>:post-hoc"`. `/self-improve` greps actor for regression patterns; real-time capture is the goal, post-hoc saves are a regression. (#517 tracks adding a structured `post_hoc` field.)

### Memory staleness

Memory records can be wrong:

- **Dead references** — file/skill/issue that no longer exists: ignore + note in skill output for `/reflect`. Don't ask the user about every dead reference.
- **Show-and-continue** — when a turn leans on memory, list inline as `(leaning on: <one-line> — <uuid>, <age>d)`. Catches staleness in real time without a question per memory. Keep terse: 1–3 records per turn max.
- **Old reversibles** — `reversibility=reversible` decisions older than ~60 days: surface but don't treat as a constraint.

### Decisions belong in memory, not in issue/PR bodies

Architectural resolutions go to `record_decision`. Issue bodies, PR bodies, PRD prose all decay; the queryable decision log doesn't. Skills that produce issues (`/to-prd`, `/to-issues`) reference `decision_uuids[]` rather than restating the *why* — see each skill for the section template.

## Repo policy — auto-merge & merge gates

Applies to every owned repo (`Osasuwu/jarvis`, `SergazyNarynov/redrobot`, and any future personal project). Foreign-owner repos are exempt — they have their own protection rules.

> **Caveat — auto-merge needs a paid GitHub plan on private repos.** `allow_auto_merge` / `gh pr merge --auto` is rejected (`Auto merge is not allowed for this repository`) on **private repos on the Free plan**. `SergazyNarynov/redrobot` is private+Free, so it has **no auto-merge**: the four gates below still apply, but the final merge is **manual when CI is green** (`gh pr merge <N> --squash --delete-branch`, or poll-then-merge). Don't retry `--auto` there. The AFK Path A loop is fully automatic only on repos with a paid plan (or public repos).

**Goal:** AFK Path A loop closes by itself — `open → CI → review → automerge → rework → escalate`. Subagent opens a PR, Jarvis flips it to ready, GitHub merges when every gate is green. No human in the merge step *unless* a gate fires.

### The four gates

Every owned repo enforces the same set via **branch protection on the default branch** + repo-level `allow_auto_merge=true`:

1. **`review` (Claude code-review plugin)** — the workflow runs `/code-review`, posts findings as a structured comment, **and a post-step (`Verify review verdict`) fails the job ONLY on a merge-blocking finding — an all-caps `CRITICAL`/`MAJOR`/`BLOCKING` severity heading — and fails closed on an unparseable review comment** (jarvis#957 false-passed when the bot used a deviant comment format the old parser didn't select). This is **Gate 1 of the two-gate model** (jarvis#988/#989): MINOR/NITPICK/LOW/INFO/MEDIUM headings and a bare `Found N issues:` line do NOT block — they pass. The merge gate is deliberately aligned with the `/rework` convergence target (`scripts/rework_policy.py`: `n_critical==0 AND n_major==0`) so a PR clean of real bugs but carrying minor nits no longer ping-pongs between "rework thinks it's done" and "merge gate rejects it" (jarvis#976 — PRs were taking 3-5 rework rounds). Without the post-step the check signals "bot ran" not "PR is clean" — auto-merge would happily ship PRs with CRITICAL findings. Plugin already drops findings below 80-confidence per its rubric, so any surfaced finding is real. Case-SENSITIVE all-caps is the discriminator (jarvis#976): title-case prose like `### Blocking issues — None` (#962) must not false-block.
2. **`owner-queue-guard`** — fails the job when the PR carries the `status:owner-queue` label. That label is the manual "park this for me" signal; the guard turns it into a hard merge block instead of a hope-Jarvis-honors-it convention. Triggered on `opened / synchronize / labeled / unlabeled` so the gate is re-evaluated whenever label state changes.
3. **`require-linked-issue`** — PR body must reference `Closes #NNN`, OR carry the `priority:critical` label (hotfix bypass), OR contain the `[no-issue]` marker (drive-by fix-inline per jarvis#428), OR use a `refactor:` / `refactor(scope):` title prefix.
4. **Project-specific test gates** — `pytest`, `meta-tests`, `Detect secrets with gitleaks` in jarvis; the equivalents in any other repo. These come from the repo's own CI surface.

### Drafts are the manual hold

A PR stays in **draft** while your attention is owed (waiting on design feedback, intentional batching, etc.). Drafts never auto-merge — that's GitHub's default and it's the right one. Once flipped to ready, the four gates above are the merge gate.

Use `status:owner-queue` for the rarer case: PR is content-complete (so it can pass review) but you still want to eyeball it before it ships. The label keeps it ready-but-blocked. Don't reach for the label when draft already covers the case.

### Required files per repo

- `.github/workflows/code-review.yml` — final step `Verify review verdict` selects the latest comment with a code-review title heading (any level, optional "Claude" prefix, case-insensitive — not just literal `### Code review`; jarvis#957), then under the **two-gate model** (jarvis#988/#989) exits **1 only on an all-caps merge-blocking severity heading** (`CRITICAL/MAJOR/BLOCKING` after 1-6 `#`'s — decoration like emoji tolerated, `findings`/`issues` suffix optional; observed deviants: `### MAJOR findings` #957, bare `### MAJOR` #956, `### 🔴 BLOCKING` #954). The block grep is **case-SENSITIVE** (`grep -qE`, not `-qiE`) so title-case prose like `### Blocking issues — None` (#962, #976) is not a false-block. Passes (exit 0): a line starting `No issues found.`; a `blocking issues … none` line (case-insensitive, #976); a bare `Found N issues:` line (now a NON-blocking pass — minor/advisory findings must not gate, was a block before #989); an all-caps non-blocking severity heading (`MINOR/NITPICK/LOW/INFO/MEDIUM`). **Exit 1 on an unrecognized verdict format (fail-closed)**; exit 0 only when no review-titled comment exists (plugin skipped). The block check runs first, before any pass check. Contract pinned by `tests/ci/test_code_review_verdict_guard.py` in jarvis. The merge gate is intentionally aligned with `scripts/rework_policy.py`'s convergence target (`n_critical==0 AND n_major==0`) — same blocking set on both sides closes the #976 rework ping-pong.
- `.github/workflows/owner-queue-guard.yml` — single job named `owner-queue-guard`, triggers on `opened, synchronize, labeled, unlabeled`, fails on the label.

The check name `owner-queue-guard` is what branch protection references — rename in lockstep with the protection rule or the gate silently disappears (cf. jarvis#326 meta-test rule: path-filtered guards need a fixture test pinning the canonical name).

### Repo-settings checklist (one-time per repo)

```
gh api -X PATCH /repos/<owner>/<repo> -F allow_auto_merge=true -F delete_branch_on_merge=true
gh api -X PUT /repos/<owner>/<repo>/branches/<default>/protection -F required_status_checks='{"strict":true,"contexts":["review","owner-queue-guard","require-linked-issue", ...repo-specific...]}' -F enforce_admins=false -F required_pull_request_reviews=null -F restrictions=null
```

`enforce_admins=false` keeps escape-hatch open for you (admin-merge for the two structural cases below — not for routinely working around a misfiring gate). `required_pull_request_reviews=null` because the `review` check already encodes the AI review verdict — adding a required human review would defeat AFK Path A.

### When to break the rules

Two structural cases where a gate *cannot* run, and admin-merge is the only path — not a convenience:

- **A PR modifies `code-review.yml` itself**: `anthropics/claude-code-action@v1` refuses to run on self-modifying PRs ("Workflow validation failed" — documented behavior). The `review` check fails as expected; admin-merge.
- **Self-hosted runner is down (redrobot)**: review/CI can't run. Verify locally, admin-merge per `redrobot_billing_blocked_manual_merge_protocol` precedent.

**A flaky or false-failing gate is NOT on this list.** A gate that fails when it shouldn't (e.g. the `review` check going red because the bot posted no parseable verdict comment) is a **bug to fix, not a bypass to normalize**. Knowing a gate is broken and routinely admin-merging around it silently disables the protection for every future PR. If a gate misfires: file an issue, fix the root cause, and only admin-merge the *one* blocked PR as a stop-gap **with that tracking issue linked in the merge comment**. If you find yourself admin-merging the same gate twice, stop and fix the gate first.

## Tooling — MCP servers

User-scope MCP servers (registered by the installer from `.claude-userlevel/.mcp.json`): `memory`, `github`, `context7`, `sequential-thinking`, `obsidian`, plus device-gated `uml` (only where `UML_MCP_HOME` is set — the workshop PC with the local Kroki backend). A server may declare `"x-jarvis-requires-env": "<VAR>"`; the installer skips it on devices where that var is unset, so the same source installs correctly everywhere.

### context7 — use it, don't forget it

`context7` provides **live, version-current library docs** (via `resolve-library-id` → `query-docs`). Reach for it BEFORE answering from memory whenever a task touches a library, framework, SDK, API, CLI, or cloud service — even ones you "know" (React/Three.js/FastAPI/mujoco/etc.). Training data lags; context7 doesn't. Prefer it over web search for library docs. Triggers: API syntax, config, version-migration, library-specific debugging, setup/CLI usage.

Do **not** use it for: refactoring, writing scripts from scratch, debugging business logic, code review, or general programming concepts — that's reasoning, not docs lookup.

Rule of thumb: about to state a library's API surface or config from memory → pull context7 first and cite what it returns.
