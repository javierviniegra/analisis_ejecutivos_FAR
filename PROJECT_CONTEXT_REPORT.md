# PROJECT_CONTEXT_REPORT.md — Central de Reportes

Master continuity document for this project. Regenerated **in full** (never as patches) whenever the owner asks for a chat handoff. **Read this before anything else if you are picking the project up in a fresh chat.**

Last generated: 2026-09-30. Repo: https://github.com/javierviniegra/analisis_ejecutivos_FAR.git (branch `main`, last code commit `6919853`). 138 tests, all passing.

---

# 0. Permanent handoff rule (owner's instruction — very important)

Whenever the owner says the context window is over / asks to move to another chat, do ALL FOUR of these, every time, without being reminded:

1. **Regenerate this `PROJECT_CONTEXT_REPORT.md` in full** (English).
2. **Write the handoff prompt** (Spanish, to paste into the new chat; keep it also in Section 13).
3. **Give the new chat's title**, format `FONDA (Central de Reportes): Chat N: <short description>`. The old "Paso N" numbering was inherited from another project and was dropped on 2026-09-30 (owner); this project's chats are counted on their own (the next one is **Chat 4**).
4. **Commit and push** to git if there is anything uncommitted (English commit message; never push secrets or the owner's real financial files).

Also: **stop the web server** of the project (port 8040; `Get-NetTCPConnection -LocalPort 8040` then stop the owning process). The owner switches chats only when less than ~20% of the context remains; do not push early handoffs.

---

# 1. What this project is

**Central de Reportes** (Django app `central`; repo keeps the old name `analisis_ejecutivos_FAR`) is Grupo Fonda Argentina's *library of reports plus automations*, served **on demand** (the user picks branches — one, several, all — and any period: week, month, bimester, quarter, semester, year or free range) and by **schedule** (each automation bound to exactly ONE period kind). Outputs: **PDF and/or Excel**, downloaded from the web today; scheduled email later (Phase 5). Sources, all **read-only**: the Wansoft MySQL warehouse (now with the unified Odoo layer), the ControlPresupuestos_AP database, Odoo (XML-RPC), and later Buk (payroll API). A Copilot "analyst" is deliberately last.

**All report text is produced by fixed rules in Python** (`central/motor/lectura.py`, `notas.py`) from the report's own numbers — no AI, no external service (the owner verified this on 2026-09-29).

Branding: Fonda Argentina template (logo badge, rounded frame, watermark; PDF green `#10564E`; UI green `#035953`, dark `#023f3b`, cream `#f0e9d8`).

---

# 2. Critical environment notes — READ FIRST

- **Project path:** `C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\AnalisisRestaurantesBI\Reportes\Analisis Ejecutivos`. The old `...\Desktop\...` path is dead (OneDrive redirection). **The harness shell resets its cwd to that dead path after every command → always `cd` to the real path or use absolute paths.** Git-Bash uses `/c/...`.
- **Sibling repos — NEVER modify them** (read only): `Wansoft/Jupyter Notebooks/Python Files` (Wansoft ETL pipeline; its `docs/data-access-guide/` is the consumer guide for the databases and its `docs/production-cutover-runbook.md` the cutover plan) and `ControlPresupuestos_AP`.
- **Venv:** `.venv` (Python 3.13, Django 4.2). Run `.venv/Scripts/python.exe manage.py ...`.
- **Secrets only in `config/.env`** (gitignored); `config/.env.example` documents every variable with blank placeholders. `.env` holds: app DB (dev = local XAMPP MariaDB, root, db `analisis_ejecutivos_dev`), **`FUENTES_ENV=prod`** (the app runs in dev but reads the PRODUCTION sources, read-only), `WANSOFT_DB_*` (prod credentials copied from the Wansoft repo's .env — the pipeline's account `wansoftuser`, which CAN write; sessions are read-only by construction), `PRESUPUESTOS_DB_*` (db `presupuestos_ap`, also a writing account), **`ODOO_*`** (copied from the Wansoft .env). To be replaced by the dedicated read-only user `central_reportes` (Section 9).
- **Reading `wansoft_prueba` (the rehearsal copy with the NEW schema) without touching `.env`:** prefix the command with `WANSOFT_DB_NAME=wansoft_prueba` (`load_dotenv` does not override existing variables). The dev server has been run that way: `WANSOFT_DB_NAME=wansoft_prueba .venv/Scripts/python.exe manage.py runserver 8040 --noreload` (background). With `--noreload`, restart it after code changes.
- **Port 8040** (dev and prod; not 8000/8010/8020). Production prefix `/central_reportes/`.
- **Owner delegated starting/stopping the dev server** to Claude: start it when there is something to see and always tell the owner the URL and what to look at.
- **Console encoding:** Windows cp1252; commands printing arrows reconfigure stdout to UTF-8; use `PYTHONIOENCODING=utf-8`.
- **Editing quirks:** very long heredocs in one Bash call can fail to parse → write a patch script with the Write tool into the scratchpad and run it. Python patch scripts inside heredocs turn `"\\n"` into real newlines in f-strings — use `chr(10)` or the Edit tool. Accented text sometimes breaks exact-match edits; anchor on ASCII.
- **PDF preview without poppler:** `pypdfium2` installed in the session scratchpad (`--target`), not in the project.
- The auto-mode permission classifier occasionally gives no verdict; just retry once.

---

# 3. Working style agreed with the owner

- Roadmap first, stepwise approval; small explained blocks; **commit only after the owner approves the block**; surface concrete numeric tradeoffs and follow the owner's choice.
- README and `docs/DECISIONS.md` updated **in the same commit** as any change of behaviour/structure/decision. Commits and docs in English (chat in Spanish). Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Validate against real data before delivering** and report data errors honestly (many were found this way — Section 8). Show real outputs (PDF pages rendered to PNG, Excel) to the owner.
- Do not commit `scripts/build_tendencia_grupo_centro.py` or `docs/Especiales/` (another session's work) nor `docs/Ejemplos/` (owner's real files, gitignored).

---

# 4. Current state (what exists and works, dev)

**Apps:** `cuentas` (`Sucursal` with cross-system ids — `wansoft_subsidiary_id`, `wansoft_ticket_nombre` = the data guide's short key / `company_source_key`, `odoo_company_id`; `PerfilUsuario` branch scope; helpers `sucursales_de(user)`, `puede_generar(user)`; commands `crear_perfiles`, `cargar_sucursales`) and `central` (catalog, engine, outputs, web).

**Roles (Django Groups, deny-by-default report access):** Director, Administrador general, Gerente, Usuario, **Nominista**, **CEDIS**, **Contabilidad**. A report with no profile is visible only to staff. A user can have several categories by being in several groups.

**Catalog categories (owner, 2026-09-30):** Marca (was Comercial), Sucursales (gerentes), Inversionistas (executive + investors + partners), CEDIS (Bodegón), Nómina / RH, Contabilidad, Inventarios. (Operativo, Ejecutivo, Socios, Financiero, Compras were removed; migrations 0004–0008 convert rows.) The catalog page **filters by category**, offering only the user's categories.

| Report (clave) | Category | Profile | State |
|---|---|---|---|
| comercial-semanal-gerentes | Sucursales | Gerente | **implemented** (PDF + Excel, web) |
| indicadores-operativos-semanal | Sucursales | Gerente | pending (Power BI table + semáforo rules) |
| oc-bodegon-empanadas-modificaciones | CEDIS | CEDIS | **implemented** (Excel, web) |
| oc-bodegon-empanadas-por-hora | CEDIS | CEDIS | **implemented** (Excel, web) |
| incidencias-nomina | Nómina / RH | Nominista | pending (Buk API token + docs) |
| resumen-ejecutivo-sucursal, inversionistas-corto-mensual, financiero-operativo-socios-mensual | Inversionistas | — | pending (monthly exec PDF still a standalone script in `scripts/`) |
| rentabilidad-plataformas-mensual | Marca | — | pending definition |

**Web:** catalog → report page → "Generar reporte" (`/reportes/<clave>/generar/`): branches (only the user's, validated server-side), period kind + date or free range (≤366 days), per-branch/consolidated per the report's `alcance`, format PDF/Excel/both (as the report admits); several branches per branch always ask (no default) one file vs one file per branch; several files → .zip. The screen shows which databases it reads ("Datos de: Wansoft `...` · Presupuestos AP `...`"). Generators registered in `central/generadores.py`.

**Commercial report (`central/motor/reporte_comercial.py` assembles everything once):**
- Page 1: title; **Lectura** (rule-based sentences: gross sales vs previous and vs last year; driver traffic vs check; controls up & ≥0.5% of net; mix/channel moves >2 pp; **both costs vs the 38.0–39.9% target** in one sentence; Costo de Ventas over prorated budget); indicators table (Ventas, Mezcla, Control, **Costo**) with arrow columns; two charts; notes about the period's data.
- Page 2 **Detalle**: per branch for consolidated (sales, var, guests, check, **costo total % and costo facturado %** with traffic lights, total row) or per day/7-day block/month for a branch (no previous-period pairing in a month); then **"Reglas y umbrales del reporte"** in two columns.
- Excel: Resumen, one sheet per chart (native Excel chart), Detalle, Notas.
- `probar_reporte <branches|todas> --tipo ... [--consolidado] [--graficas DIR] [--pdf DIR] [--excel DIR]` prints and writes outputs.

**CEDIS reports (`central/motor/reporte_cedis.py`, `fuentes/odoo.py`, `salidas/excel_cedis.py`):** provider side (El Bodegón / Las Empanadas sales orders, from each provider's Odoo start) so **every branch** appears; orders coming from a branch purchase order are read from that PO (branch counted from its Odoo purchases start, read live from Wansoft `dim_company_analytical`); the rest from the sales order, mapped to a branch by **`ClienteCedis`** (admin table, seeded by `cargar_clientes_cedis`; delivery address wins over customer); changes after confirmation only (quantity notes, extra/additional lines, amount tracking), **"Hecho por" Sucursal/CEDIS** (Odoo user's main company), origin per order; two definitions of "modified" as the owner's originals; Mexico City = UTC-6. Validated against the owner's Excel of 2026-09-23 (same orders; same figures with the same cut).

**Source checks:** `verificar_fuentes [--hoy] [--sin-tickets]` (schema vs `COLUMNAS_REQUERIDAS` declared next to each query, write rights of the account, cutover migration applied, freshness per branch). `deploy/sql/create_central_reportes_readonly_user.sql` (SELECT-only user for `wansoft` + `presupuestos_ap`, run by the owner).

Phases: 1 users/roles ✔ dev; 2 catalog ✔ dev; 3 engine/outputs ✔ for commercial + CEDIS; 4 web on-demand ✔ dev; 5 automations (not started; commercial = weekly AND monthly); 6 Copilot (last); 7 production deploy (not started).

---

# 5. Business rules (do not re-litigate)

- **Week Mon–Sun;** same week last year = same ISO week of the previous ISO year. **Operating day:** a cash closing before 14:00 belongs to the previous day. **Duplicate closings** (same day, same totals, different times) counted once — still needed after the cutover's unique key `(subsidiary_id, fecha_corte)`.
- **Arrows ±1% (±1 pp for shares);** **s/c** no data; **s/cf** when either period has data on <90% of expected days. **Comparable branches:** a branch without ≥90% data in the comparison period leaves both sides of that comparison (notes name it).
- **Month charts measure calendar months:** per-day chart alone + 12-month trend vs last year (new branches included, noted; source gaps — Nov–Dec 2024 Odoo pilot — leave both years of that month; month in progress compared month-to-date).
- **Gross sales** in charts and the Lectura headline; table shows gross and net; cost percentages over **net** sales.
- **Cost target (owner): 38.0–39.9% of net sales per week and month** — green; <38% orange (bought too little / not captured); ≥40% red (bought too much). Two costs shown and named: **Costo total (Wansoft/Odoo)** = `CostoTotal − COALESCE(CostoDeConsumo,0)` (data guide; week = `costeomensual_semanapyq` row captured the Monday after; month = last `costeomensual` row; bimester–year = sum of months; free range = not available; 0 = no data) and **Costo facturado (Presupuestos AP)** = invoiced (the cash flow). Consumption is booked unevenly. The receipt-based measure ("how much each branch receives per week") is **pending**: the unified purchase tables have no receipt date — to request in the Wansoft project.
- **Costo de Ventas real (Presupuestos AP) is preliminary until 10 days after the close of the period's month** (invoices keep being captured): comparisons s/cf, note with the final date. A budget is shown even with no invoices yet; % ejercido only where both exist.
- **Sales targets:** found only for 2025 (SharePoint BI_Fonda scorecards, 4 levels) → no targets for now; pending task when 2026 targets exist.
- Multi-branch behaviour per report (`alcance`).

---

# 6. Wansoft cutover (Thursday 2026-10-01) — what to do

The live `wansoft` gets the new schema (41 tables + views, unique keys) and the new daily pipeline (01:30). The DB keeps its name, so this app's config does not change. The Wansoft runbook validates the cutover **against this app's commercial report**. Checked on `wansoft_prueba`: the commercial report needs no code change; the new pipeline is more complete (e.g. Sunday closings the legacy loader missed). CEDIS needs `dim_company_analytical`, which only exists after the migration. Puebla/CentroMyJ costs (0 today) are backfilled at the cutover (runbook step 3d).

**Steps for us on Thursday:** (1) owner runs `deploy/sql/create_central_reportes_readonly_user.sql` as root after the migration and puts `central_reportes` in `WANSOFT_DB_*` and `PRESUPUESTOS_DB_*` of `config/.env`; (2) run `verificar_fuentes` against `wansoft` (expect all PASS; no WARN about write rights); (3) generate the commercial report (week 39 and September, consolidated and per branch) and CEDIS workbooks from live `wansoft`; compare with the `wansoft_prueba` figures; confirm Puebla/CentroMyJ now have cost; (4) confirm Isabel, San Jerónimo and Vía Vallejo appear in CEDIS from 2026-10-01 once the pipeline flips them in `dim_company_analytical`.

---

# 7. Decisions log

Full text, newest first, in `docs/DECISIONS.md` (read it). Highlights of 2026-09-24..30: comparable branches; batched queries; month charts; gross sales; source gaps; Excel; web screen + delivery rule; read-only user + `verificar_fuentes`; preliminary cost; catalog by area + profiles; cost target and two costs; two-page PDF; CEDIS (provider side, `ClienteCedis`, who changed); category filter; payroll report skeleton.

---

# 8. Errors found and corrected (learn from these)

1. Metepec/Versalles ticket detail searched under wrong names (they have detail from 2026-08-21).
2. August 2026 executive PDFs summed duplicate closings (3 branches, ~$337k) — regenerate when the monthly report moves to the engine.
3. A `git revert` of a commit that added files deleted them from disk.
4. ControlPresupuestos_AP has no sales budget.
5. Real Costo de Ventas returned $0.00 when no records → now None.
6. La Esquina Coyoacán lost its budget when no invoice was recorded yet → budget shown independently.
7. The daily cost table includes consumption; the official "Costo Total" subtracts it (Isabel Aug 38.5% vs 35.2%).
8. **Odoo paging stopped at the first short page and lost 10,469 of 17,611 messages** → page until an empty page, de-duplicate by id.
9. `odoo_company_migration_policy.operational_start_date` is now the COST switch date (2026-10-01), not the purchases start — use `dim_company_analytical` for purchases.
10. A stale chart image was shown to the owner once — always regenerate before showing.

---

# 9. Risks and open items

- **Accounts:** the app still uses writing accounts (Wansoft ETL `wansoftuser`, the Presupuestos app account, the pipeline's Odoo user) — sessions are read-only by construction (MySQL `SET SESSION TRANSACTION READ ONLY` + 120 s statement cap; Odoo client whitelists query methods). Switch to `central_reportes` (MySQL) and a read-only Odoo user.
- Large ticket table unindexed on (Sucursal, Fecha): batched queries; mix query per month; semester/year consolidated take minutes → a local monthly summary table before production on-demand.
- **Consolidated reliability rule per branch** (not only total): proposed after week 39 (8 missing Sundays read as 94% "reliable"); not built.
- **8 unassigned Odoo customers of the CEDIS** (no September orders): Grupo Hospitalario Rodiva, Inmobiliaria Ares Ríos, LCDP Restaurantes, Peralta y Lau, "Público En general", Tacos FA Fuentes, Tacos P y T, Universatil — ask the owner and set them in the admin ("Clientes de CEDIS").
- For CEDIS users to pick branches, their `PerfilUsuario` needs "todas las sucursales".
- No SMTP yet; production not deployed (`docs/PRODUCTION_SETUP.md` untested); `scripts/` still import the Wansoft repo's `core`.

---

# 10. Backlog / next steps (in order)

1. **Thursday 2026-10-01 cutover validation** (Section 6).
2. Owner answers: the 8 CEDIS customers; payroll period cut-offs (weekly paid Fridays; biweekly paid on the 14th and the day before month end).
3. **Buk payroll report** (`incidencias-nomina`) as soon as the owner gets the API token and docs: incidents as Buk provides them, per branch (map Buk areas to branches), Excel + PDF, read at generation time (personal data, no copy stored), Nominista only.
4. **Automations (Phase 5):** subscriptions (report, recipients, format, ONE period kind, schedule; commercial = weekly and monthly), dispatcher via Task Scheduler, SMTP in `.env`, send log.
5. Monthly executive report onto the engine (costs from `costeomensual` for every branch); regenerate the 3 August PDFs with duplicates.
6. Pending definitions: operating indicators (Power BI semáforos), platform profitability, investors/partners reports; receipt-based cost measure (needs receipt date from the Wansoft pipeline); 2026 sales targets; consolidated reliability per branch; local monthly summary table; Copilot; Phase 7 deploy.

---

# 11. How to run things

```
cd "C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\AnalisisRestaurantesBI\Reportes\Analisis Ejecutivos"
.venv\Scripts\python.exe manage.py test                                   # 138 tests (needs local MariaDB)
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py crear_perfiles
.venv\Scripts\python.exe manage.py cargar_sucursales
.venv\Scripts\python.exe manage.py cargar_catalogo
.venv\Scripts\python.exe manage.py cargar_clientes_cedis                  # reads Odoo
.venv\Scripts\python.exe manage.py verificar_fuentes
.venv\Scripts\python.exe manage.py probar_reporte todas --tipo semana --fecha 2026-09-23 --consolidado --pdf C:/temp/pdf
.venv\Scripts\python.exe manage.py runserver 8040 --noreload              # stop it when done
```
(Git-Bash: prefix `WANSOFT_DB_NAME=wansoft_prueba` to read the rehearsal copy.)

---

# 12. Files map (main)

`central/motor/`: `periodo(s).py`, `comparativos.py` (arrows, s/cf, cost traffic light), `metricas.py` (batched read, consolidation, comparables, costs), `tabla_comercial.py`, `lectura.py`, `notas.py`, `graficas.py` / `graficas_png.py`, `detalle.py`, `reporte_comercial.py`, `reporte_cedis.py`; `central/motor/fuentes/`: `conexiones.py`, `wansoft.py`, `presupuestos.py`, `odoo.py`, `verificacion.py`. `central/salidas/`: `pdf_comercial.py`, `excel_comercial.py`, `excel_cedis.py`. `central/generadores.py`, `forms.py`, `views.py`, `models.py` (`Reporte`, `ClienteCedis`). `deploy/sql/`. `docs/DECISIONS.md`, `docs/PRODUCTION_SETUP.md`.

---

# 13. HANDOFF PROMPT

**Paste this as the first message of the new chat:**

```
Continúo el proyecto FONDA "Central de Reportes": aplicación Django, biblioteca de
reportes + automatizaciones, a demanda (sucursales y cualquier periodo) y programada.
Repo: https://github.com/javierviniegra/analisis_ejecutivos_FAR.git
Carpeta: C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\
AnalisisRestaurantesBI\Reportes\Analisis Ejecutivos

Lee completo PROJECT_CONTEXT_REPORT.md (sobre todo Secciones 0, 2, 3, 5, 6, 9 y 10)
y luego docs/DECISIONS.md. Reglas clave:
- NO modifiques los repos hermanos (Wansoft ETL y ControlPresupuestos_AP); solo se leen.
  La guía de datos de Wansoft (docs/data-access-guide) y su runbook del corte son referencia.
- Claves solo en config/.env (placeholders en .env.example). La app lee las fuentes de
  producción en solo lectura (FUENTES_ENV=prod); para la base nueva de prueba antepón
  WANSOFT_DB_NAME=wansoft_prueba al comando.
- Roadmap y aprobación por bloque; bloques pequeños y explicados; commit solo con mi visto bueno.
- README y docs en el mismo commit; commits y docs en inglés.
- Tú levantas/apagas el servidor de pruebas (puerto 8040) y me avisas la liga.
- Al cambiar de chat: regenerar el reporte, prompt, título "FONDA (Central de Reportes):
  Chat N: ...", commit/push y apagar el servidor.
- El shell regresa a una ruta muerta (Desktop): usa cd a la ruta real o rutas absolutas.

Estado: reporte comercial terminado (PDF de 2 páginas con Detalle, Excel, pantalla web,
reglas de comparables y s/cf, dos costos con semáforo 38-39.9%, costo preliminar);
reportes de CEDIS terminados (Excel desde Odoo del lado del proveedor, todas las sucursales,
quién hizo cada cambio); catálogo por categorías con filtro y perfiles Gerente, CEDIS,
Contabilidad y Nominista; reporte de nómina (Buk) dado de alta, pendiente la API.
138 pruebas pasan.

Hoy/mañana: corte de Wansoft del jueves 1-oct (Sección 6): usuario de solo lectura
central_reportes, verificar_fuentes contra wansoft, generar reportes y comparar con
wansoft_prueba, confirmar costos de Centro y Puebla. Pendientes míos: asignar 8 clientes
de CEDIS sin sucursal y los cortes de los periodos de nómina. Después: Buk y automatizaciones.
```

**Suggested title for the new chat:** `FONDA (Central de Reportes): Chat 4: Corte de Wansoft, CEDIS y Buk`
