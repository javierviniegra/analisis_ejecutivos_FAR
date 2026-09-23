# Decisions

Newest first. Each entry: what, why, and where it applies.

## 2026-09-23 — Rollout plan and additional requirements

- **All secrets/credentials live only in `config/.env`, with blank placeholders in `config/.env.example`** (database, admin account for setup, and later SMTP, API tokens, Odoo/Wansoft access). Never in code, SQL, docs or git. Consequence: the dev DB is created by `scripts/setup_dev_db.py`, which reads `.env`, instead of a SQL file with a password.
- **Dev-only exception: the app may connect to the local database as the local `root` account** (owner's explicit choice, 2026-09-23). `scripts/setup_dev_db.py` then only creates the database and never touches root's password; empty passwords are accepted because the script refuses non-local hosts. This must NOT carry over to production, where the app uses a dedicated user restricted to its own database (see `docs/PRODUCTION_SETUP.md`).
- **Everything starts in test mode on the owner's PC with the local database** (`scripts/setup_dev_db.py`). Production comes only after a few reports are implemented and validated locally.
- **Production auto-update:** production will run a scheduled script that updates the code daily (pull from GitHub) and restarts the app, so production always runs the latest version with the latest reports. To be built in Phase 7 (analogous to ControlPresupuestos_AP's `deploy/update.ps1`, plus a Scheduled Task).
- **Per-user report views and manual generation:** each user sees the reports allowed to their role/branches, and authorized users can generate any report by hand from the web.
- **New initial report: weekly Operating Indicators** (Carlos's Power BI table) with Power BI traffic-light (semáforo) rules. Needs the table structure, the metrics and the semáforo thresholds/colors from the Power BI file before it can be built — to be gathered at the start of its phase.

## 2026-09-23 — Project scope and stack

- **Django app in its own repo** (`analisis_ejecutivos_FAR`), separate from the Wansoft ETL repo and from ControlPresupuestos_AP. Neither of those repos is touched by this project.
- **Roles are Django Groups**, plus `PerfilUsuario` for branch scope. Why: "configurable profiles" is satisfied by editing Group permissions in the admin without code, instead of hardcoding roles.
- **Port 8040**, prefix `/analisis_ejecutivos/`. 8020 was rejected: ControlPresupuestos_AP already uses it in production on the same app machine.
- **No `core` package; `.env` at `config/.env`.** The standalone scripts import the Wansoft repo's `core`; a second package with the same name would collide.
- **No fallback SECRET_KEY.** Unlike a dev convenience default, production must never be able to boot with a key committed to git; the app fails at startup if `DJANGO_SECRET_KEY` is missing.
- **Own database on the database server**, separate from report data. Report data is read from Odoo or the productive Wansoft MySQL (read-only).
- **Copilot integration deferred to the last phase.** Feasibility of calling a paid Copilot seat from a custom app is unverified; the analysis layer will be designed as interchangeable.
- **PDF library: reportlab** (already used by the proven generator) instead of ControlPresupuestos_AP's xhtml2pdf. Revisit only if the financial-report template proves easier in HTML/CSS.
- **Generated report files are not versioned** (`docs/Mensuales/**/*.pdf` gitignored): they are regenerable output. Revisit if report history must be auditable via git.

## Open questions

- Definition of the weekly commercial report for managers.
- Exact P&L sources for the investor and partner reports (budget from ControlPresupuestos_AP and Odoo; actuals from Odoo) — to be mapped in Phase 2/3.
- Dev database name and credentials for this app (must be created by the owner).
