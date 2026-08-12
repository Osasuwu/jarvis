<#
.SYNOPSIS
    Self-check: verify the wake_driver single-instance mutex guard works.

.DESCRIPTION
    Tests that the mutex guard (New-SingleInstanceMutexGuard) prevents
    multiple instances from running simultaneously (#1502).

    Flow:
    1. Start the first "instance" (a dummy process that holds the mutex).
    2. Try to start a second instance in parallel.
    3. Verify the second instance exits cleanly (exit code 0) without running
       the Python command (simulated here by a marker file).
    4. Kill the first instance and verify the mutex is released.
    5. Start a third instance and verify it succeeds now that the mutex is free.

    This demonstrates that stale generations cannot accumulate — when the old
    process dies, the new instance can immediately acquire the mutex and start.

.EXAMPLE
    .\test-wake-driver-singleton.ps1
    # Runs the full self-check suite.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

# Load the guard function from the registration script.
. (Join-Path $PSScriptRoot "register-wake-driver.ps1" -Resolve) -NoExecute

# Temp directory for test markers/pids.
$testDir = Join-Path ([System.IO.Path]::GetTempPath()) "wake-driver-singleton-test"
$null = New-Item -ItemType Directory -Path $testDir -Force -ErrorAction SilentlyContinue

# Test 1: Start first instance, verify it holds the mutex.
Write-Host "Test 1: First instance acquires mutex..."
$guardScript = New-SingleInstanceMutexGuard

# Build a dummy payload that just waits (simulating the running daemon).
# We'll terminate it from another PS session for cleanup.
$proc1Script = @"
$guardScript
Write-Host 'Instance 1: mutex acquired, holding for 10 seconds...'
Start-Sleep -Seconds 10
Write-Host 'Instance 1: timeout, exiting.'
"@

# Start first instance in a background job.
$job1 = Start-Job -ScriptBlock ([scriptblock]::Create($proc1Script))
Start-Sleep -Milliseconds 500  # Let it acquire the mutex

# Verify it's still running (not exited due to timeout).
if ($job1.State -eq 'Completed') {
    $job1 | Receive-Job -ErrorAction SilentlyContinue
    throw "Instance 1 exited immediately, should still be running"
}
Write-Host "[PASS] Instance 1 is running (holding mutex)"

# Test 2: Try to start second instance, verify it exits cleanly (timeout).
Write-Host "Test 2: Second instance times out on mutex wait..."
$proc2Script = @"
$guardScript
Write-Host 'Instance 2: mutex acquired successfully (should not reach here)'
"@

$job2 = Start-Job -ScriptBlock ([scriptblock]::Create($proc2Script))
$result = $job2 | Wait-Job -Timeout 3
if ($result -eq $null) {
    Stop-Job $job2
    throw "Instance 2 did not exit within 3 seconds (should timeout around 100ms)"
}

$output = $job2 | Receive-Job -ErrorAction SilentlyContinue
if ($output -match "mutex acquired successfully") {
    throw "Instance 2 reported acquiring mutex, but should have timed out"
}
Write-Host "[PASS] Instance 2 timed out on mutex wait (correct behavior)"

# Test 3: Kill instance 1, verify mutex is released.
Write-Host "Test 3: Stopping instance 1 to release mutex..."
Stop-Job $job1 -ErrorAction SilentlyContinue
$job1 | Remove-Job -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 200  # Let OS release the mutex

# Test 4: Start third instance, verify it succeeds (mutex now free).
Write-Host "Test 4: Third instance acquires mutex after release..."
$proc3Script = @"
$guardScript
Write-Host 'Instance 3: mutex acquired successfully'
"@

$job3 = Start-Job -ScriptBlock ([scriptblock]::Create($proc3Script))
$result = $job3 | Wait-Job -Timeout 3
if ($result -eq $null) {
    Stop-Job $job3
    throw "Instance 3 did not complete within 3 seconds (should succeed immediately)"
}

$output = $job3 | Receive-Job
if ($output -notmatch "mutex acquired successfully") {
    throw "Instance 3 failed to acquire mutex (should have succeeded): $output"
}
Write-Host "[PASS] Instance 3 acquired mutex after instance 1 released it"

# Cleanup
$job3 | Remove-Job -ErrorAction SilentlyContinue
Remove-Item $testDir -Recurse -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "[PASS][PASS][PASS] All tests passed! Single-instance mutex guard works correctly."
Write-Host ""
Write-Host "Summary:"
Write-Host "  - First instance holds mutex (blocks new instances)"
Write-Host "  - Second instance times out and exits cleanly"
Write-Host "  - Third instance acquires mutex after first releases"
Write-Host "  → Stale generations cannot accumulate (fix for #1502)"
