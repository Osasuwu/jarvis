# Jarvis installer — Windows wrapper (PowerShell 5.1+).
# Forwards to scripts/install/installer.py. Default is dry-run.
#
# Examples:
#   .\install.ps1                      # dry-run plan
#   .\install.ps1 -Apply               # perform install
#   .\install.ps1 -Rollback <path>     # restore from backup
#
# Epic #335 / M1 #336.

[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$Target,
    [string]$Manifest,
    [string]$Rollback,
    [switch]$SkipEnv,
    [switch]$SkipHealthCheck
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$pyArgs = @("$repoRoot\scripts\install\installer.py")
if ($Apply)            { $pyArgs += "--apply" }
if ($SkipEnv)          { $pyArgs += "--skip-env" }
if ($SkipHealthCheck)  { $pyArgs += "--skip-health-check" }
if ($Target)           { $pyArgs += @("--target", $Target) }
if ($Manifest)         { $pyArgs += @("--manifest", $Manifest) }
if ($Rollback)         { $pyArgs += @("--rollback", $Rollback) }

$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { $py = Get-Command python3 -ErrorAction Stop }

& $py.Source @pyArgs
exit $LASTEXITCODE
