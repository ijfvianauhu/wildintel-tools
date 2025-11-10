# Script PowerShell para instalar Spice Guest Tools, VirtIO y habilitar SSH
# Ejecutar con privilegios de administrador

# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# ------------------------------
# Comprobar si se ejecuta como Administrador
# ------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "❌ Este script debe ejecutarse como Administrador." -ForegroundColor Red
    exit 1
}

# ------------------------------
# Variables
# ------------------------------
$spiceUrl = "https://www.spice-space.org/download/windows/spice-guest-tools/spice-guest-tools-latest.exe"
$virtioUrl = "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-0.1.285-1/virtio-win-gt-x86.msi"
$tempDir = "$env:TEMP\vmtools"
$spiceInstaller = "$tempDir\spice-guest-tools.exe"
$virtioInstaller = "$tempDir\virtio-win.msi"

# ------------------------------
# Crear carpeta temporal
# ------------------------------
if (!(Test-Path -Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir | Out-Null
}

# ------------------------------
# Descargar instaladores
# ------------------------------
Write-Host "Descargando Spice Guest Tools..."
Invoke-WebRequest -Uri $spiceUrl -OutFile $spiceInstaller

Write-Host "Descargando VirtIO..."
Invoke-WebRequest -Uri $virtioUrl -OutFile $virtioInstaller

# ------------------------------
# Instalar Spice Guest Tools
# ------------------------------
Write-Host "Instalando Spice Guest Tools..."
Start-Process -FilePath $spiceInstaller -ArgumentList "/S" -Wait -NoNewWindow

# ------------------------------
# Instalar VirtIO
# ------------------------------
Write-Host "Instalando VirtIO..."
Start-Process "msiexec.exe" -ArgumentList "/i `"$virtioInstaller`" /quiet /norestart" -Wait -NoNewWindow

# ------------------------------
# Instalar y habilitar OpenSSH Server
# ------------------------------
Write-Host "Instalando servidor OpenSSH..."
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Configurar servicio
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd

# (Opcional) permitir SSH en el firewall
if (!(Get-NetFirewallRule -Name "SSHD-In-TCP" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name "SSHD-In-TCP" -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
}

Write-Host "Instalación completada. El servidor SSH está en marcha."
