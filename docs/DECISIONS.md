# Decisions

Newest first. Each entry: what, why, and where it applies.

## 2026-09-23 — Data layer for the weekly commercial report (findings and rules)

- **Operating day of a cash closing:** `getglobalcashclosing.fecha_corte` is when the closing was done. A closing before 14:00 belongs to the PREVIOUS operating day (validated: 30/30 days of a full month match the ticket detail to the cent; unshifted only 8/30).
- **Duplicate closings exist in the source.** The same closing can be stored several times (same operating day, identical totals; e.g. three identical rows 13 s apart, or the previous night's closing re-issued the next noon). The engine counts one row per identical (day, totals). **Impact on the August 2026 executive PDFs already delivered:** they summed the table without deduplicating; 4 duplicate rows in 3 branches (San Jeronimo $152,228, Viaducto $110,188, Tepeyac $74,270; about $337k of $67.5M, 0.5%). Puebla not affected. Decision pending: regenerate those 3 PDFs with the deduplicated numbers.
- **Branch mapping across systems:** `Sucursal` now carries `wansoft_subsidiary_id`, `wansoft_ticket_nombre` and `odoo_company_id` (loaded by `cargar_sucursales`); no name matches across systems, so queries use these keys, never names.
- **Ticket detail coverage is partial for some branches** (added late, or none: Metepec, Versalles). Coverage (days with data out of 7) is returned so reports can flag partial data.
- **Presupuestos AP** is only active for the 7 Odoo-migrated branches; other branches have no budget block (None, never zero). Its "everything else" spread logic is reproduced (and tested) so numbers agree with its dashboard.
- **Read-only by construction:** every source connection runs `SET SESSION TRANSACTION READ ONLY`; production accounts must also be SELECT-only.
- **RISK before production use:** `getallordenesbyday_new_venta` is large and unindexed on (Sucursal, Fecha); on 2026-09-15 an ad-hoc query against the production copy hung for over an hour. Channel and mix queries filter on exactly those columns. Before pointing at production: check row count and indexes, run off-peak, and decide with the owner whether to request an index. Fine on the local dev copy.
- `manage.py probar_semana <branch> [date]` prints every input of the week from the sources, for verification.

## 2026-09-23 — Weekly commercial report for managers: definition

- **Content (all of it):** sales (gross and net), tickets, guests, average check and ticket; food/beverage mix and channel mix; cancellations, courtesies and discounts; sales by day of the week.
- **Comparisons:** previous week, same numeric week of the previous year, and weekly budget, each with an arrows column. Year-over-year is shown only for branches that have history.
- **Audience:** each manager receives only their own branch (one PDF per branch).
- **Resolved 2026-09-23:** week = Monday to Sunday. Channel comes from the Wansoft order type (`Restaurant`, `Para llevar`, `eCommerce`). Format approved: one page, standard Fonda template, a "Lectura de la semana" box, an indicators table (week / previous week / var / same week last year / var / target / % target) with arrow columns, and two charts (sales by day vs previous week; weekly sales vs same week last year).
- **Sales target: none for now.** ControlPresupuestos_AP only holds monthly *expense* budgets (categories Costo de Ventas and Gasto Operativo, 12 expense types); it has no sales budget, and that app is not modified by this project. The owner will define a KPI later to feed the target; until then the Meta / % Meta columns are omitted.
- **Added block: spend vs budget from ControlPresupuestos_AP** -- real Costo de Ventas spend of the week against the Costo de Ventas budget prorated by days (`GastoReal` vs `Presupuesto`), with its arrow. Read directly from that app's database (read-only); Odoo is not needed for this report.
- **Data sources for this report:** Wansoft warehouse (cash closing, order type, order detail) and the ControlPresupuestos_AP database, both MySQL, both read-only. Credentials only in `config/.env` (`WANSOFT_DB_*`, `PRESUPUESTOS_DB_*`, dev and prod); production must use SELECT-only accounts.
- **Arrows:** up-green if better, down-red if worse, grey `=` when the change is within +-1%. For cancellations, courtesies and discounts an increase is bad (inverted).
- **"Lectura de la semana" starts rule-based** (observations computed from the real numbers, nothing invented); the AI analyst (Copilot, last phase) will later rewrite the same box without changing the rest of the report.
- **Same week last year = same ISO week number of the previous ISO year.** If that year has no such week (week 53) there is no comparison ("sin comparativo"), never a substitute week.

## 2026-09-23 — Phase 2: report catalog

- **A report is data, not code:** `Reporte` rows describe category, periodicity, template, source, scope (per branch / consolidated), formats and state. The generator (Phase 3) and the sender (Phase 5) hang off this definition.
- **Deny by default:** a report with no profiles assigned is invisible to everyone except staff; a non-visible report answers 404 (not 403) so its existence is not disclosed. Access is granted explicitly per profile (Django Group) from the admin.
- **Seed command never overwrites:** `cargar_catalogo` only creates missing keys, so admin edits (profiles, notes, state) survive re-runs and deploys.
- Seeded reports: executive summary per branch, weekly commercial (undefined), short investor report, financial and operational report for partners (needs new template), the two Bodegon/Empanadas purchase-order Excel reports, weekly operating indicators (needs Power BI table + semaforo rules), monthly profitability by delivery platform (Uber, Didi, etc.; added 2026-09-23, definition pending: platform list, sales source, commissions/costs source, per-branch vs consolidated, profitability formula).

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
