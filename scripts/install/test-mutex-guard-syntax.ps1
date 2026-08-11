<#
.SYNOPSIS
    Validate mutex guard function syntax and basic operation.
#>

$ErrorActionPreference = 'Stop'

Write-Host "Loading register-wake-driver.ps1 functions..."
. (Join-Path $PSScriptRoot "register-wake-driver.ps1" -Resolve) -NoExecute

Write-Host "Testing New-SingleInstanceMutexGuard..."
$guardScript = New-SingleInstanceMutexGuard

if ([string]::IsNullOrEmpty($guardScript)) {
    throw "Guard script is empty"
}

if ($guardScript -notmatch "System.Threading.Mutex") {
    throw "Guard script does not contain mutex logic"
}

if ($guardScript -notmatch "jarvis-wake-driver-singleton") {
    throw "Guard script does not contain the expected mutex name"
}

Write-Host "Testing Format-WakeDriverActionArgs..."
$args = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-Command', '"..."'
)

# The function should return arguments as an array
$testArgs = Format-WakeDriverActionArgs -PythonExe "C:\test\python.exe" -WatchdogSeconds 300

if ($testArgs.Count -lt 5) {
    throw "Expected at least 5 arguments, got $($testArgs.Count)"
}

# The command should contain the mutex guard (it's in the last argument)
$command = $testArgs[-1]
if ($command -notmatch "jarvis-wake-driver-singleton") {
    throw "Formatted command does not include mutex guard"
}

if ($command -notmatch "agents.wake_driver") {
    throw "Formatted command does not include wake_driver invocation"
}

Write-Host ""
Write-Host "[PASS] All syntax checks passed!"
Write-Host "  - New-SingleInstanceMutexGuard returns valid script"
Write-Host "  - Format-WakeDriverActionArgs includes mutex guard"
Write-Host "  - Guard includes proper mutex name"
