# PowerShell script to install Docker Desktop on Windows
# It downloads the latest stable release from the official Docker source
# and installs it silently.
# Requires admin rights for installation.

# ------------------------------
# Configuration
# ------------------------------
$dockerInstallerUrl = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
$installerPath = "$env:TEMP\DockerDesktopInstaller.exe"

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
Write-Host "`n🚢 Starting Docker Desktop..."
Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"

Write-Host "`n✅ Installation complete!"
Write-Host "You may need to log out and back in for Docker to integrate with WSL2."
Write-Host "Once Docker Desktop starts, run 'docker run hello-world' to verify."
