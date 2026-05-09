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

    It 'returns empty hashtable for missing file' {
        $vars = Read-DotEnvFile -Path "$env:TEMP\does-not-exist-$([guid]::NewGuid()).env"
        $vars.Count | Should Be 0
    }

    Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
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
        Mock Read-DotEnvFile { @{ SUPABASE_URL = 'https://x'; SUPABASE_KEY = 'k' } }
    }

    It 'records success when both daemons are up' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'qwen2.5-coder:14b' `
            -WindowEnd '' -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Start-DockerDesktop -Times 0 -Exactly -Scope It
        Assert-MockCalled Start-OllamaServer  -Times 0 -Exactly -Scope It
        Assert-MockCalled Invoke-Sandcastle   -Times 1 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'success' }
    }

    It 'records failure: docker-down when Docker never starts' {
        Mock Test-DockerRunning { $false }
        Mock Test-OllamaRunning { $true }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 1 -OllamaTimeoutSec 1 } | Should Throw 'docker-down'

        Assert-MockCalled Start-DockerDesktop -Times 1 -Exactly -Scope It
        Assert-MockCalled Invoke-Sandcastle   -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'failure' -and $Summary -like '*docker-down*' }
    }

    It 'records failure: ollama-down when Ollama never starts' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $false }

        { Invoke-Watchdog -Repo 'jarvis' -MaxIterations 1 -Model 'm' `
            -WindowEnd '' -DockerTimeoutSec 1 -OllamaTimeoutSec 1 } | Should Throw 'ollama-down'

        Assert-MockCalled Start-OllamaServer  -Times 1 -Exactly -Scope It
        Assert-MockCalled Invoke-Sandcastle   -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'failure' -and $Summary -like '*ollama-down*' }
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

    It 'soft-stops with partial:window-expired before iteration starts' {
        Mock Test-DockerRunning { $true }
        Mock Test-OllamaRunning { $true }

        Invoke-Watchdog -Repo 'jarvis' -MaxIterations 3 -Model 'm' `
            -WindowEnd ((Get-Date).AddMinutes(-1).ToString('s')) `
            -DockerTimeoutSec 5 -OllamaTimeoutSec 5

        Assert-MockCalled Invoke-Sandcastle   -Times 0 -Exactly -Scope It
        Assert-MockCalled Write-OutcomeRecord -Times 1 -Exactly -Scope It `
            -ParameterFilter { $Status -eq 'partial' -and $Summary -like '*window-expired*' }
    }
}
