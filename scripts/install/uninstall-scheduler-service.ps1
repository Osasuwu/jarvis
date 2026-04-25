# Uninstall jarvis-scheduler Windows service
# Gracefully stops and removes the service
# Usage: .\uninstall-scheduler-service.ps1

param(
    [Parameter(HelpMessage = "Skip confirmation prompt")]
    [switch]$Force = $false
)

# Colors for output
$ErrorColor = "Red"
$SuccessColor = "Green"
$InfoColor = "Cyan"
$WarningColor = "Yellow"

function Write-Status {
    param(
        [string]$Message,
        [string]$Color = $InfoColor
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Error-Message {
    param([string]$Message)
    Write-Host "ERROR: $Message" -ForegroundColor $ErrorColor
}

function Exit-Script {
    param([int]$ExitCode = 1, [string]$Message = "")
    if ($Message) { Write-Error-Message $Message }
    exit $ExitCode
}

$ServiceName = "jarvis-scheduler"

Write-Status "Jarvis Scheduler Uninstall" $InfoColor

# Check if service exists
$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Status "Service '$ServiceName' does not exist." $WarningColor
    exit 0
}

Write-Status "Found service: $($service.DisplayName)" $InfoColor
Write-Status "Current status: $($service.Status)" $InfoColor

# Confirm before uninstall
if (-not $Force) {
    Write-Host "`nThis will stop and remove the service. Continue? [y/N] " -NoNewline
    $confirm = Read-Host
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Status "Cancelled." $WarningColor
        exit 0
    }
}

# Stop the service
if ($service.Status -eq "Running") {
    Write-Status "Stopping service..." $InfoColor
    try {
        Stop-Service -Name $ServiceName -Force
        Start-Sleep -Seconds 2
        Write-Status "Service stopped" $SuccessColor
    }
    catch {
        Write-Error-Message "Failed to stop service: $_"
    }
}

# Remove the service via NSSM
Write-Status "Removing service via NSSM..." $InfoColor
try {
    nssm remove $ServiceName confirm 2>&1 | Out-Null
    Write-Status "Service removed successfully" $SuccessColor
}
catch {
    Exit-Script 1 "Failed to remove service: $_"
}

Write-Status "`nUninstall complete!" $SuccessColor
