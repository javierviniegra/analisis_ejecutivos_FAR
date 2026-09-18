# Analisis Ejecutivos

Branded executive branch reports (Ventas + Costos) for Grupo Fonda Argentina, generated from the Wansoft/Odoo analytical layer built in the sibling `Wansoft` project.

## Status

Report generator (PDF, all 19 branches) is built and validated for August 2026 — see `scripts/`. A Django web app (scheduled email delivery, in-browser dashboard, week/month/year on-demand generation, period-over-period comparisons) is planned as the next step; not started yet.

## Structure

- `scripts/` — standalone report-generation scripts (no Django yet). `build_executive_pdf_all.py` is the current standard generator (19 branches); `build_executive_pdf.py` and `build_executive_pdf_multi.py` are kept as historical/reference versions.
- `docs/Mensuales/<year>/<Spanish month name>/` — generated monthly PDF reports (gitignored — regenerated, not source).

## Cross-repo dependency (temporary)

`scripts/*.py` import `core.database.*` / `core.config.*` from the sibling `Wansoft` repo via a hardcoded absolute path (`WANSOFT_REPO_ROOT` near the top of each script). This only works because both repos live as sibling folders on this machine — not portable elsewhere. Meant to be resolved when the Django app is built (own connection module, or a proper shared package) rather than assumed permanent.

## Running the generator

Requires the Wansoft repo's local dev MySQL to be running (see that repo's own docs) and its `core/config/.env` populated. From `scripts/`, set `ANIO`/`MES_NUM` at the top of `build_executive_pdf_all.py` and run it — it creates `docs/Mensuales/<year>/<month>/` if needed and writes one PDF per branch there.
