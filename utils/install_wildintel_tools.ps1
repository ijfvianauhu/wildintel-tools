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

if (-not $hasGit -or -not $hasUV) {
    Write-Host ""
    Write-Host "✕ No se puede continuar porque faltan dependencias requeridas (Git o UV)." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✓ Dependencias mínimas presentes. Continuando..."
Write-Host ""


# -------------------------------------
# Clone repository
# -------------------------------------

if (Test-Path $repo_dir) {
    Write-Host "El directorio '$repo_dir' ya existe. Usaré ese." -ForegroundColor Yellow
} else {
    Write-Host "Clonando repositorio..."
    git clone $repo_url

    if ($LASTEXITCODE -ne 0) {
        Write-Host "✕ Error clonando el repositorio." -ForegroundColor Red
        exit 1
    }
}

Set-Location $repo_dir

Write-Host "Cambiando a la versión $wildintel_tools_version..."
git checkout $wildintel_tools_version

if ($LASTEXITCODE -ne 0) {
    Write-Host "✕ No se pudo cambiar a la versión especificada." -ForegroundColor Red
    exit 1
}

Write-Host "✓ Repositorio listo." -ForegroundColor Green
Write-Host ""


# -------------------------------------
# Run the tool
# -------------------------------------

Write-Host "Ejecutando wildintel-tools con uv..."
Write-Host ""

try {
    uv run wildintel-tools --help
} catch {
    Write-Host "✕ Error ejecutando wildintel-tools." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✓ Instalación finalizada correctamente!" -ForegroundColor Green
