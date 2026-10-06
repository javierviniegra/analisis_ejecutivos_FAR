# Production setup

Same layout as ControlPresupuestos_AP (owner, 2026-10-06):

| Piece | Where |
|---|---|
| App (Waitress + WhiteNoise, no IIS/nginx) | App VM `SVR-HIKCENTER` (192.168.100.93), next to Presupuestos AP, **port 8040** (8020 is Presupuestos'; XAMPP holds 80/443/3306) |
| App database `centraldereportes` | MySQL/MariaDB (XAMPP) on the DB/proxy server **187.251.203.223** -- the same server as `presupuestos_ap` and `wansoft` |
| Report sources (read-only) | `wansoft` and `presupuestos_ap` on that same server, read with the SELECT-only user `central_reportes`; Odoo via XML-RPC |
| URL for users | **`http://187.251.203.223:8088/central_reportes/`** (Apache reverse proxy on that server) |
| Scheduled e-mails | Task Scheduler on the app VM, every 15 minutes |

Production changes are run by the owner; every step below says where it runs.

## 1. Code and virtualenv (app VM)

Python 3.12+ and Git are already on the VM (Presupuestos uses them). In PowerShell:

```powershell
cd C:\Apps
git clone https://github.com/javierviniegra/analisis_ejecutivos_FAR.git CentralDeReportes
cd CentralDeReportes
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. App database (DB server 187.251.203.223, phpMyAdmin > SQL, as root)

```sql
CREATE DATABASE centraldereportes CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'centraldereportes'@'%' IDENTIFIED BY 'CHOOSE_A_REAL_PASSWORD';
GRANT ALL PRIVILEGES ON centraldereportes.* TO 'centraldereportes'@'%';
FLUSH PRIVILEGES;
```

**Initial data = a copy of the dev database** (owner's choice): users and profiles, catalogue and report profiles, branches (with their default recipients), CEDIS customers and the automations. The dump is generated on the dev PC into `logs\centraldereportes_inicial.sql` (never committed: it holds password hashes). In phpMyAdmin select `centraldereportes` > **Import** > that file. The migrations table travels with it, so `migrate` afterwards only applies what is newer.

## 3. Read-only user for the sources (same server, as root)

Run `deploy/sql/create_central_reportes_readonly_user.sql` after replacing `CHANGE_ME` with a long password (only in `.env`, never in git). It grants SELECT on the tables of `wansoft` and `presupuestos_ap` the reports read (including `costs_source_by_company`, published by the Wansoft pipeline since 2026-10-06).

## 4. `config\.env` (app VM)

```powershell
copy config\.env.example config\.env
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
notepad config\.env
```

```ini
ENV=prod
FUENTES_ENV=prod
DJANGO_SECRET_KEY=<what the command above printed - never reuse dev's>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=187.251.203.223,192.168.100.93,localhost,127.0.0.1
DJANGO_FORCE_SCRIPT_NAME=/central_reportes
DJANGO_CSRF_TRUSTED_ORIGINS=http://187.251.203.223:8088

EJECUTIVOS_DB_HOST=187.251.203.223
EJECUTIVOS_DB_PORT=3306
EJECUTIVOS_DB_USER=centraldereportes
EJECUTIVOS_DB_PASSWORD=<step 2>
EJECUTIVOS_DB_NAME=centraldereportes

WANSOFT_DB_HOST=187.251.203.223
WANSOFT_DB_USER=central_reportes
WANSOFT_DB_PASSWORD=<step 3>
WANSOFT_DB_NAME=wansoft
PRESUPUESTOS_DB_HOST=187.251.203.223
PRESUPUESTOS_DB_PORT=3306
PRESUPUESTOS_DB_USER=central_reportes
PRESUPUESTOS_DB_PASSWORD=<step 3>
PRESUPUESTOS_DB_NAME=presupuestos_ap

ODOO_URL=<same as dev>
ODOO_DB_NAME=<same as dev>
ODOO_USER=<same as dev; a read-only Odoo user is recommended>
ODOO_PASSWORD=<same as dev>

CORREO_MODO=smtp
EMAIL_HOST=smtp.office365.com
EMAIL_PORT=587
EMAIL_HOST_USER=inteligencia@gruporodiva.com
EMAIL_HOST_PASSWORD=<that mailbox's password>
EMAIL_FROM=Grupo Hospitalario Rodiva
CORREO_CONTACTO=aidee.lopez@fondaargentina.com
```

Leave the `_DEV` variables empty (read only when `ENV=dev`). `DJANGO_SECURE_COOKIES=true` only once HTTPS is in front of the proxy.

**E-mail:** `inteligencia@gruporodiva.com` needs "SMTP autenticado" on (done 2026-10-06 with `Set-CASMailbox ... -SmtpClientAuthenticationDisabled $false`; the tenant itself keeps it off). Until a login succeeds, keep `CORREO_MODO=archivo` (e-mails saved under `logs\correos\`, nothing sent) or pause the automations, so they do not burn their 3 attempts.

## 5. Reverse proxy (DB/proxy server, Apache `httpd-vhosts.conf`)

Inside the existing `<VirtualHost *:8088>`, next to `/presupuestos_ap/`:

```apache
# Central de Reportes
ProxyPass /central_reportes/ http://192.168.100.93:8040/
ProxyPassReverse /central_reportes/ http://192.168.100.93:8040/
RedirectMatch ^/central_reportes$ /central_reportes/
ProxyTimeout 300
```

Restart Apache. `DJANGO_FORCE_SCRIPT_NAME` (step 4) makes every link Django generates carry the prefix, as in Presupuestos. `ProxyTimeout 300`: a long consolidated report can take more than the default 60 s.

## 6. First start (app VM)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser   # once, if scripts are blocked
.\deploy\update.ps1
```

It pulls, installs, migrates, creates missing profiles, collects static files, starts Waitress on 8040 (`deploy\windows\iniciar_servidor.ps1`; logs in `logs\waitress.*.log`) and runs `verificar_fuentes` (expect all PASS, no write-rights WARN once `central_reportes` is in `.env`).

Check `Test-NetConnection 127.0.0.1 -Port 8040` on the VM, then `http://187.251.203.223:8088/central_reportes/` from any PC.

## 7. Scheduled tasks (app VM, administrator PowerShell)

```powershell
.\deploy\windows\registrar_tareas.ps1
```

Registers **"Central de Reportes - Envios"** (every 15 min: `deploy\windows\enviar_automatizaciones.cmd`, log `logs\enviar_automatizaciones.log`) and **"Central de Reportes - Arranque"** (at VM startup: starts the web server, so a reboot does not leave the app down -- the limitation Presupuestos still has). Both run whether or not anyone is logged on (S4U, no stored password).

Before relying on them: `.venv\Scripts\python.exe manage.py enviar_automatizaciones --pendientes` (what is due; sends nothing) and `--probar <id>` (one automation now, without touching the send log).

## Updates

Push to GitHub from dev, then on the app VM: `.\deploy\update.ps1`.
