---
name: weekly-release
description: "Draft a weekly GitHub release per config/repos.conf `releases=weekly` repo — readiness/semver/trust-ramp decided by scripts/weekly_release_engine.py, window+repos.conf/gh I/O by scripts/weekly_release_gather.py, release-note prose authored and fact-anchoring-linted inline. S1: manual invocation, draft-only output — never auto-publishes. Routine scheduling and delivery are S2 (#1572 body)."
disable-model-invocation: true
---

# Weekly Release

Produces one draft GitHub release per [`config/repos.conf`](../../../config/repos.conf) repo carrying a `releases=weekly` token. S1 slice (#1572): the vertical to a first **draft**. No scheduling, no auto-publish delivery — those are S2. Invoke by name (`/weekly-release`); it has no anchored chat trigger.

**Boundary — draft only, always.** Per `docs/context/invariants.md` → *"Sending as the owner isn't autonomous until 'digital twin' ships"*: this skill NEVER runs `gh release edit --draft=false` / publishes. Even when [`trust_ramp_state()`](../../../scripts/weekly_release_engine.py) returns `"auto"`, S1 still stops at a draft — trust-ramp-driven auto-publish is S2 delivery wiring, not this slice. The owner publishes manually.

**Split.** Decision core (pure functions, no I/O) is [`scripts/weekly_release_engine.py`](../../../scripts/weekly_release_engine.py). I/O adapter (repos.conf + `gh` reads, no writes) is [`scripts/weekly_release_gather.py`](../../../scripts/weekly_release_gather.py). This skill is the only place that writes (`gh release create`/`edit --draft`) — neither module touches `gh` write paths, mirroring the read/write split the rest of the gather/engine family uses.

## Step 1 — Gather

No MCP tool is registered for this yet (same registration-ceiling situation as `mcp-morning`) — call `gather()` in-process:

```bash
python -c "
import json
from scripts.weekly_release_gather import gather
print(json.dumps(gather().to_dict(), indent=2, default=str))
"
```

Returns a `WeeklyReleaseGatherResult`: one `RepoWindowResult` per `releases=weekly` repos.conf entry, each with `prior_releases` (most-recent-first, `published`/`edited_after_publish` flags), `window_entries` (merged PRs + standalone closed issues, deduped, Dependabot-flagged), `window_refs` (valid PR/issue numbers for the linter), `remaining_issues` (open milestone issues with movement), `window_start`/`window_end`/`window_truncated`.

If `result.errors` is non-empty, surface it and stop for that repo — a failed gather must never fall through to an authored-from-nothing release.

## Step 2 — Per repo, decide

For each `RepoWindowResult`:

1. **Readiness** — `is_release_worthy(window_entries)`. `False` (dep-bumps/CI-fixes-only week, or empty window) → skip this repo, no release, no draft touched. State this explicitly in your final report ("o/r: no release — window was dep-bump/CI only").
2. **Semver bump** — `classify_bump(window_entries)` → `"patch"` or `"minor"`, never `"major"` (no breaking-change signal exists in any form; trust ramp is the only human gate — do not escalate on a `!` marker or `BREAKING CHANGE:` body yourself).
3. **Version string** — apply the bump to the latest tag from `prior_releases` (semver arithmetic is a skill-runtime step; no helper computes it, `weekly_release_engine.py` only classifies the bump). Zero prior releases → first version is a per-repo decision recorded when the repo was onboarded (e.g. redrobot: `v0.1.0`, target branch `master`, per issue #1572's own text — not a default this skill invents for a new repo).
4. **Trust ramp** — `trust_ramp_state(repo_result.prior_releases)`. Informational only in S1 (see Boundary above) — record it in the report; it does not change what this skill does.
5. **Draft-aware anchor** — `repo_result.window_truncated` is already computed by `compute_window()` inside `gather()`. If `True`, the notes MUST disclose the covered period ("покрывает период с {window_start} по {window_end}") — this is a fact the linter can't check for you; don't drop it.
6. **Existing pending draft** — scan `prior_releases` for an entry with `published: False` (an unpublished draft). If one exists for this repo, you are **updating it in place** (`gh release edit`), not creating a second one — this is what "draft-aware anchor" means operationally, not just windowing.

## Step 3 — Author the notes (agent-written prose, then linted)

Write `notes_body`: one line per substantive `window_entries` item, each citing its PR/issue number (`#NNN`) so `lint_release_notes` can validate it against `window_refs`. `lang=ru,en` on the repos.conf entry (`repo_result.lang`) → append an English `<details>` block translating the same cited facts, no new claims.

Write the goals section: `format_goal_section(goal_list(project=<repo-slug>, status="active"))` — **`project` must be the explicit repo slug, never empty/None**: `goal_list`'s unscoped default returns cross-project (including personal) goals for other callers' benefit (`/goals`, `/end`, `/verify`), so an empty project here would leak personal goals into a public release body. Scoping is this skill's own responsibility, not the handler's.

Write `remaining_section` as prose over `repo_result.remaining_issues` (LLM rewrites the open-milestone-issue list into prose; the issues themselves are the source of truth, this step only rewrites into readable text under a `## Осталось` heading — omit the heading entirely if there's nothing to say).

**Lint gate — mandatory, not advisory:**

```python
from scripts.weekly_release_engine import lint_release_notes
violations = lint_release_notes(notes_body.splitlines() + remaining_section.splitlines(), repo_result.window_refs)
```

Non-empty `violations` → rewrite the offending lines (add a real `#NNN` citation from `window_refs`, or drop the uncited claim). Never bypass this by loosening a claim's wording to dodge the digit check — fix the citation or cut the claim.

## Step 4 — Assemble and create the draft

```python
from scripts.weekly_release_engine import assemble_release_body
body = assemble_release_body(notes_body, remaining_section, full_changelog_url, footer="Опубликовано ботом")
```

`full_changelog_url` = `https://github.com/<repo>/compare/<last_tag>...<new_version>` (or omit the compare range for a repo's first-ever release — there is no prior tag to diff against).

Then, via `gh` (write step — the one thing this skill does that the gather module deliberately doesn't):

- **No existing pending draft** → `gh release create <version> --repo <owner/repo> --target <branch> --title <version> --draft --notes-file <path-to-body>`
- **Existing pending draft found in Step 2.6** → `gh release edit <existing-tag> --repo <owner/repo> --notes-file <path-to-body>` (update in place, do not create a second draft for the same window)

Report the draft URL(s) back to the owner. Do not publish. Do not send anything as the owner beyond creating the draft itself (the draft is a proposal artifact, not outbound communication).

## Failure modes

- `gather()` returns `errors` for a repo → skip that repo, surface the error, do not author a release from an incomplete gather.
- `lint_release_notes` keeps failing after a rewrite attempt → stop for that repo and report the unresolved violation; never ship a release with an uncited quantitative claim.
- `gh release create`/`edit` fails (auth, branch not found, tag collision) → surface the `gh` error verbatim; do not retry with `--force` or improvise a different tag.
- Repo has `releases=weekly` but zero prior releases and no explicit first-version decision on record → do not guess a version number; ask the owner (this is exactly the redrobot `v0.1.0` case — settled once per repo, not invented per run).
