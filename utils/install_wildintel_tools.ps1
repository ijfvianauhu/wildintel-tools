# PowerShell script to install wildintel-tools using uv
# Requires: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# -------------------------------------
# Configuration
# -------------------------------------
$wildintel_tools_version = "v0.1.0"
$repo_url = "https://github.com/ijfvianauhu/wildintel-tools.git"
$repo_dir = "wildintel-tools"


Write-Host "-------------------------------------"
Write-Host " WildIntel Tools Installer"
Write-Host "-------------------------------------"
Write-Host ""


# -------------------------------------
# Check dependencies
# -------------------------------------

function Check-Command {
    param(
        [string]$cmd,
        [string]$name
    )

    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "✕ $name NO está instalado." -ForegroundColor Red
        return $false
    }

    Write-Host "✓ $name encontrado." -ForegroundColor Green
    return $true
}


Write-Host "Checking dependencies..."

$hasGit = Check-Command -cmd "git" -name "Git"
$hasUV = Check-Command -cmd "uv" -name "uv"
$hasWinget = Check-Command -cmd "winget" -name "winget"

if (-not $hasGit -or -not $hasUV) {
    Write-Hos
