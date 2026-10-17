---
topic: memory-sync-backend
tags: area:memory, research
source_provenance: /research invocation from session local_11153d39 (delegate-tier /grill, 2026-10-17)
status: open
audit: 2026-10-17 — 216 claims: 192 SUPPORTED, 21 PARTIAL, 0 UNSUPPORTED, 3 UNCHECKABLE
---

## Question

Existing tools/projects that keep Claude Code memory files (~/.claude/projects/<project>/memory/MEMORY.md, decisions.md, topic files; plus user-level ~/.claude files) as ordinary local files read/written directly by Claude's Read/Write/Edit tools, while transparently syncing them to a private server-side store/DB across 3 Windows devices. Requirements: files stay local; sync to server DB (MongoDB-like JSON store as analogy); keep user-level vs project-level split; no public services (private infra or E2E). Compare: purpose-built Claude/agent memory sync projects (GitHub), generic file sync (Syncthing, git auto-sync into private jarvis-private repo, rclone bisync), DB-backed FUSE/virtual-FS (Windows support). Per option: Windows support, conflict handling on concurrent appends (decisions.md append-only from several sessions), privacy, maintenance cost.

Asked for a sync "to a server DB", answering "to a private server-side store" — a git remote or a file server counts — because no DB-backed option for Windows turned up that keeps files local (Q4), and the requirement that matters is that the store is private and the files stay local.

Sub-questions: Q1 purpose-built Claude Code memory sync projects, and what Claude Code itself allows (location, project key, settings); Q2 git auto-sync into a private repo — tools and how concurrent appends merge; Q3 Syncthing and rclone bisync — conflicts, Windows, privacy (plus encryption over a git remote); Q4 DB-backed FUSE / virtual filesystems on Windows.

Earlier report: `docs/research/cross-device-sync-2026-05-18.md` treated memory as rows in a Supabase Postgres via a memory MCP server. That server has since been removed and memory is machine-local files again (prior: user-level rules file, not fetched), so its memory sections no longer describe the system; its `.gitattributes` point (line endings) still applies (C251).

## Summary

**Recommendation: plain git, not a DB.** Put the memory directories in a private git repo and sync it from hooks: pull at SessionStart, commit and push at Stop. Mark `decisions.md` and other append-only logs (e.g. the delegate tier's `delegate-shadow.md`) `merge=union` in `.gitattributes`. Leave `MEMORY.md` and topic files on git's default merge, so a concurrent edit stops as a conflict for a human to resolve instead of merging silently.

**Answer to the literal question: no tool checked does this.** Of the three main purpose-built tools checked, none syncs Claude Code memory as local files to a private store and offers all three of: Windows support, client-side encryption, and a merge that is safe for concurrent appends [C141]. A fresh search turned up 15 more 0–1-star repos by name; of the two read, neither closes the gap [C145]–[C148].

How the purpose-built tools compare:

| Tool | What it has | What it lacks |
|---|---|---|
| tawanorg/claude-sync | age encryption to self-hosted MinIO/WebDAV [C130] | No Windows build [C133], [C134]; can overwrite append-only files with truncated copies [C135] |
| perfectra1n/claude-code-sync | Windows builds, a 3-way merge and a per-machine project map [C125]–[C127] | No encryption [C128]; recently had a silent-revert bug [C129] |
| MarimerLLC claude-memsync | Runs on Windows [C118] | Leaves git conflict markers in non-MEMORY files such as `decisions.md` [C121], [C122]; needs identical paths on every PC [C120] |

rclone mount and JuiceFS on Windows need WinFsp, and both WinFsp and Dokany install a kernel-mode driver on every device [C431]. The candidates are weak:

- No maintained MongoDB/GridFS or Postgres filesystem for Windows turned up [C436].
- JuiceFS on Windows is Beta, cannot guarantee close-open consistency [C413], [C415], and cannot commit writes without its metadata service [C422].
- rclone mount will not start offline [C444], does not tell the writer when an upload failed on Windows [C441], and does not raise change notifications for writes made on another device [C443].

**Why git fits.**

- **Append-only files merge cleanly.** With `merge=union`, concurrent appends on two clones merge or rebase without a conflict [C246] (M1, M9). Without the attribute they conflict and leave markers in the file (M1).
- **Union is wrong for edited files.** On a file edited in place, union silently keeps both contradictory versions of a line [C247] and brings back a line that one device had pruned [C248] (M2, M9). So union belongs on `decisions.md` but not on `MEMORY.md` [C250].
- **Conflicts should stop the sync.** The mature auto-sync tools stop on a conflict and hand it to the user [C210], [C222], [C229]. The one data-loss report found blames force-push [C252], [C253].
- **The sync tools themselves fall short.** git-sync works on Git for Windows' bash [C219] but has no file watcher [C220]. Users report that git-auto-sync's Windows daemon never commits [C244], [C245]. gitwatch has no Windows route [C213] and runs its push even after a failed pull, without aborting or notifying [C216], [C217].
- **Hooks are the trigger.** That leaves session hooks as the place to run the sync. This is the pattern ikook-wang and sunjinpak use [C138], [C139].

**Why not Syncthing or bisync.** Neither merges text. Two devices appending to `decisions.md` between syncs give a whole-file loser copy (`.sync-conflict-*` or `.conflictN`), which someone has to merge by hand [C344].

- **Syncthing:** it has no central store, so it needs two devices online at once or an always-on peer of your own [C325]. Its encrypted untrusted-device mode is still beta [C319].
- **bisync:** it runs only on a schedule [C339], uses a hub topology [C343], and had a recent edge-case data-loss bug (a silently reverted delete, closed 2026-10-14) [C358].

**Privacy.** A private GitHub repo is hosted by a third party and is not end-to-end encrypted. Encrypting the repo at rest gives up the clean append merge:

- An encrypting clean/smudge filter (a git-crypt stand-in) turns the union append into a binary conflict [C363] (M4).
- git-remote-gcrypt by default makes every push effectively a force push [C361].

So the choice is between two setups [C364]:

- **(a)** A private GitHub repo. This accepts the same trust jarvis-private already places in GitHub (inference, not fetched).
- **(b)** A plaintext bare repo on a machine of your own, reachable over a private network. This meets "private infra" and keeps union merges.

The choice is Пётр's. The research does not settle it.

**Claude Code constraints any setup must handle.**

- **Memory is machine-local, keyed by path.** The memory directory key is the encoded repo-root path [C101], [C108], [C114]. The same repo at different paths or usernames on the three devices becomes different projects [C115], [C120].
- **Moving it means one path per project.** `autoMemoryDirectory` relocates memory, but only to one fixed path [C103]–[C105]. To keep the user/project split it must be set per project [C107]. A project-level value is honoured only under workspace trust [C106].
- **Open bugs in this area.** In auto mode, writing that value to project settings is blocked as self-modification [C144]. A resumed session can recreate the old directory and split memory [C143].
- **No built-in sync.** Claude Code has none for memory [C102], [C112], [C142].
- **Line endings.** Git on this device converts LF to CRLF [C251]. Line-ending normalisation belongs in the repo's `.gitattributes`.

**Carrier for the standing rule.** The rule "append-only memory files merge by union; everything else stops on conflict" belongs in `.gitattributes` in the memory repo, and the pull/push in SessionStart/Stop hooks (modelled on jarvis-private's existing `sync-private-clone.py` pull hook: prior, not fetched). Both are mechanisms that run whether or not the agent remembers a rule. A prose rule in AGENTS.md or memory would be broken the first time a session forgets, and the failure is silent [C247], [C248].

For the delegate-shadow question that prompted this run: a per-device `delegate-shadow.md` is safe now. Once the memory repo exists, the file syncs with no change because it is append-only.


## Findings

### Q1 — Purpose-built Claude Code memory sync projects, and what Claude Code itself allows — answered with a gap

- **C101** [quoted] Auto memory default location is ~/.claude/projects/<project>/memory/ and the <project> key is derived from the git repository, so all worktrees and subdirectories of one repo share one memory directory; outside a git repo the project root is used — "The `<project>` path is derived from the git repository, so all worktrees and subdirectories within the same repo share one auto memory directory. Outside a git repo, the project root is used instead." — [S1], Auto memory > Storage location
- **C102** [quoted] Docs state auto memory is machine-local and not shared across machines or cloud environments — "Auto memory is machine-local. All worktrees and subdirectories within the same git repository share one auto memory directory. Files are not shared across machines or cloud environments." — [S1], Auto memory > Storage location
- **C103** [quoted] A setting autoMemoryDirectory relocates auto memory, readable from any settings scope (user, project, local, policy, --settings) — "To store auto memory in a different location, set `autoMemoryDirectory` in your `settings.json`. It is read from any [settings scope](/docs/en/settings#settings-precedence): user, project, local, policy, or `--settings`." — [S1], Auto memory > Storage location
- **C104** [quoted] autoMemoryDirectory must be an absolute path or start with ~/ — "The value must be an absolute path or start with `~/`." — [S1], Auto memory > Storage location
- **C105** [quoted] autoMemoryDirectory replaces the per-project default with one directory you choose (the reference describes no per-project placeholder) — "Store [auto memory](/docs/en/memory#storage-location) in a directory of your choice instead of the per-project default." — [S2], autoMemoryDirectory
- **C106** [quoted] When autoMemoryDirectory comes from project or local settings it is honored only under the same workspace-trust rule as hooks — "From project or local settings, Claude Code honors this key under the same [workspace trust rule as hooks](/docs/en/permissions#what-runs-before-you-trust-a-folder), since a cloned repository can supply those files." — [S2], autoMemoryDirectory
- **C107** [inference] To keep a per-project split with a relocated directory, autoMemoryDirectory must be set per project (project/local settings), because a user-level value is one fixed path for all projects — from [C103], [C105]
- **C108** [quoted] Session transcripts live under ~/.claude/projects/<project>/ where <project> is the working-directory path with non-alphanumerics replaced by '-' (truncated plus hash past 200 chars) — "where `<project>` is your working directory path with non-alphanumeric characters replaced by `-`. For a working directory whose converted name exceeds 200 characters, Claude Code truncates the name to 200 characters and appends a hash of the full path" — [S3], Where transcripts are stored
- **C109** [quoted] CLAUDE_CODE_PROJECT_DIR_NAME (v2.1.234+) names the <project> directory for transcripts and auto memory, but only alongside CLAUDE_CONFIG_DIR; it is ignored when CLAUDE_CONFIG_DIR is unset — "Claude Code ignores `CLAUDE_CODE_PROJECT_DIR_NAME` when `CLAUDE_CONFIG_DIR` is unset." — [S3], Name the project directory yourself
- **C110** [quoted] CLAUDE_CONFIG_DIR moves the whole ~/.claude home (settings, session history, plugins); on Windows ~/.claude means %USERPROFILE%\.claude — "On Windows, `~/.claude` means `%USERPROFILE%\.claude`. To keep the home-directory files somewhere else, set [`CLAUDE_CONFIG_DIR`](/docs/en/env-vars); Claude Code then stores your settings, session history, and plugins there instead." — [S4], Settings files
- **C111** [quoted] User settings ~/.claude/settings.json apply to every project on this machine only, not a teammate's machine or a cloud session — "**`~/.claude/settings.json`**: every project on your machine, and nothing on your teammate's or in the cloud session" — [S4], Where settings apply
- **C112** [quoted] The settings reference describes claude.ai-account sync for skills and plugins (syncClaudeAiSkills / syncClaudeAiPlugins opt-outs), not for memory — "Stop loading the [skills enabled on your claude.ai account](/docs/en/skills#how-synced-skills-behave) and stop downloading new ones" — [S2], settings table, syncClaudeAiSkills
- **C113** [quoted] Memory files are excluded from the cleanupPeriodDays transcript retention sweep — "excludes the memory files in the memory directory from that [retention sweep]" — [S1], Auto memory > Storage location
- **C114** [measured] On this device the redrobot repo has 71 project dirs under ~/.claude/projects (one per worktree path, for transcripts) but only the main-checkout dir C--Users-petrk-GitHub-redrobot has a memory/ subdir — the memory key is the encoded main repo root path — Own measurements, M6
- **C115** [inference] Because the default key is an encoded absolute path, the same repo cloned at different paths or under different usernames on the 3 devices gets different <project> dir names; a sync must map them or pin autoMemoryDirectory per device — from [C108], [C114], [C101]
- **C116** [quoted] MarimerLLC/claude-utils claude-memsync is a background daemon syncing ~/.claude/projects/<hash>/memory/ across workstations via a private git repo, with a custom merge driver that unions MEMORY.md section blocks — "merge driver unions `MEMORY.md` section blocks instead of producing line-level" — [S5], top section
- **C117** [measured] MarimerLLC/claude-utils: 13 stars, last push 2026-07-24, latest release v0.1.8 (2026-05-09), MIT, Go, self-described pre-1.0 — Own measurements, M7
- **C118** [quoted] claude-memsync runs on Windows, Linux and macOS and needs no server of its own, only a git remote — "It's a single Go binary, runs on Windows, Linux, and macOS, and needs no server" — [S6], intro
- **C119** [quoted] claude-memsync mechanics: fsnotify watcher with 3s debounce into a git mirror at ~/.claudesync, hourly ls-remote check, pull only when remote SHA moved; Claude's own dir stays authoritative — "fsnotify watcher, 3s debounce" — [S6], How it works diagram
- **C120** [quoted] claude-memsync requires identical project paths on each PC because the memory dir name is the escaped absolute path; different paths become different projects — "name by escaping the project's absolute path. PCs that open the same repo at" — [S6], Limitations
- **C121** [quoted] claude-memsync conflicts in files other than MEMORY.md surface as standard git conflict markers in the affected file — "Conflicts in non-`MEMORY.md` files surface as standard git conflict markers in the affected file." — [S6], Limitations
- **C122** [inference] Under claude-memsync a non-MEMORY.md file such as decisions.md gets no merge driver, so a git conflict there surfaces as conflict markers; no encryption is mentioned, so the private git host holds plaintext — from [C121], [C116], [C118]
- **C123** [measured] No issues are listed on MarimerLLC/claude-utils (gh issue list --state all returned none), so no user-reported failure record exists to check against — Own measurements, M7
- **C124** [quoted] perfectra1n/claude-code-sync (Rust CLI, git backend) syncs per-project memory/ dirs as part of the attachments category alongside ~/.claude config categories — "Images, PDFs, and per-project `memory/` dirs; governed by `--exclude-attachments`, not a toggle" — [S7], What gets synced table
- **C125** [measured] perfectra1n/claude-code-sync: 99 stars, last push 2026-10-13, release v0.4.1 (2026-10-13) with windows-x86_64 and windows-aarch64 .exe assets, MIT — Own measurements, M7
- **C126** [quoted] perfectra1n/claude-code-sync conflict policy is 3-way against a recorded last-synced base; when both machines changed a file it keeps the local version and holds it back from push — "keeps this machine's version and holds it back" — [S7], Conflict policy and undo
- **C127** [quoted] perfectra1n/claude-code-sync offers a per-machine project map so relocated checkouts stay one project, and stores __HOME__/__CLAUDE_DIR__ instead of absolute paths in synced config — "Pin a project to its path per machine, so renamed or relocated checkouts stay one project" — [S7], features table
- **C128** [quoted] perfectra1n/claude-code-sync does not encrypt; its README only suggests considering encrypting the git repo — "Consider encrypting the git repository for additional security" — [S7], Security Considerations
- **C129** [quoted] perfectra1n/claude-code-sync v0.4.0 had a bug where sync's pull silently reverted local edits including non-index memory files; issue closed 2026-10-10 — "non-index memory files under `projects/*/memory/`) is **silently reverted** by the next `sync`" — [S8], issue body
- **C130** [quoted] tawanorg/claude-sync encrypts every file with age before upload, to R2, S3, GCS, S3-compatible (incl. self-hosted MinIO) or WebDAV (Nextcloud/ownCloud) — "Cloudflare R2, AWS S3, Google Cloud Storage, S3-compatible (Backblaze B2, MinIO, Wasabi), or WebDAV (Nextcloud, ownCloud)" — [S9], Features
- **C131** [quoted] tawanorg/claude-sync syncs ~/.claude/projects/ including auto-memory and maps home directories across machines via a portable HOME token, with a configurable path_map for other layout differences — "then rewritten to each device's real home on pull" — [S9], Cross-Device Path Mapping
- **C132** [quoted] tawanorg/claude-sync conflict handling: when both sides changed, the remote copy is saved as a .conflict file for manual/interactive resolution; sync is push/pull commands, optionally run from shell hooks — "When both local and remote files change, the remote version is saved as `.conflict`" — [S9], Conflict Resolution
- **C133** [measured] tawanorg/claude-sync: 299 stars, last push 2026-10-06, release v1.17.2 assets only darwin/linux (no Windows binary), no license file — Own measurements, M7
- **C134** [quoted] tawanorg/claude-sync has an open issue that it has no Windows support (only darwin/linux binaries published) — "`claude-sync` has no Windows support." — [S10], issue body (OPEN)
- **C135** [quoted] tawanorg/claude-sync open issue: push can overwrite a fuller remote append-only transcript with a truncated local copy, propagating to all machines — "the push replaces the fuller remote copy with the truncated one" — [S11], issue body (OPEN)
- **C136** [quoted] MikeVeerman/jean-claude (163 stars, last push 2026-07-26) syncs ~/.claude config (CLAUDE.md, settings.json, hooks, skills, agents) via Git and works on Windows, but its sync list does not include auto memory — "optionally syncs everything across machines via Git. Works on macOS, Linux, and Windows." — [S12], intro + What gets synced
- **C137** [quoted] kneetworks/claude-sync (29 stars, last push 2026-01-09) syncs sessions with AES-256-GCM client-side encryption to Git/S3/GCS/R2 via Claude Code hooks; README does not mention memory — "AES-256-GCM encryption before data leaves your machine" — [S13], features
- **C138** [quoted] ikook-wang/cc-sync-legacy (28 stars, last push 2026-02-23, shell) syncs projects/*/memory/ via git with a SessionStart git pull and auto-resolves pull conflicts by keeping the local version — "it auto-resolves by keeping the local version (`--ours`)" — [S14], FAQ conflicts
- **C139** [quoted] sunjinpak/claude-code-memory-sync (1 star, 2026-05-21) puts the memory dir under a private git repo with a SessionStart ff-only pull hook — "Add one SessionStart hook that does an `ff-only` pull at the start of every Claude Code session." — [S15], How it works
- **C140** [quoted] elizabethfuentes12/claude-code-dotfiles (19 stars, 2026-03-21) is a git-dotfiles approach for ~/.claude that handles concurrent pushes with pull --rebase — "git -C ~/.claude pull --rebase origin main" — [S16], troubleshooting
- **C141** [inference] None of the three main tools (tawanorg, perfectra1n, MarimerLLC) combines Windows support, auto-memory coverage, client-side encryption and a merge safe for concurrent appends — tawanorg has encryption+memory but no Windows; perfectra1n has Windows+memory but no encryption; MarimerLLC has Windows+memory and mentions no encryption — from [C118], [C121], [C124], [C125], [C128], [C130], [C133], [C134]
- **C142** [quoted] Open Claude Code feature request #101522 confirms project identity is path-based and memory stays local; its author's junction-to-OneDrive workaround produced OneDrive conflict copies on simultaneous writes — "OneDrive can also create conflict copies when both machines write at the same time." — [S17], issue body (OPEN, 2026-10-12)
- **C143** [quoted] Open Claude Code bug #101500: after the memory directory changes, a resumed conversation's system prompt still names the old directory, so writes can recreate it and split memory — "A write there recreates the old folder and splits the memory." — [S18], issue body (OPEN)
- **C144** [quoted] Open Claude Code bug #95693: in auto mode, writing autoMemoryDirectory to project .claude/settings.json is denied by the classifier as Self-Modification — "is denied by the auto mode classifier with reason `[Self-Modification]`" — [S19], issue body (OPEN)
- **C145** [measured] A GitHub repo search for "claude memory sync" sorted by update returned 15 repos (the --limit) named like such projects, pushed 2026-06..10, each with 0 or 1 stars (e.g. gagoar, tahabozdemir, turbyho, Xu-Jiaqi, BrentlBowers, DevKitRU); only names were seen, and one is an e2e test repo — Own measurements, M5
- **C146** [quoted] Xu-Jiaqi/claude-memory-sync (cmsync) syncs Claude Code auto memory over git or a Seafile server and never auto-resolves: git conflicts are saved as .conflict-*.patch files — "git conflicts become `.conflict-*.patch` files, never auto-resolved" — [S20], Features
- **C147** [quoted] cmsync was verified only on Ubuntu machines; Windows support is listed under its roadmap — "Developed and verified on three Ubuntu machines" — [S20], Verified on real machines / Roadmap
- **C148** [quoted] BrentlBowers/claude-memory-sync syncs its own structured JSON context files (not Claude's memory dir) to Proton Drive once a day — "Structured JSON context files stored locally, synced to end-to-end encrypted cloud storage once a day" — [S21], intro

### Q2 — git auto-sync into a private repo (tools, conflict handling of concurrent appends) — answered with a gap

- **C201** [measured] GitJournal/git-auto-sync: last push 2024-07-16, 202 stars, 17 open issues and PRs (13 issues + 4 PRs), not archived — over two years without a push — Own measurements, M8
- **C202** [measured] gitwatch/gitwatch: last push 2026-08-13, 1743 stars, 7 open issues, not archived — Own measurements, M8
- **C203** [measured] simonthum/git-sync: last push 2025-09-10, 895 stars, 1 open PR and 0 open issues, not archived — Own measurements, M8
- **C204** [measured] Vinzent03/obsidian-git: last push 2026-10-14, 12131 stars, 104 open issues and PRs (90 + 14), not archived — the most active of the four — Own measurements, M8
- **C205** [quoted] Git's built-in union merge driver runs a 3-way text merge but keeps lines from both sides instead of writing conflict markers — "union Run 3-way file level merge for text files, but take lines from both versions, instead of leaving conflict markers." — [S22], Built-in merge drivers (whitespace normalised)
- **C206** [quoted] The docs warn union tends to leave added lines in random order, the result needs manual verification, and it should not be used without understanding the implications — "This tends to leave the added lines in the resulting file in random order and the user should verify the result. Do not use this if you do not understand the implications." — [S22], Built-in merge drivers (whitespace normalised)
- **C207** [quoted] union is one of three built-in drivers; the default text driver writes conflict markers, binary keeps own version and leaves the path conflicted — "Usual 3-way file level merge for text files. Conflicted regions are marked with conflict markers" — [S22], Built-in merge drivers
- **C208** [quoted] git-auto-sync ships a Windows build as a downloadable release (alongside brew/apt/yum for macOS and Linux) — "Windows - Download the [latest release](https://github.com/GitJournal/git-auto-sync/releases/latest)" — [S23], Installation
- **C209** [quoted] git-auto-sync has a manual `sync` command that commits, pulls, rebases and pushes, and a daemon mode that watches a repo continuously — "You can test it out by running `git-auto-sync sync` to commit, pull, rebase and push any changes." — [S23], Usage
- **C210** [quoted] On a rebase conflict git-auto-sync aborts, stops syncing that repo, and raises a system notification — it never merges — "In the case of a rebase conflict, it will abort and stop syncing that repo. It will send a system notification to inform you of the conflict." — [S23], Merge Conflicts (whitespace normalised)
- **C211** [quoted] git-auto-sync ignores hidden files and git-ignored files — "It currently ignores all hidden files, files ignored by git, and additional temporary swap files" — [S23], Ignored Files
- **C212** [inference] Because git-auto-sync ignores hidden files and the target path is ~/.claude/projects/..., the watched repo root must not itself sit under a hidden-dir filter — whether "hidden" means dot-prefixed path components on Windows is not stated in the README — from [C211]
- **C213** [quoted] gitwatch requires inotifywait (inotify-tools) on Linux, or fswatch + coreutils via Homebrew on macOS; the README names no Windows route — "`inotifywait` (part of" — [S24], Requirements (grep for windows/cygwin/wsl: no hits)
- **C214** [quoted] gitwatch waits 2 seconds after a change before committing, to let several writes finish, and commits with `git add --all .` for a directory — "the waiting period of 2 sec is added to allow for several changes to be written out completely before committing" — [S24], What it does
- **C215** [quoted] gitwatch pulls only when -R is given with -r, and then runs `git pull --rebase` before every push — "If given along with -r, a 'git pull --rebase <remote>' is done before any push" — [S25], usage text, line 74
- **C216** [quoted] gitwatch runs the pull command and then the push command without checking the pull's exit status — "eval "$PULL_CMD"" — [S25], lines 433-441 (pull block followed directly by push block)
- **C217** [inference] Under gitwatch, the push command runs after a `git pull --rebase` even if the pull failed; the script neither aborts nor notifies — from [C215], [C216], [C226], [C227]
- **C218** [quoted] simonthum/git-sync targets exactly this use: text files, several machines, one central repo, coarse versioning over clean history — "Suppose you have a set of text files you care about, multiple machines to work on, and a central git repository" — [S26], Use case
- **C219** [quoted] git-sync states it is tested on msysgit (Git for Windows' bash) and needs only git and bash — "Tested on msysgit and a real bash." — [S26], Use case
- **C220** [quoted] git-sync has no file watcher of its own — on-change sync is via its contrib directory or external scheduling — "To synchronize automatically on filesystem changes, have a look at the `contrib` directory." — [S26], Use case
- **C221** [quoted] git-sync's flow: sanity checks, auto-commit, fetch, then push if ahead, fast-forward if behind, rebase-then-push if diverged — "If ahead, push. If behind, fast-forward. If diverged, rebase, then push." — [S26], How does it work?
- **C222** [quoted] git-sync refuses to run in the middle of a rebase/merge/am and exits non-zero with a message whenever something non-trivial occurs — "resort to manual intervention as soon as something non-trivial occurs" — [S26], What does git-sync do?
- **C223** [quoted] On a failed rebase git-sync exits 1 and leaves the rebase for the user to finish — it does not abort it (a TODO notes saving the old branch is not done) — "Rebasing failed, likely there are conflicting changes. Resolve them and finish the rebase before repeating git-sync." — [S27], lines 426-437
- **C224** [quoted] git-sync's README admits the rebase can fail precisely when several machines sync in an intertwined way — "If you don't sync in an intertwined manner (from multiple repositories/machines), `git-sync` is virtually guaranteed to succeed." — [S26], How am I supposed to use it?
- **C225** [quoted] Because git-sync rebases, commit order need not match change order; auto-commits record machine name and time — "Because git-sync rebases, the order of commits does not always reflect the order of changes." — [S26], How does it work?
- **C226** [quoted] gitwatch has a -M flag that skips commits while a merge is in progress (off by default) — " -M               Prevent commits when there is an ongoing merge in the repo" — [S25], usage text, line 106
- **C227** [quoted] gitwatch's merge detection is only a check for the MERGE_HEAD file — "[ -f "$(git rev-parse --git-dir)"/MERGE_HEAD ]" — [S25], is_merging(), line 151-153
- **C228** [prior] During a conflicted `git rebase` Git writes state under .git/rebase-merge and REBASE_HEAD, not MERGE_HEAD — so a MERGE_HEAD check misses it — not fetched in this run
- **C229** [quoted] Obsidian Git documents that conflicts commonly arise when a note is edited on two devices before both copies sync, and that automatic routines cannot finish a sync until the user resolves them — "Commit-and-sync and automatic routines cannot finish that sync until you resolve them." — [S28], intro
- **C230** [quoted] Obsidian Git's default pull strategy is merge; a rebase strategy is desktop-only and needs `git rebase --continue` from a terminal or Git client — "The steps above describe a merge, the default pull strategy." — [S28], If you use a different pull strategy
- **C231** [quoted] Obsidian Git offers an automatic one-side-wins merge strategy on conflicts, and warns that the losing side's conflicting text may be dropped — "check the resulting notes because the other side's conflicting text may be omitted." — [S28], If you use a different pull strategy
- **C232** [quoted] Obsidian Git warns against force-pushing past a rejected push, since that can overwrite another device's commits — "Avoid force pushing to bypass this, since it may overwrite commits from another device." — [S28], If the conflict is not listed in Obsidian
- **C233** [quoted] Obsidian Git runs the system Git from PATH, with a Windows troubleshooting path (`where git`) — "It takes it from the PATH." — [S29], Error: spansSync git ENOENT
- **C234** [inference] Obsidian Git only runs inside the Obsidian app on a vault, so it does not fit syncing ~/.claude/projects/*/memory/ for a headless Claude Code session unless that directory is opened as (or inside) a vault — its docs are useful as evidence of how a mature auto-sync tool treats conflicts (stop and hand to the user), not as a candidate tool — from [C229], [C233]
- **C235** [quoted] A solo user syncing a repo across machines (a3nm, 2017, updated 2018) uses custom git merge drivers so conflicts never surface on log files (timestamped, one event per line) and set files (order irrelevant, no duplicates) — "For several of these projects, I am the only user, and I mostly use git to synchronize things across machines." — [S30], intro (whitespace normalised)
- **C236** [quoted] The same author says the built-in union driver is enough only if you only add lines and do not care about duplicate entries — "If you are only adding lines, and you do not care about removing duplicate entries, you can use the predefined union merge strategy" — [S30], Set files (whitespace normalised)
- **C237** [quoted] For a log file he uses a custom driver that orders merged lines by a numeric timestamp prefix, rather than union, which picks its own order — "This merge driver will simply add the lines while choosing some order on the insertions." — [S30], Set files / Log files (whitespace normalised)
- **C238** [quoted] The custom-driver setup is per machine: the driver is registered in ~/.gitconfig and points at a script in ~/bin, while only the .gitattributes mapping is versioned — "driver = ~/bin/git-merge-set %O %A %B %L" — [S30], Set files
- **C239** [quoted] He reports running this setup for months without issues — "I have been using the setup for some months now without issues." — [S30], intro (whitespace normalised)
- **C240** [quoted] HN practitioners report `CHANGELOG merge=union` as the common fix for changelog conflicts, which are append-mostly files — "Setting `CHANGELOG.md merge=union` in .gitattributes mostly eliminates spurious merges conflicts on the changelog." — [S31], HN comment 32124145 (2022-07-17)
- **C241** [quoted] An HN user who applied merge=union to Xcode project files reports occasional duplicate items as the known failure — "Very occasionally you will get duplicate items but Xcode then warns you can take approbate action." — [S32], HN comment 8128510 (2014-08-03)
- **C242** [quoted] git-auto-sync's maintainer said he had mostly tested on macOS and Linux and had not used Windows in years — "I've mostly only tested this on MacOS, and Linux." — [S33], maintainer comment 2022-05-15
- **C243** [quoted] v1.5 (2022-06-10, still the latest release per gh api) removed the Windows service dependency bug — "I've just released version 1.5 without the dependencies." — [S33], maintainer comment 2022-06-10
- **C244** [quoted] After v1.5, three users in the Windows issue thread (2022-09, 2023-04, 2024-07; two on Windows 10, one names no version) report the daemon shows as running and monitoring but never commits, while manual `git-auto-sync sync` works — "the daemon appears to start and monitor the folder, but it doesn't actually ever do commits." — [S33], comment 2024-07-30 (also 2022-09-08, 2023-04-17)
- **C245** [inference] On Windows, users report that the git-auto-sync daemon does not commit while the manual `sync` command works; issue #7 is open and the repo has had no push since 2024-07 — from [C201], [C243], [C244]
- **C246** [measured] With merge=union, concurrent appends to a journal file on two clones rebase cleanly (exit 0, no conflict), the remote's entry placed before the local one — chronological by push order, not by write time — Own measurements, M9
- **C247** [measured] With merge=union on an in-place-edited index, a line edited differently on two devices silently ends up twice (both versions kept), with exit 0 and no warning — Own measurements, M9
- **C248** [measured] With merge=union, a line one device deleted (pruning) while the other edited it comes back in the edited form — union silently undoes the prune — Own measurements, M9
- **C249** [measured] With merge=union the surviving conflicting lines are interleaved out of their original order (the local edit of line 2 landed after line 3) — Own measurements, M9
- **C250** [inference] merge=union fits decisions.md (append-only, one entry per line) but not MEMORY.md, which is rewritten and pruned in place — there it turns every concurrent edit into silent duplicates or resurrected lines, the failure the docs warn of as "verify the result" — from [C206], [C236], [C246], [C247], [C248]
- **C251** [measured] On this device Git converts LF to CRLF in the working copy (core.autocrlf in effect), so a synced memory repo will see line-ending normalisation; whether the other two devices use the same setting was not checked — Own measurements, M9
- **C252** [quoted] An HN user (2023-12-30) reports losing over a month of notes with the Obsidian Git plugin across machines, noticed late and unrecoverable, and abandoned Obsidian — "I lost over a month of notes due to how badly behaved its git merge heuristics are." — [S34], HN comment 38813211
- **C253** [quoted] The same user attributes the loss to the plugin force-pushing and rewriting history over other machines' updates — this conflicts with the plugin's current docs, which warn against force-pushing (C232); the comment names no version — "It force pushes and rewrites history and will step on other machines with different updates." — [S34], HN comment 38813211
- **C254** [quoted] A reply in the same thread reports hitting the same plugin problem — "I've hit that "git plugin is crap" problem with obsidian too." — [S35], HN comment 38814000 (2023-12-30)

### Q3 — Syncthing and rclone bisync (and encryption over a git remote) — answered with a gap

- **C301** [quoted] Syncthing detects a conflict when a file is modified on two devices and content differs; one copy is renamed to a .sync-conflict file, no merge is described — "one of the files will be renamed to <filename>.sync-conflict-<date>-<time>-<modifiedBy>.<ext>" — [S36], Conflicting Changes
- **C302** [quoted] The loser is the copy with the older modification time; ties broken by device ID — "The file with the older modification time will be marked as the conflicting file and thus be renamed." — [S36], Conflicting Changes
- **C303** [quoted] Conflict copies are ordinary files afterwards and propagate to all devices; Syncthing does not pick the best version for the user — "files are treated as normal files after they are created, so they are propagated between devices" — [S36], Conflicting Changes
- **C304** [quoted] Modify-vs-delete conflict where deletion wins still keeps a conflict copy — "the deletion wins the conflict resolution, the file is renamed to a conflict copy as above" — [S36], Conflicting Changes
- **C305** [inference] For an append-only decisions.md appended on two devices between syncs, Syncthing yields two whole-file versions (winner + .sync-conflict copy) and a human/agent must merge the appended lines by hand; for MEMORY.md rewritten in place the same applies — from [C301], [C302], [C303]
- **C306** [quoted] Change detection is a filesystem watcher plus hourly full scans; the watcher batches changes for 10 s, so propagation is near-real-time when both devices are online — "It accumulates changes for 10s (adjustable by fsWatcherDelayS) and deleted files are further delayed for 1min." — [S36], Scanning
- **C307** [quoted] Received blocks are written to a temporary copy, not the live file, so a partially transferred file does not replace the target — "If it matches the block is written to a temporary copy of the file" — [S36], Blocks
- **C308** [quoted] Temporary partial-download files are cleaned after transfer or after 24 h by default — "Temporary files are used to store partial data downloaded from other devices." — [S37], How does Syncthing work / blocks
- **C309** [quoted] After reconnecting from offline, Syncthing only sees the latest change per file from each neighbour, then runs conflict resolution — "we only see the latest change for a given file or directory" — [S37], conflict / topology answer
- **C310** [quoted] No official Windows installer; docs list Task Scheduler, Startup folder, third-party wrappers, or a service — "There is currently no official installer available for Windows." — [S38], Windows
- **C311** [quoted] Built-in Windows autostart options are Task Scheduler (at logon or system startup) and the Startup folder — "Run at user log on or at system startup using Task Scheduler" — [S38], Windows
- **C312** [quoted] Running as a Windows service is done via third-party NSSM, with documented exit-code settings — "This can be achieved using NSSM, the “Non-Sucking Service Manager”." — [S38], Run as a service independent of user login
- **C313** [quoted] Third-party Windows GUI wrappers (installer, tray app) are pointed to from the docs rather than shipped — "There are a number of third-party utilities which aim to help install and run Syncthing more easily." — [S38], Install and run using third-party tools
- **C314** [quoted] All device-to-device traffic is TLS, and only devices whose certificate fingerprint (Device ID) is pre-listed can join — "All device to device traffic is protected by TLS." — [S39], Security Principles
- **C315** [quoted] Global discovery servers (default on, currently hosted by @calmh) learn device ID to IP mappings and who connects to whom; can be replaced with a self-run server — "The operator of the discovery server can map arbitrary device addresses to IP addresses, and deduce which devices are connected to each other." — [S39], Global Discovery
- **C316** [quoted] Pointing to a custom discovery server sends nothing to the default ones — "If a different global discovery server is configured, no data is sent to the default global discovery servers." — [S39], Global Discovery
- **C317** [quoted] Public relays are run by anyone, learn both device IDs, but cannot read data (end-to-end TLS) — "Any data exchanged between the two devices is encrypted as usual and not subject to inspection by the relay." — [S39], Relay Connections
- **C318** [quoted] Relaying defaults on and can be disabled or restricted to specific relays — "Syncthing can be configured to disable relaying, or only use specific relays." — [S39], Relay Connections
- **C319** [quoted] Untrusted (encrypted) devices feature is still labelled beta — "This feature should still be considered beta / testing only." — [S40], page banner
- **C320** [quoted] A folder password encrypts data sent to an untrusted device (e.g. a cloud server); other trusted devices can sync through it without contacting the origin — "There is also an untrusted device U1, perhaps a cloud server, where we want to sync data but in unreadable form." — [S40], intro
- **C321** [quoted] Trusted devices sync from the untrusted relay peer with the same password, so an encrypted always-on peer can stand in for simultaneous online devices — "have these sync the data from the untrusted device U1 without being in contact with T1" — [S40], intro
- **C322** [quoted] Encrypted on untrusted side: file data, names, times, hashes, structure; NOT protected: folder ID/label and file sizes — "File sizes (files grow a little on the encrypted side" — [S40], Technicals
- **C323** [quoted] Cipher: XChaCha20-Poly1305 and AES-SIV, key from password + folder ID via scrypt — "Encryption is XChaCha20-Poly1305 and AES-SIV with a key derived from the password and folder ID using scrypt." — [S40], Technicals
- **C324** [quoted] Untrusted device folder type must be Receive Encrypted — "On untrusted devices, you need to set the folder type to “Receive Encrypted”." — [S40], Configuration GUI
- **C325** [inference] Syncthing needs either two devices online at the same time or an always-on peer (own server, optionally as an encrypted untrusted device); there is no central store otherwise — from [C309], [C320], [C321]
- **C326** [quoted] bisync has been out of beta since rclone v1.71 (changelog on the bisync page; page lists up to v1.74.2) — "bisync is now officially released from beta." — [S41], Changelog, v1.71
- **C327** [quoted] Docs still warn it is an advanced command and data loss can result if the manual is not read — "bisync is considered an advanced command, so use with care." — [S41], Bisync intro
- **C328** [quoted] A bisync conflict = file new/changed on both sides since the prior run and not currently identical — "a "conflict" is a file that is new or changed on both sides (relative to the prior run) AND is not currently identical on both sides" — [S41], --conflict-resolve
- **C329** [quoted] Default --conflict-resolve none keeps both, renamed file.txt.conflict1 / .conflict2, copied to both sides; no merge — "file.txt on Path1 is renamed file.txt.conflict1 and file.txt on Path2 is renamed file.txt.conflict2" — [S41], --conflict-resolve
- **C330** [quoted] --conflict-resolve can pick a winner by newer, older, larger, smaller, path1 or path2; the loser is renamed or deleted per --conflict-loser — "The older file (the "loser") is handled according to --conflict-loser and --conflict-suffix settings (either renamed or deleted.)" — [S41], --conflict-resolve
- **C331** [quoted] --conflict-loser options: num (default), pathname, delete; --conflict-suffix default 'conflict' — "Action to take on the loser of a sync conflict (when there is a winner) or on both files (when there is no winner): , num, pathname, delete (default: num)" — [S41], flags table
- **C332** [quoted] By default most errors abort and lock out future runs until --resync; --resilient lets the next scheduled run retry less-serious errors — "By default, most errors or interruptions will cause bisync to abort and require --resync to recover." — [S41], --resilient
- **C333** [quoted] --recover auto-recovers after an unclean shutdown via a backup listing, at a slightly higher conflict risk — "--recover carries with it a slightly increased chance of having conflicts" — [S41], --recover
- **C334** [quoted] Lock files from an interrupted run block all future runs forever unless --max-lock is set — "If --max-lock is 0 or not set, the default is that lock files will never expire" — [S41], --max-lock
- **C335** [quoted] Docs recommend --resilient --recover --max-lock 2m plus frequent schedule for unattended use — "consider setting a relatively short duration like --max-lock 2m along with --resilient and --recover, and a relatively frequent cron schedule" — [S41], --max-lock
- **C336** [quoted] Files changing during a run can still lose data; v1.66 snapshot model greatly reduced but did not remove this — "Files that change during a bisync run may result in data loss." — [S41], Concurrent modifications
- **C337** [quoted] Since v1.66 changes missed mid-run are picked up next run, but an error can still occur at the exact moment of read/write — "an error can still occur if a file happens to change at the exact moment it's being read/written by bisync" — [S41], Concurrent modifications
- **C338** [quoted] --inplace on Local/SFTP remotes skips temp files and can corrupt and propagate; docs say omit it — "It is therefore recommended to omit --inplace." — [S41], Concurrent modifications
- **C339** [quoted] No filesystem watching: bisync must be run on a schedule; on Windows via Task Scheduler — "Rclone does not yet have a built-in capability to monitor the local file system for changes and must be blindly run periodically." — [S41], Usage examples / Cron
- **C340** [quoted] Tested on Windows 8.1, Windows 10 Pro and Windows GitHub runners; working dir under AppData\Local\rclone\bisync — "Bisync has been tested on Windows 8.1, Windows 10 Pro 64-bit and on Windows GitHub runners." — [S41], Windows support
- **C341** [quoted] Docs show combining bisync with a crypt remote so sensitive files sit encrypted on the shared remote — "configure an rclone crypt remote to point to a subdirectory within the local disk tree" — [S41], Sharing an encrypted folder tree between hosts
- **C342** [quoted] Lock files mean concurrent scheduled runs on the same path pair are serialised — "bisync can safely run in concurrent cron jobs thanks to lock files it maintains" — [S41], Getting started
- **C343** [inference] bisync syncs a pair of paths, so 3 devices means each device bisyncs against one hub remote (own SFTP server or crypt-over-cloud); the hub must be reachable, but devices need not be online together; conflict detection is per run so the sync window is the schedule interval — from [C328], [C339], [C341]
- **C344** [inference] Neither tool merges text: both produce a whole-file loser copy (.sync-conflict-* / .conflictN), so concurrent appends to decisions.md on two devices always need a manual or scripted merge — from [C301], [C329]
- **C345** [quoted] User with Syncthing + Obsidian reports regular conflicts handled manually — "I'm using syncthing with Obsidian but of course i have regular conflicts which i just deal with manually." — [S42], comment 2023-08-24
- **C346** [quoted] User left Syncthing for Obsidian Sync over the overhead of cleaning conflict files when a vault is open on two devices; conflicts themselves easy — "you're always thinking about if you're going to have to clean up a bunch of sync conflict files later" — [S43], comment 2026-02-28
- **C347** [quoted] Counter-report: three intermittently syncing devices, no conflicts recalled — "I cannot recall ever having a sync conflict." — [S44], comment 2024-01-17
- **C348** [quoted] Counter-report: ~500-file Obsidian dir over 3 devices + server, a handful of conflicts in a year — "I don’t think I’ve seen more than a handful of conflicts" — [S45], comment 2023-06-25
- **C349** [inference] Field reports split: single-writer-at-a-time use rarely conflicts; same file open/edited on two devices produces recurring conflict copies; this matches the doc model of whole-file loser copies — from [C301], [C345], [C346], [C347], [C348]
- **C350** [quoted] Forum user: dozens of .sync-conflicts syncing an Obsidian vault between two Macs on default settings — "But I end up with dozens of .sync-conflicts." — [S46], post 1, 2022-10-17
- **C351** [quoted] Forum user (Windows + SyncTrayzor + Android, v2.0.12): conflicts appear even when a note is edited on one device only, especially right after file creation — "editing on only one device (in Obsidian) and a conflict file appears for no apparent reason" — [S47], post 5, 2026-01-03
- **C352** [quoted] A forum regular attributes such cases to many saves from more than one device at about the same time, not to Syncthing — "Lots of saves seems to mean more opportunities for conflicts. Only if they happen in more than one device at more or less the same time." — [S47], post 8
- **C353** [quoted] Forum helper: topology (star vs mesh) should not matter; conflicts need both peers to have modified before syncing — "This shouldn’t lead to a conflict unless both B and C have modified the file before trying to sync it with each other." — [S48], post 2, 2024-02-17
- **C354** [quoted] Long-open feature request for a merge/select-winner conflict tool (2015) confirms there is no built-in merge — "I was thinking if something like git merge tool would be possible?" — [S49], issue body, state open
- **C355** [quoted] Original SyncTrayzor is unmaintained/archived; README points to the GermanCoding fork — "SyncTrayzor is unmaintained" — [S50], README
- **C356** [quoted] Syncthing community page lists SyncTrayzor v2 (fork, Syncthing v2) and Syncthing Windows Setup (Inno Setup installer with auto-start) for Windows — "SyncTrayzor v2 (GermanCoding’s fork of SyncTrayzor, updated for Syncthing v2)" — [S51], Windows
- **C357** [measured] GermanCoding/SyncTrayzor not archived, pushed 2026-10-15, latest release v2.2.0 (2026-07-18); canton7/SyncTrayzor archived — Own measurements, M14
- **C358** [quoted] An rclone bisync bug (closed 2026-10-14) silently reverted one-sided deletes when paths share no hash type and --ignore-checksum is set, reproduced on v1.75.1 — "If that file is later deleted on one side, bisync sees it as a new file on the other side and copies it back, so the delete is silently reverted." — [S52], issue body
- **C359** [quoted] Syncthing 3-device report on Windows 10, v2.1.5, of out-of-sync and conflicts after adding a third device, closed not-planned as support request — "after adding a third device, the original device starts reporting **Folder Out of Sync** and file conflicts" — [S53], issue body
- **C360** [quoted] git-crypt's own README says it is not the best tool for encrypting most or all files of a repo and points to git-remote-gcrypt for that — "git-crypt is not the best tool for encrypting most or all of the files in a repository" — [S54], Limitations
- **C361** [quoted] git-remote-gcrypt has a longstanding bug that every push is effectively a force push — "A longstanding bug is that every git push effectively has a ``--force``." — [S55], gcrypt.require-explicit-force-push
- **C362** [quoted] Over an arbitrary git URL or sftp, git-remote-gcrypt uploads the whole history on every push, and rsync:// does not work with GitHub/GitLab hosting — "requires uploading the entire repository history with each push" — [S55], Performance
- **C363** [measured] With a git-crypt-like clean/smudge filter (NUL-prefixed blob in the repo) plus merge=union, concurrent appends to decisions.md end in "Cannot merge binary files" and a UU conflict — the filter disables the union driver — Own measurements, M4
- **C364** [inference] Encrypting the memory repo at rest on a hosted remote costs the clean append merge: a git-crypt-like clean/smudge filter turned a union append into a binary conflict (C363), and gcrypt by default makes every push effectively a force push (a require-explicit-force-push flag makes it refuse un-forced pushes) (C361); a self-hosted plaintext remote keeps union merges — from [C360], [C361], [C363], [C246]

### Q4 — DB-backed FUSE / virtual filesystems on Windows — answered with a gap

- **C401** [quoted] rclone mount on Windows requires installing WinFsp, which provides the FUSE emulation layer rclone uses via cgofuse — "To run rclone mount on Windows, you will need to download and install WinFsp." — [S56], Installing on Windows
- **C402** [quoted] rclone mount docs warn that file systems expect 100% reliability while remote storage is not, and mount cannot retry like sync/copy without local copies of uploads — "rclone mount can't use retries in the same way without making local copies of the uploads." — [S56], rclone mount vs rclone sync/copy
- **C403** [quoted] Without a VFS cache mode, rclone mount can only write files sequentially and many applications will not work with their files — "This means that many applications won't work with their files on an rclone mount without --vfs-cache-mode writes or --vfs-cache-mode full." — [S56], Limitations
- **C404** [quoted] With --vfs-cache-mode off, files cannot be opened for both read and write, and a failed upload cannot be retried — "If an upload fails it can't be retried" — [S56], --vfs-cache-mode off (also minimal)
- **C405** [quoted] In writes mode (and full, which is otherwise identical), all normal file operations should work and failed uploads are retried with exponential backoff capped at 1 minute — "If an upload fails it will be retried at exponentially increasing intervals up to 1 minute." — [S56], --vfs-cache-mode writes
- **C406** [quoted] In full mode all reads and writes go through an on-disk sparse-file cache that tracks which parts were downloaded — "In this mode all reads and writes are buffered to and from disk." — [S56], --vfs-cache-mode full
- **C407** [quoted] Written files are uploaded only after close plus the --vfs-write-back delay (default 5s); pending uploads survive an rclone crash and resume on next run with the same flags — "If rclone is quit or dies with files that haven't been uploaded, these will be uploaded next time rclone is run with the same flags." — [S56], VFS File Caching
- **C408** [quoted] Cached files are evicted after --vfs-cache-max-age since last access (default 1h), so the full-mode cache is not a durable offline replica by default — "The default value of 1 hour will start evicting files from cache that haven't been accessed for 1 hour." — [S56], VFS File Caching
- **C409** [quoted] Changes made on the remote by another rclone instance (another device) are seen only after the directory cache expires (default 5m) unless the backend supports change polling — "changes made directly on the cloud storage by the web interface or a different copy of rclone will only be picked up once the directory cache expires if the backend configured does not support polling for changes." — [S56], VFS Directory Cache
- **C410** [quoted] Running two rclone instances on the same VFS cache with overlapping remotes can corrupt data — "This can potentially cause data corruption if you do." — [S56], VFS File Caching
- **C411** [quoted] On Windows rclone mounts as a fixed disk by default and can mount as a network drive with --network-mode; kernel write-back caching is not supported on Windows — "Makes kernel buffer writes before sending them to rclone (without this, writethrough caching is used) (not supported on Windows)" — [S56], flags, --write-back-cache
- **C412** [inference] The rclone mount page describes no offline mode: there is no documented guarantee that directory listing or uncached reads work while the remote is unreachable, only that pending uploads are retried — from [C402], [C405], [C407], [C408]
- **C413** [quoted] JuiceFS Enterprise 5.2+ runs on Windows but its Windows client is labelled Beta — "Please note that the Windows client is currently in Beta phase, make sure you read the following instructions carefully." — [S57], intro
- **C414** [quoted] The JuiceFS Windows client requires WinFsp because Windows has no native FUSE — "To run JuiceFS on Windows, you must install WinFsp, an open-source implementation of FUSE for Windows." — [S57], Install
- **C415** [quoted] On Windows, JuiceFS on the 2025 WinFsp beta cannot guarantee close-open consistency, because WinFsp does not block on CloseHandle cleanup like Linux FUSE — "JuiceFS on the current WinFsp beta (2025) cannot guarantee close-open consistency as Linux can." — [S57], Close-Open Consistency
- **C416** [quoted] JuiceFS stores names case-sensitively but ignores case on Windows, so names differing only by case misbehave — "If you happen to have two files in the same directory whose names differ only by case (e.g. a.txt and A.TXT), you may see unexpected behavior." — [S57], Case sensitivity
- **C417** [quoted] JuiceFS on Windows has no automatic mount at startup; Task Scheduler or winsw are suggested — "Currently, JuiceFS does not support automatic mounting on Windows." — [S57], Auto mount
- **C418** [quoted] The open-source Community Edition ships a precompiled juicefs.exe for Windows (also via Scoop or the Linux client in WSL), again on top of WinFsp — "There are three ways to use JuiceFS on Windows systems." — [S58], Windows
- **C419** [quoted] JuiceFS default consistency is close-to-open across clients, with a 1s kernel metadata cache by default — "after a client modified and closed a file, other clients will see the latest state when they open this file again." — [S59], Consistency
- **C420** [quoted] By default a JuiceFS write is not committed to the metadata service until its data is uploaded to object storage — "To ensure data security, client will not commit file writes to the Metadata Service until data is uploaded to object storage." — [S59], Client write cache
- **C421** [quoted] With --writeback, JuiceFS commits to the metadata service first and uploads data asynchronously from the local cache dir, so the metadata service is still contacted on every write — "file writes will not be blocked by data uploads, instead it will be written to the local cache directory and committed to the metadata service, and then returned immediately." — [S59], Client write cache
- **C422** [inference] JuiceFS has no offline mode: both write paths go through the remote metadata engine (Redis/Postgres etc.), so a laptop that cannot reach the metadata engine cannot commit writes — from [C420], [C421]
- **C423** [quoted] WinFsp lets user-mode programs implement Windows drives, FUSE-like, via a kernel-mode FSD plus a user-mode DLL — "The core WinFsp consists of a kernel mode file system driver (FSD) and a user mode DLL." — [S60], Overview
- **C424** [quoted] WinFsp claims (self-description) stability with no known kernel crashes or leaks, backed by its testing regime — "Stable software without any known kernel mode crashes, resource leaks or similar problems." — [S60], Stability
- **C425** [quoted] WinFsp exposes Native, FUSE2, FUSE3 and .NET APIs, so a custom DB-backed FS can be written in C/C++, any FUSE binding, or .NET — "Includes Native, FUSE2, FUSE3 and .NET API's." — [S60], Flexible API
- **C426** [quoted] WinFsp is GPLv3 with a FLOSS exception, commercial license available — "Available under the [GPLv3](License.txt) license with a special exception for Free/Libre and Open Source Software." — [S60], Flexible licensing
- **C427** [measured] WinFsp latest stable release is v2.1 "WinFsp 2025" (2025-06-05); v2.2 "WinFsp 2026" is in beta (Beta5 on 2026-10-13) — Own measurements, M10
- **C428** [quoted] Dokany is a user-mode FS layer with a kernel driver (dokan2.sys) and a FUSE wrapper for porting FUSE filesystems — "dokany includes a [FUSE wrapper](https://github.com/dokan-dev/dokany/wiki/FUSE) that helps you to port your FUSE filesystems without changes." — [S61], intro
- **C429** [quoted] Dokany ships signed drivers with every release, and is LGPL (driver, DLLs) plus MIT (tools, samples) — "**Signed Release and Debug drivers** are provided at each release for all platforms." — [S61], Signed drivers
- **C430** [measured] Dokany latest release is v2.3.1.1000 (2025-09-28, non-prerelease); previous v2.3.0.1000 2025-04-19 — Own measurements, M10
- **C431** [inference] rclone mount and JuiceFS on Windows both require WinFsp, and both WinFsp and Dokany install a kernel-mode driver on each Windows device — from [C401], [C414], [C423], [C428]
- **C432** [quoted] postgresqlfs exposes a PostgreSQL instance's object structure (schemas, tables) as files for browsing, not a general file store, and is Linux FUSE (/dev/fuse, fusermount) — "It exposes the object structure of a PostgreSQL database instance as directories and files that you can operate on using file system tools." — [S62], README
- **C433** [measured] postgresqlfs was last pushed 2018-01-15 (110 stars); the gridfs-fuse (Imroy) and pgfuse (andreasbaumann) GitHub repos returned 404 — Own measurements, M11
- **C434** [snippet] The Imroy/gridfs-fuse README (per search summary) lists no directories, no permissions, and very experimental file writing, with no Windows mention — "no directories, no permissions, file creation/writing very experimental" — [S63], search snippet (repo now 404, not verifiable)
- **C435** [quoted] WinFsp's Known File Systems list includes remote/object-backed ones (JuiceFS, rclone, s3fs-fuse, objfs, sshfs-win, nfs-win, KS2.Drive for WebDAV) but no MongoDB, GridFS or SQL-database-backed general file store — "a distributed POSIX file system built on top of Redis and S3" — [S64], File Systems (JuiceFS entry; absence of DB entries read from the full list)
- **C436** [inference] No maintained off-the-shelf MongoDB/GridFS or Postgres-backed general filesystem for Windows turned up; the realistic DB-backed option on Windows is JuiceFS (metadata in Redis per [C435]) or a custom FS written against WinFsp/cgofuse — from [C432], [C433], [C435], [C418]
- **C437** [quoted] Open rclone issue (2024-08, label OS: Windows): file watchers on Windows do not consistently detect new files in a directory mounted with rclone — "File watchers doesn't detect files added by rclone mount on Windows" — [S65], title
- **C438** [quoted] The reporter reproduced the same missing-notification behaviour on a plain WinFsp mount without rclone — "Indeed the same issue happens on a directory mounted with WinFSP without rclone." — [S65], comment by felipecrs
- **C439** [quoted] WinFsp maintainer: notifications are reported only for operations that go through the local kernel, not for remote changes, unless the filesystem calls WinFsp's notify API — "By default WinFsp reports notifications for file system operations that happen via the local kernel, because it cannot know about files that are added remotely." — [S66], comment by billziss-gh
- **C440** [quoted] The notify API exists (cgofuse FileSystemHost.Notify), so a custom FS can push remote-change notifications itself — "It is possible to notify the kernel of remote file changes by using the [`FileSystemHost.Notify`]" — [S66], comment by billziss-gh
- **C441** [quoted] rclone maintainer on open issue #5465: upload errors are surfaced at Flush, but Windows ignores Flush's return code, so a failed write-back is not reported to the writing program — "Flush - this is what we are doing already but Windows ignores the return code" — [S67], comment by ncw
- **C442** [measured] Other open Windows rclone-mount issues: #9482 mount disconnects after idle (2026-06), #7321 kernel read-ahead causes BadFileDescriptor on write (2023), #5570 blue screen reading a mounted folder (2021), #2333 invalid Windows file names exported (2018) — Own measurements, M12
- **C443** [inference] For Claude Code memory on a mount, a write made on device A would not raise change notifications on device B; tools that rely on file watching would see it only on re-read — from [C437], [C439]
- **C444** [quoted] Open rclone feature request (2026-04, v1.73.4, Linux): an rclone mount with --vfs-cache-mode full cannot be started without internet, even with a local cache — "If you shut down your laptop and restart it somewhere without internet connectivity, the mount won't work until you regain internet connectivity." — [S68], issue body
- **C445** [quoted] Same reporter: files in the cache dir can still be read directly, but only by going around the mount — "Of course you can access the files in the cache, but that feels like a hack." — [S68], issue body
- **C446** [quoted] Nextcloud desktop client 3.2 shipped Virtual Files on Windows: files appear in the folder, download on first open, then stay available offline — "the first time you open a file, it will have to be downloaded. Afterward, it will remain available offline." — [S69], Virtual Files
- **C447** [quoted] Users can pin files offline before travelling, or set them online-only — "If you are going to travel without a internet connection, you can always right-click files to make them available offline." — [S69], Virtual Files
- **C448** [measured] The nextcloud/desktop source has a cfapi VFS backend (src/libsync/vfs/cfapi, beside openvfs, suffix, xattr); latest release v35.0.0 on 2026-10-12 — Own measurements, M13
- **C449** [inference] Nextcloud's Windows client keeps real local files (sync, with placeholder hydration and offline pinning) instead of a live mount, so unlike a mount it tolerates an offline laptop — from [C446], [C447], [C448]
- **C450** [prior] Windows Cloud Files API (cfapi) sync roots hold real NTFS placeholders that hydrate on demand; edits are local and the sync engine uploads later, unlike a WinFsp mount where every operation goes to the FS process — not fetched in this run

## Disconfirming evidence

- [C102] — query: `gh search issues --repo anthropics/claude-code "autoMemoryDirectory"` — no built-in sync found; open feature requests #87027 and #101522 ask for one [C142].
- [C116], [C126], [C130] — query: `gh issue list` on MarimerLLC/claude-utils, tawanorg/claude-sync ("windows OR conflict"), perfectra1n/claude-code-sync ("memory OR windows OR conflict").
  - tawanorg: open #31 (no Windows) [C134], #69 (false conflicts on append-only files), and #70 (truncation overwrite) [C135].
  - perfectra1n: #103 silent revert, closed 2026-10-10 [C129].
  - MarimerLLC: no issues [C123].
- [C141] — query: `gh search repos "claude memory sync" --sort updated` — 15 more 0–1-star repos, seen by name only [C145]; the two read add a Seafile backend but only on Linux [C146], [C147], or sync a different file set [C148]. Nothing found against.
- [C250] — query: WebSearch `git "merge=union" problem duplicate lines modified line both versions kept` — no source on the edited-line case; settled locally [C247], [C248].
- [C240] — query: HN Algolia comments `"merge=union"` — the only failure reported is occasional duplicates [C241]. Nothing against union on append-only files.
- [C222], [C229] — query: HN Algolia `git sync notes across devices conflicts lost` (0 hits), `obsidian git plugin lost notes` — one data-loss report, attributed to force-push, not to stop-on-conflict [C252], [C253].
- [C208] — query: `gh issue list GitJournal/git-auto-sync` — issue #7: users report the daemon never commits on Windows [C244].
- [C326] — query: `gh search issues rclone/rclone "bisync conflict"` / `"bisync data loss"` — #9939, a silently reverted delete [C358]; "stable" does not mean free of edge cases.
- [C301], [C344] — query: `gh search issues syncthing/syncthing "conflict"` — merge-tool request #1746 open since 2015 [C354]; no built-in merge.
- [C349] — query: forum.syncthing.net `obsidian conflict` — counter-reports of conflicts with single-device editing [C351], [C359]. The explanation offered (near-simultaneous saves) comes from a forum regular, not a maintainer [C352].
- [C424] — query: GitHub search `repo:rclone/rclone "mount windows"` — #5570, a blue screen reading an rclone (WinFsp) mount [C442]; weakens the self-claim, cause not established.
- [C405] — same query — #5465: failed uploads are not reported to the writer on Windows [C441].
- [C412] — query: `rclone mount offline remote unreachable vfs-cache-mode full` plus GitHub search `repo:rclone/rclone offline mode vfs` — no working offline mode documented; #9343 supports [C412] [C444].
- [C364] (encryption keeps union) — tested instead of searched: the filter+union run conflicts [C363] (M4).

## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | GitHub issues (tawanorg #31/#69/#70, perfectra1n #103, git-auto-sync #7, rclone #7985/#5465/#9343/#9939, syncthing #10904, claude-code #95693/#101500/#101522); HN threads [C240], [C241], [C252]–[C254], [C345]–[C348]; Syncthing forum [C350]–[C353] | No user reports for MarimerLLC (no issues) or cmsync |
| Specialists | Claude Code docs [C101]–[C113]; gitattributes docs [C205]–[C207]; tool READMEs and scripts; Syncthing and rclone docs; JuiceFS, WinFsp, Dokany docs; WinFsp maintainer [C439], rclone maintainer [C441]; a3nm blog [C235]–[C239] | Windows Cloud Files API from prior knowledge only [C450] |
| Data | Own measurements M1–M14 (local git experiments, GitHub metadata) | No benchmark or study of sync tools under concurrent appends found or searched; the local experiments stand in for it |
| Adversarial | Disconfirming searches above; HN Obsidian Git data loss [C252]; rclone Windows mount issues [C442] | No report on atomic save (temp + rename) failing on WinFsp/rclone mounts on Windows — search returned 0 |

Overruns, declared: every sub-question went past the three-full-read ceiling, each time because the brief named several separate tools.

- **Q1:** four repo searches plus READMEs of seven projects.
- **Q2:** about ten full reads (docs, four READMEs, two scripts, a blog, an issue and three HN trees).
- **Q3:** the Syncthing docs pages, the bisync manual and several forum threads.
- **Q4:** five searches, one over the ceiling of four, and more than three page reads.

The orchestrator added a fifth search to Q1 (the C141 disconfirm) and three reads to Q3 (git-crypt, gcrypt).

Tools: Firecrawl was not used. The floor (WebSearch, curl, gh) was used throughout. The Xu-Jiaqi root README was a 319-byte stub, so docs/README.md was read via gh api. The gcrypt web page was a stub, so the GitHub README.rst was read. One gh search errored on a field name and was rerun without it.

## Own measurements

All runs on mainPC, git 2.44.0.windows.1, Git Bash, in a temp directory; scripts in the scratch dir `exp/`.

### M1 — concurrent appends to an append-only file across two git clones

Command: `bash union_append.sh <none|union> <merge|rebase>`. The script sets up a bare remote and clones a and b; each clone appends a different line to decisions.md; a pushes; b commits and pulls.

Output, trimmed (CRLF warnings dropped):

- `none merge`: `CONFLICT (content): Merge conflict in decisions.md`. Status `UU decisions.md`; the file holds `<<<<<<< HEAD` / `=======` / `>>>>>>>` markers around the two entries.
- `union merge` (`.gitattributes`: `decisions.md merge=union`): `Auto-merging decisions.md`, clean status. File: `first entry`, `device B entry`, `device A entry`.
- `union rebase`: clean status. File: `first entry`, `device A entry`, `device B entry`.

### M2 — merge=union on a file edited in place (MEMORY.md-like)

Command: `bash union_inplace.sh`. Both clones rewrite the same line of MEMORY.md differently, with `MEMORY.md merge=union` set.

Output:
```
Auto-merging MEMORY.md
status:
--- MEMORY.md:
- Round 6: block A slipped to 18.10
- Round 6: block A closed 16.10
- Runners: off
```
No conflict was reported. Both contradictory versions of the line were kept, silently.

### M3 — memory volume and project-key derivation on this device

Command: `cd ~/.claude/projects && for d in */memory; do … ls | wc -l; cat * | wc -c; done`

Output (non-empty dirs):

| Directory | Files | Bytes |
|---|---|---|
| `C--Users-petrk-GitHub-redrobot/memory` | 24 | 454789 |
| `C--Users-petrk-GitHub-jarvis/memory` | 19 | 301607 |
| `C--Users-petrk-GitHub-jarvis-oss/memory` | 11 | 123621 |
| `C--Users-petrk-GitHub-jarvis-private/memory` | 6 | 63322 |

Four more directories hold under 15 KB each. There are 213 project dirs in total, 21 of them with a `memory/` subdir. A session in a redrobot worktree uses the main checkout's memory dir. This totals about 1 MB of text, small for a git repo.

### M4 — merge=union through a git-crypt-like clean/smudge filter

Command: `bash exp/filter_union.sh`.

- The clean filter stores `\0ENC\0` followed by base64 of the file; the smudge filter reverses it.
- `.gitattributes`: `decisions.md filter=fakecrypt merge=union`.
- Two clones append different lines; b pulls with merge.

Output:
```
stored blob starts with: \0 E N C \0 L S A y M D I
warning: Cannot merge binary files: decisions.md (HEAD vs. 804ece32…)
Auto-merging decisions.md
CONFLICT (content): Merge conflict in decisions.md
Automatic merge failed; fix conflicts and then commit the result.
status:
UU decisions.md
```
The working tree held only the first entry and device B's entry. A stored blob that git sees as binary bypasses the union driver.

### M5 — GitHub repo search for Claude memory sync projects

Command: `gh search repos "claude memory sync" --sort updated --limit 15 --json fullName,stargazersCount,pushedAt`

Output (name, stars, last push):
```
gagoar/claude-memory-sync 0 2026-10-14
Orfeo42/claude-memory-sync 0 2026-10-11
tahabozdemir/claude-memory-sync 0 2026-10-08
turbyho/claude-memory-sync 0 2026-10-07
BoxPistols/claude-memory-sync 1 2026-10-04
omersahin00/claude-memory-sync 0 2026-09-21
nicoladj77/claude-memory-syncer 0 2026-09-07
Xu-Jiaqi/claude-memory-sync 1 2026-08-31
Xu-Jiaqi/cmsync-e2e-test 0 2026-08-31
netzilla1130/claude-memory-sync 0 2026-08-23
BrentlBowers/claude-memory-sync 1 2026-08-13
muj-i/claude-memory-sync 0 2026-07-22
bbuschsg/claude-memory-sync 0 2026-07-14
DevKitRU/claude-memory-sync 1 2026-06-14
gjoris/claude-memory-sync 0 2026-06-04
```

### M6 — redrobot project dirs vs memory dir (Q1 subagent)

Commands:

- `ls ~/.claude/projects | grep -i redrobot` → 71 dirs.
- `test -d <dir>/memory` → true only for `C--Users-petrk-GitHub-redrobot`.

### M7 — repo metadata for the Q1 projects (Q1 subagent)

Commands:

- `gh api repos/<r>` for stars, pushed_at, license and archived.
- `gh release view -R <r>` for tag, date and asset names.
- `gh issue list -R MarimerLLC/claude-utils --state all` → empty.

The values are in [C117], [C123], [C125] and [C133].

### M8 — repo metadata for the Q2 git tools (Q2 subagent)

Command: `gh api repos/<o>/<r> --jq '.pushed_at,.stargazers_count,.open_issues_count,.archived'`, run for the four repos. The values are in [C201]–[C204].

### M9 — union on a journal and an index together (Q2 subagent)

Command: `union_test.sh`. It sets up a temp bare repo and clones A and B, with `.gitattributes` setting `decisions.md` and `MEMORY.md` to `merge=union`.

- **B:** appends "- d2 from B", edits MEMORY line 2 to fact=fromB and line 3 to "prune-me edited by B", and pushes.
- **A:** appends "- d3 from A", edits line 2 to fact=fromA, deletes line 3, then runs `git pull --rebase`.

Output: exit=0, status clean.

- decisions.md = d1, d2 from B, d3 from A.
- MEMORY.md = "line1 keep / line2 fact=fromB / line3 prune-me edited by B / line2 fact=fromA / line4 keep".
- Git printed LF→CRLF warnings.

### M10 — WinFsp and Dokany releases (Q4 subagent)

Commands: `gh api repos/winfsp/winfsp/releases[/latest]`; `gh api repos/dokan-dev/dokany/releases`. The values are in [C427] and [C430].

### M11 — DB-as-filesystem repos (Q4 subagent)

Command: `gh api repos/{Imroy/gridfs-fuse,petere/postgresqlfs,andreasbaumann/pgfuse}`. postgresqlfs was last pushed 2018-01-15 (110 stars); the other two returned 404.

### M12 — open rclone Windows mount issues (Q4 subagent)

Command: `gh api -X GET search/issues -f q='repo:rclone/rclone mount windows notify OR watcher OR "file change" in:title'`. The results are in [C442].

### M13 — Nextcloud desktop VFS backends (Q4 subagent)

Commands: `gh api repos/nextcloud/desktop/contents/src/libsync/vfs`; `releases/latest`. The values are in [C448].

### M14 — SyncTrayzor forks (Q3 subagent)

Command: `gh repo view` on GermanCoding/SyncTrayzor and canton7/SyncTrayzor, 2026-10-17. The values are in [C357].

## Open questions

- **Q1 — how to map project keys across devices.** The three devices may use different checkout paths or usernames, which changes the memory dir name [C115]. It is unconfirmed whether `autoMemoryDirectory` accepts any per-project placeholder. The docs describe none [C105]. Settled by: comparing `ls ~/.claude/projects` on all three devices, and reading the settings reference again for placeholders.
- **Q1 — junction versus autoMemoryDirectory.** Untested: whether pointing the memory dir at a git working tree with a directory junction behaves under Claude Code on Windows (cf. the OneDrive junction report [C142]). Settled by: a one-device trial.
- **Q2 — CRLF on the other two devices.** core.autocrlf on the other two devices was not checked [C251]. Settled by: `git config --show-origin core.autocrlf` on each.
- **Q2 — Claude Code's write pattern.** It is not established whether Claude Code rewrites a memory file whole or appends to it. This decides whether union sees an append. Settled by: diffing a memory file before and after an Edit-tool append in a test repo.
- **Q3 — Syncthing encrypted untrusted device.** Not tested in practice; it is beta [C319].
- **Q4 — atomic rename and locking on mounts.** Atomic rename-over-existing and file locking on WinFsp/rclone mounts on Windows: no source found. Cloud Files API details are prior knowledge only [C450].
- **Privacy choice.** Private GitHub or a self-hosted bare remote is a decision for Пётр, not a research gap. A self-hosted remote's availability and backup were not examined.
- **Q1 (audit) — memory placement is unverified.** The claims on autoMemoryDirectory had no disconfirming search, and whether one git tree can hold the same project's memory on all three devices is untested. Settled by: the `ls ~/.claude/projects` comparison and junction trial above, plus a search of claude-code issues for autoMemoryDirectory failures.
- **Q2 (audit) — gitwatch mid-rebase behaviour is prior only.** That `-M` misses a stopped rebase (C228) was not fetched, so C217 was narrowed. Settled by: reading `is_merging` in gitwatch.sh, or a conflicting-rebase run.
- **Q3 (audit) — Syncthing conflict cause and the untrusted mode are unresolved.** Single-device conflict reports are explained by a forum regular (near-simultaneous saves) and, in one reply, by a v1.22 bug; no maintainer statement or current-version test settles it, and the encrypted untrusted device was not tried. Settled by: a maintainer source or a two-device test on the current release, including one untrusted peer.
- **Q4 (audit) — two claims could not be checked.** The gridfs-fuse README is 404 (C434) and the Cloud Files API comparison is prior knowledge (C450); atomic rename and locking on mounts have no source. Settled by: Microsoft's cfapi documentation, and a rename-over-existing and lock test on a WinFsp/rclone mount.
- **Label verdict (audit) — what keeps it open.** The question requires private infra or E2E; the Summary leaves that choice open, and the per-device memory placement under git is untested. Settled by: Пётр choosing private GitHub or a self-hosted remote, and a three-device placement trial (project keys plus autoMemoryDirectory or junction) that works.

## Sources


- [S1] https://code.claude.com/docs/en/memory.md — https://code.claude.com/docs/en/memory.md — passage
- [S2] https://code.claude.com/docs/en/settings-reference.md — https://code.claude.com/docs/en/settings-reference.md — passage
- [S3] https://code.claude.com/docs/en/sessions.md — https://code.claude.com/docs/en/sessions.md — passage
- [S4] https://code.claude.com/docs/en/settings.md — https://code.claude.com/docs/en/settings.md — passage
- [S5] https://github.com/MarimerLLC/claude-utils/blob/main/README.md — https://github.com/MarimerLLC/claude-utils/blob/main/README.md — passage
- [S6] https://github.com/MarimerLLC/claude-utils/blob/main/docs/claude-memsync.md — https://github.com/MarimerLLC/claude-utils/blob/main/docs/claude-memsync.md — passage
- [S7] https://github.com/perfectra1n/claude-code-sync/blob/main/README.md — https://github.com/perfectra1n/claude-code-sync/blob/main/README.md — passage
- [S8] https://github.com/perfectra1n/claude-code-sync/issues/103 — https://github.com/perfectra1n/claude-code-sync/issues/103 — passage
- [S9] https://github.com/tawanorg/claude-sync/blob/main/README.md — https://github.com/tawanorg/claude-sync/blob/main/README.md — passage
- [S10] https://github.com/tawanorg/claude-sync/issues/31 — https://github.com/tawanorg/claude-sync/issues/31 — passage
- [S11] https://github.com/tawanorg/claude-sync/issues/70 — https://github.com/tawanorg/claude-sync/issues/70 — passage
- [S12] https://github.com/MikeVeerman/jean-claude/blob/master/README.md — https://github.com/MikeVeerman/jean-claude/blob/master/README.md — passage
- [S13] https://github.com/kneetworks/claude-sync/blob/main/README.md — https://github.com/kneetworks/claude-sync/blob/main/README.md — passage
- [S14] https://github.com/ikook-wang/cc-sync-legacy/blob/main/README.md — https://github.com/ikook-wang/cc-sync-legacy/blob/main/README.md — passage
- [S15] https://github.com/sunjinpak/claude-code-memory-sync/blob/main/README.md — https://github.com/sunjinpak/claude-code-memory-sync/blob/main/README.md — passage
- [S16] https://github.com/elizabethfuentes12/claude-code-dotfiles/blob/main/README.md — https://github.com/elizabethfuentes12/claude-code-dotfiles/blob/main/README.md — passage
- [S17] https://github.com/anthropics/claude-code/issues/101522 — https://github.com/anthropics/claude-code/issues/101522 — passage
- [S18] https://github.com/anthropics/claude-code/issues/101500 — https://github.com/anthropics/claude-code/issues/101500 — passage
- [S19] https://github.com/anthropics/claude-code/issues/95693 — https://github.com/anthropics/claude-code/issues/95693 — passage
- [S20] https://github.com/Xu-Jiaqi/claude-memory-sync/blob/main/docs/README.md — https://github.com/Xu-Jiaqi/claude-memory-sync/blob/main/docs/README.md — passage
- [S21] https://github.com/BrentlBowers/claude-memory-sync/blob/main/README.md — https://github.com/BrentlBowers/claude-memory-sync/blob/main/README.md — passage
- [S22] https://git-scm.com/docs/gitattributes — https://git-scm.com/docs/gitattributes — passage
- [S23] https://raw.githubusercontent.com/GitJournal/git-auto-sync/HEAD/README.md — https://raw.githubusercontent.com/GitJournal/git-auto-sync/HEAD/README.md — passage
- [S24] https://raw.githubusercontent.com/gitwatch/gitwatch/HEAD/README.md — https://raw.githubusercontent.com/gitwatch/gitwatch/HEAD/README.md — passage
- [S25] https://raw.githubusercontent.com/gitwatch/gitwatch/HEAD/gitwatch.sh — https://raw.githubusercontent.com/gitwatch/gitwatch/HEAD/gitwatch.sh — passage
- [S26] https://raw.githubusercontent.com/simonthum/git-sync/HEAD/README.md — https://raw.githubusercontent.com/simonthum/git-sync/HEAD/README.md — passage
- [S27] https://raw.githubusercontent.com/simonthum/git-sync/HEAD/git-sync — https://raw.githubusercontent.com/simonthum/git-sync/HEAD/git-sync — passage
- [S28] https://raw.githubusercontent.com/Vinzent03/obsidian-git/HEAD/docs/Conflict%20resolution.md — https://raw.githubusercontent.com/Vinzent03/obsidian-git/HEAD/docs/Conflict%20resolution.md — passage
- [S29] https://raw.githubusercontent.com/Vinzent03/obsidian-git/HEAD/docs/Common%20issues.md — https://raw.githubusercontent.com/Vinzent03/obsidian-git/HEAD/docs/Common%20issues.md — passage
- [S30] https://a3nm.net/blog/git_auto_conflicts.html — https://a3nm.net/blog/git_auto_conflicts.html — passage
- [S31] https://hn.algolia.com/api/v1/items/32124145 — https://hn.algolia.com/api/v1/items/32124145 — passage
- [S32] https://hn.algolia.com/api/v1/items/8128510 — https://hn.algolia.com/api/v1/items/8128510 — passage
- [S33] https://github.com/GitJournal/git-auto-sync/issues/7 — https://github.com/GitJournal/git-auto-sync/issues/7 — passage
- [S34] https://hn.algolia.com/api/v1/items/38813211 — https://hn.algolia.com/api/v1/items/38813211 — passage
- [S35] https://hn.algolia.com/api/v1/items/38814000 — https://hn.algolia.com/api/v1/items/38814000 — passage
- [S36] https://docs.syncthing.net/users/syncing.html — https://docs.syncthing.net/users/syncing.html — passage
- [S37] https://docs.syncthing.net/users/faq.html — https://docs.syncthing.net/users/faq.html — passage
- [S38] https://docs.syncthing.net/users/autostart.html — https://docs.syncthing.net/users/autostart.html — passage
- [S39] https://docs.syncthing.net/users/security.html — https://docs.syncthing.net/users/security.html — passage
- [S40] https://docs.syncthing.net/users/untrusted.html — https://docs.syncthing.net/users/untrusted.html — passage
- [S41] https://rclone.org/bisync/ — https://rclone.org/bisync/ — passage
- [S42] https://news.ycombinator.com/item?id=37253055 — https://news.ycombinator.com/item?id=37253055 — passage
- [S43] https://news.ycombinator.com/item?id=47198841 — https://news.ycombinator.com/item?id=47198841 — passage
- [S44] https://news.ycombinator.com/item?id=39029474 — https://news.ycombinator.com/item?id=39029474 — passage
- [S45] https://news.ycombinator.com/item?id=36470057 — https://news.ycombinator.com/item?id=36470057 — passage
- [S46] https://forum.syncthing.net/t/19101 — https://forum.syncthing.net/t/19101 — passage
- [S47] https://forum.syncthing.net/t/25954 — https://forum.syncthing.net/t/25954 — passage
- [S48] https://forum.syncthing.net/t/21665 — https://forum.syncthing.net/t/21665 — passage
- [S49] https://github.com/syncthing/syncthing/issues/1746 — https://github.com/syncthing/syncthing/issues/1746 — passage
- [S50] https://github.com/canton7/SyncTrayzor — https://github.com/canton7/SyncTrayzor — passage
- [S51] https://docs.syncthing.net/users/contrib.html — https://docs.syncthing.net/users/contrib.html — passage
- [S52] https://github.com/rclone/rclone/issues/9939 — https://github.com/rclone/rclone/issues/9939 — passage
- [S53] https://github.com/syncthing/syncthing/issues/10904 — https://github.com/syncthing/syncthing/issues/10904 — passage
- [S54] https://raw.githubusercontent.com/AGWA/git-crypt/master/README.md — https://raw.githubusercontent.com/AGWA/git-crypt/master/README.md — passage
- [S55] https://raw.githubusercontent.com/spwhitton/git-remote-gcrypt/master/README.rst — https://raw.githubusercontent.com/spwhitton/git-remote-gcrypt/master/README.rst — passage
- [S56] https://rclone.org/commands/rclone_mount/ — https://rclone.org/commands/rclone_mount/ — passage
- [S57] https://juicefs.com/docs/cloud/reference/windows_usage — https://juicefs.com/docs/cloud/reference/windows_usage — passage
- [S58] https://juicefs.com/docs/community/getting-started/installation — https://juicefs.com/docs/community/getting-started/installation — passage
- [S59] https://juicefs.com/docs/community/guide/cache — https://juicefs.com/docs/community/guide/cache — passage
- [S60] https://github.com/winfsp/winfsp/blob/master/README.md — https://github.com/winfsp/winfsp/blob/master/README.md — passage
- [S61] https://github.com/dokan-dev/dokany/blob/master/README.md — https://github.com/dokan-dev/dokany/blob/master/README.md — passage
- [S62] https://github.com/petere/postgresqlfs — https://github.com/petere/postgresqlfs — passage
- [S63] https://github.com/Imroy/gridfs-fuse — https://github.com/Imroy/gridfs-fuse — snippet only
- [S64] https://winfsp.dev/doc/Known-File-Systems/ — https://winfsp.dev/doc/Known-File-Systems/ — passage
- [S65] https://github.com/rclone/rclone/issues/7985 — https://github.com/rclone/rclone/issues/7985 — passage
- [S66] https://github.com/winfsp/winfsp/issues/571 — https://github.com/winfsp/winfsp/issues/571 — passage
- [S67] https://github.com/rclone/rclone/issues/5465 — https://github.com/rclone/rclone/issues/5465 — passage
- [S68] https://github.com/rclone/rclone/issues/9343 — https://github.com/rclone/rclone/issues/9343 — passage
- [S69] https://help.nextcloud.com/t/nextcloud-desktop-client-3-2-with-status-feature-and-virtual-files-available-now/113533 — https://help.nextcloud.com/t/nextcloud-desktop-client-3-2-with-status-feature-and-virtual-files-available-now/113533 — passage

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED |  |
| C102 | SUPPORTED |  |
| C103 | SUPPORTED |  |
| C104 | SUPPORTED |  |
| C105 | SUPPORTED |  |
| C106 | PARTIAL | blockReadsOutsideWorkingDirectories half is from a different S2 entry, not the quote; narrowed to the workspace-trust part |
| C107 | SUPPORTED |  |
| C108 | SUPPORTED |  |
| C109 | SUPPORTED |  |
| C110 | SUPPORTED |  |
| C111 | SUPPORTED |  |
| C112 | PARTIAL | "the only built-in sync" goes beyond the quote (S2 also lists account-synced settings); narrowed to skills/plugins account sync |
| C113 | SUPPORTED | --quotes reports NOT FOUND because the page has the words inside a markdown link "[retention sweep](...)"; text present in the fetched memory.md, line 542 |
| C114 | SUPPORTED | re-ran: 71 redrobot dirs, memory/ only in C--Users-petrk-GitHub-redrobot |
| C115 | SUPPORTED |  |
| C116 | SUPPORTED |  |
| C117 | SUPPORTED | M7 records the command, not the output; re-ran gh api, values match |
| C118 | SUPPORTED |  |
| C119 | SUPPORTED |  |
| C120 | SUPPORTED |  |
| C121 | PARTIAL | "committed and pushed with markers" is about conflicts the MEMORY.md driver emits; non-MEMORY files only "surface as standard git conflict markers"; rewritten with that quote |
| C122 | PARTIAL | relied on the unstated premise that two EOF appends always conflict; narrowed to "a conflict there surfaces as markers" |
| C123 | SUPPORTED | re-ran, empty |
| C124 | SUPPORTED |  |
| C125 | SUPPORTED | re-ran gh api, values match |
| C126 | SUPPORTED |  |
| C127 | SUPPORTED |  |
| C128 | SUPPORTED |  |
| C129 | SUPPORTED |  |
| C130 | SUPPORTED |  |
| C131 | SUPPORTED |  |
| C132 | PARTIAL | README also offers optional shell hooks for auto push/pull; "manual push/pull" narrowed |
| C133 | SUPPORTED | re-ran gh api, values match |
| C134 | SUPPORTED |  |
| C135 | SUPPORTED |  |
| C136 | SUPPORTED |  |
| C137 | SUPPORTED |  |
| C138 | SUPPORTED |  |
| C139 | SUPPORTED |  |
| C140 | PARTIAL | kasimmj/claude-code-memory-sync is not in S16 or any listed source; clause dropped |
| C141 | PARTIAL | covers only the three main tools; MarimerLLC's "no encryption" rests on C122 (not mentioned), which C141 does not name; narrowed to those three |
| C142 | SUPPORTED |  |
| C143 | SUPPORTED |  |
| C144 | SUPPORTED |  |
| C145 | PARTIAL | M5 returned exactly 15 repos (= --limit) and only their names were seen; one is an e2e test repo; "such projects" narrowed to "repos named like" |
| C146 | SUPPORTED |  |
| C147 | SUPPORTED |  |
| C148 | SUPPORTED |  |
| C201 | PARTIAL | open_issues_count counts PRs too: 13 issues + 4 PRs; rewritten "17 open issues and PRs" |
| C202 | SUPPORTED | re-ran: 7 issues, 0 PRs |
| C203 | PARTIAL | the 1 is an open PR, 0 open issues; rewritten |
| C204 | PARTIAL | 104 = 90 issues + 14 PRs; rewritten |
| C205 | SUPPORTED |  |
| C206 | SUPPORTED |  |
| C207 | SUPPORTED |  |
| C208 | SUPPORTED |  |
| C209 | SUPPORTED |  |
| C210 | SUPPORTED |  |
| C211 | SUPPORTED |  |
| C212 | SUPPORTED |  |
| C213 | SUPPORTED |  |
| C214 | SUPPORTED |  |
| C215 | SUPPORTED |  |
| C216 | SUPPORTED |  |
| C217 | PARTIAL | the "-M misses a stopped rebase" step rests on C228 (prior), not on the claims named; narrowed to: push runs after a failed pull, no abort or notification |
| C218 | SUPPORTED |  |
| C219 | SUPPORTED |  |
| C220 | SUPPORTED |  |
| C221 | SUPPORTED |  |
| C222 | SUPPORTED |  |
| C223 | SUPPORTED |  |
| C224 | SUPPORTED |  |
| C225 | SUPPORTED |  |
| C226 | SUPPORTED |  |
| C227 | SUPPORTED |  |
| C228 | UNCHECKABLE | prior |
| C229 | SUPPORTED |  |
| C230 | SUPPORTED |  |
| C231 | SUPPORTED |  |
| C232 | SUPPORTED |  |
| C233 | SUPPORTED |  |
| C234 | SUPPORTED |  |
| C235 | SUPPORTED |  |
| C236 | SUPPORTED |  |
| C237 | SUPPORTED |  |
| C238 | SUPPORTED |  |
| C239 | SUPPORTED |  |
| C240 | SUPPORTED |  |
| C241 | SUPPORTED |  |
| C242 | SUPPORTED |  |
| C243 | SUPPORTED |  |
| C244 | PARTIAL | of the three post-v1.5 reports two name Windows 10, one (2022-09) names no version; none names 11; rewritten |
| C245 | PARTIAL | "usable only as manual" generalises three user reports; narrowed to "reported by users" |
| C246 | SUPPORTED |  |
| C247 | SUPPORTED |  |
| C248 | SUPPORTED |  |
| C249 | SUPPORTED |  |
| C250 | SUPPORTED |  |
| C251 | SUPPORTED | re-ran: core.autocrlf=true from the system gitconfig |
| C252 | SUPPORTED |  |
| C253 | PARTIAL | "the comment predates those docs" has no source; dropped |
| C254 | SUPPORTED |  |
| C301 | SUPPORTED |  |
| C302 | SUPPORTED |  |
| C303 | SUPPORTED |  |
| C304 | SUPPORTED |  |
| C305 | SUPPORTED |  |
| C306 | SUPPORTED |  |
| C307 | SUPPORTED |  |
| C308 | SUPPORTED |  |
| C309 | SUPPORTED |  |
| C310 | SUPPORTED |  |
| C311 | SUPPORTED |  |
| C312 | SUPPORTED |  |
| C313 | SUPPORTED |  |
| C314 | SUPPORTED |  |
| C315 | PARTIAL | page says the discovery servers are hosted by @calmh; "project lead" is not on the page; rewritten |
| C316 | SUPPORTED |  |
| C317 | SUPPORTED |  |
| C318 | SUPPORTED |  |
| C319 | SUPPORTED |  |
| C320 | SUPPORTED |  |
| C321 | SUPPORTED |  |
| C322 | SUPPORTED |  |
| C323 | SUPPORTED |  |
| C324 | SUPPORTED |  |
| C325 | SUPPORTED |  |
| C326 | SUPPORTED |  |
| C327 | SUPPORTED |  |
| C328 | SUPPORTED |  |
| C329 | SUPPORTED |  |
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
| C340 | SUPPORTED |  |
| C341 | SUPPORTED |  |
| C342 | SUPPORTED |  |
| C343 | SUPPORTED |  |
| C344 | SUPPORTED |  |
| C345 | SUPPORTED |  |
| C346 | SUPPORTED |  |
| C347 | SUPPORTED |  |
| C348 | SUPPORTED |  |
| C349 | SUPPORTED |  |
| C350 | SUPPORTED |  |
| C351 | SUPPORTED |  |
| C352 | SUPPORTED |  |
| C353 | SUPPORTED |  |
| C354 | SUPPORTED |  |
| C355 | SUPPORTED |  |
| C356 | SUPPORTED |  |
| C357 | SUPPORTED | re-ran gh api and gh release view; values match |
| C358 | SUPPORTED | read via gh issue view (script reported unfetchable); closed as COMPLETED 2026-10-14, linked PR #9940 closed unmerged |
| C359 | SUPPORTED | stateReason NOT_PLANNED confirmed |
| C360 | SUPPORTED |  |
| C361 | SUPPORTED |  |
| C362 | SUPPORTED |  |
| C363 | SUPPORTED |  |
| C364 | PARTIAL | C361 shows a forced push, not a lost append merge (gcrypt merges locally on plaintext objects); C363 is a git-crypt stand-in, not git-crypt; narrowed |
| C401 | SUPPORTED |  |
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
| C412 | SUPPORTED |  |
| C413 | SUPPORTED |  |
| C414 | SUPPORTED |  |
| C415 | SUPPORTED |  |
| C416 | SUPPORTED |  |
| C417 | SUPPORTED |  |
| C418 | SUPPORTED |  |
| C419 | SUPPORTED |  |
| C420 | SUPPORTED |  |
| C421 | SUPPORTED |  |
| C422 | SUPPORTED |  |
| C423 | SUPPORTED |  |
| C424 | SUPPORTED |  |
| C425 | SUPPORTED |  |
| C426 | SUPPORTED |  |
| C427 | SUPPORTED | re-ran gh api; values match |
| C428 | SUPPORTED |  |
| C429 | SUPPORTED |  |
| C430 | SUPPORTED | re-ran gh api; values match |
| C431 | PARTIAL | the named claims show rclone and JuiceFS need WinFsp and that WinFsp and Dokany install kernel drivers; "every DB-backed FS on Windows" needs an unstated premise (no other route, e.g. Cloud Files API); narrowed |
| C432 | SUPPORTED |  |
| C433 | SUPPORTED | re-ran gh api; values match |
| C434 | UNCHECKABLE | S63 repo returns 404; snippet only |
| C435 | SUPPORTED |  |
| C436 | SUPPORTED |  |
| C437 | PARTIAL | issue says new files in an rclone-mounted directory are not detected consistently; "by another machine" is not in the issue; narrowed |
| C438 | SUPPORTED |  |
| C439 | SUPPORTED |  |
| C440 | SUPPORTED | --quotes reports NOT FOUND because the plain-HTTP GitHub page renders the link; the quote is in the raw comment markdown (billziss-gh) read via gh issue view |
| C441 | SUPPORTED |  |
| C442 | PARTIAL | re-ran gh api on the four issues, values match; the recorded M12 query (notify/watcher in:title) cannot return them, so "found in the same search" dropped |
| C443 | SUPPORTED |  |
| C444 | SUPPORTED |  |
| C445 | SUPPORTED |  |
| C446 | SUPPORTED |  |
| C447 | SUPPORTED |  |
| C448 | SUPPORTED | re-ran gh api; values match |
| C449 | PARTIAL | named claims cover the client only; "the one self-hosted option" (Syncthing in Q3 also keeps local files) and the server-storage clause rest on no named claim; narrowed |
| C450 | UNCHECKABLE | prior |

Label verdict: open — the privacy requirement is left as Пётр's choice between a private GitHub repo and a self-hosted remote rather than answered, and the Q1 gap (how the same project's memory lands in one git tree on three devices whose project keys may differ, with per-project autoMemoryDirectory blocked in auto mode [C144] and the junction route untested) would, resolved unfavourably, change how the recommended git setup is built.
Quote check: Quote check memory-sync-backend-2026-10-17.md: 170 quoted claim(s): 168 found, 2 NOT FOUND, 0 unfetchable, 0 no source
