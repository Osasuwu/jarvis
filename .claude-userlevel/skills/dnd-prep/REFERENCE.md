# /dnd-prep — Reference

Methodology details and templates. Loaded on demand from SKILL.md.

---

## Lazy DM (Sly Flourish) — checklist order

Mike Shea's *Return of the Lazy Dungeon Master*. Prep in this order; stop early if time runs out — earlier items matter more.

1. **Strong start.** What's the very first thing? Should hook in <60 seconds. Action, mystery, or stakes — never exposition.
2. **Outline potential scenes.** 4–6 high-likelihood scenes. NOT a script. Each scene = a situation, not a sequence. Players' choices determine which fire.
3. **Define secrets and clues.** 10–15 atomic facts. Not tied to scene or NPC. When a player investigates anything, hand out a fitting clue. Reuses facts that PCs miss in one scene by surfacing in another.
4. **Develop fantastic locations.** 3 evocative details per location. One sensory anchor (sound, smell, light), one weird/wrong detail, one interactive element.
5. **Outline important NPCs.** Personality > script. 3 traits + 1 motive + 4 phrases (greet/threat/request/farewell). Names ready.
6. **Choose relevant monsters.** Pick from existing statblocks — don't invent. CR-balance for party. Have 2 backup encounters for if pacing drags.
7. **Select magic items.** Only if relevant. Don't force loot.

**Rule of thumb**: skip steps 5–7 in a pinch; never skip 1–4.

---

## Fronts & Clocks (PbtA/Blades)

A **front** is a coherent threat with intent. The world has multiple fronts; they advance whether or not PCs engage.

### Front template

```
## Front: <name>

**Type:** <BBEG-faction | environmental | rival-PC-group | etc.>
**Agenda (one line):** <what they want to achieve>
**Stakes question:** <what's at risk if they succeed; what's at risk if they fail>

### Clock (1–6 segments)
- [ ] 1: <visible event, reachable in current state>
- [ ] 2: <next escalation>
- [ ] 3: <midpoint, world visibly changes>
- [ ] 4: <near-completion, PCs feel pressure>
- [ ] 5: <last chance to stop>
- [ ] 6: <front succeeds — describe consequence>

### Tick triggers
- PCs ignore X
- PCs do Y
- N hours of in-game time pass
- Specific event Z occurs

### Cast (NPCs tied to this front)
- <name>, <role>
- <name>, <role>
```

**Common mistake**: making the BBEG-clock the only one. Have at least one secondary front (faction conflict, environmental decay, rival party) that ticks independently. This makes the world feel alive even when PCs fixate on BBEG.

### Clock cadence rule

Clocks tick **at scene boundaries**, not on a wall-clock. If three scenes pass with no PC interaction with front F, tick F by 1. If PCs actively oppose F, may tick *backward* on success. Tell players when a clock ticks (in fiction) — they should *see* the world change.

---

## Causal chain audit (Phase 4 detail)

For each scene in `14_Сцены.md`, write three lines:

```
Scene <N>: <name>
  Triggers because: <what causes this scene to fire>
  Connects forward to: <which scenes it can lead into, and what determines which>
  Front impact: <which clocks tick / un-tick based on PC actions here>
```

**If you can't write the "triggers because" line without saying "DM scheduled it" — the scene is a railroad. Either:**
- Replace it with a *front clock tick* that manifests as a scene (event-driven, not script-driven), OR
- Cut it and add the information to secrets-and-clues so it surfaces wherever PCs probe, OR
- Tie it to a specific PC choice in a previous scene.

---

## BBEG planning template

```
## BBEG: <name>

**Wants (positive goal):** <what they're trying to achieve, in their words>
**Method:** <how they're achieving it>
**Blocked by:** <what's currently in their way; if nothing — they'd already have won>
**Believes (lie they tell themselves):** <the rationalisation that makes them sympathetic-or-comprehensible>

### State at session start
- Plan completion: <0–100%>
- Resources: <what they currently have>
- Allies: <names>
- Enemies: <names, including PCs if known>

### Visible moves per act (if PCs do nothing)
- Act 1: <what PCs hear about / see consequence of>
- Act 2: <escalation>
- Act 3: <near-victory; world visibly worsens>

### What stops them
- Specific weakness: <thing>
- Required to defeat: <not just HP — what conditions / items / allies>

### Defeat / victory states
- BBEG wins: <world state>
- BBEG loses cleanly: <world state>
- BBEG loses with cost: <world state — usually most interesting>
```

**Rule**: BBEG must have a plan that doesn't require PCs. Test: remove PCs from world. Does BBEG still progress? If yes → good. If no → BBEG is reactive, not active. Rewrite.

---

## Secrets and Clues — patterns

Format each clue as a single short fact. Examples (from a generic mystery world):

1. The mayor's son disappeared on the same night the lighthouse went dark.
2. The lighthouse keeper hasn't been seen in 3 weeks; mail piles up at the door.
3. A specific brand of brass key fits both the mayor's office and the lighthouse cellar.
4. The harbour fish have been migrating away — fishermen are angry.
5. ...

**Rules:**
- Each clue ≤ 1 sentence.
- Clues are *atomic facts*, not full conclusions. Players synthesise.
- Don't tie a clue to one scene/roll. If PCs investigate anything (rumour, search, interrogation, inspection), pull from this list.
- Aim for 10–15. Some PCs will miss; redundancy is fine.
- Clues should *combine* into the BBEG's plan when 4–5 are gathered. Don't make it solvable from any single clue.
- Mark clues used per session so you don't repeat.

---

## Scaffold file templates

### 00_Обзор.md

```md
# <Имя мира> — обзор

[[01_Мир]] [[02_Законы]] [[09_Вход_и_Выход]] [[14_Сцены]]

## Pitch
<1 paragraph, hook the DM>

## Структура
- [[01_Мир]] — мир и тон
- [[02_Законы]] — что отличает его от других
- [[05_Локации/00_Обзор|Локации]] — карта и узлы
- [[06_NPCs|NPCs]] — кто живёт
- [[08_Цели_и_Финалы]] — миссии и финалы
- [[09_Вход_и_Выход]] — точки входа/выхода

## DM-only
- [[10_Fronts_и_Clocks]]
- [[11_Secrets_и_Clues]]
- [[12_BBEG]]
- [[13_Причинная_карта]]
```

### 06_NPCs/<имя>.md (Petr's "phrases" pattern)

```md
# <Имя>

**Тип:** <фракция / роль>
**Локация по умолчанию:** [[<локация>]]

## Личность (3 черты)
- <черта 1, цветным ключевым словом>
- <черта 2>
- <черта 3>

## Мотив (1 строка)
<что хочет, прямо сейчас>

## Связи
- <NPC X> — <отношение>
- <фронт Y> — <роль в нём>

## Фразы
- **Приветствие:** "<...>"
- **Угроза:** "<...>"
- **Просьба:** "<...>"
- **Прощание:** "<...>"

## Что знает (Secrets-and-Clues)
- Clue #N: <выдаёт при каком триггере>
- Clue #M: <выдаёт при каком триггере>
```

### 08_Цели_и_Финалы.md (oneshot version)

```md
# Цели и финалы

## Условие выхода
Портал открывается, когда выполнено **любое одно** из заданий ниже.

## Миссии (выбор игроков)

### Миссия A: <имя>
- **Что нужно сделать:** <verifiable action>
- **Кто заинтересован:** <NPC / фракция>
- **Как игроки узнают:** <hook source>
- **Что меняется в мире:** <consequence visible in finale>

### Миссия B: <имя>
... (same template)

### Миссия C: <имя>
... (same template)

## Финалы

### Чистый успех
<world state, NPC reactions, what PCs carry out (если кампейн)>

### Успех с ценой
<most interesting; default if PCs choose mission but harm BBEG-front simultaneously>

### Провал / откат
<if clocks fill before PCs finish; world ends in worse state, but PCs still exit>
```

### 12_BBEG.md (DM-only)

Use BBEG planning template above, verbatim.

### 13_Причинная_карта.md (DM-only)

```md
> ⚠️ DM ONLY

# Причинная карта

## Цепочка (because-chain, не "and then")

```
Сцена 1 (Сильное начало)
   ↓ because PCs <X>
Сцена 2A (если PCs выбрали миссию A)
   ↓ because clue <#3> + front F1 tick 2→3
Сцена 3 (BBEG's lieutenant arrives)
   ↓ because ...
```

## Front-clock зависимости

- F1 tick 1→2: PCs не пошли по миссии A в первом акте
- F1 tick 2→3: PCs убили <X> или <Y>
- F2 tick 1→2: время — после первой ночи
- ...

## "Что было бы без PCs" (sanity check)

- За 24 часа без PCs: <world state>
- За неделю без PCs: <world state>
- BBEG достигает плана: <how long, what world looks like>
```

---

## Common failure modes (audit checklist)

- [ ] **One-true-path syndrome**: every scene leads to next on rails. Fix: make scenes *fire on conditions*, not order.
- [ ] **BBEG vacuum**: BBEG only acts when PCs poke them. Fix: clock ticks regardless.
- [ ] **NPC clones**: 3 NPCs want the same thing. Fix: distinct motives, even if they overlap on surface.
- [ ] **Clue bottleneck**: critical info gated behind one roll. Fix: 2+ paths to every load-bearing fact.
- [ ] **Strong-start tavern**: opening is exposition, not action. Fix: drop PCs into a moment with stakes.
- [ ] **Goal opacity**: PCs don't know what to do for 2+ scenes. Fix: by end of strong start, PCs have *a* direction (even if wrong).
- [ ] **Combat dump**: 3+ fights in 4-hour session. Fix: 1–2 fights, social/exploration the rest (Petr default).
- [ ] **Final-room BBEG**: BBEG only appears at climax. Fix: visible-from-act-1, even if not engaged.

---

## Petr-specific notes

- Vault: `C:/Users/petrk/OneDrive/Документы/Obsidian Vault/DnD/`. Cyrillic `Документы`, space in `Obsidian Vault`. Always quote paths.
- Existing worlds (reference for tone/depth): `Стимпанк/` (closed), `Бездна/` (active, Lumenite mechanic). Don't copy plot, copy *structural density*.
- Players overlap with campaign (Эдуард, Никита, Даня): out-of-fiction they may know meta. **Never** drop hints that connect a oneshot world to the campaign chain. Treat as different Worm entirely.
- Combat balance: Petr historically prepped for 2–3 PCs. Now group up to 5. Default: monsters at advertised CR + 1–2 minion mooks; have ready 1 "elite" upgrade for boss if pacing demands.
- Petr explicitly dislikes "and then" plotting (his own assessment of Бездна notes). The causal audit is *the* differentiator of this skill.
