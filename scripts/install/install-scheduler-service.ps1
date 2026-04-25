# Install jarvis-scheduler as a Windows service using NSSM
# Supports portable paths from config/device.json or environment variables
# Usage: .\install-scheduler-service.ps1

param(
    [Parameter(HelpMessage = "Skip NSSM check (for automated environments)")]
    [switch]$SkipNssmCheck = $false
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

# Resolve repository path and Python interpreter
Write-Status "Reading configuration..." $InfoColor

$repoPath = $null
$pythonPath = $null

# Try config/device.json first
$configPath = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))) "config" "device.json"
if (Test-Path $configPath) {
    try {
        $config = Get-Content $configPath | ConvertFrom-Json
        $repoPath = $config.repos_path
        if ($repoPath) {
            # Append "\jarvis" if repos_path is a parent directory
            if (-not (Test-Path (Join-Path $repoPath "agents"))) {
                $repoPath = Join-Path $repoPath "jarvis"
            }
        }
        Write-Status "Loaded config from $configPath" $InfoColor
    }
    catch {
        Write-Status "Failed to parse config: $_. Using environment variables." $WarningColor
    }
}

# Fall back to environment variables
if (-not $repoPath) {
    $repoPath = $env:JARVIS_REPO_PATH
    if (-not $repoPath) {
        Write-Status "config/device.json not found and JARVIS_REPO_PATH not set. Assuming current script directory." $WarningColor
        $repoPath = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
    }
}

if (-not $pythonPath) {
    $pythonPath = $env:JARVIS_PYTHON
    if (-not $pythonPath) {
        $pythonPath = "python"  # Rely on PATH
        Write-Status "JARVIS_PYTHON not set, using 'python' from PATH" $InfoColor
    }
}

# Resolve to absolute path
$repoPath = Resolve-Path $repoPath -ErrorAction Stop | Select-Object -ExpandProperty Path
Write-Status "Repository path: $repoPath" $InfoColor
Write-Status "Python interpreter: $pythonPath" $InfoColor

# Verify repo structure
if (-not (Test-Path (Join-Path $repoPath "agents"))) {
    Exit-Script 1 "Repository path does not contain 'agents' directory. Check JARVIS_REPO_PATH or config/device.json"
}

# Check NSSM is installed
Write-Status "Checking for NSSM..." $InfoColor
$nssmPath = $null
try {
    $nssmPath = (Get-Command nssm -ErrorAction Stop).Source
    Write-Status "NSSM found at: $nssmPath" $SuccessColor
}
catch {
    if (-not $SkipNssmCheck) {
        Write-Error-Message "NSSM is not installed or not in PATH"
        Write-Host "`nTo install NSSM:"
        Write-Host "  Option 1 (winget): winget install NSSM.NSSM"
        Write-Host "  Option 2 (download): https://nssm.cc/download"
        Exit-Script 1
    }
    else {
        Write-Status "Skipping NSSM check (--SkipNssmCheck set)" $WarningColor
    }
}

# Verify Python installation
Write-Status "Checking Python installation..." $InfoColor
try {
    $pythonVer = & $pythonPath --version 2>&1
    Write-Status "Python: $pythonVer" $SuccessColor
}
catch {
    Exit-Script 1 "Python interpreter not found at: $pythonPath"
}

# Prepare service configuration
$ServiceName = "jarvis-scheduler"
$ServiceDisplayName = "Jarvis Scheduler"
$ServiceDescription = "Persistent task dispatcher via APScheduler (Jarvis issue #368)"
$LogDir = Join-Path $repoPath "logs" "scheduler"
$StdoutLog = Join-Path $LogDir "stdout.log"
$StderrLog = Join-Path $LogDir "stderr.log"

Write-Status "Service name: $ServiceName" $InfoColor
Write-Status "Log directory: $LogDir" $InfoColor

# Create log directory
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Status "Created log directory" $SuccessColor
}

# Check if service already exists
Write-Status "Checking for existing service..." $InfoColor
$serviceExists = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($serviceExists) {
    Write-Status "Service '$ServiceName' already exists. Stopping and updating..." $WarningColor
    nssm stop $ServiceName 2>&1 | Out-Null
    Start-Sleep -Seconds 2
}
else {
    Write-Status "Creating new service..." $InfoColor
}

# Install/update service with NSSM
Write-Status "Installing service via NSSM..." $InfoColor

try {
    # Install or update
    nssm install $ServiceName "$pythonPath" "-m agents.scheduler" 2>&1 | Out-Null

    # Set working directory
    nssm set $ServiceName AppDirectory "$repoPath" 2>&1 | Out-Null

    # Set log files
    nssm set $ServiceName AppStdout "$StdoutLog" 2>&1 | Out-Null
    nssm set $ServiceName AppStderr "$StderrLog" 2>&1 | Out-Null

    # Set startup type to Automatic
    nssm set $ServiceName Start SERVICE_AUTO_START 2>&1 | Out-Null

    # Configure restart on failure
    nssm set $ServiceName AppExit Default Restart 2>&1 | Out-Null
    nssm set $ServiceName AppRestartDelay 5000 2>&1 | Out-Null

    # Set service description
    nssm set $ServiceName Description "$ServiceDescription" 2>&1 | Out-Null
    nssm set $ServiceName DisplayName "$ServiceDisplayName" 2>&1 | Out-Null

    Write-Status "Service configured successfully" $SuccessColor
}
catch {
    Exit-Script 1 "Failed to configure service: $_"
}

# Display service status
Write-Status "`nFinal service configuration:" $InfoColor
& Get-Service -Name $ServiceName | Format-List DisplayName, Name, Status, StartType

Write-Status "`nService installation complete!" $SuccessColor
Write-Host "`nTo start the service:"
Write-Host "  Start-Service -Name '$ServiceName'"
Write-Host "`nTo view logs:"
Write-Host "  Get-Content '$StdoutLog' -Tail 50 -Wait"
Write-Host "`nTo uninstall:"
Write-Host "  & '$PSScriptRoot\uninstall-scheduler-service.ps1'"
