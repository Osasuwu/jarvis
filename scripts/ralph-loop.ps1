# Ralph-loop driver - runs a task through repeated, genuinely fresh `claude -p`
# invocations instead of one long session that thrashes on autocompaction.
#
# Pattern: Geoffrey Huntley's "Ralph Wiggum" technique (2025) - a driver loop
# feeds the same task prompt to a fresh agent invocation every iteration;
# progress persists in external state (here: jarvis working_state in Supabase
# memory, per the mcp__memory tools), never in the LLM's own context window.
# Chosen over the pre-built ralph frameworks surveyed for #1461 because every
# one of them owns its own state file/service (Linear, PRD.md,
# IMPLEMENTATION_PLAN.md) that would duplicate working_state instead of
# reusing it - see decision recorded against jarvis#1461.
#
# Each iteration is a brand-new `claude -p` process: no --continue/--resume/
# --session-id is passed, so there is nothing to compact. The iteration ends
# by writing progress back to working_state and emitting a status sentinel
# the driver can check without any MCP access of its own.
#
# The driver verifies the no-compaction claim rather than asserting it: after
# each iteration it locates that session's transcript by session_id and counts
# `"subtype":"compact_boundary"` records. A non-zero count means the iteration
# bit off more than one context - the loop is not doing its job and the task
# decomposition needs to shrink.
#
# Usage:
#   ./scripts/ralph-loop.ps1 -Task "Take jarvis issue #1455 from grill through merged PR" -MaxIterations 6
#   ./scripts/ralph-loop.ps1 -Task "..." -DryRun          # print the prompt, spawn nothing
#
# See docs/reference/ralph-loop.md for the full usage guide.

[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Task,
    [string]$WorkingStateName = 'working_state_jarvis',
    [string]$Project = 'jarvis',
    [int]$MaxIterations = 8,
    [double]$MaxBudgetUsdPerIteration = 5.0,
    [string]$Model = 'sonnet',
    # acceptEdits only auto-approves file writes; real implementation work also
    # runs git/gh/pytest, which would block on a permission prompt no human is
    # there to answer. Use bypassPermissions for genuinely unattended runs.
    [ValidateSet('acceptEdits', 'bypassPermissions', 'plan', 'default')]
    [string]$PermissionMode = 'acceptEdits',
    # Off by default, deliberately. docs/reference/mcp-slim-profile.md suggests wiring
    # config/mcp-slim.json in here, but that profile's ~90k baseline was measured
    # inside a host-managed desktop session, where claude.ai connectors (Browser,
    # visualize, ccd_*) dominate. Headless `claude -p` never loads those: measured
    # 2026-08-08 on identical no-op prompts, slim 66 815 tokens vs full 65 555 - no
    # gain, within noise. Pass a profile path to opt in anyway.
    [string]$McpConfig = '',
    [string]$Cwd = (Get-Location).Path,
    [string]$LogDir = (Join-Path (Get-Location).Path 'logs/ralph-loop'),
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Read one iteration's own session transcript for the two numbers that say whether
# the loop is working: how many times it autocompacted (must be 0), and how much of
# the context window was already spent before it did anything (the startup baseline
# that #1464's slim MCP profile exists to shrink).
#
# Transcripts live under ~/.claude/projects/<mangled-cwd>/<session-id>.jsonl; glob on
# the session id rather than reproducing the cwd-mangling scheme.
function Get-IterationTelemetry {
    param([string]$SessionId)

    if (-not $SessionId) { return $null }
    $transcript = Get-ChildItem -Path (Join-Path $env:USERPROFILE ".claude/projects/*/$SessionId.jsonl") -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $transcript) { return $null }

    $boundaries = Select-String -Path $transcript.FullName -Pattern '"subtype":"compact_boundary"' -AllMatches
    $auto = Select-String -Path $transcript.FullName -Pattern '"compactMetadata":\{"trigger":"auto"' -AllMatches

    # Effective startup context = the first assistant turn's usage, per
    # docs/reference/mcp-slim-profile.md.
    $startCtx = $null
    foreach ($line in [System.IO.File]::ReadLines($transcript.FullName)) {
        if ($line -notmatch '"type":"assistant"') { continue }
        try { $rec = $line | ConvertFrom-Json } catch { continue }
        $u = $rec.message.usage
        if (-not $u) { continue }
        $startCtx = [int]$u.input_tokens + [int]$u.cache_read_input_tokens + [int]$u.cache_creation_input_tokens
        break
    }

    [pscustomobject]@{
        Total      = @($boundaries).Count
        Auto       = @($auto).Count
        StartCtx   = $startCtx
        Transcript = $transcript.FullName
    }
}

# stderr is merged into the captured stream on purpose (hook failures and CLI
# diagnostics belong in the iteration log), so the capture is NOT valid JSON as a
# whole - a SessionEnd hook warning alone is enough to break a naive parse. Pull
# out the single JSON result object instead of parsing the mixed stream.
function Get-ResultJson {
    param([string[]]$Raw)

    $joined = ($Raw -join "`n")
    try { return $joined | ConvertFrom-Json } catch {}
    foreach ($line in ($Raw | Where-Object { $_ -match '^\s*\{.*\}\s*$' })) {
        try { return $line | ConvertFrom-Json } catch {}
    }
    return $null
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$promptFile = Join-Path $LogDir "$runId-prompt.txt"
$summaryLog = Join-Path $LogDir "$runId-summary.log"

$prompt = @"
You are ONE iteration of a ralph-loop: a driver that runs long work as a series of
fresh Claude Code sessions instead of one session that thrashes on autocompaction.
You have ZERO memory of previous iterations. Everything you need is in working_state.

TASK (the whole task, across all iterations - not just yours): $Task

## 1. Orient (do this first, before anything else)

Read working_state via mcp__memory__memory_get(name='$WorkingStateName', project='$Project').
Find the entry for THIS task. It tells you which phase is already done and what is next.
If there is no entry for this task, you are iteration 1 - start at the beginning of the chain.

## 2. Pick exactly ONE phase and do only that

The canonical jarvis chain is: /reason (optional) -> /grill -> /to-spec -> /to-tickets ->
/implement -> (review/rework) -> merge. Pick the earliest phase that is NOT yet done:

- Facts are missing / an unfamiliar library or mechanism blocks the design -> /research.
- The work has no locked acceptance criteria, or the issue carries needs-grill, or SOUL's
  grill trigger checkbox fires with no grill artifact -> /grill. (If /implement exits
  'grill_required', that IS the signal - the next phase is /grill, not a retry.)
- Acceptance criteria are locked and decision UUIDs exist -> /implement.
- A PR exists with review findings -> /rework.

Do ONE phase per iteration. Do NOT chain phases to 'save a round trip' - chaining is what
fills the context window and defeats the entire point of this loop. A short iteration that
ends cleanly beats a long one that compacts.

## 3. Protect the context window - this is the whole point

If you notice your context filling up mid-phase, STOP, checkpoint (step 4), and emit
CONTINUE. Do not push on. An iteration that autocompacts has failed even if it produced
work, because the loop exists precisely to make compaction unnecessary.

## 4. Checkpoint working_state (do NOT leave this to the final message)

Write progress to working_state as soon as any durable artifact exists (a locked AC, a
decision UUID, a branch, a commit, a PR) - not only at the end. If you stall or run out of
context, whatever you checkpointed is all the next iteration will ever know.

memory_store is a full-content upsert keyed by (project, name): read the current content
first and re-emit it with your entry updated. Do not drop other entries.

Your entry must carry, explicitly:
- which phase you just completed, and which phase is next
- artifacts: issue number, branch name, PR number, decision/episode UUIDs
- anything you learned that the next iteration would otherwise have to re-derive
- what is blocked, and on whom

## 5. End with exactly one status line, nothing after it

- Every acceptance criterion met AND verified:            RALPH_STATUS: COMPLETE
- Blocked on a HUMAN (owner answer to grill questions, design sign-off, PR review)
  and NO phase can proceed without it - name what you are
  waiting for and where it was requested, then emit:      RALPH_STATUS: BLOCKED
- Otherwise:                                              RALPH_STATUS: CONTINUE

BLOCKED matters: without it the driver would re-spawn you every round to re-discover
the same missing human input, burning a full startup cost each time for zero progress.
Emitting CONTINUE while waiting on a human is a defect, not optimism.
"@

Set-Content -Path $promptFile -Value $prompt -Encoding utf8

if ($DryRun) {
    Write-Host "=== DRY RUN - prompt written to $promptFile, no claude process spawned ===" -ForegroundColor Yellow
    Write-Host $prompt
    exit 0
}

$claudeArgs = @(
    '-p'
    '--output-format', 'json'
    '--permission-mode', $PermissionMode
    '--max-budget-usd', $MaxBudgetUsdPerIteration
    '--model', $Model
    '--add-dir', $Cwd
)
if ($McpConfig) {
    # --mcp-config alone ADDS to the registered surface; only --strict-mcp-config
    # makes it replace user scope, project .mcp.json, plugins and connectors.
    # Without the second flag the profile buys nothing.
    $claudeArgs += @('--mcp-config', $McpConfig, '--strict-mcp-config')
}

Write-Host "ralph-loop: task=`"$Task`"" -ForegroundColor Cyan
Write-Host "ralph-loop: maxIterations=$MaxIterations model=$Model permissionMode=$PermissionMode budget/iter=`$$MaxBudgetUsdPerIteration" -ForegroundColor DarkGray
Write-Host "ralph-loop: mcp=$(if ($McpConfig) { "$McpConfig (strict)" } else { 'full registered surface' })" -ForegroundColor DarkGray
Write-Host "ralph-loop: logs -> $LogDir" -ForegroundColor DarkGray

$ledger = @()

for ($i = 1; $i -le $MaxIterations; $i++) {
    Write-Host ""
    Write-Host "=== ralph-loop iteration $i/$MaxIterations ===" -ForegroundColor Cyan
    $iterRaw = Join-Path $LogDir "$runId-iter$i.json"

    # Native stderr under 2>&1 arrives as ErrorRecords, and under a host running
    # $ErrorActionPreference = 'Stop' the first hook warning on stderr terminates
    # the whole driver mid-iteration (bitten 2026-08-08: iteration 1 of the first
    # real run did 9 minutes of good work and the driver lost the result). Relax
    # the preference around the native call only, and normalize every record to a
    # plain string so the log and the JSON extraction see one uniform stream.
    $eapBefore = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $rawOutput = @(Get-Content -Path $promptFile -Raw | & claude @claudeArgs 2>&1 | ForEach-Object { "$_" })
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $eapBefore

    $rawOutput | Out-File -FilePath $iterRaw -Encoding utf8

    $resultObj = Get-ResultJson -Raw $rawOutput
    $resultText = if ($resultObj -and $resultObj.result) { $resultObj.result } else { ($rawOutput -join "`n") }

    # Per-iteration telemetry: the point of the loop is one context per iteration,
    # so measure that instead of trusting it.
    $tel = Get-IterationTelemetry -SessionId $resultObj.session_id
    $compactNote = if ($null -eq $tel) { 'transcript not found' }
                   elseif ($tel.Auto -gt 0) { "$($tel.Auto) AUTO-COMPACTION(S)" }
                   else { 'none' }
    $startNote = if ($tel -and $tel.StartCtx) { "$([math]::Round($tel.StartCtx / 1000))k" } else { 'n/a' }

    $ledger += [pscustomobject]@{
        Iter        = $i
        Session     = $resultObj.session_id
        StartCtxK   = if ($tel -and $tel.StartCtx) { [math]::Round($tel.StartCtx / 1000) } else { $null }
        CostUsd     = if ($resultObj.total_cost_usd) { [math]::Round($resultObj.total_cost_usd, 3) } else { $null }
        Turns       = $resultObj.num_turns
        Compactions = if ($tel) { $tel.Auto } else { $null }
        Status      = if ($resultText -match 'RALPH_STATUS:\s*(COMPLETE|BLOCKED|CONTINUE)') { $Matches[1] } else { 'NONE' }
    }

    $costNote = if ($resultObj.total_cost_usd) { '$' + [math]::Round($resultObj.total_cost_usd, 3) } else { 'n/a' }
    Write-Host "ralph-loop: iteration $i -> startCtx=$startNote cost=$costNote turns=$($resultObj.num_turns) compactions=$compactNote" -ForegroundColor DarkGray
    if ($tel -and $tel.Auto -gt 0) {
        Write-Host "ralph-loop: WARNING - iteration $i autocompacted. The loop is not preventing compaction; shrink the per-iteration phase." -ForegroundColor Yellow
    }

    Add-Content -Path $summaryLog -Value "--- iteration $i (session $($resultObj.session_id), startCtx $startNote, cost $costNote, compactions $compactNote) ---`n$resultText`n"

    if ($exitCode -ne 0) {
        # Distinguish 'ran out of money' from 'crashed' - both exit non-zero.
        $why = if ($resultObj.subtype) { "$($resultObj.subtype): $($resultObj.errors -join '; ')" } else { "exit $exitCode" }
        Add-Content -Path $summaryLog -Value "--- iteration ${i}: FAILED ($why) ---"
        Write-Host "ralph-loop: iteration $i FAILED ($why). Stopping - see $iterRaw" -ForegroundColor Red
        if ($resultObj.subtype -eq 'error_max_budget_usd') {
            Write-Host "ralph-loop: raise -MaxBudgetUsdPerIteration and re-run; working_state already holds this iteration's progress." -ForegroundColor Yellow
        }
        $ledger | Format-Table -AutoSize | Out-String | Write-Host
        exit 1
    }

    if ($resultText -match 'RALPH_STATUS:\s*COMPLETE') {
        Write-Host "ralph-loop: task reported COMPLETE after $i iteration(s)." -ForegroundColor Green
        $ledger | Format-Table -AutoSize | Out-String | Write-Host
        exit 0
    } elseif ($resultText -match 'RALPH_STATUS:\s*BLOCKED') {
        # A HITL phase (grill answers, design sign-off, PR review) is waiting on a
        # human. Re-spawning fresh iterations cannot unblock it - each would burn a
        # full startup cost to re-discover the same missing input. Stop cleanly;
        # re-run the same command after the human input lands.
        Write-Host "ralph-loop: iteration $i reports BLOCKED on human input. Stopping - answer what it asked for (see $summaryLog), then re-run the same command to continue." -ForegroundColor Yellow
        $ledger | Format-Table -AutoSize | Out-String | Write-Host
        exit 3
    } elseif ($resultText -notmatch 'RALPH_STATUS:\s*CONTINUE') {
        Write-Host "ralph-loop: iteration $i produced no status sentinel - treating as a stall, stopping. See $iterRaw" -ForegroundColor Red
        $ledger | Format-Table -AutoSize | Out-String | Write-Host
        exit 1
    }
}

Write-Host ""
Write-Host "ralph-loop: reached MaxIterations ($MaxIterations) without COMPLETE. Inspect $summaryLog and re-run to continue -- state already persisted in working_state." -ForegroundColor Yellow
$ledger | Format-Table -AutoSize | Out-String | Write-Host
exit 2
