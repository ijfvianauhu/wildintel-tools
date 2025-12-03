# PowerShell script to install Docker Desktop on Windows
# Requires admin rights for installation.

# Ensure script is running as administrator
If (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole] "Administrator")) {
    Write-Host "Please run this script as Administrator!"
    Exit
}

# ------------------------------
# Configuration
# ------------------------------
$dockerInstallerUrl = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
$installerPath = "$env:TEMP\DockerDesktopInstaller.exe"
$wslInstallerUrl = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
$wslInstallerPath = "$env:TEMP\wsl_update_x64.msi"

Write-Host "============================================="
Write-Host "Enabling WSL and Virtual Machine Platform..."
Write-Host "============================================="

dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

Write-Host "============================================="
Write-Host "Setting WSL 2 as default version..."
Write-Host "============================================="

wsl --set-default-version 2

Write-Host "============================================="
Write-Host "⬇️ Downloading WSL 2 Linux kernel..."
Write-Host "============================================="

Invoke-WebRequest -Uri $wslInstallerUrl -OutFile $wslInstallerPath

Write-Host "============================================="
Write-Host "🚀 Installing WSL 2 Linux kernel..."
Write-Host "============================================="

Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$wslInstallerPath`" /quiet /norestart" -Wait
Remove-Item $wslInstallerPath

Write-Host "============================================="
Write-Host "🚀 Installing Docker Desktop for Windows..."
Write-Host "============================================="

# ------------------------------
# Check if Docker is already installed
# ------------------------------
if (Get-Command "docker" -ErrorAction SilentlyContinue) {
    Write-Host "✅ Docker is already installed. Checking version..."
    docker --version
    exit 0
}

# ------------------------------
# Download installer
# ------------------------------
Write-Host "`n⬇️ Downloading Docker Desktop installer..."
Invoke-WebRequest -Uri $dockerInstallerUrl -OutFile $installerPath

if (!(Test-Path $installerPath)) {
    Write-Host "❌ Failed to download Docker installer." -ForegroundColor Red
    exit 1
}

# ------------------------------
# Install Docker Desktop (requires elevation)
# ------------------------------
Write-Host "`n⚙️ Installing Docker Desktop... (this may take a few minutes)"
Start-Process -FilePath $installerPath -ArgumentList "install", "--quiet" -Verb RunAs -Wait

# ------------------------------
# Verify installation
# ------------------------------
Write-Host "`n🔍 Checking Docker installation..."
$dockerPath = "$env:ProgramFiles\Docker\Docker\resources\bin"

if (Test-Path "$dockerPath\docker.exe") {
    Write-Host "✅ Docker Desktop installed successfully."
} else {
    Write-Host "❌ Docker Desktop installation failed." -ForegroundColor Red
    exit 1
}

# ------------------------------
# Add Docker to PATH (if needed)
# ------------------------------
$oldPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if (-not ($oldPath.Split(";") -contains $dockerPath)) {
    Write-Host "Adding Docker to the user PATH..."
    $newPath = "$dockerPath;$oldPath"
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    $env:PATH = $newPath
} else {
    Write-Host "Docker path already exists in user PATH."
}

# ------------------------------
# Start Docker Desktop
# ------------------------------
$dockerDesktopExe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"

if (Test-Path $dockerDesktopExe) {
    Write-Host "`n🚢 Starting Docker Desktop..."
    & "$dockerDesktopExe"
} else {
    Write-Host "❌ Docker Desktop executable not found at $dockerDesktopExe" -ForegroundColor Red
}

Write-Host "`n✅ Installation complete!"
Write-Host "You may need to log out and back in for Docker to integrate with WSL2."
Write-Host "Once Docker Desktop starts, run 'docker run hello-world' to verify."
