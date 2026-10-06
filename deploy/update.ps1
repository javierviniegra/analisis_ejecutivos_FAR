# deploy/update.ps1
#
# Run this by hand on the production VM whenever there's a new version to
# deploy (same routine as ControlPresupuestos_AP). Pulls the latest code from
# GitHub, installs any new dependencies, applies migrations, refreshes static
# files, restarts the server and checks the data sources.
#
# First-time setup (clone, venv, .env, database) is NOT part of this script -
# see docs/PRODUCTION_SETUP.md, once.

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
Set-Location $ProjectDir

Write-Host "=== Pulling latest code from GitHub ==="
git pull origin main

Write-Host "=== Installing/updating dependencies ==="
& $Python -m pip install -r requirements.txt

Write-Host "=== Applying database migrations ==="
& $Python manage.py migrate --noinput

Write-Host "=== Base profiles (only creates missing ones; admin edits are kept) ==="
& $Python manage.py crear_perfiles

Write-Host "=== Collecting static files ==="
& $Python manage.py collectstatic --noinput

Write-Host "=== Restarting the server ==="
& (Join-Path $PSScriptRoot "windows\iniciar_servidor.ps1") -Reiniciar

Write-Host "=== Checking the data sources (read-only) ==="
# Reports a FAIL without stopping the deploy: the app is up either way, and
# the output says what to fix (.env, read-only user, schema).
$ErrorActionPreference = "Continue"
& $Python manage.py verificar_fuentes --sin-tickets
