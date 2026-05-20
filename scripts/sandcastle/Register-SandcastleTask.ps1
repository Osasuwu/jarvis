<#
.SYNOPSIS
    Register (or re-register) a Windows Task Scheduler entry for the sandcastle
    AFK loop or the quota probe. Idempotent -- running again replaces the
    existing entry.

.DESCRIPTION
    Two modes:

    **Sandcastle mode** (default, requires -Repo):
    Slices #545 (jarvis) and #546 (redrobot). The task fires Run-Sandcastle.ps1
    nightly inside the chosen safe-hours window:
        jarvis   : 18:00 → soft-stop at 01:00  (7h)
        redrobot : 01:00 → soft-stop at 08:00  (7h)
    Non-overlapping schedule covers all non-working hours (18 → 08) end-to-end.
    Earlier 22:00 / 02:00 defaults were Ollama-VRAM-contention-driven; with
    Tier 2-as-primary (#711) the local Ollama is bypassed in AFK runs, so the
    contention constraint no longer applies and the windows can grow.

    **Quota-probe mode** (-QuotaProbe):
    Registers Quota-Probe.ps1 as a recurring task every N minutes (default 30).
    Polls Claude Max weekly usage and broadcasts pressure state. See issue #635.

    The script must run on the Workshop PC (decision 4890aa35 -- Workshop = prod,
    Main = dev/test bench). On other devices the script refuses unless -Force.

.PARAMETER QuotaProbe
    Register the quota-probe recurring task instead of a sandcastle loop.
    Mutually exclusive with -Repo.

.PARAMETER QuotaProbeInterval
    Polling interval in minutes for quota-probe mode. Default 30.

.PARAMETER Repo
    Which sandcastle loop to wire up: jarvis or redrobot. Ignored in quota-probe mode.

.PARAMETER StartTime
    Override the default start time. Default per-repo:
        jarvis   = 18:00
        redrobot = 01:00

.PARAMETER WindowEnd
    Override the soft-stop boundary passed to Run-Sandcastle.ps1. Default per-repo:
        jarvis   = 01:00
        redrobot = 08:00

.PARAMETER Model
    Tier 0 Ollama model. Default flipped from qwen2.5-coder:14b → qwen3-coder:30b
    on 2026-05-14 to track the #538 benchmark winner. Both models still fail the
    real-Claude-Code tool_use fidelity probe (14b: markdown JSON fence;
    30b: Hermes-XML — see memory ollama_bench_must_measure_tool_use_fidelity),
    which is why AFK scheduled tasks use -Tier2AsPrimary to bypass the Ollama
    chain entirely; this parameter only matters for interactive smoke runs
    that opt back into the local chain.

.PARAMETER Tier1Model
    Tier 1 OOM-downgrade Ollama model. Defaults from #538: qwen2.5-coder:7b.

.PARAMETER Tier2Provider
    deepseek (default) routes AFK runs through DeepSeek's Anthropic-compatible
    endpoint as Tier 2 primary (paired with the auto-appended -Tier2AsPrimary
    on Run-Sandcastle.ps1). Pass an empty string to disable Tier 2 entirely
    (interactive Ollama-only smoke runs). Set to claude to use the Anthropic
    API key from .env instead (carries Max-subscription quota risk -- prefer
    deepseek for unattended cron).

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
    # Registers Sandcastle-Jarvis daily at 18:00, soft-stop 01:00.

.EXAMPLE
    .\Register-SandcastleTask.ps1 -Repo redrobot -RepoRoot D:\Github\redrobot\redrobot
    # Registers Sandcastle-Redrobot daily at 01:00, soft-stop 08:00 (non-overlapping).

.EXAMPLE
    .\Register-SandcastleTask.ps1 -QuotaProbe
    # Registers Quota-Probe polling every 30 minutes.

.EXAMPLE
    .\Register-SandcastleTask.ps1 -QuotaProbe -QuotaProbeInterval 15
    # Registers Quota-Probe polling every 15 minutes.
#>
[CmdletBinding(DefaultParameterSetName = 'Sandcastle')]
param(
    [Parameter(ParameterSetName = 'QuotaProbe')]
    [switch]$QuotaProbe,

    [Parameter(ParameterSetName = 'QuotaProbe')]
    [int]$QuotaProbeInterval = 30,

    [Parameter(ParameterSetName = 'Sandcastle', Mandatory)]
    [ValidateSet('jarvis', 'redrobot')]
    [string]$Repo,

    [string]$StartTime,

    [string]$WindowEnd,

    [string]$Model = 'qwen3-coder:30b',

    [string]$Tier1Model = 'qwen2.5-coder:7b',

    [ValidateSet('', 'deepseek', 'claude')]
    [string]$Tier2Provider = 'deepseek',

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
# Quota-probe mode (#635)
# ---------------------------------------------------------------------------

if ($QuotaProbe) {
    if (-not $QuotaProbeInterval -or $QuotaProbeInterval -lt 1) {
        throw "QuotaProbeInterval must be >= 1."
    }

    $taskName = 'Quota-Probe'
    $probeScript = Join-Path $PSScriptRoot 'Quota-Probe.ps1'
    if (-not (Test-Path -LiteralPath $probeScript)) {
        throw "Quota-Probe.ps1 not found at '$probeScript'."
    }

    # Working directory: the jarvis repo root (same discovery as sandcastle mode)
    if (-not $RepoRoot) {
        $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    }

    $pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
    $pwshExe = if ($pwshCmd) { $pwshCmd.Source } else { (Get-Command powershell -ErrorAction Stop).Source }

    $probeQuoted = '"' + $probeScript + '"'
    $argParts = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $probeQuoted
    )

    $action = New-ScheduledTaskAction -Execute $pwshExe `
        -Argument ($argParts -join ' ') `
        -WorkingDirectory $RepoRoot

    # Daily trigger with repetition interval (runs every N minutes all day)
    $startDt = (Get-Date).Date.AddMinutes(5)  # start 5 min past midnight
    if ($startDt -lt (Get-Date)) { $startDt = $startDt.AddDays(1) }

    $trigger = New-ScheduledTaskTrigger -Daily -At $startDt
    $trigger.Repetition = New-ScheduledTaskTriggerRepetition `
        -Interval ([timespan]::FromMinutes($QuotaProbeInterval)) `
        -Duration ([timespan]::MaxValue)  # indefinite

    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit ([timespan]::FromMinutes(15))

    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

    if ($WhatIfOnly) {
        Write-Host "[whatif] Would register task '$taskName'"
        Write-Host "         Execute   : $pwshExe"
        Write-Host "         Arguments : $($argParts -join ' ')"
        Write-Host "         WorkingDir: $RepoRoot"
        Write-Host "         Interval  : Every ${QuotaProbeInterval}min"
        Write-Host "         Existing  : $(if ($existing) { 'YES (would be replaced)' } else { 'no' })"
        return
    }

    if ($existing) {
        Write-Host "[register] Unregistering existing '$taskName' (idempotent)"
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }

    Register-ScheduledTask -TaskName $taskName `
        -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings `
        -Description "Quota pressure probe every ${QuotaProbeInterval}min. Issue #635." | Out-Null

    Write-Host "[register] '$taskName' scheduled every ${QuotaProbeInterval}min."
    Write-Host "           Inspect: Get-ScheduledTask -TaskName '$taskName'"
    Write-Host "           Trigger now: Start-ScheduledTask -TaskName '$taskName'"
    return
}

# ---------------------------------------------------------------------------
# Per-repo defaults
# ---------------------------------------------------------------------------

$defaults = @{
    jarvis   = @{ Start = '18:00'; End = '01:00'; TaskName = 'Sandcastle-Jarvis' }
    redrobot = @{ Start = '01:00'; End = '08:00'; TaskName = 'Sandcastle-Redrobot' }
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
if ($Tier2Provider) {
    $argParts += @('-Tier2Provider', $Tier2Provider)
    # 2026-05-14: Tier 2 runs as primary for AFK scheduled tasks. Local Ollama
    # tiers fail the real-Claude-Code tool_use fidelity check on qwen2.5-coder:14b
    # and qwen3-coder:30b — see memory ollama_bench_must_measure_tool_use_fidelity.
    $argParts += '-Tier2AsPrimary'
}

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
    -ExecutionTimeLimit ([timespan]::FromHours(8))

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
