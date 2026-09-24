"""PDF of the commercial report on the Fonda Argentina template (reportlab).

One letter page per `ReporteComercial`: title, the Lectura box, the
indicators table with arrow columns, the two charts, and the footnotes
(coverage notes plus every rule and threshold). If the footnotes do not fit,
they continue on a second page with the same template.

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

from ..motor import formato
from ..motor.comparativos import BAJA, IGUAL, ROJO, SUBE, VERDE
from ..motor.graficas_png import dibujar
from ..motor.lectura import AVISO, NEGATIVO, POSITIVO
from ..motor.periodo import _MESES_ES
from ..motor.reporte_comercial import TITULO, ReporteComercial

FONDO = str(Path(__file__).resolve().parent / "recursos" / "fondo_fonda.jpeg")

VERDE_MARCA = HexColor("#10564E")
TEXTO = HexColor("#1A1A1A")
TEXTO_SUAVE = HexColor("#555555")
LINEA = HexColor("#CCCCCC")
FONDO_CAJA = HexColor("#F2F5F4")
COLOR_VAR = {VERDE: HexColor("#1E7B4F"), ROJO: HexColor("#B3261E")}
GRIS_VAR = HexColor("#8A8A8A")
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


def _filas_visibles(filas):
    """A section with no value at all in the period (e.g. Costo de Ventas for a
    branch that is not in Presupuestos AP) is left out of the page."""
    vacias = {f.indicador.seccion for f in filas} - {f.indicador.seccion for f in filas if f.actual is not None}
    return [f for f in filas if f.indicador.seccion not in vacias]


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
    for f in _filas_visibles(r.filas):
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
        c.drawString(x[0] + 11, base, f.indicador.etiqueta)
        for i, v in ((1, f.actual), (2, f.anterior), (4, f.anio_anterior)):
            c.setFont(FB if i == 1 else F, 7.6)
            c.setFillColor(TEXTO if i == 1 else TEXTO_SUAVE)
            c.drawRightString(x[i + 1] - 5, base, formato.valor(v, fmt))
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


def _notas(c, notas: list[str], y: float) -> None:
    tam, interlinea = 5.9, 7.0
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 7)
    c.drawString(MARGEN, y, "Notas")
    y -= 9
    for nota in notas:
        renglones = _renglones(c, nota, FI, tam, ANCHO_NOTAS - 8)
        if y - len(renglones) * interlinea < Y_MIN:  # continue on a new page with the same template
            c.showPage()
            _pagina(c)
            y = Y_INICIO
        c.setFillColor(TEXTO_SUAVE)
        c.setFont(FI, tam)
        c.drawString(MARGEN, y, "•")
        for renglon in renglones:
            c.drawString(MARGEN + 8, y, renglon)
            y -= interlinea
        y -= 1.2


def generar(reportes: list[ReporteComercial]) -> bytes:
    """One PDF with one page (or two, if the footnotes need it) per report."""
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
        _notas(c, r.notas, y)
        c.showPage()
    c.save()
    return salida.getvalue()


def _limpio(base: str) -> str:
    limpio = "".join(ch if ch.isalnum() else "_" for ch in base)
    return "_".join(p for p in limpio.split("_") if p) + ".pdf"


def nombre_archivo(reportes: list[ReporteComercial]) -> str:
    """File name: the branch (or "Consolidado"), or how many branches when
    the PDF holds one page per branch; then the period."""
    quien = reportes[0].nombre if len(reportes) == 1 else f"{len(reportes)} sucursales"
    return _limpio(f"Reporte_Comercial_{quien}_{reportes[0].periodo.etiqueta()}")
