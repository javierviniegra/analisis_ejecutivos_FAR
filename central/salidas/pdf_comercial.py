"""PDF of the commercial report on the Fonda Argentina template (reportlab).

Two letter pages per `ReporteComercial` (owner, 2026-09-30: two pages that
read better, the second with more information): page 1 has the title, the
Lectura box, the indicators table with arrow columns, the two charts and the
notes about the period's data; page 2 has the detail (per branch for a
consolidated report, per day/block for a branch) and the rules and
thresholds in two columns.

Template (same as the monthly executive PDFs): full-page brand background
(logo badge, rounded frame, watermark bottom right), brand green #10564E,
header on the right. Font: DejaVu Sans (bundled with matplotlib) because the
standard PDF fonts lack the arrow glyphs (▲ ▼), and it is the charts' font.
"""

import io
import os
from datetime import date
from pathlib import Path

import matplotlib
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from ..motor import detalle, formato
from ..motor.comparativos import BAJA, IGUAL, NARANJA, ROJO, SUBE, VERDE
from ..motor.graficas_png import dibujar
from ..motor.lectura import AVISO, NEGATIVO, POSITIVO
from ..motor.periodo import _MESES_ES
from ..motor.reporte_comercial import TITULO, ReporteComercial, filas_visibles, nombre_base
from ..motor.tabla_comercial import ENTERO, MONEDA, PORCENTAJE

FONDO = str(Path(__file__).resolve().parent / "recursos" / "fondo_fonda.jpeg")

VERDE_MARCA = HexColor("#10564E")
TEXTO = HexColor("#1A1A1A")
TEXTO_SUAVE = HexColor("#555555")
LINEA = HexColor("#CCCCCC")
FONDO_CAJA = HexColor("#F2F5F4")
COLOR_VAR = {VERDE: HexColor("#1E7B4F"), ROJO: HexColor("#B3261E")}
GRIS_VAR = HexColor("#8A8A8A")
COLOR_SEMAFORO = {VERDE: HexColor("#1E7B4F"), NARANJA: HexColor("#D9822B"), ROJO: HexColor("#B3261E")}
COLOR_TONO = {POSITIVO: HexColor("#1E7B4F"), NEGATIVO: HexColor("#B3261E"), AVISO: HexColor("#B7791F")}

ANCHO, ALTO = letter
MARGEN = 48
ANCHO_UTIL = ANCHO - 2 * MARGEN
ANCHO_NOTAS = ANCHO_UTIL - 70  # keep clear of the watermark in the bottom-right corner
Y_MIN = 34
Y_INICIO = ALTO - 134  # content starts below the logo badge

F, FB, FI = "DejaVuSans", "DejaVuSans-Bold", "DejaVuSans-Oblique"


def _registrar_fuentes():
    if F in pdfmetrics.getRegisteredFontNames():
        return
    carpeta = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
    for nombre, archivo in ((F, "DejaVuSans.ttf"), (FB, "DejaVuSans-Bold.ttf"), (FI, "DejaVuSans-Oblique.ttf")):
        pdfmetrics.registerFont(TTFont(nombre, os.path.join(carpeta, archivo)))


def _fecha(d: date) -> str:
    return f"{d.day} de {_MESES_ES[d.month - 1]} de {d.year}"


def _renglones(c, texto: str, fuente: str, tam: float, ancho: float) -> list[str]:
    renglones, actual = [], ""
    for palabra in texto.split(" "):
        prueba = f"{actual} {palabra}".strip()
        if c.stringWidth(prueba, fuente, tam) <= ancho or not actual:
            actual = prueba
        else:
            renglones.append(actual)
            actual = palabra
    if actual:
        renglones.append(actual)
    return renglones


def _pagina(c):
    c.drawImage(FONDO, 0, 0, width=ANCHO, height=ALTO, preserveAspectRatio=False)
    c.setFont(F, 7.5)
    c.setFillColor(TEXTO)
    c.drawRightString(ANCHO - MARGEN, ALTO - 50, "Fonda Argentina · Central de Reportes")
    c.setFillColor(TEXTO_SUAVE)
    c.drawRightString(ANCHO - MARGEN, ALTO - 61, f"Generado el {_fecha(date.today())}")


def _titulo(c, r: ReporteComercial, y: float) -> float:
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 15)
    nombre = r.nombre if r.nombre != "Consolidado" else f"Consolidado ({len(r.sucursales)} sucursales)"
    c.drawString(MARGEN, y, f"{TITULO} · {nombre}")
    y -= 15
    c.setFillColor(TEXTO)
    c.setFont(F, 9)
    p = r.periodo
    c.drawString(MARGEN, y, f"{p.etiqueta()}  ({p.desde:%d/%m/%Y} al {p.hasta:%d/%m/%Y})")
    y -= 11
    c.setFillColor(TEXTO_SUAVE)
    c.setFont(F, 7.5)
    ant = p.anterior().etiqueta()
    anio = p.mismo_periodo_anio_anterior()
    comparado = ant if anio is None or anio == p.anterior() else f"{ant} y {anio.etiqueta()}"
    c.drawString(MARGEN, y, f"Comparado con: {comparado}")
    return y - 12


def _lectura(c, r: ReporteComercial, y: float) -> float:
    tam, interlinea, sangria = 7.8, 9.8, 12
    bloques = [(o, _renglones(c, o.texto, F, tam, ANCHO_UTIL - 20 - sangria)) for o in r.lectura.observaciones]
    alto = 20 + sum(len(rs) * interlinea + 2.5 for _, rs in bloques) + 3
    c.setFillColor(FONDO_CAJA)
    c.roundRect(MARGEN, y - alto, ANCHO_UTIL, alto, 6, fill=1, stroke=0)
    c.setFillColor(VERDE_MARCA)
    c.rect(MARGEN, y - alto, 3, alto, fill=1, stroke=0)
    c.setFont(FB, 9.5)
    c.drawString(MARGEN + 12, y - 14, r.lectura.titulo)
    yy = y - 26
    for obs, renglones in bloques:
        c.setFillColor(COLOR_TONO.get(obs.tono, GRIS_VAR))
        c.circle(MARGEN + 15, yy + 2.8, 2.3, fill=1, stroke=0)
        c.setFillColor(TEXTO)
        c.setFont(F, tam)
        for renglon in renglones:
            c.drawString(MARGEN + 12 + sangria, yy, renglon)
            yy -= interlinea
        yy -= 2.5
    return y - alto - 8


def _flecha(c, x: float, y: float, direccion: str, color):
    """Filled triangle as the arrow (the colour carries the good/bad meaning)."""
    c.setFillColor(color)
    p = c.beginPath()
    if direccion == SUBE:
        p.moveTo(x, y), p.lineTo(x + 6, y), p.lineTo(x + 3, y + 5.5)
    else:
        p.moveTo(x, y + 5.5), p.lineTo(x + 6, y + 5.5), p.lineTo(x + 3, y)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def _variacion(c, x_der: float, y: float, var, fmt: str):
    texto = formato.variacion(var, fmt)
    if var.direccion in (SUBE, BAJA):
        cifra = texto.split(" ", 1)[1]  # "▲ +5.0%" -> "+5.0%"
        c.setFillColor(TEXTO)
        c.setFont(F, 7.6)
        c.drawRightString(x_der, y, cifra)
        _flecha(c, x_der - c.stringWidth(cifra, F, 7.6) - 9, y, var.direccion, COLOR_VAR.get(var.color, GRIS_VAR))
    else:
        c.setFillColor(GRIS_VAR)
        c.setFont(F, 7.6)
        c.drawRightString(x_der, y, texto if var.direccion == IGUAL else var.simbolo)


def _tabla(c, r: ReporteComercial, y: float) -> float:
    columnas = [170, 80, 80, 53, 80, 53]  # indicator, period, previous, var, last year, var (= ANCHO_UTIL)
    alto = 10.4
    x = [MARGEN]
    for w in columnas:
        x.append(x[-1] + w)
    c.setFillColor(VERDE_MARCA)
    c.rect(MARGEN, y - alto + 2.5, ANCHO_UTIL, alto + 1, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FB, 7.4)
    c.drawString(x[0] + 5, y - 6, "Indicador")
    for i, h in ((1, "Periodo"), (2, "Anterior"), (3, "Var."), (4, "Año anterior"), (5, "Var.")):
        c.drawRightString(x[i + 1] - 5, y - 6, h)
    y -= alto + 1
    seccion, par = None, False
    for f in filas_visibles(r.filas):
        if f.indicador.seccion != seccion:
            seccion = f.indicador.seccion
            c.setFillColor(VERDE_MARCA)
            c.setFont(FB, 7.2)
            c.drawString(x[0] + 5, y - 6.5, seccion)
            y -= alto - 1
            par = False
        if par:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - alto + 2.5, ANCHO_UTIL, alto, fill=1, stroke=0)
        par = not par
        fmt = f.indicador.formato
        base = y - 6.5
        c.setFillColor(TEXTO)
        c.setFont(F, 7.6)
        c.drawString(x[0] + 11, base, f.etiqueta)
        for i, v in ((1, f.actual), (2, f.anterior), (4, f.anio_anterior)):
            c.setFont(FB if i == 1 else F, 7.6)
            c.setFillColor(TEXTO if i == 1 else TEXTO_SUAVE)
            c.drawRightString(x[i + 1] - 5, base, formato.valor(v, fmt))
        if f.semaforo:  # target indicator: coloured dot before the period's value
            ancho_valor = c.stringWidth(formato.valor(f.actual, fmt), FB, 7.6)
            c.setFillColor(COLOR_SEMAFORO[f.semaforo])
            c.circle(x[2] - 5 - ancho_valor - 6, base + 2.6, 2.4, fill=1, stroke=0)
        _variacion(c, x[4] - 5, base, f.var_anterior, fmt)
        _variacion(c, x[6] - 5, base, f.var_anio, fmt)
        y -= alto
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.5)
    c.line(MARGEN, y + 2.5, MARGEN + ANCHO_UTIL, y + 2.5)
    return y - 8


def _graficas(c, r: ReporteComercial, y: float) -> float:
    separacion = 12
    ancho = (ANCHO_UTIL - separacion) / 2
    for i, g in enumerate(r.graficas[:2]):
        imagen = ImageReader(io.BytesIO(dibujar(g)))
        iw, ih = imagen.getSize()
        alto = ancho * ih / iw
        c.drawImage(imagen, MARGEN + i * (ancho + separacion), y - alto, width=ancho, height=alto)
    return y - alto - 6


def _nota(c, texto: str, x: float, y: float, ancho: float, tam: float, interlinea: float) -> float:
    renglones = _renglones(c, texto, FI, tam, ancho - 8)
    c.setFillColor(TEXTO_SUAVE)
    c.setFont(FI, tam)
    c.drawString(x, y, "•")
    for renglon in renglones:
        c.drawString(x + 8, y, renglon)
        y -= interlinea
    return y - 1.2


def _nueva_pagina(c) -> float:
    c.showPage()
    _pagina(c)
    return Y_INICIO


def _notas(c, r: ReporteComercial, y: float) -> None:
    """Page 1: the notes about this period's data (they explain its figures)."""
    if not r.cobertura:
        return
    tam, interlinea = 5.9, 6.8
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 7)
    c.drawString(MARGEN, y, "Notas")
    y -= 9
    for nota in r.cobertura:
        if y - len(_renglones(c, nota, FI, tam, ANCHO_NOTAS - 8)) * interlinea < Y_MIN:
            y = _nueva_pagina(c)
        y = _nota(c, nota, MARGEN, y, ANCHO_NOTAS, tam, interlinea)


def _encabezado_tabla(c, x: list[float], y: float, titulos: list[str], alto: float) -> float:
    c.setFillColor(VERDE_MARCA)
    c.rect(MARGEN, y - alto + 2.5, ANCHO_UTIL, alto + 1, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FB, 7.4)
    c.drawString(x[0] + 5, y - 6, titulos[0])
    for i, t in enumerate(titulos[1:], start=1):
        c.drawRightString(x[i + 1] - 5, y - 6, t)
    return y - alto - 1


def _celdas(c, x: list[float], base: float, valores: list[str], negrita: bool = False):
    c.setFillColor(TEXTO)
    c.setFont(FB if negrita else F, 7.6)
    c.drawString(x[0] + 5, base, valores[0])
    for i, v in enumerate(valores[1:], start=1):
        if v is not None:
            c.drawRightString(x[i + 1] - 5, base, v)


def _columnas(anchos: list[float]) -> list[float]:
    x = [MARGEN]
    for w in anchos:
        x.append(x[-1] + w)
    return x


def _pct_con_punto(c, x_der: float, base: float, pct, color, negrita: bool, marca: str = ""):
    texto = formato.valor(pct, PORCENTAJE) + marca if pct is not None else "—"
    fuente = FB if negrita else F
    c.setFillColor(TEXTO)
    c.setFont(fuente, 7.6)
    c.drawRightString(x_der, base, texto)
    if color:
        c.setFillColor(COLOR_SEMAFORO[color])
        c.circle(x_der - c.stringWidth(texto, fuente, 7.6) - 6, base + 2.6, 2.4, fill=1, stroke=0)


def _detalle_sucursales(c, r: ReporteComercial, y: float) -> float:
    alto = 11.0
    costos = r.incluir_costos
    x = _columnas([138, 86, 56, 58, 72, 53, 53] if costos else [178, 106, 76, 78, 78])  # = ANCHO_UTIL
    y = _encabezado_tabla(c, x, y, ["Sucursal", "Venta bruta", "Var.", "Clientes", "Cheque prom."]
                          + (["Costo total", "Costo fact."] if costos else []), alto)
    filas, total = detalle.por_sucursal(r)
    for i, f in enumerate(filas + [total]):
        es_total = f is total
        if es_total:
            c.setStrokeColor(LINEA)
            c.line(MARGEN, y + 2.5, MARGEN + ANCHO_UTIL, y + 2.5)
        elif i % 2:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - alto + 2.5, ANCHO_UTIL, alto, fill=1, stroke=0)
        base = y - 6.5
        _celdas(c, x, base, [f.nombre, formato.valor(f.venta_bruta, MONEDA), None, formato.valor(f.clientes, ENTERO),
                             formato.valor(f.cheque_promedio, MONEDA)] + [None, None] * costos, negrita=es_total)
        _variacion(c, x[3] - 5, base, f.var_anterior, MONEDA)
        if costos:
            _pct_con_punto(c, x[6] - 5, base, f.pct_costo_total, f.semaforo_total, es_total,
                           "*" if f.costo_total_estimado else "")
            _pct_con_punto(c, x[7] - 5, base, f.pct_costo, f.semaforo, es_total)
        y -= alto
    if costos and total.costo_total_estimado:
        c.setFillColor(TEXTO)
        c.setFont(F, 6.6)
        c.drawRightString(MARGEN + ANCHO_UTIL, y - 5, "* costo total estimado (Odoo aún no factura todo el periodo)")
        y -= 10
    return y - 6


def _detalle_periodo(c, r: ReporteComercial, y: float) -> float:
    alto = 10.4
    compara = detalle.compara_con_anterior(r)
    anchos = [86, 96, 60, 64, 76, 82, 52] if compara else [120, 120, 90, 90, 96]  # = ANCHO_UTIL
    x = _columnas(anchos)
    titulos = ["Día" if detalle.granularidad(r.periodo) == "dia" else "Periodo", "Venta bruta", "Tickets",
               "Clientes", "Cheque prom."] + (["Anterior", "Var."] if compara else [])
    y = _encabezado_tabla(c, x, y, titulos, alto)
    for i, f in enumerate(detalle.por_periodo(r)):
        if i % 2:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - alto + 2.5, ANCHO_UTIL, alto, fill=1, stroke=0)
        base = y - 6.5
        valores = [f.etiqueta.replace(chr(10), " "), formato.valor(f.venta_bruta, MONEDA),
                   formato.valor(f.tickets, ENTERO), formato.valor(f.clientes, ENTERO),
                   formato.valor(f.cheque_promedio, MONEDA)]
        if compara:
            valores += [formato.valor(f.venta_anterior, MONEDA), None]
        _celdas(c, x, base, valores)
        if compara:
            _variacion(c, x[7] - 5, base, f.var_anterior, MONEDA)
        y -= alto
    return y - 6


def _reglas(c, r: ReporteComercial, y: float) -> None:
    """The fixed rules and thresholds, in two columns."""
    tam, interlinea = 6.2, 7.4
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 8)
    c.drawString(MARGEN, y, "Reglas y umbrales del reporte")
    y -= 11
    separacion = 12
    ancho = (ANCHO_NOTAS - separacion) / 2
    mitad = (len(r.reglas) + 1) // 2
    columnas = [r.reglas[:mitad], r.reglas[mitad:]]
    alto = max(sum(len(_renglones(c, t, FI, tam, ancho - 8)) * interlinea + 1.2 for t in col) for col in columnas)
    if y - alto < Y_MIN:
        y = _nueva_pagina(c)
    for i, col in enumerate(columnas):
        yy = y
        for regla in col:
            yy = _nota(c, regla, MARGEN + i * (ancho + separacion), yy, ancho, tam, interlinea)


def _pagina_detalle(c, r: ReporteComercial) -> None:
    """Page 2: detail per branch (consolidated) or per day/block (branch), then the rules."""
    _pagina(c)
    y = Y_INICIO
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 13)
    nombre = r.nombre if r.nombre != "Consolidado" else f"Consolidado ({len(r.sucursales)} sucursales)"
    c.drawString(MARGEN, y, f"Detalle · {nombre}")
    c.setFillColor(TEXTO_SUAVE)
    c.setFont(F, 8)
    c.drawString(MARGEN, y - 12, r.periodo.etiqueta())
    y -= 26
    titulo = "Por sucursal" if r.por_sucursal else "Por día" if detalle.granularidad(r.periodo) == "dia" else "Por periodo"
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 9)
    c.drawString(MARGEN, y, titulo)
    y -= 6
    y = _detalle_sucursales(c, r, y) if r.por_sucursal else _detalle_periodo(c, r, y)
    _reglas(c, r, y - 8)


def generar(reportes: list[ReporteComercial]) -> bytes:
    """One PDF with two pages per report: the report, and its detail with the rules."""
    _registrar_fuentes()
    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=letter)
    c.setTitle(TITULO)
    c.setAuthor("Fonda Argentina · Central de Reportes")
    for r in reportes:
        _pagina(c)
        y = _titulo(c, r, Y_INICIO)
        y = _lectura(c, r, y)
        y = _tabla(c, r, y)
        y = _graficas(c, r, y)
        _notas(c, r, y)
        c.showPage()
        _pagina_detalle(c, r)
        c.showPage()
    c.save()
    return salida.getvalue()


def nombre_archivo(reportes: list[ReporteComercial]) -> str:
    return nombre_base(reportes) + ".pdf"
