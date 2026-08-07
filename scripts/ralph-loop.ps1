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
# Usage:
#   ./scripts/ralph-loop.ps1 -Task "Implement jarvis issue #1460 end to end via /implement" -MaxIterations 6
#   ./scripts/ralph-loop.ps1 -Task "..." -DryRun          # print the prompt, spawn nothing
#
# See docs/reference/ralph-loop.md for the full usage guide.

[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Task,
    [string]$WorkingStateName = 'working_state_jarvis',
    [string]$Project = 'jarvis',
    [int]$MaxIterations = 8,
    [double]$MaxBudgetUsdPerIteration = 3.0,
    [string]$Model = 'sonnet',
    [string]$Cwd = (Get-Location).Path,
    [string]$LogDir = (Join-Path (Get-Location).Path 'logs/ralph-loop'),
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$promptFile = Join-Path $LogDir "$runId-prompt.txt"
$summaryLog = Join-Path $LogDir "$runId-summary.log"

$prompt = @"
You are one iteration of a ralph-loop driver executing this task end-to-end:

TASK: $Task

Rules for this iteration:
1. Start by recalling working_state ('$WorkingStateName', project '$Project') via mcp__memory__memory_get to see what prior iterations already did. If there is no entry for this task, this is the first iteration - start fresh.
2. Do ONE coherent unit of real, verifiable progress on the task (per jarvis CLAUDE.md engineering posture: non-trivial logic leaves one runnable check). Prefer finishing one full phase cleanly over spanning many partially.
3. Before your final message, update working_state with exactly what you did and what remains, so the next iteration -- which has ZERO memory of this conversation -- can continue correctly without re-deriving context from scratch.
4. End your final message with exactly one status line, and nothing after it:
   - If the ENTIRE task is complete (every acceptance criterion met and verified) write:
     RALPH_STATUS: COMPLETE
   - Otherwise write:
     RALPH_STATUS: CONTINUE
"@

Set-Content -Path $promptFile -Value $prompt -Encoding utf8

if ($DryRun) {
    Write-Host "=== DRY RUN - prompt written to $promptFile, no claude process spawned ===" -ForegroundColor Yellow
    Write-Host $prompt
    exit 0
}

Write-Host "ralph-loop: task=`"$Task`" maxIterations=$MaxIterations model=$Model" -ForegroundColor Cyan
Write-Host "ralph-loop: logs -> $LogDir" -ForegroundColor DarkGray

for ($i = 1; $i -le $MaxIterations; $i++) {
    Write-Host ""
    Write-Host "=== ralph-loop iteration $i/$MaxIterations ===" -ForegroundColor Cyan
    $iterRaw = Join-Path $LogDir "$runId-iter$i.json"

    $rawOutput = Get-Content -Path $promptFile -Raw | & claude -p `
        --output-format json `
        --permission-mode acceptEdits `
        --max-budget-usd $MaxBudgetUsdPerIteration `
        --model $Model `
        --add-dir $Cwd `
        2>&1
    $exitCode = $LASTEXITCODE

    $rawOutput | Out-File -FilePath $iterRaw -Encoding utf8

    if ($exitCode -ne 0) {
        Add-Content -Path $summaryLog -Value "--- iteration ${i}: claude exited $exitCode, see $iterRaw ---"
        Write-Host "ralph-loop: iteration $i FAILED (exit $exitCode). Stopping - see $iterRaw" -ForegroundColor Red
        exit 1
    }

    $resultObj = $null
    try { $resultObj = ($rawOutput -join "`n") | ConvertFrom-Json } catch {}
    $resultText = if ($resultObj -and $resultObj.result) { $resultObj.result } else { ($rawOutput -join "`n") }

    Add-Content -Path $summaryLog -Value "--- iteration $i (session $($resultObj.session_id)) ---`n$resultText`n"

    if ($resultText -match 'RALPH_STATUS:\s*COMPLETE') {
        Write-Host "ralph-loop: task reported COMPLETE after $i iteration(s)." -ForegroundColor Green
        exit 0
    } elseif ($resultText -notmatch 'RALPH_STATUS:\s*CONTINUE') {
        Write-Host "ralph-loop: iteration $i produced no status sentinel - treating as a stall, stopping. See $iterRaw" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "ralph-loop: reached MaxIterations ($MaxIterations) without COMPLETE. Inspect $summaryLog and re-run to continue -- state already persisted in working_state." -ForegroundColor Yellow
exit 2
