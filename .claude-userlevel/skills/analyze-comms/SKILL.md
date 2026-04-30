---
name: analyze-comms
description: "Analyze communication patterns between user and Jarvis across local Claude Code sessions. Extracts corrective/affirmative moments + style samples, runs qualitative pattern analysis, uploads artifacts to private GDrive (NOT to repo). Trigger: 'проанализируй сессии', 'analyze comms', 'comm patterns', 'паттерны общения'."
---

# Analyze Comms

Looks at user's interaction style with Jarvis across N local sessions on the current device. Goal: extract communication patterns (what triggers pushback, what gets approved, phrasing style) — NOT task content. Output is sensitive (contains real quotes about people/decisions) and MUST go to private GDrive, never to the open repo.

## When to run

- User says "проанализируй сессии" / "analyze comms" / "что я делаю не так" / "паттерны"
- Manually after accumulating significant session history on a new/another device
- Per-device, not per-session — one device = one analysis run

## What it does NOT do

- Does not auto-write to memory. User reviews report, decides which feedback rules to keep.
- Does not analyze task content / project progress (that's `/reflect`'s job).
- Does not touch jarvis repo — all artifacts go to staging dir → GDrive → cleaned up.

## Conventions

- **GDrive root folder name**: `jarvis-comms-analysis` (in user's own Drive — each user gets their own). Resolved by name on each run; created if missing. ID is never hardcoded in this skill.
- **Local staging dir**: `~/.cache/jarvis-comms-analysis/<YYYY-MM-DD>_<device>/` — temp, deleted after upload confirmed.
- **Sessions source**: `~/.claude/projects/*/*.jsonl` (universal across OSes; `Path.home()` resolves correctly).

## Step 1 — Resolve GDrive folder

Search Drive for the root folder by name:

```
mcp__*__search_files(query="title = 'jarvis-comms-analysis' and mimeType = 'application/vnd.google-apps.folder' and 'me' in owners and trashed = false")
```

If exactly one match → use its `id`. If zero matches → create it via `mcp__*__create_file` with `mimeType: 'application/vnd.google-apps.folder'`, no `parentId` (lands in My Drive root). If multiple matches → ask user which one.

Save the resolved id as `$ROOT_FOLDER_ID` for Step 5.

If GDrive MCP is not connected at all → tell user "GDrive connector required for output upload — connect it or skip this skill" and stop. Do NOT fall back to writing artifacts inside the repo.

## Step 2 — Prepare staging dir

```bash
DEVICE=$(hostname || echo "unknown")
DATE=$(date +%Y-%m-%d)
STAGE="$HOME/.cache/jarvis-comms-analysis/${DATE}_${DEVICE}"
mkdir -p "$STAGE"
```

## Step 3 — Run extraction pipeline

```bash
SKILL_DIR="$(dirname "$0")"  # the directory containing this SKILL.md
python "$SKILL_DIR/extract_comms.py"  "$STAGE/comms_extract.jsonl"
python "$SKILL_DIR/analyze_comms.py"  "$STAGE/comms_extract.jsonl"
python "$SKILL_DIR/build_bundle.py"   "$STAGE/comms_extract.jsonl"  "$STAGE/comms_bundle.md"
```

Print `analyze_comms.py` stdout inline — these are aggregate stats (counts, percentiles, time-of-day), no quotes, safe to show.

If `interactive sessions: 0` → tell user "no sessions with ≥3 user msgs on this device, nothing to analyze" and stop.

## Step 4 — Qualitative pattern extraction (subagent)

Delegate to a `general-purpose` Agent with this brief:

> Read `<STAGE>/comms_bundle.md`. It contains:
> - Corrective moments (assistant said X → user pushed back Y)
> - Affirmative moments (what worked)
> - Neutral style samples (random user msgs for style characterization)
>
> Extract communication patterns ONLY — not task content. Output structured report:
> 1. Top-5 pushback triggers (name + frequency + 2-3 anchor quotes + why it cuts)
> 2. Top-3 approved patterns
> 3. User phrasing style (length, structure, RU/EN split, tone)
> 4. Metacommunication (how disagreement is expressed, reaction to long replies, pushback acceptance)
> 5. Non-obvious findings (2-3, not surface-level)
> 6. Candidate feedback rules (3-5, format: rule + Why + How to apply)
>
> Under 1500 words. RU output (user's language).

## Step 5 — Upload artifacts to GDrive

Create a dated subfolder under `$ROOT_FOLDER_ID` (mimeType `application/vnd.google-apps.folder`, title `${DATE}_${device}`). Then for each file in staging dir, base64-encode and upload via `mcp__*__create_file` with `parentId` set to the dated subfolder's id.

Files to upload:
- `comms_extract.jsonl` (full extracted text — sensitive)
- `comms_bundle.md` (curated quotes — sensitive)
- `report.md` (subagent output — also sensitive but smallest)

Set `disableConversionToGoogleType: true` on all uploads to keep raw formats.

After successful upload, save the dated subfolder's `viewUrl` for the user.

## Step 6 — Cleanup local staging

```bash
rm -rf "$STAGE"
```

Confirm to user: "uploaded to <viewUrl>, local staging cleaned".

## Step 7 — Show report inline + offer next steps

Show only:
- Aggregate stats from Step 3 (already printed)
- Section headings + 1-line summaries from Step 4 report (NOT full quotes — user can open GDrive for those)
- Candidate feedback rules — full text, since these are the actionable output

Offer:
- "save these N rules to memory?" (only if N is small and rules look solid)
- "run on other devices and merge before deciding?" (default recommendation when this is a single-device run)

## Safety notes

- `comms_bundle.md` and the report contain real quotes about people, decisions, and frustrations. Treat as sensitive personal data.
- This skill is in the open jarvis repo — only the **scripts and SKILL.md** are public. Output artifacts NEVER stay in the repo or get committed.
- If GDrive upload fails, leave files in `$STAGE` and tell user the path — don't delete unsaved data.
- If the staging dir already exists from a previous run on the same day, append a `_N` suffix rather than overwriting.

## Limitations

- Local sessions only. Each device has its own jsonl files; analysis is per-device.
- Regex for corrective/affirmative is RU+EN but narrow. False negatives expected on subtle pushback.
- Sessions with <3 user msgs are skipped (autonomous queue ops, scheduled tasks, etc).
- Bundle truncates messages to 500 chars — long context arguments may lose detail.

## Future merging

When data exists from 2+ devices, a separate cross-device merge step (not yet implemented) would:
- Download all `report.md` from GDrive
- Merge candidate rules, dedup by intent
- Surface only patterns confirmed across ≥2 devices
- That's when memory writes become safe.
