<#
.SYNOPSIS
    Poll Claude Max weekly usage and broadcast pressure state via hysteresis.

.DESCRIPTION
    Standalone scheduled job for the Workshop PC. Runs `claude -p "/usage"`,
    parses the weekly% consumption, caches the result, and applies hysteresis
    to broadcast pressure state via `gh variable set CLAUDE_QUOTA_PRESSURE`
    and a `quota_pressure` row in `events_canonical`.

    Hysteresis:
        weekly% >= 80  → trip  (CLAUDE_QUOTA_PRESSURE=true)
        weekly% <  70  → release (CLAUDE_QUOTA_PRESSURE=false)
        70 <= weekly% < 80 → no state change (anti-flap)

    Cache: result cached as `~/.jarvis/orchestrator/usage.json` (default TTL 35 min).
    Reuses cached value on parse failure so transient Claude-CLI glitches don't
    flip the pressure variable.

    Realizes decisions d5b3fdd3 (initial 90% gate) and 46830b4e (80%/70% hysteresis).

.PARAMETER CacheDir
    Directory for the usage cache file. Default: ~/.jarvis/orchestrator.

.PARAMETER CacheTTLMinutes
    How long a cached result is considered fresh. Default 35 min (for a 30-min
    probe cadence, gives ~5 min overlap so transient probe failures use cache).

.PARAMETER TripThreshold
    weekly% threshold to set pressure=true. Default 80.

.PARAMETER ReleaseThreshold
    weekly% below which pressure is released. Default 70.

.PARAMETER NoBroadcast
    Dry-run switch: log what would happen but don't call gh or events_canonical.

.PARAMETER DotEnvPath
    Path to a .env file with SUPABASE_URL and SUPABASE_KEY for writing
    events_canonical rows. Default: $PSScriptRoot\..\..\.sandcastle\.env
    (the sandcastle env, which also carries these creds).

.PARAMETER ClaudeCli
    Path to the claude CLI executable. Default: auto-discover via Get-Command.

.EXAMPLE
    .\Quota-Probe.ps1
    # Normal probe: check usage, apply hysteresis, broadcast if state changed.

.EXAMPLE
    .\Quota-Probe.ps1 -NoBroadcast
    # Check-only: parse usage, log state, but do not write gh var or events.
#>

[CmdletBinding()]
param(
    [string]$CacheDir,

    [int]$CacheTTLMinutes = 35,

    [int]$TripThreshold = 80,

    [int]$ReleaseThreshold = 70,

    [switch]$NoBroadcast,

    [string]$DotEnvPath,

    [string]$ClaudeCli
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

if (-not $CacheDir) {
    $CacheDir = Join-Path $env:USERPROFILE '.jarvis\orchestrator'
}
$stateFile = Join-Path $CacheDir 'usage.json'
$pressureVar = 'CLAUDE_QUOTA_PRESSURE'

if (-not $DotEnvPath) {
    $DotEnvPath = Join-Path $PSScriptRoot '..\..\.sandcastle\.env'
}

if (-not $ClaudeCli) {
    $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
    if (-not $claudeCmd) {
        Write-Error "claude CLI not found on PATH."
        exit 2
    }
    $ClaudeCli = $claudeCmd.Source
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Read-DotEnvFile {
    [CmdletBinding()]
    param([string]$Path)
    $vars = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $vars }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $eq = $trimmed.IndexOf('=')
        if ($eq -lt 1) { continue }
        $key = $trimmed.Substring(0, $eq).Trim()
        $val = $trimmed.Substring($eq + 1).Trim()
        if ($val.Length -ge 2) {
            $first = $val[0]; $last = $val[$val.Length - 1]
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $val = $val.Substring(1, $val.Length - 2)
            }
        }
        $vars[$key] = $val
    }
    return $vars
}

function Test-CacheFresh {
    [CmdletBinding()]
    param(
        [string]$Path,
        [int]$MaxAgeMinutes
    )
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $data = Get-Content -LiteralPath $Path -Raw -Encoding utf8 -ErrorAction Stop | ConvertFrom-Json
        if (-not $data.cached_at) { return $false }
        $age = (Get-Date) - [datetime]::Parse($data.cached_at)
        return ($age.TotalMinutes -lt $MaxAgeMinutes)
    } catch {
        return $false
    }
}

function Read-Cache {
    [CmdletBinding()]
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $data = Get-Content -LiteralPath $Path -Raw -Encoding utf8 -ErrorAction Stop | ConvertFrom-Json
        return [pscustomobject]@{
            percent   = [int]$data.percent
            cached_at = $data.cached_at
        }
    } catch {
        return $null
    }
}

function Write-Cache {
    [CmdletBinding()]
    param(
        [string]$Path,
        [int]$Percent
    )
    $dir = Split-Path $Path -Parent
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force -ErrorAction Stop | Out-Null
    }
    $content = @{
        percent   = $Percent
        cached_at = (Get-Date).ToString('o')
    } | ConvertTo-Json
    $content | Out-File -FilePath $Path -Encoding utf8 -Force
}

function Invoke-UsageProbe {
    [CmdletBinding()]
    param([string]$CliPath)
    try {
        $output = & $CliPath -p '/usage' 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "claude -p '/usage' exited with code $LASTEXITCODE"
            return $null
        }
        return ($output | Out-String)
    } catch {
        Write-Warning "claude -p '/usage' call failed: $_"
        return $null
    }
}

function Get-UsagePercentFromOutput {
    [CmdletBinding()]
    param([string]$Output)
    if ([string]::IsNullOrWhiteSpace($Output)) { return $null }

    # Match patterns like:
    #   "Weekly usage: 45%"   "weekly%: 45"   "Weekly: 72%"   "weekly = 80"
    # Capture group 1 = the percentage number.
    if ($Output -match 'weekly[:\s]*%?[:\s]*(\d+)\s*%?') {
        $val = [int]$Matches[1]
        if ($val -ge 0 -and $val -le 100) {
            return $val
        }
    }
    return $null
}

function Get-PressureState {
    [CmdletBinding()]
    param([string]$VarName)
    try {
        $list = & gh variable list --json name,value 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($list)) { return $false }
        $entry = $list | ConvertFrom-Json | Where-Object { $_.name -eq $VarName }
        if (-not $entry) { return $false }
        return ($entry[0].value -eq 'true')
    } catch {
        Write-Warning "Failed to read gh variable $VarName`: $_"
        return $false
    }
}

function Write-GhVariable {
    [CmdletBinding()]
    param(
        [string]$VarName,
        [bool]$Value
    )
    $strVal = if ($Value) { 'true' } else { 'false' }
    try {
        & gh variable set $VarName --body $strVal 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "gh variable set $VarName=$strVal exited with code $LASTEXITCODE"
            return $false
        }
        Write-Host "[quota] gh variable $VarName = $strVal"
        return $true
    } catch {
        Write-Warning "Failed to set gh variable $VarName`: $_"
        return $false
    }
}

function Write-EventsCanonical {
    [CmdletBinding()]
    param(
        [string]$SupabaseUrl,
        [string]$SupabaseKey,
        [int]$Percent,
        [ValidateSet('tripped', 'released')]
        [string]$State
    )
    if (-not $SupabaseUrl -or -not $SupabaseKey) {
        Write-Warning "Supabase credentials missing — skipping events_canonical write."
        return $null
    }

    $title = if ($State -eq 'tripped') {
        "Claude Max weekly at ${Percent}% — pressure tripped"
    } else {
        "Claude Max weekly at ${Percent}% — pressure released"
    }

    $body = @{
        event_type = 'quota_pressure'
        severity    = 'high'
        repo        = 'Osasuwu/jarvis'
        source      = 'quota_probe'
        title       = $title
        payload     = @{
            weekly_percent = $Percent
            state          = $State
        }
    } | ConvertTo-Json -Depth 4

    $headers = @{
        apikey          = $SupabaseKey
        Authorization   = "Bearer $SupabaseKey"
        'Content-Type'  = 'application/json'
    }

    $url = "$($SupabaseUrl.TrimEnd('/'))/rest/v1/events_canonical"
    try {
        $resp = Invoke-RestMethod -Uri $url -Method Post -Headers $headers -Body $body -ErrorAction Stop
        Write-Host "[quota] events_canonical row written (state=$State, percent=$Percent)"
        return $resp
    } catch {
        Write-Warning "events_canonical write failed: $_"
        return $null
    }
}

# ---------------------------------------------------------------------------
# Main probe logic
# ---------------------------------------------------------------------------

function Invoke-QuotaProbe {
    [CmdletBinding()]
    param(
        [string]$CacheDir,
        [int]$CacheTTLMinutes,
        [int]$TripThreshold,
        [int]$ReleaseThreshold,
        [switch]$NoBroadcast,
        [string]$DotEnvPath,
        [string]$ClaudeCli
    )

    $stateFile = Join-Path $CacheDir 'usage.json'
    [int?]$percent = $null
    $cacheHit = $false

    # ---- Phase 1: Probe ----
    if (Test-CacheFresh -Path $stateFile -MaxAgeMinutes $CacheTTLMinutes) {
        $cached = Read-Cache -Path $stateFile
        if ($cached -and $cached.percent -ge 0) {
            $percent = $cached.percent
            $cacheHit = $true
            Write-Host "[quota] cache hit: ${percent}% (age < ${CacheTTLMinutes}m)"
        }
    }

    if (-not $percent.HasValue) {
        $raw = Invoke-UsageProbe -CliPath $ClaudeCli
        if ($raw) {
            $parsed = Get-UsagePercentFromOutput -Output $raw
            if ($parsed.HasValue) {
                $percent = $parsed.Value
                Write-Cache -Path $stateFile -Percent $percent.Value
                Write-Host "[quota] probe: ${percent}% (cached)"
            }
        }

        # Fallback: if probe failed and we have stale cached data, use it
        if (-not $percent.HasValue) {
            $cached = Read-Cache -Path $stateFile
            if ($cached -and $cached.percent -ge 0) {
                $percent = $cached.percent
                Write-Warning "[quota] probe failed — using stale cached value ${percent}%"
            }
        }
    }

    if (-not $percent.HasValue) {
        Write-Error "[quota] no usage data available — skipping hysteresis check."
        return [pscustomobject]@{
            action     = 'error'
            reason     = 'no-usage-data'
            percent    = $null
        }
    }

    # ---- Phase 2: Hysteresis ----
    $currentlyPressed = Get-PressureState -VarName $pressureVar
    Write-Host "[quota] percent=${percent}% pressed=$currentlyPressed trip=$TripThreshold release=$ReleaseThreshold"

    $action = 'none'
    $reason = ''
    $newState = $null

    if ($percent.Value -ge $TripThreshold) {
        if (-not $currentlyPressed) {
            $action = 'trip'
            $newState = $true
            $reason = "weekly ${percent}% >= ${TripThreshold}% — tripping pressure"
        } else {
            $reason = "weekly ${percent}% >= ${TripThreshold}% but already pressed (no change)"
        }
    } elseif ($percent.Value -lt $ReleaseThreshold) {
        if ($currentlyPressed) {
            $action = 'release'
            $newState = $false
            $reason = "weekly ${percent}% < ${ReleaseThreshold}% — releasing pressure"
        } else {
            $reason = "weekly ${percent}% < ${ReleaseThreshold}% but already released (no change)"
        }
    } else {
        $reason = "weekly ${percent}% in hysteresis band (${ReleaseThreshold}-$($TripThreshold - 1)%) — no change"
    }

    # ---- Phase 3: Broadcast ----
    $ghOk = $null
    $eventOk = $null

    if ($action -eq 'none') {
        Write-Host "[quota] $reason"
    } elseif ($NoBroadcast) {
        Write-Host "[quota] dry-run: would $action ($reason)"
    } else {
        Write-Host "[quota] $action: $reason"

        # 1. gh variable
        $ghOk = Write-GhVariable -VarName $pressureVar -Value $newState.Value

        # 2. events_canonical
        $envVars = Read-DotEnvFile -Path $DotEnvPath
        $sbUrl = $envVars['SUPABASE_URL']
        $sbKey = $envVars['SUPABASE_KEY']
        if ($env:SUPABASE_URL) { $sbUrl = $env:SUPABASE_URL }
        if ($env:SUPABASE_KEY) { $sbKey = $env:SUPABASE_KEY }
        $eventOk = Write-EventsCanonical -SupabaseUrl $sbUrl -SupabaseKey $sbKey `
            -Percent $percent.Value -State $action
    }

    return [pscustomobject]@{
        action           = $action
        reason           = $reason
        percent          = $percent.Value
        cacheHit         = $cacheHit
        currentlyPressed = $currentlyPressed
        ghVariableSet    = $ghOk
        eventWritten     = ($eventOk -ne $null)
    }
}

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

$result = Invoke-QuotaProbe -CacheDir $CacheDir -CacheTTLMinutes $CacheTTLMinutes `
    -TripThreshold $TripThreshold -ReleaseThreshold $ReleaseThreshold `
    -NoBroadcast:$NoBroadcast -DotEnvPath $DotEnvPath -ClaudeCli $ClaudeCli

$result | ConvertTo-Json -Depth 4 | Out-Host

if ($result.action -eq 'error') { exit 2 }
exit 0
