"""
Reportes Ejecutivos -- Agosto 2026 -- TODAS las sucursales (19).

Regla de negocio (confirmada por el usuario 2026-09-18, reemplaza la regla
anterior por-sucursal documentada en companies.py):
- Costo de Productos Vendidos: si la empresa esta en Odoo (COMPANY_SOURCE
  == "odoo") -> Odoo en vivo (account.move.line, cuenta 501.xx).
  Si no -> Wansoft (costeomensual.CostoDeProductosVendidos).
- Merma, Cortesias, Cancelaciones/Descuentos: SIEMPRE Wansoft, sin
  importar si la empresa esta en Odoo o no.
    - Merma: costeomensual.CostoDeMerma (no existe en el cierre diario).
    - Cortesias / Cancelaciones / Anulaciones: getglobalcashclosing
      (cierre diario), igual que la Venta -- a precio de venta, no a
      costo de insumo, por eso se muestran aparte del Costo Total
      (mezclar valuaciones distintas en una sola suma no es correcto).

Guarda los PDFs en Reportes/Analisis Ejecutivos/Mensuales/.
"""

import sys
import os
from pathlib import Path
from datetime import date

# Cross-repo dependency: this project (Analisis Ejecutivos) reuses the
# Wansoft repo's DB connection helpers (core.database.*, core.config.*)
# instead of duplicating them. Works because both repos live as siblings
# on this machine -- NOT portable to another machine without the same
# folder layout. Revisit in Step 25 (own connection module, or a proper
# installable shared package) instead of assuming this path forever.
WANSOFT_REPO_ROOT = r"C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\AnalisisRestaurantesBI\Wansoft\Jupyter Notebooks\Python Files"
sys.path.insert(0, WANSOFT_REPO_ROOT)
os.environ["ENV"] = "dev"

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

from core.database.mysql import get_mysql_connection
from core.database.odoo import get_odoo_connection
from core.config.companies import COMPANY_SOURCE

HERE = Path(__file__).resolve().parent
ANALISIS_EJECUTIVOS_DIR = Path(r"C:\Users\JavierViniegra\OneDrive - GRUPO FONDA ARGENTINA\Escritorio\AnalisisRestaurantesBI\Reportes\Analisis Ejecutivos")
BG_IMAGE = str(HERE / "logo_extract_0.jpeg")

# --- Mes a generar: cambiar aqui cada corrida mensual ---
ANIO = 2026
MES_NUM = 8  # 1-12
# ---------------------------------------------------------

MESES_ES = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
            7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
def fecha_es(d):
    m = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
         7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
    return f"{d.day} de {m[d.month]} de {d.year}"

MES_ANO = f"{MES_NUM:02d}-{ANIO}"
MES_NOMBRE = MESES_ES[MES_NUM]
MES_LABEL = f"{MES_NOMBRE} {ANIO}"
FILENAME_SUFFIX = f"{MES_NOMBRE}_{ANIO}"

# docs/Mensuales/<año>/<Mes>/ -- se crea si no existe (regla del usuario, 2026-09-18)
OUT_DIR = ANALISIS_EJECUTIVOS_DIR / "docs" / "Mensuales" / str(ANIO) / MES_NOMBRE

BRAND_GREEN = HexColor("#10564E")
DARK_TEXT = HexColor("#1A1A1A")
GREY_TEXT = HexColor("#555555")
LIGHT_LINE = HexColor("#CCCCCC")
PAGE_W, PAGE_H = letter
MARGIN_L, MARGIN_R = 60, 60
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

# key -> (display, gcc_term or exact, ticket_term or exact, odoo_company_name)
COMPANIES = [
    {"key": "Acoxpa", "display": "Acoxpa", "gcc_term": "Acoxpa", "ticket_term": "Acoxpa",
     "odoo_company_name": "FONDA COSTA NERA"},
    {"key": "Aeropuerto", "display": "Aeropuerto", "gcc_term": "Aeropuerto", "ticket_term": "Aeropuerto"},
    {"key": "IsabelLaCatolica", "display": "Isabel La Católica", "gcc_term": "Isabel", "ticket_term": "Isabel"},
    {"key": "Antenas", "display": "Antenas", "gcc_term": "Antenas", "ticket_term": "Antenas",
     "odoo_company_name": "FONDA ARGENTINA LAS ANTENAS"},
    {"key": "TaqueriaParroquia", "display": "Taquería Parroquia", "gcc_term": "Parroqu", "ticket_term": "Parroqu"},
    {"key": "ViaVallejo", "display": "Vía Vallejo", "gcc_term": "Vallejo", "ticket_term": "Vallejo"},
    {"key": "Viaducto", "display": "Viaducto", "gcc_exact": "Fonda Argentina - Viaducto", "ticket_exact": "Viaducto"},
    {"key": "TaqueriaViaducto", "display": "Taquería Viaducto", "gcc_exact": "Fonda Argentina - Taqueria Viaducto", "ticket_term": "Taquer\u00eda Viaducto"},
    {"key": "SanJeronimo", "display": "San Jerónimo", "gcc_term": "Jer", "ticket_term": "Jeronimo"},
    {"key": "Tepeyac", "display": "Tepeyac", "gcc_term": "Tepeyac", "ticket_term": "Tepeyac",
     "odoo_company_name": "FONDA ARGENTINA MAQ"},
    {"key": "PlayaDelCarmen", "display": "Playa del Carmen", "gcc_term": "Carmen", "ticket_term": "Carmen"},
    {"key": "Oceania", "display": "Oceanía", "gcc_term": "Ocean", "ticket_term": "Ocean",
     "odoo_company_name": "FONDA ARGENTINA ENCUENTRO OCEANIA"},
    {"key": "Cancun", "display": "Cancún", "gcc_term": "Canc", "ticket_term": "Cancun"},
    {"key": "Napoles", "display": "Nápoles", "gcc_term": "poles", "ticket_term": "Napoles"},
    {"key": "Metepec", "display": "Metepec", "gcc_term": "Tollocan", "ticket_term": "Tollocan"},
    {"key": "Versalles", "display": "Versalles", "gcc_term": "Exhibimex", "ticket_term": "Exhibimex"},
    {"key": "Coyoacan", "display": "La Esquina Coyoacán", "gcc_term": "Coyoacan", "ticket_term": "Coyoac",
     "odoo_company_name": "FONDA ARGENTINA COYOACAN"},
    {"key": "CentroMyJ", "display": "CentroMyJ (Mario y July)", "gcc_term": "Mario", "ticket_term": "CentroMyJ",
     "odoo_company_name": "MARIO Y JULY"},
    {"key": "Puebla", "display": "Puebla", "gcc_term": "Puebla", "ticket_term": "Puebla",
     "odoo_company_name": "FONDA ARGENTINA PUEBLA"},
]
CS_KEY_BY_COMPANY = {
    "Acoxpa": "Acoxpa", "Aeropuerto": "Aeropuerto", "IsabelLaCatolica": "Isabel La Católica",
    "Antenas": "Antenas", "TaqueriaParroquia": "Taquería parroquia", "ViaVallejo": "Vía Vallejo",
    "Viaducto": "Viaducto", "TaqueriaViaducto": "Taquería Viaducto", "SanJeronimo": "San Jeronimo",
    "Tepeyac": "Tepeyac", "PlayaDelCarmen": "Playa del Carmen", "Oceania": "Oceanía",
    "Cancun": "Cancun", "Napoles": "Napoles", "Metepec": "Metepec", "Versalles": "Versalles",
    "Coyoacan": "La Esquina Coyoacán", "CentroMyJ": "CentroMyJ", "Puebla": "Puebla",
}
for cfg in COMPANIES:
    cfg["is_odoo"] = COMPANY_SOURCE[CS_KEY_BY_COMPANY[cfg["key"]]] == "odoo"


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------

def resolve_name(cur, table, name_col, sucursal_col_filter, cfg, kind):
    if f"{kind}_exact" in cfg:
        return cfg[f"{kind}_exact"]
    term = cfg[f"{kind}_term"]
    cur.execute(f"SELECT DISTINCT {name_col} FROM {table} WHERE {name_col} LIKE %s", (f"%{term}%",))
    rows = [r[0] for r in cur.fetchall()]
    if len(rows) == 0 and kind == "ticket":
        return None  # sin datos de detalle de ticket para esta sucursal (ej. Metepec, Versalles)
    if len(rows) != 1:
        raise ValueError(f"{cfg['key']}/{kind}: esperaba 1 match, encontre {rows}")
    return rows[0]


def fetch_ventas(cur, gcc_name):
    cur.execute("""
        SELECT SUM(total_ventas), SUM(subtotal), SUM(no_ordenes), SUM(total_personas), SUM(total_mesas_atendidas),
            SUM(cortesias_en_cuentas)+SUM(cortesias_en_platillos),
            SUM(cancelaciones_en_cuentas)+SUM(cancelaciones_en_platillos),
            SUM(anulaciones_en_cuentas)+SUM(anulaciones_en_platillos)
        FROM getglobalcashclosing WHERE subsidiary_name=%s AND mes_ano=%s
    """, (gcc_name, MES_ANO))
    row = cur.fetchone()
    if row[0] is None:
        return None
    keys = ["venta_bruta", "venta_neta", "tickets", "clientes", "mesas", "cortesias", "cancelaciones", "anulaciones"]
    return {k: float(v) for k, v in zip(keys, row)}


def fetch_ticket_data(cur, ticket_name):
    cur.execute("SELECT MIN(Fecha), MAX(Fecha), COUNT(DISTINCT Mesero) FROM getallordenesbyday_new_venta WHERE Sucursal=%s AND Fecha LIKE '2026-08%%'", (ticket_name,))
    min_f, max_f, meseros = cur.fetchone()
    full_coverage = (min_f is not None and min_f[:10] == "2026-08-01")
    cur.execute("""
        SELECT d.TipoGrupo, SUM(CAST(d.Total AS DECIMAL(12,2)))
        FROM getallordenesbyday_new_detalleventa d
        JOIN getallordenesbyday_new_venta v ON d.Movimiento_Id = v.Movimento AND d.Sucursal = v.Sucursal
        WHERE d.Sucursal=%s AND v.Fecha LIKE '2026-08%%' GROUP BY d.TipoGrupo
    """, (ticket_name,))
    mix = dict(cur.fetchall())
    alim = float(mix.get("Alimentos", 0))
    beb = float(mix.get("Bebidas", 0))
    total = alim + beb
    return {
        "meseros": int(meseros or 0),
        "full_coverage": full_coverage,
        "min_fecha": min_f[:10] if min_f else None,
        "max_fecha": max_f[:10] if max_f else None,
        "mix_alimentos_pct": (alim / total) if total else None,
        "mix_bebidas_pct": (beb / total) if total else None,
    }


def fetch_wansoft_cpv_merma(cur, gcc_name):
    cur.execute("SELECT * FROM costeomensual WHERE subsidiary_name=%s AND created_date='2026-08-31'", (gcc_name,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    d = dict(zip(cols, row))
    return {
        "cpv": float(d["CostoDeProductosVendidos"] or 0),
        "merma": float(d[cols[8]] or 0),  # CostoDeMerma by position (encoding-safe)
        "utilidad_marginal": float(d["UtilidadMarginal"] or 0),
    }


def fetch_wansoft_merma_only(cur, gcc_name):
    cur.execute("SELECT * FROM costeomensual WHERE subsidiary_name=%s AND created_date='2026-08-31'", (gcc_name,))
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    d = dict(zip(cols, row))
    return float(d[cols[8]] or 0)  # CostoDeMerma


def fetch_odoo_cost(odoo_company_name):
    uid, models, db, password = get_odoo_connection()
    companies = models.execute_kw(db, uid, password, "res.company", "search_read",
                                   [[["name", "=", odoo_company_name]]], {"fields": ["id", "name"]})
    company_id = companies[0]["id"]
    ctx = {"allowed_company_ids": [company_id]}
    accounts = models.execute_kw(db, uid, password, "account.account", "search_read",
        [[["company_ids", "in", [company_id]], ["code", "like", "501"]]],
        {"fields": ["id", "code", "name"], "context": ctx})
    acc_map = {a["id"]: (a["code"], a["name"]) for a in accounts}
    ids = list(acc_map.keys())
    lines = models.execute_kw(db, uid, password, "account.move.line", "search_read",
        [[["company_id", "=", company_id], ["account_id", "in", ids], ["parent_state", "=", "posted"],
          ["date", ">=", "2026-08-01"], ["date", "<=", "2026-08-31"]]],
        {"fields": ["account_id", "balance"], "context": ctx})
    df = pd.DataFrame(lines)
    if df.empty:
        return {"breakdown": pd.DataFrame(columns=["code","name","balance"]), "cogs": 0.0, "var_inv": 0.0}
    df["account_id"] = df["account_id"].apply(lambda v: v[0] if isinstance(v, list) else v)
    df["code"] = df["account_id"].map(lambda i: acc_map[i][0])
    df["name"] = df["account_id"].map(lambda i: acc_map[i][1])
    g = df.groupby(["code", "name"])["balance"].sum().reset_index().sort_values("code")
    product_codes = {"501.01.02","501.01.03","501.01.04","501.01.05","501.01.06","501.01.07",
                      "501.01.08","501.01.09","501.01.10","501.01.11","501.01.12","501.01.13","501.01.16"}
    cogs = float(g.loc[g["code"].isin(product_codes), "balance"].sum())
    var_inv = float(g.loc[g["code"] == "501.01.14", "balance"].sum())
    return {"breakdown": g, "cogs": cogs, "var_inv": var_inv}


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _bar_chart(labels, values, title, out_path):
    fig, ax = plt.subplots(figsize=(7.2, 3.2), dpi=200)
    bars = ax.barh(labels, values, color="#10564E", height=0.55)
    ax.set_xlabel("MXN", fontsize=9, color="#333333")
    ax.tick_params(axis="y", labelsize=9.5, colors="#222222")
    ax.tick_params(axis="x", labelsize=8, colors="#555555")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x/1000:,.0f}k"))
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#CCCCCC")
    maxval = max(values) if values else 1
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + maxval * 0.015, bar.get_y() + bar.get_height()/2,
                 f"${val:,.0f}", va="center", ha="left", fontsize=8, color="#333333")
    ax.set_xlim(0, maxval * 1.28)
    plt.title(title, fontsize=10.5, color="#10564E", fontweight="bold", loc="left", pad=10)
    plt.tight_layout()
    plt.savefig(out_path, dpi=200, transparent=True)
    plt.close(fig)


def build_chart_odoo(g, out_path):
    product_codes = {"501.01.02","501.01.03","501.01.04","501.01.05","501.01.06","501.01.07",
                      "501.01.08","501.01.09","501.01.10","501.01.11","501.01.12","501.01.13","501.01.16"}
    prod = g[g["code"].isin(product_codes)].sort_values("balance", ascending=True)
    prod = prod[prod["balance"] > 0]
    _bar_chart(prod["name"].tolist(), prod["balance"].tolist(),
               f"Costo por categoría — Cuenta 501 (Odoo) — {MES_LABEL}", out_path)


def build_chart_wansoft(venta_neta, costo_total, utilidad, out_path):
    _bar_chart(["Utilidad Marginal", "Costo Total", "Venta Neta"], [utilidad, costo_total, venta_neta],
               f"Venta Neta vs. Costo vs. Utilidad Marginal — {MES_LABEL}", out_path)


# ---------------------------------------------------------------------------
# PDF drawing helpers
# ---------------------------------------------------------------------------

def draw_background(c):
    c.drawImage(BG_IMAGE, 0, 0, width=PAGE_W, height=PAGE_H, preserveAspectRatio=False)


def draw_header(c, page_title):
    c.setFont("Times-Roman", 9)
    c.setFillColor(DARK_TEXT)
    c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 55, "Fonda Argentina -- Business Intelligence")
    c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 68, page_title)
    c.setFillColor(GREY_TEXT)
    c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 81, f"Generado el {fecha_es(date.today())}")
    c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 94, "Rev. 1.0")


def wrap_text(c, text, font, size, max_width):
    c.setFont(font, size)
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if c.stringWidth(trial, font, size) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_footer(c, page_num, note):
    c.setFont("Times-Italic", 6.8)
    c.setFillColor(GREY_TEXT)
    lines = wrap_text(c, note, "Times-Italic", 6.8, PAGE_W - 2 * MARGIN_L + 20)
    yy = 40 + (len(lines) - 1) * 9
    for line in lines:
        c.drawString(MARGIN_L - 20, yy, line)
        yy -= 9
    c.setFont("Times-Roman", 9)
    c.setFillColor(DARK_TEXT)
    c.drawCentredString(PAGE_W / 2, 22, str(page_num))


def draw_bullet(c, x, y, bold_lead, rest, max_width, leading=12.5):
    bullet_indent = 14
    c.setFillColor(DARK_TEXT)
    c.setFont("Times-Bold", 9.3)
    c.drawString(x, y, "\u2022")
    words_bold = bold_lead.split(" ")
    words_rest = rest.split(" ")
    tokens = [(w, True) for w in words_bold] + [(w, False) for w in words_rest]
    cur_line, cur_bold_flags, cur_width = [], [], 0
    lines = []
    for w, is_bold in tokens:
        font = "Times-Bold" if is_bold else "Times-Roman"
        wpiece = w + " "
        ww = c.stringWidth(wpiece, font, 9.3)
        if cur_width + ww > max_width - bullet_indent and cur_line:
            lines.append(list(zip(cur_line, cur_bold_flags)))
            cur_line, cur_bold_flags, cur_width = [], [], 0
        cur_line.append(w)
        cur_bold_flags.append(is_bold)
        cur_width += ww
    if cur_line:
        lines.append(list(zip(cur_line, cur_bold_flags)))
    yy = y
    for line in lines:
        xx = x + bullet_indent
        for word, is_bold in line:
            font = "Times-Bold" if is_bold else "Times-Roman"
            c.setFont(font, 9.3)
            c.drawString(xx, yy, word + " ")
            xx += c.stringWidth(word + " ", font, 9.3)
        yy -= leading
    return yy


def draw_kpi_table(c, x, y, title, rows, col_widths, header=None):
    c.setFont("Times-Bold", 11)
    c.setFillColor(BRAND_GREEN)
    c.drawString(x, y, title)
    y -= 16
    row_h = 15.2
    total_w = sum(col_widths)
    if header:
        c.setFillColor(BRAND_GREEN)
        c.rect(x, y - row_h + 4, total_w, row_h, fill=1, stroke=0)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Times-Bold", 8.6)
        xx = x + 6
        for h, w in zip(header, col_widths):
            c.drawString(xx, y - row_h + 9, h)
            xx += w
        y -= row_h
    for i, row in enumerate(rows):
        if i % 2 == 1:
            c.setFillColor(HexColor("#F2F5F4"))
            c.rect(x, y - row_h + 4, total_w, row_h, fill=1, stroke=0)
        c.setFillColor(DARK_TEXT)
        xx = x + 6
        for j, (val, w) in enumerate(zip(row, col_widths)):
            font = "Times-Bold" if j == 0 else "Times-Roman"
            c.setFont(font, 8.8)
            c.drawString(xx, y - row_h + 9, str(val))
            xx += w
        y -= row_h
    c.setStrokeColor(LIGHT_LINE)
    c.rect(x, y + 4, total_w, (len(rows) + (1 if header else 0)) * row_h, fill=0, stroke=1)
    return y


# ---------------------------------------------------------------------------
# Build one company's PDF
# ---------------------------------------------------------------------------

def build_company_report(cfg, cur):
    key = cfg["key"]
    print(f"=== {key} (odoo={cfg['is_odoo']}) ===")

    gcc_name = resolve_name(cur, "getglobalcashclosing", "subsidiary_name", None, cfg, "gcc")
    ticket_name = resolve_name(cur, "getallordenesbyday_new_venta", "Sucursal", None, cfg, "ticket")

    ventas = fetch_ventas(cur, gcc_name)
    if ventas is None:
        print(f"  SIN DATOS de venta para {key} en {MES_ANO} -- se omite.")
        return
    if ticket_name is None:
        ticket = {"meseros": 0, "full_coverage": False, "min_fecha": None, "max_fecha": None,
                   "mix_alimentos_pct": None, "mix_bebidas_pct": None}
    else:
        ticket = fetch_ticket_data(cur, ticket_name)

    merma = fetch_wansoft_merma_only(cur, gcc_name)

    if cfg["is_odoo"]:
        odoo = fetch_odoo_cost(cfg["odoo_company_name"])
        cpv = odoo["cogs"]
        var_inv = odoo["var_inv"]
        costo_total = cpv + merma + var_inv
        chart_path = str(HERE / f"chart_{key}.png")
        build_chart_odoo(odoo["breakdown"], chart_path)
        cost_source_label = "Odoo (cuenta contable 501)"
    else:
        wcost = fetch_wansoft_cpv_merma(cur, gcc_name)
        cpv = wcost["cpv"]
        var_inv = None
        costo_total = cpv + merma
        chart_path = str(HERE / f"chart_{key}.png")
        build_chart_wansoft(ventas["venta_neta"], costo_total, wcost["utilidad_marginal"], chart_path)
        cost_source_label = "Wansoft (costeo mensual real)"

    cost_pct = costo_total / ventas["venta_neta"] if ventas["venta_neta"] else 0

    clientes_por_mesa = ventas["clientes"] / ventas["mesas"] if ventas["mesas"] else 0
    cheque_prom = ventas["venta_bruta"] / ventas["clientes"] if ventas["clientes"] else 0
    ticket_prom = ventas["venta_bruta"] / ventas["tickets"] if ventas["tickets"] else 0
    venta_por_mesero = ventas["venta_bruta"] / ticket["meseros"] if ticket["meseros"] else None
    clientes_por_mesero = ventas["clientes"] / ticket["meseros"] if ticket["meseros"] else None
    cov_note = "" if ticket["full_coverage"] else " *"

    out_path = OUT_DIR / f"Reporte_Ejecutivo_{key}_{FILENAME_SUFFIX}.pdf"
    c = canvas.Canvas(str(out_path), pagesize=letter)

    # ---- PAGE 1 ----
    draw_background(c)
    page_title = f"Reporte Ejecutivo -- Sucursal {cfg['display']} -- {MES_LABEL}"
    draw_header(c, page_title)

    y = PAGE_H - 165
    c.setFont("Times-Bold", 19)
    c.setFillColor(BRAND_GREEN)
    c.drawString(MARGIN_L, y, f"{cfg['display']} -- Resumen Ejecutivo de {MES_LABEL}")
    y -= 16
    c.setFont("Times-Italic", 9.5)
    c.setFillColor(GREY_TEXT)
    c.drawString(MARGIN_L, y, f"Fuente: Wansoft (Ventas, Merma, Cortesías, Cancelaciones) y {cost_source_label} (Costo de Productos Vendidos)")
    y -= 26

    c.setFont("Times-Bold", 12.5)
    c.setFillColor(BRAND_GREEN)
    c.drawString(MARGIN_L, y, "Resumen Ejecutivo")
    y -= 18

    bullets = [
        ("Venta del mes: ",
         f"{cfg['display']} facturó ${ventas['venta_bruta']:,.2f} en agosto (venta neta sin IVA: ${ventas['venta_neta']:,.2f}), "
         f"con {ventas['clientes']:,.0f} clientes atendidos en {ventas['tickets']:,.0f} tickets -- ticket promedio de "
         f"${ticket_prom:,.2f} y cheque promedio de ${cheque_prom:,.2f} por cliente."),
        ("Costo total del mes: ",
         f"${costo_total:,.2f}, equivalente al {cost_pct*100:.2f}% de la venta neta (Costo de Productos Vendidos ${cpv:,.2f} "
         f"+ Merma ${merma:,.2f}" + (f" + Variaciones de Inventario ${var_inv:,.2f}" if var_inv else "") + ")."),
    ]
    if ticket["mix_alimentos_pct"] is not None:
        bullets.append((
            "Mix de venta: ",
            f"{ticket['mix_alimentos_pct']*100:.2f}% Alimentos / {ticket['mix_bebidas_pct']*100:.2f}% Bebidas." + (
                " (muestra parcial -- ver nota)" if not ticket["full_coverage"] else "")
        ))
    bullets.append((
        "Cancelaciones y Cortesías (a precio de venta): ",
        f"sumaron ${ventas['cancelaciones']+ventas['cortesias']:,.2f} combinadas (cancelaciones ${ventas['cancelaciones']:,.2f} "
        f"+ cortesías ${ventas['cortesias']:,.2f}), {(ventas['cancelaciones']+ventas['cortesias'])/ventas['venta_bruta']*100:.2f}% de la venta total."
    ))
    if venta_por_mesero is not None:
        bullets.append((
            "Productividad por mesero: ",
            f"con {ticket['meseros']} meseros distintos{' (muestra parcial)' if not ticket['full_coverage'] else ''}, "
            f"la venta promedio por mesero fue de ${venta_por_mesero:,.2f} y {clientes_por_mesero:,.1f} clientes atendidos por mesero."
        ))

    for lead, rest in bullets:
        y = draw_bullet(c, MARGIN_L, y, lead, rest, CONTENT_W)
        y -= 4
    y -= 6

    rows_ventas = [
        ("Ventas totales (bruta, con IVA)", f"${ventas['venta_bruta']:,.2f}"),
        ("Venta Neta (sin IVA)", f"${ventas['venta_neta']:,.2f}"),
        ("Clientes atendidos", f"{ventas['clientes']:,.0f}"),
        ("# Tickets", f"{ventas['tickets']:,.0f}"),
        ("# Mesas atendidas", f"{ventas['mesas']:,.0f}"),
        ("# Clientes por Mesa", f"{clientes_por_mesa:.2f}"),
        (f"# Meseros distintos{cov_note}", f"{ticket['meseros']}" if ticket['meseros'] else "N/D"),
        (f"Venta por Mesero{cov_note}", f"${venta_por_mesero:,.2f}" if venta_por_mesero else "N/D"),
        (f"Clientes por Mesero{cov_note}", f"{clientes_por_mesero:.1f}" if clientes_por_mesero else "N/D"),
        ("Cheque Promedio (venta/cliente)", f"${cheque_prom:,.2f}"),
        ("Ticket Promedio (venta/ticket)", f"${ticket_prom:,.2f}"),
        (f"Mix de ventas -- Alimentos{cov_note}", f"{ticket['mix_alimentos_pct']*100:.2f}%" if ticket['mix_alimentos_pct'] is not None else "N/D"),
        (f"Mix de ventas -- Bebidas{cov_note}", f"{ticket['mix_bebidas_pct']*100:.2f}%" if ticket['mix_bebidas_pct'] is not None else "N/D"),
    ]
    y = draw_kpi_table(c, MARGIN_L, y, f"Ventas -- {MES_LABEL}", rows=rows_ventas, col_widths=[190, 130])
    y -= 10

    rows_costos = [
        ("Costo de Productos Vendidos", f"${cpv:,.2f}", f"{cpv/ventas['venta_neta']*100:.2f}%"),
    ]
    if var_inv is not None:
        rows_costos.append(("Variaciones de Inventario", f"${var_inv:,.2f}", f"{var_inv/ventas['venta_neta']*100:.2f}%"))
    rows_costos.append(("Costo por Merma", f"${merma:,.2f}", f"{merma/ventas['venta_neta']*100:.2f}%"))
    rows_costos.append(("COSTO TOTAL OPERATIVO TEÓRICO", f"${costo_total:,.2f}", f"{cost_pct*100:.2f}%"))

    y = draw_kpi_table(c, MARGIN_L, y, f"Costos -- {MES_LABEL} (% s/venta neta)",
                        header=("Concepto", "Monto", "% s/venta neta"),
                        rows=rows_costos, col_widths=[230, 90, 70])
    y -= 8
    c.setFont("Times-Bold", 10)
    c.setFillColor(BRAND_GREEN)
    c.drawString(MARGIN_L, y, "Ajustes de Venta -- informativo, a precio de venta (Wansoft, cierre diario)")
    y -= 14
    ajustes_line = (
        f"Cortesías: ${ventas['cortesias']:,.2f}    |    Cancelaciones: ${ventas['cancelaciones']:,.2f}    |    "
        f"Anulaciones: ${ventas['anulaciones']:,.2f}"
    )
    c.setFont("Times-Roman", 9)
    c.setFillColor(DARK_TEXT)
    c.drawString(MARGIN_L, y, ajustes_line)
    y -= 6

    draw_footer(c, 1,
        f"Fuentes: Ventas, Merma, Cortesías, Cancelaciones -- Wansoft. Costo de Productos Vendidos -- {cost_source_label}. "
        "Ver notas y fuentes detalladas en la página 2.")
    c.showPage()

    # ---- PAGE 2 ----
    draw_background(c)
    draw_header(c, page_title)
    y = PAGE_H - 165
    c.setFont("Times-Bold", 14)
    c.setFillColor(BRAND_GREEN)
    c.drawString(MARGIN_L, y, "Desglose de Costo")
    y -= 10
    chart_w = CONTENT_W
    chart_h = chart_w * (3.2 / 7.2)
    c.drawImage(chart_path, MARGIN_L, y - chart_h, width=chart_w, height=chart_h, preserveAspectRatio=True, mask='auto')
    y -= chart_h + 26

    c.setFont("Times-Bold", 12.5)
    c.setFillColor(BRAND_GREEN)
    c.drawString(MARGIN_L, y, "Notas y Fuentes de Datos")
    y -= 16

    notes = [
        "Ventas, Cancelaciones, Cortesías y Anulaciones: getglobalcashclosing (Wansoft), el cierre de caja diario oficial -- "
        "siempre Wansoft, sin importar si la sucursal ya migró Compras/Inventario a Odoo.",
        (
            f"Meseros, Venta/Clientes por Mesero y Mix Alimentos/Bebidas: getallordenesbyday_new_venta / _new_detalleventa "
            f"(Wansoft, detalle por ticket). Cobertura real detectada para agosto en esta sucursal: "
            f"{ticket['min_fecha'] or 'sin datos'} a {ticket['max_fecha'] or 'sin datos'}"
            + (" -- mes completo." if ticket["full_coverage"] else " -- MUESTRA PARCIAL, no el mes completo. Los indicadores marcados con * están basados en esta ventana, no en los 31 días de agosto.")
        ),
        "Costo por Merma: costeomensual (Wansoft) -- siempre Wansoft, no existe un campo equivalente en el cierre diario "
        "ni se usa Odoo para este concepto, sin importar la fuente de Compras.",
    ]
    if cfg["is_odoo"]:
        notes.append(
            "Costo de Productos Vendidos y Variaciones de Inventario: Odoo en vivo, account.move.line, cuenta contable "
            "501.xx, solo movimientos contabilizados (parent_state='posted') -- porque esta sucursal ya tiene Compras/"
            "Inventario en Odoo, por regla de negocio el Costo de Productos Vendidos también se toma de ahí."
        )
    else:
        notes.append(
            "Costo de Productos Vendidos: costeomensual (Wansoft) -- esta sucursal aún no está en Odoo, así que el "
            "costo real sigue viniendo del reporte de costeo de Wansoft."
        )
    notes.append("Los % sobre venta se calculan contra Venta Neta (sin IVA), no venta bruta.")
    notes.append(
        "Cortesías/Cancelaciones/Anulaciones se muestran a precio de venta (lo que costó el descuento al cliente), no a "
        "costo de insumo -- por eso van aparte del Costo Total Operativo Teórico y no se sum an a él."
    )

    for n in notes:
        lines = wrap_text(c, n, "Times-Roman", 8.3, CONTENT_W - 14)
        c.setFillColor(DARK_TEXT)
        c.setFont("Times-Bold", 8.3)
        c.drawString(MARGIN_L, y, "\u2022")
        for line in lines:
            c.setFont("Times-Roman", 8.3)
            c.drawString(MARGIN_L + 14, y, line)
            y -= 11.5
        y -= 4

    draw_footer(c, 2, "Reporte generado automáticamente a partir de datos en vivo de Wansoft y Odoo.")
    c.showPage()
    c.save()
    print(f"  guardado: {out_path}")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_mysql_connection("wansoft")
    cur = conn.cursor()
    for cfg in COMPANIES:
        try:
            build_company_report(cfg, cur)
        except Exception as e:
            print(f"  ERROR en {cfg['key']}: {e}")
    conn.close()
    print("Listo.")
