# PowerShell script to install WSL2, Ubuntu 22.04, and Docker Desktop
# Downloads using Start-BitsTransfer for reliability
# Requires administrator privileges
# 
# ⚠️ If this script is executed inside a virtual machine, nested virtualization must be enabled 
# and the hypervisor must support Hyper-V; otherwise WSL2 and Docker Desktop will not work."
#

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
$dockerInstallerUrl = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
$dockerInstallerPath = "$env:TEMP\DockerDesktopInstaller.exe"
$wslKernelUrl = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
$wslKernelPath = "$env:TEMP\wsl_update_x64.msi"
$wslDistro = "Ubuntu-22.04"

Write-Host "=== Docker + WSL2 Installation Script ===" -ForegroundColor Cyan
Write-Host "This script will install WSL2, Ubuntu 22.04, and Docker Desktop"
Write-Host ""

# ------------------------------
# Enable WSL and Virtual Machine Platform
# ------------------------------
$wslFeature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
$vmFeature = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform

$needsReboot = $false

if ($wslFeature.State -ne "Enabled") {
    Write-Host "[1/6] Enabling WSL feature..." -ForegroundColor Yellow
    Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -All -NoRestart
    $needsReboot = $true
}

if ($vmFeature.State -ne "Enabled") {
    Write-Host "[2/6] Enabling Virtual Machine Platform..." -ForegroundColor Yellow
    Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -All -NoRestart
    $needsReboot = $true
}

if ($needsReboot) {
    Write-Host "`n⚠️ A system restart is required." -ForegroundColor Magenta
    Write-Host "After restart, please run this script again to continue."
    
    $choice = Read-Host "Restart now? (Y/N)"
    if ($choice -eq 'Y' -or $choice -eq 'y') {
        Restart-Computer -Force
    }
    Exit
}

# ------------------------------
# Download and install WSL2 Linux kernel
# ------------------------------
Write-Host "[3/6] Installing WSL2 Linux kernel..." -ForegroundColor Yellow

if (!(Test-Path $wslKernelPath)) {
    Write-Host "  Downloading WSL2 kernel..."
    try {
        Invoke-WebRequest -Uri $wslKernelUrl -OutFile $wslKernelPath
    } catch {
        Write-Host "  Failed to download, trying alternative method..." -ForegroundColor Yellow
        Start-BitsTransfer -Source $wslKernelUrl -Destination $wslKernelPath -ErrorAction Stop
    }
}

Write-Host "  Installing kernel update..."
Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$wslKernelPath`" /quiet /norestart" -Wait -NoNewWindow
Remove-Item $wslKernelPath -Force -ErrorAction SilentlyContinue

# ------------------------------
# Set WSL2 as default and install Ubuntu
# ------------------------------
Write-Host "[4/6] Configuring WSL2 and Ubuntu..." -ForegroundColor Yellow

Write-Host "  Setting WSL2 as default..."
wsl --set-default-version 2

# Check if Ubuntu is already installed
$wslList = wsl --list --quiet
if ($wslList -contains $wslDistro) {
    Write-Host "  Ubuntu 22.04 is already installed."
    
    # Ensure it's using WSL2
    $distroInfo = wsl --list --verbose | Select-String $wslDistro
    if ($distroInfo -notmatch "2$") {
        Write-Host "  Converting to WSL2..."
        wsl --set-version $wslDistro 2
    }
} else {
    Write-Host "  Installing Ubuntu 22.04..."
    
    # Download and install Ubuntu
    $ubuntuUrl = "https://aka.ms/wslubuntu2204"
    $ubuntuPath = "$env:TEMP\Ubuntu2204.appx"
    
    Write-Host "  Downloading Ubuntu..."
    Invoke-WebRequest -Uri $ubuntuUrl -OutFile $ubuntuPath
    
    Write-Host "  Installing Ubuntu..."
    Add-AppxPackage -Path $ubuntuPath
    
    Remove-Item $ubuntuPath -Force -ErrorAction SilentlyContinue
    
    Write-Host "  ⚠️  IMPORTANT: After installation completes," -ForegroundColor Magenta
    Write-Host "  launch Ubuntu from Start Menu to create your user account."
    Write-Host "  Then return to this script."
    
    $continue = Read-Host "Press Enter after creating Ubuntu user account"
}

# ------------------------------
# Download Docker Desktop
# ------------------------------
Write-Host "[5/6] Installing Docker Desktop..." -ForegroundColor Yellow

if (!(Test-Path $dockerInstallerPath)) {
    Write-Host "  Downloading Docker Desktop..."
    try {
        Invoke-WebRequest -Uri $dockerInstallerUrl -OutFile $dockerInstallerPath
    } catch {
        Write-Host "  Failed to download, trying alternative method..." -ForegroundColor Yellow
        Start-BitsTransfer -Source $dockerInstallerUrl -Destination $dockerInstallerPath -ErrorAction Stop
    }
}

# Check if Docker is already installed
$dockerRegPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop"
if (Test-Path $dockerRegPath) {
    Write-Host "  Docker Desktop is already installed."
} else {
    Write-Host "  Installing Docker Desktop (this may take a few minutes)..."
    
    # Docker Desktop silent install with required flags
    $installArgs = @(
        "install",
        "--quiet",
        "--accept-license",
        "--no-windows-containers"
    )
    
    $process = Start-Process -FilePath $dockerInstallerPath -ArgumentList $installArgs -PassThru -Wait
    if ($process.ExitCode -ne 0) {
        Write-Host "  ❌ Docker installation failed with exit code: $($process.ExitCode)" -ForegroundColor Red
        Write-Host "  You may need to install Docker Desktop manually from docker.com"
    } else {
        Write-Host "  ✅ Docker Desktop installed successfully."
    }
}

# ------------------------------
# Post-installation configuration
# ------------------------------
Write-Host "[6/6] Finalizing setup..." -ForegroundColor Yellow

# Restart WSL to ensure clean state
Write-Host "  Restarting WSL..."
wsl --shutdown
Start-Sleep -Seconds 3

# Configure Docker to use WSL2 backend
$dockerSettingsPath = "$env:APPDATA\Docker\settings.json"
if (Test-Path $dockerSettingsPath) {
    $settings = Get-Content $dockerSettingsPath | ConvertFrom-Json
    $settings.wslEngineEnabled = $true
    $settings | ConvertTo-Json -Depth 10 | Set-Content $dockerSettingsPath
}

# ------------------------------
# Completion message
# ------------------------------
Write-Host "`n" + ("="*60) -ForegroundColor Green
Write-Host "✅ INSTALLATION COMPLETE!" -ForegroundColor Green
Write-Host "="*60 -ForegroundColor Green

Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Launch 'Docker Desktop' from the Start Menu"
Write-Host "2. Accept the terms of service when prompted"
Write-Host "3. Go to Settings > Resources > WSL Integration"
Write-Host "4. Enable integration with your Ubuntu distro"
Write-Host "5. Open Ubuntu and run: docker run hello-world"
Write-Host "`nNote: You may need to log out and back in for PATH changes to take effect."

Pause
