# deploy/windows/registrar_tareas.ps1
#
# Registers (or updates) the two Windows Scheduled Tasks of Central de
# Reportes on the production VM. Run once, in an administrator PowerShell,
# from the project folder; safe to run again (-Force replaces them).
#
#   1. "Central de Reportes - Envios"  : every 15 minutes, sends the
#      automations that are due (deploy\windows\enviar_automatizaciones.cmd).
#   2. "Central de Reportes - Arranque": at VM startup, starts the web server
#      (deploy\windows\iniciar_servidor.ps1), so a reboot does not leave the
#      app down.
#
# Both run as the current user with logon type S4U: they run whether or not
# anyone is logged on, without storing a password (they only need the
# network - MySQL and Microsoft 365 - not Windows file shares).

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Usuario = "$env:USERDOMAIN\$env:USERNAME"
$Principal = New-ScheduledTaskPrincipal -UserId $Usuario -LogonType S4U -RunLevel Highest
$Ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# 1. Sends, every 15 minutes, indefinitely.
$Envios = New-ScheduledTaskAction -Execute (Join-Path $ProjectDir "deploy\windows\enviar_automatizaciones.cmd") `
    -WorkingDirectory $ProjectDir
$Cada15 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "Central de Reportes - Envios" -Action $Envios -Trigger $Cada15 `
    -Principal $Principal -Settings $Ajustes -Force | Out-Null

# 2. Web server at startup.
$Arranque = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $ProjectDir 'deploy\windows\iniciar_servidor.ps1')`"" `
    -WorkingDirectory $ProjectDir
$AlIniciar = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "Central de Reportes - Arranque" -Action $Arranque -Trigger $AlIniciar `
    -Principal $Principal -Settings $Ajustes -Force | Out-Null

Get-ScheduledTask -TaskName "Central de Reportes*" | Format-Table TaskName, State -AutoSize
Write-Host "Listo. Historial de envios: logs\enviar_automatizaciones.log y, en la app, Admin > Envios automaticos."
