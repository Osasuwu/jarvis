---
name: dnd-prep
description: Prepare D&D 5e worlds, oneshots, and campaign segments using Lazy DM + Fronts/Clocks methodology, with mandatory grill causal audit and scaffolding into Petr's Obsidian vault. Use when the user says "подготовь мир/ваншот", "новый сегмент кампейна", "придумай BBEG", "проработай мир X", "/dnd-prep", or describes prepping a D&D session that does not yet exist. Do NOT use for in-session play (that is /dnd), rules questions, character sheets, or generic GM advice (that is /gm-craft).
---

# /dnd-prep — D&D world & oneshot preparation

Companion to `/dnd` (in-session) and `/gm-craft` (storytelling reference). This skill produces **prepared worlds**, scaffolded into Petr's vault, with causal sanity-checked plots.

## Hard rules (non-negotiable)

1. **Meta-setting is invisible to players.** The campaign frame is "worlds inside the Червь parasite." Output that goes to players (handouts, in-fiction text, NPC dialogue) NEVER references this directly. Hints only as world-reactions ("вселенная недовольна", echoes on ascent like Бездна's Depth Strain).
2. **Causal chain, not "and then".** Every major event must answer: *"why now? why here? what would happen without PCs?"* "Because DM wrote it" → rewrite. Run the audit in Phase 4.
3. **Grill is mandatory** before scaffolding (Phase 1) AND after (Phase 5). Do not skip on "small task" — see SOUL.md grill trigger checkbox.
4. **Vault path:** `C:/Users/petrk/OneDrive/Документы/Obsidian Vault/DnD/` (Cyrillic `Документы`, space in `Obsidian Vault`). New worlds go to `DnD/Сюжет/<Имя>/`.
5. **Petr's DM philosophy** (memory: `dnd_dm_philosophy`): short notes with colour keywords, NPC personality > scripted lines, flexible combat, homebrew-but-accessible. Never produce wall-of-text NPCs.
6. **Don't rewrite 5e mechanics.** PHB/DMG live in `DnD/Мануалы/`. Reference page numbers when needed.
7. **Default scope:** 1–2 fights, rest social. Petr's group prefers social. Override only if user says so.
8. **BBEG (if used)** has a *plan with clocks*, not "waits in final room." See REFERENCE.md → Fronts.

## Phase flow

Run phases in order. Each phase has a gate — don't skip.

### Phase 0 — Intake

Ask only what's missing from the user's prompt:

- **Tone**: серьёзный / тёмный / комедийный / смешанный (pick one dominant)
- **Length**: ваншот (~4–5h, single sit) / multi-act ваншот / campaign segment
- **Players**: count + names if given (matters for balance + character carry-over)
- **Type**: standalone / will-integrate-into-campaign / segment of existing
- **BBEG?**: yes / no / unclear
- **Special mechanics**: amnesia, hidden sheets, time loop, swapped bodies, etc.
- **World direction**: user's preference, or "propose 3 candidates fitting tone+mechanics"

Do NOT ask everything. Read the prompt; ask only gaps.

### Phase 1 — WHY (grill on premise)

**Gate: do not proceed without resolved answers to all four.**

Invoke `/grill` with these questions (or run the equivalent inline if grill is unavailable):

1. **Why this world?** What does it offer thematically that another wouldn't? What's the *experience* the players walk away with?
2. **Why this BBEG?** (if any) Their motive must intersect with PCs, not be cosmic-ambient. What do they *want*, what's their *plan*, what's *blocking* them?
3. **Why this group?** Are PCs randomly thrown together or is there causal connection (shared history, common target, mutual enemy)? In oneshots with amnesia — especially load-bearing.
4. **Why now?** What event triggered the timeline being relevant? Why didn't this happen 10 years ago or in 10 years?

Output: 4 short answers, each ≤100 words. Save to scratch — used in Phase 2.

### Phase 2 — HOW (mechanism design)

Build, in order:

1. **Fronts** (1 BBEG-front + 1–2 secondary). Each front = name, agenda, clock (3–6 segments), what each segment manifests as in-world. See REFERENCE.md → Fronts/Clocks.
2. **Secrets and clues** — list **10–15 facts** about the world/BBEG/history. Not tied to scenes. Drop them as opportunities arise. See REFERENCE.md → Secrets-and-Clues.
3. **BBEG plan** — what's their state at session start (% complete), what visible moves do they make per act if PCs do nothing, what stops them, what victory/defeat looks like.
4. **Goal / portal-key (oneshot only)** — what must PCs accomplish to exit. Multiple equivalent missions if possible (don't rail-road).
5. **Strong start** — opening scene that immediately puts PCs in motion. No "you're in a tavern."

### Phase 3 — Scaffolding (Obsidian write)

Create folder `DnD/Сюжет/<Имя>/` with these files. **All files contain draft content, not empty templates.** Use Petr's existing world structure (see `Стимпанк/`, `Бездна/`) as reference for tone/depth.

Files (numbered for sort-order in Obsidian):

```
00_Обзор.md              ← entry point, links to all sections, 1-paragraph pitch
01_Мир.md                ← genre, tech level, broad strokes
02_Законы.md             ← physics/magic/society laws (3–5 distinct)
03_Существа.md           ← inhabitant types, brief
04_Экономика.md          ← key resource, scarcity, who controls what
05_Локации/              ← folder
   00_Обзор.md           ← map sketch, 6 locations, 2-sentence each
   <Имя_локации>.md      ← per-location file with vivid 1-paragraph desc
06_NPCs/                 ← folder, 6 NPCs, one file each
   <Имя>.md              ← personality (3 traits), motive (1 line), 4 phrases:
                            (greet / threat / request / farewell)
07_Враги/                ← folder, 6 enemy types, CR estimates for party size
08_Цели_и_Финалы.md      ← 2–4 mission options, each opens portal/exit
                            3 endings with consequences
09_Вход_и_Выход.md       ← entrance scene, exit conditions, what PCs see
10_Fronts_и_Clocks.md    ← DM-only, fronts + clocks, escalation triggers
11_Secrets_и_Clues.md    ← DM-only, 10–15 facts, where each can surface
12_BBEG.md               ← DM-only, full plan, motive, statblock pointer
13_Причинная_карта.md    ← DM-only, "X because Y because Z" diagram
14_Сцены.md              ← 4–6 key scenes, each with strong opening + branches
```

Files marked DM-only get a top banner: `> ⚠️ DM ONLY — НЕ показывать игрокам`.

### Phase 4 — Causal audit

Walk through `14_Сцены.md` and `10_Fronts_и_Clocks.md`. For each scene transition and each clock tick, write the *because* explicitly. If you find an "and then" — fix it.

Acceptable patterns:
- "Scene B happens **because** PCs found clue X in Scene A, **and** front F's clock ticked from 2→3 due to PC inaction."
- "BBEG's lieutenant attacks **because** PCs robbed the courier in Act 1, signalling threat."

Unacceptable:
- "Scene C is the next scene." → fix it or cut it.
- "BBEG appears here." → why here, why now?

Save audit notes inline in `13_Причинная_карта.md`.

### Phase 5 — Final grill pass

Re-invoke `/grill` on the written scaffold. Focus areas:

- Are clues redundant or load-bearing on a single roll?
- Can PCs reach the goal without ever encountering BBEG? (Often a feature, not bug — but be intentional.)
- Are NPC motives distinct or do 3 NPCs want the same thing?
- Does each location pull its weight (≥1 secret OR ≥1 NPC OR ≥1 front-tick)?
- Strong start passes the "would I want to play this opening?" test?

Patch findings inline. Done when grill returns no critical gaps.

## Output to user

After Phase 5:

```
Подготовлено: <Имя_мира> в <vault_path>/Сюжет/<Имя>/

Тон: <tone> | Длина: <length> | Игроки: <n> | BBEG: <name | none>

Strong start: <one-line pitch of opening scene>

Mission(s) → portal: <list>

Fronts: <count> active, <count> clocks ticking
Secrets: <count> facts seeded
Scenes: <count> drafted

Что спросить у игроков ДО сессии: <list, e.g. character concepts, comfort lines>
Что Петру решить: <unresolved items, if any>
```

## When NOT to use this skill

- In-session play, dice, combat tracking → `/dnd`
- General GM technique reference (fail-forward, NPC voice, etc.) → `/gm-craft`
- D&D 5e rules questions → reference PHB/DMG in `DnD/Мануалы/`
- Player-side character creation → not this skill
- Editing an already-prepared world → use Edit on the existing files; this skill is for *new* worlds

## See also

- [REFERENCE.md](REFERENCE.md) — Lazy DM details, Fronts/Clocks templates, BBEG planning, secrets-and-clues patterns, scaffold file templates with example content.
