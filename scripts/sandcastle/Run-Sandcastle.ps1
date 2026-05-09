# Run-Sandcastle.ps1 -- slice 4 watchdog wrapper for the AFK sandcastle loop.
# Single entry point production code paths use instead of `tsx main.mts`.
# Decision: 0c3017c6 (fail-fast + autostart + soft-stop window).
#
# Responsibilities:
#  1. Ensure Docker daemon is up (autostart + poll, fail fast on timeout).
#  2. Ensure Ollama is up (autostart + poll, fail fast on timeout).
#  3. Run sandcastle one or more iterations via tsx/npm.
#  4. Parse the result JSON dumped by main.mts.
#  5. Write outcome_record to Supabase via PostgREST anon insert.
#  6. Honor a safe-hours window -- soft-stop between iterations only.
#
# Telegram (slice 6) and multi-tier escalation (slice 5) are layered later.

[CmdletBinding()]
param(
    [ValidateSet('jarvis', 'redrobot')]
    [string]$Repo,

    [int]$MaxIterations = 1,

    [string]$Model,

    # Either ISO-8601 datetime ("2026-05-09T03:00:00") or "HH:mm" interpreted
    # as the next occurrence today. Empty string disables the window.
    [string]$WindowEnd,

    [int]$DockerTimeoutSec = 120,

    [int]$OllamaTimeoutSec = 30,

    # Skip the actual sandcastle invocation -- for dry runs and Pester.
    [switch]$NoExecute
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Daemon health probes
# ---------------------------------------------------------------------------

function Test-DockerRunning {
    [CmdletBinding()]
    param()
    try {
        & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Start-DockerDesktop {
    [CmdletBinding()]
    param()
    $exe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "Docker Desktop not installed at expected path: $exe"
    }
    Start-Process -FilePath $exe -WindowStyle Hidden | Out-Null
}

function Wait-DockerReady {
    [CmdletBinding()]
    param([int]$TimeoutSec)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerRunning) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Test-OllamaRunning {
    [CmdletBinding()]
    param([string]$BaseUrl = 'http://localhost:11434')
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl/api/tags" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Start-OllamaServer {
    [CmdletBinding()]
    param()
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "ollama executable not on PATH; cannot autostart."
    }
    Start-Process -FilePath $cmd.Source -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
}

function Wait-OllamaReady {
    [CmdletBinding()]
    param([int]$TimeoutSec, [string]$BaseUrl = 'http://localhost:11434')
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-OllamaRunning -BaseUrl $BaseUrl) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

# ---------------------------------------------------------------------------
# Safe-hours window
# ---------------------------------------------------------------------------

function Resolve-WindowEnd {
    [CmdletBinding()]
    param([string]$WindowEnd)
    if ([string]::IsNullOrWhiteSpace($WindowEnd)) { return $null }
    if ($WindowEnd -match '^\d{2}:\d{2}$') {
        $today = (Get-Date).Date
        $end = $today.Add([TimeSpan]::Parse($WindowEnd + ':00'))
        # If the wall clock has already passed HH:mm today, the window is
        # already closed -- we treat it as "now" so the watchdog records
        # window-expired before doing any work.
        return $end
    }
    return [datetime]::Parse($WindowEnd)
}

function Test-WindowExpired {
    [CmdletBinding()]
    param([Nullable[datetime]]$WindowEnd)
    if (-not $WindowEnd) { return $false }
    return ((Get-Date) -ge $WindowEnd)
}

# ---------------------------------------------------------------------------
# Sandcastle invocation
# ---------------------------------------------------------------------------

function Get-RepoRoot {
    [CmdletBinding()]
    param([string]$Repo)
    switch ($Repo) {
        'jarvis' {
            # scripts/sandcastle/Run-Sandcastle.ps1 → repo root is two levels up.
            return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
        }
        'redrobot' {
            $root = $env:REDROBOT_REPO_ROOT
            if ([string]::IsNullOrWhiteSpace($root)) {
                throw "Set REDROBOT_REPO_ROOT to the redrobot checkout (slice 9 will deploy this on Workshop)."
            }
            if (-not (Test-Path -LiteralPath $root)) {
                throw "REDROBOT_REPO_ROOT does not exist: $root"
            }
            return (Resolve-Path -LiteralPath $root).Path
        }
        default { throw "Unknown repo: $Repo" }
    }
}

function New-RuntimeDir {
    [CmdletBinding()]
    param([string]$RepoRoot, [string]$Stamp)
    $dir = Join-Path $RepoRoot ".sandcastle/runtime/$Stamp"
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    return $dir
}

function Invoke-Sandcastle {
    [CmdletBinding()]
    param(
        [string]$RepoRoot,
        [string]$Model,
        [int]$MaxIterations,
        [string]$ResultFile,
        [string]$LogFile,
        [string]$RunId
    )

    # Stale result.json from a prior iteration would otherwise be silently
    # re-read on a partial-write crash. Always start clean.
    Remove-Item -LiteralPath $ResultFile -ErrorAction SilentlyContinue

    # Save-and-restore so dot-sourced Pester runs don't bleed values across calls.
    $prev = @{
        SANDCASTLE_RESULT_FILE    = $env:SANDCASTLE_RESULT_FILE
        SANDCASTLE_MAX_ITERATIONS = $env:SANDCASTLE_MAX_ITERATIONS
        SANDCASTLE_RUN_ID         = $env:SANDCASTLE_RUN_ID
        OLLAMA_MODEL              = $env:OLLAMA_MODEL
    }
    $env:SANDCASTLE_RESULT_FILE    = $ResultFile
    $env:SANDCASTLE_MAX_ITERATIONS = "$MaxIterations"
    if ($RunId) { $env:SANDCASTLE_RUN_ID = $RunId }
    if ($Model) { $env:OLLAMA_MODEL      = $Model }

    Push-Location -LiteralPath $RepoRoot
    $cmdNotFound = $false
    try {
        try {
            $combined = & npm run --silent sandcastle 2>&1
            $exitCode = $LASTEXITCODE
            $combined | Out-File -FilePath $LogFile -Encoding utf8 -Append
        } catch [System.Management.Automation.CommandNotFoundException] {
            $cmdNotFound = $true
        }
    } finally {
        Pop-Location
        $env:SANDCASTLE_RESULT_FILE    = $prev.SANDCASTLE_RESULT_FILE
        $env:SANDCASTLE_MAX_ITERATIONS = $prev.SANDCASTLE_MAX_ITERATIONS
        $env:SANDCASTLE_RUN_ID         = $prev.SANDCASTLE_RUN_ID
        $env:OLLAMA_MODEL              = $prev.OLLAMA_MODEL
    }

    if ($cmdNotFound) {
        return [pscustomobject]@{ ok = $false; exitCode = -1; result = $null; reason = 'npm-not-found' }
    }
    if ($exitCode -ne 0) {
        return [pscustomobject]@{ ok = $false; exitCode = $exitCode; result = $null; reason = "exit=$exitCode" }
    }
    if (-not (Test-Path -LiteralPath $ResultFile)) {
        return [pscustomobject]@{ ok = $false; exitCode = $exitCode; result = $null; reason = 'no-result-file' }
    }
    try {
        $json = Get-Content -LiteralPath $ResultFile -Raw -Encoding utf8 | ConvertFrom-Json
    } catch {
        return [pscustomobject]@{ ok = $false; exitCode = $exitCode; result = $null; reason = "json-parse-error: $_" }
    }
    return [pscustomobject]@{ ok = $true; exitCode = 0; result = $json; reason = $null }
}

# ---------------------------------------------------------------------------
# Telegram alerting -- infra-down only (slice 6, #544, decision 0c3017c6).
# Routine partial / agent-side failure / OOM-escalated outcomes stay silent.
# ---------------------------------------------------------------------------

# Reasons that warrant waking up the principal in chat. Anything else
# (agent-side exit codes, partial:window-expired, success) stays silent
# so morning chat carries signal not noise.
$script:TelegramInfraReasons = @(
    'docker-down',
    'ollama-down',
    'npm-not-found',
    'no-result-file',
    'container-launch-fail'
)

function Test-IsInfraDown {
    [CmdletBinding()]
    param([string]$Reason)
    if (-not $Reason) { return $false }
    foreach ($r in $script:TelegramInfraReasons) {
        if ($Reason.StartsWith($r)) { return $true }
    }
    return $false
}

function Send-TelegramAlert {
    [CmdletBinding()]
    param(
        [string]$BotToken,
        [string]$ChatId,
        [string]$Message
    )
    if (-not $BotToken -or -not $ChatId) {
        Write-Warning "Telegram token/chat-id missing -- skipping alert."
        return $null
    }
    # 200-char cap is an AC. Truncate defensively; real callers stay well under.
    if ($Message.Length -gt 200) { $Message = $Message.Substring(0, 197) + '...' }
    $url = "https://api.telegram.org/bot$BotToken/sendMessage"
    $body = @{ chat_id = $ChatId; text = $Message }
    return Invoke-RestMethod -Uri $url -Method Post -Body $body -ErrorAction Stop
}

# ---------------------------------------------------------------------------
# Outcome recording -- direct PostgREST insert (anon, RLS-gated by source_provenance)
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
        # Strip only matched outer quote pairs so values like "it's" or
        # base64 padding ending in '=' survive verbatim.
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

function Write-OutcomeRecord {
    [CmdletBinding()]
    param(
        [string]$SupabaseUrl,
        [string]$SupabaseKey,
        [string]$Repo,
        [string]$Status,        # success | partial | failure
        [string]$Summary,
        [hashtable]$LlmMetrics, # @{ input_tokens; output_tokens; cache_read; cache_creation; model }
        [string[]]$ExtraTags = @(),
        [string]$RunId
    )

    if (-not $SupabaseUrl -or -not $SupabaseKey) {
        Write-Warning "SUPABASE_URL/SUPABASE_KEY missing -- skipping outcome_record write."
        return $null
    }

    $tags = @('sandcastle', 'afk') + $ExtraTags

    $body = @{
        task_type         = 'autonomous'
        task_description  = "sandcastle:$Repo watchdog run $RunId"
        outcome_status    = $Status
        outcome_summary   = $Summary
        project           = $Repo
        pattern_tags      = $tags
        # Token metrics ride in lessons until task_outcomes gains a dedicated
        # llm jsonb column -- slice 4 keeps the schema untouched on purpose.
        # `lessons` carries token metrics as JSON until task_outcomes gains a
        # dedicated llm jsonb column. Stable shape consumers can rely on:
        #   { input_tokens, output_tokens, cache_read_input_tokens,
        #     cache_creation_input_tokens, model }
        lessons           = ($LlmMetrics | ConvertTo-Json -Compress)
        source_provenance = "sandcastle:watchdog:$RunId"
    }
    $headers = @{
        apikey          = $SupabaseKey
        Authorization   = "Bearer $SupabaseKey"
        'Content-Type'  = 'application/json'
        Prefer          = 'return=representation'
    }

    $url = "$($SupabaseUrl.TrimEnd('/'))/rest/v1/task_outcomes"
    $resp = Invoke-RestMethod -Uri $url -Method Post -Headers $headers -Body ($body | ConvertTo-Json -Depth 6) -ErrorAction Stop
    return $resp
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

function Invoke-Watchdog {
    [CmdletBinding()]
    param(
        [string]$Repo,
        [int]$MaxIterations,
        [string]$Model,
        [string]$WindowEnd,
        [int]$DockerTimeoutSec,
        [int]$OllamaTimeoutSec
    )

    $repoRoot = Get-RepoRoot -Repo $Repo
    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
    $runtimeDir = New-RuntimeDir -RepoRoot $repoRoot -Stamp $stamp
    $logFile = Join-Path $runtimeDir 'run.log'
    $resultFile = Join-Path $runtimeDir 'result.json'
    $runId = "$Repo-watchdog-$stamp"

    $envVars = Read-DotEnvFile -Path (Join-Path $repoRoot '.sandcastle/.env')
    $supabaseUrl = $envVars['SUPABASE_URL']
    $supabaseKey = $envVars['SUPABASE_KEY']
    $tgToken     = $envVars['TELEGRAM_BOT_TOKEN']
    $tgChatId    = $envVars['TELEGRAM_CHAT_ID']
    if ($env:SUPABASE_URL)        { $supabaseUrl = $env:SUPABASE_URL }
    if ($env:SUPABASE_KEY)        { $supabaseKey = $env:SUPABASE_KEY }
    if ($env:TELEGRAM_BOT_TOKEN)  { $tgToken     = $env:TELEGRAM_BOT_TOKEN }
    if ($env:TELEGRAM_CHAT_ID)    { $tgChatId    = $env:TELEGRAM_CHAT_ID }

    $windowEndDt = Resolve-WindowEnd -WindowEnd $WindowEnd

    function Record([string]$status, [string]$summary, [hashtable]$llm, [string]$reason) {
        try {
            Write-OutcomeRecord -SupabaseUrl $supabaseUrl -SupabaseKey $supabaseKey `
                -Repo $Repo -Status $status -Summary $summary -LlmMetrics $llm `
                -RunId $runId | Out-Null
        } catch {
            Write-Warning "outcome_record write failed: $_"
        }
        if ((Test-IsInfraDown -Reason $reason)) {
            $msg = "[sandcastle:$Repo] $reason | run=$runId | log=$logFile"
            try {
                Send-TelegramAlert -BotToken $tgToken -ChatId $tgChatId -Message $msg | Out-Null
            } catch {
                Write-Warning "telegram alert failed: $_"
            }
        }
    }

    # 1. Docker
    if (-not (Test-DockerRunning)) {
        Write-Host "[watchdog] Docker not running -- autostarting."
        Start-DockerDesktop
        if (-not (Wait-DockerReady -TimeoutSec $DockerTimeoutSec)) {
            Record 'failure' "docker-down: daemon not ready within ${DockerTimeoutSec}s" @{} 'docker-down'
            throw "docker-down: daemon did not come up within ${DockerTimeoutSec}s"
        }
    }

    # 2. Ollama
    if (-not (Test-OllamaRunning)) {
        Write-Host "[watchdog] Ollama not running -- autostarting."
        Start-OllamaServer
        if (-not (Wait-OllamaReady -TimeoutSec $OllamaTimeoutSec)) {
            Record 'failure' "ollama-down: server not ready within ${OllamaTimeoutSec}s" @{} 'ollama-down'
            throw "ollama-down: server did not come up within ${OllamaTimeoutSec}s"
        }
    }

    # 3. Iterate (soft-stop on window expiry between iterations)
    $totalUsage = @{ input_tokens = 0; output_tokens = 0; cache_read_input_tokens = 0; cache_creation_input_tokens = 0; model = $Model }
    $allCommits = @()
    $branch = $null
    $iter = 0
    $partialReason = $null

    while ($iter -lt $MaxIterations) {
        if (Test-WindowExpired -WindowEnd $windowEndDt) {
            $partialReason = 'window-expired'
            break
        }

        $iter++
        Write-Host "[watchdog] iteration $iter/$MaxIterations"

        $invocation = Invoke-Sandcastle -RepoRoot $repoRoot -Model $Model `
            -MaxIterations 1 -ResultFile $resultFile -LogFile $logFile -RunId $runId

        if (-not $invocation.ok) {
            $reason = if ($invocation.reason) { $invocation.reason } else { "exit=$($invocation.exitCode)" }
            Record 'failure' "sandcastle invocation failed: $reason" $totalUsage $reason
            throw "sandcastle invocation failed: $reason"
        }

        $r = $invocation.result
        $branch = $r.branch
        if ($r.commits) { $allCommits += $r.commits }
        foreach ($it in $r.iterations) {
            if ($it.usage) {
                $totalUsage.input_tokens               += [int]$it.usage.inputTokens
                $totalUsage.output_tokens              += [int]$it.usage.outputTokens
                $totalUsage.cache_read_input_tokens    += [int]$it.usage.cacheReadInputTokens
                $totalUsage.cache_creation_input_tokens+= [int]$it.usage.cacheCreationInputTokens
            }
        }
    }

    if ($partialReason) {
        $summary = "partial:$partialReason -- branch=$branch iterations=$iter commits=$($allCommits.Count)"
        Record 'partial' $summary $totalUsage ''
        Write-Host "[watchdog] $summary"
        return
    }

    $summary = "success -- branch=$branch iterations=$iter commits=$($allCommits.Count)"
    Record 'success' $summary $totalUsage ''
    Write-Host "[watchdog] $summary"
}

# Entry guard: only run when invoked as a script with a -Repo argument.
# Dot-sourcing without arguments (Pester) loads functions but does not execute.
if (-not $NoExecute -and $Repo) {
    Invoke-Watchdog -Repo $Repo -MaxIterations $MaxIterations -Model $Model `
        -WindowEnd $WindowEnd -DockerTimeoutSec $DockerTimeoutSec `
        -OllamaTimeoutSec $OllamaTimeoutSec
}
