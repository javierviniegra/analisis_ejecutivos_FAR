# deploy/windows/actualizar_diario.ps1
#
# Daily automatic update (owner, 2026-10-14; same idea as the Wansoft repo's
# Wansoft_Update_Repo_Diario). Fetches GitHub; only when main has new commits
# it runs deploy\update.ps1 (pull, dependencies, migrations, catalog, static
# files, server restart, source check). Nothing new: logs it and exits, the
# server is not touched. Everything goes to logs\update.log.
#
# Registered by registrar_tareas.ps1 as "Central de Reportes - Actualizar".

$ProjectDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Log = Join-Path $LogDir "update.log"
$SafeDir = $ProjectDir -replace '\\', '/'

function Escribir([string]$msg) {
    Add-Content -Path $Log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

Set-Location $ProjectDir
git -c "safe.directory=$SafeDir" fetch origin main 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Escribir "FALLO: git fetch (exit $LASTEXITCODE)"; exit 1 }
$Local = (git -c "safe.directory=$SafeDir" rev-parse HEAD).Trim()
$Remoto = (git -c "safe.directory=$SafeDir" rev-parse origin/main).Trim()
if ($Local -eq $Remoto) {
    Escribir ("Sin cambios ({0})" -f $Local.Substring(0, 7))
    exit 0
}

Escribir ("Actualizando {0} -> {1}" -f $Local.Substring(0, 7), $Remoto.Substring(0, 7))
$env:GIT_CONFIG_COUNT = "1"  # safe.directory for the update's own git pull
$env:GIT_CONFIG_KEY_0 = "safe.directory"
$env:GIT_CONFIG_VALUE_0 = $SafeDir
# A separate process with its output to files: in Windows PowerShell 5.1,
# redirecting it here would turn git's progress on stderr into errors that stop
# update.ps1 ($ErrorActionPreference = "Stop"). WaitForExit() and not -Wait:
# -Wait also waits for child processes, and update.ps1 leaves Waitress running.
# Files named per run: Waitress may inherit and keep a handle open.
$Marca = Get-Date -Format "yyyyMMdd_HHmmss"
$Salida = Join-Path $LogDir "update_$Marca.out.log"
$Errores = Join-Path $LogDir "update_$Marca.err.log"
$Proceso = Start-Process powershell.exe -PassThru -NoNewWindow -WorkingDirectory $ProjectDir `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $ProjectDir 'deploy\update.ps1')`"" `
    -RedirectStandardOutput $Salida -RedirectStandardError $Errores
$Proceso.WaitForExit()
Get-Content $Salida, $Errores -ErrorAction SilentlyContinue | Add-Content -Path $Log
Get-ChildItem $LogDir -Filter "update_*.log" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -ErrorAction SilentlyContinue
$Ahora = (git -c "safe.directory=$SafeDir" rev-parse HEAD).Trim()
if ($Ahora -ne $Remoto) { Escribir "FALLO: el codigo no quedo en origin/main, revisar arriba"; exit 1 }
Escribir ("Listo en {0}" -f $Ahora.Substring(0, 7))
