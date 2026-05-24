<#
.SYNOPSIS
    Register (or re-register) a Windows Task Scheduler entry for the
    orchestrator watcher daemon. Idempotent.

.DESCRIPTION
    Registers a task that runs scripts/orchestrator/watcher.py as a continuous
    daemon (poll loop). The task starts at user logon and restarts on failure.

    Device guard: only registers on Workshop PC (config/device.json "name"
    == "VividFormsPC4Workshop") unless -Force is passed.

.PARAMETER PollInterval
    Seconds between ticks (default: 45). Passed through to --poll-interval.

.PARAMETER PythonExe
    Path to the Python interpreter. Defaults to the first `python3` on PATH.

.PARAMETER RepoRoot
    Repository root. Defaults to the repo containing this script.

.PARAMETER WhatIf
    Print the planned scheduled task XML without registering.

.PARAMETER Force
    Allow registration on non-Workshop devices (dev rehearsal).

.EXAMPLE
    .\register-watcher.ps1
    # Registers Orchestrator-Watcher to run at user logon.

.EXAMPLE
    .\register-watcher.ps1 -PollInterval 60
    # Registers with a 60-second poll interval.
#>

[CmdletBinding()]
param(
    [int]$PollInterval = 45,

    [string]$PythonExe,

    [string]$RepoRoot,

    [switch]$WhatIfOnly,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Device guard -- Workshop only per decision e6441d77.
# ---------------------------------------------------------------------------

$expectedDevice = 'VividFormsPC4Workshop'
$deviceJson     = Join-Path $PSScriptRoot '..\..\config\device.json'
$currentDevice  = $null
if (Test-Path $deviceJson) {
    try {
        $currentDevice = (Get-Content $deviceJson -Raw | ConvertFrom-Json).name
    } catch {
        Write-Warning "config/device.json present but unparsable: $($_.Exception.Message)"
    }
}

if (-not $Force -and $currentDevice -ne $expectedDevice) {
    throw "Refusing to register on '$currentDevice' -- orchestrator watcher production target is '$expectedDevice'. Pass -Force for dev rehearsal."
}

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

if (-not (Test-Path $RepoRoot)) {
    throw "RepoRoot '$RepoRoot' does not exist."
}

$watcherScript = Join-Path $RepoRoot 'scripts\orchestrator\watcher.py'
if (-not (Test-Path $watcherScript)) {
    throw "Watcher script not found at '$watcherScript'. Is the repo root correct?"
}

if (-not $PythonExe) {
    $cmd = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command python -ErrorAction Stop }
    $PythonExe = $cmd.Source
}

# ---------------------------------------------------------------------------
# Task identity
# ---------------------------------------------------------------------------

$taskName = 'Orchestrator-Watcher'

# ---------------------------------------------------------------------------
# Build the action -- continuous daemon, not one-shot.
# ---------------------------------------------------------------------------

$argParts = @(
    "`"$watcherScript`"",
    "--poll-interval", "$PollInterval"
)

$action = New-ScheduledTaskAction -Execute $PythonExe `
    -Argument ($argParts -join ' ') `
    -WorkingDirectory $RepoRoot

# ---------------------------------------------------------------------------
# Trigger -- start at user logon, keep running.
# ---------------------------------------------------------------------------

$trigger = New-ScheduledTaskTrigger -AtLogOn

# ---------------------------------------------------------------------------
# Principal + settings -- restart on crash.
# ---------------------------------------------------------------------------

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 5 `
    -RestartInterval ([timespan]::FromMinutes(1))

# ---------------------------------------------------------------------------
# Register (idempotent)
# ---------------------------------------------------------------------------

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($WhatIfOnly) {
    Write-Host "[whatif] Would register task '$taskName'"
    Write-Host "         Execute   : $PythonExe"
    Write-Host "         Arguments : $($argParts -join ' ')"
    Write-Host "         WorkingDir: $RepoRoot"
    Write-Host "         Trigger   : AtLogOn (continuous, restart on crash)"
    Write-Host "         Existing  : $(if ($existing) { 'YES (would be replaced)' } else { 'no' })"
    return
}

if ($existing) {
    Write-Host "[register] Unregistering existing '$taskName' (idempotent)"
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$description = "Orchestrator watcher daemon -- poll events, gate on quota, dispatch /rework. Poll interval: ${PollInterval}s. Decision e6441d77."

Register-ScheduledTask -TaskName $taskName `
    -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description $description | Out-Null

Write-Host "[register] '$taskName' registered (continuous daemon, poll interval ${PollInterval}s)."
Write-Host "           Script: $watcherScript"
Write-Host "           Python : $PythonExe"
Write-Host "           Inspect: Get-ScheduledTask -TaskName '$taskName'"
Write-Host "           Invoke : Start-ScheduledTask -TaskName '$taskName'"
