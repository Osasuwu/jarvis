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
