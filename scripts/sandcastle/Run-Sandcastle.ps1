# Run-Sandcastle.ps1 -- slice 4 watchdog wrapper for the AFK sandcastle loop.
# Single entry point production code paths use instead of `tsx main.mts`.
# Decision: 0c3017c6 (fail-fast + autostart + soft-stop window).
#
# Responsibilities:
#  1. Ensure Docker daemon is up (autostart + poll, fail fast on timeout).
#  2. Ensure Ollama is up (autostart + poll, fail fast on timeout).
#  3. Prune stale .sandcastle/runtime/<stamp>/ dirs (keep N most recent).
#  4. Run sandcastle one or more iterations via tsx/npm.
#  5. Parse the result JSON dumped by main.mts.
#  6. Write outcome_record to Supabase via PostgREST anon insert.
#  7. Honor a safe-hours window -- soft-stop between iterations only.
#
# Telegram (slice 6) and multi-tier escalation (slice 5) are layered later.
#
# -RuntimeRetention <N> (default 30) controls the runtime-dir sweep at the
# start of each watchdog run. Env var SANDCASTLE_RUNTIME_RETENTION overrides.
# Pass -RuntimeRetention -1 to disable sweep. (#572)

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

    # Slice 5 (#543): multi-tier escalation. -Model is Tier 0; -Tier1Model is
    # the smaller Ollama fallback on OOM/crash; -Tier2Provider switches to a
    # remote API (deepseek | claude) on persistent failure. Empty values
    # disable that tier (the chain still runs as a single-tier loop).
    [string]$Tier1Model,

    [ValidateSet('', 'deepseek', 'claude')]
    [string]$Tier2Provider = '',

    # 2026-05-14: skip Tier 0/1 Ollama and run Tier 2 as primary. Local Ollama
    # models fail the real-Claude-Code tool_use fidelity check (memory
    # ollama_bench_must_measure_tool_use_fidelity). Recommended for AFK runs;
    # the OOM-escalation chain stays available when this flag is off.
    [switch]$Tier2AsPrimary,

    # Runtime-dir retention: keep the N most-recent .sandcastle/runtime/<stamp>/
    # directories on watchdog entry, prune older ones. -1 disables the sweep.
    # Env var SANDCASTLE_RUNTIME_RETENTION overrides this if set (#572).
    [int]$RuntimeRetention = 30,

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

function Invoke-RuntimeSweep {
    # Prune .sandcastle/runtime/<stamp>/ to the most recent $Keep directories.
    # Used by Invoke-Watchdog before each run so nightly AFK loops don't fill
    # disk with stale per-iteration runtime dirs. $Keep -lt 0 disables sweep.
    [CmdletBinding()]
    param(
        [string]$RuntimeRoot,
        [int]$Keep = 30
    )
    if ($Keep -lt 0) { return @() }
    if (-not (Test-Path -LiteralPath $RuntimeRoot)) { return @() }
    $dirs = Get-ChildItem -LiteralPath $RuntimeRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object -Property Name -Descending
    if ($dirs.Count -le $Keep) { return @() }
    $toPrune = $dirs | Select-Object -Skip $Keep
    $pruned = @()
    foreach ($d in $toPrune) {
        try {
            Remove-Item -LiteralPath $d.FullName -Recurse -Force -ErrorAction Stop
            $pruned += $d.Name
        } catch {
            Write-Warning "runtime-sweep: failed to remove $($d.FullName): $_"
        }
    }
    return $pruned
}

function Invoke-NpmSandcastle {
    # Thin wrapper around `npm run sandcastle` extracted from Invoke-Sandcastle
    # so the npm call can be mocked in tests (#572). The PS 5.1 stderr-wrapping
    # workaround (#608) lives here.
    [CmdletBinding()]
    param([string]$LogFile)
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        return [pscustomobject]@{ cmdNotFound = $true; exitCode = -1 }
    }
    # PS 5.1 wraps every native-command stderr line as a NativeCommandError
    # under EAP=Stop, killing the watchdog on npm's first stderr line
    # (any warning). Delegate the 2>&1 merge to cmd.exe so PS only sees
    # a single stdout stream -- no wrapping, no terminating exception.
    # See issue #608.
    $combined = & cmd.exe /c 'npm run --silent sandcastle 2>&1'
    $exitCode = $LASTEXITCODE
    if ($LogFile) {
        $combined | Out-File -FilePath $LogFile -Encoding utf8 -Append
    }
    return [pscustomobject]@{ cmdNotFound = $false; exitCode = $exitCode }
}

function Invoke-Sandcastle {
    [CmdletBinding()]
    param(
        [string]$RepoRoot,
        [string]$Model,
        [int]$MaxIterations,
        [string]$ResultFile,
        [string]$LogFile,
        [string]$RunId,
        # Slice 5 (#543) tier overrides. Empty => main.mts falls back to Ollama
        # defaults via OLLAMA_BASE_URL / "ollama" auth.
        [string]$BaseUrl,
        [string]$AuthToken,
        # Forced-target issue (escalation retries). Empty => agent free-picks.
        [string]$TargetIssue
    )

    # Stale result.json from a prior iteration would otherwise be silently
    # re-read on a partial-write crash. Always start clean.
    Remove-Item -LiteralPath $ResultFile -ErrorAction SilentlyContinue

    # Save-and-restore so dot-sourced Pester runs don't bleed values across calls.
    $prev = @{
        SANDCASTLE_RESULT_FILE      = $env:SANDCASTLE_RESULT_FILE
        SANDCASTLE_MAX_ITERATIONS   = $env:SANDCASTLE_MAX_ITERATIONS
        SANDCASTLE_RUN_ID           = $env:SANDCASTLE_RUN_ID
        SANDCASTLE_AGENT_MODEL      = $env:SANDCASTLE_AGENT_MODEL
        SANDCASTLE_AGENT_BASE_URL   = $env:SANDCASTLE_AGENT_BASE_URL
        SANDCASTLE_AGENT_AUTH_TOKEN = $env:SANDCASTLE_AGENT_AUTH_TOKEN
        SANDCASTLE_TARGET_ISSUE     = $env:SANDCASTLE_TARGET_ISSUE
        OLLAMA_MODEL                = $env:OLLAMA_MODEL
    }
    $env:SANDCASTLE_RESULT_FILE    = $ResultFile
    $env:SANDCASTLE_MAX_ITERATIONS = "$MaxIterations"
    if ($RunId)       { $env:SANDCASTLE_RUN_ID           = $RunId }
    if ($Model)       { $env:SANDCASTLE_AGENT_MODEL      = $Model
                        $env:OLLAMA_MODEL                = $Model }
    if ($BaseUrl)     { $env:SANDCASTLE_AGENT_BASE_URL   = $BaseUrl }
    if ($AuthToken)   { $env:SANDCASTLE_AGENT_AUTH_TOKEN = $AuthToken }
    # TargetIssue: pass empty string verbatim so retries can clear it.
    $env:SANDCASTLE_TARGET_ISSUE = "$TargetIssue"

    Push-Location -LiteralPath $RepoRoot
    $cmdNotFound = $false
    try {
        $npmResult = Invoke-NpmSandcastle -LogFile $LogFile
        $cmdNotFound = $npmResult.cmdNotFound
        $exitCode = $npmResult.exitCode
    } finally {
        Pop-Location
        $env:SANDCASTLE_RESULT_FILE      = $prev.SANDCASTLE_RESULT_FILE
        $env:SANDCASTLE_MAX_ITERATIONS   = $prev.SANDCASTLE_MAX_ITERATIONS
        $env:SANDCASTLE_RUN_ID           = $prev.SANDCASTLE_RUN_ID
        $env:SANDCASTLE_AGENT_MODEL      = $prev.SANDCASTLE_AGENT_MODEL
        $env:SANDCASTLE_AGENT_BASE_URL   = $prev.SANDCASTLE_AGENT_BASE_URL
        $env:SANDCASTLE_AGENT_AUTH_TOKEN = $prev.SANDCASTLE_AGENT_AUTH_TOKEN
        $env:SANDCASTLE_TARGET_ISSUE     = $prev.SANDCASTLE_TARGET_ISSUE
        $env:OLLAMA_MODEL                = $prev.OLLAMA_MODEL
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
# Tier escalation -- slice 5 (#543, decision f8e27d53)
# ---------------------------------------------------------------------------
#
# Detects model-side resource exhaustion (OOM / model-load failure) so the
# watchdog can retry on a smaller Ollama model (Tier 1) or escalate to a
# remote API (Tier 2). False positives are cheap (one extra retry); false
# negatives downgrade to a generic failure outcome, which is still safe.

# Substrings (case-insensitive) that indicate the agent's model itself fell
# over due to memory pressure rather than a logic / agent-side error.
$script:OOMSignatures = @(
    'out of memory',
    'oom',
    'cuda out of memory',
    'model requires more system memory',
    'model load failed',
    'failed to load model',
    'unable to allocate'
)

function Test-IsOOM {
    [CmdletBinding()]
    param(
        [string]$Reason,
        [string]$LogFile
    )
    if ($Reason -match '^exit=137$') { return $true }   # SIGKILL on Linux OOM
    if ($Reason -like 'json-parse-error*') { return $false }  # malformed result, not OOM
    if (-not $LogFile -or -not (Test-Path -LiteralPath $LogFile)) { return $false }
    try {
        $content = Get-Content -LiteralPath $LogFile -Raw -Encoding utf8 -ErrorAction Stop
    } catch {
        return $false
    }
    if (-not $content) { return $false }
    foreach ($sig in $script:OOMSignatures) {
        if ($content -match [regex]::Escape($sig)) { return $true }
    }
    return $false
}

function Get-IssueFromBranch {
    [CmdletBinding()]
    param([string]$Branch)
    if (-not $Branch) { return $null }
    if ($Branch -match '^(?:feat|fix|chore)/(\d+)\b') { return [int]$Matches[1] }
    return $null
}

function Get-IssueLabels {
    [CmdletBinding()]
    param([int]$Issue, [string]$RepoSlug)
    if (-not $Issue) { return @() }
    try {
        $args = @('issue', 'view', "$Issue", '--json', 'labels', '--jq', '[.labels[].name]')
        if ($RepoSlug) { $args += @('--repo', $RepoSlug) }
        $raw = & gh @args 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $raw) { return @() }
        return ($raw | ConvertFrom-Json)
    } catch {
        return @()
    }
}

function Add-IssueLabel {
    [CmdletBinding()]
    param([int]$Issue, [string]$Label, [string]$RepoSlug)
    if (-not $Issue -or -not $Label) { return $false }
    $args = @('issue', 'edit', "$Issue", '--add-label', $Label)
    if ($RepoSlug) { $args += @('--repo', $RepoSlug) }
    & gh @args 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Resolve-Tier2Config {
    [CmdletBinding()]
    param(
        [string]$Provider,        # 'deepseek' | 'claude' | ''
        [int]$Issue,
        [string]$RepoSlug,
        [hashtable]$EnvVars       # parsed .sandcastle/.env
    )
    if (-not $Provider) { return $null }

    # `use-claude-api` label flips Tier 2 from the configured default to
    # Claude (AC: cron runs never auto-promote to Claude; the label is the
    # explicit owner gate).
    $labels = Get-IssueLabels -Issue $Issue -RepoSlug $RepoSlug
    $effective = if ($labels -contains 'use-claude-api') { 'claude' } else { $Provider }

    function Coalesce([string]$a, [string]$b) {
        if ([string]::IsNullOrWhiteSpace($a)) { return $b } else { return $a }
    }
    switch ($effective) {
        'deepseek' {
            return @{
                Provider  = 'deepseek'
                Model     = (Coalesce $EnvVars['DEEPSEEK_MODEL']    'deepseek-coder')
                BaseUrl   = (Coalesce $EnvVars['DEEPSEEK_BASE_URL'] 'https://api.deepseek.com/anthropic')
                AuthToken = $EnvVars['DEEPSEEK_API_KEY']
            }
        }
        'claude' {
            return @{
                Provider  = 'claude'
                Model     = (Coalesce $EnvVars['CLAUDE_MODEL']    'claude-haiku-4-5-20251001')
                BaseUrl   = (Coalesce $EnvVars['CLAUDE_BASE_URL'] 'https://api.anthropic.com')
                AuthToken = $EnvVars['ANTHROPIC_API_KEY']
            }
        }
        default { return $null }
    }
}

# ---------------------------------------------------------------------------
# Telegram alerting -- infra-down only (slice 6, #544, decision 0c3017c6).
# Routine partial / agent-side failure / OOM-escalated outcomes stay silent.
# ---------------------------------------------------------------------------

# Reasons that warrant waking up the principal in chat. Anything else
# (agent-side exit codes, partial:window-expired, success) stays silent
# so morning chat carries signal not noise.
#
# Note: AC #534/#544 mention 'container-launch-fail' as a class but the
# watchdog has no current call site that emits that literal reason --
# Docker container start failures surface as `exit=N` from sandcastle's
# tsx/npm wrapper, classified agent-side by Test-IsInfraDown. Wiring a
# Docker-level health check that distinguishes "image missing / container
# crashed at start" from agent-side errors is tracked in the watchdog
# hardening follow-up #572.
$script:TelegramInfraReasons = @(
    'docker-down',
    'ollama-down',
    'npm-not-found',
    'no-result-file'
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

function Format-RedactedError {
    [CmdletBinding()]
    param([string]$Message, [string]$Secret)
    if (-not $Secret) { return $Message }
    return ($Message -replace [regex]::Escape($Secret), '<TOKEN-REDACTED>')
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
        return
    }
    # 200-char cap is an AC; -3 for the '...' tail.
    $maxLen = 200
    if ($Message.Length -gt $maxLen) {
        $Message = $Message.Substring(0, $maxLen - 3) + '...'
    }
    $url = "https://api.telegram.org/bot$BotToken/sendMessage"
    # JSON-encoded body for parity with Write-OutcomeRecord (the file's other
    # HTTP call) and explicit content-type. Telegram accepts both, but
    # consistency makes drift / regressions easier to spot.
    $body = @{ chat_id = $ChatId; text = $Message } | ConvertTo-Json -Compress
    try {
        return Invoke-RestMethod -Uri $url -Method Post -Body $body -ContentType 'application/json' -ErrorAction Stop
    } catch {
        # Sanitize before re-raising: Invoke-RestMethod error messages
        # include the request URL with the bot token embedded. Strip it
        # so callers / logs only ever see "<TOKEN-REDACTED>".
        throw "telegram alert failed: $(Format-RedactedError -Message "$_" -Secret $BotToken)"
    }
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
        [int]$OllamaTimeoutSec,
        # Slice 5 (#543) tier overrides; empty disables the corresponding tier.
        [string]$Tier1Model,
        [string]$Tier2Provider,
        # 2026-05-14: when set, skip Tier 0/1 Ollama entirely and run Tier 2
        # (DeepSeek / Anthropic API) as the primary invocation. Local Ollama
        # models fail the real-Claude-Code tool_use fidelity check — see memory
        # ollama_bench_must_measure_tool_use_fidelity. Default $false preserves
        # the original OOM-escalation chain used by existing tests.
        [switch]$Tier2AsPrimary,
        # #572: runtime-dir retention; env var SANDCASTLE_RUNTIME_RETENTION wins.
        [int]$RuntimeRetention = 30
    )

    $repoRoot = Get-RepoRoot -Repo $Repo
    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')

    $retention = $RuntimeRetention
    if ($env:SANDCASTLE_RUNTIME_RETENTION) {
        $parsed = 0
        if ([int]::TryParse($env:SANDCASTLE_RUNTIME_RETENTION, [ref]$parsed)) {
            $retention = $parsed
        }
    }
    $runtimeRoot = Join-Path $repoRoot '.sandcastle/runtime'
    $pruned = Invoke-RuntimeSweep -RuntimeRoot $runtimeRoot -Keep $retention
    if ($pruned.Count -gt 0) {
        Write-Host "[watchdog] runtime-sweep: pruned $($pruned.Count) stale dirs (kept $retention)"
    }

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

    # 2. Resolve Tier 2 primary (DeepSeek / Anthropic API) — when set, the
    #    watchdog skips local Ollama tiers entirely. Local Ollama failed the
    #    real-Claude-Code tool_use fidelity check on qwen2.5-coder:14b (markdown
    #    JSON fence) and qwen3-coder:30b (Hermes-XML) — see memory
    #    ollama_bench_must_measure_tool_use_fidelity + smoke 2026-05-14. Remote
    #    Anthropic-compat endpoints (DeepSeek native, Anthropic itself) emit
    #    structured tool_use blocks reliably.
    $repoSlug = switch ($Repo) {
        'jarvis'   { 'Osasuwu/jarvis' }
        'redrobot' { 'SergazyNarynov/redrobot' }
        default    { '' }
    }
    $tier2Primary = $null
    if ($Tier2AsPrimary -and $Tier2Provider) {
        $tier2Primary = Resolve-Tier2Config -Provider $Tier2Provider -Issue '' `
            -RepoSlug $repoSlug -EnvVars $envVars
        if (-not ($tier2Primary -and $tier2Primary.AuthToken)) {
            Write-Warning "[watchdog] Tier 2 ($Tier2Provider) requested as primary but config incomplete (key missing) — falling back to local Ollama tiers."
            $tier2Primary = $null
        } else {
            Write-Host "[watchdog] Tier 2 ($($tier2Primary.Provider): $($tier2Primary.Model)) is primary — Tier 0/1 Ollama disabled for this run."
        }
    }

    # 3. Ollama (skipped when Tier 2 is primary — no local model will be invoked)
    if (-not $tier2Primary) {
        if (-not (Test-OllamaRunning)) {
            Write-Host "[watchdog] Ollama not running -- autostarting."
            Start-OllamaServer
            if (-not (Wait-OllamaReady -TimeoutSec $OllamaTimeoutSec)) {
                Record 'failure' "ollama-down: server not ready within ${OllamaTimeoutSec}s" @{} 'ollama-down'
                throw "ollama-down: server did not come up within ${OllamaTimeoutSec}s"
            }
        }
    }

    # 4. Iterate (soft-stop on window expiry between iterations)
    $totalUsage = @{ input_tokens = 0; output_tokens = 0; cache_read_input_tokens = 0; cache_creation_input_tokens = 0; model = $Model }
    $allCommits = @()
    $branch = $null
    $iter = 0
    $partialReason = $null
    $tierCompleted = $null    # 'tier0' | 'tier1' | 'tier2:deepseek' | 'tier2:claude'

    while ($iter -lt $MaxIterations) {
        if (Test-WindowExpired -WindowEnd $windowEndDt) {
            $partialReason = 'window-expired'
            break
        }

        $iter++
        Write-Host "[watchdog] iteration $iter/$MaxIterations"

        if ($tier2Primary) {
            # ----- Tier 2 primary: remote Anthropic-compat endpoint (DeepSeek / Anthropic API) -----
            $invocation = Invoke-Sandcastle -RepoRoot $repoRoot -Model $tier2Primary.Model `
                -MaxIterations 1 -ResultFile $resultFile -LogFile $logFile -RunId $runId `
                -BaseUrl $tier2Primary.BaseUrl -AuthToken $tier2Primary.AuthToken `
                -TargetIssue ''
            $tierUsed = "tier2:$($tier2Primary.Provider)"
            $targetIssue = Get-IssueFromBranch -Branch $invocation.result.branch
            $oomDetected = $false
        } else {
            # ----- Tier 0: primary Ollama model -----
            $invocation = Invoke-Sandcastle -RepoRoot $repoRoot -Model $Model `
                -MaxIterations 1 -ResultFile $resultFile -LogFile $logFile -RunId $runId `
                -TargetIssue ''
            $tierUsed = 'tier0'
            $targetIssue = Get-IssueFromBranch -Branch $invocation.result.branch
            $oomDetected = (-not $invocation.ok) -and (Test-IsOOM -Reason $invocation.reason -LogFile $logFile)
        }

        # ----- Tier 1: smaller Ollama model on OOM/crash (only when Tier 2 is NOT primary) -----
        if (-not $tier2Primary -and -not $invocation.ok -and $Tier1Model -and $oomDetected) {
            Write-Host "[watchdog] Tier 0 OOM detected -- escalating to Tier 1 model: $Tier1Model"
            $invocation = Invoke-Sandcastle -RepoRoot $repoRoot -Model $Tier1Model `
                -MaxIterations 1 -ResultFile $resultFile -LogFile $logFile -RunId $runId `
                -TargetIssue ([string]$targetIssue)
            $tierUsed = 'tier1'
            if (-not $targetIssue) {
                $targetIssue = Get-IssueFromBranch -Branch $invocation.result.branch
            }
        }

        # ----- Tier 2: remote API on persistent failure -----
        # Reached when the chain saw a Tier-0 OOM (gate above set $oomDetected)
        # and the chain still hasn't recovered. Tier 1 may have been skipped
        # entirely (no $Tier1Model) or it may have run and failed for any
        # reason -- both qualify per AC #3 ("persistent failure after Tier 1").
        if (-not $tier2Primary -and -not $invocation.ok -and $oomDetected -and $Tier2Provider) {
            $tier2 = Resolve-Tier2Config -Provider $Tier2Provider -Issue $targetIssue `
                -RepoSlug $repoSlug -EnvVars $envVars
            if ($tier2 -and $tier2.AuthToken) {
                Write-Host "[watchdog] Tier 1 failed -- escalating to Tier 2 ($($tier2.Provider): $($tier2.Model))"
                $invocation = Invoke-Sandcastle -RepoRoot $repoRoot -Model $tier2.Model `
                    -MaxIterations 1 -ResultFile $resultFile -LogFile $logFile -RunId $runId `
                    -BaseUrl $tier2.BaseUrl -AuthToken $tier2.AuthToken `
                    -TargetIssue ([string]$targetIssue)
                $tierUsed = "tier2:$($tier2.Provider)"
            } else {
                Write-Warning "[watchdog] Tier 2 requested but config incomplete (provider=$Tier2Provider, key set=$([bool]$tier2.AuthToken)); skipping."
            }
        }

        if (-not $invocation.ok) {
            $reason = if ($invocation.reason) { $invocation.reason } else { "exit=$($invocation.exitCode)" }
            # Full chain failure: label the issue if we know which one was attempted.
            $labelApplied = $false
            if ($targetIssue -and $repoSlug) {
                $labelApplied = Add-IssueLabel -Issue $targetIssue -Label 'too-large-for-local' -RepoSlug $repoSlug
            }
            $totalUsage.tier = $tierUsed
            $totalUsage.too_large_for_local = $labelApplied
            Record 'failure' "sandcastle invocation failed: $reason (tier=$tierUsed issue=$targetIssue label=$labelApplied)" $totalUsage $reason
            throw "sandcastle invocation failed: $reason"
        }

        $tierCompleted = $tierUsed
        $r = $invocation.result
        $branch = $r.branch
        $totalUsage.tier = $tierCompleted
        if ($tierCompleted -ne 'tier0') {
            $totalUsage.model = $r.model    # not always set; best-effort
            if (-not $totalUsage.model) {
                # Fall back to tier label so reviewers see which tier won.
                $totalUsage.model = $tierCompleted
            }
        }
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
        -OllamaTimeoutSec $OllamaTimeoutSec `
        -Tier1Model $Tier1Model -Tier2Provider $Tier2Provider `
        -Tier2AsPrimary:$Tier2AsPrimary `
        -RuntimeRetention $RuntimeRetention
}
