# Central de Reportes

**Central de Reportes** — web application (Django) for Grupo Fonda Argentina: a library of reports and automations, on demand by branch(es) and period. It will:

1. **Show** report information to authorized users.
2. **Generate** reports as Excel, PDF or both.
3. **Send** reports by email to configurable recipients, in a configurable format, on a configurable schedule (daily, weekly, monthly, semiannual, annual).

Report data comes from Odoo and the productive Wansoft MySQL. Executive reports use the standard Fonda Argentina branded template (see `scripts/`).

## Status

| Phase | What | State |
|---|---|---|
| 1 | Django skeleton, users, roles (Director, Administrador general, Gerente, Usuario), login | **Done in dev** (skeleton, models, roles, login; local database created and migrated, server verified on :8040). Pending: create the owner's superuser and assign branches |
| 2 | Report catalog (definition per report) | **Done in dev** (`reportes` app: model, admin, seed command, catalog/detail pages, 7 tests). Pending: assign profiles to each report in the admin |
| 3 | Generation engine (PDF + Excel), standard and financial-report templates | **In progress**: read-only data layer, open periods, metrics/consolidation, indicators table, rule-based Lectura, footnotes, charts, the two-page PDF (report + detail with the rules), the Excel workbook, the 38.0-39.9% cost target, the estimated total cost while Odoo invoicing is behind, the "Incluir costos" option and the on-demand web screen done; automations next (monthly PDFs still come from the standalone scripts) |
| 4 | Report viewing in the web app | Not started |
| 5 | Scheduled email delivery (subscriptions + dispatcher) | **In progress**: automation model (`Automatizacion`: one period kind, days after the close + hour, branches, consolidated and/or per branch, format, report options, recipients with "each one only their branch"), send log (`EnvioAutomatico`), permission `gestionar_envios` (Director, Administrador general), schedule logic, the "Automatizaciones" section on each report page (list, create, edit, pause) with separate recipients for the consolidated and the per-branch files, each branch's default recipients (one list for every report, in the admin), an "Enviar por correo" option on the generation screen for one-off e-mails (audited), and the dispatcher `enviar_automatizaciones` (every 15 min via Task Scheduler; one e-mail per recipient with all their files; retries; Microsoft 365 SMTP, or .eml files in dev) done; pending: SMTP credentials in production and the weekly send day |
| 6 | Analysis with Copilot (paid account) | Deferred to last, feasibility unverified |
| 7 | Production deployment | Not started |

Initial reports planned: weekly commercial report for managers (not yet defined), monthly short investor report, monthly Financial & Operational report for partners (PDF), the two weekly purchase-order Excel reports (Bodegón / Empanadas: modifications and by-hour), the weekly Operating Indicators report (Carlos's Power BI table, with traffic-light rules), the monthly profitability-by-delivery-platform report (Uber, Didi, etc.), the payroll incidents report from Buk for the payroll staff (pending: Buk API token and documentation), and more later.

**Rollout:** everything is built and tested locally first (owner's PC, local database). Production comes once a few reports are validated; there it will run a scheduled script that updates the code daily and restarts the app. Users get their own report view and can generate reports by hand. See `docs/DECISIONS.md`.

## Structure

- `config/` — Django project (settings, urls, wsgi). Settings are env-driven; see `config/.env.example`.
- `cuentas/` — users: `Sucursal`, `PerfilUsuario` (branch scope per user), role bootstrap command.
- `central/` — the report library (Django app `central`): report catalog: `Reporte` model (category, periodicity, template, data source, scope, formats, state, allowed profiles), `cargar_catalogo` seed command, catalog/detail pages.
- `central/motor/` — engine building blocks shared by every report (pure, tested): `periodos.py` / `periodo.py` (open periods: week, month, bimester, quarter, semester, year or free range, each with its previous period and same period last year), `comparativos.py` (arrow rule +-1%, and the project rule **s/cf = sin comparativo fiable** when either period has data on less than 90% of its expected days), `metricas.py` (batched read of all branches of a period, consolidation with explicit coverage, and the **comparable-branches rule**: a branch without full data in a comparison period is left out of both sides of that comparison), `tabla_comercial.py` (indicators table), `lectura.py` (rule-based "Lectura del periodo" box), `notas.py` (report footnotes: coverage notes plus every rule and threshold the report applies, built from the code's own constants), `graficas.py` (chart data, gross sales: per day / 7-day block / month by period length, matched by position to the comparison period; a month instead gets its sales per day alone plus a 12-month calendar trend vs the previous year) and `graficas_png.py` (draws them as PNG with matplotlib for the PDF), `formato.py`.
- `central/motor/reporte_comercial.py` — assembles the commercial report (Lectura, table, charts, footnotes) for a branch selection and a period, per branch or consolidated; the console check, the PDF, the web and the automations all use it.
- **On-demand generation (web):** `/reportes/<clave>/generar/` — pick branches (only the user's: `cuentas.models.sucursales_de`), period kind and date (or a free range up to 366 days), per branch or consolidated as the report's `alcance` allows; format PDF, Excel or both (only those the report admits); downloads the file. Several branches per branch always ask (no default) for one file or one file per branch; several files are delivered together in a .zip. Needs the `cuentas.generar_reportes` permission (or superuser) and a generator registered in `central/generadores.py` (today only `comercial-semanal-gerentes`).
- **CEDIS reports:** `central/motor/reporte_cedis.py` + `central/motor/fuentes/odoo.py` (read-only XML-RPC client) + `central/salidas/excel_cedis.py` — the Bodegón/Empanadas workbooks (modificaciones, por hora) from Odoo, from the providers' side so every branch appears: branch purchase orders for the branches on Odoo (each from its Odoo purchases start, Wansoft `dim_company_analytical`), the providers' sales orders for the rest, mapped to branches by `ClienteCedis` (admin; seed with `python manage.py cargar_clientes_cedis`); every change says whether the branch or the CEDIS made it.
- `central/salidas/` — outputs: `excel_comercial.py` (workbook per report: Resumen with real numbers and arrow columns, the data behind each chart with a native Excel chart, Detalle, Notas; one sheet group per branch when several share a workbook), `pdf_comercial.py` (two letter pages per report on the Fonda template -- the report, then the detail per branch or per day and the rules: brand background in `recursos/fondo_fonda.jpeg`, DejaVu Sans font bundled with matplotlib).
- `central/motor/fuentes/` — read-only data access: `wansoft.py` (deduplicated daily cash closings by operating day, channel, mix; one batched query per period for all branches), `presupuestos.py` (Costo de Ventas budget vs real from ControlPresupuestos_AP), `odoo.py` (read-only XML-RPC: CEDIS orders, and the invoiced sales behind the estimated total cost), `conexiones.py` (read-only sessions, 120 s server-side cap per statement). **`FUENTES_ENV`** in `config/.env` chooses where report data is read from (`prod` or `dev`, defaults to `ENV`), independently of the app's own database. Verify with `python manage.py probar_reporte <branches|todas> --tipo <kind> [--fecha | --desde --hasta] [--consolidado]` (prints the Lectura, the table and the footnotes; `--graficas <folder>` also saves the charts as PNG, `--pdf <folder>` the PDF, `--excel <folder>` the workbook, `--sin-costos` leaves every cost out). Branch mapping across systems: `python manage.py cargar_sucursales`.
- `templates/` — shared templates (`base.html`, login, admin branding). Same look as ControlPresupuestos_AP: brand green `#035953`, dark green `#023f3b`, cream `#f0e9d8`, gradient login card, Fonda Argentina logo.
- `static/ejecutivos/` — logo and admin theme CSS (copied from ControlPresupuestos_AP so both apps stay visually consistent).
- `scripts/` — standalone report generators (pre-Django). `build_executive_pdf_all.py` is the current standard (19 branches); `build_executive_pdf.py` and `build_executive_pdf_multi.py` are historical.
- **Source checks:** `python manage.py verificar_fuentes [--hoy YYYY-MM-DD] [--sin-tickets]` — read-only PASS/WARN/FAIL check that every table/column the engine reads exists (declared as `COLUMNAS_REQUERIDAS` next to the queries in `central/motor/fuentes/`), that the configured accounts cannot write, that the 2026-10-01 cutover migration is applied, and that cash closings and ticket detail are fresh for every active branch. Run it after any change on the source side.
- `deploy/sql/create_central_reportes_readonly_user.sql` — the dedicated read-only database user for this app (SELECT on the documented `wansoft` tables and the 5 `presupuestos_ap` tables it reads; 4 connections, 5 min per query). Run by the owner as root; password only in `config/.env`.
- `docs/` — documentation (`docs/PRODUCTION_SETUP.md`, `docs/DECISIONS.md`), example reports (`docs/Ejemplos/`) and generated monthly PDFs (`docs/Mensuales/<year>/<Month>/`, gitignored).

## Conventions (mirrors ControlPresupuestos_AP)

- Django `>=4.2,<5.0` (the dev/prod MariaDB is 10.4.32; Django 5 needs 10.5+).
- `.env` driven, with a `_DEV` suffix for the dev database variables. **One deliberate difference:** the `.env` lives at `config/.env`, not `core/config/.env`, because this repo has no `core` package (the scripts import the Wansoft repo's own `core`; two packages with that name would collide).
- Production: Waitress + WhiteNoise on the app machine, behind the Apache reverse proxy under the URL prefix `/central_reportes/`.
- **Port 8040** (dev and production). Do not use 8000 (XAMPP), 8010/8020 (ControlPresupuestos_AP).
- The app's own database (users, profiles, subscriptions, send log) lives on the **separate database server**, not on the app machine.

## Roles and permissions

A user's role is a Django **Group**; what each role may do is editable from the admin (Groups) without code changes. Custom permissions: `ver_reportes`, `generar_reportes`, `gestionar_envios`, `gestionar_usuarios`. `PerfilUsuario` adds branch scope (a manager only sees their branches unless `todas_las_sucursales`). Area groups -- **Nominista** (payroll), **CEDIS** (El Bodegón) and **Contabilidad** -- only see the reports assigned to them.

Create the base roles -- Director, Administrador general, Gerente, Usuario, Nominista, CEDIS, Contabilidad (idempotent, never overwrites admin edits to existing groups):

```
python manage.py crear_perfiles
```

## Report catalog

Each report is a `Reporte` row (admin: *Reportes*). **Access rule:** a report is visible only to users whose group (profile) is assigned to it in the report's `perfiles`; a report with no profiles is visible to nobody except staff, and a report you may not see returns 404. The catalog page filters by category (only the user's categories are offered). Load the initial reports (idempotent, never overwrites admin edits; new ones start with no profiles assigned):

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
