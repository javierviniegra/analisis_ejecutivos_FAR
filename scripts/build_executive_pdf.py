"""
Reporte Ejecutivo -- Sucursal Puebla -- Agosto 2026
Genera un PDF de 1-2 paginas reusando la plantilla de marca de Fonda Argentina
(extraida de analisis_impactoCarne.pdf: logo, marco, marca de agua).
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from datetime import date

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def fecha_es(d):
    return f"{d.day} de {MESES_ES[d.month]} de {d.year}"


BRAND_GREEN = HexColor("#10564E")
DARK_TEXT = HexColor("#1A1A1A")
GREY_TEXT = HexColor("#555555")
LIGHT_LINE = HexColor("#CCCCCC")
TABLE_HEADER_BG = HexColor("#10564E")

PAGE_W, PAGE_H = letter
BG_IMAGE = "logo_extract_0.jpeg"
OUT_PATH = "Reporte_Ejecutivo_Puebla_Agosto_2026.pdf"

MARGIN_L = 60
MARGIN_R = 60
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R


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


def draw_bullet(c, x, y, bold_lead, rest, max_width, leading=12.5):
    """Bullet estilo 'Hallazgos Clave': lead en bold + texto normal, con wrap."""
    bullet_indent = 14
    c.setFillColor(DARK_TEXT)
    c.setFont("Times-Bold", 9.3)
    c.drawString(x, y, "•")

    full = bold_lead + rest
    # Construimos linea por linea combinando bold + normal
    words_bold = bold_lead.split(" ")
    words_rest = rest.split(" ")
    tokens = [(w, True) for w in words_bold] + [(w, False) for w in words_rest]

    cur_line = []
    cur_bold_flags = []
    cur_width = 0
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
    """rows: list of tuples matching col_widths length."""
    c.setFont("Times-Bold", 11)
    c.setFillColor(BRAND_GREEN)
    c.drawString(x, y, title)
    y -= 16

    row_h = 15.2
    total_w = sum(col_widths)

    if header:
        c.setFillColor(TABLE_HEADER_BG)
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
        c.setFont("Times-Roman", 8.8)
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


def build():
    c = canvas.Canvas(OUT_PATH, pagesize=letter)

    # ---------------- PAGE 1 ----------------
    draw_background(c)
    draw_header(c, "Reporte Ejecutivo -- Sucursal Puebla -- Agosto 2026")

    y = PAGE_H - 165
    c.setFont("Times-Bold", 20)
    c.setFillColor(BRAND_GREEN)
    c.drawString(MARGIN_L, y, "Puebla -- Resumen Ejecutivo de Agosto 2026")
    y -= 16
    c.setFont("Times-Italic", 9.5)
    c.setFillColor(GREY_TEXT)
    c.drawString(MARGIN_L, y, "Sucursal nueva (arranque operativo 2026-06) -- sin comparación contra año anterior")
    y -= 26

    c.setFont("Times-Bold", 12.5)
    c.setFillColor(BRAND_GREEN)
    c.drawString(MARGIN_L, y, "Resumen Ejecutivo")
    y -= 18

    bullets = [
        ("Venta sólida en el arranque: ",
         "Puebla facturó $3,724,753.95 en agosto (venta neta sin IVA: $3,210,994.63), con 4,553 clientes "
         "atendidos en 1,633 tickets -- ticket promedio de $2,280.93 y cheque promedio de $818.09 por cliente."),
        ("El costo real de materia prima está en 38.65% de la venta neta: ",
         "según contabilidad de Odoo (cuenta 501), el costo total del mes fue de $1,241,074.08. Carnes concentra "
         "más de la mitad de ese costo ($643,084.62, 52%), seguido por bebidas con y sin alcohol."),
        ("El mix de venta está dominado por Alimentos: ",
         "74.76% de la venta vino de alimentos contra 25.24% de bebidas -- consistente con una operación de "
         "cocina fuerte más que de barra."),
        ("Cancelaciones y Cortesías bajo control: ",
         "sumaron $35,779.00 combinadas (cancelaciones $10,135.00 + cortesías $25,644.00), menos del 1% de la "
         "venta total -- sin señales de descontrol operativo en el primer mes cerrado."),
        ("Productividad por mesero: ",
         "con 30 meseros distintos activos en el mes, la venta promedio por mesero fue de $124,158.47 y 151.8 "
         "clientes atendidos por mesero."),
    ]
    max_w = CONTENT_W
    for lead, rest in bullets:
        y = draw_bullet(c, MARGIN_L, y, lead, rest, max_w)
        y -= 6

    y -= 10

    # ---- Tabla Ventas ----
    col_w_ventas = [190, 130]
    y = draw_kpi_table(
        c, MARGIN_L, y, "Ventas -- Agosto 2026",
        rows=[
            ("Ventas totales (bruta, con IVA)", "$3,724,753.95"),
            ("Venta Neta (sin IVA)", "$3,210,994.63"),
            ("Clientes atendidos", "4,553"),
            ("# Tickets", "1,633"),
            ("# Mesas atendidas", "1,576"),
            ("# Clientes por Mesa", "2.89"),
            ("# Meseros distintos", "30"),
            ("Venta por Mesero", "$124,158.47"),
            ("Clientes por Mesero", "151.8"),
            ("Cheque Promedio (venta/cliente)", "$818.09"),
            ("Ticket Promedio (venta/ticket)", "$2,280.93"),
            ("Mix de ventas -- Alimentos", "74.76%"),
            ("Mix de ventas -- Bebidas", "25.24%"),
        ],
        col_widths=col_w_ventas,
    )

    y -= 14

    col_w_costos = [230, 90, 70]
    y = draw_kpi_table(
        c, MARGIN_L, y, "Costos -- Agosto 2026 (Odoo, cuenta contable 501, real)",
        header=("Concepto", "Monto", "% s/venta neta"),
        rows=[
            ("Costo de Productos Vendidos (Alimentos/Bebidas)", "$1,170,105.92", "36.44%"),
            ("Variaciones de Inventario", "$62,846.33", "1.96%"),
            ("Costo por Merma", "$8,121.83", "0.25%"),
            ("COGS TOTAL / Costo Operativo Teórico", "$1,241,074.08", "38.65%"),
        ],
        col_widths=col_w_costos,
    )

    draw_footer(c, 1,
        "Fuentes: Ventas y Cancelaciones/Cortesías -- Wansoft (cierre diario). Costos -- Odoo en vivo, cuenta contable 501, datos reales. "
        "Ver notas y fuentes detalladas en la página 2.")
    c.showPage()

    # ---------------- PAGE 2 ----------------
    draw_background(c)
    draw_header(c, "Reporte Ejecutivo -- Sucursal Puebla -- Agosto 2026")

    y = PAGE_H - 165
    c.setFont("Times-Bold", 14)
    c.setFillColor(BRAND_GREEN)
    c.drawString(MARGIN_L, y, "Desglose de Costo por Categoría")
    y -= 10

    chart_w = CONTENT_W
    chart_h = chart_w * (3.4 / 7.2)
    c.drawImage("cost_breakdown_chart.png", MARGIN_L, y - chart_h, width=chart_w, height=chart_h,
                preserveAspectRatio=True, mask='auto')
    y -= chart_h + 26

    c.setFont("Times-Bold", 12.5)
    c.setFillColor(BRAND_GREEN)
    c.drawString(MARGIN_L, y, "Notas y Fuentes de Datos")
    y -= 16

    notes = [
        "Ventas, Cancelaciones, Cortesías y Anulaciones: getglobalcashclosing (Wansoft), el cierre de caja diario "
        "oficial -- cobertura completa de los 31 días de agosto.",
        "Meseros, Venta por Mesero, Clientes por Mesero y Mix Alimentos/Bebidas: getallordenesbyday_new_venta y "
        "_new_detalleventa (Wansoft, detalle por ticket) -- cobertura completa de agosto (1-31 ago).",
        "Costo de Productos Vendidos, Variaciones de Inventario, Merma y COGS Total: Odoo en vivo, "
        "account.move.line, cuenta contable 501.xx, company_id=34 (FONDA ARGENTINA PUEBLA), solo movimientos "
        "contabilizados (parent_state='posted'). Réplica exacta del reporte \"Reportes Analíticos\" de Odoo "
        "Contabilidad, validada por el usuario.",
        "Los % sobre venta se calculan contra Venta Neta (sin IVA), no venta bruta -- por decisión del usuario, "
        "ya que así se calculan los costos contra venta en el negocio.",
        "Puebla opera con Compras e Inventario en Odoo (no en Wansoft); Ventas sí se registran en Wansoft como "
        "el resto de las sucursales.",
    ]
    for n in notes:
        lines = wrap_text(c, n, "Times-Roman", 8.3, CONTENT_W - 14)
        c.setFillColor(DARK_TEXT)
        c.setFont("Times-Bold", 8.3)
        c.drawString(MARGIN_L, y, "•")
        for i, line in enumerate(lines):
            c.setFont("Times-Roman", 8.3)
            c.drawString(MARGIN_L + 14, y, line)
            y -= 11.5
        y -= 4

    draw_footer(c, 2, "Reporte generado automáticamente a partir de datos en vivo de Wansoft y Odoo.")
    c.showPage()

    c.save()
    print(f"Guardado: {OUT_PATH}")


if __name__ == "__main__":
    build()
