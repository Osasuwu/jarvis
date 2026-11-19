---
topic: storytold-oracles-cleanroom-supply-chain-main-health
tags: area:process, research
source_provenance: /research invocation in session b065a837 — fifth run, the second of two covering the next runs proposed in docs/research/storytold-project-side-2026-11-18.md (PR #2235)
status: open
audit: 2026-11-19 — 204 claims: 176 SUPPORTED, 27 PARTIAL, 1 UNSUPPORTED, 0 UNCHECKABLE
---

## Question

The user, verbatim, quoting the earlier report's list of questions not yet asked, which ended with "Как 543 внешних автора узнают правила, и что это значит, если у redrobot появятся новые участники.":

"вот эти ещё не посмотрели. И теперь по новой инфе можно ещё попробовать вопросы задать, которые с их проектов получится узнать

Грилл чуть позже, пока инфу собираем, откладываем как вход на грилл"

The list has seven questions, and the user asks for new ones on top. A run takes at most four sub-questions, so they are split into two runs, done in parallel. This run takes three from the list (test oracles, clean-room and licensing, supply chain) and one new question drawn from the latest information. Our third run measured redrobot's red-main baseline (`docs/research/ci-red-main-baseline-and-relaxation-options-2026-11-18.md`, PR #2237); the open counterpart is how healthy main stays at storytold, where CI is advisory. The companion run `storytold-contribution-scale-rules-sync-autocraft-2026-11-18` takes the other four list questions. The /grill the user deferred is not part of either run; both feed it.

Sub-questions:
- Q1 — reference corpora and parity floors as test oracles, and whether redrobot can use recorded robot runs the same way;
- Q2 — clean-room and licensing discipline when an agent studies a reference product;
- Q3 — storytold's shared security and supply-chain checks against our gitleaks and minimum release age;
- Q4 — (new) how healthy photocraft's main is under advisory CI, measured with the same method as our redrobot baseline.

## Summary

**Main health under advisory CI (Q4, new).** On the same method as our redrobot baseline, photocraft's main is red far more than redrobot's master: 94 of 196 main commits red by the whole check rollup, red 61% of the time, and 58 of 192 red counting the shared gate job alone, 32% of the time [C402], [C403], [C431]. It swings by window, from 3% to 42% gate-red [C404]. A typical red streak lasts about an hour, but one ran 25 hours after a framework port, and 24 commits merged through it, 16 PRs in 23 minutes [C408], [C409], [C410], [C432]. The cause mix is the reverse of redrobot's: 6 of 9 sampled streak starts were deterministic — a compile error, lockfile drift, stale generated files, tests on renamed labels — mostly interaction between merges or generated files going stale between merges [C412], [C413], [C414], [C419], [C433]. photocraft never reverts; every traced streak ends with a named fix-forward PR, the longest after about a day, and no rule in AGENTS.md covers red main, retries or quarantine [C420], [C421], [C426], [C427], [C429]. A red main reaches every open PR: in October one issue counted 194 of 489 open PRs failing for main's reasons [C424]. In short, advisory CI at storytold's volume buys throughput at the price of a main that is often red and fixed by hand. Main almost never lacks a result, because CI runs on every push to main [C411], [C434].

**Reference corpora as test oracles (Q1).** photocraft's PSD corpus is files storytold generates in Photoshop by script, pinned by commit and sha256, compared against Photoshop's own composite within 2/255 per channel; CI always runs it [C101], [C103], [C108], [C109]. The test asserts no crashes plus pass counts at or above raise-only floors per source, and the Photoshop floor rose from 133 to 190 in ten days with no decrease in the commits read [C111], [C112], [C113]. Wrong references are kept with a reason rather than deleted [C115], [C116], [C119], [C171]. The menu-parity floor counts wired commands, not behaviour; fidelity rests on the corpus [C124], [C128]. Outside sources name the same limits: regenerating a snapshot over a bug records the bug, and a regression oracle assumes the old version was right [C133], [C140]. redrobot already has the pattern in miniature — a committed trace catalog with a hardware/mock flag, per-trace tolerance, comparison by travelled path, verbatim-flagged controller envelopes, and measured controller hypotheses re-checked in CI [C154], [C155], [C156], [C157], [C158], [C164], [C169]. The gap is volume: one hardware trace, no tools, no MovC with rotation, no alarms [C159], [C160], [C167]. Its level-1 leveling golden came from the engine's own run, so a physics bug present at blessing passes forever [C148], [C172]. Replay through the mock checks the controller model, not new motions far from the recording [C170]. **Recommendation:** treat robot days as corpus capture — same-day commit of verbatim wire-logs and traces, a raise-only floor over hardware-trace passes, a known-bad list with reasons, and a progression set for traces the mock cannot match yet [C173].

**Clean-room and licensing (Q2).** storytold has a written clean-room procedure for file formats in craft-libs: assumptions written before any reading and never edited, a log of every URL and search, a frozen format before implementation, a never-consult list, and a contamination rule [C224], [C225], [C226], [C227], [C228], [C229], [C230]. It is a single-team logged derivation, not the classic two-team split [C233]. App look and behaviour rest on short rules with no procedure or record — learn from behaviour and public specs, copy no code, assets, strings or artwork — plus a licence allowlist, ATTRIBUTION.md and a naming rule, while photocraft's guide reuses the reference app's menu ids and shortcuts [C201], [C202], [C203], [C207], [C210], [C234]. Legally a clean room is best practice, not a requirement; formats and functionality are free, manual wording is not [C241], [C243], [C244]. The chardet 7.0 relicensing showed that an agent's prior exposure is the open question, and no storytold rule read addresses training-data exposure [C245], [C246], [C249]. jarvis and music-intel-mcp are MIT, redrobot has no licence file, and attribution of outside material is ad hoc [C235], [C236], [C239].

**Supply chain (Q3).** No storytold shared security or supply-chain check blocks a merge: main requires a PR with zero approvals and no status checks, the SBOM-and-signing workflow is opt-in and uncalled, SonarCloud does not wait on its quality gate, and no sampled CI checks Rust advisories [C303], [C304], [C312], [C322], [C324]. Third-party actions are SHA-pinned, but 138 workflow files call the org's own shared workflows at @main, release jobs with signing secrets included, so one merged zero-approval PR to that repo runs everywhere [C317], [C318], [C320], [C321], [C363]. jarvis is stricter: gitleaks and ruff required, everything SHA-pinned including its own lanes, a 7-day cooldown on Dependabot and uv [C340], [C342], [C343], [C350]. Its gaps: Dependabot security updates and alerts are off, so the cooldown's security bypass does not reach it; no advisory lookup; CI installs uv unpinned [C346], [C347], [C348], [C349]. music-intel-mcp's gitleaks is not required [C352]. redrobot has a well-hardened gitleaks but no branch protection, weekly-only audits, no Dependabot and 46 tag-pinned actions [C354], [C356], [C357], [C358]. Outside data supports a week-long cooldown for most attacks — 8 of 10 had windows under a week — with known long-game exceptions [C333], [C334], [C332].

## Findings

### Q1 — Reference corpora and parity floors as test oracles, and recorded robot runs in redrobot — answered with a gap

- **C101** [quoted] Corpus PSDs are made in Photoshop by storytold's own scripts and tests compare against Photoshop's stored rendering, file by file — "Each file stores Photoshop's rendering of itself, and PhotoCraft's tests compare their output with that rendering, file by file." — [S1], header
- **C103** [quoted] Apps fetch the corpus at a pinned commit plus sha256 manifest — "so test results can't change without a reviewed pin bump." — [S1], What this is
- **C104** [quoted] Only generator-made files are allowed — "Hand-made, downloaded or found files don't belong here." — [S1], Adding files, 1
- **C105** [quoted] Regeneration is not byte-identical, so files are regenerated only when the set changes — "The output has the same content each time but is not identical byte for byte, because Photoshop writes fresh document ids, timestamps and XMP." — [S1], Regenerating
- **C106** [quoted] A pin bump reruns corpus tests and raises floors in the same PR — "Never lower a floor silently." — [S1], Pinning workflow, 3
- **C108** [quoted] CI always runs the corpus job; opted in locally, a missing corpus fails rather than skips — "With the feature on, a missing `corpus/photoshop` is a failure, never a silent skip." — [S1], Using this from PhotoCraft
- **C109** [quoted] Tolerance vs Photoshop's composite is 2/255 per channel (round trip 1/255) — "const PASS_TOL: f32 = 2.0 / 255.0;" — [S2], line 68
- **C111** [quoted] The run tolerates unrendered features and asserts only no crashes plus pass and round-trip counts at or above per-source floors — "the run asserts no crashes, and that the oracle pass count and the export" — [S2], module doc
- **C112** [quoted] Photoshop-set floors: 190 passes, 258 round trips of 258 files — "pass_floor: 190, roundtrip_floor: 258" — [S2], line 159
- **C113** [measured] The Photoshop pass floor rose 133 to 190 between 2026-10-13 and 2026-10-22, with no decrease in the commits read — Own measurements, L1-M2
- **C114** [quoted] Concurrent PRs raising one floor: the later one takes the measured total — "Whichever lands later should take the measured total." — [S3], body
- **C115** [quoted] Known-invalid upstream files are listed with a reason — "Files known to be invalid upstream: their parse error is expected." — [S2], KNOWN_BAD
- **C116** [quoted] A thumbnail-oracle failure may be the reference's fault — "a thumbnail DIFF may be the thumbnail's fault" — [S2], module doc
- **C117** [quoted] When an older scripted Photoshop measurement contradicted six corpus oracles, the PR dropped that row and asked where it was measured — "That row keeps 128 at 128, which needs pivot 128 and disagrees with all six oracles above" — [S4], body
- **C118** [quoted] The generator itself once used a wrong Photoshop key — "after `onPath` turned out to be wrong." — [S1], How it was generated
- **C119** [quoted] A known model gap (GIMP linear vs gamma compositing) is kept as measured files, not dropped — "the default ones measure the known gap between the two." — [S1], gimp/
- **C120** [quoted] Only the read direction is oracle-checked — "The write direction has no Photoshop check yet" — [S5], body
- **C121** [quoted] The write-recipe check uses PhotoCraft's own importer — "These checks use PhotoCraft's own importer and inspector; they do **not** prove that" — [S6], PSD write recipes
- **C122** [quoted] The Photoshop-authored oracles contain no noise-gradient fills; the 22 occurrences found are all in the psd-tools and ag-psd sets — "The `photoshop/` oracles have none." — [S7], body
- **C123** [quoted] Corpus findings become committed synthetic tests — "Synthetic reproductions of corpus findings live in" — [S6], Rendering fidelity
- **C124** [quoted] FLOOR counts live Photoshop menu items (663), raise-only — "Raise it when parity grows; never lower it." — [S8], FLOOR doc
- **C125** [quoted] The test also fails if the catalog shrinks — "assert!(p.total > 500, \"catalog shrank: {}\", p.total);" — [S8], parity_does_not_regress
- **C126** [quoted] Parity = share of the menu catalog wired live — "Photoshop menu parity: how much of [`crate::menu_catalog::CATALOG`] is live." — [S8], module doc
- **C127** [measured] FLOOR went 604 to 663 with no decrease in 16 commits; the catalog grew from 625 items (2026-10-03) to 664 — Own measurements, L1-M1, L1-M3
- **C128** [inference] The menu floor measures wiring, not behavioural fidelity; fidelity rests on the corpus — from [C109], [C126]
- **C129** [quoted] AGENTS.md tells agents to raise FLOOR in `crates/ui-egui/src/parity.rs` — "When parity rises, raise `FLOOR` in `crates/ui-egui/src/parity.rs` (never lower it)." — [S9], line 144
- **C130** [measured] That path is 404; the file moved under menus/ on 2026-10-26 — Own measurements, L1-M6
- **C131** [inference] Floors are counts, so a change can lose one passing file and gain another unseen — from [C111], [C112]
- **C133** [quoted] Updating over an unfixed bug records the bug — "we would need to fix the bug before re-generating snapshots to avoid recording snapshots of the buggy behavior." — [S10], line 82
- **C134** [quoted] Reflexive regeneration is the habit to fight — "fight against the habit of regenerating snapshots when test suites fail instead of examining the root causes of their failure." — [S10], Best practices
- **C136** [quoted] Exact-match snapshots are brittle — "Because tests have to match the saved output exactly, even tiny changes count as failures." — [S11], brittleness
- **C137** [quoted] The remedy offered is human review — "The remedy is to rely on human review" — [S11], brittleness
- **C139** [quoted] WPT fuzz can be a range, so a too-small difference also fails — "In this case the maximum pixel difference must be in the range" — [S12], Fuzzy Matching
- **C140** [quoted] A regression oracle assumes the previous version is correct — "It rests on the implicit assumption that the previous version can serve as an oracle for existing functionality." — [S13], Barr et al. 2015, 5.3
- **C141** [quoted] Open-loop re-simulation pins the system to recorded positions — "so the position of the autonomous system in the re-simulation is fixed to the position in the original drive data file." — [S14], Log re-simulation
- **C142** [quoted] Closed-loop re-simulation degrades as behaviour diverges from the log — "it can become inaccurate if the behavior of the re-simulated autonomous system diverges too much from the behavior in the original drive data file." — [S14], Log re-simulation
- **C143** [quoted] Open-loop replay cannot react to changed behaviour — "As open-loop log replay is unable to respond to differing stack behavior, it cannot evaluate how motion planning and control systems would have behaved" — [S15], Open-Loop Log Replay
- **C144** [quoted] Unsolved cases go to a separate progression suite — "programs can add it to a progression test suite that evaluates the stack’s progress toward aspirational goals." — [S14], issue does not re-appear
- **C146** [quoted] Tier 2 (simulation, golden baselines) requires golden/replay tests — "Golden/replay tests are mandatory." — [S16], Research Tiers
- **C147** [quoted] The level-1 golden hashes the sand map after replaying strokes; a physics edit needs re-blessing — "A physics edit therefore turns this tier-2 test red and needs an explicit re-blessing." — [S17], module doc
- **C148** [quoted] The golden came from the engine's own run, not hardware — "must equal the recorded one, which came from the engine's own run, not from this replay." — [S17], module doc
- **C149** [quoted] Re-blessing is copying JSON from the runner log — "that JSON from the log of the self-hosted runner's ``pr-fast`` run into ``golden/``." — [S17], module doc
- **C150** [quoted] A tolerance at level 1 was rejected; bitwise equality is the criterion — "Допуск (allclose) на уровне 1 — отказ: побитовость — сам критерий продвижения." — [S18], alternatives
- **C152** [quoted] The envelope corpus exists because unit tests check invented rules, fixtures check what the controller sent — "проверяет правило, которое я *придумал*. Фикстура проверяет форму, которую" — [S19], intro
- **C153** [quoted] Robot day 2026-07-26 lost three day-blockers to that gap — "контроллер *прислал*. Робот-день 2026-07-26 стоил трёх day-blocker'ов подряд" — [S19], intro
- **C154** [quoted] Envelopes carry a verbatim flag; the 07-26 ones are reconstructed — "Конверты робот-дня 2026-07-26 идут с `verbatim: false`: wire-log (#1736/#1737)" — [S19], verbatim
- **C155** [quoted] A committed trace catalog exists after 2026-06-22 runs were lost to a gitignored folder — "`.gitignore`** и обязан таким остаться — прогоны 2026-06-22 писались в" — [S20], intro
- **C156** [quoted] Origin hardware vs mock bounds what a trace proves; a mock trace guards only regression — "построению воспроизводит H, и сравнение с ним проверяет отсутствие регрессии," — [S20], origin
- **C157** [quoted] Tolerance lives per trace: poll step, controller accuracy, run cleanliness — "`tolerance` живёт в записи, а не константой в коде: допуск складывается из шага" — [S20], sidecar
- **C158** [quoted] Traces are aligned by travelled path, not time — "Почему сравнение идёт по **пройденному пути**, а не по времени: время в трейсе" — [S21], module doc
- **C159** [quoted] The one hardware trace is matched within 0.029 deg / 0.038 mm vs 2 deg / 5 mm; wrong hypotheses miss by 180 or 7.8 deg — "под `slerp` — 7.8°, так что допуск различает гипотезы." — [S20], catalog state
- **C160** [quoted] It does not cover tools, MovC with rotation or alarms — "Чего этот трейс не покрывает: инструмент (только фланец, tool 0), MovC с" — [S20], catalog state
- **C161** [quoted] The trace was first held out: a mock frame bug would fail it under any law — "Из-за этого первый hardware-трейс НЕ положен в каталог паритета (тест был бы красным" — [S22], section 5
- **C163** [quoted] A recorded J6 limit was a harness-timeout artifact (wrong reference) — "артефакт фиксированного таймаута нашей обвязки при длинном возврате на 6% скорости," — [S22], section 2
- **C164** [quoted] Measured controller hypotheses need trace and tolerance, re-verified every CI run — "`trace` and `tolerance` are required, and a verifier in" — [S23], header
- **C165** [measured] Registry: 6 measured, 8 uncharacterized — Own measurements, L1-M4
- **C166** [quoted] Decision: mock-robot divergence is fixed by parity, not by a document — "Правило шире #3144: расхождение мока с роботом чинится паритетом, а не документом." — [S24], Почему
- **C167** [measured] 2 catalog traces (1 hardware), 11 envelopes, 3 robot-day folders; the 08-08 report lists 10 divergences — Own measurements, L1-M5
- **C168** [inference] storytold regenerates references by script on demand; redrobot gets references only on robot days, so its corpus grows per site visit — from [C104], [C105], [C153], [C167]
- **C169** [inference] redrobot already has the corpus pattern in miniature (committed refs, provenance flag, per-record tolerance, fail on missing); the gap is volume and coverage — from [C154], [C155], [C157], [C159], [C160], [C167]
- **C170** [inference] Replaying robot runs through the mock checks the controller model; it cannot judge new motions far from the recording — from [C141], [C142], [C143], [C158], [C159]
- **C171** [inference] Both meet wrong references (recording artifacts, convention mismatches); storytold keeps its known-bad files listed with a reason, and redrobot held its first hardware trace out of the catalog with the reason recorded — from [C115], [C116], [C119], [C161], [C163]
- **C172** [inference] The level-1 golden is a pure regression oracle: a physics bug present at blessing passes forever — from [C133], [C140], [C147], [C148]
- **C173** [inference] Robot runs as oracle needs: same-day capture with verbatim wire-logs, a raise-only floor over hardware-trace passes, a reasoned known-bad list, and a progression set for unmatched traces — from [C106], [C115], [C144], [C154], [C164], [C169]
### Q2 — Clean-room and licensing discipline when an agent studies a reference product — answered with a gap

- **C201** [quoted] The suite-wide Rust house rules (copied into photocraft AGENTS.md from craft-contrib standards/house-rules-rust.md) carry a one-sentence clean-room rule: learn from behaviour and public specs, copy no code, assets, strings or artwork — "2. **Clean room.** Learn from observed behaviour and public specifications. Do not copy another product's code, assets, strings or artwork. Check a dependency's licence before adding it." — [S25], Rust Craft repositories block, rule 2
- **C202** [quoted] The same block requires every asset be original or suitably licensed and recorded in ATTRIBUTION.md in the same change; fonts live in a separate repo — "3. **Assets and fonts.** Every asset is original or suitably licensed, and is recorded in `ATTRIBUTION.md` in the same change." — [S25], Rust Craft repositories block, rule 3
- **C203** [quoted] storytold keeps an SPDX licence allowlist for dependencies and assets (ISC, MIT, BSD-2/3, Apache-2.0, OFL-1.1, CC0, CC-BY, CC-BY-SA and others); a repo may shorten it but not extend it locally — "An expression is allowed when every identifier is in this list. A repository may name a shorter list. It may not add an identifier here by editing its own copy of these rules." — [S25], Licence allowlist
- **C204** [quoted] Licensing outside the allowlist is one of the few things an agent must stop and ask about — "9. **Stop and ask only about** licensing outside the allowlist, publishing, releases, a new remote, secrets, spending money, destructive git, and anything else hard to undo." — [S25], House rules (core), rule 9
- **C205** [quoted] photocraft's own rule names the reference products, scope (behaviour and look only), forbidden artefacts (code, shaders, profiles, assets) and permitted sources (named public specs and papers) — "We studied Photoshop and other proprietary editors for *behaviour and look only*. Never copy their code, shaders, profiles or assets." — [S25], photocraft rules, rule 3 (line 118)
- **C206** [quoted] photocraft requires third-party assets to keep their licence file next to them and get an ATTRIBUTION.md row with path, title, author, source and licence — "Third-party assets must be permissively licensed, keep their license file next to them, and get a row in `ATTRIBUTION.md` (path, title, author, source, license) in the same change; so do original assets." — [S25], photocraft rules, rule 3
- **C207** [quoted] photocraft forbids naming its features with another company's product or feature names; parity means same place and behaviour, not the same name; file-format names stay accurate — "Parity means the same place and behaviour, not the same name." — [S25], photocraft rules, rule 10
- **C208** [quoted] photocraft's real-file corpora — storytold's own Photoshop- and GIMP-authored oracles from a separate corpus repo, plus psd-tools, ag-psd and PngSuite from their upstreams — are fetched at pinned, sha256-verified commits and never committed into the app repo — "Real-file corpora live in `corpus/` (gitignored, never committed), fetched at pinned commits and sha256-verified by `cargo xtask corpus --all`: our Photoshop- and GIMP-authored oracles" — [S25], Test corpora
- **C209** [quoted] photocraft contributing.md restates the clean-room rule, naming icons and ICC profiles from proprietary software as not to be copied — "**Clean-room:** do not copy code, shaders, icons, ICC profiles or other assets from proprietary software (such as Photoshop). Match behaviour and look by observation and public specs." — [S26], bullet list, Clean-room
- **C210** [quoted] The same contributing guide tells contributors to reuse the reference app's menu-item ids and default shortcuts for new commands — "**Find the id.** Search `crates/ui-egui/src/menu_catalog.rs` for the Photoshop menu item. Using its id makes the menu item live with no UI work." — [S26], Adding a command, step 1
- **C211** [quoted] photocraft contributions are licensed MIT OR Apache-2.0 with a NOTICE file; brand logos are separately licensed and not open source — "**Licence:** contributions are MIT OR Apache-2.0 (`LICENSE-MIT`, `LICENSE-APACHE`, `NOTICE`). The ArtCraft logos in `docs/brand/` are not open source" — [S26], bullet list, Licence
- **C212** [quoted] RFC-0006 (the shared AGENTS.md section) carries the same clean-room rule, in near-identical wording, in its proposed rule list — "2. **Clean room.** Learn from observed behaviour and public specifications; do not copy another product's code, assets, strings or artwork. Check dependency licences before adding them." — [S27], Rust rules list, rule 2
- **C213** [quoted] RFC-0029 sets a naming rule for other companies' names and states it is not legal advice or trademark clearance — "This is a conservative naming policy, not legal advice or trademark clearance." — [S28], intro
- **C214** [quoted] RFC-0029 requires a recorded trademark check (owner list, TM/R marks, USPTO, EUIPO/TMview, WIPO) for every new or changed feature name, logged in the PR — "Record the date, the sources searched, what turned up and the decision, in the pull request and the app's existing feature-naming document" — [S28], Checking a name
- **C215** [quoted] RFC-0029 explicitly allows file-format names and stable interoperability names, including in exported files — "names that belong to the user's documents, and stable interoperability names, including in files we export;" — [S28], exceptions list
- **C216** [quoted] craft-anything's AGENTS.md has an "original work only" rule wider than photocraft's: no code, scripts, schemas, names, assets or wording from another project — "**Original work only:** never copy code, scripts, schemas, names, assets or wording from another project, and never name other reverse-engineering products in source, docs, UI or commit messages." — [S29], header
- **C217** [quoted] craft-anything enforces its clean-room mode in code: only tools listed in engine/src/clean_room.rs run, and a tool may be listed only if it watches from outside — "it may be listed only if it touches no target or watches from outside, as a visitor or user would." — [S29], rule 4
- **C218** [quoted] craft-anything's README defines clean room as reading nothing inside the original (code, files or page source) and working from what a visitor sees — "nothing inside the original is read, not its code, files or page source." — [S30], Clean room or Deep
- **C219** [quoted] craft-anything's Deep mode reads the target's code and files, including decompilation via Ghidra, framed as for private use — "**Deep**: every tool is used, for your private use. A program's code and files are read with the built-in engines (and Ghidra when it's installed)" — [S30], Clean room or Deep
- **C220** [quoted] craft-anything says its clean room is a product rule, not an isolation boundary: the coding agent still acts with its own permissions — "Clean room is a rule about what Craft Anything offers and refuses. It is not an operating-system sandbox: it doesn't isolate your computer." — [S30], Clean room or Deep
- **C221** [quoted] craft-anything's responsible-use note: use only on software you own or may examine; agent told not to copy logos, photos or text without confirmed ownership or permission — "the agent is told not to copy logos, photos or text unless you confirm you own them or have permission." — [S30], Responsible use
- **C222** [quoted] The ibl.ai article states the clean-room/no-DRM rules do not settle legal questions a rebuild can raise — "None of that settles the legal questions a rebuild can raise; it states what the tool will and will not do." — [S31], section on clean-room vs deep mode
- **C224** [quoted] storytold has a written clean-room procedure in craft-libs, for format crates: it exists so every line is theirs and a reviewer can check that from the repo alone — "This document is the standard a format crate follows so that every line of it is ours, and so that a reviewer can check that claim from the repository alone." — [S32], intro
- **C225** [quoted] The procedure's allowed inputs: published specs, prose documentation (never code), consented/CC0/own sample files, and a reference implementation run only as a logged black box whose source is never opened — "Its source is never opened, read, searched, diffed or quoted, including comments, licence headers, mirrors and excerpts in forum posts or AI answers." — [S32], What "clean-room" means here
- **C226** [quoted] The procedure names copyleft sources (dcraw, LibRaw, FFmpeg, ExifTool's Perl and others), Adobe SDKs and profiles, and any earlier unclean attempt of their own as never consulted — "Never consulted, in any form: GPL/LGPL/AGPL/CDDL decoder and encoder sources" — [S32], What "clean-room" means here
- **C227** [quoted] The record must contain starting assumptions written before any source is consulted, committed once and never edited — "**Starting assumptions**, written before any source is consulted, every item marked unverified, committed once and never edited." — [S32], The process, item 1
- **C228** [quoted] The record must contain a source log of every URL opened and search run, including unrequested implementation details a page exposed — "**A source log**: every URL opened and every search run, in order, with the time, what was asked and what was taken." — [S32], The process, item 3
- **C229** [quoted] The procedure freezes the derived format before verification and implementation; later mismatches reopen it explicitly with a new revision — "Its commit is the freeze point. Nothing in it is tuned afterwards. A mismatch found later reopens the derivation *explicitly*" — [S32], The process, item 5
- **C230** [quoted] Contamination rule: stop, log it, tell the maintainer; later code by the same person for that part is suspect and the maintainer decides re-derivation by someone else, licensed derivation, or dropping it — "Code written afterwards by the same person for the same part of the format is suspect" — [S32], When something is not clean
- **C231** [quoted] Sample files are never committed; tests fetch them by pinned URL and SHA-256, and code that came from an app is listed in NOTICE under Source provenance — "Sample files are never committed (sizes aside, they are other people's photographs)" — [S32], Assets and attribution
- **C232** [quoted] The CRW record shows the procedure applied: LibRaw's pre-built binary was run as a black box and its shipped source never opened — "only `unprocessed_raw.exe` was ever run, as a black box. The source tree shipped alongside it was never opened, read or searched." — [S33], What stayed local
- **C233** [inference] storytold's procedure is a single-team logged derivation (assumptions, source log, freeze, verification) rather than the classic two-team separation; separation of people appears only as a remedy after contamination — from [C224], [C227], [C228], [C229], [C230]
- **C234** [inference] The written procedure covers file formats derived for libraries; the app rules read for UI and behaviour parity are short rules with no procedure or record, and photocraft's command guide reuses the reference app's menu ids and shortcuts — from [C201], [C205], [C210], [C224]
- **C235** [measured] jarvis and music-intel-mcp are MIT (GitHub licence field); redrobot is private with no licence detected and no LICENSE, NOTICE or attribution file at its root — Own measurements, L2-M1
- **C236** [measured] jarvis's only third-party notice is THIRD_PARTY_LICENSES/aihero-skills-MIT.txt (Matt Pocock skills); no storytold or AutoCraft notice exists on jarvis main, and jarvis-private master carries the same single file — Own measurements, L2-M2
- **C237** [quoted] jarvis issue #2233 (open, 2026-11-18) plans a review prompt that follows AutoCraft's OPUS_REVIEW, citing repo, file, commit and licence — "The second review follows AutoCraft's Opus review (`storytold/autocraft`, `src/prompts/index.ts`, `OPUS_REVIEW` at commit `d8e45b5`, licensed MIT OR Apache-2.0)" — [S34], Area
- **C238** [quoted] redrobot's architecture doc records a licence column for its libraries, listing Warp's licence as NVIDIA — "| **NVIDIA Warp** | GPU DEM particle physics | NVIDIA |" — [S35], Technology Stack (private, gh api)
- **C239** [inference] Attribution of outside material in our repos is ad hoc: one third-party notice file in jarvis, a citation in an open issue, and no licence file in redrobot — from [C235], [C236], [C237]
- **C240** [quoted] Classic method: one person examines the system and writes a spec, a lawyer reviews it, a team with no connection to the examiners implements it — "The specification is then implemented by a team with no connection to the original examiners." — [S36], lead, para 3
- **C241** [quoted] Clean-room design is usually best practice, not strictly required by law — "Clean-room design is usually employed as best practice, but not strictly required by law." — [S36], Case law
- **C242** [quoted] In Sony v. Connectix the appeal court accepted direct disassembly where there was no other way to learn behaviour — "the direct disassembly and observation of proprietary code was necessary because there was no other way to determine its behavior" — [S36], Sony v. Connectix
- **C243** [quoted] CJEU SAS v WPL (C-406/10, 2012): functionality, programming language and data-file formats are not protected expression — "Neither the functionality of a computer program nor the programming language and the format of data files in order to exploit its functions constitute a form of expression of that program" — [S37], Ruling 1
- **C244** [quoted] The same ruling: reproducing expressive elements of another program's user manual can infringe, so docs and wording are not free — "of elements described in the user manual for another computer program protected by copyright can infringe" — [S37], Ruling 3
- **C245** [quoted] chardet 7.0 (March 2026) was relicensed LGPL to MIT after a Claude-assisted rewrite claimed as a clean room; it is unclear whether training data carried the original — "it's unclear whether Claude ingested chardet's code during training and, if that occurred, whether Claude's output cloned that training data" — [S38], para 4
- **C246** [quoted] The original author's objection: prior exposure defeats the clean-room claim and an AI generator adds no rights — "Adding a fancy code generator into the mix does not somehow grant them any additional rights." — [S38], quoting GitHub issue
- **C247** [quoted] Lawyer Heather Meeker (2026-04-09): the maintainer's decade of exposure could not be cleansed, but AI can act as a neutral actor between spec and implementation — "using AI to perform clean room development can help manage this issue by interposing a neutral actor" — [S39], The Chardet Controversy post
- **C248** [quoted] Meeker flags reusing the same project name and API as a key misstep, a trademark-style confusion issue — "A key issue here was that the clean room reimplementation used the same project name and API, which could cause confusion with the prior version." — [S39], The Chardet Controversy post
- **C249** [inference] storytold's rules map onto the legal picture: formats and behaviour treated as free (SAS), code, assets, strings and wording forbidden (SAS ruling 3), own names enforced (naming confusion), and an agent's training exposure is not addressed by any rule read — from [C201], [C215], [C216], [C243], [C244], [C245], [C248]
### Q3 — storytold's shared security and supply-chain checks against our gitleaks and minimum release age — answered with a gap

- **C301** [quoted] craft-common-actions supply-chain.yml (workflow_call) builds a CycloneDX SBOM and signs release files with actions/attest after a release: provenance, not a pass/fail check — "Generate the CycloneDX SBOM" — [S40], job attest
- **C302** [quoted] The shared release workflow does not call supply-chain.yml; an app must add it as a separate opt-in job — "`release.yml` does not call `supply-chain.yml`." — [S41], README line 231
- **C303** [measured] No storytold repo calls supply-chain.yml: an org code search for "supply-chain.yml@" hits only craft-common-actions/README.md — Own measurements, L3-M1
- **C304** [measured] The shared SonarCloud workflow runs step-security/sonarqube-scan-action with no sonar.qualitygate.wait setting (0 occurrences of "qualitygate"), so the job does not wait on the Sonar quality gate — Own measurements, L3-M2
- **C305** [quoted] SonarCloud is skipped, not failed, without a token (fork PRs) — "skipping SonarCloud scan." — [S42], line 583
- **C307** [measured] 29 storytold workflow files call sonarcloud.yml@ — Own measurements, L3-M1
- **C308** [quoted] craft-anything's deny.toml denies yanked crates and ignores four RUSTSEC ids with reasons — "yanked = \"deny\"" — [S43], [advisories]
- **C309** [measured] craft-anything's `cargo xtask ci` does not run cargo deny; only the separate `xtask licenses` does, and only `check licenses` — Own measurements, L3-M3
- **C310** [quoted] The shared gate mentions cargo-deny only as an example value of its optional prebuilt-tools input — "cargo-nextest@0.9.150,cargo-deny@0.20.2); empty installs none" — [S44], inputs, line 103
- **C311** [quoted] anicraft runs cargo-deny itself because the shared gate does not, checking licenses, bans and sources, not advisories — "the shared gate doesn't run" — [S45], job licenses, lines 33-50
- **C312** [quoted] photocraft's own docs state it has no dependency-advisory check — "No `cargo-deny` policy file, `cargo-audit` job, or equivalent dependency-advisory workflow is present in the current tree." — [S46], line 7
- **C313** [measured] cargo vet: 0 hits in the storytold org; cargo-audit: 7 files, none a CI workflow — Own measurements, L3-M1
- **C314** [quoted] photocraft's Dependabot updates cargo and github-actions daily at 06:00 New York, each grouped into one PR, with no cooldown key — "Consolidate updates into a single PR rather than one PR per crate" — [S47], cargo entry, interval "daily"
- **C315** [quoted] craft-common-actions' own Dependabot (github-actions, daily, grouped) sets a 7-day cooldown — "default-days: 7" — [S48], cooldown
- **C316** [inference] photocraft's daily cargo and actions updates have no cooldown key, so GitHub's 3-day default applies; the shared repo holds 7 days — from [C314], [C315], [C330]
- **C317** [quoted] photocraft tracks the shared release workflow at @main on purpose, for propagation without PRs — "Intentionally tracked at @main (not SHA-pinned) so org-wide CI improvements, security fixes, and build optimizations propagate without PR churn across all craftapp repos." — [S49], job release, line 34
- **C318** [quoted] That @main release call passes Apple, Windows, Azure and Linux signing secrets into the shared workflow — "APPLE_CERTIFICATE: ${{ secrets.APPLE_CERTIFICATE }}" — [S49], job release, secrets block lines 43-58
- **C319** [quoted] craft-anything's CI states the same @main rationale for the gate — "Tracks @main so suite-wide CI fixes reach every app without a PR in each repository." — [S50], job gate
- **C320** [measured] storytold SHA-pins third-party actions and pins its own workflows and actions to @main: craft-common-actions (4 workflows) 88 SHA, 50 @main; photocraft ci+release 55 SHA, 12 @main, 3 tag — Own measurements, L3-M4
- **C321** [measured] Org code search finds 138 workflow files that reference craft-common-actions with @main — Own measurements, L3-M1
- **C322** [measured] photocraft and craft-common-actions main: only deletion, non_fast_forward and pull_request (0 approvals) rules, no required status checks. No storytold check blocks a merge; a change to the shared @main workflows needs a PR with zero approvals — Own measurements, L3-M5
- **C323** [quoted] supply-chain.yml's harden-runner step runs in audit mode, which logs egress rather than blocking it — "egress-policy: audit" — [S40], step Harden runner, line 28
- **C324** [inference] No storytold shared security or supply-chain check blocks a merge: supply-chain.yml is opt-in and uncalled, Sonar does not wait on its quality gate, nothing is required, cargo-deny is outside the shared gate, and no sampled CI checks RustSec advisories — from [C302], [C303], [C304], [C309], [C311], [C312], [C322]
- **C340** [measured] jarvis main requires seven checks, gitleaks and ruff among them (strict true): require-linked-issue, pytest, code-gate, gitleaks, waiting-human-review, risk-tier, ruff — Own measurements, L3-M6
- **C341** [quoted] jarvis gitleaks runs unfiltered on every PR with full history via a SHA-pinned gitleaks-action, because it is required — "NOTE: `gitleaks` is a REQUIRED status check." — [S51], header, lines 3-10
- **C342** [quoted] jarvis Dependabot: pip and github-actions, monthly, grouped, 7-day cooldown — "Minimum release age (#2143): hold a new version 7 days before Dependabot proposes it." — [S52], both entries
- **C343** [quoted] jarvis sets a relative uv minimum release age — "exclude-newer = \"7 days\"" — [S53], [tool.uv], added in #2215
- **C344** [quoted] The jarvis coverage doc marks the minimum age as configured but not enforced; a hand-added dependency younger than 7 days passes — "Configured, not enforced (#2143 AC2)" — [S54], row 19
- **C345** [quoted] Row 18: the required ruff check runs `uv sync --locked`, which fails when a named package is not on the index; the lookalike-package half is an accepted gap — "installs with `uv sync --locked`, which resolves `pyproject.toml` against the index and fails when a named package is not on it" — [S54], row 18 (PR #2219)
- **C346** [quoted] Row 20: jarvis has no advisory or malware lookup at install, and declined one — "No advisory or malware lookup." — [S54], row 20
- **C347** [quoted] jarvis CI installs uv itself unpinned from PyPI, outside the lock and the 7-day age — "run: python -m pip install uv" — [S55], line 51; pytest.yml 29, 51
- **C348** [measured] jarvis and music-intel-mcp: secret-scanning push protection on, Dependabot security updates disabled; vulnerability-alerts returns 404 (disabled) on both — Own measurements, L3-M6, L3-M7
- **C349** [inference] With security updates off and no advisory lookup, jarvis cannot use the cooldown's security bypass: a fix for a known-vulnerable version waits for the monthly run plus 7 days unless done by hand — from [C338], [C342], [C346], [C348]
- **C350** [measured] jarvis pins all 43 remote uses: to a SHA, its own reusable lane workflows and risk-tier action included (@2d4b5aeb...) — Own measurements, L3-M4
- **C351** [quoted] jarvis' check on that self-pin is advisory — "Advisory only: push/dispatch triggers, never a pull_request check, never required, never fails" — [S56], header
- **C352** [measured] music-intel-mcp requires require-linked-issue, lint, test, verify-verdict, waiting-human-review; its gitleaks workflow is not required. 20/20 refs SHA-pinned; no exclude-newer — Own measurements, L3-M6, L3-M4, L3-M8
- **C353** [quoted] music-intel-mcp Dependabot covers github-actions only, monthly, with no cooldown key, and a test fails on a movable tag — "tests/test_workflow_action_pins.py fails if a `uses:` falls back to a movable tag" — [S57], header
- **C354** [measured] redrobot master is unprotected (status checks off); rulesets need Pro (403) — Own measurements, L3-M7
- **C355** [quoted] redrobot AGENTS.md: merging is a manual step, not a gated one — "PR workflows report but do not block; merging is a manual, disciplined step, not a gated one." — [S58], lines 105-111
- **C356** [quoted] redrobot gitleaks pins the binary by version and sha256, uses the base branch's config on PRs and fails closed on a shallow clone — "GITLEAKS_SHA256: \"551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb\"" — [S59], env and step Resolve the range
- **C357** [quoted] redrobot's pip-audit, uv.lock audit, bandit and npm audit run weekly and on dispatch, not on PRs; a red lock audit files an issue — "cron: \"0 6 * * 1\"" — [S60], on.schedule
- **C358** [measured] redrobot: no dependabot.yml or renovate.json; 17 workflows hold 46 tag pins (actions/checkout@v4 etc.), 4 SHA pins, 5 local; no exclude-newer — Own measurements, L3-M4, L3-M7, L3-M8
- **C330** [quoted] Since 2026-07-14 Dependabot holds a release 3 days before a version-update PR by default; security updates open immediately — "Security updates still open immediately, so critical fixes are never delayed." — [S61], body
- **C331** [quoted] GitHub: the chalk/debug poisoned versions were live about two hours — "The poisoned versions were live for roughly two hours before the community caught them and npm pulled them." — [S62], intro
- **C332** [quoted] GitHub states the cooldown's limit: long-game attacks — "It does little against attacks that play a longer game, including backdoors planted in releases and left dormant, maintainer sabotage, or a compromised build system." — [S62], limits section
- **C333** [quoted] Woodruff: 8 of 10 attacks had windows under a week; 14 days would have stopped all but one — "8/10 attacks had windows of opportunity of less than a week" — [S63], Cooldowns section
- **C334** [quoted] Woodruff's windows: xz-utils about 5 weeks, Kong about 10 days, tj-actions 3 days, Ultralytics 12 h then 1 h, Nx 4 h — "Kong Ingress Controller ≈ 10 days" — [S63], window table
- **C335** [quoted] Woodruff: a small sample, and not a panacea — "some attackers will evade detection" — [S63], after the table
- **C336** [quoted] PyPI LiteLLM (2026): upload to quarantine took 2h 32m; Telnyx 3h 42m — "From upload to quarantine (total exposure time): 2h 32m" — [S64], timeline
- **C337** [quoted] PyPI 2025: two-thirds of malware reports handled within 4 h, 92% within 24 h, worst cases 4 days — "66% of all reports were handled within 4 hours, climbing to 92% within 24 hours" — [S65], malware section
- **C338** [quoted] PyPI advises pairing cooldowns with vulnerability scanning, since bots bypass cooldown for security updates — "Dependency cooldowns should be paired with a vulnerability scanning strategy" — [S64], guidance section
- **C339** [quoted] Dependabot's GitHub Actions cooldown dates a tag by its commit, so an old commit tagged yesterday passes a 7-day cooldown — "a tag cut 100 days ago but only released yesterday sails straight through a 7-day cooldown" — [S66], timestamps section
- **C360** [quoted] Cargo has no stable client-side release-age filter yet: min-publish-age is nightly-only — "the unstable -Zmin-publish-age flag in the Cargo shipped with Rust 1.98 in August 2026, so it's usable on nightly but not yet stabilized" — [S66], Other ecosystems
- **C361** [quoted] tj-actions/changed-files (CVE-2025-30066): attackers moved version tags to a malicious commit that dumped CI secrets into logs, over 23,000 repos, 14-15 March 2025 — "Attackers retroactively modified multiple version tags to reference a malicious commit, exposing CI/CD secrets in workflow logs." — [S67], summary
- **C362** [quoted] GitHub: pin actions to a full-length SHA; a tag can be moved; the same applies to reusable workflows — "Pin actions to a full-length commit SHA" — [S68], Using third-party actions
- **C363** [inference] A branch ref is weaker than a tag: it moves on every merge by design. storytold's exposure is in-org: one merged PR to craft-common-actions main (0 approvals, no required checks) runs in 138 caller workflows, signing-secret release jobs included. Their SHA pins close the tj-actions vector of a moved third-party ref — from [C317], [C318], [C320], [C321], [C322], [C361], [C362]
- **C365** [inference] Cooldowns: jarvis 7 d on Dependabot and uv; music-intel a 3-d default on actions only; redrobot none; storytold 7 d on shared-repo actions, a 3-d default on app crates, no install-side age (stable Cargo has none) — from [C316], [C330], [C342], [C343], [C353], [C358], [C360]
### Q4 — How healthy photocraft's main is under advisory CI, by the redrobot baseline's method — answered with a gap

- **C401** [measured] Three windows gave 58, 113 and 26 first-parent main commits (Nov 15 15:53–Nov 18 17:01, Nov 9 10:38–Nov 10 23:55, Nov 3 00:27–20:39), 197 in all, from five samples of 200 commits — Own measurements, L4-M1
- **C402** [measured] By the baseline's rollup definition, 94 of 196 photocraft main commits with a result were red, and main was red 61% of the time (82.9 h of 136.0 h) — Own measurements, L4-M5
- **C403** [measured] Counting only the shared gate job, 58 of 192 main commits with a gate result were red, and main was gate-red 32% of the time (43.8 h of 136.0 h) — Own measurements, L4-M5
- **C404** [measured] Gate-red time varies by window: 42% (Nov 15–18), 32% (Nov 9–10), 3% (Nov 3); rollup-red time 50%, 61%, 97% — Own measurements, L4-M2, L4-M3, L4-M4
- **C405** [measured] On Nov 3 the rollup was red almost all day because of `sonarcloud / SonarCloud Scan` (16 of 25 main commits) while the gate was green on 24 of 25 — Own measurements, L4-M4, L4-M6
- **C406** [measured] Over the three windows, Windows test jobs and the web/wasm job were the other common push failures: `test (windows-latest, unit)` 51, `test (windows-latest, integration)` 40, `web build and wasm size gate` 29 main commits — Own measurements, L4-M6
- **C407** [measured] Main throughput differs by window: 58 main commits in 75 h (Nov 15–18) against 113 in 37 h (Nov 9–10) — Own measurements, L4-M2, L4-M3
- **C408** [measured] Rollup red streaks (first red to next green commit): 26 closed, median 1.04 h, max 24.94 h; gate streaks: 10 closed, median 1.35 h, max 24.94 h — Own measurements, L4-M5
- **C409** [measured] The longest streak ran from 2026-11-17 15:41 (the commit of #15449, the craft UI framework port) to 2026-11-18 16:38 and covered 24 main commits, 23 of them gate-red — Own measurements, L4-M2, L4-M11
- **C410** [measured] Merging went on while main was red: 16 PRs merged into main between 09:20 and 09:43 on Nov 18, all gate-red, 17.5 h into that streak; Nov 10 had 8 red merges in 4 minutes (23:51–23:55) — Own measurements, L4-M11
- **C411** [measured] Only 1 of 197 main commits had no check rollup at all; the gate was missing on 2 and cancelled on 3 — Own measurements, L4-M5
- **C412** [measured] Of 9 gate failures read at the start of a red streak, 6 were deterministic (a compile error E0308, Cargo.lock drift, a stale `panel-commands` allowlist entry, a stale `docs/scorecard.md`, tests still querying renamed button labels, half-pixel sampler assertions) and 3 were nondeterministic (a CMYK split-route proptest, a wall-clock Liquify twirl test, GPU `PollError` timeouts); one mid-streak log showed the same panel-commands failure, and one log returned 404 — Own measurements, L4-M7
- **C413** [quoted] The pen-tool red streak was merge skew: one PR renamed buttons while tests added by another PR, landing around the same time, still queried the old labels — "#12993 renamed the buttons from "Make Selection" / "Make Shape" to the "Make:" caption with Selection…, Mask and Shape. The tests added for #12892 landed around the same time and still query the old labels, so three of them fail on main" — [S70], PR body, ## Why
- **C414** [quoted] The Nov 15 streak had two causes, a test broken by another PR's signature change and a lockfile check that fails with every test green — "Otherwise the gate's `git diff --exit-code -- Cargo.lock` step fails even when every test passes." — [S71], PR body, Cargo.lock bullet
- **C415** [quoted] The same PR names the source of the compile error as another merged PR — "matching the `assign_shortcut(app, index, shortcut)` signature from #11674" — [S71], PR body, Test bullet
- **C416** [quoted] The Liquify failure was a known flaky test, filed the day before it hit main — "compares two Twirl dabs whose strength now comes from the wall clock, so it fails when the runner is slow." — [S72], issue body, TL;DR
- **C417** [quoted] The project's own nextest config records GPU timeouts under contention as a known failure mode — "Too many concurrent wgpu devices time out (`PollError: ... Wait timed out`)" — [S73], header comment, [test-groups]
- **C418** [quoted] After the framework port main's own Windows unit job was red with 16 failing tests, tracked as an open high-priority issue — "`main`'s own unit job is red with 16 failing tests at `c337d6e4e`" — [S74], issue body, first line
- **C419** [inference] Of the deterministic causes traced, most came from interaction between merges (renamed labels against new tests, a changed signature) or generated files going stale between merges (Cargo.lock, the panel-commands allowlist, the scorecard) — from [C412], [C413], [C414], [C415]
- **C420** [measured] No revert: 0 of 197 main commit headlines contain "revert", and a search for merged photocraft PRs with "revert" in the title returns 1 hit, a feature PR (#11850) — Own measurements, L4-M2, L4-M9
- **C421** [measured] Red streaks end with a named fix-forward PR: #13023 "(main red since #12993)", #15196 "Main green: ...", #15474 "Fix main's CI: ..." and #15624 (scorecard regen), the last two closing the 25 h streak — Own measurements, L4-M10, L4-M12
- **C422** [quoted] Fixes are bundled when one fix alone cannot turn main green — "Main's CI failures after #15449, fixed in one PR because each fix alone leaves the others red." — [S75], PR body, first line
- **C423** [measured] "Fix main"-style work is routine: 43 issues/PRs carry "main red", "main green" or "main CI" in the title — Own measurements, L4-M9
- **C424** [quoted] A red main reaches every PR, because PRs run the same test jobs: in October one issue counted 194 of 489 open PRs failing for main's reasons — "Of the **489 open PRs**, **194 already fail one of them**" — [S76], issue body, TL;DR
- **C425** [quoted] The same issue says a main-red check can block its own fix from going green — "until it is resolved no PR can be green" — [S76], issue body, TL;DR
- **C426** [measured] photocraft's AGENTS.md has no rule on a red main, revert or fix-forward, flaky tests or retries; the nearest line is about local edits ("wait and retry") — Own measurements, L4-M8
- **C427** [measured] No nextest retries: `.config/nextest.toml` has no `retries` key, and none of the 10 gate logs read shows a `TRY n` or `FLAKY` line; a failure fails the run — Own measurements, L4-M8
- **C428** [quoted] The CI nextest profile is set to collect all failures in one run — "Collect all failures in one integration run" — [S73], [profile.ci] comment
- **C429** [measured] No test quarantine: code search for "quarantine" returns 6 paths, none test-related (macOS packaging, web presets, atomic meta, release docs); "#[ignore" with "flaky" returns 1 file, where the ignored test is a benchmark — Own measurements, L4-M9
- **C430** [measured] 18 photocraft issues/PRs have "flaky" in the title, e.g. #12697 opened 2026-11-09, closed 2026-11-10 — Own measurements, L4-M9
- **C431** [inference] photocraft main is red much more than redrobot master: gate-only 32% of the time and rollup 61% against redrobot's 12%; red commits 58/192 (gate) or 94/196 (rollup) against 23/153 — from [C402], [C403]
- **C432** [inference] Typical streaks are similar in length (median ~1.0–1.4 h against ~0.8 h), but photocraft has a 25 h streak with 24 commits merged through it — from [C408], [C409], [C410]
- **C433** [inference] The cause mix is inverted: redrobot's red was mostly timing-flaky tests (16 of 23), while photocraft's sampled gate reds were mostly deterministic (6 of 9) — from [C412], [C419]
- **C434** [inference] photocraft almost never lacks a result on main (1 of 197 against redrobot's 46 of 200), because CI runs on every push to main — from [C411]

## Disconfirming evidence

- C103/C106: gh search `repo:storytold/photocraft oracle in:title` (19) and `floor lowered` (16) — no PR lowers a floor; found the conflicting-oracle case #5132 (C117) and write gap #6130 (C120).
- C113/C127: FLOOR and pass_floor lines in 16+16 commit patches (L1-M1, L1-M2); no decrease. Sample, not full history.
- C131: search `coverage ratchet "never decrease" problems gaming threshold` — snippet-level criticism only (deletion distorts percentage ratchets; arbitrary thresholds invite gaming); nothing on count floors hiding swaps.
- C133/C172: search `golden master snapshot tests problems regenerate accept incorrect output` — sources agree snapshots check stability, not correctness; Sampson defends the velocity trade (C136/C137), not a refutation.
- C141–C143/C170: search `log replay testing autonomous robots open-loop non-reactive limitation resimulation` — all hits agree; none claims open-loop replay validates planning.
- C169: catalog contents (L1-M5) and the README itself state one hardware trace and its limits (C160).
- C173: search `robot simulator validation against recorded hardware trajectories industrial arm` — no accepted per-joint/TCP tolerance found; Robotarium ~5 mm sim-hardware error, mobile robots (snippet, not entered).
- For [C233]: gh code search "clean-room" org:storytold (30 paths); only craft-libs docs/clean-room.md is a procedure; "someone else" appears only after contamination. Nothing against.
- For [C239]: git grep, gh issue search for storytold/autocraft in jarvis and jarvis-private: only research docs and #2233. redrobot: one licence code search only.
- For [C247]: counters [C245], [C246]; Meeker's own heading "Clean Room is Rarely a Real Solution".
- For [C243]: EUR-Lex fetch returned 0 bytes; Directive Art. 5(3)/6 unverified first-hand.
- For the no-blocking claim (C324): checked for a required-checks rule, a Sonar gate wait and any supply-chain.yml caller (L3-M1, L3-M2, L3-M5); nothing against, and the earlier report agrees. Gap: an org rule hidden from a non-member cannot be ruled out.
- For the no-advisory-check claim (C312, C324): searched "cargo deny", "cargo-audit", "cargo vet", "rustsec" (L3-M1). Counter: craft-anything and anicraft keep a deny.toml (C308, C311), but neither CI runs `check advisories`. The pdfcraft and craft-ai-integrations deny.toml files were not read.
- For cooldowns stopping most attacks (C333): query "dependency cooldown criticism malicious package undetected weeks" returned GitHub's own limits (C332), and the outliers xz and Kong (C334). 8/10 is one author's sample of 10; no larger dataset with a stated method found.
- For detection within hours (C336, C337): query "PyPI malicious packages time to removal median 2025". PyPI's 4 h/24 h counts from the report, not the upload.
- For the security-update bypass (C330): PyPI agrees (C338). Counter for us: the bypass needs Dependabot security updates, which are off in jarvis and music-intel (C348, C349).
- For the branch-pin risk (C363): storytold's counter-rationale is quoted (C317, C319). tj-actions (C361) is a moved third-party tag, not an in-org branch; no incident of an org's own @main workflow being abused was searched. Gap.
- For the Actions tag-date flaw (C339): one source (Nesbitt), not checked against Dependabot docs.
- C402/C403 (main red ~1/3 to ~2/3 of the time): looked for a calm period that would make the windows unrepresentative. The Nov 3 window is gate-green 97% of the time (C404), so the gate figure ranges from 3% to 42% by window, and three windows of 6–75 h are thin. Searching titles for "main red"/"main green"/"main CI" gave 43 hits (L4-M9), so red main recurs and the sampled windows are not one bad week.
- C408/C409 (one 25 h streak): checked whether the streak was one cause or several. Gate logs at its start and middle show the same panel-commands failure (L4-M7), and #15474 lists four independent breakages from one PR (C422). The streak is real; as a duration it is an outlier.
- C412/C419 (causes mostly deterministic): searched for flaky-titled issues to test whether flakiness dominates instead. 18 hits against 43 main-red titles (L4-M9). Two of the 3 flaky gate failures had issues and fixes (#12697, #10386). With n=9, the 6:3 split is a direction, not a rate.
- C420/C421 (fix-forward, not revert): searched merged PR titles for "revert" → 1 hit, not a revert (L4-M9); 0 "revert" headlines on main. Nothing found against.
- C427/C429 (no retries, no quarantine): grepped nextest.toml for retries, searched code for "quarantine" and for "#[ignore" with "flaky" (L4-M8, L4-M9). Nothing found against. Retries outside nextest (a job re-run in Actions) would not show in the rollup's latest attempt; not checked.
- Merging through red (C410): a possible counter is that the merges were queued before main broke. The Nov 18 burst came 17.5 h into the streak, so it was not.


## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | storytold PR and issue threads on main red, flaky tests, corpus floors ([C114], [C117], [C413], [C424]); the chardet relicensing dispute ([C245], [C246]) | Reddit not used; no forum discussion of storytold's practices found |
| Specialists | storytold's own docs, RFCs, test code and shared workflows; Jest, WPT, Sampson and Applied Intuition on oracles and replay; GitHub, PyPI, Woodruff and Nesbitt on cooldowns and pinning; Meeker on clean room; our repos' rules, workflows and fixtures | craftrules `standards/test-corpora.md` returned 404; SonarCloud's own quality-gate settings live outside GitHub |
| Data | own measurements over the GitHub API: corpus and parity floor history, photocraft main check rollups in three windows, gate logs, org code search for workflow refs, branch protection (L1-M1..L4-M12); Woodruff's 10 attacks, PyPI's response times | the main-health windows are short (6–75 h) and the causes rest on 9 Linux gate logs; Woodruff's sample is 10 attacks |
| Adversarial | disconfirming searches per load-bearing claim; storytold's own red-main issues; tj-actions advisory; legal limits of clean room ([C241], [C222]) | no incident found where an org's own @main shared workflow was abused |

Declared overruns:
- Q1: 6 web searches against a ceiling of 4, page reads far past three (the question has three parts including a private-repo audit), about 65 GitHub API calls against about 60.
- Q2: page reads past three, because the written procedure was found mid-run. EUR-Lex was blocked (empty response); the SAS ruling is read through a secondary source.
- Q3: 9 full page reads against a ceiling of 3, because the question has three parts; about 45 API calls.
- Q4: about 46 API calls, within budget; no web search.

The redrobot baseline figures this report compares against (12% red time, 23 red of 153, 16 of 23 flaky, 46 of 200 without a result) come from the third run, `docs/research/ci-red-main-baseline-and-relaxation-options-2026-11-18.md` (PR #2237), not from a measurement in this run.

No fetched page addressed instructions to the agents. No redrobot content went into an external request. No search-and-scrape connector was used.

## Own measurements

<!-- ledger Q1 -->
### L1-M1

`python floorhist.py` (gh api commits on ui-egui parity.rs, FLOOR lines): "fa5dfb3e1 2026-11-08 … 662 → 663" · "ad59d9962 … 640 → 660" · "d21c403e5 2026-11-03 … 631 → 640" · "01cd6fffa 2026-10-08 … 620 → 627" · "58653e617 2026-10-03 … 619 → 620 | 625/625 menu items live (100%)" · "9cfbe11bf 2026-10-03 … 604 → 613". No decrease in 16 commits.

### L1-M2

`python corpushist.py` (gh api commits on corpus.rs): PHOTOSHOP pass_floor 133→145 (becc27ac1, 10-13) →147 →149 →152 →165 →185 (a62ef68ca) →188 (4e1e325b1) →190 (b526378de, 10-22); PSD_TOOLS 236→241→242→249. No decrease.

### L1-M3

`curl -sL https://raw.githubusercontent.com/storytold/photocraft/HEAD/docs/parity-checklist.md`: "**664 of 664 menu items live (100.0%).**"

### L1-M4

`python count_status.py rr/hyp.yaml`: {'uncharacterized': 8, 'measured': 6}

### L1-M5

redrobot git tree (recursive, not truncated): tests/fixtures/traces/{mock_movl_uvw_slerp.csv, movl_orientation_ref_20260808_151957.csv}; controller_envelopes/*.json = 11; reports/robot_day/{2026-07-26, 2026-08-08, 2026-08-21}. `grep -c "^## [0-9]" mock_div.md` → 10

### L1-M6

`curl -sL https://raw.githubusercontent.com/storytold/photocraft/HEAD/crates/ui-egui/src/parity.rs` → "404: Not Found"; commit 086bdba30 2026-10-26 "refactor(ui-egui): move menus modules under menus/".

<!-- ledger Q2 -->
### L2-M1

python -I ours.py (gh api repos/<r>, contents/): "Osasuwu/jarvis private= False license= MIT" · "SergazyNarynov/redrobot private= True license= None" root licence-like: ['.gitattributes'] · "Osasuwu/music-intel-mcp private= False license= MIT" ['LICENSE']

### L2-M2

git ls-tree origin/main THIRD_PARTY_LICENSES (jarvis) and origin/master (jarvis-private): "aihero-skills-MIT.txt" only; git grep -i "storytold|autocraft" outside docs/research and discussions: no hits

<!-- ledger Q3 -->
### L3-M1

`st_search.py`, `st_search2.py` (gh api search/code org:storytold): `"cargo deny": total_count=19`; `cargo-audit: total_count=7`; `"cargo vet": total_count=0`; `"supply-chain.yml@": total_count=1  craft-common-actions/README.md`; `"sonarcloud.yml@": total_count=29`; `"craft-common-actions" "@main" path:.github/workflows: total_count=138`.

### L3-M2

`grep -c -i qualitygate sonarcloud.yml` → `0`; scan args: projectKey, organization, rust.lcov.reportPaths, cpd.exclusions.

### L3-M3

craft-anything xtask main.rs: `Some("ci") => { status::check(&root) && layers(&root) && locks::check(&root) && i18n_coverage::check(&root) && secrets::secrets(&root, false) && run("cargo", &["fmt", ...` … `&& wasm() }`; `fn licenses()` → `run("cargo", &["deny", "check", "licenses"])`.

### L3-M4

`pin_count.py`: `redrobot: files=17 {'tag': 46, 'local': 5, 'sha': 4}`; `music-intel-mcp: files=7 {'sha': 20}`; `jarvis: files=17 {'local': 2, 'sha': 43}`; `photocraft(ci,release): files=2 {'branch': 12, 'sha': 55, 'tag': 3}`; `craft-common-actions(gate,sonarcloud,supply-chain,release): files=4 {'sha': 88, 'branch': 50}`.

### L3-M5

`st_rules.py` (rules/branches/main, branches/main), photocraft and craft-common-actions: rules `deletion`, `non_fast_forward`, `pull_request {"required_approving_review_count": 0, ...}` (ruleset 26661234); `protection={"enabled": false, "required_status_checks": {"enforcement_level": "off", "contexts": [], "checks": []}}`.

### L3-M6

`our_probe.py`, `our_probe2.py`: jarvis `"strict":true,"contexts":["require-linked-issue","pytest","code-gate","gitleaks","waiting-human-review","risk-tier","ruff"]`; music-intel-mcp `"contexts":["require-linked-issue","lint","test","verify-verdict","waiting-human-review"]`; both: `"secret_scanning_push_protection": {"status": "enabled"}, "dependabot_security_updates": {"status": "disabled"}`.

### L3-M7

redrobot: `.github/dependabot.yml: NOT FOUND`, `renovate.json: NOT FOUND`; `protected=False ... "enforcement_level": "off"`; rulesets `HTTP 403 Upgrade to GitHub Pro`; `vuln_alerts.py`: jarvis, music-intel-mcp, redrobot `HTTP/2.0 404 Not Found` (for redrobot possibly token scope).

### L3-M8

`grep -i "exclude-newer\|\[tool.uv\]"` on redrobot and music-intel-mcp pyproject.toml → no output.

<!-- ledger Q4 -->
### L4-M1

`python sample.py 4 now w1.json` / `4 2026-11-11T00:00:00Z w2.json` / `4 2026-11-04T00:00:00Z w3.json` / `4 2026-11-10T12:16:00Z w2b.json` / `4 2026-11-03T14:22:00Z w3b.json` → each "calls 4 commits 200". `analyze.py`: "w1.json ... first-parent main 58 commits 2026-11-15T15:53:01Z .. 2026-11-18T17:01:55Z"; "w2.json+w2b.json ... 399 commits sampled, first-parent main 113 commits 2026-11-09T10:38:43Z .. 2026-11-10T23:55:07Z"; "w3.json+w3b.json ... 377 commits sampled, first-parent main 26 commits 2026-11-03T00:27:12Z .. 2026-11-03T20:39:21Z".

### L4-M2

w1: "[rollup] counts {'RED': 35, 'GREEN': 23}; ... time red 37.4h of 75.1h = 50%"; "[gate] counts {'RED': 31, 'GREEN': 25, 'CANC': 2}; red share of commits with a result 31/56; time red 31.3h of 75.1h = 42%"; "streak 2026-11-17T15:41:35Z 24.94h n=24"; "fix/revert-like headlines on main: 1 ... main-gate-fixes".

### L4-M3

w2: "[rollup] counts {'RED': 42, 'GREEN': 71}; ... time red 22.7h of 37.4h = 61%"; "[gate] counts {'GREEN': 85, 'RED': 26, 'NONE': 1, 'CANC': 1}; red share of commits with a result 26/111; time red 11.8h of 37.4h = 32%"; "fix/revert-like headlines on main: 0".

### L4-M4

w3: "[rollup] counts {'RED': 17, 'NONE': 1, 'GREEN': 8}; ... time red 22.9h of 23.5h = 97%"; "[gate] counts {'GREEN': 24, 'NONE': 1, 'RED': 1}; ... time red 0.8h of 23.5h = 3%".

### L4-M5

ALL WINDOWS: "[rollup] commits {'RED': 94, 'GREEN': 102, 'NONE': 1} red/with-result 94/196; time red 82.9h of 136.0h = 61%; closed streaks 26 median 1.04h max 24.94h"; "[gate] commits {'RED': 58, 'GREEN': 134, 'CANC': 3, 'NONE': 2} red/with-result 58/192; time red 43.8h of 136.0h = 32%; closed streaks 10 median 1.35h max 24.94h".

### L4-M6

failing checks on main commits: w1 "('gate / gate (ubuntu-24.04)', 'push'), 31), (('test (windows-latest, integration)', 'push'), 31), (('test (windows-latest, unit)', 'push'), 29), (('web build and wasm size gate', 'push'), 22)"; w2 "gate ... 26 ... unit 21 ... SonarCloud Code Analysis 14 ... integration 8 ... wasm 7"; w3 "(('sonarcloud / SonarCloud Scan', 'push'), 16) ... gate 1, integration 1, unit 1".

### L4-M7

`fetch_logs.py <job ids>` then `scan2.py`: 125855113034 "FAIL [ 9.861s] ... photocraft-compose cmyk::tests::the_split_route_agrees_with_the_exact_path" / "13957 tests run: 13956 passed (4 slow), 1 failed"; 129579135296 "assertion `left == right` failed: layer.translate left: [[65.5, 35.5]] right: [[65.0, 35.0]]" (5 failed); 129903063405 "FAIL ... liquify_ui::tests::alt_with_twirl_clockwise_twirls_counterclockwise"; 130115656455 "No nodes found matching the query: ... label: "Make Selection"" (3 failed); 132867356347 "error[E0308]: mismatched types" / "ci failed at `clippy`"; 133032906500 "2078 tests run: 2078 passed" then "--- a/Cargo.lock +++ b/Cargo.lock" (craft-psd rev); 133229877617 ""PollError: The requested Wait timed out before the submission was completed."" (3 failed); 134158592840 and 134641458629 "FAIL  panel-commands: 0 unrouted click handler(s), 1 stale allowlist entr(y/ies)"; 134923487421 "FAIL  scorecard: docs/scorecard.md is stale"; 129155936994 "ERR b'gh: HTTP 404'".

### L4-M8

`curl -sL .../photocraft/main/.config/nextest.toml` (6473 bytes); `grep -n -i "retr\|flaky\|quarantine\|junit\|leak" nextest.toml` → no output. `scan2.py` pattern includes `TRY \d+|FLAKY|RETRY` → no such status line in 10 logs. AGENTS.md (27199 bytes) `grep -i "flak\|quarantin\|retry\|retries\|#\[ignore\|red main\|main red\|revert\|fix forward"` → only "177:- If someone else's in-progress edit breaks the build, wait and retry; don't fix their files."

### L4-M9

`search.py`: "code: quarantine repo:storytold/photocraft -> total 6" (apps/photocraft-web/src/preset_bridge.rs, crates/format/src/atomic/meta.rs, apps/photocraft-web/src/indexed_presets.rs, docs/releasing.md, packaging/macos/verify.sh, packaging/macos/package.sh); "issues: repo:storytold/photocraft flaky in:title -> total 18"; "revert in:title is:pr is:merged -> total 1" (11850 "Escape in the Brush Preset picker reverts what was typed"); ""main red" OR "main green" OR "main CI" in:title -> total 43"; "code: "#[ignore" flaky ... -> total 1" (crates/engine/src/preset_store/tests.rs; line 365 `#[ignore]` on `bench_load_500_sampled_presets`). `grep -ciE revert` over 197 main headlines → 0.

### L4-M10

streak-ending commits: "2026-11-10T23:00:07Z de9add28 SUCCESS gate=GREEN | Merge pull request #13023 from ljkx/fix/pen-enter-tests-make-labels"; "2026-11-15T20:30:18Z d547d50c SUCCESS gate=GREEN | Merge pull request #15196 from davidmann4/fix/main-green-lockfile-test"; "2026-11-18T15:04:46Z d039f542 FAILURE gate=CANC | Merge pull request #15474 from aiongg/main-gate-fixes"; "2026-11-18T16:38:01Z 3bc25b0c SUCCESS gate=GREEN | Merge pull request #15624 from aiongg/scorecard-regen"; "2026-11-03T20:39:21Z 81bd9737 ... #10387 from davidmann4/fix/flaky-split-route".

### L4-M11

`grep -cE "^   2026-11-18T09:(2[0-9]|3[0-9]|4[0-3]).*gate=RED" summary.txt` → 16; Nov 17 15:41–Nov 18 15:43 main rows → "23 FAILURE gate=RED", "1 FAILURE gate=CANC". w2: "open streak at window end: 0.14h, 8 commits since 2026-11-10T23:51:50Z".

### L4-M12

`fetch_prs.py`: "#13023 by ljkx merged_by davidmann4 created 2026-11-10T22:18:59Z merged 2026-11-10T23:00:08Z"; "#15196 ... created 2026-11-15T18:53:34Z merged 2026-11-15T20:30:18Z"; "#15474 by aiongg ... created 2026-11-17T16:08:45Z merged 2026-11-18T15:04:46Z"; "#15624 ... created 2026-11-18T15:55:59Z merged 2026-11-18T16:38:02Z".


## Open questions

- Q4 — the causes of photocraft's red main rest on 9 Linux gate logs; the Windows test jobs, which fail often, were not read. Settled by reading the first failing Windows job log of each streak in the three windows.
- Q4 — whether the red share holds over a longer period. Settled by the same sampling over two more weeks, spaced apart.
- Q1 — how storytold's `standards/test-corpora.md` frames corpora (404 in this run), and redrobot's replay-format-2, sigma and `f2_oracle_gate` decisions, which were not read.
- Q1 — what tolerance is accepted for comparing industrial-arm trajectories; no source was found. Settled by a vendor or standards source on path accuracy, or by redrobot's own repeatability measurements.
- Q2 — whether any storytold rule addresses an agent's training-data exposure to the reference product; none was found in the files read. RFC-0027 and the lightcraft ARW derivation were not read.
- Q3 — SonarCloud's quality-gate setting (outside GitHub) and whether redrobot's Dependabot alerts 404 is token scope or the real setting.
- Q4 — when each red streak started (the break-to-fix times of #13023 and #15196 were not recorded). Settled by the merge time of the PR that first turned main red in each traced streak.
- Q2 — whether storytold has any written procedure for app UI and behaviour parity beyond the short rules, and whether our repos have a rule for studying a reference product; both rest on searches not recorded as measurements. Settled by a recorded org code search and a grep of our rules files.
- Q3 — when SonarCloud's job goes red: the shared workflow continues the scan when tests fail (sonarcloud.yml line 456), so what does fail it was not established. Settled by reading the workflow's failure paths and a failed SonarCloud run.

## Sources

- [S1] https://github.com/storytold/photocraft-corpus/blob/main/README.md — passage
- [S2] https://github.com/storytold/photocraft/blob/main/crates/io/tests/it/corpus.rs — passage
- [S3] https://github.com/storytold/photocraft/pull/5781 — passage
- [S4] https://github.com/storytold/photocraft/pull/5132 — passage
- [S5] https://github.com/storytold/photocraft/issues/6130 — passage
- [S6] https://github.com/storytold/photocraft/blob/main/docs/development.md — passage
- [S7] https://github.com/storytold/photocraft/issues/9495 — passage
- [S8] https://github.com/storytold/photocraft/blob/main/crates/ui-egui/src/menus/parity.rs — passage
- [S9] https://github.com/storytold/photocraft/blob/main/AGENTS.md — passage
- [S10] https://github.com/jestjs/jest/blob/main/docs/SnapshotTesting.md — passage
- [S11] https://www.cs.cornell.edu/~asampson/blog/turnt.html — passage
- [S12] https://github.com/web-platform-tests/wpt/blob/master/docs/writing-tests/reftests.md — passage
- [S13] https://web.eecs.umich.edu/~weimerw/2018-481/readings/testoracles.pdf — passage
- [S14] https://appliedintuition.com/blog/log-management-handbook-part-3 — passage
- [S15] https://www.appliedintuition.com/blog/closed-loop-log-replay — passage
- [S16] https://github.com/SergazyNarynov/redrobot/blob/master/AGENTS.md — passage
- [S17] https://github.com/SergazyNarynov/redrobot/blob/master/tests/leveling/test_golden_replay.py — passage
- [S18] https://github.com/SergazyNarynov/redrobot/blob/master/docs/decisions/2026-10-21-leveling-engine-promotion.md — passage
- [S19] https://github.com/SergazyNarynov/redrobot/blob/master/tests/fixtures/controller_envelopes/README.md — passage
- [S20] https://github.com/SergazyNarynov/redrobot/blob/master/tests/fixtures/traces/README.md — passage
- [S21] https://github.com/SergazyNarynov/redrobot/blob/master/redrobot/driver/trace_parity.py — passage
- [S22] https://github.com/SergazyNarynov/redrobot/blob/master/reports/robot_day/2026-08-08/mock_divergences_2026_08_08.md — passage
- [S23] https://github.com/SergazyNarynov/redrobot/blob/master/assets/controller_hypotheses.yaml — passage
- [S24] https://github.com/SergazyNarynov/redrobot/blob/master/docs/decisions/2026-11-12-mock-robot-read-only-parity.md — passage
- [S25] https://raw.githubusercontent.com/storytold/photocraft/HEAD/AGENTS.md — passage
- [S26] https://raw.githubusercontent.com/storytold/photocraft/HEAD/docs/contributing.md — passage
- [S27] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0006-coding-agents.md — passage
- [S28] https://raw.githubusercontent.com/storytold/craft-contrib/HEAD/rfcs/0029-other-companies-names.md — passage
- [S29] https://raw.githubusercontent.com/storytold/craft-anything/HEAD/AGENTS.md — passage
- [S30] https://raw.githubusercontent.com/storytold/craft-anything/HEAD/README.md — passage
- [S31] https://ibl.ai/blog/craft-anything-clean-room-rebuild-software-moat — passage
- [S32] https://raw.githubusercontent.com/storytold/craft-libs/HEAD/docs/clean-room.md — passage
- [S33] https://raw.githubusercontent.com/storytold/craft-libs/HEAD/crates/crw/clean-room/README.md — passage
- [S34] https://github.com/Osasuwu/jarvis/issues/2233 — passage
- [S35] https://github.com/SergazyNarynov/redrobot/blob/master/docs/pipeline_v3_architecture.md — passage
- [S36] https://en.wikipedia.org/w/index.php?title=Clean-room_design&action=raw — passage
- [S37] https://en.wikipedia.org/w/index.php?title=SAS_Institute_Inc_v_World_Programming_Ltd&action=raw — passage
- [S38] https://www.theregister.com/2026/03/06/ai_kills_software_licensing/ — passage
- [S39] https://heathermeeker.com/tag/lgpl/ — passage
- [S40] https://raw.githubusercontent.com/storytold/craft-common-actions/main/.github/workflows/supply-chain.yml — passage
- [S41] https://github.com/storytold/craft-common-actions/blob/main/README.md — passage
- [S42] https://raw.githubusercontent.com/storytold/craft-common-actions/main/.github/workflows/sonarcloud.yml — passage
- [S43] https://github.com/storytold/craft-anything/blob/main/deny.toml — passage
- [S44] https://raw.githubusercontent.com/storytold/craft-common-actions/main/.github/workflows/gate.yml — passage
- [S45] https://raw.githubusercontent.com/storytold/anicraft/main/.github/workflows/ci.yml — passage
- [S46] https://raw.githubusercontent.com/storytold/photocraft/main/book/src/development/dependencies.md — passage
- [S47] https://raw.githubusercontent.com/storytold/photocraft/main/.github/dependabot.yml — passage
- [S48] https://raw.githubusercontent.com/storytold/craft-common-actions/main/.github/dependabot.yml — passage
- [S49] https://raw.githubusercontent.com/storytold/photocraft/main/.github/workflows/release.yml — passage
- [S50] https://raw.githubusercontent.com/storytold/craft-anything/main/.github/workflows/ci.yml — passage
- [S51] https://github.com/Osasuwu/jarvis/blob/main/.github/workflows/gitleaks.yml — passage
- [S52] https://github.com/Osasuwu/jarvis/blob/main/.github/dependabot.yml — passage
- [S53] https://github.com/Osasuwu/jarvis/blob/main/pyproject.toml — passage
- [S54] https://github.com/Osasuwu/jarvis/blob/main/docs/reference/failure-class-coverage.md — passage
- [S55] https://github.com/Osasuwu/jarvis/blob/main/.github/workflows/ruff.yml — passage
- [S56] https://github.com/Osasuwu/jarvis/blob/main/.github/workflows/lane-pin-drift.yml — passage
- [S57] https://github.com/Osasuwu/music-intel-mcp/blob/main/.github/dependabot.yml — passage
- [S58] https://github.com/SergazyNarynov/redrobot/blob/master/AGENTS.md — passage, read via gh api
- [S59] https://github.com/SergazyNarynov/redrobot/blob/master/.github/workflows/gitleaks.yml — passage
- [S60] https://github.com/SergazyNarynov/redrobot/blob/master/.github/workflows/security.yml — passage
- [S61] https://github.blog/changelog/2026-07-14-dependabot-version-updates-introduce-default-package-cooldown/ — passage
- [S62] https://github.blog/security/supply-chain-security/the-case-for-a-cooldown-why-dependabot-now-waits-before-issuing-version-updates/ — passage
- [S63] https://blog.yossarian.net/2025/11/21/We-should-all-be-using-dependency-cooldowns — passage
- [S64] https://blog.pypi.org/posts/2026-04-02-incident-report-litellm-telnyx-supply-chain-attack/ — passage
- [S65] https://blog.pypi.org/posts/2025-12-31-pypi-2025-in-review/ — passage
- [S66] https://nesbitt.io/2026/03/04/package-managers-need-to-cool-down — passage
- [S67] https://github.com/advisories/GHSA-mrrh-fwg8-r2c3 — passage
- [S68] https://docs.github.com/en/actions/reference/security/secure-use — passage
- [S69] https://www.veracode.com/?p=17004 — snippet only
- [S70] https://github.com/storytold/photocraft/pull/13023 — passage
- [S71] https://github.com/storytold/photocraft/pull/15196 — passage
- [S72] https://github.com/storytold/photocraft/issues/12697 — passage
- [S73] https://raw.githubusercontent.com/storytold/photocraft/main/.config/nextest.toml — passage
- [S74] https://github.com/storytold/photocraft/issues/15503 — passage
- [S75] https://github.com/storytold/photocraft/pull/15474 — passage
- [S76] https://github.com/storytold/photocraft/issues/3907 — passage

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED |  |
| C103 | SUPPORTED |  |
| C104 | SUPPORTED |  |
| C105 | SUPPORTED |  |
| C106 | SUPPORTED |  |
| C108 | SUPPORTED |  |
| C109 | SUPPORTED |  |
| C111 | SUPPORTED |  |
| C112 | SUPPORTED |  |
| C113 | PARTIAL | L1-M2 shows 133→190 over 10-13..10-22 and no decrease; 'inside feature PRs' and '16 sampled commits' are not in the recorded output; narrowed |
| C114 | SUPPORTED |  |
| C115 | SUPPORTED |  |
| C116 | SUPPORTED |  |
| C117 | SUPPORTED |  |
| C118 | SUPPORTED |  |
| C119 | SUPPORTED |  |
| C120 | SUPPORTED |  |
| C121 | SUPPORTED |  |
| C122 | PARTIAL | quote is about noise-gradient fills only; generalisation 'gaps show up as missing oracles' narrowed to that case |
| C123 | SUPPORTED |  |
| C124 | SUPPORTED |  |
| C125 | SUPPORTED |  |
| C126 | SUPPORTED |  |
| C127 | PARTIAL | L1-M1/L1-M3 show values and no decrease; 'raised in feature PRs' not in the output; narrowed |
| C128 | SUPPORTED |  |
| C129 | PARTIAL | quote shows the path AGENTS.md names; that it no longer exists is C130's measurement, not this quote; narrowed |
| C130 | SUPPORTED |  |
| C131 | SUPPORTED |  |
| C133 | SUPPORTED |  |
| C134 | SUPPORTED |  |
| C136 | SUPPORTED |  |
| C137 | SUPPORTED |  |
| C139 | SUPPORTED |  |
| C140 | SUPPORTED | PDF read via pdftotext |
| C141 | SUPPORTED |  |
| C142 | SUPPORTED |  |
| C143 | SUPPORTED |  |
| C144 | SUPPORTED |  |
| C146 | SUPPORTED |  |
| C147 | SUPPORTED |  |
| C148 | SUPPORTED |  |
| C149 | SUPPORTED |  |
| C150 | SUPPORTED |  |
| C152 | SUPPORTED |  |
| C153 | SUPPORTED |  |
| C154 | SUPPORTED |  |
| C155 | SUPPORTED |  |
| C156 | SUPPORTED |  |
| C157 | SUPPORTED |  |
| C158 | SUPPORTED |  |
| C159 | SUPPORTED |  |
| C160 | SUPPORTED |  |
| C161 | SUPPORTED |  |
| C163 | SUPPORTED |  |
| C164 | SUPPORTED |  |
| C165 | SUPPORTED |  |
| C166 | SUPPORTED |  |
| C167 | SUPPORTED |  |
| C168 | SUPPORTED |  |
| C169 | SUPPORTED |  |
| C170 | SUPPORTED |  |
| C171 | PARTIAL | S22 shows the J6 artifact still treated as a bound in the registry note, not annotated; narrowed to the known-bad list and the held-out trace |
| C172 | SUPPORTED |  |
| C173 | SUPPORTED |  |
| C201 | SUPPORTED |  |
| C202 | SUPPORTED |  |
| C203 | SUPPORTED |  |
| C204 | SUPPORTED |  |
| C205 | SUPPORTED |  |
| C206 | SUPPORTED |  |
| C207 | SUPPORTED |  |
| C208 | PARTIAL | S25 lists psd-tools, ag-psd and PngSuite upstream corpora alongside storytold's own; 'PSD oracles are storytold's own files' overstated; rewritten |
| C209 | SUPPORTED |  |
| C210 | SUPPORTED |  |
| C211 | SUPPORTED |  |
| C212 | PARTIAL | RFC-0006 wording differs from the house rule ('; do not' vs '. Do not', 'dependency licences' vs 'a dependency's licence'); 'verbatim' dropped |
| C213 | SUPPORTED |  |
| C214 | SUPPORTED |  |
| C215 | SUPPORTED |  |
| C216 | SUPPORTED |  |
| C217 | SUPPORTED |  |
| C218 | SUPPORTED |  |
| C219 | SUPPORTED |  |
| C220 | SUPPORTED |  |
| C221 | SUPPORTED |  |
| C222 | SUPPORTED |  |
| C224 | PARTIAL | quote shows the craft-libs procedure; 'not in photocraft or craft-contrib' rests on a code search not recorded under Own measurements; dropped |
| C225 | SUPPORTED |  |
| C226 | SUPPORTED |  |
| C227 | SUPPORTED |  |
| C228 | SUPPORTED |  |
| C229 | SUPPORTED |  |
| C230 | SUPPORTED |  |
| C231 | SUPPORTED |  |
| C232 | SUPPORTED |  |
| C233 | SUPPORTED |  |
| C234 | PARTIAL | 'rests only on the one-sentence rule' contradicted by C205 (photocraft rule 3 is longer) and rests on the dropped absence part of C224; narrowed |
| C235 | SUPPORTED |  |
| C236 | SUPPORTED |  |
| C237 | PARTIAL | S34 does not say whether text is copied; clause dropped. Open, created 2026-11-18 confirmed via gh |
| C238 | PARTIAL | table says only 'NVIDIA'; 'non-OSI' is not in the source; narrowed |
| C239 | PARTIAL | C235-C237 show licences and notices, not the absence of a rule for studying a reference product; narrowed to ad hoc attribution |
| C240 | SUPPORTED |  |
| C241 | PARTIAL | quote supports best practice / not required; 'evidence of independent creation' is in a different passage of S36; narrowed |
| C242 | SUPPORTED |  |
| C243 | SUPPORTED |  |
| C244 | SUPPORTED |  |
| C245 | SUPPORTED |  |
| C246 | SUPPORTED |  |
| C247 | SUPPORTED |  |
| C248 | SUPPORTED |  |
| C249 | SUPPORTED | nearest rule is C225's ban on AI answers as a contamination channel, which is not the agent's own training exposure |
| C301 | SUPPORTED |  |
| C302 | SUPPORTED |  |
| C303 | SUPPORTED |  |
| C304 | PARTIAL | 0 'qualitygate' confirmed; 'goes red on coverage or test failures' is wrong for tests: S42 line 456 continues the scan when a shard's tests fail; narrowed to 'does not wait on the quality gate' |
| C305 | SUPPORTED |  |
| C307 | SUPPORTED |  |
| C308 | SUPPORTED |  |
| C309 | SUPPORTED | L3-M3 elides part of the chain; craft-anything xtask main.rs read: 'deny' only in fn licenses |
| C310 | SUPPORTED |  |
| C311 | SUPPORTED |  |
| C312 | SUPPORTED |  |
| C313 | SUPPORTED | the 7 cargo-audit hits re-listed: docs, engine code and a Containerfile, no workflow |
| C314 | SUPPORTED |  |
| C315 | SUPPORTED |  |
| C316 | SUPPORTED |  |
| C317 | SUPPORTED |  |
| C318 | SUPPORTED |  |
| C319 | SUPPORTED |  |
| C320 | SUPPORTED |  |
| C321 | SUPPORTED |  |
| C322 | SUPPORTED |  |
| C323 | PARTIAL | quote is from supply-chain.yml; gate.yml also uses audit, but sonarcloud.yml uses egress-policy: block (4 steps); generalisation narrowed |
| C324 | PARTIAL | re-judged after C304: Sonar part rewritten; 'no check blocks a merge' still follows from C322 |
| C340 | SUPPORTED |  |
| C341 | SUPPORTED |  |
| C342 | SUPPORTED |  |
| C343 | SUPPORTED |  |
| C344 | SUPPORTED |  |
| C345 | SUPPORTED |  |
| C346 | SUPPORTED |  |
| C347 | SUPPORTED |  |
| C348 | PARTIAL | L3-M6 shows push protection, not secret scanning itself; narrowed |
| C349 | SUPPORTED |  |
| C350 | SUPPORTED | self-pins @2d4b5aeb on lane.yml, lane-watch.yml, lane-close.yml and risk-tier confirmed in jarvis .github/workflows |
| C351 | SUPPORTED | quote present across a YAML comment line break ('never\n# fails'); script reports NOT FOUND for that reason |
| C352 | SUPPORTED | music-intel-mcp has .github/workflows/gitleaks.yml; not in required contexts |
| C353 | PARTIAL | S57 confirms actions-only, monthly, no cooldown; '3-day default applies' comes from S61, not S57; dropped. Quote present across a YAML comment line break |
| C354 | SUPPORTED |  |
| C355 | SUPPORTED |  |
| C356 | SUPPORTED |  |
| C357 | SUPPORTED |  |
| C358 | SUPPORTED |  |
| C330 | SUPPORTED |  |
| C331 | SUPPORTED |  |
| C332 | SUPPORTED |  |
| C333 | SUPPORTED |  |
| C334 | SUPPORTED |  |
| C335 | SUPPORTED |  |
| C336 | SUPPORTED |  |
| C337 | SUPPORTED |  |
| C338 | SUPPORTED |  |
| C339 | SUPPORTED |  |
| C360 | SUPPORTED |  |
| C361 | SUPPORTED |  |
| C362 | SUPPORTED |  |
| C363 | SUPPORTED |  |
| C364 | UNSUPPORTED | S69 (resolves to Veracode 'Typosquatting and Other Attacks...') has no TurkoRat and no 'remained undetected for over two months'; removed with its references in Disconfirming evidence and Coverage |
| C365 | PARTIAL | music-intel's 3-day default needs C330, which it did not name; [C330] added |
| C401 | PARTIAL | '999 sampled commits' not in L4-M1 (five calls of 200; 399 and 377 for w2, w3); rewritten |
| C402 | SUPPORTED |  |
| C403 | SUPPORTED |  |
| C404 | SUPPORTED |  |
| C405 | SUPPORTED |  |
| C406 | SUPPORTED |  |
| C407 | SUPPORTED |  |
| C408 | SUPPORTED |  |
| C409 | SUPPORTED |  |
| C410 | SUPPORTED |  |
| C411 | SUPPORTED |  |
| C412 | PARTIAL | a proptest failure is random-input, not timing; 'timing-dependent' narrowed to 'nondeterministic' |
| C413 | PARTIAL | S70 says the PRs landed around the same time; that each passed alone is not stated; narrowed |
| C414 | SUPPORTED |  |
| C415 | SUPPORTED | quote verbatim in the PR body read via gh api; the script reads the rendered page and reports NOT FOUND |
| C416 | SUPPORTED | issue #12697 created 2026-11-09 19:41Z; gate job 129903063405 created 2026-11-10 14:45Z (gh api) |
| C417 | SUPPORTED |  |
| C418 | SUPPORTED | issue #15503 OPEN, label priority: high, names the Windows job; quote verbatim in the issue body via gh api, the script reads the rendered page and reports NOT FOUND |
| C419 | PARTIAL | 'not defects any single PR's own CI would have shown' contradicted by S71: #15175's own gate was red on the lockfile; narrowed |
| C420 | SUPPORTED |  |
| C421 | PARTIAL | 2.3 h and 4.6 h break-to-fix times are not in L4-M10/L4-M12 (break times not recorded); dropped |
| C422 | SUPPORTED |  |
| C423 | SUPPORTED |  |
| C424 | SUPPORTED | issue #3907 created 2026-10-12 |
| C425 | SUPPORTED |  |
| C426 | SUPPORTED |  |
| C427 | SUPPORTED |  |
| C428 | PARTIAL | comment says collect all failures; nothing about retries; 'not to retry' dropped |
| C429 | SUPPORTED |  |
| C430 | PARTIAL | L4-M9 gives the title count only; 'handled as issues with a fix' not shown; narrowed |
| C431 | SUPPORTED | redrobot figures (12%, 23/153) checked against the PR #2237 branch report |
| C432 | SUPPORTED | redrobot median ~0.8 h checked against the PR #2237 branch report |
| C433 | PARTIAL | follows C419's narrowing: 'merge skew' dropped, 'deterministic (6 of 9)' kept; redrobot 16 of 23 matches PR #2237 |
| C434 | SUPPORTED | redrobot 46 of 200 matches PR #2237; push-event checks in L4-M6 |

Label verdict: open — every sub-question has a gap that could move its answer: Q4's red share rests on three windows of 6–75 h whose gate-red time ranges from 3% to 42%, and its cause mix on 9 logs; Q2's absence findings rest on unrecorded searches; Q3's 'nothing blocks a merge' cannot exclude an org rule hidden from a non-member.

Quote check storytold-oracles-cleanroom-supply-chain-main-health-2026-11-18.md: 141 quoted claim(s): 113 found, 4 NOT FOUND, 24 unfetchable, 0 no source — the 4 NOT FOUND are verified by hand (C351, C353: the quote breaks across a YAML `#` comment line; C415, C418: verbatim in the PR/issue body via gh api, absent from the rendered page the script reads); the 24 unfetchable are private redrobot files and one storytold raw URL, all read via gh api.

## Disposition

| Recommendation | State | Where |
|---|---|---|
| treat robot days as corpus capture — same-day commit of verbatim wire-logs and traces, a raise-only floor over hardware-trace passes, a known-bad list with reasons, and a progression set for traces the mock cannot match yet | deferred | unfiled: a redrobot process change; the user is still collecting input for the deferred /grill on redrobot's CI rules (2026-11-18), and it goes there before any issue |
