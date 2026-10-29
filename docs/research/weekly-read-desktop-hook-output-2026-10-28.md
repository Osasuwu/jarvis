---
topic: weekly-read-desktop-hook-output
tags: area:config, research
source_provenance: /grill #2172 research-pass gate, https://github.com/Osasuwu/jarvis/issues/2172
status: open
audit: 2026-10-28 — 86 claims: 69 SUPPORTED, 17 PARTIAL, 0 UNSUPPORTED, 0 UNCHECKABLE
---

## Question

Question (verbatim, from the /grill #2172 research-pass gate):

How does output from a Claude Code SessionStart hook (systemMessage, additionalContext, exit-2 stderr, MessageDisplay displayContent, terminalSequence notifications) reach the user in the Claude desktop app (Code tab), IDE extensions and Agent SDK hosts, versus the CLI; and what is the documented CLAUDE_CODE_ENTRYPOINT value set per host (cli, claude-desktop, IDE, sdk-*). Decision already leaning: relay via additionalContext in every non-cli entrypoint, agent repeats the user-facing line verbatim in its first reply; direct-channel desktop probe deferred to a follow-up. Want: anything that would flip that (a documented direct-to-user channel that desktop renders; entrypoint values that would misclassify a host).

Sub-questions:
Q1 — Per the Claude Code hooks reference, which SessionStart output channels reach the user and which reach the model (systemMessage, additionalContext, plain stdout, exit-2 stderr, terminalSequence, MessageDisplay, sessionTitle, initialUserMessage)?
Q2 — What do the desktop app, the IDE extensions and Agent SDK hosts render of those channels (documented behaviour and reported issues)?
Q3 — What CLAUDE_CODE_ENTRYPOINT values are documented or observed per host, and can a host be misclassified by an `entrypoint != cli` test?


No earlier report on this topic exists in `docs/research/`.

## Summary

Recommendation: keep the leaning decision. Relay the weekly-read pick through SessionStart
`additionalContext` on every entrypoint other than `cli`, with the agent repeating the user-facing
line verbatim, and defer the direct-channel desktop probe. Nothing found in this run flips it.

- **No direct SessionStart channel to the desktop user was found.** The documented user-facing
  SessionStart channels are systemMessage, exit-2 stderr as a hook-error notice, and sessionTitle;
  additionalContext and plain stdout go to Claude's context [C119]. In the desktop app (macOS and
  Windows) and the VS Code extension, a SessionStart hook's systemMessage is reported not to reach
  the user, and its exit-2 stderr was not shown in the macOS desktop app on 2.1.233 [C229]. Two of
  those reports were closed for inactivity or as a duplicate, not as fixed, the drop was still
  reported on 2.1.304, and no CHANGELOG line that mentions systemMessage is a rendering fix [C244].
  terminalSequence is ignored under the Agent SDK, through which the docs say Desktop hosts Claude
  Code [C118], [C120]. The only hook systemMessage reported visible in the desktop app is a Stop
  hook's, not a SessionStart hook's [C231].
- **The model channel works there.** SessionStart additionalContext is added before the first
  prompt, and for an interactive start, a resume at launch or /clear the first response waits for
  SessionStart hooks [C104], [C116]; desktop and VS Code reports confirm it reaches the model
  [C203], [C219]. Three reporters on desktop and VS Code describe a model relay of the user-facing
  line as their workaround [C230].
- **The `entrypoint != cli` test holds.** Every value documented or observed for a non-terminal
  host differs from `cli`, so the test sends each of them, and an unset or new value, to the relay
  [C310]. It misclassifies only when a terminal CLI reports a value other than `cli` or a
  non-terminal host reports `cli` [C311]. A positive allowlist of desktop values would leave the
  VS Code extension and SDK hosts without a relay [C312].

Caveats the decision should carry:

- The variable is not documented on the four docs pages checked, and its desktop values come from
  a third party's reading of the binary [C313]; a third-party host that sets it to `cli` gets no
  relay [C321].
- An interactive CLI launched from a shell that carries a non-`cli` value gets the relay as well
  as its systemMessage, so the line shows twice; a CLI started in the desktop app's Terminal panel
  does not inherit a non-`cli` value [C319].
- The CLI itself drops a SessionStart systemMessage in reported conditions [C232], so keeping the
  CLI on systemMessage only keeps a channel with known drops.
- If the desktop app later renders systemMessage, the relay shows the line twice [C206].
- A desktop rewind (source=fork) drops additionalContext, but the weekly-read hook does not run on
  fork [C233], [C242].
- Remote Control sessions report `sdk-cli` and so get the relay [C320].


## Findings

### Q1 — Which SessionStart output channels reach the user and which reach the model, per the hooks reference — answered

- **C101** [quoted] The hooks reference names systemMessage as the field for surfacing a message to the user on any platform, and says some events discard it or deliver it elsewhere — "To surface a message to the user on any platform, return [`systemMessage`](#json-output) in JSON output. Some events discard it or deliver it elsewhere, and each [event's section](#hook-events) says so." — [S1], Hook input and output
- **C102** [quoted] systemMessage is a warning shown to the user, and in Agent SDK and stream-json output it can arrive as an SDKInformationalMessage — "Warning message shown to the user. In [Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview.md) and [`--output-format stream-json`](https://code.claude.com/docs/en/headless) output, it can arrive as an [`SDKInformationalMessage`](https://code.claude.com/docs/en/agent-sdk/typescript#sdkinformationalmessage)" — [S1], JSON output, universal fields table
- **C103** [quoted] additionalContext is wrapped in a system reminder that Claude reads, and it does not appear as a chat message in the interface — "Claude reads the reminder on the next model request, but it doesn't appear as a chat message in the interface." — [S1], Add context for Claude
- **C104** [quoted] For SessionStart, additionalContext is added to Claude's context before the first prompt — "String added to Claude's context at the start of the conversation, before the first prompt." — [S1], SessionStart decision control
- **C105** [quoted] A SessionStart hook's plain-text stdout is also added to Claude's context — "because Claude Code adds a SessionStart hook's [plain-text stdout](#exit-code-0) to Claude's context." — [S1], SessionStart decision control
- **C106** [quoted] On exit 2 a SessionStart hook cannot block, and its stderr is shown to the user only — "| `SessionStart` | No | Shows stderr to user only |" — [S1], Exit code 2 behavior per event
- **C107** [quoted] Exit-2 stderr of SessionStart renders in the transcript as a "hook error" notice that Claude does not see — "For `SessionStart`, `SubagentStart`, and `PostModelSwitch`, Claude Code renders the exit code 2 stderr in the transcript as a `<hook name> hook error` notice, the same way it renders a [non-blocking error](#exit-code-output). Claude doesn't see it, and the session or subagent proceeds." — [S1], Exit code 2 behavior per event
- **C108** [quoted] When exit 2 and JSON are mixed, exit 2 keeps its blocking effect and Claude Code still reads the JSON fields, with one elicitation exception — "If you mix them, exit 2 keeps its [blocking effect](#exit-code-2-behavior-per-event), and Claude Code still reads the JSON fields, with the one elicitation exception noted under [Exit code 2](#exit-code-2)." — [S1], JSON output, note
- **C109** [quoted] terminalSequence is limited to an allowlist of window-title, notification and bell sequences — "Restricted to OSC `0`/`1`/`2`/`9`/`99`/`777` and BEL." — [S1], JSON output, universal fields table
- **C110** [quoted] terminalSequence is written only in an interactive session with its interface on screen, and is ignored in -p mode and in the Agent SDK — "Claude Code writes the sequence only in an interactive session, and only while its interface is on screen. In non-interactive mode with the `-p` flag and in the Agent SDK, it ignores the field." — [S1], Emit terminal notifications
- **C111** [quoted] MessageDisplay displayContent changes only what is rendered on screen, and the hook receives assistant message text only — "MessageDisplay is display-only: the replacement text changes only what is rendered on screen. … The hook receives assistant message text only" — [S1], MessageDisplay
- **C112** [quoted] In non-interactive runs, including Agent SDK queries and claude -p, MessageDisplay runs once per assistant message instead of once per batch of lines — "In non-interactive runs, including Agent SDK queries and `claude -p`, MessageDisplay runs once per assistant message instead of once per batch of lines." — [S1], MessageDisplay
- **C113** [quoted] SessionStart sessionTitle sets the session title like /rename, but only for startup, resume and fork sources — "Sets the session title, with the same effect as `/rename`. Applies when `source` is `"startup"`, `"resume"`, or `"fork"`" — [S1], SessionStart decision control
- **C114** [quoted] SessionStart initialUserMessage is used as the first user message of the session in non-interactive -p mode — "String used as the first user message of the session, in [non-interactive mode](https://code.claude.com/docs/en/headless.md) with the `-p` flag." — [S1], SessionStart decision control
- **C115** [quoted] Claude Code fires the same hook events in the terminal, IDE extensions, the desktop app and cloud sessions — "Claude Code fires the same hook events wherever it runs: sessions in the terminal, IDE extensions, the [Desktop app](https://code.claude.com/docs/en/desktop-quickstart.md), and [cloud sessions](https://code.claude.com/docs/en/claude-code-on-the-web.md)." — [S1], intro
- **C116** [quoted] On an interactive start, a resume at launch with --continue or --resume, or /clear, SessionStart hooks run in the background, and Claude's first response waits for them to finish, so their context reaches Claude — "When you start an interactive session, resume a conversation at launch with `--continue` or `--resume`, or run `/clear`, SessionStart hooks run in the background. … Claude's first response still waits for the hooks to finish, so their context reaches Claude." — [S1], SessionStart
- **C117** [quoted] additionalContext, systemMessage and initialUserMessage strings are each capped at 10,000 characters — "A hook's `additionalContext`, `systemMessage`, and `initialUserMessage` strings, and its plain stdout, are capped at 10,000 characters" — [S1], JSON output
- **C118** [quoted] Claude Desktop and the VS Code extension host Claude Code through the Agent SDK's canUseTool callback — "which is how Claude Desktop and the VS Code extension host Claude Code" — [S1], Notification, permission_prompt timing
- **C119** [inference] The documented user-facing SessionStart channels are systemMessage (which in Agent SDK output can arrive as an SDKInformationalMessage), exit-2 stderr as a hook-error notice, and sessionTitle; additionalContext reaches Claude and does not appear as a chat message, and plain stdout is added to Claude's context; terminalSequence is ignored under the Agent SDK; MessageDisplay changes only what is rendered and receives assistant message text only — from [C101], [C102], [C103], [C105], [C107], [C110], [C111], [C113]
- **C120** [inference] If Desktop hosts Claude Code through the Agent SDK, terminalSequence from a SessionStart hook is ignored in the desktop app — from [C110], [C118]
- **C121** [quoted] A hook process inherits the parent environment, apart from the OTEL_* exporter variables Claude Code removes, the variables it strips when CLAUDE_CODE_SUBPROCESS_ENV_SCRUB is set to 1, and, in a HIPAA-configured session, Anthropic credentials — "A hook process inherits the parent environment, apart from the `OTEL_*` exporter variables that Claude Code … and, when [`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`](https://code.claude.com/docs/en/env-vars#variables) is set to `1`, the variables it strips. In a session that [gets the HIPAA configuration](https://code.claude.com/docs/en/hipaa-setup.md#check-how-developers-sign-in-and-connect), Claude Code also [removes Anthropic credentials](https://code.claude.com/docs/en/hipaa-setup.md#anthropic-credentials-in-commands-hooks-and-mcp-servers) from the hook's environment." — [S1], Hook input and output

### Q2 — What the desktop app, the IDE extensions and Agent SDK hosts render of those channels — answered with a gap


#### Desktop app

- **C201** [quoted] In the desktop app, the transcript stores hook_system_message attachments for SessionStart, UserPromptSubmit and PreToolUse, but the user never sees them — "In the desktop app, the transcript stores `hook_system_message` attachments for SessionStart, UserPromptSubmit and PreToolUse, but the user never sees them." — [S6], issue body, What we measured (2026-10-20, Claude Code 2.1.304, macOS)
- **C202** [quoted] In the desktop app only a Stop hook's message shows, collapsed under a Claude Code notice — "Only a Stop hook's message shows, collapsed under "Claude Code notice"." — [S6], issue body, What we measured
- **C203** [quoted] In the desktop app additionalContext reaches the model on every event — "`additionalContext` reaches the model on every event, so the hooks do run." — [S6], issue body, What we measured
- **C204** [quoted] A repro comment counts hook_system_message stored in a desktop-only session per event, with only the Stop messages shown — "In a desktop-only session, `hook_system_message` is stored for SessionStart (9), UserPromptSubmit (3), PreToolUse (1) and Stop (2), but only the Stop messages were shown." — [S6], comment by vimox-shah-genea, 2026-10-20 (https://github.com/anthropics/claude-code/issues/103739#issuecomment-6291251118)
- **C205** [quoted] The #103739 reporter's workaround on a desktop entrypoint passes each user-facing line to the model with an instruction to repeat it word for word — "On a desktop entrypoint, our hooks pass each user-facing line to the model, with an instruction to repeat it word for word." — [S6], issue body, workaround
- **C206** [quoted] The same reporter names two costs of that workaround: it depends on the model following the instruction, and a line shows twice if the app later renders it — "it depends on the model following the instruction; … a line shows twice if the app later starts rendering it." — [S6], issue body, workaround
- **C207** [quoted] The same reporter says that in the CLI a hook's systemMessage shows to the user on every event — "In the CLI, a hook's `systemMessage` shows to the user on every event." — [S6], issue body, What we measured
- **C208** [quoted] For a UserPromptSubmit hook in the desktop app, systemMessage is silently dropped — "`systemMessage` is documented as a warning shown to the user; in the desktop app it is silently dropped." — [S7], issue body (2026-06-09), UserPromptSubmit channel matrix
- **C209** [quoted] In the same UserPromptSubmit matrix, plain stdout context injection works in both the CLI and the desktop app — "| plain stdout (context injection) | ✅ injected | ✅ injected |" — [S7], issue body, Channel matrix
- **C210** [quoted] A commenter reproduces the SessionStart systemMessage drop in the macOS desktop app on 2.1.233 — "Not just the VSCode extension panel. Claude Code **2.1.233**, macOS 26.5, arm64, plain local `~/.claude/settings.json`, no remote-control." — [S8], comment by mattlavine, 2026-08-16, section 1 (https://github.com/anthropics/claude-code/issues/80882#issuecomment-5309670328)
- **C211** [quoted] The same commenter finds SessionStart exit-2 stderr renders in the terminal CLI as a hook error but is not shown in the desktop app — "| exit-2 stderr | **renders** — `SessionStart:startup hook error … EXIT2-PROBE-9F3A` | **not shown** |" — [S8], comment by mattlavine, section 2 table (https://github.com/anthropics/claude-code/issues/80882#issuecomment-5309670328)
- **C212** [quoted] The same commenter concludes that on non-terminal clients a SessionStart hook has no way to say anything to the user — "**So on non-terminal clients there is currently no way for a `SessionStart` hook to say anything to the user.**" — [S8], comment by mattlavine, section 2 (https://github.com/anthropics/claude-code/issues/80882#issuecomment-5309670328)
- **C213** [quoted] A commenter reproduces the drop in the Windows desktop app on 2.1.251 — "Confirming on a fourth client configuration — the **Windows desktop app**" — [S8], comment by adriaan-wessels, 2026-08-30 (https://github.com/anthropics/claude-code/issues/80882#issuecomment-5468463223)
- **C214** [quoted] In the same Windows desktop session, a Stop hook's root-level systemMessage rendered as a visible Claude Code notice — "a `Stop` hook returning a root-level `systemMessage` rendered normally as a visible "Claude Code notice" in the transcript" — [S8], comment by adriaan-wessels (https://github.com/anthropics/claude-code/issues/80882#issuecomment-5468463223)
- **C215** [quoted] The same commenter states the only reliable user-visible delivery for SessionStart information on these surfaces is asking the model to relay additionalContext — "the only reliable user-visible delivery for SessionStart information on these surfaces is asking the model to relay `additionalContext` — a workaround, not a channel." — [S8], comment by adriaan-wessels (https://github.com/anthropics/claude-code/issues/80882#issuecomment-5468463223)
- **C216** [quoted] The desktop docs say hooks and skills defined in settings apply to both the CLI and Desktop — "* **[Hooks](https://code.claude.com/docs/en/hooks.md)** and **[skills](https://code.claude.com/docs/en/skills.md)** defined in settings apply to both" — [S2], Shared configuration
- **C217** [quoted] The desktop docs say --print and --output-format are not available in Desktop, which is interactive only — "| `--print`, `--output-format` | Not available. Desktop is interactive only. |" — [S2], CLI flag equivalents table
- **C218** [measured] The desktop docs page does not mention systemMessage — Own measurements, M2

#### IDE extension

- **C219** [quoted] In the VS Code extension panel a SessionStart hook's additionalContext is ingested while its systemMessage is dropped — "The hook's `additionalContext` output is ingested correctly on both surfaces (the model receives it); only the user-visible `systemMessage` is dropped in the extension panel." — [S8], issue body (2026-07-24)
- **C220** [quoted] A VS Code-on-Windows user's workaround drops systemMessage and instructs the model via additionalContext to relay the status as its own chat text — "Workaround in use: drop `systemMessage` entirely and instruct the model via `additionalContext` to proactively relay the status as its own chat text at session start" — [S8], comment by guruchill, 2026-09-03 (https://github.com/anthropics/claude-code/issues/80882#issuecomment-5530910271)

#### Terminal CLI

- **C221** [quoted] After /clear, a SessionStart systemMessage is not shown in the default terminal renderer, measured 0 of 17 — "- 0/17 displayed, across plugin vs `settings.json` registration, hook latency 0 to 3 s, with and without a status line, with and without `--debug-file`." — [S9], issue body (2026-09-24, CLI 2.1.281)
- **C222** [quoted] In the same /clear runs, additionalContext reached the model 17 of 17 times — "The hook's `additionalContext` reaches the model (17/17)" — [S9], issue body
- **C223** [quoted] With the fullscreen TUI the /clear message is shown — "With `tui: "fullscreen"` it is shown (2/2)." — [S9], issue body
- **C224** [quoted] On a plain interactive startup on 2.1.278 the SessionStart systemMessage was shown only some of the time, measured on 15 starts — "We measured **4 of 15** interactive starts on 2.1.278" — [S10], issue body (2026-09-29)
- **C225** [quoted] On those startups additionalContext reached the model every time it was checked — "On the same starts, the hook's `additionalContext` reached the model every time we checked (3/3)." — [S10], issue body
- **C226** [quoted] On the CLI startup path, exit-2 stderr is not a more reliable channel — "Emitting on stderr with exit code 2 is not a more reliable alternative." — [S10], issue body
- **C227** [quoted] A commenter on Windows saw the systemMessage dropped on all 9 launches with an initial prompt in one config home — "the `systemMessage` was dropped on all 9 test launches with an initial prompt" — [S10], comment by FlorinI, 2026-10-04 (https://github.com/anthropics/claude-code/issues/98162#issuecomment-5982057123)
- **C228** [quoted] On continue, resume and fork the SessionStart systemMessage is not displayed when the hook's additionalContext is byte-identical to one already in the transcript — "a SessionStart hook's `systemMessage` is silently not displayed whenever the hook's `additionalContext` is byte-identical to a SessionStart `additionalContext` already present in the transcript." — [S11], issue body (2026-09-24, CLI 2.1.281)

#### Inferences

- **C229** [inference] In the desktop app (macOS on 2.1.233 and 2.1.304, Windows on 2.1.251) and the VS Code extension, a SessionStart hook's systemMessage is reported not to reach the user, and its exit-2 stderr was not shown in the macOS desktop app on 2.1.233; additionalContext reaches the model on these surfaces, and plain stdout was injected for a UserPromptSubmit hook in the desktop app — from [C201], [C203], [C204], [C209], [C210], [C211], [C213], [C219]
- **C230** [inference] Three reporters on desktop and VS Code describe a model relay as their workaround: the #103739 reporter passes each user-facing line to the model with an instruction to repeat it word for word, one commenter calls asking the model to relay additionalContext the only reliable user-visible delivery, and a VS Code user has the model relay the status from additionalContext — from [C205], [C215], [C220]
- **C231** [inference] The only hook systemMessage reported visible in the desktop app is a Stop hook's, shown as a Claude Code notice (collapsed, per one report), not a SessionStart hook's — from [C202], [C204], [C214]
- **C232** [inference] The CLI also drops a SessionStart systemMessage in reported conditions (after /clear in the default renderer, intermittently at startup, at startup with an initial prompt in one of two config homes, and on resume with a repeated additionalContext), so systemMessage is not reliable in the CLI either; this conflicts with C207 — from [C207], [C221], [C224], [C227], [C228]

#### Disconfirming pass

- **C233** [quoted] In the desktop app (bundled 2.1.260, Windows), a SessionStart hook's additionalContext is dropped when the session is created by a rewind (source=fork), while on startup and compact it is injected — "SessionStart hook additionalContext silently dropped when source=fork (rewind); startup/compact inject normally" — [S12], issue title (OPEN, 2026-09-10)
- **C234** [quoted] In the desktop app a rewind is started by sending an edited earlier message, which forks a new CLI session — "In the desktop app a rewind is triggered by sending an edited earlier message" — [S12], comment by turtleziv, 2026-09-11 (https://github.com/anthropics/claude-code/issues/93458#issuecomment-5629456411)
- **C235** [quoted] CLI release 2.1.199 fixed SessionStart exit-2 stderr being hidden, so the error shows in the transcript — "Fixed `SessionStart`, `Setup`, and `SubagentStart` hooks silently hiding stderr when exiting with code 2 — the error is now shown in the transcript" — [S5], section 2.1.199
- **C236** [quoted] A desktop user reports that the only hook outputs that surface in the desktop app are the exit-2 block reason and additionalContext, the latter only through the model — "The only outputs that do surface are the exit-2 block reason (matches your report) and `hookSpecificOutput.additionalContext` (model-mediated, so not deterministic)." — [S13], comment by paul-0320, 2026-07-30 (issue is about UserPromptSubmit in Desktop) (https://github.com/anthropics/claude-code/issues/78266#issuecomment-5124901625)
- **C237** [quoted] In the VS Code extension a SessionStart hook's systemMessage is not rendered anywhere — "`systemMessage` → nothing rendered." — [S14], issue body (2026-07-11, v2.1.197), Actual behavior
- **C238** [quoted] The VS Code SessionStart rendering issue was closed by a bot for inactivity, not as fixed — "Closing for now — inactive for too long." — [S14], github-actions comment, 2026-09-05 (state CLOSED, reason NOT_PLANNED) (https://github.com/anthropics/claude-code/issues/76736#issuecomment-5555167126)
- **C239** [quoted] The issue that desktop and Remote Control sessions never render hook systemMessage was closed as a duplicate of the VS Code issue — "This issue has been automatically closed as a duplicate of #76736." — [S15], github-actions comment, 2026-07-18 (https://github.com/anthropics/claude-code/issues/77518#issuecomment-5010765456)
- **C240** [measured] The CHANGELOG up to 2.1.312 has two lines that mention systemMessage (SessionEnd support, and the field being added), and neither is about desktop or VS Code rendering — Own measurements, M6
- **C241** [measured] The weekly-read SessionStart hook is registered under the matcher startup|clear, so it does not run on resume, compact or fork — Own measurements, M5
- **C242** [inference] C203's "every event" holds for startup and compact but not for a desktop rewind (source=fork); since the weekly-read hook is not registered for fork, that drop does not touch its delivery at startup or clear — from [C203], [C233], [C234], [C241]
- **C243** [inference] The 2.1.199 fix made SessionStart exit-2 stderr visible in the terminal, but the desktop app on 2.1.233 still did not show it, so the fix did not reach the desktop renderer — from [C210], [C211], [C235]
- **C244** [inference] Two reports of hook systemMessage not rendering, the VS Code SessionStart issue and the desktop and Remote Control issue, were closed for inactivity and as a duplicate of it, not as fixed; the drop was still reported on 2.1.304; and neither CHANGELOG line that mentions systemMessage is a rendering fix; so no direct SessionStart channel to the desktop user was found in these sources — from [C201], [C236], [C238], [C239], [C240]

### Q3 — Which CLAUDE_CODE_ENTRYPOINT values are documented or observed per host, and whether an `entrypoint != cli` test can misclassify a host — answered with a gap

- **C301** [quoted] The monitoring docs list app.entrypoint values cli, sdk-cli, sdk-ts, sdk-py, claude-vscode and claude-in-slack as examples of how a session was launched — "How the session was launched, such as `cli`, `sdk-cli`, `sdk-ts`, `sdk-py`, `claude-vscode`, or `claude-in-slack` for Claude Tag sessions" — [S4], Metrics attributes table, app.entrypoint
- **C302** [quoted] The monitoring docs name claude-desktop, claude-desktop-3p and local-agent as Claude Desktop's own entrypoints — "Claude Desktop owns a session it started from one of its own entrypoints, `claude-desktop`, `claude-desktop-3p`, or `local-agent`, when that session isn't a nested child" — [S4], MCP server type values, sdk_host_builtin_mcp
- **C303** [quoted] The app.entrypoint metric attribute is off by default and enabled by OTEL_METRICS_INCLUDE_ENTRYPOINT, added in v2.1.152 — "Set to `true` to include the session entrypoint in metrics attributes (default: excluded). Added in v2.1.152." — [S3], OTEL_METRICS_INCLUDE_ENTRYPOINT
- **C304** [measured] The environment-variables, hooks, desktop and monitoring docs pages do not contain the string CLAUDE_CODE_ENTRYPOINT — Own measurements, M3
- **C305** [quoted] The #103739 reporter observed desktop sessions report claude-desktop and terminal sessions report cli — "Desktop sessions report `CLAUDE_CODE_ENTRYPOINT=claude-desktop`; terminal sessions report `cli`." — [S6], issue body, Environment (2.1.304, macOS)
- **C306** [quoted] The same reporter tells desktop from the CLI by the values claude-desktop, claude-desktop-3p and local-agent, found in the binary and called undocumented — "Today we read the `CLAUDE_CODE_ENTRYPOINT` values `claude-desktop`, `claude-desktop-3p` and `local-agent`, which we found in the binary and which are not documented." — [S6], issue body, request 4
- **C307** [quoted] The same reporter asks for a documented, supported way for a hook to tell the desktop app from the CLI — "A documented, supported way for a hook to tell the desktop app from the CLI." — [S6], issue body, request 4
- **C308** [measured] In this desktop-app (Code tab) session on Windows, a shell started by the session's Bash tool sees CLAUDE_CODE_ENTRYPOINT=claude-desktop — Own measurements, M1
- **C309** [measured] A shell in the desktop app's Terminal panel has CLAUDECODE, CLAUDE_CODE_SESSION_ID and CLAUDE_CODE_ENTRYPOINT all unset — Own measurements, M4
- **C310** [inference] The values documented or observed for non-terminal hosts (sdk-cli, sdk-ts, sdk-py, claude-vscode, claude-in-slack, claude-desktop, claude-desktop-3p, local-agent) all differ from cli, so a `!= cli` test sends each of them to the relay, and an unset or new value is also sent to the relay — from [C301], [C302], [C305], [C308]
- **C311** [inference] `!= cli` misclassifies only if the terminal CLI reports a value other than cli (it then relays as well as showing systemMessage) or a non-terminal host reports cli (it then gets no relay) — from [C301], [C302], [C305]
- **C312** [inference] A positive allowlist of desktop values, as the #103739 reporter uses, would leave the VS Code extension and SDK hosts without a relay, although the VS Code extension also drops SessionStart systemMessage — from [C301], [C306], [C219]
- **C313** [inference] On the four docs pages checked, the CLAUDE_CODE_ENTRYPOINT variable is not documented; its values appear only on the monitoring page, as examples of telemetry attribute values, and the desktop values were found by a third party in the binary — from [C301], [C302], [C304], [C306]

#### Disconfirming pass

- **C314** [quoted] Remote Control spawns a headless claude child that sets the entrypoint to sdk-cli — "which sets `CLAUDE_CODE_ENTRYPOINT=sdk-cli`, so every transcript record carries" — [S16], issue body (OPEN, 2026-09-17, 2.1.274)
- **C315** [quoted] An interactive claude started from a shell whose environment already has the entrypoint set to sdk-cli records sdk-cli too — "an interactive `claude` started from a shell that has `CLAUDE_CODE_ENTRYPOINT=sdk-cli` in its environment records `sdk-cli` too." — [S17], comment by Z3l20, 2026-09-27 (https://github.com/anthropics/claude-code/issues/97074#issuecomment-5854738845)
- **C316** [quoted] In Agent SDK 0.3.276 the process transport sets the entrypoint to sdk-ts only when it is not already set, and the VS Code extension sets claude-vscode itself — "the process transport sets `CLAUDE_CODE_ENTRYPOINT="sdk-ts"` when it isn't already set. … The difference is that it sets `CLAUDE_CODE_ENTRYPOINT="claude-vscode"` itself." — [S17], comment by kler, 2026-10-17 (https://github.com/anthropics/claude-code/issues/97074#issuecomment-6232567215)
- **C317** [quoted] Headless claude -p runs are recorded with entrypoint sdk-cli, interactive TUI runs with cli — "recorded as `entrypoint: "sdk-cli"` in the transcripts" — [S17], issue body (OPEN, 2026-09-25)
- **C318** [quoted] A commenter advises headless and Agent SDK tools to set the entrypoint variable to their own tool name, and not to cli or claude-vscode, which belong to other clients — "Don't use `cli` or `claude-vscode`, since those belong to other clients." — [S17], comment by frostfire575, 2026-10-26 (https://github.com/anthropics/claude-code/issues/97074#issuecomment-6426128541)
- **C319** [inference] The entrypoint is read from the inherited environment, so an interactive terminal CLI launched from a shell that carries a non-cli value reads as non-cli and gets the relay as well as its systemMessage (the duplicate-line cost of C206); the desktop app's Terminal panel does not carry the variable, so a CLI started there does not inherit a non-cli value — from [C121], [C206], [C309], [C315], [C316]
- **C320** [inference] Remote Control sessions report sdk-cli, so a `!= cli` test gives them the relay — from [C314]
- **C321** [inference] Hosts and tools can set the variable to values of their own choosing; a host that sets it to cli would be classified as the terminal CLI and get no relay, which is the second misclassification case of C311, advised against by one commenter — from [C311], [C316], [C318]


## Disconfirming evidence

- [C229] — query: `gh search issues --repo anthropics/claude-code "systemMessage desktop"` — no results.
- [C229] — query: `gh search issues --repo anthropics/claude-code "SessionStart hook systemMessage not shown"` — no results.
- [C229] — query: `gh search issues --repo anthropics/claude-code "SessionStart hook desktop"` — no results.
- [C229], [C231] — query: `gh search issues --repo anthropics/claude-code "systemMessage" --state open --limit 30` — the threads read from it ([S6]–[S11]) report drops; none reports the desktop app or the VS Code extension showing a SessionStart systemMessage. Counter-claims entered: C232 (the CLI drops it too in some conditions) and, through #93458 named in the #96698 body, C233 (the desktop app drops additionalContext on a rewind).
- [C244], [C231] — query: `gh search issues --repo anthropics/claude-code "systemMessage" --state closed --limit 40` — the closed threads read ([S13]–[S15]) were closed for inactivity or as duplicates [C238], [C239]. Counter-claim entered: C236 (an exit-2 block reason does surface in the desktop app, reported for UserPromptSubmit).
- [C244] — query: `grep -n -i 'systemMessage' changelog.md` (Own measurements, M6) — two lines, neither about desktop or VS Code rendering [C240]. The 2.1.199 fix for hidden SessionStart exit-2 stderr entered as counter-claim C235, narrowed by C243.
- [C120] — query: `gh search issues --repo anthropics/claude-code "terminalSequence" --limit 15` — nothing found against: none of the 15 titles reports a hook's terminalSequence reaching a desktop user (titles only; no thread opened).
- [C104], [C116], [C203], [C230] — query: `gh search issues --repo anthropics/claude-code "additionalContext ignored"` — no results.
- [C104], [C116], [C203], [C230] — query: `gh search issues --repo anthropics/claude-code "SessionStart additionalContext not"` — one feature request on conversation lifecycle hooks (#19909, title only), not about delivery. The one drop found is C233 (rewind), bounded by C241 and C242.
- [C310], [C311], [C313] — query: `gh search issues --repo anthropics/claude-code "CLAUDE_CODE_ENTRYPOINT" --limit 30` — counter-claims entered: C314 (a Remote Control child sets `sdk-cli`), C315 (an interactive claude from a shell carrying `sdk-cli` records `sdk-cli`), C316 (the Agent SDK sets `sdk-ts` only when unset; the VS Code extension sets `claude-vscode`), C317 (headless `-p` is recorded as `sdk-cli`), C318 (advice not to use `cli`). They give C319, C320 and C321.
- [C304], [C313] — query: `grep -c CLAUDE_CODE_ENTRYPOINT` over four docs pages (Own measurements, M3) — no mention on any of them; values are documented only for the `app.entrypoint` telemetry attribute [C301], [C302].

## Coverage

| Channel | Read | Gap |
|---|---|---|
| Users | [S6]–[S17] — anthropics/claude-code issue threads and their comments | Hacker News, Stack Overflow and blogs not searched: the reports on this behaviour sit in the tool's own tracker |
| Specialists | [S1]–[S5] — official docs (hooks, desktop, environment variables, monitoring) and the CHANGELOG | |
| Data | | not searched: the question is about one tool's behaviour; the reporters' own counts (C221, C224, C227) are user reports |
| Adversarial | [S12], [S14], [S15], [S16], [S17] — drop reports, closed and duplicate threads, entrypoint misreports | see Disconfirming evidence |

Tools: no web search connector and no WebSearch were used. GitHub issue search (`gh search issues`),
`gh issue view --json` for full threads and `curl -sL` of the docs' markdown pages covered the
question; quotes were copied from that text. #47828 and #52775 (Remote Control: hook systemMessage
not displayed, or rendered as a dialog; both closed as not planned) were seen as metadata only and
are not cited.

Declared overruns of the ceiling (three full reads per sub-question): Q2 read twelve sources (ten
issue threads, the desktop docs page and the CHANGELOG) and Q3 five; each thread held a distinct
host, version or entrypoint report.

## Own measurements

### M1 — the entrypoint seen by a shell that this desktop session's Bash tool starts

Command: `PYTHONIOENCODING=utf-8 python -I ../probe_env.py` (Bash tool of a Claude desktop app Code-tab session, Windows, 2026-10-28; the script prints presence only for the first two variables and the value of the third)
Output:

```
CLAUDECODE: set
CLAUDE_CODE_SESSION_ID: set
CLAUDE_CODE_ENTRYPOINT: claude-desktop
```

### M2 — whether the desktop and environment-variables docs pages mention systemMessage

Command: `grep -c systemMessage desktop.md env-vars.md` (pages fetched with `curl -sL https://code.claude.com/docs/en/<page>.md`, 2026-10-28)
Output:

```
desktop.md:0
env-vars.md:0
```

### M3 — whether four docs pages mention CLAUDE_CODE_ENTRYPOINT

Command: `grep -c CLAUDE_CODE_ENTRYPOINT env-vars.md hooks.md desktop.md monitoring-usage.md`
Output:

```
env-vars.md:0
hooks.md:0
desktop.md:0
monitoring-usage.md:0
```

### M4 — the entrypoint seen by a shell in the desktop app's Terminal panel

Command: `python '<run dir>\probe_env.py'` in a Terminal-panel tab of the desktop app (PowerShell, opened and driven by the session's run_in_terminal tool), 2026-10-28; same script as M1
Output:

```
CLAUDECODE: unset
CLAUDE_CODE_SESSION_ID: unset
CLAUDE_CODE_ENTRYPOINT: unset
```

### M5 — the matchers that register jarvis-private's hooks

Command: `grep -n -E '"matcher"|weekly-read' <jarvis-private plugin checkout>/hooks/hooks.json` (checkout at 3aadea0)
Output (trimmed: the two long command lines are cut):

```
5:        "matcher": "Bash|PowerShell",
22:        "matcher": "Bash|PowerShell|mcp__.*__merge_pull_request",
31:        "matcher": "Bash|PowerShell|Edit|Write",
40:        "matcher": "Bash|PowerShell|Edit|Write|MultiEdit|NotebookEdit|mcp__.*__run_in_terminal",
44:            "command": "input=$(cat); case \"$input\" in *weekly-read*) ;; *) exit 0 ;; esac; f=\"${CLAUDE_PLUGIN_ROOT}/hooks/weekly-read.py\"; [...] guard"
51:        "matcher": "Bash|PowerShell|Edit|Write|MultiEdit",
62:        "matcher": "startup|resume|clear",
72:        "matcher": "startup|clear",
81:            "command": "f=\"${CLAUDE_PLUGIN_ROOT}/hooks/weekly-read.py\"; [...] \"$p\" \"$f\" hook",
87:        "matcher": "compact",
96:        "matcher": "compact",
```

### M6 — the CHANGELOG lines that mention systemMessage

Command: `grep -n -i 'systemMessage' changelog.md` (raw CHANGELOG.md fetched 2026-10-28; its first release heading is `## 2.1.312`)
Output:

```
8981:- Hooks: Added systemMessage support for SessionEnd hooks
9125:- Hooks: Added systemMessage field to hook JSON output for displaying warnings and context
```

## Open questions

- Q2 — blocked: no own repro on the current build — Whether the current desktop app, and Agent SDK hosts other than Desktop and VS Code, render a SessionStart systemMessage, exit-2 stderr or sessionTitle. The desktop reports read are from 2.1.233 to 2.1.304. Settled by a live probe in the desktop app: a SessionStart hook emitting each channel, with a Stop-hook systemMessage as the positive control (the deferred follow-up).
- Q2 — no new information — Whether the CLI's own drops (C232) make systemMessage-only delivery in the CLI unreliable enough to relay there too. Settled by a decision in /grill #2172, or by counting CLI startups and clears where the line was missed.
- Q2 — not examined — Whether the desktop app, the IDE extensions and other Agent SDK hosts render a MessageDisplay hook's displayContent, which could carry the user-facing line into the first reply's display without relying on the model. Settled by adding a MessageDisplay hook to the deferred desktop probe and checking the rendered first reply.
- Q3 — not checked — Whether CLAUDE_CODE_ENTRYPOINT and its per-host values are documented anywhere beyond the four docs pages checked, and which values IDE hosts other than VS Code set. Settled by a search of the full docs text and a probe of the variable in each IDE host.
- Label verdict — open — The recommendation rests on there being no direct channel the desktop app renders; the desktop reports are from 2.1.233 to 2.1.304 and MessageDisplay displayContent was not examined. Settled by the desktop probe on the current build covering SessionStart systemMessage, exit-2 stderr, sessionTitle and a MessageDisplay hook.

## Sources

- [S1] Claude Code docs — Hooks reference — https://code.claude.com/docs/en/hooks.md — passage (full text fetched)
- [S2] Claude Code docs — Desktop — https://code.claude.com/docs/en/desktop.md — passage (full text fetched)
- [S3] Claude Code docs — Environment variables — https://code.claude.com/docs/en/env-vars.md — passage (full text fetched)
- [S4] Claude Code docs — Monitoring usage — https://code.claude.com/docs/en/monitoring-usage.md — passage (full text fetched)
- [S5] Claude Code CHANGELOG (raw, top release 2.1.312) — https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md — passage (full text fetched)
- [S6] anthropics/claude-code#103739 — Desktop app: render hook systemMessage and statusLine, start plugin monitors (parity with the CLI) — https://github.com/anthropics/claude-code/issues/103739 — read in full
- [S7] anthropics/claude-code#66555 — Claude Code in the Claude Desktop app runs UserPromptSubmit hooks and enforces blocks, but renders no user-facing hook feedback — https://github.com/anthropics/claude-code/issues/66555 — read in full
- [S8] anthropics/claude-code#80882 — SessionStart hook systemMessage not surfaced in VSCode extension side panel (works in terminal CLI) — https://github.com/anthropics/claude-code/issues/80882 — read in full
- [S9] anthropics/claude-code#96699 — SessionStart:clear systemMessage not rendered after /clear in the default TUI renderer — https://github.com/anthropics/claude-code/issues/96699 — read in full
- [S10] anthropics/claude-code#98162 — SessionStart:startup systemMessage intermittently not rendered in the interactive TUI — https://github.com/anthropics/claude-code/issues/98162 — read in full
- [S11] anthropics/claude-code#96698 — SessionStart hook systemMessage silently dropped on --continue/--resume/fork when additionalContext matches one already in the transcript — https://github.com/anthropics/claude-code/issues/96698 — read in full
- [S12] anthropics/claude-code#93458 — SessionStart hook additionalContext silently dropped when source=fork (rewind) — https://github.com/anthropics/claude-code/issues/93458 — read in full
- [S13] anthropics/claude-code#78266 — UserPromptSubmit hook systemMessage does not render in the Desktop app (or VS Code extension) — https://github.com/anthropics/claude-code/issues/78266 — read in full
- [S14] anthropics/claude-code#76736 — VS Code extension renders no SessionStart hook output — https://github.com/anthropics/claude-code/issues/76736 — read in full
- [S15] anthropics/claude-code#77518 — Desktop app and remote-control sessions never render hook systemMessage (PreToolUse/PostToolUse) — https://github.com/anthropics/claude-code/issues/77518 — read in full
- [S16] anthropics/claude-code#95231 — Remote Control sessions are hidden from the local /resume picker (filtered as entrypoint=sdk-cli) — https://github.com/anthropics/claude-code/issues/95231 — read in full
- [S17] anthropics/claude-code#97074 — Headless `claude -p` (entrypoint `sdk-cli`) uses more of the 5-hour window per token than interactive `cli` — https://github.com/anthropics/claude-code/issues/97074 — read in full

## Audit

| Claim | Verdict | Note |
|---|---|---|
| C101 | SUPPORTED | verbatim in hooks.md, Hook input and output |
| C102 | SUPPORTED | verbatim, universal fields table; the quote's cut-off link was completed with its URL so the check can match it |
| C103 | SUPPORTED | verbatim, Add context for Claude |
| C104 | SUPPORTED | verbatim, SessionStart decision control |
| C105 | SUPPORTED | verbatim, SessionStart decision control |
| C106 | SUPPORTED | verbatim table row, Exit code 2 behavior per event |
| C107 | SUPPORTED | verbatim, Exit code 2 behavior per event |
| C108 | PARTIAL | quote was cut before the elicitation exception; quote extended to the full sentence, claim names the exception, locator corrected to the JSON output note |
| C109 | SUPPORTED | verbatim, universal fields table |
| C110 | SUPPORTED | verbatim, Emit terminal notifications |
| C111 | SUPPORTED | verbatim, two passages of the MessageDisplay section joined by an ellipsis |
| C112 | PARTIAL | "after it completes" is not in the quote; claim narrowed to the quote |
| C113 | SUPPORTED | verbatim, SessionStart decision control |
| C114 | PARTIAL | "only" in -p mode goes past the quote; dropped |
| C115 | SUPPORTED | verbatim, page intro |
| C116 | PARTIAL | the quote holds only for an interactive start, a resume at launch or /clear; condition added from the same paragraph via an ellipsis |
| C117 | SUPPORTED | verbatim, JSON output |
| C118 | SUPPORTED | verbatim, Notification permission_prompt timing |
| C119 | PARTIAL | "only" for plain stdout and "MessageDisplay cannot carry SessionStart output" do not follow from its premises; removed |
| C120 | SUPPORTED | follows from C110 and C118 |
| C121 | PARTIAL | the quote omitted two documented exceptions (env scrub, HIPAA credentials); quote extended and claim names all three |
| C201 | SUPPORTED | verbatim, #103739 body |
| C202 | SUPPORTED | verbatim, #103739 body |
| C203 | SUPPORTED | verbatim, #103739 body |
| C204 | SUPPORTED | verbatim, vimox-shah-genea comment |
| C205 | SUPPORTED | verbatim, #103739 body |
| C206 | SUPPORTED | verbatim, two parts of one sentence |
| C207 | SUPPORTED | verbatim, #103739 body |
| C208 | SUPPORTED | verbatim, #66555 body; the issue is UserPromptSubmit-specific, as the claim says |
| C209 | SUPPORTED | verbatim table row, #66555 body |
| C210 | SUPPORTED | verbatim, mattlavine comment |
| C211 | SUPPORTED | verbatim table row, mattlavine comment |
| C212 | SUPPORTED | verbatim, mattlavine comment |
| C213 | SUPPORTED | verbatim, adriaan-wessels comment; 2.1.251 is in the same comment |
| C214 | SUPPORTED | verbatim, adriaan-wessels comment |
| C215 | SUPPORTED | verbatim, adriaan-wessels comment |
| C216 | SUPPORTED | verbatim, desktop.md Shared configuration |
| C217 | SUPPORTED | verbatim table row, desktop.md |
| C218 | SUPPORTED | M2 output shows 0 matches on desktop.md |
| C219 | SUPPORTED | verbatim, #80882 body |
| C220 | SUPPORTED | verbatim, guruchill comment |
| C221 | SUPPORTED | verbatim, #96699 body; quote check NOT FOUND only because the page renders the leading list marker as a list item; read by hand in the gh issue JSON text |
| C222 | SUPPORTED | verbatim, #96699 body |
| C223 | SUPPORTED | verbatim, #96699 body |
| C224 | SUPPORTED | verbatim, #98162 body |
| C225 | SUPPORTED | verbatim, #98162 body |
| C226 | SUPPORTED | verbatim, #98162 body |
| C227 | SUPPORTED | verbatim, FlorinI comment; "one config home" is in the same sentence |
| C228 | SUPPORTED | verbatim, #96698 body |
| C229 | PARTIAL | exit-2 evidence is macOS desktop 2.1.233 only, not Windows or VS Code; plain stdout evidence is a UserPromptSubmit case; versions named, both narrowed |
| C230 | PARTIAL | "independent" and "converged on the same workaround" go past the premises, and #103739 names no channel; rewritten to what each reporter says |
| C231 | PARTIAL | "at turn end" is in no premise, and "collapsed" rests on one report; rewritten |
| C232 | PARTIAL | the initial-prompt drop was in one of two config homes; condition added |
| C233 | SUPPORTED | verbatim, #93458 title; version and date from the issue body |
| C234 | SUPPORTED | verbatim, turtleziv comment |
| C235 | SUPPORTED | verbatim, CHANGELOG 2.1.199 |
| C236 | SUPPORTED | verbatim, paul-0320 comment |
| C237 | SUPPORTED | verbatim, #76736 body |
| C238 | SUPPORTED | verbatim, github-actions comment; state CLOSED, NOT_PLANNED per issue JSON |
| C239 | SUPPORTED | verbatim, github-actions comment |
| C240 | PARTIAL | M6 shows two systemMessage lines, neither about desktop or VS Code rendering; "no line about rendering of a hook message" is broader than M6's grep; narrowed |
| C241 | SUPPORTED | M5 matches the cache checkout's hooks.json; the commit hash there differs from the one the draft cites, the matcher is the same |
| C242 | PARTIAL | C233 names startup and compact, not clear; the clause on a rewound session carrying the parent's context has no premise; both removed |
| C243 | SUPPORTED | follows from C210, C211 and C235 |
| C244 | PARTIAL | the premises cover two closed reports, not all; the CHANGELOG half narrowed to the two systemMessage lines; rewritten |
| C301 | SUPPORTED | verbatim, monitoring-usage.md metrics attributes |
| C302 | SUPPORTED | verbatim, monitoring-usage.md |
| C303 | SUPPORTED | verbatim, env-vars.md |
| C304 | PARTIAL | M3 measured only the absence of the string; "the documented value list is for the telemetry attribute" was not measured; dropped |
| C305 | SUPPORTED | verbatim, #103739 body |
| C306 | SUPPORTED | verbatim, #103739 body |
| C307 | SUPPORTED | verbatim, #103739 body |
| C308 | SUPPORTED | M1 output |
| C309 | SUPPORTED | M4 output |
| C310 | SUPPORTED | follows from C301, C302, C305 and C308 |
| C311 | SUPPORTED | follows from its premises as a two-case enumeration |
| C312 | SUPPORTED | follows from C301, C306 and C219 |
| C313 | PARTIAL | "not a documented contract" generalizes from four pages; scoped to the four pages checked |
| C314 | SUPPORTED | verbatim, #95231 body |
| C315 | SUPPORTED | verbatim, Z3l20 comment |
| C316 | SUPPORTED | verbatim, kler comment, two parts joined by an ellipsis |
| C317 | SUPPORTED | verbatim, #97074 body |
| C318 | SUPPORTED | verbatim, frostfire575 comment; quote check NOT FOUND because that comment is not in the issue page's HTML (collapsed timeline); read by hand in the gh issue JSON text |
| C319 | PARTIAL | no premise says a CLI started with the variable unset reads `cli`; ending narrowed to "does not inherit a non-cli value" |
| C320 | SUPPORTED | follows from C314 |
| C321 | PARTIAL | "not prevented" has no premise and the advice is one commenter's; rewritten |

Label verdict: open — whether the desktop app renders a MessageDisplay hook's displayContent (or, on the current build, a SessionStart systemMessage) is unexamined; if it does, a deterministic direct channel exists and the relay recommendation would change for desktop.

Quote check: Quote check weekly-read-desktop-hook-output-2026-10-28.md: 64 quoted claim(s): 62 found, 2 NOT FOUND, 0 unfetchable, 0 no source

## Disposition

| Recommendation | State | Where |
|---|---|---|
| Relay the weekly-read pick through SessionStart `additionalContext` on every entrypoint other than `cli`, with the agent repeating the user-facing line verbatim | deferred | Osasuwu/jarvis#2172 |
| Defer the direct-channel desktop probe | deferred | Osasuwu/jarvis#2174 |
