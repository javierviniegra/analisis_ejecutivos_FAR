# PROJECT_CONTEXT_REPORT.md — Central de Reportes

Master continuity document for this project. Regenerated **in full** (never as patches) whenever the owner asks for a chat handoff. **Read this before anything else if you are picking the project up in a fresh chat.**

Last generated: 2026-09-24. Repo: https://github.com/javierviniegra/analisis_ejecutivos_FAR.git (branch `main`, last commit `dd7278c`).

---

# 0. Permanent handoff rule (owner's instruction — very important)

Whenever the owner says the context window is over / asks to move to another chat, do ALL FOUR of these, every time, without being reminded:

1. **Regenerate this `PROJECT_CONTEXT_REPORT.md` in full** (English).
2. **Write the handoff prompt** (Spanish, to paste into the new chat; keep it also in Section 12).
3. **Give the new chat's title**, format `FONDA (<short project>): Paso N[-M]: <short description>`. `FONDA` is a fixed prefix; the short project here is **Central de Reportes**; `N` continues the owner's running step count; `-M` is a sub-part when a step spans several chats.
4. **Commit and push** to git if there is anything uncommitted (English commit message; never push secrets or the owner's real financial files).

Also: **if a web server of the project is running, stop it** (check port 8040 and any `runserver`/`waitress` process of this project).

---

# 1. What this project is

**Central de Reportes** is a Django web application for Grupo Fonda Argentina: a *library of reports plus automations*, served **on demand** and by schedule. Working name history: "Analisis Ejecutivos" → renamed **Central de Reportes** on 2026-09-24 (Django app `central`). The GitHub repo keeps the old name `analisis_ejecutivos_FAR` (renaming it is the owner's call). The local folder is `...\AnalisisRestaurantesBI\Reportes\Analisis Ejecutivos\`.

It does three things:
1. **Show** report information to authorized users.
2. **Generate** reports as Excel, PDF or both, for **any branch selection (one, several, all) and any period** (week, month, bimester, quarter, semester, year, or free date range) chosen by the user.
3. **Send** reports by email to configurable recipients, format and schedule (daily/weekly/monthly/semiannual/annual). **An automation is bound to exactly ONE period kind**, defined per automation.

Data sources: Odoo, the productive Wansoft MySQL, and the ControlPresupuestos_AP database (all **read-only** for reports). A paid Copilot account is meant for an "analyst" feature, deliberately **last** (feasibility of calling a paid Copilot seat from a custom app is unverified; design the analyst layer to be interchangeable).

Executive reports use the standard Fonda Argentina branded template (logo badge, rounded frame, watermark, brand green `#10564E` in PDFs; UI green `#035953`, dark `#023f3b`, cream `#f0e9d8`, same look as ControlPresupuestos_AP).

---

# 2. Critical environment notes — READ FIRST

- **Project path (current, correct):** `C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\AnalisisRestaurantesBI\Reportes\Analisis Ejecutivos`. The old `C:\Users\JavierViniegra\Desktop\AnalisisRestaurantesBI\...` path is permanently dead (OneDrive folder redirection, ~2026-09-15). **The harness's shell resets its working directory to that dead path after every command → always `cd` to the real path or use absolute paths.** Windows Python wants `C:\...` paths; Git-Bash uses `/c/...`.
- **Sibling repos — NEVER touch them** (owner's explicit rule): `Wansoft/Jupyter Notebooks/Python Files` (restaurant-wansoft-zenput-etl-pipeline_FAR) and `ControlPresupuestos_AP` (presupuestos_semanales_AP_FAR). This project only reads from their databases and (temporarily) imports the Wansoft repo's `core` from the standalone scripts in `scripts/`.
- **Venv:** `.venv` inside the project (Python 3.13, Django 4.2.30). Run things as `.venv\Scripts\python.exe manage.py ...`.
- **All secrets live only in `config/.env`** (gitignored); `config/.env.example` documents every variable with blank placeholders. Never in code, SQL, docs or git. The `.env` is at `config/.env` (not `core/config/`) because this repo has no `core` package (the scripts import the Wansoft repo's `core`; two packages with that name would collide).
- **Dev setup:** local XAMPP MariaDB 10.4 on `localhost:3306`. Dev-only, owner-approved exception: the app connects as local `root` (`EJECUTIVOS_DB_USER_DEV=root`). Never in production. Dev database: `analisis_ejecutivos_dev`, created by `scripts/setup_dev_db.py` (reads `.env`, refuses non-local hosts).
- **Port 8040** (dev and prod). Not 8000 (XAMPP), not 8010/8020 (ControlPresupuestos_AP). Production prefix behind the Apache proxy: `/central_reportes/`.
- **MariaDB strict mode** is enabled in the app's DB connection.
- **Console encoding:** Windows consoles default to cp1252 and cannot print arrows (▲▼); management commands that print them reconfigure stdout to UTF-8.
- **Editing quirk:** files that contain accented characters sometimes fail exact-match edits; anchor edits on ASCII-only text. Large multi-file heredocs in one Bash call sometimes fail to parse; use several smaller calls or the Write tool.

---

# 3. Working style agreed with the owner

- **Roadmap first, stepwise approval.** Propose the design (mock, list of blocks), get an explicit yes, then build in small explained blocks. No big silent scaffolds. Surface concrete numeric tradeoffs on data-definition ambiguities, then follow the owner's explicit choice.
- **Always update README and `docs/` in the same commit** as any change of behaviour, structure, setup or decision. Commit messages and docs in English (chat in Spanish). Commits end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- **Report data errors honestly** (this session found and corrected two of my own earlier mistakes — see Section 8). Cross-check a metric across all branches before delivering; surface anomalies instead of smoothing them.
- The owner asks to **stop the web server** at the end of a working session.
- Do not commit the owner's real financial examples (`docs/Ejemplos/` is gitignored) nor another session's work (`scripts/build_tendencia_grupo_centro.py` and `docs/Especiales/` are not mine: left untracked/ignored).

---

# 4. Current state (what exists and works)

Repo layout:
- `config/` Django project (env-driven settings; `SECRET_KEY` has NO fallback on purpose).
- `cuentas/` — `Sucursal` (with cross-system ids: `wansoft_subsidiary_id`, `wansoft_ticket_nombre`, `odoo_company_id`), `PerfilUsuario` (branch scope), commands `crear_perfiles` (4 roles as Django Groups: Director, Administrador general, Gerente, Usuario; custom permissions `ver_reportes`, `generar_reportes`, `gestionar_envios`, `gestionar_usuarios`) and `cargar_sucursales` (19 branches; idempotent, never overwrites filled fields).
- `central/` — the report library: `Reporte` model (category, periodicity, template, source, scope `por_sucursal|consolidado|ambos`, formats, state, allowed profiles = Groups), admin, catalog/detail pages, command `cargar_catalogo` (8 reports; idempotent, never overwrites admin edits; new ones start with no profiles). **Deny-by-default:** a report with no profiles is visible only to staff; a non-visible report returns 404.
- `central/motor/` (pure, tested engine building blocks):
  - `periodos.py` (Monday–Sunday weeks, previous week, same ISO week last year — `None` for week 53, monthly-budget proration by days) and `periodo.py` (**`Periodo`**: week/month/bimester/quarter/semester/year/free range, each with `anterior()` and `mismo_periodo_anio_anterior()`, plus `etiqueta()` and `de_fecha()` for automations).
  - `comparativos.py` (arrow rule: ▲ green better / ▼ red worse / `=` grey within ±1%; inverted where up is bad; `s/c` when there is nothing to compare).
  - `metricas.py` (`Metricas` for one branch or consolidated, explicit coverage of cash-closing days and ticket-detail days), `tabla_comercial.py` (the indicators table; shares compared in percentage POINTS, threshold 1 pt; neutral rows always grey), `formato.py` (display formatting).
  - `fuentes/`: `conexiones.py` (read-only connections, `SET SESSION TRANSACTION READ ONLY`), `wansoft.py` (deduplicated daily cash closings by operating day, channel mix, food/beverage mix, detail coverage), `presupuestos.py` (Costo de Ventas budget vs real from ControlPresupuestos_AP, reproducing its "everything else" split).
- Management commands for verification: `probar_reporte <branches|todas> --tipo <kind> [--fecha|--desde --hasta] [--consolidado]` prints the indicator table from the real sources.
- `scripts/` standalone PDF generators (pre-Django, still the only thing that produces the monthly executive PDFs): `build_executive_pdf_all.py` (19 branches, current), `build_executive_pdf.py`, `build_executive_pdf_multi.py`, `build_puebla_scorecard.py`, `build_cost_chart.py`, `setup_dev_db.py`; brand background `logo_extract_0.jpeg`. They import `core.database.*` from the Wansoft repo via a hardcoded absolute path (`WANSOFT_REPO_ROOT`) — temporary.
- `docs/`: `DECISIONS.md` (all decisions, newest first), `PRODUCTION_SETUP.md` (proxy vhost, `.env`, run — written ahead of deployment, nothing executed), `Ejemplos/` (owner's real examples, gitignored), `Mensuales/<year>/<Month>/` (generated PDFs, gitignored; the 19 August 2026 PDFs live here).
- **51 tests, all passing** (`manage.py test`, needs the local MariaDB).

Phases: 1 skeleton/users/roles/login **done (dev)**; 2 report catalog **done (dev)**; 3 generation engine **in progress** (data layer + indicators table done, PDF not yet); 4 web viewing, 5 scheduled email, 6 Copilot analyst, 7 production deploy **not started**.

Pending owner-side action: nothing blocking. (The owner created their superuser and used the app locally; server currently stopped.)

---

# 5. The reports (catalog)

`resumen-ejecutivo-sucursal` (monthly executive PDF per branch — exists as script), `comercial-semanal-gerentes` (**being built now**), `inversionistas-corto-mensual` (example PDF in `docs/Ejemplos`, not versioned; budget from ControlPresupuestos_AP and Odoo budgets, actuals from Odoo), `financiero-operativo-socios-mensual` (needs a NEW template with Fonda colors/logo; content undefined), `oc-bodegon-empanadas-modificaciones` and `oc-bodegon-empanadas-por-hora` (weekly Excel; examples generated in the Wansoft repo under `reports/ordenes_compra_proveedores_internos/`), `rentabilidad-plataformas-mensual` (Uber/Didi/etc.; definition pending: platform list, sales source, commissions/costs source, formula), `indicadores-operativos-semanal` (Carlos's Power BI table with semáforos; needs the table, metrics and semáforo rules from the Power BI file).

## The weekly commercial report for managers — approved design (build in progress)
- **Content (all blocks):** sales gross and net, tickets, guests, average check and ticket; food/beverage mix and channel mix (Wansoft order type `Restaurant`→salón, `Para llevar`→llevar, `eCommerce`→plataformas); cancellations, courtesies, discounts; sales by day; plus a **Costo de Ventas real vs budget** block from ControlPresupuestos_AP.
- **Comparisons:** previous period and same period last year, each with an arrow column. Year-over-year only when data exists (`s/c` otherwise).
- **No sales target for now** (ControlPresupuestos_AP only has monthly *expense* budgets; a KPI to feed a target will be defined later by the owner). Meta / % Meta columns are omitted until then.
- **Audience:** each manager receives only their own branch (one PDF per branch).
- **Format approved (one page, standard Fonda template):** a "Lectura de la semana" box (rule-based observations computed from real numbers, nothing invented; the AI analyst will later rewrite the same box), the indicators table, and two charts (sales by day vs previous period; period sales vs same period last year). **Owner's on-demand generalization:** the report is not "weekly-only": the user picks branches and the period kind.
- **Open question asked, not yet answered:** for long periods (year, semester), should the "sales by day" chart automatically group by week or by month? (Proposal: yes, automatically.)

---

# 6. Business rules and findings (do not re-litigate)

- **Week = Monday–Sunday.** Same week last year = same ISO week number of the previous ISO year; none if that year has no such week. Months are calendar months. Monthly budgets are prorated by days (a week spanning two months blends both months' daily rates).
- **Operating day of a cash closing:** `getglobalcashclosing.fecha_corte` is when the closing was done; a closing **before 14:00 belongs to the previous operating day**. Validated: 30/30 days of a full month match the ticket detail to the cent (unshifted: only 8/30).
- **Duplicate closings exist in `getglobalcashclosing`** (same operating day, identical totals — e.g. three identical rows 13 s apart, or the previous night's closing re-issued next noon). The engine counts one row per identical (day, totals). **Impact on the delivered August 2026 PDFs** (they summed without dedup): 4 duplicate rows in 3 branches — San Jerónimo $152,228, Viaducto $110,188, Tepeyac $74,270 (~$337k of $67.5M, 0.5%); Puebla unaffected. **Decision:** not regenerated yet; regenerate those 3 when the monthly report runs on the new engine.
- **Ticket detail (`getallordenesbyday_new_venta/_detalleventa`) coverage is partial for several branches** (loaded late). Metepec and Versalles only have detail from 2026-08-21. Coverage must be returned and flagged, never assumed.
- **Percent-of-sales convention (executive PDFs):** cost percentages are against **venta neta (sin IVA)**.
- **Costs routing (executive PDFs, owner's rule 2026-09-18, supersedes the old per-branch split in the Wansoft repo's `companies.py`):** Costo de Productos Vendidos from Odoo (`account.move.line`, account code like `501`, `parent_state='posted'`, no move_type filter, XML-RPC call MUST pass `context={'allowed_company_ids': [id]}` or `code` returns False) if the branch is Odoo-sourced, else Wansoft `costeomensual`; **Merma, Cortesías, Cancelaciones, Anulaciones always Wansoft** (Merma from `costeomensual`, the others from `getglobalcashclosing`), valued at sale price and shown apart from the Costo Total. Metepec's low cost % (10.34%) is an accepted operational limitation (franchise does not upload purchases): present as-is, never "fix".
- **Cross-system branch names never match** — use the ids on `cuentas.Sucursal`; each table must be searched under its own name (the cash-closing name is not the ticket-table name).
- **ControlPresupuestos_AP** is active only for the 7 Odoo-migrated branches (Acoxpa 7, Antenas 9, Tepeyac 10, Oceanía 11, Coyoacán 36, Puebla 34, CentroMyJ 35 = Odoo company ids); other branches have no budget block (`None`, never zero). Its real spend is keyed by the Monday of the week of goods receipt (PO-linked) or payment, so week-to-week swings are normal (e.g. Puebla $13k vs $319k).
- **`Costo de Ventas real` is shown even when no budget is captured**; `% ejercido` only uses branches that have both.
- **Multi-branch behaviour is dictated by each report** (`alcance`: por sucursal, consolidado, ambos) — no global rule.

---

# 7. Decisions log (summary — full text in `docs/DECISIONS.md`)

Django app in its own repo; roles = Django Groups + branch scope model; port 8040; own DB on the separate database server in production (a dedicated restricted user, never root); read-only report sources; secrets only in `.env`; dev root exception; test-first rollout on the owner's PC, production only after a few reports are validated, with a scheduled script that updates the code daily and restarts the app (Phase 7, analogous to ControlPresupuestos_AP's `deploy/update.ps1`); per-user report views and manual generation; reportlab (not xhtml2pdf) for PDFs; generated PDFs are not versioned; Copilot last; name Central de Reportes/`central`; on-demand open periods.

---

# 8. Errors found and corrected (learn from these)

1. **Wrong claim: "Metepec and Versalles have no ticket detail."** False — searched under wrong names (Tollocan/Exhibimex). They have partial detail from 2026-08-21. Corrected in `docs/DECISIONS.md` and in the assistant's memory. Their August PDFs show N/D where partial data (with `*`) was possible.
2. **August PDFs did not deduplicate cash closings** (Section 6). Found while validating the operating-day rule.
3. Earlier this session: a `git revert` of a commit that ADDED new files also deleted them from disk (recovered from history via `git show <commit>:path`); mind this when reverting commits that add files.
4. ControlPresupuestos_AP has **no sales budget** (only expense budgets), contradicting the owner's assumption; verified against its database read-only, then the design changed (no target for now).

---

# 9. Risks and open items

- **PRODUCTION QUERY RISK:** `getallordenesbyday_new_venta` is large and unindexed on (Sucursal, Fecha); on 2026-09-15 an ad-hoc query against the production Wansoft copy hung for over an hour. Channel/mix/coverage queries filter exactly on those columns. Before pointing at production: check row count and indexes, run off-peak, decide with the owner whether to request an index. Fine on the local dev copy. Consolidating all 19 branches × 3 periods takes ~56 s in dev (per-branch queries); batching into one query is a known optimization.
- Production DB accounts for report sources must be SELECT-only at the database level.
- `scripts/*.py` depend on the Wansoft repo via `WANSOFT_REPO_ROOT` (temporary; to be replaced by this app's own data access).
- Production nothing deployed; `docs/PRODUCTION_SETUP.md` is untested.
- No email/SMTP configured (console backend); no credentials yet — add `SMTP_*` placeholders to `.env.example` when Phase 5 starts.
- Open owner-side items: weekly-target KPI (later), Power BI table and semáforo rules for the operating-indicators report, definition of the platform-profitability and partner-financial reports, whether to regenerate the 3 affected August PDFs, whether to rename the GitHub repo.

---

# 10. Backlog / next steps (in order)

1. **Finish the commercial report (Phase 3):** "Lectura de la semana" rule-based observations (from the indicators table); the two charts (chart granularity by period length: day ≤ ~31 days, week for medium, month for long — ask/confirm); **PDF generator** on the Fonda template (reuse `scripts/logo_extract_0.jpeg` background and the reportlab helpers in `scripts/build_executive_pdf_all.py`); one PDF per branch and/or consolidated per the report's `alcance`; then an Excel output.
2. **Web UI for on-demand generation (Phases 3–4):** pick report, branches (one/several/all), period kind and value (incl. free range), format; per-user view restricted to their branches/reports; consolidated vs per-branch as each report dictates.
3. **Automations (Phase 5):** subscription model (report, recipients per branch, format, ONE period kind, schedule), a dispatcher run by Task Scheduler (like ControlPresupuestos_AP), SMTP config, send log.
4. Regenerate the 3 affected August PDFs via the new engine once the monthly report is ported.
5. Remaining reports (investors short, partners financial with new template, OC Excel, platform profitability, operating indicators).
6. Copilot analyst layer (last); Phase 7 production deployment (daily auto-update script + restart).

---

# 11. How to run things

```
cd "C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\AnalisisRestaurantesBI\Reportes\Analisis Ejecutivos"
.venv\Scripts\python.exe manage.py test                       # 51 tests
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py crear_perfiles
.venv\Scripts\python.exe manage.py cargar_sucursales
.venv\Scripts\python.exe manage.py cargar_catalogo
.venv\Scripts\python.exe manage.py probar_reporte puebla --tipo semana --fecha 2026-09-14
.venv\Scripts\python.exe manage.py probar_reporte todas --tipo mes --fecha 2026-08-15 --consolidado
.venv\Scripts\python.exe manage.py runserver 8040             # stop it when done (Ctrl+C / kill the process)
```

---

# 12. HANDOFF PROMPT

**Paste this as the first message of the new chat:**

```
Continúo el proyecto FONDA "Central de Reportes" (antes "Análisis Ejecutivos"): una
aplicación Django que es una biblioteca de reportes + automatizaciones, a demanda
(el usuario elige sucursal(es) y periodo abierto: semana, mes, bimestre, trimestre,
semestre, año o rango libre) y programada (cada automatización usa UN solo tipo de
periodo). Repo: https://github.com/javierviniegra/analisis_ejecutivos_FAR.git
Carpeta: C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\
AnalisisRestaurantesBI\Reportes\Analisis Ejecutivos

Lee completo PROJECT_CONTEXT_REPORT.md en la raíz del repo antes de responder
(sobre todo Secciones 0, 2, 3, 6, 9 y 10) y luego docs/DECISIONS.md. Reglas clave:
- NO toques los repos hermanos (Wansoft ETL y ControlPresupuestos_AP); solo se leen sus bases.
- Todas las claves solo en config/.env (con placeholders en .env.example).
- Trabajamos por roadmap y aprobación paso a paso, en bloques pequeños y explicados.
- README y docs actualizados en el mismo commit; commits y docs en inglés.
- Al final de cada sesión: apagar el servidor web, y cuando te pida cambiar de chat
  haz siempre las 4 cosas: (1) regenerar PROJECT_CONTEXT_REPORT.md, (2) prompt de
  indicaciones, (3) nombre del nuevo chat, (4) commit y push si hace falta.
- El shell de este entorno regresa siempre a una ruta muerta (Desktop): usa cd a la
  ruta real o rutas absolutas.

Estado: Fase 1 (usuarios/roles/login) y Fase 2 (catálogo) hechas en dev; Fase 3 en
curso: ya está la capa de datos de solo lectura (Wansoft y Presupuestos AP), el
modelo de periodo abierto, las métricas/consolidación y la tabla de indicadores con
flechas (probar_reporte imprime la tabla con datos reales); 51 pruebas pasan.
Siguiente: el reporte comercial a demanda — caja "Lectura de la semana" por reglas,
las dos gráficas (la granularidad de "venta por día" cambia con la longitud del
periodo: día/semana/mes; te propuse hacerlo automático, pendiente de confirmar) y el
PDF con la plantilla Fonda (un PDF por sucursal y/o consolidado según lo dicte el
reporte); después la pantalla web de generación a demanda y las automatizaciones.

Recordatorios importantes: el cierre diario de Wansoft trae cierres duplicados y el
día operativo es "cierre antes de las 14:00 = día anterior" (el motor ya lo maneja;
los PDF de agosto de San Jerónimo, Viaducto y Tepeyac quedaron con duplicados y se
regeneran cuando el mensual pase al motor nuevo). Metepec y Versalles SÍ tienen
detalle de tickets, parcial desde el 21-ago. No hay meta de venta por ahora.
Antes de apuntar a producción hay que revisar el riesgo de consultas a la tabla
grande de tickets (Sección 9).
```

**Suggested title for the new chat:** `FONDA (Central de Reportes): Paso 25-2: PDF del reporte comercial y generación a demanda`

---

# Permanent Rule

Regenerate this document in full (never as patches) when the owner asks for a chat handoff, a major step closes, or the conversation gets very long. In that case do the four things of Section 0 (this report, the handoff prompt, the new chat title, commit and push) and stop any running web server. **Language:** this document, all commit messages and everything pushed to GitHub in this project are written in English, even though the conversation with the owner is in Spanish.
