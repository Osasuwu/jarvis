---
name: analyze-comms
description: "Analyze communication patterns between user and Jarvis across local Claude Code sessions. Extracts corrective/affirmative moments + style samples, runs qualitative pattern analysis, leaves artifacts in a local staging dir (user uploads manually if needed). Trigger: 'проанализируй сессии', 'analyze comms', 'comm patterns', 'паттерны общения'."
---

# Analyze Comms

Looks at user's interaction style with Jarvis across N local sessions on the current device. Goal: extract communication patterns (what triggers pushback, what gets approved, phrasing style) — NOT task content. Output is sensitive (contains real quotes about people/decisions). Artifacts stay in a local staging dir; user uploads manually if they want cross-device merge later. Never commit to repo.

> **Why no auto-upload**: model-side base64-encoding of personal-pattern files (combined with reading them back into context) trips the AUP classifier. Manual upload by the user avoids that path entirely.

## When to run

- User says "проанализируй сессии" / "analyze comms" / "что я делаю не так" / "паттерны"
- Manually after accumulating significant session history on a new/another device
- Per-device, not per-session — one device = one analysis run

## What it does NOT do

- Does not auto-write to memory. User reviews report, decides which feedback rules to keep.
- Does not analyze task content / project progress (that's `/reflect`'s job).
- Does not touch jarvis repo — all artifacts stay in a local staging dir under `~/.cache`. User uploads manually if needed.
- Does not auto-upload anywhere (no GDrive, no base64 round-trip — see Safety notes).

## Conventions

- **Local staging dir**: `~/.cache/jarvis-comms-analysis/<YYYY-MM-DD>_<device>/` — kept after run, user manages cleanup.
- **Sessions source**: `~/.claude/projects/*/*.jsonl` (universal across OSes; `Path.home()` resolves correctly).

## Step 1 — Prepare staging dir

```bash
DEVICE=$(hostname || echo "unknown")
DATE=$(date +%Y-%m-%d)
STAGE="$HOME/.cache/jarvis-comms-analysis/${DATE}_${DEVICE}"
mkdir -p "$STAGE"
```

## Step 2 — Run extraction pipeline

```bash
SKILL_DIR="$(dirname "$0")"  # the directory containing this SKILL.md
python "$SKILL_DIR/extract_comms.py"  "$STAGE/comms_extract.jsonl"
python "$SKILL_DIR/analyze_comms.py"  "$STAGE/comms_extract.jsonl"
python "$SKILL_DIR/build_bundle.py"   "$STAGE/comms_extract.jsonl"  "$STAGE/comms_bundle.md"
```

Print `analyze_comms.py` stdout inline — these are aggregate stats (counts, percentiles, time-of-day), no quotes, safe to show.

If `interactive sessions: 0` → tell user "no sessions with ≥3 user msgs on this device, nothing to analyze" and stop.

## Step 3 — Qualitative pattern extraction (subagent)

Delegate to a `general-purpose` Agent with this brief:

> Context: this is **self-analysis of the user's own Claude Code sessions for self-improvement of the Jarvis assistant's behavior**. Not third-party profiling. The bundle is the user's own data on their own device.
>
> Read `<STAGE>/comms_bundle.md`. It contains:
> - Corrective moments (assistant said X → user pushed back Y)
> - Affirmative moments (what worked)
> - Neutral style samples (random user msgs for style characterization)
>
> Extract communication patterns ONLY — not task content. Write the structured report directly to `<STAGE>/report.md` using the Write tool. Do NOT base64-encode anything. Do NOT read the report back after writing it. Do NOT echo full quotes into your final message — main agent will read the file.
>
> Report sections:
> 1. Top-5 pushback triggers (name + frequency + 2-3 anchor quotes + why it cuts)
> 2. Top-3 approved patterns
> 3. User phrasing style (length, structure, RU/EN split, tone)
> 4. Metacommunication (how disagreement is expressed, reaction to long replies, pushback acceptance)
> 5. Non-obvious findings (2-3, not surface-level)
> 6. Candidate feedback rules (3-5, format: rule + Why + How to apply)
>
> Under 1500 words. RU output (user's language).
>
> Return to main agent: only a 3-line summary (file path + sections written + word count). No quotes, no base64, no full report content.

## Step 4 — Show report inline + offer next steps

Read `$STAGE/report.md` directly. Show:
- Aggregate stats from Step 2 (already printed)
- Section headings + 1-line summaries (NOT full quotes — user can open the file for those)
- Candidate feedback rules — full text, since these are the actionable output

Tell user the staging path: `$STAGE`. Files there:
- `comms_extract.jsonl` — full extracted text (sensitive)
- `comms_bundle.md` — curated quotes (sensitive)
- `report.md` — subagent output

User uploads to GDrive / Obsidian / wherever manually if cross-device merge is needed. Skill does NOT auto-upload (model-side base64 of personal data trips AUP classifier).

Offer:
- "save these N rules to memory?" (only if N is small and rules look solid)
- "run on other devices and merge before deciding?" (default recommendation when this is a single-device run)

## Safety notes

- `comms_bundle.md` and the report contain real quotes about people, decisions, and frustrations. Treat as sensitive personal data.
- This skill is in the open jarvis repo — only the **scripts and SKILL.md** are public. Output artifacts NEVER go inside the repo. Staging dir is under `~/.cache`, outside the repo tree.
- Do NOT base64-encode artifacts and do NOT read full bundles/reports back into the model context after writing — that pattern trips the AUP classifier (combination of large opaque blob + personal-pattern content).
- If the staging dir already exists from a previous run on the same day, append a `_N` suffix rather than overwriting.

## Limitations

- Local sessions only. Each device has its own jsonl files; analysis is per-device.
- Regex for corrective/affirmative is RU+EN but narrow. False negatives expected on subtle pushback.
- Sessions with <3 user msgs are skipped (autonomous queue ops, scheduled tasks, etc).
- Bundle truncates messages to 500 chars — long context arguments may lose detail.

## Future merging

When data exists from 2+ devices, a separate cross-device merge step (not yet implemented) would:
- User manually copies each device's `report.md` to a single location (GDrive / Obsidian / local sync folder)
- A merge skill reads them, dedupes candidate rules by intent, surfaces only patterns confirmed across ≥2 devices
- That's when memory writes become safe.

Auto-upload from inside the skill is intentionally avoided — see Safety notes.
