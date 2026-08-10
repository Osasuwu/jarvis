# Pester tests for scripts/install/register-wake-driver.ps1 (issue #1384).
# Exercises the -Command argument assembly, in particular the nested-quote
# escaping around $PythonExe (this logic already broke once during #1384's
# own development -- a double-quote-inside-double-quote bug that corrupted
# Windows argv parsing, fixed before this test existed). No real Task
# Scheduler calls -- covered by -NoExecute.
#
# Compatible with Pester 3.4 (built-in on Windows PowerShell 5.1).
#
# Run:
#   Invoke-Pester -Path tests/install/Register-WakeDriver.Tests.ps1

$script:TaskPath = Join-Path $PSScriptRoot '..\..\scripts\install\register-wake-driver.ps1'
# -NoExecute short-circuits before the device guard or any scheduler call --
# no parameters are mandatory in this script's default parameter set, so
# dot-sourcing needs nothing else supplied at load time.
. $script:TaskPath -NoExecute

# ---------------------------------------------------------------------------
# PowerShell executable resolution
# ---------------------------------------------------------------------------

Describe 'Get-PowerShellExe' {
    It 'prefers pwsh over powershell.exe when pwsh is available' {
        Mock Get-Command {
            if ($Name -eq 'pwsh') { return [pscustomobject]@{ Source = 'C:\Program Files\PowerShell\7\pwsh.exe' } }
            throw "unexpected Get-Command for '$Name'"
        }
        $exe = Get-PowerShellExe
        $exe | Should Be 'C:\Program Files\PowerShell\7\pwsh.exe'
    }

    It 'falls back to powershell.exe when pwsh is absent' {
        Mock Get-Command {
            if ($Name -eq 'pwsh') { return $null }
            if ($Name -eq 'powershell') { return [pscustomobject]@{ Source = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' } }
            throw "unexpected Get-Command for '$Name'"
        }
        $exe = Get-PowerShellExe
        $exe | Should Be 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    }

    It 'throws when both pwsh and powershell.exe are absent' {
        Mock Get-Command {
            if ($Name -eq 'pwsh') { return $null }
            if ($Name -eq 'powershell') { throw 'powershell not found' }
            throw "unexpected Get-Command for '$Name'"
        }
        { Get-PowerShellExe } | Should Throw
    }
}

# ---------------------------------------------------------------------------
# -Command argument assembly -- the nested-quote escaping regression
# ---------------------------------------------------------------------------

Describe 'Format-WakeDriverActionArgs' {
    It 'builds the expected -NoProfile / -ExecutionPolicy / -Command shape' {
        $args = Format-WakeDriverActionArgs -PythonExe 'C:\Python311\python.exe' -WatchdogSeconds 300
        $args[0] | Should Be '-NoProfile'
        $args[1] | Should Be '-ExecutionPolicy'
        $args[2] | Should Be 'Bypass'
        $args[3] | Should Be '-Command'
        $args.Count | Should Be 5
    }

    It 'sets JARVIS_PRINCIPAL=autonomous in the inner command' {
        $args = Format-WakeDriverActionArgs -PythonExe 'C:\Python311\python.exe' -WatchdogSeconds 300
        $args[4] | Should Match ([regex]::Escape("`$env:JARVIS_PRINCIPAL = 'autonomous'"))
    }

    It 'sets REACTIVE_CONCURRENCY_CAP=2 in the inner command (#1390 AC8)' {
        $args = Format-WakeDriverActionArgs -PythonExe 'C:\Python311\python.exe' -WatchdogSeconds 300
        $args[4] | Should Match ([regex]::Escape("`$env:REACTIVE_CONCURRENCY_CAP = '2'"))
    }

    It 'passes --watchdog-seconds through unchanged' {
        $args = Format-WakeDriverActionArgs -PythonExe 'C:\Python311\python.exe' -WatchdogSeconds 120
        $args[4] | Should Match '--watchdog-seconds 120'
    }

    It 'wraps the -Command payload in a single outer double-quoted string (no nested double quotes)' {
        $args = Format-WakeDriverActionArgs -PythonExe 'C:\Python311\python.exe' -WatchdogSeconds 300
        $payload = $args[4]
        $payload.Substring(0, 1)  | Should Be '"'
        $payload.Substring($payload.Length - 1, 1) | Should Be '"'
        # Only the two wrapping quotes are double quotes -- the inner python
        # path must be single-quoted, or Windows argv parsing breaks on the
        # nested-double-quote bug this test guards against.
        $inner = $payload.Substring(1, $payload.Length - 2)
        ($inner -like '*"*') | Should Be $false
    }

    It 'doubles an embedded single quote in the python path so the string cannot break out' {
        $args = Format-WakeDriverActionArgs -PythonExe "C:\Users\o'brien\python.exe" -WatchdogSeconds 300
        $args[4] | Should Match ([regex]::Escape("o''brien"))
    }

    It 'single-quotes the python invocation, not double-quotes' {
        $args = Format-WakeDriverActionArgs -PythonExe 'C:\Python311\python.exe' -WatchdogSeconds 300
        $args[4] | Should Match ([regex]::Escape("& 'C:\Python311\python.exe'"))
    }
}

# ---------------------------------------------------------------------------
# Python interpreter resolution + validation (#1495) -- the PATH default used
# to resolve to the Microsoft Store app-execution-alias python3 stub (exit
# 9009), registering a task that died instantly at every start.
# ---------------------------------------------------------------------------

Describe 'Resolve-WakeDriverPython' {
    It 'returns an explicit -PythonExe unchanged' {
        $exe = Resolve-WakeDriverPython -PythonExe 'C:\custom\python.exe' -RepoRoot 'C:\repo'
        $exe | Should Be 'C:\custom\python.exe'
    }

    It 'prefers <RepoRoot>\.venv\Scripts\python.exe when it exists' {
        Mock Test-Path { return $true }
        $exe = Resolve-WakeDriverPython -RepoRoot 'C:\repo'
        $exe | Should Be 'C:\repo\.venv\Scripts\python.exe'
    }

    It 'falls back to python3 on PATH when the venv is absent' {
        Mock Test-Path { return $false }
        Mock Get-Command {
            if ($Name -eq 'python3') { return [pscustomobject]@{ Source = 'C:\tools\python3.exe' } }
            throw "unexpected Get-Command for '$Name'"
        }
        $exe = Resolve-WakeDriverPython -RepoRoot 'C:\repo'
        $exe | Should Be 'C:\tools\python3.exe'
    }

    It 'falls back python3 -> python when python3 is absent from PATH' {
        Mock Test-Path { return $false }
        Mock Get-Command {
            if ($Name -eq 'python3') { return $null }
            if ($Name -eq 'python') { return [pscustomobject]@{ Source = 'C:\Python311\python.exe' } }
            throw "unexpected Get-Command for '$Name'"
        }
        $exe = Resolve-WakeDriverPython -RepoRoot 'C:\repo'
        $exe | Should Be 'C:\Python311\python.exe'
    }
}

Describe 'Assert-WakeDriverPython' {
    It 'passes when the interpreter answers --version with exit 0' {
        Mock Start-Process { return [pscustomobject]@{ ExitCode = 0 } }
        { Assert-WakeDriverPython -PythonExe 'C:\Python311\python.exe' } | Should Not Throw
    }

    It 'throws on the Microsoft Store stub (exit 9009), naming the resolved path' {
        Mock Start-Process { return [pscustomobject]@{ ExitCode = 9009 } }
        { Assert-WakeDriverPython -PythonExe 'C:\WindowsApps\python3.exe' } | Should Throw 'C:\WindowsApps\python3.exe'
    }

    It 'throws when the interpreter cannot be launched at all' {
        Mock Start-Process { throw 'The system cannot find the file specified' }
        { Assert-WakeDriverPython -PythonExe 'C:\missing\python.exe' } | Should Throw 'could not be executed'
    }
}

# ---------------------------------------------------------------------------
# Repetition watchdog graft (#1479 AC2) -- AtLogOn has no -RepetitionInterval
# parameter set, so the fix builds a throwaway -Once trigger for its
# well-formed Repetition CIM instance and grafts it onto the logon trigger.
# ---------------------------------------------------------------------------

Describe 'Set-WakeDriverRepetition' {
    It 'grafts the requested interval onto the trigger (PT5M)' {
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $result = Set-WakeDriverRepetition -Trigger $trigger -RepetitionInterval (New-TimeSpan -Minutes 5)
        $result.Repetition.Interval | Should Be 'PT5M'
    }

    It 'leaves the repetition duration unset so the pattern repeats indefinitely (#1479: MaxValue is rejected at registration, 0x80041318)' {
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $result = Set-WakeDriverRepetition -Trigger $trigger -RepetitionInterval (New-TimeSpan -Minutes 5)
        [string]::IsNullOrEmpty($result.Repetition.Duration) | Should Be $true
    }

    It 'preserves the AtLogOn trigger type -- only Repetition is grafted on' {
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $result = Set-WakeDriverRepetition -Trigger $trigger -RepetitionInterval (New-TimeSpan -Minutes 5)
        $result.CimClass.CimClassName | Should Be 'MSFT_TaskLogonTrigger'
    }
}

# ---------------------------------------------------------------------------
# NoExecute guard: loading the script without executing the main body
# ---------------------------------------------------------------------------

Describe 'NoExecute guard' {
    It 'loads functions without executing main body (no device guard, no Task Scheduler call)' {
        Get-PowerShellExe -ErrorAction SilentlyContinue | Out-Null
        Format-WakeDriverActionArgs -PythonExe 'p' -WatchdogSeconds 1 -ErrorAction SilentlyContinue | Out-Null
        # If we get here without errors (or a device-guard throw), the
        # -NoExecute short-circuit worked.
        $true | Should Be $true
    }
}
