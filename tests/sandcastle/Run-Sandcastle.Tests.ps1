# Pester tests for scripts/sandcastle/Run-Sandcastle.ps1 (issue #541).
# Exercises the daemon-state matrix and soft-stop window logic with mocked
# health probes -- no real Docker/Ollama/Supabase calls.
#
# Compatible with Pester 3.4 (built-in on Windows PowerShell 5.1) -- uses
# `Should Be` and `Assert-MockCalled` rather than the Pester 5 dash-syntax.
#
# Run:
#   Invoke-Pester -Path tests/sandcastle/Run-Sandcastle.Tests.ps1

$script:WatchdogPath = Join-Path $PSScriptRoot '..\..\scripts\sandcastle\Run-Sandcastle.ps1'
. $script:WatchdogPath -NoExecute

Describe 'Resolve-WindowEnd' {
    It 'returns null for empty input' {
        Resolve-WindowEnd -WindowEnd '' | Should BeNullOrEmpty
    }

    It 'parses HH:mm as today' {
        $end = Resolve-WindowEnd -WindowEnd '23:30'
        $end.Hour   | Should Be 23
        $end.Minute | Should Be 30
        $end.Date   | Should Be (Get-Date).Date
    }

    It 'parses ISO datetime' {
        $end = Resolve-WindowEnd -WindowEnd '2026-05-09T03:00:00'
        $end.Year | Should Be 2026
        $end.Hour | Should Be 3
    }
}

Describe 'Test-WindowExpired' {
    It 'returns false when window is null' {
        Test-WindowExpired -WindowEnd $null | Should Be $false
    }

    It 'returns true when window is in the past' {
        Test-WindowExpired -WindowEnd ((Get-Date).AddMinutes(-5)) | Should Be $true
    }

    It 'returns false when window is in the future' {
        Test-WindowExpired -WindowEnd ((Get-Date).AddMinutes(5)) | Should Be $false
    }
}

Describe 'Wait-DockerReady' {
    It 'returns true when Docker becomes ready before timeout' {
        Mock Test-DockerRunning { $true }
        Wait-DockerReady -TimeoutSec 2 | Should Be $true
    }

    It 'returns false when Docker never comes up within timeout' {
        Mock Test-DockerRunning { $false }
        Wait-DockerReady -TimeoutSec 1 | Should Be $false
    }
}

Describe 'Wait-OllamaReady' {
    It 'returns true when Ollama is up' {
        Mock Test-OllamaRunning { $true }
        Wait-OllamaReady -TimeoutSec 1 | Should Be $true
    }

    It 'returns false when Ollama times out' {
        Mock Test-OllamaRunning { $false }
        Wait-OllamaReady -TimeoutSec 1 | Should Be $false
    }
}

Describe 'Read-DotEnvFile' {
    $tmp = Join-Path $env:TEMP "sandcastle-watchdog-env-$([guid]::NewGuid()).env"
    @(
        '# comment',
        'SUPABASE_URL=https://example.supabase.co',
        'SUPABASE_KEY="anon-key-here"',
        "QUOTED='single'",
        # Unbalanced quotes must survive verbatim (regression: naive Trim
        # corrupted base64 padding `key=` and apostrophes in values).
        'BASE64_KEY=abcd1234==',
        "APOS_VAL=it's",
        '',
        'INVALID_LINE_NO_EQUALS'
    ) | Set-Content -Path $tmp -Encoding UTF8

    It 'parses key=value, ignores comments and blanks' {
        $vars = Read-DotEnvFile -Path $tmp
        $vars['SUPABASE_URL']                          | Should Be 'https://example.supabase.co'
        $vars['SUPABASE_KEY']                          | Should Be 'anon-key-here'
        $vars['QUOTED']                                | Should Be 'single'
        $vars.ContainsKey('INVALID_LINE_NO_EQUALS')    | Should Be $false
    }

    It 'preserves base64 padding and apostrophes' {
        $vars = Read-DotEnvFile -Path $tmp
        $vars['BASE64_KEY'] | Should Be 'abcd1234=='
        $vars['APOS_VAL']   | Should Be "it's"
    }

    It 'returns empty hashtable for missing file' {
        $vars = Read-DotEnvFile -Path "$env:TEMP\does-not-exist-$([guid]::NewGuid()).env"
        $vars.Count | Should Be 0
    }

    Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
}

Describe 'Test-IsInfraDown' {
    It 'returns true for whitelisted infra reasons' {
        Test-IsInfraDown -Reason 'docker-down'    | Should Be $true
        Test-IsInfraDown -Reason 'ollama-down'    | Should Be $true
        Test-IsInfraDown -Reason 'npm-not-found'  | Should Be $true
        Test-IsInfraDown -Reason 'no-result-file' | Should Be $true
    }

    It 'matches reasons with trailing detail (StartsWith)' {
        Test-IsInfraDown -Reason 'docker-down: daemon timed out' | Should Be $true
    }

    It 'returns false for routine / agent-side reasons' {
        Test-IsInfraDown -Reason ''                  | Should Be $false
        Test-IsInfraDown -Reason 'exit=7'            | Should Be $false
        Test-IsInfraDown -Reason 'window-expired'    | Should Be $false
        Test-IsInfraDown -Reason 'json-parse-error'  | Should Be $false
    }
}

Describe 'Send-TelegramAlert' {
    It 'returns null without HTTP call when token/chat-id missing' {
        Mock Invoke-RestMethod { 'should-not-be-called' }
        Send-TelegramAlert -BotToken '' -ChatId '' -Message 'hello' | Should BeNullOrEmpty
        Assert-MockCalled Invoke-RestMethod -Times 0 -Exactly -Scope It
    }

    It 'truncates messages over 200 chars' {
        $script:captured = $null   # script-scoped; clear before mock so prior tests don't bleed in.
        Mock Invoke-RestMethod -ParameterFilter { $true } -MockWith {
            $script:captured = $Body
            'ok'
        }
        $long = ('x' * 250)
        Send-TelegramAlert -BotToken 't' -ChatId '1' -Message $long | Out-Null
        # Body is JSON-encoded; parse to inspect the text field.
        $parsed = $script:captured | ConvertFrom-Json
        $parsed.text.Length | Should Be 200
        $parsed.text        | Should Match '\.\.\.$'
    }

}

Describe 'Format-RedactedError' {
    It 'replaces every occurrence of the secret with TOKEN-REDACTED' {
        $err = "Invoke-RestMethod : (404) https://api.telegram.org/botSECRET-TOKEN/sendMessage failed; SECRET-TOKEN exposed twice"
        $out = Format-RedactedError -Message $err -Secret 'SECRET-TOKEN'
        $out | Should Match '<TOKEN-REDACTED>'
        $out | Should Not Match 'SECRET-TOKEN'
    }

    It 'returns input unchanged when secret is empty (no global wipe)' {
        $err = 'boom'
        Format-RedactedError -Message $err -Secret '' | Should Be 'boom'
    }

    It 'escapes regex metacharacters in the secret' {
        $err = 'leaked: a.b+c'
        $out = Format-RedactedError -Message $err -Secret 'a.b+c'
        $out | Should Match '<TOKEN-REDACTED>'
        $out | Should Not Match 'a\.b\+c'
    }
}

Describe 'Test-IsOOM' {
    It 'flags exit code 137 (Linux OOM-kill) without a log file' {
        Test-IsOOM -Reason 'exit=137' -LogFile '' | Should Be $true
    }

    It 'rejects unrelated exit codes' {
        Test-IsOOM -Reason 'exit=7' -LogFile '' | Should Be $false
    }

    It 'rejects json-parse-error even if the log mentions OOM' {
        # Malformed result.json comes from a torn write, not from a model
        # OOM -- escalating to a smaller model would not help.
        $tmp = Join-Path $env:TEMP "oom-log-$([guid]::NewGuid()).txt"
        'CUDA out of memory' | Set-Content -Path $tmp -Encoding UTF8
        try {
            Test-IsOOM -Reason 'json-parse-error: Unexpected token' -LogFile $tmp | Should Be $false
        } finally {
            Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
        }
    }

    It 'matches OOM substrings in the log file (case-insensitive)' {
        $tmp = Join-Path $env:TEMP "oom-log-$([guid]::NewGuid()).txt"
        'ollama serve: model requires more system memory than available' | Set-Content -Path $tmp -Encoding UTF8
        try {
            Test-IsOOM -Reason 'exit=1' -LogFile $tmp | Should Be $true
        } finally {
            Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
        }
    }

    It 'returns false when log file does not exist' {
        Test-IsOOM -Reason 'exit=1' -LogFile (Join-Path $env:TEMP "missing-$([guid]::NewGuid()).log") | Should Be $false
    }
}

Describe 'Get-IssueFromBranch' {
    It 'parses feat/<N>-slug' {
        Get-IssueFromBranch -Branch 'feat/543-multi-tier' | Should Be 543
    }
    It 'parses fix/<N>-slug' {
        Get-IssueFromBranch -Branch 'fix/42-broken' | Should Be 42
    }
    It 'returns null for unknown shapes' {
        Get-IssueFromBranch -Branch 'main' | Should BeNullOrEmpty
        Get-IssueFromBranch -Branch ''     | Should BeNullOrEmpty
        Get-IssueFromBranch -Branch $null  | Should BeNullOrEmpty
    }
}

Describe 'Resolve-Tier2Config' {
    It 'returns null when provider is empty' {
        Mock Get-IssueLabels { @() }
        Resolve-Tier2Config -Provider '' -Issue 1 -RepoSlug 'x/y' -EnvVars @{} | Should BeNullOrEmpty
    }

    It 'maps deepseek with envVar overrides + key' {
        Mock Get-IssueLabels { @() }
        $env = @{ DEEPSEEK_API_KEY = 'ds-secret'; DEEPSEEK_MODEL = 'ds-coder-mini' }
        $cfg = Resolve-Tier2Config -Provider 'deepseek' -Issue 99 -RepoSlug 'x/y' -EnvVars $env
        $cfg.Provider  | Should Be 'deepseek'
        $cfg.Model     | Should Be 'ds-coder-mini'
        $cfg.AuthToken | Should Be 'ds-secret'
        $cfg.BaseUrl   | Should Match '^https://'
    }

    It 'use-claude-api label flips deepseek default to claude' {
        Mock Get-IssueLabels { @('use-claude-api', 'priority:high') }
        $env = @{ ANTHROPIC_API_KEY = 'sk-ant-test'; DEEPSEEK_API_KEY = 'ds' }
        $cfg = Resolve-Tier2Config -Provider 'deepseek' -Issue 99 -RepoSlug 'x/y' -EnvVars $env
        $cfg.Provider  | Should Be 'claude'
        $cfg.AuthToken | Should Be 'sk-ant-test'
    }

    It 'leaves provider as deepseek when label missing' {
        Mock Get-IssueLabels { @('priority:medium') }
        $env = @{ DEEPSEEK_API_KEY = 'ds' }
        $cfg = Resolve-Tier2Config -Provider 'deepseek' -Issue 99 -RepoSlug 'x/y' -EnvVars $env
        $cfg.Provider | Should Be 'deepseek'
    }
}

Describe 'Invoke-Watchdog tier escalation matrix (slice 5, #543)' {
    BeforeEach {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }
        Mock Start-DockerDesktop { }
        Mock Start-OllamaServer  { }
        Mock Get-RepoRoot { $env:TEMP }
        Mock Read-DotEnvFile {
            @{
                SUPABASE_URL       = 'https://x'
                SUPABASE_KEY       = 'k'
                TELEGRAM_BOT_TOKEN = 't'
                TELEGRAM_CHAT_ID   = '1'
                DEEPSEEK_API_KEY   = 'ds-key'
                ANTHROPIC_API_KEY  = 'cl-key'
            }
        }
        Mock New-RuntimeDir { Join-Path $env:TEMP "sandcastle-tier-test-$([guid]::NewGuid())" }
        Mock Invoke-RuntimeSweep { @() }   # #572: keep sweep no-op in matrix tests
        Mock Write-OutcomeRecord { 'mocked' }
        Mock Send-TelegramAlert  { 'mocked' }
        Mock Add-IssueLabel      { $true }
        Mock Get-IssueLabels     { @() }
    }

    It 'AC: Tier 0 success -> no escalation, no labels, no Tier 1/2 invocation' {
        $script:calls = @()
        Mock Invoke-Sandcastle {
            $script:calls += $Model
            [pscustomobject]@{
                ok = $true; exitCode = 0; reason = $null
                result = [pscustomobject]@{
                    branch = 'feat/100-foo'; commits = @(); iterations = @()
                }
            }
        }
        Mock Test-IsOOM { $false }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'qwen-large' `
            -Tier1Model 'qwen-small' -Tier2Provider 'deepseek' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Invoke-Sandcastle -Times 1 -Exactly -Scope It
        Assert-MockCalled Add-IssueLabel    -Times 0 -Exactly -Scope It
        $script:calls[0] | Should Be 'qwen-large'
    }

    It 'AC: Tier 0 OOM -> exactly one Tier 1 retry, success records tier1' {
        $script:calls = @()
        $script:n = 0
        Mock Invoke-Sandcastle {
            $script:n++
            $script:calls += $Model
            if ($script:n -eq 1) {
                return [pscustomobject]@{ ok = $false; exitCode = 137; reason = 'exit=137'; result = $null }
            }
            return [pscustomobject]@{
                ok = $true; exitCode = 0; reason = $null
                result = [pscustomobject]@{
                    branch = 'feat/200-bar'; commits = @(); iterations = @()
                }
            }
        }
        Mock Test-IsOOM { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'qwen-large' `
            -Tier1Model 'qwen-small' -Tier2Provider 'deepseek' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Invoke-Sandcastle -Times 2 -Exactly -Scope It
        $script:calls[0] | Should Be 'qwen-large'
        $script:calls[1] | Should Be 'qwen-small'
        Assert-MockCalled Add-IssueLabel -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'success' -and $LlmMetrics.tier -eq 'tier1' }
    }

    It 'AC: Tier 0+1 fail -> Tier 2 (deepseek) success, no too-large label' {
        $script:n = 0
        $script:calls = @()
        Mock Invoke-Sandcastle {
            $script:n++
            $script:calls += @{ Model = $Model; BaseUrl = $BaseUrl; Token = $AuthToken }
            if ($script:n -le 2) {
                $branch = if ($script:n -eq 1) { 'feat/300-baz' } else { $null }
                return [pscustomobject]@{
                    ok = $false; exitCode = 137; reason = 'exit=137'
                    result = if ($branch) { [pscustomobject]@{ branch = $branch } } else { $null }
                }
            }
            return [pscustomobject]@{
                ok = $true; exitCode = 0; reason = $null
                result = [pscustomobject]@{
                    branch = 'feat/300-baz'; commits = @(); iterations = @()
                }
            }
        }
        Mock Test-IsOOM { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'qwen-large' `
            -Tier1Model 'qwen-small' -Tier2Provider 'deepseek' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Invoke-Sandcastle -Times 3 -Exactly -Scope It
        $script:calls[2].Token | Should Be 'ds-key'
        Assert-MockCalled Add-IssueLabel -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'success' -and $LlmMetrics.tier -eq 'tier2:deepseek' }
    }

    It 'AC: full chain fail -> too-large-for-local label applied + outcome=failure' {
        Mock Invoke-Sandcastle {
            [pscustomobject]@{
                ok = $false; exitCode = 137; reason = 'exit=137'
                result = [pscustomobject]@{ branch = 'feat/400-qux' }
            }
        }
        Mock Test-IsOOM { $true }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'qwen-large' `
              -Tier1Model 'qwen-small' -Tier2Provider 'deepseek' `
              -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5 } | Should Throw

        Assert-MockCalled Invoke-Sandcastle -Times 3 -Exactly -Scope It
        Assert-MockCalled Add-IssueLabel -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Issue -eq 400 -and $Label -eq 'too-large-for-local' }
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'failure' -and $Summary -like '*tier=tier2:deepseek*' }
    }

    It 'AC: use-claude-api label flips Tier 2 to Claude API key' {
        Mock Get-IssueLabels { @('use-claude-api') }
        $script:n = 0
        $script:tier2Token = $null
        Mock Invoke-Sandcastle {
            $script:n++
            if ($script:n -le 2) {
                return [pscustomobject]@{
                    ok = $false; exitCode = 137; reason = 'exit=137'
                    result = [pscustomobject]@{ branch = 'feat/500-claude' }
                }
            }
            $script:tier2Token = $AuthToken
            return [pscustomobject]@{
                ok = $true; exitCode = 0; reason = $null
                result = [pscustomobject]@{ branch = 'feat/500-claude'; commits = @(); iterations = @() }
            }
        }
        Mock Test-IsOOM { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'qwen-large' `
            -Tier1Model 'qwen-small' -Tier2Provider 'deepseek' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        $script:tier2Token | Should Be 'cl-key'
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $LlmMetrics.tier -eq 'tier2:claude' }
    }

    It 'AC: non-OOM Tier 0 failure does NOT escalate (logic error stays a failure)' {
        Mock Invoke-Sandcastle {
            [pscustomobject]@{ ok = $false; exitCode = 7; reason = 'exit=7'; result = $null }
        }
        Mock Test-IsOOM { $false }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'qwen-large' `
              -Tier1Model 'qwen-small' -Tier2Provider 'deepseek' `
              -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5 } | Should Throw

        Assert-MockCalled Invoke-Sandcastle -Times 1 -Exactly -Scope It
        Assert-MockCalled Add-IssueLabel    -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'failure' -and $LlmMetrics.tier -eq 'tier0' }
    }

    It 'no Tier 1 configured: Tier 0 OOM jumps directly to Tier 2 (deepseek)' {
        $script:n = 0
        Mock Invoke-Sandcastle {
            $script:n++
            if ($script:n -eq 1) {
                return [pscustomobject]@{
                    ok = $false; exitCode = 137; reason = 'exit=137'
                    result = [pscustomobject]@{ branch = 'feat/600-skip-tier1' }
                }
            }
            return [pscustomobject]@{
                ok = $true; exitCode = 0; reason = $null
                result = [pscustomobject]@{ branch = 'feat/600-skip-tier1'; commits = @(); iterations = @() }
            }
        }
        Mock Test-IsOOM { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'qwen-large' `
            -Tier1Model '' -Tier2Provider 'deepseek' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Invoke-Sandcastle -Times 2 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $LlmMetrics.tier -eq 'tier2:deepseek' }
    }
}

Describe 'Invoke-Watchdog daemon-state matrix' {
    BeforeEach {
        Mock Start-DockerDesktop { }
        Mock Start-OllamaServer  { }
        Mock Invoke-Sandcastle {
            [pscustomobject]@{
                ok       = $true
                exitCode = 0
                result   = [pscustomobject]@{
                    branch     = 'feat/test'
                    commits    = @(@{ sha = 'abc123' })
                    iterations = @(
                        [pscustomobject]@{
                            usage = [pscustomobject]@{
                                inputTokens               = 1000
                                outputTokens              = 200
                                cacheReadInputTokens      = 50
                                cacheCreationInputTokens  = 10
                            }
                        }
                    )
                }
            }
        }
        Mock Write-OutcomeRecord { 'mocked-outcome-id' }
        Mock Get-RepoRoot { $env:TEMP }
        Mock Read-DotEnvFile {
            @{
                SUPABASE_URL       = 'https://x'
                SUPABASE_KEY       = 'k'
                TELEGRAM_BOT_TOKEN = 'test-token'
                TELEGRAM_CHAT_ID   = '12345'
            }
        }
        # No real .sandcastle/runtime/* directories or HTTP calls during tests.
        Mock New-RuntimeDir { Join-Path $env:TEMP "sandcastle-test-$([guid]::NewGuid())" }
        Mock Invoke-RuntimeSweep { @() }   # #572: keep sweep no-op in matrix tests
        Mock Send-TelegramAlert { 'mocked-tg-response' }
    }

    It 'records success when both daemons are up (no Telegram alert)' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'qwen2.5-coder:14b' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Start-DockerDesktop -Times 0 -Exactly -Scope It
        Assert-MockCalled Start-OllamaServer  -Times 0 -Exactly -Scope It
        Assert-MockCalled Invoke-Sandcastle   -Times 1 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'success' }
        Assert-MockCalled Send-TelegramAlert  -Times 0 -Exactly -Scope It
    }

    It 'records failure: docker-down when Docker never starts (fires one Telegram alert)' {
        Mock Test-DockerRunning { $false }
        Mock Test-OllamaRunning { $true }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 1 -OllamaTimeoutSec 1 } | Should Throw 'docker-down'

        Assert-MockCalled Start-DockerDesktop -Times 1 -Exactly -Scope It
        Assert-MockCalled Invoke-Sandcastle   -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'failure' -and $Summary -like '*docker-down*' }
        # AC: Docker autostart timeout produces exactly one Telegram message
        # with run id, repo, and (via log path) timestamp.
        Assert-MockCalled Send-TelegramAlert -Times 1 -Exactly -Scope It `
            -ParameterFilter {
                $Message -like '*docker-down*' -and
                $Message -like '*sandcastle:jarvis*' -and
                $Message -like '*run=jarvis-watchdog-*' -and
                $Message -like '*log=*run.log*' -and
                $Message.Length -le 200
            }
    }

    It 'records failure: ollama-down when Ollama never starts (fires one Telegram alert)' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $false }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 1 -OllamaTimeoutSec 1 } | Should Throw 'ollama-down'

        Assert-MockCalled Start-OllamaServer  -Times 1 -Exactly -Scope It
        Assert-MockCalled Invoke-Sandcastle   -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'failure' -and $Summary -like '*ollama-down*' }
        Assert-MockCalled Send-TelegramAlert  -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Message -like '*ollama-down*' }
    }

    It 'records failure when both daemons time out (Docker fails first, fail-fast)' {
        Mock Test-DockerRunning { $false }
        Mock Test-OllamaRunning { $false }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 1 -OllamaTimeoutSec 1 } | Should Throw

        Assert-MockCalled Start-DockerDesktop -Times 1 -Exactly -Scope It
        Assert-MockCalled Start-OllamaServer  -Times 0 -Exactly -Scope It
        Assert-MockCalled Invoke-Sandcastle   -Times 0 -Exactly -Scope It
    }

    It 'soft-stops with partial:window-expired before iteration starts (no Telegram)' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 3 -Model 'm' `
            -WindowEnd ((Get-Date).AddMinutes(-1).ToString('s')) `
            -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Invoke-Sandcastle   -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'partial' -and $Summary -like '*window-expired*' }
        Assert-MockCalled Send-TelegramAlert  -Times 0 -Exactly -Scope It
    }

    It 'AC: 5-iteration AFK run with one OOM-escalated success produces zero Telegram calls' {
        # Slice 5 self-recovers OOM via model fallback. From the watchdog's
        # vantage point that iteration still returns ok=true. Routine
        # iteration outcomes (success / partial) MUST stay silent.
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 5 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Invoke-Sandcastle  -Times 5 -Exactly -Scope It
        Assert-MockCalled Send-TelegramAlert -Times 0 -Exactly -Scope It
    }

    It 'AC: agent-side exit failure (non-infra reason) does NOT fire Telegram' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }
        Mock Invoke-Sandcastle {
            [pscustomobject]@{ ok = $false; exitCode = 7; result = $null; reason = 'exit=7' }
        }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5 } | Should Throw

        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'failure' }
        Assert-MockCalled Send-TelegramAlert -Times 0 -Exactly -Scope It
    }

    It 'AC: no-result-file surfaces as infra-down and fires Telegram' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }
        Mock Invoke-Sandcastle {
            [pscustomobject]@{ ok = $false; exitCode = 0; result = $null; reason = 'no-result-file' }
        }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5 } | Should Throw

        Assert-MockCalled Send-TelegramAlert -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Message -like '*no-result-file*' }
    }

    It 'AC: npm-not-found surfaces as infra-down and fires Telegram' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }
        Mock Invoke-Sandcastle {
            [pscustomobject]@{ ok = $false; exitCode = -1; result = $null; reason = 'npm-not-found' }
        }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5 } | Should Throw

        Assert-MockCalled Send-TelegramAlert -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Message -like '*npm-not-found*' }
    }

    It 'accumulates commits and usage across multiple successful iterations' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 3 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        # 3 iterations × the BeforeEach mock (1k input, 200 output, 1 commit each)
        Assert-MockCalled Invoke-Sandcastle -Times 3 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter {
                $Status -eq 'success' -and
                $Summary -like '*iterations=3*' -and
                $Summary -like '*commits=3*' -and
                $LlmMetrics.input_tokens -eq 3000 -and
                $LlmMetrics.output_tokens -eq 600
            }
    }

    It 'records failure when npm is not on PATH (npm-not-found surfaces through Record)' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }
        Mock Invoke-Sandcastle {
            [pscustomobject]@{ ok = $false; exitCode = -1; result = $null; reason = 'npm-not-found' }
        }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5 } |
            Should Throw 'npm-not-found'

        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'failure' -and $Summary -like '*npm-not-found*' }
    }

    It 'records failure and stops loop when sandcastle invocation returns ok=false' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }
        Mock Invoke-Sandcastle {
            [pscustomobject]@{ ok = $false; exitCode = 0; result = $null; reason = 'no-result-file' }
        }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 3 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5 } |
            Should Throw 'no-result-file'

        Assert-MockCalled Invoke-Sandcastle   -Times 1 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'failure' -and $Summary -like '*no-result-file*' }
    }

    It 'soft-stops mid-run when window expires after iteration N succeeds' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }

        # Window expires partway through. First call → not expired; subsequent
        # calls → expired. With MaxIterations=3 the watchdog should run
        # exactly one iteration then bail with partial:window-expired.
        $script:windowChecks = 0
        Mock Test-WindowExpired {
            $script:windowChecks++
            return ($script:windowChecks -gt 1)
        }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 3 -Model 'm' `
            -WindowEnd '23:59' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Invoke-Sandcastle   -Times 1 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter {
                $Status -eq 'partial' -and
                $Summary -like '*window-expired*' -and
                $Summary -like '*iterations=1*'
            }
    }
}

# ---------------------------------------------------------------------------
# Invoke-Sandcastle internals (#572) -- previously only tested via the daemon
# matrix wholesale-mock. Cover env save/restore, stale-file cleanup,
# json-parse-error, exit-vs-no-result paths directly.
# ---------------------------------------------------------------------------

Describe 'Invoke-Sandcastle' {
    BeforeEach {
        $script:tmpRoot = Join-Path $env:TEMP "sandcastle-inv-$([guid]::NewGuid())"
        New-Item -ItemType Directory -Path $script:tmpRoot | Out-Null
        $script:resultFile = Join-Path $script:tmpRoot 'result.json'
        $script:logFile    = Join-Path $script:tmpRoot 'run.log'
    }
    AfterEach {
        if (Test-Path -LiteralPath $script:tmpRoot) {
            Remove-Item -LiteralPath $script:tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    It 'removes a stale result.json before invoking npm' {
        '{"stale":true}' | Out-File -FilePath $script:resultFile -Encoding utf8
        # npm exits cleanly but writes nothing -> ok=false, reason=no-result-file,
        # AND the stale file must be gone (proving the pre-clean ran).
        Mock Invoke-NpmSandcastle { [pscustomobject]@{ cmdNotFound = $false; exitCode = 0 } }
        $r = Invoke-Sandcastle -RepoRoot $script:tmpRoot -Model 'm' -MaxIterations 1 `
            -ResultFile $script:resultFile -LogFile $script:logFile -RunId 'run1' -TargetIssue ''
        $r.ok     | Should Be $false
        $r.reason | Should Be 'no-result-file'
        Test-Path -LiteralPath $script:resultFile | Should Be $false
    }

    It 'restores env vars after the call (save-and-restore symmetry)' {
        $env:SANDCASTLE_RESULT_FILE      = 'prev-result'
        $env:SANDCASTLE_MAX_ITERATIONS   = 'prev-max'
        $env:SANDCASTLE_RUN_ID           = 'prev-run'
        $env:SANDCASTLE_AGENT_MODEL      = 'prev-model'
        $env:SANDCASTLE_AGENT_BASE_URL   = 'prev-url'
        $env:SANDCASTLE_AGENT_AUTH_TOKEN = 'prev-token'
        $env:SANDCASTLE_TARGET_ISSUE     = 'prev-target'
        $env:OLLAMA_MODEL                = 'prev-ollama'
        Mock Invoke-NpmSandcastle { [pscustomobject]@{ cmdNotFound = $false; exitCode = 0 } }
        Invoke-Sandcastle -RepoRoot $script:tmpRoot -Model 'new-m' -MaxIterations 5 `
            -ResultFile $script:resultFile -LogFile $script:logFile -RunId 'new-run' `
            -BaseUrl 'http://new' -AuthToken 'new-tok' -TargetIssue '42' | Out-Null
        $env:SANDCASTLE_RESULT_FILE      | Should Be 'prev-result'
        $env:SANDCASTLE_MAX_ITERATIONS   | Should Be 'prev-max'
        $env:SANDCASTLE_RUN_ID           | Should Be 'prev-run'
        $env:SANDCASTLE_AGENT_MODEL      | Should Be 'prev-model'
        $env:SANDCASTLE_AGENT_BASE_URL   | Should Be 'prev-url'
        $env:SANDCASTLE_AGENT_AUTH_TOKEN | Should Be 'prev-token'
        $env:SANDCASTLE_TARGET_ISSUE     | Should Be 'prev-target'
        $env:OLLAMA_MODEL                | Should Be 'prev-ollama'
    }

    It 'returns json-parse-error when result.json is malformed' {
        Mock Invoke-NpmSandcastle {
            # Simulate npm writing a bad result.json before exiting 0.
            'not json {' | Out-File -FilePath $script:resultFile -Encoding utf8
            [pscustomobject]@{ cmdNotFound = $false; exitCode = 0 }
        }
        $r = Invoke-Sandcastle -RepoRoot $script:tmpRoot -Model 'm' -MaxIterations 1 `
            -ResultFile $script:resultFile -LogFile $script:logFile -RunId 'run1' -TargetIssue ''
        $r.ok     | Should Be $false
        $r.reason | Should Match '^json-parse-error'
    }

    It 'distinguishes exit!=0 (reason=exit=N) from missing result file (reason=no-result-file)' {
        Mock Invoke-NpmSandcastle { [pscustomobject]@{ cmdNotFound = $false; exitCode = 137 } }
        $r1 = Invoke-Sandcastle -RepoRoot $script:tmpRoot -Model 'm' -MaxIterations 1 `
            -ResultFile $script:resultFile -LogFile $script:logFile -RunId 'r1' -TargetIssue ''
        $r1.ok       | Should Be $false
        $r1.exitCode | Should Be 137
        $r1.reason   | Should Be 'exit=137'

        Mock Invoke-NpmSandcastle { [pscustomobject]@{ cmdNotFound = $false; exitCode = 0 } }
        $r2 = Invoke-Sandcastle -RepoRoot $script:tmpRoot -Model 'm' -MaxIterations 1 `
            -ResultFile $script:resultFile -LogFile $script:logFile -RunId 'r2' -TargetIssue ''
        $r2.ok     | Should Be $false
        $r2.reason | Should Be 'no-result-file'
    }

    It 'returns npm-not-found when npm is absent' {
        Mock Invoke-NpmSandcastle { [pscustomobject]@{ cmdNotFound = $true; exitCode = -1 } }
        $r = Invoke-Sandcastle -RepoRoot $script:tmpRoot -Model 'm' -MaxIterations 1 `
            -ResultFile $script:resultFile -LogFile $script:logFile -RunId 'r' -TargetIssue ''
        $r.ok     | Should Be $false
        $r.reason | Should Be 'npm-not-found'
    }

    It 'returns ok with parsed result on success' {
        Mock Invoke-NpmSandcastle {
            '{"branch":"feat/1-x","commits":[],"iterations":[]}' | Out-File -FilePath $script:resultFile -Encoding utf8
            [pscustomobject]@{ cmdNotFound = $false; exitCode = 0 }
        }
        $r = Invoke-Sandcastle -RepoRoot $script:tmpRoot -Model 'm' -MaxIterations 1 `
            -ResultFile $script:resultFile -LogFile $script:logFile -RunId 'r' -TargetIssue ''
        $r.ok            | Should Be $true
        $r.result.branch | Should Be 'feat/1-x'
    }
}

# ---------------------------------------------------------------------------
# Runtime-dir retention sweep (#572). Default keeps 30 most-recent dirs.
# ---------------------------------------------------------------------------

Describe 'Invoke-RuntimeSweep' {
    BeforeEach {
        $script:rootSweep = Join-Path $env:TEMP "sandcastle-sweep-$([guid]::NewGuid())"
        New-Item -ItemType Directory -Path $script:rootSweep | Out-Null
    }
    AfterEach {
        if (Test-Path -LiteralPath $script:rootSweep) {
            Remove-Item -LiteralPath $script:rootSweep -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    function New-StampDir([string]$Stamp) {
        $d = Join-Path $script:rootSweep $Stamp
        New-Item -ItemType Directory -Path $d | Out-Null
        return $d
    }

    It 'returns empty array when runtime root does not exist' {
        Invoke-RuntimeSweep -RuntimeRoot (Join-Path $script:rootSweep 'nope') -Keep 3 | Should BeNullOrEmpty
    }

    It 'returns empty array when count <= Keep' {
        New-StampDir '20260101-000000' | Out-Null
        New-StampDir '20260102-000000' | Out-Null
        Invoke-RuntimeSweep -RuntimeRoot $script:rootSweep -Keep 5 | Should BeNullOrEmpty
        (Get-ChildItem -LiteralPath $script:rootSweep -Directory).Count | Should Be 2
    }

    It 'prunes oldest dirs and keeps the N most recent (lexicographic by name)' {
        $stamps = @(
            '20260101-000000','20260102-000000','20260103-000000',
            '20260104-000000','20260105-000000'
        )
        foreach ($s in $stamps) { New-StampDir $s | Out-Null }
        $pruned = Invoke-RuntimeSweep -RuntimeRoot $script:rootSweep -Keep 2
        $pruned.Count | Should Be 3
        ($pruned -contains '20260101-000000') | Should Be $true
        ($pruned -contains '20260102-000000') | Should Be $true
        ($pruned -contains '20260103-000000') | Should Be $true
        $kept = Get-ChildItem -LiteralPath $script:rootSweep -Directory | Select-Object -ExpandProperty Name
        ($kept -contains '20260104-000000') | Should Be $true
        ($kept -contains '20260105-000000') | Should Be $true
        $kept.Count | Should Be 2
    }

    It 'disables sweep when Keep is negative' {
        New-StampDir '20260101-000000' | Out-Null
        New-StampDir '20260102-000000' | Out-Null
        Invoke-RuntimeSweep -RuntimeRoot $script:rootSweep -Keep -1 | Should BeNullOrEmpty
        (Get-ChildItem -LiteralPath $script:rootSweep -Directory).Count | Should Be 2
    }
}

# ---------------------------------------------------------------------------
# Write-OutcomeRecord HTTP path (#572). Asserts URL, headers, and body shape
# against a mocked Invoke-RestMethod so endpoint/auth regressions are caught
# in CI rather than at the first AFK run.
# ---------------------------------------------------------------------------

Describe 'Write-OutcomeRecord HTTP path' {
    It 'posts to <SupabaseUrl>/rest/v1/task_outcomes with apikey + Bearer headers and required body keys' {
        $script:captured = $null
        Mock Invoke-RestMethod {
            $script:captured = @{
                Uri     = $Uri
                Method  = $Method
                Headers = $Headers
                Body    = ($Body | ConvertFrom-Json)
            }
            return [pscustomobject]@{ id = 'rec-1' }
        }

        $r = Write-OutcomeRecord -SupabaseUrl 'https://example.supabase.co/' `
            -SupabaseKey 'sk-test' -Repo 'jarvis' -Status 'success' `
            -Summary 'all green' `
            -LlmMetrics @{ input_tokens = 10; output_tokens = 20; model = 'm' } `
            -RunId 'run-xyz'

        Assert-MockCalled Invoke-RestMethod -Times 1 -Exactly -Scope It
        $script:captured.Uri    | Should Be 'https://example.supabase.co/rest/v1/task_outcomes'
        $script:captured.Method | Should Be 'Post'
        $script:captured.Headers['apikey']        | Should Be 'sk-test'
        $script:captured.Headers['Authorization'] | Should Be 'Bearer sk-test'
        $script:captured.Headers['Content-Type']  | Should Be 'application/json'

        $body = $script:captured.Body
        $body.task_type         | Should Be 'autonomous'
        $body.outcome_status    | Should Be 'success'
        $body.project           | Should Be 'jarvis'
        $body.source_provenance | Should Be 'sandcastle:watchdog:run-xyz'
        # pattern_tags must include the baseline sandcastle/afk tags.
        ($body.pattern_tags -contains 'sandcastle') | Should Be $true
        ($body.pattern_tags -contains 'afk')        | Should Be $true
        # lessons carries serialised LLM metrics (JSON string for now, until
        # task_outcomes gains a dedicated llm jsonb column).
        $body.lessons | Should Not BeNullOrEmpty
        $lessons = $body.lessons | ConvertFrom-Json
        $lessons.input_tokens  | Should Be 10
        $lessons.output_tokens | Should Be 20
    }

    It 'short-circuits without calling Invoke-RestMethod when credentials are missing' {
        Mock Invoke-RestMethod { throw 'should not be called' }
        $r = Write-OutcomeRecord -SupabaseUrl '' -SupabaseKey '' -Repo 'jarvis' `
            -Status 'success' -Summary 's' -LlmMetrics @{} -RunId 'r'
        $r | Should BeNullOrEmpty
        Assert-MockCalled Invoke-RestMethod -Times 0 -Exactly -Scope It
    }
}
