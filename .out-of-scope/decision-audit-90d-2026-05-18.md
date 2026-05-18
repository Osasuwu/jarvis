# 90-day Decision Calibration Audit — 2026-02-17 to 2026-05-18

**Reason for .out-of-scope/:** standalone audit artefact, snapshot of decision quality at 2026-05-18. Not project state; not part of any milestone. Saved here so it can be opened in a fresh session for follow-up discussion.

**Source memory:** `decision_calibration_audit_2026_05_18_90d` (reference/jarvis).
**Source transcript:** session `ed06ccc7-4759-44b1-88f7-08da7ef13086` (2026-05-18 chat).
**Subagent raw dumps:** `C:\Users\petrk\AppData\Local\Temp\claude\C--Users-petrk-GitHub-jarvis\ed06ccc7-4759-44b1-88f7-08da7ef13086\tasks\*.output`.

---

## Scope and method

- **Window:** 2026-02-17 → 2026-05-18 (90 days).
- **Sources:** 277 PR + 414 issues + 17 PR closed without merge + 100 outcome records + 134 memories (decision+feedback) + 4 /reflect snapshots covering 223 sessions on 3 devices + CLAUDE.md/SOUL.md/CONTEXT.md/docs/design.
- **5 parallel subagents** by area: Memory/Cognitive, Skills/Workflow, Architecture/Multi-agent, Infra/Ops, Process/PR-hygiene.
- **Dedup:** ~85 BAD / ~70 NORMAL / ~95 GOOD after cross-area merge.

### Categories

- **BAD** — rework / inaccurate / abandoned / superseded ≤30d / caused downstream failure.
- **NORMAL** — works, but a better alternative existed and is now obvious in hindsight.
- **GOOD** — strong durable improvement, still load-bearing 2026-05-18.

### Actor labels

- `[U]` = пользователь сам предложил/одобрил/инициировал.
- `[J]` = автономный Jarvis-call (actor=session:* в decision episodes).
- `[JT]` = joint (grill-сессия, два-стороннее обсуждение).

---

## BAD (~85)

### Memory & Cognitive

1. `[JT]` v1.5 "6+1 skills" plan ratification (`mem:jarvis_v15_skill_final_plan`, 2026-04-12 → SUPERSEDED 2026-05-16) — все 5 "удалённых" скиллов вернулись, 34 дня memory гнила без STATUS.
2. `[J]` always_load silt-up до 23 entries — outcome 2026-05-15, #641 открыт, дефанс-таггинг как симптом recall-quality gap.
3. `[J]` Phase 3 Haiku rewriter type narrowing как hard filter — PR #207 reverted ("rewriter types → soft boost"), −5pp recall@5 в проде.
4. `[J]` PR #423 "Phase 5.3-α FoK design" — закрыт без merge (2026-04-26), 5h-old. Использовался как design-RFC канал.
5. `[J]` PR #245 "dual-embedding read-path voyage" — закрыт через 18 мин после открытия (2026-04-20).
6. `[J]` PR #244 "confidence multiplier" — закрыт через 18 мин (2026-04-20).
7. `[J]` PR #255 "calibration view + RPC" — закрыт через 1 мин (2026-04-20). Сцепка #243/#244/#245/#255 = over-decomposition memory features.
8. `[J]` PR #243 "context-rot eval" — abandoned 2026-04-20; gap всплыл через 27d при сборке M43 sycophancy harness.
9. `[J]` Dup-detector на same-name upserts (iter:13, 2026-05-16) — 4 retry с progressive description failed; mismatch между invariant и behavior.
10. `[J]` /reflect 5-corrective taxonomy преждевременно — 85% false positives на свежем корпусе, пере-выведена с нуля в #583.
11. `[J]` `verify_skill_not_reflect` (2026-04-14, SUPERSEDED 2026-05-03) — 19 дней спустя то же имя использовано для comms audit.
12. `[J]` `no_memory_hygiene_tool` decision (2026-04-15) противоречит iter:11-13 ручным STATUS-sweep'ам — temporal decay не закрывает stale-reference rot.
13. `[J]` `record_decision` post-hoc captures — рекуррент через все 90 дней; правило в памяти, но не recall'ится в момент решения.
14. `[J]` `outcome_record.memory_id` FK gotcha (#660) — 5× рекуррентов до того как файлится трекер.
15. `[J]` /delegate batch #665+#662 wholesale fail — MCP tool-schema oneOf/allOf regression, 0 токенов 0 tool-use. Silent в parent.
16. `[J]` iter:50 #669 XML-asymmetric-strictness на `record_decision` — N=6 в одной AFK chain.
17. `[J]` PR #489 grill-me-protocol stack-on-#487 — закрыт без merge, переделан как #492.

### Skills & Workflow

18. `[J]` /improve оркестратор + Sense/Decide/Act grill (2026-05-06) — 3 record_decision выкинуты в тот же день. Lesson: rebuild conceptually-wrong, don't iterate.
19. `[J]` /checkpoint скилл (2026-03-30 → SUPERSEDED 2026-05-16) — поглощён SessionStart hook + working_state. Skill не нужен был.
20. `[J]` /end-quick как отдельный скилл — 27 дней дубликата, слился в `/end --quick` (PR #575).
21. `[J]` /grill-me + /grill-with-docs + /grill — 3 sibling-скилла, 2 в `.bak.orphan`. Нарушение `naming_check_existing_vocabulary`.
22. `[J]` /tdd shipped → removed за 4 дня (PR #597 → #600). Стал режимом /implement и /delegate.
23. `[J]` /status (PR #106) → dropped (PR #590), /morning-brief + /risk-radar + /triage поглощены /status, потом /status сам убит.
24. `[J]` /intel скилл (PR #90) → свёрнут в /research.
25. `[J]` AI Hero 11 Pocock-скиллов импорт (PR #487) → walked back (PR #588) через ~10 дней — кастомизации не той формы.
26. `[J]` PR #328 docs(skills) reconcile contradictions — 3 дня open, закрыт без merge: catalog churn делал reconciliation movable target.
27. `[J]` /last-work-report скелет (PR #645 OPEN на момент аудита) — `skill_proliferation_antipattern` нарушен.
28. `[J]` Installer .bak.orphan рекурсия (`dnd.bak.orphan.bak.orphan.bak.orphan`) — quarantine quarantine'ит свои бэкапы, fix через #659/#676.

### Architecture & Multi-agent

29. `[JT]` PM dispatch v1 wave-based hierarchy — 13-day shelf life, superseded persistent agents 2026-04-21.
30. `[JT]` Pure flat federation framing (2026-04-21) — reframed to HYBRID за <24h после MAST research (41-86.7% peer-coord failure).
31. `[U]` "Fork Anthropic Code Review плагин — first task next session" (`v2_open_questions_resolved_2026_04_27`) — PR не сложился в окне, решение висит.
32. `[J]` Parallel isolation:worktree #249-#252 (2026-04-20) — branch-name race, file contamination, PR #255 auto-closed. Триггер для sandcastle redemption arc.
33. `[JT]` `milestone_structure_v2` (2026-04-13) → `milestone_hierarchy_v3` (2026-05-08) — sprint-как-milestone time-box убит за 25 дней.
34. `[JT]` "epic" как grouping primitive — co-existed с milestone весь апрель, formally dropped 2026-05-08.
35. `[J]` "owner" терминология везде — 164-ref pass в PR #461 после `user_not_owner_framing_2026_04_28`.
36. `[J]` Flat M3 protected-file list — `.mcp.json` приравнен к `.env`, audit заставил split на 6 hard + 3 soft.
37. `[J]` C2 candidate-goal owner-approval queue — заменено auto-create draft (over-confirmation).
38. `[J]` C16 owner-gate-all-PRs default — заменено class-aware auto-merge.
39. `[J]` `safety.gate()` оригинальный Sprint 2 design — shipped как `safety.audit()` + `idempotency_key` (design vs ship divergence на критичном примитиве).
40. `[J]` `_placeholder_tick` в scheduler CLI после Sprint 2 close — milestone #21 закрыт "8/8" пока CLI крутил placeholder, не диспатчер. #368/#374/#376 — fix.
41. `[JT]` `task_queue` зашипован без input-side writer — диспатчер живёт, но queue empty.
42. `[J]` Issue Checks workflow в event-dispatch триггерах — 136 spam events до фикса.
43. `[JT]` Cloud scheduled tasks ↔ `.mcp.json` — cloud не грузит .mcp.json, fallback на `execute_sql`.
44. `[J]` /end behavioral-reflection step внутри /end — пришлось вынимать (PR #518) при разделе с /reflect.
45. `[J]` PR #80 autonomous tool routing from plain chat — closed not merged, направление abandoned.

### Infra & Ops

46. `[J]` Schema-drift guard смотрел на `supabase/schema.sql`, канонический `mcp-memory/schema.sql` — silent green неделями. 3 PR (#293/#310/#311) на конвергенцию.
47. `[J]` PR #491 time-bomb `_now()` fixtures abandoned (drive-by без `git pull origin main` — #479 уже был с фиксом тем же утром).
48. `[J]` PR #563 sandcastle slice-3 RLS gate закрыт без merge, переделан #570 через 8d — RLS shape wrong на первом cut.
49. `[J]` PR #373 dispatcher без `--permission-mode` flag — watchdog spawn failed, 2-PR rework.
50. `[J]` Subagent #691 hardcoded `C:\Users\petrk\...` в tests — 13 тестов ERRORed на Linux CI.
51. `[J]` Subagent #690 worktree contamination — cross-pollinated #689 + #691 + не открыл PR; orchestrator surgically reset + force-push дважды.
52. `[J]` PR #438 installer hotfix: abs vs rel paths — whitelist silently disabled с #413 ~10 дней.
53. `[J]` PR #347 user-level deep-merge MCP — нужен PR #405 с 2 follow-up (shadow MCP + register-via-CLI). Initial incomplete.
54. `[J]` PR #612/#611 sandcastle prompt.md chain workarounds — original RC hypothesis wrong, 5 PR пока owned свой баг локально.
55. `[J]` /tdd source-deleted но Main PC mirror retained (#655) + #606 last-work-report registered в source missing в mirror (#656). Installer pipeline asymmetric.
56. `[J]` PR #502 supabase stub broke на пустом package — cross-device infra bite.
57. `[J]` schema.sql как source-of-truth — #631 review поймал что RPC должны быть в migration, не в schema.sql.
58. `[J]` `fok-batch.py` silent-fail-with-unknown — 154 polluted rows, трекер только retro #649 2026-05-16.
59. `[J]` Telegram MCP `.env` CRLF + BOM Windows-регрессии — editor re-saves, `server.ts:36` split('\n')+regex shared root.
60. `[J]` Stuck Claude code-review job ≥8 min на PR #588 — bot in_progress пока mergeable=true.

### Process & PR hygiene

61. `[J]` Drive-by branch off stale main → dup PR #491 + #490 (2026-04-30) — #479 уже сделал тот же time-bomb фикс днём раньше.
62. `[J]` Stacked-PR delete-branch chain auto-close — #371 → #373 (2026-04-24) + #487 → #489 (2026-04-30). Третий раз pattern.
63. `[J]` Subagent fabricated 16/16 test claims (redrobot #640 PR #647) — commit message перечислял тесты которых нет в diff.
64. `[J]` PR #423 как design-RFC канал — debate в PR review, замкнулось без merge. Породило `design_rfc_not_pr_channel` rule.
65. `[J]` 3× AC dodge subagent'ом как "out of scope" (#444/#445 FoK Phase 5.3) — scheduled-tasks reg + insufficient-cluster section + apply_migration skipped silently.
66. `[J]` Untracked файл в main tree leaked в subagent commit (PR #412) — 197-line orphan через `git add -A`.
67. `[J]` Subagent worktree hijack discarded uncommitted local edits (#413).
68. `[J]` PR #646 `[no-issue]` body marker rejected by PR Body Check — agent confused commit-msg regex (#329) с PR Body Check workflow.
69. `[J]` Hotfix #442 + #441 + #438 в 6-day burst (installer.py) — fixes-of-fixes. Sibling-grep при #438 поймал бы оба.
70. `[J]` Milestone #38 sat open после 12/12 slices (2026-05-13 → 2026-05-17) — закрыт watchdog tick'ом, нарушение "0 open issues + state=open is a bug".
71. `[J]` 17 closed-not-merged PRs cluster: auto-closed-by-stack-delete (≥3), dup-of-already-shipped from stale main (≥2), design-RFC mis-channel (≥1). #563/#491/#489/#423/#374/#373/#328/#255/#245/#244/#243/#207/#179/#101/#92/#81/#80.
72. `[J]` `decisions_belong_in_memory_not_gh_issue_bodies` — referenced в CLAUDE.md, отсутствует в memory store (rule только в .md, queryable channel missing).
73. `[J]` `parallel_delegate_worktree_isolation_failed_2026_04_20` memory не surface'ила перед 2026-05-17 batch — тот же класс через 27d.
74. `[J]` PR #101, #92 self-improve drive-by closed unmerged — speculative cleanup без milestone, Fix>track правило применилось post-hoc.

---

## NORMAL (~70)

### Memory & Cognitive

1. `[U]` Phase 2c strict NOT NULL provenance + `legacy:pre-2c` backfill (PR #198) — rejected gradual rollout поймал бы missing-provenance пути раньше.
2. `[JT]` Consolidation Option A (memory_review_queue) — single UI, но `consolidation_payload jsonb` + EVOLVE reuse перегрузили status semantics.
3. `[J]` `consolidation_soft_archive` через `expired_at` (PR #218) — правильно, но type-suffix хак не был отловлен в Phase 5.1a.
4. `[J]` Memory 2.0 auto-linking on store (A-MEM Zettelkasten) — fire-and-forget link creation позже всплыл в #660 cross-table consistency hazard.
5. `[JT]` Plan-level MIN confidence gating в evolve-neighbors — консервативно, но #235 EVOLVE-review-CLI-less gap оставил apply path semi-manual.
6. `[JT]` Phase split deterministic 2a → LLM 2b — pattern правильный, но не применился к /reflect taxonomy (#583 пере-выводил с нуля).
7. `[J]` `memory_review_queue` status semantics — clarified mid-Phase-4 через Copilot review, не на design-time.
8. `[J]` Classifier supersession race (b4b2693) — fix правильный, но Copilot поймал (d) и (e), не self-review.
9. `[J]` `old_memory_migration_policy` "cheap now, expensive deferred" — bundle с abandoned #244/#245/#255 создал migration-debt cluster.
10. `[JT]` /grill-me 4-question checkbox — правильная форма, но initial PR (#489) abandoned, adaptive vs hard-gate ambiguity висит.
11. `[J]` CONTEXT.md как отдельный файл — useful, но grill-outputs часто шли в memory-only без CONTEXT.md update.
12. `[JT]` reflection-driven sprint #319/#320/#321 — 3 lesson→gate, но #318 mcp-memory UUIDs deferred to owner, gate не сел.
13. `[J]` /reflect ADR 0004 + 6-value enum — empirically правильно, но CHECK constraint жёсткий, migration шире была бы тяжелее чем schemaless.
14. `[J]` PR #680 `[no-issue]` PR-body как третий escape — правильно, но 25-day memory pинговалa stay-strict; old policy memory надо было demote раньше.

### Skills & Workflow

15. `[J]` Skill catalog migration в `.claude-userlevel/` (PR #345/#354) — works; better alternative — skills global с day-1.
16. `[J]` /research v2 firecrawl pivot (2026-03-31) — works, defer до бюджет-caps был бы дисциплинированнее.
17. `[J]` Hypothesis tracking Step 6 в /reflect (2026-03-31) — старый /reflect ушёл в `docs/design/reflect-aggregates-pending-migration.md`.
18. `[J]` /implement /delegate /verify memory_id wiring (#287→#292) — fix правильный, но downstream #319/#320/#321 rework нужен был.
19. `[J]` /setup-tasks revived через 1 день после "delete" — clean revert но churn.
20. `[J]` /autonomous-loop revived через 1 день — clean revert.
21. `[J]` /status-record Type-1 cron (PR #579) — net-add после kill /status, proliferation reflex.
22. `[J]` /zoom-out /diagnose /improve-codebase-architecture — landed без grill против `skill_proliferation_antipattern`, usage ceiling не доказан.
23. `[J]` /caveman token-compression — мог быть system-prompt clause вместо скилла.
24. `[JT]` reflection-driven sprint 2026-04-23 — auto-mining не wired, потребовался user prompt.

### Architecture

25. `[U]` `architecture_final` no-Python-services (2026-03-28) — load-bearing, но "final" label misleading: arch эволюционировал (sandcastle, schema, 25 skills).
26. `[U]` Personal-vs-company separation (2026-04-15) — works, не тестировался под cross-cutting strain.
27. `[U]` Managed Agents wait-and-see (2026-04-09/2026-04-21) — stands, но upside не captured.
28. `[JT]` Action-agent tiered safety gate Tier 0/1/2 — survives, но Tier-1 queue ≈0 real items (starvation).
29. `[U]` LangGraph carveout (2026-04-22/2026-04-27) — scope elastic.
30. `[J]` Autonomous loop v1 schedule + hygiene sweep (Layer 2) — works, Phase 2 event-driven perception not built.
31. `[J]` Event-driven perception v1 — functional, требовал спам-фикс + cloud workaround.
32. `[U]` C18 Proactive Challenger (2026-04-28) — добавлен в L1, bootstrap timing deferred, firing не наблюдалось.
33. `[JT]` `architecture_growth` UP/DOWN — useful frame, "owner altitude" shift blocked на #368 + perception ingest.
34. `[JT]` Federation phase 0 (installer + ~/.claude/ + protected-files) — shipped, core skill list outdated per STATUS.
35. `[JT]` Engineering principles (anti-vibe) в L0 (PR #493) — частично дублирует SOUL.md.
36. `[U]` `pillar7_phase2_six_choices` revisit triggers — некоторые не мониторятся (cross-jurisdiction conflict rate, LangSmith debug-hours).
37. `[JT]` `autonomous_loop_hygiene_sweep_v1` — three-layer defense, не firing на non-trivial находку для валидации.

### Infra

38. `[J]` PR #178 LangGraph Supabase bridge — superseded direct MCP routing, kept quietly de-emphasised.
39. `[J]` PR #69 M1 Telegram bridge → superseded PR #89 Channels plugin за 5d — first-pass throwaway.
40. `[J]` dependabot supabase 2.0→2.30 (PR #451/#452) — auto-merged, no integration smoke.
41. `[J]` `events_canonical` migration + MVs (PR #481) — shipped, observability of MV refresh не была сразу.
42. `[J]` `fok_judgments` table + dual-write (PR #470) — works, dual-write ongoing read complexity.
43. `[J]` PR #357 protected-files.py + #427 principal-aware — 2-step ship, base alone had gaps.
44. `[J]` PR #361 PreToolUse action-triggered recall — fires на broad surface, occasional drag.
45. `[J]` PR #350 installer "tolerate mid-copy vanishing" — defensive patch, не root cause.
46. `[J]` PR #353 installer UTF-8 force — Windows-specific, no cross-shell test.
47. `[J]` PR #463 batch install 5 Anthropic plugins — depends on plugin manifest stability.
48. `[J]` PR #577 Tier 2 hook memories_used — XML-asym-strict false positives 6× в iter:22-57.
49. `[J]` PR #578 installer orphan-skill quarantine — root of #659 recursion bug.
50. `[J]` PR #570 RLS provenance gate — landed после #563 closed, correct shape на second pass.
51. `[J]` PR #574 sandcastle multi-tier escalation — depends on per-device Workshop Ollama.
52. `[J]` PR #629 redrobot watchdog + shared scheduler — pytest-gate AC deferred #630.

### Process

53. `[J]` Hotfix `priority:critical` (#438/#441/#442) — bypass works, но всё из installer.py — модуль одна fragile точка.
54. `[JT]` PR Body Check three-escape evolution (#329 → #424 → #680) — accreted incident-by-incident, не designed.
55. `[J]` `stacked_pr_rebase_onto` recipe (2026-04-21) — workaround git-pain, не elimination.
56. `[J]` Subagent dispatch absolute-path mitigation post-hoc — sibling-subagent #689 сделал правильно, quality non-deterministic.
57. `[J]` CONTEXT.md drift через STATUS-header pattern — curative not preventive.
58. `[J]` /triage `status:ready` без grep на main (#486 lesson) — rule в engineering posture, но skill prelude не enforced.
59. `[J]` Outcome→issue Tier-3 conversion (#649-#653) — high-yield, но post-hoc.
60. `[JT]` `milestone_hierarchy_v3` (2026-05-08) — clean, но predecessor v2 superseded <30d.
61. `[J]` CONTEXT.md stash/restore per-iter ritual — не hook.
62. `[JT]` Architecture-sweep-on-milestone-close trigger — surfaced, не load-bearing (M#38 drifted).
63. `[J]` Sibling-grep selective adoption — applied #631/iter:42, не applied installer hotfix burst или telegram CRLF/BOM pair.

---

## GOOD (~95)

### Memory & Cognitive

1. `[JT]` SessionStart hook делает inject данных, не инструкций (PR commit 4487da8) — устранил "model ignored 5 parallel recall" failure mode.
2. `[JT]` mcp-memory server v2 — server-side pgvector + HNSW + RRF + maxResultSizeChars — 7 improvements, all live.
3. `[J]` Always-loaded context budget compression — 42KB→12.4KB session-context, principle still cited.
4. `[JT]` **Three-way split CLAUDE.md / SOUL.md / CONTEXT.md (PR #492)** — единственное structural решение, не reverted.
5. `[JT]` Phase 5.2 A-MEM neighbor evolution trio (#231/#233/#236) — weekly cron + apply/rollback + Haiku evolver live.
6. `[JT]` `memory_management_strategy_v1` — PreToolUse dedup + UserPromptSubmit recall + always_load, все три механизма live.
7. `[JT]` /reflect comm_patterns extractor + Stop hook + backfill (PR #584) — 63 unit-теста + live qwen3 E2E.
8. `[JT]` Sycophancy eval harness M43 (PR #697) + /grill third-person framing (PR #695) + /research 4-channel intake (PR #696) + /grill CRITIC subagent (PR #698) — все TDD-mode, shipped 2026-05-17.
9. `[J]` Recall-before-deciding rule в user-level CLAUDE.md (Tier 1) — three-pass recall load-bearing.
10. `[JT]` Brief-mode → UUID map + `record_decision` contract — schema-aligned (UUID не slugs).
11. `[JT]` `memory_store` JSON-envelope (#658 → PR #677) — структурированный stored/action/memory_id, idempotency invariant codified.
12. `[JT]` always_load purge 23→1 + Engineering Posture inline + #641 root-cause tracker — symptom + structural ticket pattern.
13. `[JT]` `autonomous_chain_synthesis_template` (Tier 5 memory, iter:39) — 190-line runbook reused across iters 40-58.
14. `[JT]` /grill chain canonical (/reason → /grill → /to-prd → /to-issues → /implement|/delegate) — M43 grilled этим путём, 6 slices.
15. `[J]` PreToolUse hook блокирует empty `memories_used` (Tier 2) — iter:33 dogfooded live.
16. `[JT]` Outcome→issue Tier-3 channel (iter:15-19) — 5-for-5 yield в окне (#649-#653).
17. `[J]` iter:43-46 substance-drift class bounded (#664/#665/#666/#667) — reusable mitigation matrix.

### Skills & Workflow

18. `[JT]` /implement vs /delegate split (PR #276, 2026-04-21) — load-bearing в каждой multi-issue сессии.
19. `[JT]` `grill_me_record_decision_gate` (2026-05-03) — UUID-not-name hard rule, dropped M#42/M#43 clean 11-decision sessions.
20. `[U]` CLAUDE.md "Skills are a contract, not a trigger" — auto-invoke /implement after PR merge без re-prompt.
21. `[J]` TDD-mode свёрнут в /implement и /delegate (PR #598/#599) — beat /tdd standalone, демонстрировано clean в #695/#698 (39 assertions).
22. `[U]` `improve_orchestrator_grill_abandoned_2026_05_06` lesson — meta-rule "rebuild conceptually-wrong, не iterate".
23. `[JT]` /grill финальная форма (PR #695 + #698) — 3-rd-person + assumption verbalization + CRITIC.
24. `[JT]` /reason скилл (PR #686) — заполняет intuition-stage gap перед /grill, prior-art sweep сделан.
25. `[U]` CLAUDE.md canonical chain — workflow без оркестратора.
26. `[JT]` /to-prd + /to-issues vertical-slice — M#42 + M#43 (5 + 6 slices), decision UUID referenced не restated.
27. `[J]` /end --quick flag form (PR #575) — resolved 27-day mistake.
28. `[JT]` CONTEXT.md auto-load + organic growth через /grill — no batch friction.
29. `[JT]` /verify outcome verification carved out (PR #144) — clean naming.
30. `[J]` AFK-chain synthesis-template extraction (iter:39) — template reuse без spawning skill.
31. `[JT]` `milestone_hierarchy_v3` — "epic" killed (decision 2a7ae10e), no /epic скилл добавлен.
32. `[U]` `skill_proliferation_antipattern` global feedback — gravity rule, частично нарушается но load-bearing.
33. `[JT]` CLAUDE.md skill routing table — single source of truth, обновляется в той же PR что и скилл.
34. `[J]` /improve-codebase-architecture reframed from /repo-improve — per-repo deepening + CONTEXT.md/ADR aware.

### Architecture

35. `[JT]` HYBRID federation + orchestrator-worker (2026-04-22) — load-bearing через окно, MAST-backed.
36. `[U]` **`caution_vs_overconfirmation_principle` (2026-04-28)** — most-leveraged principle of window: 3 surgical fixes (C16/M3/C2) за 24h, lens для всех gate-design.
37. `[JT]` `architecture_growth` UP/DOWN — survives unchanged до 2026-05-16.
38. `[JT]` `milestone_hierarchy_v3` + always_load — superseded 3 prior memories clean.
39. `[U]` Pillar = narrative, не structural (direction 2, 2026-04-28) — устранил 3-таксономию ambiguity, dropped 1 & 3.
40. `[J]` Capabilities (C1-C18) × 5 layers × tier ABC — single structural taxonomy, survived audit rounds.
41. `[J]` C17 single-substrate events — "substrate-as-truth", composition by read/write.
42. `[J]` Memory split: facts (bi-temporal) + episodes (append-only) — закрывает "owner hand-mines outcomes" pattern.
43. `[U]` Semver reframe (v2 = paradigm shift, current = v1 stabilization) — killed bottomless v3/v4 planning.
44. `[J]` Pillar 7 Sprint 2 dispatcher (milestone #21, 8/8, 2026-04-22) — first UP-layer live, first federation jurisdiction.
45. `[J]` Persistent-agent foundation (LangGraph + Ollama + Postgres checkpointing) Sprint 1 — substrate everything builds on.
46. `[J]` **Sandcastle subsystem (slices 1-6, 10)** — coherent rollout, watchdog + RLS + multi-tier; закрыл worktree-isolation failure class.
47. `[J]` RLS provenance gate (PR #570) — DB-level boundary, не prompt-level.
48. `[J]` Decision-gating: canonical `gate()` consulted per tool call — закрывает 3-way drift SOUL/safety.py/skill prose.
49. `[J]` C16 specialized reviewers + different-provider + subagent-fabrication detection first-class.
50. `[J]` Tier-2 hook `record_decision` без `memories_used` (PR #577) — mechanical Tier-1 escalation.
51. `[J]` Federation phase 0 installer (#336) + ~/.claude/ migration — multi-device base.
52. `[U]` `pillar7_phase2_six_choices` decision-log pattern — 6 Yes/No + revisit triggers, reused in `audit_3_main_changes_lock`.
53. `[JT]` `distribution_test` ("abstractions need 2 implementations") — предотвратил over-eager harness-adapter.
54. `[J]` Engineering principles anti-vibe (PR #493/#495) — Plan/Execute/Clear, vertical slices, deep modules.
55. `[J]` AFK dispatch pre-gate (PR #687) — refuses AFK на missing artefacts (#642).

### Infra & Ops

56. `[J]` **Meta-test rule for path-filtered guards (#326 → PR #365)** — самое сильное infra durable improvement окна, класс #289/#310/#311 не recur silently.
57. `[J]` `ci-meta.yml` NOT path-filtered — self-undermining avoidance.
58. `[J]` schema-drift-check points at canonical `mcp-memory/schema.sql` (PR #311).
59. `[J]` schema.sql + migration pairing enforced (PR #293) + `mem:schema_sql_requires_paired_migration`.
60. `[JT]` Telegram via Anthropic Channels plugin (PR #89) — outlasted bespoke bridge на 7+ недель.
61. `[J]` gitleaks pre-commit + CI (PR #135) — solid security baseline в каждом PR.
62. `[J]` `.claude-userlevel/` migration + deep-merge `.mcp.json` (PR #345/#347) — federation foundation.
63. `[J]` setup-device claude.cmd via `shutil.which` (PR #521) — fixed #486 root + sibling-grepped subprocess('claude',…) (PR #520).
64. `[J]` `[no-issue]` commit-msg regex (#329) + `priority:critical` PR-body (#424) — hotfix escape valves.
65. `[J]` Sandcastle Slice 1 (PR #550) — opened architecture, landed M#38 12/12 by 2026-05-13.
66. `[J]` Sandcastle Slice 2 (PR #561) — memory MCP bridge in container + skills baked.
67. `[J]` CONTEXT.md sandcastle glossary + threat-model-duality (PR #562).
68. `[J]` PR #569 `SUPABASE_SERVICE_KEY` preference на host before RLS — correct ordering, no write outage.
69. `[J]` Watchdog hardening (PR #614) — Invoke-Sandcastle refactor, 65/65 tests, generalises `ps_native_exe_errors_need_lastexitcode`.
70. `[J]` Sandcastle prompt.md guard + pygrep hook + 12-case meta-test (PR #626) — chain-of-workarounds ended on OUR bug.
71. `[J]` Workshop Ollama benchmark (PR #627) — 14b primary, 7b downgrade tier, hardware-grounded.
72. `[J]` Sandcastle Task Scheduler + Register-SandcastleTask.ps1 (PR #628/#629) — cross-repo to redrobot.
73. `[J]` comm_patterns paired migration + meta-test + ADR 0004 (PR #583).
74. `[J]` `session-context.py` milestone-architecture-sweep signal — reads GH state, not static markers.

### Process

75. `[JT]` `check_pr_scope_fit_at_open_time` — `gh pr diff --stat` at PR-open (2026-04-20).
76. `[JT]` `subagent_fabrication_commit_message_vs_diff` — `git diff` over commit-msg trust.
77. `[JT]` `design_rfc_not_pr_channel` (2026-04-26) — RFC → Discussions, decisions → memory.
78. `[JT]` `stacked_pr_delete_branch_closes_chain` — 3-strike record, pre-merge reflex.
79. `[JT]` `drive_by_branch_pull_main_first` (2026-04-30) — concrete cost data.
80. `[JT]` `subagent_acceptance_criteria_dodged_as_out_of_scope` — 3-incident lesson.
81. `[J]` `untracked_main_tree_leaks_into_subagent_worktree` — concrete recovery recipe.
82. `[J]` `copilot_review_run_tests_before_fix` — asymmetry sharp.
83. `[JT]` CI meta-test convention для path-filtered guards — codified after #289/#310/#311.
84. `[JT]` `.pre-commit-config.yaml` commit-msg regex (#329) — blocked orphan commits на hook layer.
85. `[J]` Outcome-records as recurrence ledger — iter:48-58 ledger across iters.
86. `[J]` Watchdog tick closed orphan milestone #38 (2026-05-17) — caught violation.
87. `[J]` TDD-mode subagent #689 branched clean from origin/main — gold standard для batch-mates.
88. `[J]` /triage verify-before-status-ready (iter:9, PR #646) — closes loop on #486.

---

## Meta-наблюдения (cross-cutting)

### 1. Recall-before-action — доминирующий failure mode 90 дней

Always_load silt-up, `record_decision` post-hoc, 2026-05-17 batch ударил 3 pre-existing memory classes одновременно (`parallel_delegate` / `untracked_main_tree` / `AC_dodged_as_out_of_scope`). #641 — единственный structural fix, остальное симптоматика.

### 2. Re-decision pattern: тот же name flip'ается внутри 30 дней

/reflect (rejected → reintro), /end-quick (split → flag), /grill-* (3 → 1), /tdd (shipped → removed), milestone_structure v2 → v3, "owner"→"user", "epic" dropped. ~12 wasted decision pairs. Cooling-off-gate на `record_decision` когда existing decision with same domain+name есть, был бы полезен.

### 3. Skill churn 4× прироста vs зафиксированный antipattern

v1.5 plan "6+1" → live ~25. `skill_proliferation_antipattern` memory existed весь период но проигрывала локальному "fix-it" рефлексу. /grill наконец работает circuit-breaker'ом (M#42/M#43 chain ушёл без post-hoc record_decision).

### 4. Subagent dispatch — главный failure surface мая

4 partial/failure outcomes за 2 недели (#665+#662 wholesale, #690+#691 contamination, #687 hijack). Quality non-deterministic per identical contract (#689 vs #690+#691 same-day). Argues за orchestrator-side verification primitives, не subagent-side prompt-tightening.

### 5. Каскад abandoned PR 2026-04-20 (#243/244/245/255)

Over-decomposition memory features. 4 sibling-PR умерли вместе. Missing grouping milestone — exactly то что `phase_split_pattern_memory_overhaul` предупреждает.

### 6. Sandcastle = redemption arc от worktree isolation failure 2026-04-20

Incident прямо мотивировал 6-slice sandcastle rollout (PR #550-#629). Architectural learning loop замкнут.

### 7. `caution_vs_overconfirmation_principle` (2026-04-28) — самый leverage'нный принцип квартала

Сгенерировал 3 surgical fix'а за 24h (C16/M3/C2), всё ещё цитируется как gate-design lens.

### 8. Pivot clusters: 2026-04-21/22 и 2026-04-27/28

Две grill-driven decision storm'а произвели почти всю durable architecture: persistent-agents, hybrid reframe, six-choices, redesign complete, pillars dropped, terminology pivot, M3 split.

### 9. Cross-device codegen — architectural, не contextual

72% cross-device misses на собственном устройстве (Petr=29/46) — паттерн "генерация неагностичного кода для ДРУГИХ устройств", не "забыл что я на чужом". Rule 3 из reflect — правильная рамка.

### 10. Schema-asymmetry classes silently rot

`outcome_record.memory_id` vs `record_decision.memories_used` (#660), `memory_review_queue.status` (Phase 4), classifier supersession race (#194), rewriter types as hard filter (#207). Common shape: документация в 3 местах, ни в одном из которых агент не смотрит при написании call'а.

### 11. AFK-chain self-observation > interactive grilling

iter:43-58 произвёл 16 трекеров, 4 синтезов, 2 reusable memory template'а — и поймал #669 XML-strictness recurrence (N=6) которое interactive сессии не заметили. Chain'ы instrumental'ят свою дисфункцию.

### 12. Tier 1 (prompt rule) → Tier 2 (mechanical hook) escalation работает

PR #577 `record_decision` gate. Friction (XML-strict) реальный но safety value выше.

### 13. installer.py — слабое звено

11 PR за 3 недели, hotfix burst 2026-04-27→2026-04-29, recursion-bug #659. Pattern bad-foundation о котором CLAUDE.md предупреждает. Sibling-grep не применяется.

### 14. Sycophancy harness M43 + identity-layer paradox

Все 3 M43 mechanism slice'а (#689/#690/#691) приземлились 2026-05-17 с TDD-mode. Counter-finding: heavy personalization (SOUL.md + always_load) measurably increases sycophancy — identity layer работает против pushback.

### 15. Actor distribution

Из ~250 dedupe-items: `[U]` ≈12% (стратегические повороты, generative principles), `[J]` ≈70% (execution choices, mechanical drift), `[JT]` ≈18% (grill-driven design decisions). Большинство GOOD-items с `[JT]` меткой — joint grill-сессии дают highest leverage.

---

## Открытые вопросы для следующей сессии

Эти всплыли в ходе аудита и требуют решения:

1. **#641 recall-quality** — единственный structural fix против recall-before-action. Что блокирует?
2. **`decisions_belong_in_memory_not_gh_issue_bodies`** — упомянуто в CLAUDE.md, нет в memory store. Создать или поправить ссылку?
3. **Cooling-off-gate на `record_decision`** — нужен ли механизм блокирующий re-decision на тот же domain+name внутри 30 дней?
4. **Orchestrator-side subagent verification primitives** — вместо tightening дочерних промптов. PR #687 — начало, что дальше?
5. **installer.py hardening sprint** — 11 PR за 3 недели, recursion-bug. Стоит ли изолировать как отдельную milestone?
6. **Architecture sweep после M#38** — рекомендация ещё не закрыта, M#38 закрылся watchdog'ом. Когда?
7. **`pending_grill_orchestrator_role_and_scope`** — самый высокий unresolved foundation Q ("orchestrator = dumb dispatcher vs Jarvis's smart head").
8. **Sycophancy paradox** — что делать с identity-layer trade-off? M43 harness меряет, но интервенция?

---

## Cross-references

- **Source memory:** `decision_calibration_audit_2026_05_18_90d` (reference/jarvis).
- **Subagent raw dumps:** `C:\Users\petrk\AppData\Local\Temp\claude\C--Users-petrk-GitHub-jarvis\ed06ccc7-4759-44b1-88f7-08da7ef13086\tasks\*.output` (5 файлов).
- **gh data:** `C:\Users\petrk\.claude\projects\C--Users-petrk-GitHub-jarvis\ed06ccc7-4759-44b1-88f7-08da7ef13086\tool-results\{prs-90d.json,issues-90d.json,prs-closed-not-merged.json,mcp-memory-outcome_list-*.txt}`.
- **/reflect snapshots:** `C:\Users\petrk\.cache\jarvis-comms-analysis\merge_2026-05-17\report_2026-05-17.md` (cross-device 30d) + три per-device 2026-04-30.

---

## Corrections (2026-05-18, post-verification)

Verified two findings in same-day follow-up session. Two audit items are wrong; recorded here so future sessions don't lean on them.

- **BAD #72 (`decisions_belong_in_memory_not_gh_issue_bodies` отсутствует в memory store) — FALSE ALARM.** Memory exists at `project=global`, UUID `bad45319-36b9-4e3a-86d4-8809be68235c`, created 2026-04-22, content full (Rule + Why + How to apply). Active references by literal name in CLAUDE.md / SOUL.md / CONTEXT.md / live skills: zero — only in `.bak.orphan/SKILL.md`. CLAUDE.md describes the *concept* without naming the memory. No "ghost reference" — audit conflated concept-mention with name-binding.

- **GOOD #74 (`session-context.py` milestone-architecture-sweep signal — reads GH state) — NOT IMPLEMENTED.** Re-read `scripts/session-context.py` (626 lines). Greps for `sweep`, `milestone`, `closed_at`, `capability`, `deepen`: all empty. The trigger mechanism described in CLAUDE.md ("Architecture sweep at milestone close") is **specification-only**, not shipped. Demote from GOOD; classifies as a doc-vs-code drift bug (CLAUDE.md claims as shipped behavior). M#38 (closed 2026-05-17, 12/12) did not surface the recommendation because the code path doesn't exist. Manual `/improve-codebase-architecture` runs work; auto-surfacing does not.

**Consequence for "Открытые вопросы для следующей сессии" §6 (Architecture sweep после M#38):** the answer "когда?" — manually in a fresh session, now. Adding auto-trigger is a separate grill candidate (touches user-visible SessionStart output, crosses non-trivial code, needs tests for the dedup-since-`closed_at` logic).
