"""
Scorecard mensual Puebla (Agosto y Septiembre 2026) -- genera el .xlsx.

Fuentes:
- Ventas: getglobalcashclosing (Wansoft, cierre diario) -- cobertura completa.
- Meseros / Mix Alimentos-Bebidas / Consumo Salon: getallordenesbyday_new_venta
  y _new_detalleventa (Wansoft) -- cobertura parcial para Puebla (ver notas).
- Cancelaciones / Cortesias: getglobalcashclosing (Wansoft, cierre diario).
- Costo de Productos Vendidos / Merma / Variaciones de Inventario / COGS total:
  Odoo en vivo, account.move.line, cuentas contables 501.xx, company_id=34
  (FONDA ARGENTINA PUEBLA) -- replica exacta de "Reportes analiticos" de Odoo
  Contabilidad, validada contra captura de pantalla del usuario.

Este script solo LEE (Wansoft vía MySQL dev, Odoo vía XML-RPC read-only).
No escribe nada en ninguna base de datos.
"""

import sys
import os
from pathlib import Path

# Cross-repo dependency: see build_executive_pdf_all.py for the full note.
WANSOFT_REPO_ROOT = r"C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\AnalisisRestaurantesBI\Wansoft\Jupyter Notebooks\Python Files"
sys.path.insert(0, WANSOFT_REPO_ROOT)
os.environ["ENV"] = "dev"

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from core.database.mysql import get_mysql_connection
from core.database.odoo import get_odoo_connection

OUT_PATH = Path(__file__).resolve().parent / "Scorecard_Puebla_Ago_Sep_2026.xlsx"

# ---------------------------------------------------------------------------
# 1. Odoo -- desglose de costo, cuenta 501.xx
# ---------------------------------------------------------------------------


def get_odoo_cost_breakdown():
    uid, models, db, password = get_odoo_connection()
    company_id = 34  # FONDA ARGENTINA PUEBLA
    ctx = {"allowed_company_ids": [company_id]}

    accounts = models.execute_kw(
        db,
        uid,
        password,
        "account.account",
        "search_read",
        [[["company_ids", "in", [company_id]], ["code", "like", "501"]]],
        {"fields": ["id", "code", "name"], "context": ctx},
    )
    acc_map = {a["id"]: (a["code"], a["name"]) for a in accounts}
    ids = list(acc_map.keys())

    lines = models.execute_kw(
        db,
        uid,
        password,
        "account.move.line",
        "search_read",
        [
            [
                ["company_id", "=", company_id],
                ["account_id", "in", ids],
                ["parent_state", "=", "posted"],
                ["date", ">=", "2026-07-01"],
                ["date", "<=", "2026-09-30"],
            ]
        ],
        {"fields": ["date", "account_id", "balance"], "context": ctx},
    )

    df = pd.DataFrame(lines)
    df["account_id"] = df["account_id"].apply(
        lambda v: v[0] if isinstance(v, list) else v
    )
    df["code"] = df["account_id"].map(lambda i: acc_map[i][0])
    df["name"] = df["account_id"].map(lambda i: acc_map[i][1])
    df["date"] = pd.to_datetime(df["date"])
    df["ym"] = df["date"].dt.strftime("%Y-%m")

    pivot = df.pivot_table(
        index=["code", "name"],
        columns="ym",
        values="balance",
        aggfunc="sum",
        fill_value=0.0,
    )
    for col in ["2026-07", "2026-08", "2026-09"]:
        if col not in pivot.columns:
            pivot[col] = 0.0
    pivot = pivot[["2026-07", "2026-08", "2026-09"]]
    pivot["Total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("code" if False else pivot.index.names[0])  # sort by code
    pivot = pivot.reset_index()
    return pivot


# ---------------------------------------------------------------------------
# 2. Wansoft -- ventas, meseros, mix, consumo salon
# ---------------------------------------------------------------------------


def get_wansoft_data():
    conn = get_mysql_connection("wansoft")
    cur = conn.cursor()

    data = {}

    cur.execute(
        """
        SELECT mes_ano,
            SUM(total_ventas), SUM(subtotal), SUM(no_ordenes), SUM(total_personas), SUM(total_mesas_atendidas),
            SUM(cortesias_en_cuentas)+SUM(cortesias_en_platillos) as cortesias,
            SUM(cancelaciones_en_cuentas)+SUM(cancelaciones_en_platillos) as cancelaciones,
            SUM(anulaciones_en_cuentas)+SUM(anulaciones_en_platillos) as anulaciones,
            MAX(fecha_corte)
        FROM getglobalcashclosing
        WHERE subsidiary_name LIKE '%uebla%' AND mes_ano IN ('08-2026','09-2026')
        GROUP BY mes_ano ORDER BY mes_ano
    """
    )
    for row in cur.fetchall():
        mes = "aug" if row[0] == "08-2026" else "sep"
        data[f"{mes}_venta"] = float(row[1])  # bruta, con IVA
        data[f"{mes}_venta_neta"] = float(
            row[2]
        )  # neta, sin IVA -- base para % de costos
        data[f"{mes}_tickets"] = int(row[3])
        data[f"{mes}_clientes"] = int(row[4])
        data[f"{mes}_mesas"] = int(row[5])
        data[f"{mes}_cortesias"] = float(row[6])
        data[f"{mes}_cancelaciones"] = float(row[7])
        data[f"{mes}_anulaciones"] = float(row[8])
        data[f"{mes}_corte_max"] = row[9]

    # Meseros distintos y venta/cliente por mesero (mismo denominador)
    cur.execute(
        "SELECT COUNT(DISTINCT Mesero) FROM getallordenesbyday_new_venta WHERE Sucursal='Puebla' AND Fecha LIKE '2026-08%'"
    )
    data["aug_meseros"] = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(DISTINCT Mesero) FROM getallordenesbyday_new_venta WHERE Sucursal='Puebla' AND Fecha LIKE '2026-09%'"
    )
    data["sep_meseros"] = cur.fetchone()[0]

    # Mix Alimentos/Bebidas (join detalleventa-venta)
    for mes, like in (("aug", "2026-08%"), ("sep", "2026-09%")):
        cur.execute(
            f"""
            SELECT d.TipoGrupo, SUM(CAST(d.Total AS DECIMAL(12,2)))
            FROM getallordenesbyday_new_detalleventa d
            JOIN getallordenesbyday_new_venta v ON d.Movimiento_Id = v.Movimento AND d.Sucursal = v.Sucursal
            WHERE d.Sucursal='Puebla' AND v.Fecha LIKE '{like}'
            GROUP BY d.TipoGrupo
        """
        )
        vals = dict(cur.fetchall())
        alim = float(vals.get("Alimentos", 0))
        beb = float(vals.get("Bebidas", 0))
        total = alim + beb
        data[f"{mes}_mix_alimentos_pct"] = alim / total if total else None
        data[f"{mes}_mix_bebidas_pct"] = beb / total if total else None

    # Consumo Salon: TipoOrden=Restaurant y Mesero no Aplicaciones/AppsLlevar
    cur.execute(
        """
        SELECT LEFT(Fecha,7) ym, SUM(CAST(Total AS DECIMAL(12,2)))
        FROM getallordenesbyday_new_venta
        WHERE Sucursal='Puebla' AND TipoOrden='Restaurant'
          AND Mesero NOT LIKE '%Aplicaciones%' AND Mesero NOT LIKE '%AppsLlevar%'
        GROUP BY ym
    """
    )
    consumo_raw = dict(cur.fetchall())
    data["sep_consumo_salon_medido"] = float(consumo_raw.get("2026-09", 0))

    # Ticket-level dine-in share (full month, para estimar agosto)
    cur.execute(
        """
        SELECT SUM(no_ordenes), SUM(total_ordenes_para_llevar)
        FROM getglobalcashclosing WHERE subsidiary_name LIKE '%uebla%' AND mes_ano='08-2026'
    """
    )
    tickets, llevar = cur.fetchone()
    data["aug_consumo_salon_share"] = (float(tickets) - float(llevar)) / float(tickets)

    # Rango de fechas real de la tabla de tickets, para las notas (evita fechas quemadas)
    cur.execute(
        "SELECT MIN(Fecha), MAX(Fecha) FROM getallordenesbyday_new_venta WHERE Sucursal='Puebla' AND Fecha LIKE '2026-08%'"
    )
    r1 = cur.fetchone()
    data["aug_ticket_min"], data["aug_ticket_max"] = r1[0][:10], r1[1][:10]
    cur.execute(
        "SELECT MIN(Fecha), MAX(Fecha) FROM getallordenesbyday_new_venta WHERE Sucursal='Puebla' AND Fecha LIKE '2026-09%'"
    )
    r2 = cur.fetchone()
    data["sep_ticket_min"], data["sep_ticket_max"] = r2[0][:10], r2[1][:10]

    conn.close()
    return data


# ---------------------------------------------------------------------------
# 3. Construir el Excel
# ---------------------------------------------------------------------------

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
SECTION_FILL = PatternFill("solid", fgColor="D9E1F2")
NOTE_FONT = Font(italic=True, size=9, color="808080")
BOLD = Font(bold=True)
HEADER_FONT = Font(bold=True, color="FFFFFF")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(ws, row, col_start, col_end):
    for c in range(col_start, col_end + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
        cell.border = BORDER


def style_section(ws, row, col_start, col_end):
    for c in range(col_start, col_end + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = SECTION_FILL
        cell.font = BOLD
        cell.border = BORDER


def write_row(ws, row, values, number_formats=None, bold=False):
    for i, val in enumerate(values, start=1):
        cell = ws.cell(row=row, column=i, value=val)
        cell.border = BORDER
        if bold:
            cell.font = BOLD
        if number_formats and i in number_formats:
            cell.number_format = number_formats[i]


def build_workbook(odoo_df, w):
    wb = Workbook()
    ws = wb.active
    ws.title = "Scorecard Puebla"

    r = 1
    ws.cell(row=r, column=1, value="SCORECARD MENSUAL — SUCURSAL PUEBLA").font = Font(
        bold=True, size=14
    )
    r += 1
    ws.cell(
        row=r,
        column=1,
        value="Sin comparación año anterior (Puebla no tiene historial previo)",
    ).font = NOTE_FONT
    r += 2

    # ---- VENTAS ----
    style_section(ws, r, 1, 3)
    write_row(ws, r, ["VENTAS", "Agosto 2026", "Septiembre 2026 (a la fecha)"])
    r += 1

    money_fmt = "#,##0.00"
    pct_fmt = "0.0%"

    rows_ventas = [
        ("Ventas totales (bruta, con IVA)", w["aug_venta"], w["sep_venta"], money_fmt),
        (
            "Venta Neta (sin IVA) — base de los % de Costos",
            w["aug_venta_neta"],
            w["sep_venta_neta"],
            money_fmt,
        ),
        ("Clientes atendidos", w["aug_clientes"], w["sep_clientes"], "#,##0"),
        ("# Tickets", w["aug_tickets"], w["sep_tickets"], "#,##0"),
        ("# Mesas atendidas", w["aug_mesas"], w["sep_mesas"], "#,##0"),
        (
            "# Clientes por Mesa",
            w["aug_clientes"] / w["aug_mesas"],
            w["sep_clientes"] / w["sep_mesas"],
            "0.00",
        ),
        ("# Meseros distintos *", w["aug_meseros"], w["sep_meseros"], "#,##0"),
        (
            "Venta por Mesero *",
            w["aug_venta"] / w["aug_meseros"],
            w["sep_venta"] / w["sep_meseros"],
            money_fmt,
        ),
        (
            "Clientes por Mesero *",
            w["aug_clientes"] / w["aug_meseros"],
            w["sep_clientes"] / w["sep_meseros"],
            "0.0",
        ),
        (
            "Cheque Promedio (venta/cliente)",
            w["aug_venta"] / w["aug_clientes"],
            w["sep_venta"] / w["sep_clientes"],
            money_fmt,
        ),
        (
            "Ticket Promedio (venta/ticket)",
            w["aug_venta"] / w["aug_tickets"],
            w["sep_venta"] / w["sep_tickets"],
            money_fmt,
        ),
        (
            "Mix de ventas — Alimentos *",
            w["aug_mix_alimentos_pct"],
            w["sep_mix_alimentos_pct"],
            pct_fmt,
        ),
        (
            "Mix de ventas — Bebidas *",
            w["aug_mix_bebidas_pct"],
            w["sep_mix_bebidas_pct"],
            pct_fmt,
        ),
    ]
    for label, v_aug, v_sep, fmt in rows_ventas:
        write_row(ws, r, [label, v_aug, v_sep], number_formats={2: fmt, 3: fmt})
        r += 1

    r += 1

    # ---- COSTOS ----
    style_section(ws, r, 1, 3)
    write_row(
        ws,
        r,
        [
            "COSTOS (Odoo — cuentas contables 501.xx, datos reales)",
            "Agosto 2026",
            "Septiembre 2026 (a la fecha)",
        ],
    )
    r += 1

    cogs_aug = float(
        odoo_df.loc[
            odoo_df["code"].isin(
                [
                    "501.01.02",
                    "501.01.03",
                    "501.01.04",
                    "501.01.05",
                    "501.01.06",
                    "501.01.07",
                    "501.01.08",
                    "501.01.09",
                    "501.01.10",
                    "501.01.11",
                    "501.01.12",
                    "501.01.13",
                    "501.01.16",
                ]
            ),
            "2026-08",
        ].sum()
    )
    cogs_sep = float(
        odoo_df.loc[
            odoo_df["code"].isin(
                [
                    "501.01.02",
                    "501.01.03",
                    "501.01.04",
                    "501.01.05",
                    "501.01.06",
                    "501.01.07",
                    "501.01.08",
                    "501.01.09",
                    "501.01.10",
                    "501.01.11",
                    "501.01.12",
                    "501.01.13",
                    "501.01.16",
                ]
            ),
            "2026-09",
        ].sum()
    )
    var_inv_aug = float(odoo_df.loc[odoo_df["code"] == "501.01.14", "2026-08"].sum())
    var_inv_sep = float(odoo_df.loc[odoo_df["code"] == "501.01.14", "2026-09"].sum())
    merma_aug = float(odoo_df.loc[odoo_df["code"] == "501.01.15", "2026-08"].sum())
    merma_sep = float(odoo_df.loc[odoo_df["code"] == "501.01.15", "2026-09"].sum())
    total_501_aug = cogs_aug + var_inv_aug + merma_aug
    total_501_sep = cogs_sep + var_inv_sep + merma_sep

    # % de costos se calculan sobre venta NETA (sin IVA), no sobre venta bruta.
    aug_venta_base = w["aug_venta_neta"]
    sep_venta_aligned = w["sep_venta_neta"]

    rows_costos = [
        (
            "Costo de Productos Vendidos (Odoo, cuentas 501.01.02–13 y 16 — Alimentos/Bebidas)",
            cogs_aug,
            cogs_aug / aug_venta_base,
            cogs_sep,
            cogs_sep / sep_venta_aligned,
        ),
        (
            "Variaciones de Inventario (Odoo, cuenta 501.01.14)",
            var_inv_aug,
            var_inv_aug / aug_venta_base,
            var_inv_sep,
            var_inv_sep / sep_venta_aligned,
        ),
        (
            "Costo por Merma (Odoo, cuenta 501.01.15)",
            merma_aug,
            merma_aug / aug_venta_base,
            merma_sep,
            merma_sep / sep_venta_aligned,
        ),
        (
            "COGS TOTAL / Costo Total Operativo Teórico (suma cuenta 501)",
            total_501_aug,
            total_501_aug / aug_venta_base,
            total_501_sep,
            total_501_sep / sep_venta_aligned,
        ),
    ]
    for label, monto_a, pct_a, monto_s, pct_s in rows_costos:
        write_row(
            ws,
            r,
            [label, monto_a, monto_s],
            number_formats={2: money_fmt, 3: money_fmt},
        )
        r += 1
        write_row(
            ws,
            r,
            ["   % sobre venta", pct_a, pct_s],
            number_formats={2: pct_fmt, 3: pct_fmt},
        )
        ws.cell(row=r, column=1).font = NOTE_FONT
        r += 1

    r += 1
    write_row(
        ws,
        r,
        [
            "COSTOS (Wansoft — cierre diario / detalle de ticket)",
            "Agosto 2026",
            "Septiembre 2026 (a la fecha)",
        ],
    )
    style_section(ws, r, 1, 3)
    r += 1

    rows_costos_wansoft = [
        (
            "Costo por Cancelaciones (cierre diario)",
            w["aug_cancelaciones"],
            w["sep_cancelaciones"],
        ),
        ("Costo por Cortesía (cierre diario)", w["aug_cortesias"], w["sep_cortesias"]),
        (
            "Anulaciones (informativo, cierre diario)",
            w["aug_anulaciones"],
            w["sep_anulaciones"],
        ),
        (
            "Consumo Salón — Agosto estimado (% mix ticket × venta total) / Septiembre medido *",
            w["aug_venta"] * w["aug_consumo_salon_share"],
            w["sep_consumo_salon_medido"],
        ),
    ]
    for label, v_a, v_s in rows_costos_wansoft:
        write_row(ws, r, [label, v_a, v_s], number_formats={2: money_fmt, 3: money_fmt})
        r += 1

    r += 2
    ws.cell(
        row=r, column=1, value="* Ver notas de cobertura de datos al final de la hoja."
    ).font = NOTE_FONT
    r += 3

    # ---- DESGLOSE COSTO CUENTA 501 (Odoo) ----
    ws.cell(
        row=r,
        column=1,
        value="DESGLOSE DE COSTO — CUENTA 501 (Odoo, Reportes Analíticos, réplica exacta)",
    ).font = Font(bold=True, size=12)
    r += 1
    ws.cell(
        row=r,
        column=1,
        value="Fuente: account.move.line, company_id=34 (FONDA ARGENTINA PUEBLA), parent_state='posted', cuentas con código 501.xx. Verificado contra captura de Odoo Contabilidad.",
    ).font = NOTE_FONT
    r += 2

    style_header(ws, r, 1, 5)
    write_row(
        ws, r, ["Cuenta", "Julio 2026", "Agosto 2026", "Septiembre 2026", "Total"]
    )
    r += 1

    total_row = {"2026-07": 0.0, "2026-08": 0.0, "2026-09": 0.0, "Total": 0.0}
    for _, row_data in odoo_df.iterrows():
        label = f"{row_data['code']} {row_data['name']}"
        vals = [
            label,
            row_data["2026-07"],
            row_data["2026-08"],
            row_data["2026-09"],
            row_data["Total"],
        ]
        write_row(
            ws,
            r,
            vals,
            number_formats={2: money_fmt, 3: money_fmt, 4: money_fmt, 5: money_fmt},
        )
        for col in ["2026-07", "2026-08", "2026-09", "Total"]:
            total_row[col] += row_data[col]
        r += 1

    write_row(
        ws,
        r,
        [
            "TOTAL",
            total_row["2026-07"],
            total_row["2026-08"],
            total_row["2026-09"],
            total_row["Total"],
        ],
        number_formats={2: money_fmt, 3: money_fmt, 4: money_fmt, 5: money_fmt},
        bold=True,
    )
    style_section(ws, r, 1, 5)
    r += 2

    notes = [
        "NOTAS DE COBERTURA DE DATOS:",
        (
            "* getallordenesbyday_new_venta / _new_detalleventa (tabla de detalle por ticket) solo tiene Puebla "
            "del "
            + w["aug_ticket_min"]
            + " al "
            + w["sep_ticket_max"]
            + " -- es la ventana real que trae la tabla, no un filtro mio."
        ),
        (
            "  Por eso: Meseros/Venta por Mesero/Clientes por Mesero/Mix Alimentos-Bebidas de AGOSTO son una "
            "muestra de los dias "
            + w["aug_ticket_min"]
            + " a "
            + w["aug_ticket_max"]
            + ", no el mes completo."
        ),
        (
            "  Septiembre ("
            + w["sep_ticket_min"]
            + " a "
            + w["sep_ticket_max"]
            + ") si es practicamente el mes completo a la fecha para esa tabla."
        ),
        "* Consumo Salón de agosto es ESTIMADO (% de tickets Salón, con cobertura completa de 31/31 días vía cierre diario, aplicado sobre la venta total exacta del mes).",
        (
            "  Consumo Salón de septiembre es MEDIDO directo sobre la ventana "
            + w["sep_ticket_min"]
            + " a "
            + w["sep_ticket_max"]
            + " (cobertura casi completa de esa tabla)."
        ),
        (
            "* Los % sobre venta de la seccion de Costos se calculan sobre VENTA NETA (sin IVA, columna "
            "'subtotal' del cierre diario), no sobre venta bruta -- por instruccion del usuario, ya que asi "
            "se calculan los costos contra venta en el negocio. Venta neta usada: agosto $"
            + f"{aug_venta_base:,.2f}"
            + ", septiembre $"
            + f"{sep_venta_aligned:,.2f}"
            + "."
        ),
        "* Costo de Productos Vendidos / Variaciones de Inventario / Merma / COGS Total vienen de Odoo en vivo (contabilidad real), no de órdenes de compra — reemplaza estimaciones anteriores basadas en compras.",
    ]
    for note in notes:
        ws.cell(row=r, column=1, value=note).font = (
            NOTE_FONT if not note.startswith("NOTAS") else Font(bold=True, size=10)
        )
        r += 1

    # column widths
    widths = [58, 20, 20, 20, 18]
    for i, wd in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = wd

    wb.save(OUT_PATH)
    print(f"Guardado: {OUT_PATH}")


if __name__ == "__main__":
    odoo_df = get_odoo_cost_breakdown()
    w = get_wansoft_data()
    build_workbook(odoo_df, w)
