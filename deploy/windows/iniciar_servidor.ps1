# deploy/windows/iniciar_servidor.ps1
#
# Starts Central de Reportes with Waitress in the background on port 8040
# (8020 is Presupuestos AP's; XAMPP holds 80/443/3306 on this VM).
# - Without arguments: starts it only if nothing is listening yet. This is
#   what the "at startup" scheduled task runs, so the app comes back by
#   itself after the VM restarts.
# - With -Reiniciar: stops the running one first (update.ps1 uses this).

param([switch]$Reiniciar)

$ErrorActionPreference = "Stop"
$Port = 8040

$ProjectDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$WaitressExe = Join-Path $ProjectDir ".venv\Scripts\waitress-serve.exe"
$LogsDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$escuchando = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue
if ($escuchando.TcpTestSucceeded -and -not $Reiniciar) {
    Write-Host "Central de Reportes ya esta escuchando en el puerto $Port."
    exit 0
}

# Only this project's Waitress (another app on the VM uses its own copy).
Get-Process waitress-serve -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $WaitressExe } |
    Stop-Process -Force
Start-Sleep -Seconds 1

Start-Process -FilePath $WaitressExe `
    -ArgumentList "--host=0.0.0.0", "--port=$Port", "--threads=8", "--channel-timeout=300", "config.wsgi:application" `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogsDir "waitress.out.log") `
    -RedirectStandardError (Join-Path $LogsDir "waitress.err.log")

Start-Sleep -Seconds 3
$escuchando = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue
if ($escuchando.TcpTestSucceeded) {
    Write-Host "Listo: Central de Reportes escucha en el puerto $Port."
} else {
    Write-Host "AVISO: el puerto $Port no responde todavia. Revisa logs\waitress.err.log."
}
