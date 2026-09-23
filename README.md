# Analisis Ejecutivos

Web application (Django) for Grupo Fonda Argentina that will:

1. **Show** report information to authorized users.
2. **Generate** reports as Excel, PDF or both.
3. **Send** reports by email to configurable recipients, in a configurable format, on a configurable schedule (daily, weekly, monthly, semiannual, annual).

Report data comes from Odoo and the productive Wansoft MySQL. Executive reports use the standard Fonda Argentina branded template (see `scripts/`).

## Status

| Phase | What | State |
|---|---|---|
| 1 | Django skeleton, users, roles (Director, Administrador general, Gerente, Usuario), login | **Done in dev** (skeleton, models, roles, login; local database created and migrated, server verified on :8040). Pending: create the owner's superuser and assign branches |
| 2 | Report catalog (definition per report) | **Done in dev** (`reportes` app: model, admin, seed command, catalog/detail pages, 7 tests). Pending: assign profiles to each report in the admin |
| 3 | Generation engine (PDF + Excel), standard and financial-report templates | Not started (PDF generator exists as standalone scripts) |
| 4 | Report viewing in the web app | Not started |
| 5 | Scheduled email delivery (subscriptions + dispatcher) | Not started |
| 6 | Analysis with Copilot (paid account) | Deferred to last, feasibility unverified |
| 7 | Production deployment | Not started |

Initial reports planned: weekly commercial report for managers (not yet defined), monthly short investor report, monthly Financial & Operational report for partners (PDF), the two weekly purchase-order Excel reports (Bodegón / Empanadas: modifications and by-hour), the weekly Operating Indicators report (Carlos's Power BI table, with traffic-light rules), the monthly profitability-by-delivery-platform report (Uber, Didi, etc.), and more later.

**Rollout:** everything is built and tested locally first (owner's PC, local database). Production comes once a few reports are validated; there it will run a scheduled script that updates the code daily and restarts the app. Users get their own report view and can generate reports by hand. See `docs/DECISIONS.md`.

## Structure

- `config/` — Django project (settings, urls, wsgi). Settings are env-driven; see `config/.env.example`.
- `cuentas/` — users: `Sucursal`, `PerfilUsuario` (branch scope per user), role bootstrap command.
- `reportes/` — report catalog: `Reporte` model (category, periodicity, template, data source, scope, formats, state, allowed profiles), `cargar_catalogo` seed command, catalog/detail pages.
- `reportes/motor/` — engine building blocks shared by every report: `periodos.py` (Monday-Sunday weeks, previous week, same ISO week last year, monthly-to-daily budget proration) and `comparativos.py` (variation and arrow rule, +-1% threshold).
- `reportes/motor/fuentes/` — read-only data access: `wansoft.py` (deduplicated daily cash closings by operating day, channel, mix), `presupuestos.py` (Costo de Ventas budget vs real from ControlPresupuestos_AP), `conexiones.py`. Verify with `python manage.py probar_semana <branch> [date]`. Branch mapping across systems: `python manage.py cargar_sucursales`.
- `templates/` — shared templates (`base.html`, login, admin branding). Same look as ControlPresupuestos_AP: brand green `#035953`, dark green `#023f3b`, cream `#f0e9d8`, gradient login card, Fonda Argentina logo.
- `static/ejecutivos/` — logo and admin theme CSS (copied from ControlPresupuestos_AP so both apps stay visually consistent).
- `scripts/` — standalone report generators (pre-Django). `build_executive_pdf_all.py` is the current standard (19 branches); `build_executive_pdf.py` and `build_executive_pdf_multi.py` are historical.
- `docs/` — documentation (`docs/PRODUCTION_SETUP.md`, `docs/DECISIONS.md`), example reports (`docs/Ejemplos/`) and generated monthly PDFs (`docs/Mensuales/<year>/<Month>/`, gitignored).

## Conventions (mirrors ControlPresupuestos_AP)

- Django `>=4.2,<5.0` (the dev/prod MariaDB is 10.4.32; Django 5 needs 10.5+).
- `.env` driven, with a `_DEV` suffix for the dev database variables. **One deliberate difference:** the `.env` lives at `config/.env`, not `core/config/.env`, because this repo has no `core` package (the scripts import the Wansoft repo's own `core`; two packages with that name would collide).
- Production: Waitress + WhiteNoise on the app machine, behind the Apache reverse proxy under the URL prefix `/analisis_ejecutivos/`.
- **Port 8040** (dev and production). Do not use 8000 (XAMPP), 8010/8020 (ControlPresupuestos_AP).
- The app's own database (users, profiles, subscriptions, send log) lives on the **separate database server**, not on the app machine.

## Roles and permissions

A user's role is a Django **Group**; what each role may do is editable from the admin (Groups) without code changes. Custom permissions: `ver_reportes`, `generar_reportes`, `gestionar_envios`, `gestionar_usuarios`. `PerfilUsuario` adds branch scope (a manager only sees their branches unless `todas_las_sucursales`).

Create the four base roles (idempotent, never overwrites admin edits to existing groups):

```
python manage.py crear_perfiles
```

## Report catalog

Each report is a `Reporte` row (admin: *Reportes*). **Access rule:** a report is visible only to users whose group (profile) is assigned to it in the report's `perfiles`; a report with no profiles is visible to nobody except staff, and a report you may not see returns 404. Load the initial reports (idempotent, never overwrites admin edits; new ones start with no profiles assigned):

```
python manage.py cargar_catalogo
```

Run the tests with `python manage.py test` (needs the local MariaDB; Django creates and drops its own `test_` database).

## Local setup (dev)

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy config\.env.example config\.env      # then fill it in (secret key, dev DB)
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py crear_perfiles
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py runserver 8040
```

**All credentials live in `config/.env`** (gitignored); `config/.env.example` documents every variable with blank placeholders. Never put a secret in code, SQL, docs or git.

The dev database must exist first. Fill in `config/.env` (`EJECUTIVOS_DB_PASSWORD_DEV`, and the local admin account `EJECUTIVOS_DB_ADMIN_USER_DEV` / `EJECUTIVOS_DB_ADMIN_PASSWORD_DEV`, e.g. XAMPP's root), then run once:

```
.venv\Scripts\python.exe scripts\setup_dev_db.py
```

It creates `analisis_ejecutivos_dev` (utf8mb4) and, if `EJECUTIVOS_DB_USER_DEV` differs from the admin user, the restricted user from those variables. (Dev-only exception: setting `EJECUTIVOS_DB_USER_DEV=root` makes the app use the local root account; the script then only creates the database. Never do this in production.) It refuses to run unless `ENV=dev` and the host is local, and is safe to re-run (re-applies the app user's password, so it also rotates it). After that the admin variables are no longer needed and can be removed from `config/.env`.

## Report generator (standalone scripts)

`scripts/*.py` import `core.database.*` / `core.config.*` from the sibling `Wansoft` repo via a hardcoded absolute path (`WANSOFT_REPO_ROOT`). This works only because both repos are sibling folders on this machine and is **temporary**: it will be replaced by this app's own data-access layer. To run: set `ANIO`/`MES_NUM` at the top of `build_executive_pdf_all.py` and run it (needs the Wansoft dev MySQL running); it creates `docs/Mensuales/<year>/<Month>/` if missing.

## Documentation rule

Every change that alters behavior, structure, setup or a decision must update this README and/or `docs/` in the same commit. Commit messages and docs are written in English.
