<#
.SYNOPSIS
    Register (or re-register) a Windows Task Scheduler entry for the sandcastle
    AFK loop. Idempotent -- running again with the same -Repo replaces the
    existing entry.

.DESCRIPTION
    Slices #545 (jarvis) and #546 (redrobot). The task fires Run-Sandcastle.ps1
    nightly inside the chosen safe-hours window:
        jarvis   : 22:00 → soft-stop at 02:00
        redrobot : 02:00 → soft-stop at 08:00
    Non-overlapping schedule prevents two Ollama jobs from contending for VRAM.

    The script must run on the Workshop PC (decision 4890aa35 -- Workshop = prod,
    Main = dev/test bench). On other devices the script refuses unless -Force.

.PARAMETER Repo
    Which sandcastle loop to wire up: jarvis or redrobot.

.PARAMETER StartTime
    Override the default start time. Default per-repo:
        jarvis   = 22:00
        redrobot = 02:00

.PARAMETER WindowEnd
    Override the soft-stop boundary passed to Run-Sandcastle.ps1. Default per-repo:
        jarvis   = 02:00
        redrobot = 08:00

.PARAMETER Model
    Tier 0 Ollama model. Defaults from #538 decision 58670ea5: qwen2.5-coder:14b.

.PARAMETER Tier1Model
    Tier 1 OOM-downgrade Ollama model. Defaults from #538: qwen2.5-coder:7b.

.PARAMETER Tier2Provider
    Empty (default) = no remote-API escalation in cron context. Set to
    deepseek or claude only when explicitly enabling Tier 2 for AFK runs.

.PARAMETER RepoRoot
    Filesystem path to the target repo. Defaults to the jarvis repo discovered
    from this script's own path (../../). For -Repo redrobot, pass the
    redrobot worktree path explicitly.

.PARAMETER WhatIf
    Print the planned scheduled task XML without registering.

.PARAMETER Force
    Allow registration on non-Workshop devices. For dev rehearsal only.

.EXAMPLE
    .\Register-SandcastleTask.ps1 -Repo jarvis
    # Registers Sandcastle-Jarvis daily at 22:00.

.EXAMPLE
    .\Register-SandcastleTask.ps1 -Repo redrobot -RepoRoot D:\Github\redrobot\redrobot
    # Registers Sandcastle-Redrobot daily at 02:00 (non-overlapping).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('jarvis', 'redrobot')]
    [string]$Repo,

    [string]$StartTime,

    [string]$WindowEnd,

    [string]$Model = 'qwen2.5-coder:14b',

    [string]$Tier1Model = 'qwen2.5-coder:7b',

    [ValidateSet('', 'deepseek', 'claude')]
    [string]$Tier2Provider = '',

    [string]$RepoRoot,

    [int]$MaxIterations = 5,

    [switch]$WhatIfOnly,

    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Device guard -- decision 4890aa35 (Workshop = production target).
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
    throw "Refusing to register on '$currentDevice' -- sandcastle production target is '$expectedDevice'. Pass -Force for dev rehearsal."
}

# ---------------------------------------------------------------------------
# Per-repo defaults
# ---------------------------------------------------------------------------

$defaults = @{
    jarvis   = @{ Start = '22:00'; End = '02:00'; TaskName = 'Sandcastle-Jarvis' }
    redrobot = @{ Start = '02:00'; End = '08:00'; TaskName = 'Sandcastle-Redrobot' }
}

if (-not $StartTime) { $StartTime = $defaults[$Repo].Start }
if (-not $WindowEnd) { $WindowEnd = $defaults[$Repo].End }
$taskName = $defaults[$Repo].TaskName

# Watchdog always lives in the jarvis repo (same dir as this script). Both
# jarvis and redrobot loops invoke the same parameterised watchdog -- it
# handles per-repo dispatch internally via Get-RepoRoot. This avoids
# duplicating the script across repos (epic #534 architectural commitment:
# "config identical between jarvis and redrobot").
$watchdog = Join-Path $PSScriptRoot 'Run-Sandcastle.ps1'
if (-not (Test-Path $watchdog)) {
    throw "Watchdog not found at '$watchdog'. Register-SandcastleTask must run from the jarvis repo's scripts/sandcastle directory."
}

# Working directory for the scheduled task -- cosmetic only (the watchdog
# does its own Push-Location to the resolved repo root). Default to the
# jarvis repo so logs / cwd-relative output land somewhere sane.
if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}

if (-not (Test-Path $RepoRoot)) {
    throw "RepoRoot '$RepoRoot' does not exist."
}

# For redrobot, the watchdog uses REDROBOT_REPO_ROOT to find the redrobot
# worktree at runtime. Surface a missing var loudly here rather than at 02:00.
if ($Repo -eq 'redrobot') {
    $machineEnv = [System.Environment]::GetEnvironmentVariable('REDROBOT_REPO_ROOT', 'Machine')
    $userEnv    = [System.Environment]::GetEnvironmentVariable('REDROBOT_REPO_ROOT', 'User')
    $envVal     = if ($machineEnv) { $machineEnv } elseif ($userEnv) { $userEnv } else { $null }
    if (-not $envVal) {
        Write-Warning "REDROBOT_REPO_ROOT machine env var not set. The scheduled task will fail at runtime. Set it once:  setx /M REDROBOT_REPO_ROOT D:\Github\redrobot"
    } elseif (-not (Test-Path $envVal)) {
        Write-Warning "REDROBOT_REPO_ROOT='$envVal' does not exist on disk. Fix before 02:00."
    } else {
        Write-Host "[register] REDROBOT_REPO_ROOT='$envVal' resolves to a real path."
    }
}

# ---------------------------------------------------------------------------
# Build the action -- pwsh preferred, fallback to powershell.exe (5.1).
# ---------------------------------------------------------------------------

$pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
$pwshExe = if ($pwshCmd) { $pwshCmd.Source } else { (Get-Command powershell -ErrorAction Stop).Source }

# Quote the watchdog path in case RepoRoot contains spaces.
$watchdogQuoted = '"' + $watchdog + '"'

$argParts = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $watchdogQuoted,
    '-Repo', $Repo,
    '-Model', $Model,
    '-MaxIterations', $MaxIterations,
    '-WindowEnd', $WindowEnd
)
if ($Tier1Model)    { $argParts += @('-Tier1Model', $Tier1Model) }
if ($Tier2Provider) { $argParts += @('-Tier2Provider', $Tier2Provider) }

$action = New-ScheduledTaskAction -Execute $pwshExe `
    -Argument ($argParts -join ' ') `
    -WorkingDirectory $RepoRoot

# ---------------------------------------------------------------------------
# Trigger -- daily including weekends, at the start of the safe-hours window.
# ---------------------------------------------------------------------------

$today = (Get-Date).Date
$startDt = [datetime]::ParseExact("$($today.ToString('yyyy-MM-dd')) $StartTime", 'yyyy-MM-dd HH:mm', $null)
# If StartTime already passed today, schedule starts firing tomorrow.
if ($startDt -lt (Get-Date)) { $startDt = $startDt.AddDays(1) }

$trigger = New-ScheduledTaskTrigger -Daily -At $startDt

# ---------------------------------------------------------------------------
# Principal + settings.
# ---------------------------------------------------------------------------

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([timespan]::FromHours(6))

# ---------------------------------------------------------------------------
# Register (idempotent).
# ---------------------------------------------------------------------------

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($WhatIfOnly) {
    Write-Host "[whatif] Would register task '$taskName'"
    Write-Host "         Execute   : $pwshExe"
    Write-Host "         Arguments : $($argParts -join ' ')"
    Write-Host "         WorkingDir: $RepoRoot"
    Write-Host "         Trigger   : Daily at $StartTime (next fire: $startDt)"
    Write-Host "         WindowEnd : $WindowEnd"
    Write-Host "         Existing  : $(if ($existing) { 'YES (would be replaced)' } else { 'no' })"
    return
}

if ($existing) {
    Write-Host "[register] Unregistering existing '$taskName' (idempotent)"
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$description = "Sandcastle AFK loop for $Repo. Slice #$(if ($Repo -eq 'jarvis') { '545' } else { '546' }). Soft-stop at $WindowEnd. Decisions 4890aa35, 0c3017c6, f8e27d53, 58670ea5."

Register-ScheduledTask -TaskName $taskName `
    -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description $description | Out-Null

Write-Host "[register] '$taskName' scheduled daily at $StartTime (window ends $WindowEnd)."
Write-Host "           Model=$Model  Tier1=$Tier1Model  Tier2=$(if ($Tier2Provider) { $Tier2Provider } else { '<disabled>' })"
Write-Host "           Inspect: Get-ScheduledTask -TaskName '$taskName'"
Write-Host "           Trigger now: Start-ScheduledTask -TaskName '$taskName'"
