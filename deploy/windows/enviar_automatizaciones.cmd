@echo off
rem Central de Reportes: send the scheduled report e-mails that are due.
rem Task Scheduler runs this every 15 minutes (see docs/PRODUCTION_SETUP.md, section 5).
cd /d "%~dp0..\.."
".venv\Scripts\python.exe" manage.py enviar_automatizaciones >> "logs\enviar_automatizaciones.log" 2>&1
