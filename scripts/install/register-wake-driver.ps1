<#
.SYNOPSIS
    Register (or re-register) a Windows Task Scheduler entry for the
    reactive-core wake_driver. Idempotent.

.DESCRIPTION
    Registers a task that runs `python -m agents.wake_driver` as a
    continuous daemon (LISTEN/NOTIFY loop). The task starts at user logon
    and restarts on crash -- a thin supervised wrapper, not a resident
    poller (the earlier NSSM jarvis-scheduler service was deliberately
    retired in #743; see scripts/install/uninstall-scheduler-service.ps1).
    The polling Orchestrator-Watcher predecessor was decommissioned in #1391.

    Sets JARVIS_PRINCIPAL=autonomous on the launched process per
    docs/security/agent-boundaries.md -- any headless launcher must set
    the principal explicitly so the detection chain doesn't default to
    `live`.

    Single-instance guard (#1502): The task launcher wraps the Python
    invocation with a named system mutex (Global\jarvis-wake-driver-singleton).
    Only one instance can hold the mutex at a time. If Stop-ScheduledTask
    is called and the old process survives as an orphan, the mutex is
    automatically released by Windows when the orphan exits. On restart,
    the new instance immediately acquires the mutex, preventing stale
    generations from accumulating. If another instance is already running
    (e.g. a delayed restart), the new instance times out (100ms) and exits
    cleanly; Task Scheduler's restart loop will retry per RestartCount/
    RestartInterval.

    Device guard: only registers on Workshop PC (config/device.json
    "name" == "VividFormsPC4Workshop") unless -Force is passed --
    wake_driver's single-driver invariant (agents/pid_sidecar.py) assumes
    exactly one supervised instance, and Workshop is the production
    target for always-on agents (matching Sandcastle-Jarvis).

    No Workshop-specific paths/IPs/usernames are hardcoded here --
    RepoRoot and PythonExe are resolved from the local machine at
    registration time, same as Register-SandcastleTask.ps1.

.PARAMETER WatchdogSeconds
    Passed through to --watchdog-seconds (re-claim stale rows, wake-wait
    timeout). Default: 300, matching wake_driver.DEFAULT_STALE_AFTER_SECONDS.

.PARAMETER PythonExe
    Path to the Python interpreter. Defaults to <RepoRoot>\.venv\Scripts\python.exe
    when it exists, else the first `python3`/`python` on PATH. Whatever is
    resolved (default or explicit) is validated with `--version` before
    registration -- on stock Windows the first `python3` on PATH is the
    Microsoft Store app-execution-alias stub, which exits 9009 and leaves
    the registered task dying instantly at every start (#1495).

.PARAMETER RepoRoot
    Repository root. Defaults to the repo containing this script.

.PARAMETER WhatIfOnly
    Print the planned scheduled task without registering.

.PARAMETER Force
    Allow registration on non-Workshop devices (dev rehearsal).

.PARAMETER NoExecute
    Load function definitions only, then return -- no device guard, no
    Task Scheduler calls. For dot-sourcing from Pester tests
    (tests/install/Register-WakeDriver.Tests.ps1).

.EXAMPLE
    .\register-wake-driver.ps1
    # Registers Wake-Driver to run at user logon, watchdog=300s.

.EXAMPLE
    .\register-wake-driver.ps1 -WatchdogSeconds 120
    # Registers with a 120-second watchdog/wake-wait timeout.
#>

[CmdletBinding()]
param(
    [int]$WatchdogSeconds = 300,

    [string]$PythonExe,

    [string]$RepoRoot,

    [switch]$WhatIfOnly,

    [switch]$Force,

    [switch]$NoExecute
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Functions -- defined up front so -NoExecute can dot-source this script for
# Pester tests without triggering the device guard or a real Task Scheduler
# call (mirrors scripts/sandcastle/Register-SandcastleTask.ps1).
# ---------------------------------------------------------------------------

function Get-PowerShellExe {
    $pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwshCmd) {
        return $pwshCmd.Source
    }
    return (Get-Command powershell -ErrorAction Stop).Source
}

function New-SingleInstanceMutexGuard {
    <#
    .SYNOPSIS
        Build a PowerShell script block that ensures only one instance of
        wake_driver runs at a time via a named system mutex (#1502).

    .DESCRIPTION
        Returns a script block (as a string) that acquires a named mutex at
        startup, keeping it held for the lifetime of the process. If another
        instance tries to start before the first one exits, the mutex
        acquisition times out (wait 100ms) and the new instance exits cleanly.

        On process exit (normal or crash), Windows automatically releases the
        mutex, so stale generations do not accumulate even if the old process
        survives a Stop-ScheduledTask.

        Mutex name is deterministic (scoped to repo + wake_driver) so all
        instances target the same mutex; a global prefix avoids collisions
        with other software on the same Windows machine.
    #>

    $mutexName = "Global\jarvis-wake-driver-singleton"
    $timeoutMs = 100

    # The guard script tries to acquire a named mutex; if it succeeds,
    # the process holds it and continues. If it times out (another
    # instance has it), the process exits cleanly.
    $guardScript = @"
`$ErrorActionPreference = 'Stop'
`$mutexName = '$mutexName'
`$timeoutMs = $timeoutMs

try {
    `$mutex = [System.Threading.Mutex]::new(`$false, `$mutexName)
    if (-not `$mutex.WaitOne(`$timeoutMs)) {
        [Environment]::Exit(0)
    }
} catch [System.UnauthorizedAccessException] {
    [Environment]::Exit(0)
}
"@

    return $guardScript
}

function Format-WakeDriverActionArgs {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][int]$WatchdogSeconds
    )

    # Single-quote the inner python path and double any literal single
    # quotes so an embedded quote in $PythonExe can't break out of the
    # PowerShell string -- nesting double quotes here breaks Windows argv
    # parsing instead (the bug fixed in this PR's own history).
    $escapedPythonExe = $PythonExe -replace "'", "''"
    # REACTIVE_CONCURRENCY_CAP=2 (#1390 AC8) pins the autonomous driver's
    # sandcastle concurrency lower than the interactive-session default (5) --
    # this is an unattended box, so a smaller blast radius per tick is safer.
    $pythonCommand = "& '$escapedPythonExe' -m agents.wake_driver --watchdog-seconds $WatchdogSeconds"

    # Wrap with the single-instance mutex guard (#1502): only one instance
    # can hold the mutex at a time. If another instance tries to start, the
    # guard times out and exits cleanly, preventing stale generations.
    $guardScript = New-SingleInstanceMutexGuard
    $innerCommand = "$guardScript; `$env:JARVIS_PRINCIPAL = 'autonomous'; `$env:REACTIVE_CONCURRENCY_CAP = '2'; $pythonCommand"

    return @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command', "`"$innerCommand`""
    )
}

function Resolve-WakeDriverPython {
    param(
        [string]$PythonExe,
        [Parameter(Mandatory)][string]$RepoRoot
    )

    # Explicit -PythonExe always wins (still validated by
    # Assert-WakeDriverPython). Default prefers the repo venv: that is the
    # interpreter agents.wake_driver actually needs (repo deps), and it
    # sidesteps the Microsoft Store python3 stub that shadows PATH on
    # stock Windows (#1495).
    if ($PythonExe) {
        return $PythonExe
    }

    $venvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $cmd = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command python -ErrorAction Stop }
    return $cmd.Source
}

function Assert-WakeDriverPython {
    param(
        [Parameter(Mandatory)][string]$PythonExe
    )

    # Start-Process instead of `& $PythonExe` -- under
    # $ErrorActionPreference='Stop' in WinPS 5.1, redirected native stderr
    # is wrapped in NativeCommandError and throws even on exit 0.
    try {
        $proc = Start-Process -FilePath $PythonExe -ArgumentList '--version' `
            -PassThru -Wait -WindowStyle Hidden
    } catch {
        throw "PythonExe '$PythonExe' could not be executed: $($_.Exception.Message)"
    }

    if ($proc.ExitCode -ne 0) {
        throw ("PythonExe '$PythonExe' failed '--version' (exit $($proc.ExitCode)) -- refusing to register a task that would die at first start. " +
            "Exit 9009 means the Microsoft Store app-execution-alias stub, not a real interpreter (#1495). " +
            "Pass -PythonExe <repo>\.venv\Scripts\python.exe.")
    }
}

function Set-WakeDriverRepetition {
    param(
        [Parameter(Mandatory)]$Trigger,
        [Parameter(Mandatory)][timespan]$RepetitionInterval
    )

    # New-ScheduledTaskTrigger has no parameter set combining -AtLogOn with
    # -RepetitionInterval (verified empirically, #1479 AC2) -- build a
    # throwaway -Once trigger to get a well-formed Repetition CIM instance,
    # then graft it onto the logon trigger. Duration is intentionally left
    # unset: Task Scheduler's schema treats an omitted duration as "repeat
    # indefinitely" (minOccurs=0), while passing [timespan]::MaxValue is
    # rejected at registration (0x80041318).
    $repetitionSource = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval $RepetitionInterval
    $Trigger.Repetition = $repetitionSource.Repetition
    return $Trigger
}

if ($NoExecute) { return }

# ---------------------------------------------------------------------------
# Device guard -- Workshop only, matching Sandcastle.
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
    throw "Refusing to register on '$currentDevice' -- wake_driver production target is '$expectedDevice'. Pass -Force for dev rehearsal."
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

$driverModule = Join-Path $RepoRoot 'agents\wake_driver.py'
if (-not (Test-Path $driverModule)) {
    throw "agents/wake_driver.py not found under '$RepoRoot'. Is the repo root correct?"
}

$PythonExe = Resolve-WakeDriverPython -PythonExe $PythonExe -RepoRoot $RepoRoot
Assert-WakeDriverPython -PythonExe $PythonExe

$pwshExe = Get-PowerShellExe

# ---------------------------------------------------------------------------
# Task identity
# ---------------------------------------------------------------------------

$taskName = 'Wake-Driver'

# ---------------------------------------------------------------------------
# Build the action -- continuous daemon, JARVIS_PRINCIPAL=autonomous set on
# the launched process (agent-boundaries.md headless-launcher requirement).
# ---------------------------------------------------------------------------

$argParts = Format-WakeDriverActionArgs -PythonExe $PythonExe -WatchdogSeconds $WatchdogSeconds

$action = New-ScheduledTaskAction -Execute $pwshExe `
    -Argument ($argParts -join ' ') `
    -WorkingDirectory $RepoRoot

# ---------------------------------------------------------------------------
# Trigger -- start at user logon, keep running. A PT5M repetition is grafted
# on as a watchdog (#1479 AC2): Task Scheduler's own restart-on-failure
# (RestartCount/RestartInterval below) only fires on a *caught* failure exit;
# an uncaught crash (e.g. wait_for_wake() on a dead connection outside any
# try, per #1479's root cause) leaves the task looking "Ready" with no new
# instance and no restart attempt. -MultipleInstances IgnoreNew (below) makes
# each repetition tick a no-op while the daemon is already alive, so this is
# pure "start if not running" watchdog semantics, not a duplicate launcher.
# ---------------------------------------------------------------------------

$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger = Set-WakeDriverRepetition -Trigger $trigger -RepetitionInterval (New-TimeSpan -Minutes 5)

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
    -RestartInterval ([timespan]::FromMinutes(1)) `
    -ExecutionTimeLimit ([timespan]::Zero)

# ---------------------------------------------------------------------------
# Register (idempotent)
# ---------------------------------------------------------------------------

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($WhatIfOnly) {
    Write-Host "[whatif] Would register task '$taskName'"
    Write-Host "         Execute   : $pwshExe"
    Write-Host "         Arguments : $($argParts -join ' ')"
    Write-Host "         WorkingDir: $RepoRoot"
    Write-Host "         Trigger   : AtLogOn + PT5M repetition watchdog (continuous, restart on crash)"
    Write-Host "         Existing  : $(if ($existing) { 'YES (would be replaced)' } else { 'no' })"
    return
}

if ($existing) {
    Write-Host "[register] Unregistering existing '$taskName' (idempotent)"
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$description = "Reactive-core wake_driver -- LISTEN/NOTIFY event loop, watchdog ${WatchdogSeconds}s. Restarts on crash/reboot, PT5M repetition watchdog for uncaught-crash silent death. #1384 #1479."

Register-ScheduledTask -TaskName $taskName `
    -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description $description | Out-Null

Write-Host "[register] '$taskName' registered (continuous daemon, watchdog ${WatchdogSeconds}s)."
Write-Host "           Module : agents.wake_driver"
Write-Host "           Python : $PythonExe"
Write-Host "           Inspect: Get-ScheduledTask -TaskName '$taskName'"
Write-Host "           Invoke : Start-ScheduledTask -TaskName '$taskName'"
