# PowerShell script to install Python, add it to the user PATH, and install uv
# Run as a normal user (admin rights are not required for modifying PATH and CurrentUser ExecutionPolicy)

# Require:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# ------------------------------
# Configuration
# ------------------------------
$pythonUrl = "https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe"   # Adjust if you want another version
$installer = "$env:TEMP\python-installer.exe"

# ------------------------------
# Download and Install Python installer
# ------------------------------
Write-Host "Downloading Python installer..."
Invoke-WebRequest -Uri $pythonUrl -OutFile $installer

Write-Host "Installing Python..."
Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=0 Include_test=0" -Wait -NoNewWindow

# Path where Python is usually installed for current user
$pythonPath = "$env:LocalAppData\Programs\Python\Python312"
$pipPath = "$pythonPath\Scripts"

# ------------------------------
# Adding Python to the user PATH
# ------------------------------
Write-Host "Adding Python to the user PATH..."

$oldPath = [Environment]::GetEnvironmentVariable("PATH", "User")

if ($oldPath -notlike "*$pythonPath*" -or $oldPath -notlike "*$pipPath*") {
    $newPath = "$pythonPath;$pipPath;$oldPath"
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    $env:PATH = $newPath
    Write-Host "Python paths added to user PATH."
} else {
    Write-Host "Python paths already exist in user PATH."
}

# ------------------------------
# Install uv (Astral)
# ------------------------------
Write-Host "Installing uv..."

winget install -e --id astral-sh.uv
#$uvInstaller = "$env:TEMP\install-uv.py"
#Invoke-WebRequest -Uri "https://astral.sh/install-uv.py" -OutFile $uvInstaller

#$pythonExe = "$pythonPath\python.exe"
#& $pythonExe $uvInstaller

# Add uv to PATH if needed
$uvPath = "$env:USERPROFILE\.local\bin"

$oldPath = [Environment]::GetEnvironmentVariable("PATH", "User")

if (-not ($oldPath.Split(";") -contains $uvPath)) {
    $newPath = $uvPath + ";" + $oldPath
    $env:PATH = $newPath
    [Environment]::SetEnvironmentVariable("PATH", $newPath, 'User')
    Write-Host "uv path added to user PATH."
} else {
    Write-Host "uv path already exists in user PATH."
}

# ------------------------------
# Verify installation
# ------------------------------
$uvExe = "$uvPath\uv.exe"
if (Test-Path $uvExe) {
    Write-Host "`n✅ uv installed successfully!"
    & $uvExe --version
} else {
    Write-Host "`n❌ uv.exe not found in $uvPath" -ForegroundColor Red
}

#
# Install git
# 

Write-Host "Installing git..."

winget install -e --id Git.Git

#
# Install exiftools
#

Write-Host "Installing exiftools..."
winget install -e --id OliverBetz.ExifTool

Write-Host "`nPlease close and reopen your terminal for the PATH changes to take effect."
Write-Host "If you encounter permission issues, run: Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force"
