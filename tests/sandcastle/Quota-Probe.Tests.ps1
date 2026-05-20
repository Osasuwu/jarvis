# Pester tests for scripts/sandcastle/Quota-Probe.ps1 (issue #635).
# Exercises the parser, cache TTL, hysteresis state machine, and broadcast logic
# with mocked external calls -- no real claude CLI, gh, or Supabase calls.
#
# Compatible with Pester 3.4 (built-in on Windows PowerShell 5.1) -- uses
# `Should Be` and `Assert-MockCalled` rather than Pester 5 dash-syntax.
#
# Run:
#   Invoke-Pester -Path tests/sandcastle/Quota-Probe.Tests.ps1

$script:ProbePath = Join-Path $PSScriptRoot '..\..\scripts\sandcastle\Quota-Probe.ps1'
. $script:ProbePath

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function New-TempDir {
    $d = Join-Path $env:TEMP "quota-probe-test-$([guid]::NewGuid())"
    New-Item -ItemType Directory -Path $d -Force | Out-Null
    return $d
}

function Remove-TempDir {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

Describe 'Get-UsagePercentFromOutput' {
    It 'extracts weekly% from live-format output' {
        $output = @"
=== Usage ===
Period       | Used     | Limit
Weekly       | 45%      | 100%
--- snip ---
"@
        $p = Get-UsagePercentFromOutput -Output $output
        $p | Should Be 45
    }

    It 'extracts weekly percentage with "weekly%:" prefix' {
        $output = 'weekly%: 72'
        $p = Get-UsagePercentFromOutput -Output $output
        $p | Should Be 72
    }

    It 'extracts at exact boundary (80)' {
        $output = 'Weekly usage: 80%'
        $p = Get-UsagePercentFromOutput -Output $output
        $p | Should Be 80
    }

    It 'extracts at release boundary (69)' {
        $output = 'weekly: 69%'
        $p = Get-UsagePercentFromOutput -Output $output
        $p | Should Be 69
    }

    It 'returns null for malformed output (no weekly line)' {
        $output = '=== Usage ===
Period | Used
Today  | 12%'
        $p = Get-UsagePercentFromOutput -Output $output
        $p | Should BeNullOrEmpty
    }

    It 'returns null for empty output' {
        Get-UsagePercentFromOutput -Output '' | Should BeNullOrEmpty
        Get-UsagePercentFromOutput -Output $null | Should BeNullOrEmpty
    }

    It 'returns null for percentage > 100' {
        # Malformed output that matches the pattern but has an implausible value
        $output = 'weekly: 150%'
        $p = Get-UsagePercentFromOutput -Output $output
        $p | Should BeNullOrEmpty
    }
}

# ---------------------------------------------------------------------------
# Cache TTL
# ---------------------------------------------------------------------------

Describe 'Test-CacheFresh' {
    It 'returns true when cache is within TTL' {
        $dir = New-TempDir
        try {
            $path = Join-Path $dir 'usage.json'
            @{ percent = 45; cached_at = (Get-Date).AddMinutes(-15).ToString('o') } | ConvertTo-Json |
                Out-File -FilePath $path -Encoding utf8
            Test-CacheFresh -Path $path -MaxAgeMinutes 30 | Should Be $true
        } finally { Remove-TempDir $dir }
    }

    It 'returns false when cache is older than TTL' {
        $dir = New-TempDir
        try {
            $path = Join-Path $dir 'usage.json'
            @{ percent = 45; cached_at = (Get-Date).AddMinutes(-40).ToString('o') } | ConvertTo-Json |
                Out-File -FilePath $path -Encoding utf8
            Test-CacheFresh -Path $path -MaxAgeMinutes 30 | Should Be $false
        } finally { Remove-TempDir $dir }
    }

    It 'returns false when cache file does not exist' {
        Test-CacheFresh -Path "Nope:\missing.json" -MaxAgeMinutes 30 | Should Be $false
    }

    It 'returns false when cache file has no cached_at' {
        $dir = New-TempDir
        try {
            $path = Join-Path $dir 'usage.json'
            @{ percent = 45 } | ConvertTo-Json | Out-File -FilePath $path -Encoding utf8
            Test-CacheFresh -Path $path -MaxAgeMinutes 30 | Should Be $false
        } finally { Remove-TempDir $dir }
    }
}

# ---------------------------------------------------------------------------
# Hysteresis state machine
# ---------------------------------------------------------------------------

Describe 'Invoke-QuotaProbe hysteresis' {
    BeforeEach {
        # Mock external calls so tests control the response.
        Mock Invoke-UsageProbe { return 'Weekly usage: 0%' }       # overridden per test
        Mock Test-CacheFresh { return $false }                     # always force probe
        Mock Read-Cache { return $null }                           # no stale fallback
        Mock Write-Cache { }                                       # no-op
        Mock Write-GhVariable { $true }
        Mock Write-EventsCanonical { 'mocked-event' }
        Mock Read-DotEnvFile { @{ SUPABASE_URL = 'https://x'; SUPABASE_KEY = 'k' } }
    }

    It 'AC: 79% -> no flip (below trip, not pressed)' {
        Mock Invoke-UsageProbe { return 'Weekly usage: 79%' }
        Mock Get-PressureState { return $false }

        $r = Invoke-QuotaProbe -CacheDir (New-TempDir) -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        $r.action | Should Be 'none'
        $r.percent | Should Be 79
    }

    It 'AC: 80% -> trip + event emit' {
        Mock Invoke-UsageProbe { return 'Weekly usage: 80%' }
        Mock Get-PressureState { return $false }

        $r = Invoke-QuotaProbe -CacheDir (New-TempDir) -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        $r.action | Should Be 'trip'
        $r.percent | Should Be 80
    }

    It 'AC: 75% after trip -> still pressed (no release, in hysteresis band)' {
        Mock Invoke-UsageProbe { return 'Weekly usage: 75%' }
        Mock Get-PressureState { return $true }  # currently pressed

        $r = Invoke-QuotaProbe -CacheDir (New-TempDir) -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        $r.action | Should Be 'none'
        $r.percent | Should Be 75
    }

    It 'AC: 69% -> release' {
        Mock Invoke-UsageProbe { return 'Weekly usage: 69%' }
        Mock Get-PressureState { return $true }  # currently pressed

        $r = Invoke-QuotaProbe -CacheDir (New-TempDir) -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        $r.action | Should Be 'release'
        $r.percent | Should Be 69
    }

    It 'AC: 71% after release -> no re-trip (below trip threshold)' {
        Mock Invoke-UsageProbe { return 'Weekly usage: 71%' }
        Mock Get-PressureState { return $false }  # already released

        $r = Invoke-QuotaProbe -CacheDir (New-TempDir) -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        $r.action | Should Be 'none'
        $r.percent | Should Be 71
    }

    It 'trip broadcasts via gh variable + events_canonical when not dry-run' {
        Mock Invoke-UsageProbe { return 'Weekly usage: 85%' }
        Mock Get-PressureState { return $false }

        $r = Invoke-QuotaProbe -CacheDir (New-TempDir) -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70

        Assert-MockCalled Write-GhVariable -Times 1 -Exactly -Scope It `
            -ParameterFilter { $VarName -eq 'CLAUDE_QUOTA_PRESSURE' -and $Value -eq $true }
        Assert-MockCalled Write-EventsCanonical -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Percent -eq 85 -and $State -eq 'tripped' }
    }

    It 'release broadcasts via gh variable + events_canonical when not dry-run' {
        Mock Invoke-UsageProbe { return 'Weekly usage: 50%' }
        Mock Get-PressureState { return $true }

        $r = Invoke-QuotaProbe -CacheDir (New-TempDir) -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70

        Assert-MockCalled Write-GhVariable -Times 1 -Exactly -Scope It `
            -ParameterFilter { $VarName -eq 'CLAUDE_QUOTA_PRESSURE' -and $Value -eq $false }
        Assert-MockCalled Write-EventsCanonical -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Percent -eq 50 -and $State -eq 'released' }
    }

    It 'no broadcast when state does not change' {
        Mock Invoke-UsageProbe { return 'Weekly usage: 75%' }
        Mock Get-PressureState { return $false }

        $r = Invoke-QuotaProbe -CacheDir (New-TempDir) -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70

        Assert-MockCalled Write-GhVariable -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-EventsCanonical -Times 0 -Exactly -Scope It
    }
}

# ---------------------------------------------------------------------------
# Parser fallback
# ---------------------------------------------------------------------------

Describe 'Invoke-QuotaProbe parser fallback' {
    BeforeEach {
        $script:tmpDir = New-TempDir
        Mock Test-CacheFresh { return $false }   # force probe (no fresh cache)
        Mock Get-PressureState { return $false }
        Mock Write-GhVariable { $true }
        Mock Write-EventsCanonical { 'mocked' }
        Mock Read-DotEnvFile { @{ SUPABASE_URL = 'https://x'; SUPABASE_KEY = 'k' } }
    }
    AfterEach {
        Remove-TempDir $script:tmpDir
    }

    It 'malformed output falls back to stale cache value, does not flip variable' {
        # Write stale cache first
        $cachePath = Join-Path $script:tmpDir 'usage.json'
        @{ percent = 30; cached_at = (Get-Date).AddHours(-2).ToString('o') } | ConvertTo-Json |
            Out-File -FilePath $cachePath -Encoding utf8

        # Probe returns malformed output
        Mock Invoke-UsageProbe { return 'ERROR: something broke' }

        $r = Invoke-QuotaProbe -CacheDir $script:tmpDir -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        # Falls back to stale cached 30%
        $r.percent | Should Be 30
        $r.action   | Should Be 'none'
    }

    It 'missing weekly% line falls back to stale cache, logs warning' {
        $cachePath = Join-Path $script:tmpDir 'usage.json'
        @{ percent = 25; cached_at = (Get-Date).AddHours(-3).ToString('o') } | ConvertTo-Json |
            Out-File -FilePath $cachePath -Encoding utf8

        # Probe output exists but has no weekly line
        Mock Invoke-UsageProbe { return '=== Usage ===
Period | Used
Today  | 12%' }

        $r = Invoke-QuotaProbe -CacheDir $script:tmpDir -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        $r.percent | Should Be 25
        $r.action   | Should Be 'none'
    }

    It 'probe failure with no cache at all returns error' {
        # No cache file exists
        Mock Invoke-UsageProbe { return $null }
        Mock Read-Cache { return $null }   # no stale fallback

        $r = Invoke-QuotaProbe -CacheDir (New-TempDir) -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        $r.action | Should Be 'error'
        $r.reason | Should Be 'no-usage-data'
    }
}

# ---------------------------------------------------------------------------
# Cache TTL integration
# ---------------------------------------------------------------------------

Describe 'Invoke-QuotaProbe cache TTL' {
    BeforeEach {
        $script:tmpDir = New-TempDir
        Mock Get-PressureState { return $false }
        Mock Write-GhVariable { $true }
        Mock Write-EventsCanonical { 'mocked' }
        Mock Read-DotEnvFile { @{ SUPABASE_URL = 'https://x'; SUPABASE_KEY = 'k' } }
    }
    AfterEach {
        Remove-TempDir $script:tmpDir
    }

    It 'reuses fresh cache (34 min old) without calling claude' {
        $cachePath = Join-Path $script:tmpDir 'usage.json'
        @{ percent = 42; cached_at = (Get-Date).AddMinutes(-34).ToString('o') } | ConvertTo-Json |
            Out-File -FilePath $cachePath -Encoding utf8

        Mock Invoke-UsageProbe { throw 'should not be called' }

        $r = Invoke-QuotaProbe -CacheDir $script:tmpDir -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        $r.percent  | Should Be 42
        $r.cacheHit | Should Be $true
        Assert-MockCalled Invoke-UsageProbe -Times 0 -Exactly -Scope It
    }

    It 'considers 36 min old cache stale and calls claude' {
        $cachePath = Join-Path $script:tmpDir 'usage.json'
        @{ percent = 42; cached_at = (Get-Date).AddMinutes(-36).ToString('o') } | ConvertTo-Json |
            Out-File -FilePath $cachePath -Encoding utf8

        Mock Invoke-UsageProbe { return 'Weekly usage: 55%' }

        $r = Invoke-QuotaProbe -CacheDir $script:tmpDir -CacheTTLMinutes 35 `
            -TripThreshold 80 -ReleaseThreshold 70 -NoBroadcast

        $r.percent  | Should Be 55
        $r.cacheHit | Should Be $false
        Assert-MockCalled Invoke-UsageProbe -Times 1 -Exactly -Scope It
    }
}

# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

Describe 'Invoke-QuotaProbe idempotency' {
    It 'running twice within TTL emits no duplicate events' {
        $dir = New-TempDir
        try {
            Mock Invoke-UsageProbe { return 'Weekly usage: 85%' }
            Mock Write-GhVariable { $true }
            Mock Write-EventsCanonical { 'mocked' }
            Mock Read-DotEnvFile { @{ SUPABASE_URL = 'https://x'; SUPABASE_KEY = 'k' } }

            # First run: no state file exists, probe + trip
            Mock Test-CacheFresh { return $false }  # no cache on first run
            Mock Get-PressureState { return $false }
            $r1 = Invoke-QuotaProbe -CacheDir $dir -CacheTTLMinutes 35 `
                -TripThreshold 80 -ReleaseThreshold 70
            $r1.action | Should Be 'trip'
            Assert-MockCalled Write-EventsCanonical -Times 1 -Exactly -Scope It

            # Second run: cache is fresh, reuses it. Same pressure state -> no broadcast.
            # Re-mock so the previous calls don't bleed into the count.
            Mock Test-CacheFresh { return $true }   # cache now fresh
            Mock Get-PressureState { return $true }  # still pressed
            # Reset call count for these mocks (Scope It = fresh per call)
            Mock Write-EventsCanonical { 'mocked' }
            Mock Write-GhVariable { $true }

            $r2 = Invoke-QuotaProbe -CacheDir $dir -CacheTTLMinutes 35 `
                -TripThreshold 80 -ReleaseThreshold 70
            $r2.action   | Should Be 'none'
            $r2.cacheHit | Should Be $true

            Assert-MockCalled Write-EventsCanonical -Times 0 -Exactly -Scope It
            Assert-MockCalled Write-GhVariable -Times 0 -Exactly -Scope It
        } finally { Remove-TempDir $dir }
    }
}
