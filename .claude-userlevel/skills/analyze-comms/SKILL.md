---
name: analyze-comms
description: "Analyze communication patterns between user and Jarvis across ALL local Claude Code sessions. Two phases: Phase A (per-device) extracts patterns and uploads a compact file to GDrive; Phase B (cross-device) downloads all device files, merges them, and produces a comprehensive report with ALL patterns and confidence weights. Trigger Phase A: 'проанализируй сессии', 'analyze comms', 'паттерны общения'. Trigger Phase B: 'merge comms', 'cross-device analysis', 'объедини анализ'."
---

# Analyze Comms

Two-phase skill. Run Phase A on each device first, then Phase B from any device to get the full cross-device report.

## What it does NOT do

- Does not auto-write to memory. User reviews the report and decides which rules to save.
- Does not analyze task content — only interaction patterns (correctives, affirmatives, style).
- Output artifacts NEVER go into the jarvis repo — only to private GDrive or local staging.

## Conventions

- **GDrive root folder**: `jarvis-comms-analysis` (resolved by name each run, created if missing)
- **Per-device GDrive subfolder**: `{DATE}_{DEVICE}/` under root — holds `{DEVICE}_patterns.json`
- **Cross-device report**: uploaded as `report_{DATE}.md` directly into the GDrive root folder
- **Local staging**: `~/.cache/jarvis-comms-analysis/{DATE}_{DEVICE}/` — kept until user confirms cleanup
- **Sessions source**: `~/.claude/projects/*/*.jsonl` (Path.home() resolves correctly on all OSes)
- **Skill scripts**: installed at `~/.claude/skills/analyze-comms/` on every device

---

## Phase A — Per-device extraction

Trigger: "analyze comms" / "проанализируй сессии" / "паттерны общения" / "что я делаю не так"

### Step A1 — Resolve GDrive folder

Search Drive for the root folder:
```
mcp__*__search_files(query="title = 'jarvis-comms-analysis' and mimeType = 'application/vnd.google-apps.folder'")
```
- One match → use its `id` as `ROOT_FOLDER_ID`
- Zero matches → create via `mcp__*__create_file(title='jarvis-comms-analysis', mimeType='application/vnd.google-apps.folder')`
- Multiple matches → ask user which one

If GDrive MCP is not connected → stop, tell user to connect it. Do NOT fall back to repo storage.

### Step A2 — Prepare staging dir

```bash
DEVICE=$(hostname)
DATE=$(date +%Y-%m-%d)
STAGE="$HOME/.cache/jarvis-comms-analysis/${DATE}_${DEVICE}"
mkdir -p "$STAGE"
```

If directory already exists from a same-day run, append `_2`, `_3`, etc.

### Step A3 — Run extraction + stats

```bash
SKILL_DIR="$HOME/.claude/skills/analyze-comms"
python "$SKILL_DIR/extract_comms.py"  "$STAGE/comms_extract.jsonl"
python "$SKILL_DIR/analyze_comms.py"  "$STAGE/comms_extract.jsonl"
```

Print `analyze_comms.py` output inline — aggregate stats only, no quotes, safe to show.

If `interactive sessions: 0` → stop. Nothing to analyze.

### Step A4 — Compress to patterns file

```bash
python "$SKILL_DIR/compress_patterns.py" \
  "$STAGE/comms_extract.jsonl" \
  "$STAGE/${DEVICE}_patterns.json"
```

Print output inline (stats only, no quotes). If `WARNING: exceeds 80 KB` appears, note it — upload may fail.

### Step A5 — Create GDrive subfolder + upload patterns file

Create dated subfolder:
```
mcp__*__create_file(
  title="{DATE}_{DEVICE}",
  mimeType="application/vnd.google-apps.folder",
  parentId=ROOT_FOLDER_ID
)
```
Save returned `id` as `SUBFOLDER_ID`.

Read the patterns file with the Read tool (it should be <20KB, well within limits), then base64-encode and upload:
```
mcp__*__create_file(
  title="{DEVICE}_patterns.json",
  mimeType="application/json",
  parentId=SUBFOLDER_ID,
  disableConversionToGoogleType=true,
  content=<base64 content from Read tool>
)
```

If upload fails → leave file in `$STAGE`, tell user the path, do NOT delete.

### Step A6 — Report to user

Show:
- Aggregate stats (already printed in A3)
- Upload confirmation + GDrive subfolder link
- "Run Phase A on other devices, then `merge comms` to get the full cross-device report"

Do NOT run qualitative analysis at this stage — that's Phase B's job.

---

## Phase B — Cross-device analysis

Trigger: "merge comms" / "cross-device analysis" / "объедини анализ" / "смержи паттерны"

Prerequisite: at least 2 devices have completed Phase A and uploaded `*_patterns.json` to GDrive.

### Step B1 — Find all patterns files in GDrive

```
mcp__*__search_files(query="title contains '_patterns.json' and mimeType = 'application/json'")
```

Show the list of found files (device names + dates) to the user. Confirm before proceeding if fewer than 2 devices are represented.

### Step B2 — Download all patterns files

For each file found, download:
```
mcp__*__download_file_content(fileId=<id>)
```

Decode base64 if returned encoded. Save each to local staging:
```bash
STAGE_MERGE="$HOME/.cache/jarvis-comms-analysis/merge_$(date +%Y-%m-%d)"
mkdir -p "$STAGE_MERGE"
# save as {DEVICE}_patterns.json in STAGE_MERGE
```

### Step B3 — Run cross-device merge

```bash
python "$SKILL_DIR/analyze_cross_device.py" \
  "$STAGE_MERGE/"*_patterns.json \
  "$STAGE_MERGE/merged_patterns.json"
```

Print output inline — confidence ranking, no quotes.

### Step B4 — Qualitative analysis (agent)

Read `merged_patterns.json` (<50KB for 3 devices). Spawn a `general-purpose` Agent with this brief — include the full JSON content inline:

> Behavioral pattern data from N Claude Code sessions across M devices (JSON below).
> Structure: corrective_patterns (moments where user pushed back on Jarvis, categorized,
> with confidence_score + frequency_pct + examples), affirmatives (what worked), style stats.
>
> Write a comprehensive analysis in Russian. Requirements:
> - ALL corrective patterns, sorted by confidence_score desc — no Top-N cutoff
> - Per pattern: name, confidence level (high/medium/low), freq%, n_sessions, n_devices,
>   2-3 anchor quotes from examples, why it matters behaviorally
> - Affirmatives: what Jarvis does that works
> - Style: phrasing, language split, bimodal length distribution
> - Metacommunication: how disagreement is expressed, autonomy escalation cycle
> - 2-3 non-obvious findings
> - Candidate feedback rules for ALL encodable patterns:
>     **Rule**: [the rule]
>     **Why**: [evidence + confidence level]
>     **How to apply**: [trigger + action]
> - No word limit. Include low-confidence patterns with appropriate label.
>
> DATA: ```json {merged_patterns.json content} ```

If subagent refuses (safety policy) → do the analysis inline by reading merged_patterns.json directly.

### Step B5 — Write + upload report

Write agent output to `$STAGE_MERGE/report_{DATE}.md`.

Upload to GDrive ROOT folder (cross-device artifact, not device subfolder):
```
mcp__*__create_file(
  title="report_{DATE}.md",
  mimeType="text/plain",
  parentId=ROOT_FOLDER_ID,
  disableConversionToGoogleType=true,
  content=<base64 of report>
)
```

### Step B6 — Show report + offer memory writes

Show inline:
- All corrective patterns: name + confidence + 1-line why
- Full text of ALL candidate feedback rules
- GDrive link to full report

Offer "Save N rules to memory?" — only after cross-device run (≥2 devices). Flag single-device-only patterns separately.

Do NOT auto-write to memory. User decides.

---

## Safety notes

- patterns files contain real quotes — treat as sensitive personal data
- NEVER commit output artifacts to the jarvis repo
- If GDrive upload fails → leave files in staging, report path, do NOT delete

## Limitations

- Corrective regex is narrow — subtle pushback generates false negatives
- Category inference is heuristic — "other" bucket may be large; agent fills the gap
- Sessions with <3 user msgs are skipped
- Same pattern corrected on 2 devices counts twice — intentional (cross-device repetition = stronger signal)
