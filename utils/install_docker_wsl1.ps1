# PowerShell script to install WSL1, Ubuntu 22.04, and Docker Toolbox
# Downloads using Start-BitsTransfer
# Works on systems WITHOUT VirtualMachinePlatform (WSL1 only)

# ------------------------------
# Check for Administrator
# ------------------------------
If (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole] "Administrator")) {
    Write-Host "Please run this script as Administrator!" -ForegroundColor Red
    Pause
    Exit
}

# ------------------------------
# Variables
# ------------------------------
$dockerToolboxUrl = "https://github.com/docker/toolbox/releases/download/v19.03.1/DockerToolbox-19.03.1.exe"
$dockerToolboxPath = "$env:TEMP\DockerToolboxInstaller.exe"
$ubuntuUrl = "https://aka.ms/wslubuntu2204"
$ubuntuPath = "$env:TEMP\Ubuntu2204.appx"
$wslDistro = "Ubuntu-22.04"

Write-Host "=== WSL1 + Ubuntu + Docker Toolbox Installer ===" -ForegroundColor Cyan
Write-Host ""

# ------------------------------
# ENABLE ONLY WSL (NO VM PLATFORM)
# ------------------------------
$wslFeature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux

if ($wslFeature.State -ne "Enabled") {
    Write-Host "[1/5] Enabling WSL1 feature..." -ForegroundColor Yellow
    Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -All -NoRestart
    Write-Host "`n⚠️ A restart is required." -ForegroundColor Magenta

    $choice = Read-Host "Restart now? (Y/N)"
    if ($choice -match "^[Yy]$") {
        Restart-Computer -Force
    }
    Exit
}

# ------------------------------
# SKIP: WSL2 KERNEL + SKIP VIRTUAL MACHINE PLATFORM
# ------------------------------
Write-Host "[2/5] WSL2 components will NOT be installed (WSL1 mode)." -ForegroundColor Yellow

# ------------------------------
# Install Ubuntu 22.04 (WSL1)
# ------------------------------
Write-Host "[3/5] Installing Ubuntu 22.04 (WSL1)..." -ForegroundColor Yellow

$wslList = wsl --list --quiet

if ($wslList -contains $wslDistro) {
    Write-Host "  Ubuntu 22.04 already installed."
} else {
    Write-Host "  Downloading Ubuntu..."
    try {
        Invoke-WebRequest -Uri $ubuntuUrl -OutFile $ubuntuPath -ErrorAction Stop
    } catch {
        Write-Host "  Failed, trying BITS transfer..."
        Start-BitsTransfer -Source $ubuntuUrl -Destination $ubuntuPath -ErrorAction Stop
    }

    Write-Host "  Installing Ubuntu..."
    Add-AppxPackage -Path $ubuntuPath
    Remove-Item $ubuntuPath -Force -ErrorAction SilentlyContinue

    Write-Host "  ⚠️ Open Ubuntu from Start Menu to create your user."
    Read-Host "Press Enter once done"
}

# Force distro to run under WSL1
Write-Host "  Ensuring Ubuntu is set to WSL1..."
wsl --set-version $wslDistro 1

# ------------------------------
# Install Docker Toolbox (works without Hyper-V/WSL2)
# ------------------------------
Write-Host "[4/5] Installing Docker Toolbox (Legacy)..." -ForegroundColor Yellow

if (!(Test-Path $dockerToolboxPath)) {
    Write-Host "  Downloading Docker Toolbox..."
    try {
        Invoke-WebRequest -Uri $dockerToolboxUrl -OutFile $dockerToolboxPath
    } catch {
        Write-Host "  Trying BITS..."
        Start-BitsTransfer -Source $dockerToolboxUrl -Destination $dockerToolboxPath -ErrorAction Stop
    }
}

Write-Host "  Installing Docker Toolbox..."
Start-Process $dockerToolboxPath -ArgumentList "/SILENT" -Wait

# ------------------------------
# Done
# ------------------------------
Write-Host "`n=============================================" -ForegroundColor Green
Write-Host "   ✅ INSTALLATION COMPLETE (WSL1 MODE)       " -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green

Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Start 'Docker Quickstart Terminal' (creates a VM using VirtualBox)"
Write-Host "2. Run: docker run hello-world"
Write-Host "3. Use Ubuntu normally under WSL1 (`wsl`)."
Pause
