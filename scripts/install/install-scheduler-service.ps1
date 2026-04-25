# Install jarvis-scheduler as a Windows service using NSSM
# Supports portable paths from config/device.json or environment variables
# Usage: .\install-scheduler-service.ps1

param(
    [Parameter(HelpMessage = "Skip NSSM check (for automated environments)")]
    [switch]$SkipNssmCheck = $false,

    [Parameter(HelpMessage = "Validate resolution end-to-end without calling nssm install/set")]
    [switch]$DryRun = $false,

    # Workshop incident 2026-04-25 (memory workshop_scheduler_logon_failure_real_cause):
    # sc.exe config and NSSM cannot grant SeServiceLogonRight, so a correct password
    # yields error 1326 when the account lacks the right. services.msc UI auto-grants
    # on password re-entry; this script does the same explicitly via secedit.
    # Format: '.\username' for local accounts, 'DOMAIN\username' for domain.
    [Parameter(HelpMessage = "Run service as this user account; grants SeServiceLogonRight. Pair with -ServicePassword to also set NSSM ObjectName.")]
    [string]$ServiceAccount = "",

    [Parameter(HelpMessage = "Password for ServiceAccount (SecureString). Omit to set password manually after install.")]
    [System.Security.SecureString]$ServicePassword
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

function Grant-SeServiceLogonRight {
    # Idempotent grant of "Log on as a service" via secedit. See issue #410 +
    # memory workshop_scheduler_logon_failure_real_cause.
    param(
        [Parameter(Mandatory = $true)][string]$Account,
        [switch]$DryRun
    )

    $sid = $null
    try {
        $ntAccount = New-Object System.Security.Principal.NTAccount($Account)
        $sid = $ntAccount.Translate([System.Security.Principal.SecurityIdentifier]).Value
    }
    catch {
        Exit-Script 1 "Cannot resolve account '$Account' to SID. Verify spelling and (for local accounts) the '.\' prefix."
    }

    Write-Status "Account $Account resolved to SID $sid" $InfoColor

    $tempInf = [System.IO.Path]::GetTempFileName() + ".inf"
    $tempSdb = [System.IO.Path]::GetTempFileName() + ".sdb"

    if ($DryRun) {
        Write-Status "[DRY-RUN] Would call: secedit /export /cfg $tempInf /areas USER_RIGHTS" $WarningColor
        Write-Status "[DRY-RUN] Would patch SeServiceLogonRight to include *$sid (no-op if already present)" $WarningColor
        Write-Status "[DRY-RUN] Would call: secedit /configure /db $tempSdb /cfg $tempInf /areas USER_RIGHTS" $WarningColor
        return
    }

    & secedit /export /cfg $tempInf /areas USER_RIGHTS | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $tempInf -ErrorAction SilentlyContinue
        Exit-Script $LASTEXITCODE "secedit /export failed (exit $LASTEXITCODE). Script must run elevated."
    }

    $content = Get-Content $tempInf -Encoding Unicode
    $newContent = New-Object System.Collections.Generic.List[string]
    $rightFound = $false
    $alreadyGranted = $false

    foreach ($line in $content) {
        if ($line -match '^\s*SeServiceLogonRight\s*=\s*(.+)$') {
            $rightFound = $true
            $accounts = $Matches[1].Trim()
            if ($accounts -match [regex]::Escape("*$sid")) {
                $alreadyGranted = $true
                $newContent.Add($line) | Out-Null
            }
            else {
                $newContent.Add("SeServiceLogonRight = $accounts,*$sid") | Out-Null
            }
        }
        else {
            $newContent.Add($line) | Out-Null
        }
    }

    if (-not $rightFound) {
        $insertIdx = -1
        for ($i = 0; $i -lt $newContent.Count; $i++) {
            if ($newContent[$i] -match '^\[Privilege Rights\]') {
                $insertIdx = $i + 1
                break
            }
        }
        if ($insertIdx -gt 0) {
            $newContent.Insert($insertIdx, "SeServiceLogonRight = *$sid")
        }
        else {
            $newContent.Add("[Privilege Rights]") | Out-Null
            $newContent.Add("SeServiceLogonRight = *$sid") | Out-Null
        }
    }

    if ($alreadyGranted) {
        Write-Status "SeServiceLogonRight already granted to $Account; no change needed" $SuccessColor
        Remove-Item $tempInf -ErrorAction SilentlyContinue
        return
    }

    Set-Content -Path $tempInf -Value $newContent -Encoding Unicode

    & secedit /configure /db $tempSdb /cfg $tempInf /areas USER_RIGHTS | Out-Null
    $configureExit = $LASTEXITCODE
    Remove-Item $tempInf, $tempSdb -ErrorAction SilentlyContinue

    if ($configureExit -ne 0) {
        Exit-Script $configureExit "secedit /configure failed (exit $configureExit); grant not applied."
    }

    Write-Status "SeServiceLogonRight granted to $Account" $SuccessColor
}

# Resolve repository path and Python interpreter
Write-Status "Reading configuration..." $InfoColor

$repoPath = $null
$pythonPath = $null

# Try config/device.json first.
# Repo root = parent of parent of $PSScriptRoot (script lives at <repo>/scripts/install/).
# Note: Windows PowerShell 5.1's Join-Path takes only -Path and -ChildPath, so multi-segment
# paths must be chained: Join-Path (Join-Path A "config") "device.json".
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$configPath = Join-Path (Join-Path $repoRoot "config") "device.json"
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
        $repoPath = $repoRoot
    }
}

if (-not $pythonPath) {
    $pythonPath = $env:JARVIS_PYTHON
    if (-not $pythonPath) {
        $pythonPath = "python"  # Rely on PATH initially
        Write-Status "JARVIS_PYTHON not set, will resolve 'python' from PATH" $InfoColor
    }
}

# Resolve to absolute path
$repoPath = Resolve-Path $repoPath -ErrorAction Stop | Select-Object -ExpandProperty Path
Write-Status "Repository path: $repoPath" $InfoColor

# Resolve pythonPath to absolute if it's not already
if (-not (Split-Path $pythonPath -IsAbsolute)) {
    try {
        $pythonPath = (Get-Command $pythonPath -ErrorAction Stop).Source
        Write-Status "Python interpreter resolved to: $pythonPath" $SuccessColor
    }
    catch {
        Exit-Script 1 "Cannot resolve Python: '$pythonPath' not found in PATH. Set JARVIS_PYTHON to absolute path."
    }
}
else {
    Write-Status "Python interpreter: $pythonPath" $InfoColor
}

# Verify repo structure
if (-not (Test-Path (Join-Path $repoPath "agents"))) {
    Exit-Script 1 "Repository path does not contain 'agents' directory. Check JARVIS_REPO_PATH or config/device.json"
}

# Check NSSM is installed
Write-Status "Checking for NSSM..." $InfoColor
$nssmPath = $null

# First, honor JARVIS_NSSM_PATH env var if set
if ($env:JARVIS_NSSM_PATH) {
    if (Test-Path $env:JARVIS_NSSM_PATH) {
        $nssmPath = $env:JARVIS_NSSM_PATH
        Write-Status "NSSM found via JARVIS_NSSM_PATH: $nssmPath" $SuccessColor
    }
    else {
        Exit-Script 1 "JARVIS_NSSM_PATH is set but file not found: $env:JARVIS_NSSM_PATH"
    }
}

# Try Get-Command next
if (-not $nssmPath) {
    try {
        $nssmPath = (Get-Command nssm -ErrorAction Stop).Source
        Write-Status "NSSM found in PATH: $nssmPath" $SuccessColor
    }
    catch {
        # Get-Command failed; try auto-discovery in winget package directory
        Write-Status "NSSM not in PATH; searching winget package directory..." $WarningColor
        $nssmPath = $null

        $wingetNssmGlob = Join-Path (Join-Path $env:LOCALAPPDATA "Microsoft") "WinGet"
        $wingetNssmGlob = Join-Path $wingetNssmGlob "Packages"
        $wingetNssmGlob = Join-Path $wingetNssmGlob "NSSM.NSSM_*"

        # Search for both win64 and win32
        $candidates = @(
            @("win64", "nssm.exe"),
            @("win32", "nssm.exe")
        )

        foreach ($subpath in $candidates) {
            $searchPattern = Join-Path (Join-Path $wingetNssmGlob "nssm-*") $subpath[0]
            $found = Get-ChildItem -Path $searchPattern -Name $subpath[1] -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                $nssmPath = Join-Path $searchPattern $subpath[1]
                Write-Status "NSSM auto-discovered in winget: $nssmPath" $SuccessColor
                break
            }
        }

        if (-not $nssmPath) {
            if (-not $SkipNssmCheck) {
                Write-Error-Message "NSSM is not installed or not in PATH"
                Write-Host "`nTo install NSSM:"
                Write-Host "  Option 1 (winget): winget install NSSM.NSSM"
                Write-Host "  Option 2 (download): https://nssm.cc/download"
                Write-Host "`nTo override NSSM path:"
                Write-Host "  `$env:JARVIS_NSSM_PATH = 'C:\path\to\nssm.exe'"
                Exit-Script 1
            }
            else {
                Write-Status "Skipping NSSM check (--SkipNssmCheck set)" $WarningColor
            }
        }
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
$LogDir = Join-Path (Join-Path $repoPath "logs") "scheduler"
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
    if (-not $DryRun) {
        & $nssmPath stop $ServiceName
        if ($LASTEXITCODE -ne 0) {
            Write-Error-Message "Failed to stop service (exit code $LASTEXITCODE)"
        }
        Start-Sleep -Seconds 2
    }
    else {
        Write-Status "[DRY-RUN] Would call: & $nssmPath stop $ServiceName" $WarningColor
    }
}
else {
    Write-Status "Creating new service..." $InfoColor
}

# Install/update service with NSSM
Write-Status "Installing service via NSSM..." $InfoColor

# Helper function to invoke nssm with error checking
function Invoke-Nssm {
    param([string[]]$Arguments)

    if ($DryRun) {
        Write-Status "[DRY-RUN] Would call: & $nssmPath $($Arguments -join ' ')" $WarningColor
        return
    }

    $output = & $nssmPath @Arguments 2>&1
    Write-Host $output

    if ($LASTEXITCODE -ne 0) {
        Exit-Script $LASTEXITCODE "nssm command failed (exit code $LASTEXITCODE): $($Arguments -join ' ')"
    }
}

# Install or update
Write-Status "Configuring service..." $InfoColor
Invoke-Nssm "install", $ServiceName, "$pythonPath", "-m agents.scheduler"

# Set working directory
Invoke-Nssm "set", $ServiceName, "AppDirectory", "$repoPath"

# Set log files
Invoke-Nssm "set", $ServiceName, "AppStdout", "$StdoutLog"
Invoke-Nssm "set", $ServiceName, "AppStderr", "$StderrLog"

# Set startup type to Automatic
Invoke-Nssm "set", $ServiceName, "Start", "SERVICE_AUTO_START"

# Configure restart on failure
Invoke-Nssm "set", $ServiceName, "AppExit", "Default", "Restart"
Invoke-Nssm "set", $ServiceName, "AppRestartDelay", "5000"

# Set service description
Invoke-Nssm "set", $ServiceName, "Description", "$ServiceDescription"
Invoke-Nssm "set", $ServiceName, "DisplayName", "$ServiceDisplayName"

# Service account configuration (issue #410)
if ($ServiceAccount) {
    Write-Status "`nConfiguring service account: $ServiceAccount" $InfoColor
    Grant-SeServiceLogonRight -Account $ServiceAccount -DryRun:$DryRun

    if ($ServicePassword) {
        $plainPassword = [System.Net.NetworkCredential]::new("", $ServicePassword).Password
        if ($DryRun) {
            Write-Status "[DRY-RUN] Would call: & $nssmPath set $ServiceName ObjectName $ServiceAccount <password>" $WarningColor
        }
        else {
            Invoke-Nssm "set", $ServiceName, "ObjectName", $ServiceAccount, $plainPassword
            Write-Status "NSSM ObjectName set to $ServiceAccount" $SuccessColor
        }
        # Scrub plaintext from this scope; GC will reclaim later.
        $plainPassword = $null
    }
    else {
        Write-Status "ServicePassword not supplied. Set the password manually before starting:" $WarningColor
        Write-Host "  sc.exe config $ServiceName obj=`"$ServiceAccount`" password=<password>"
        Write-Host "  OR services.msc -> $ServiceName -> Properties -> Log On -> Set password"
    }
}

if ($DryRun) {
    Write-Status "`n[DRY-RUN] All validations passed. Actual service installation would proceed." $SuccessColor
}
else {
    Write-Status "Service configured successfully" $SuccessColor
}

# Display service status (only in actual run, not dry-run)
if (-not $DryRun) {
    Write-Status "`nFinal service configuration:" $InfoColor
    Get-Service -Name $ServiceName | Format-List DisplayName, Name, Status, StartType

    Write-Status "`nService installation complete!" $SuccessColor
    Write-Host "`nTo start the service:"
    Write-Host "  Start-Service -Name '$ServiceName'"
    Write-Host "`nTo view logs:"
    Write-Host "  Get-Content '$StdoutLog' -Tail 50 -Wait"
    Write-Host "`nTo uninstall:"
    Write-Host "  & '$PSScriptRoot\uninstall-scheduler-service.ps1'"
}
else {
    Write-Status "`n[DRY-RUN] Script completed. All validations passed." $SuccessColor
}
