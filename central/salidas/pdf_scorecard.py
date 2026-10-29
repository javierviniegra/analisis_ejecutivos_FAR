"""PDF of the "Semáforos scorecard" on the Fonda Argentina template (reportlab).

Two letter pages per report: page 1 the scorecard (rows Category > KPI;
columns Actual, Mes anterior, Meta, Estado, as Power BI's "Resultados KPI's");
page 2 the rule of every KPI. Template, fonts and colours are the commercial
report's (`pdf_comercial`, reused as is).
"""

import io

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..motor import formato
from ..motor import scorecard as sc
from ..motor.periodo import TipoPeriodo, _MESES_ES
from ..motor.reporte_scorecard import ReporteScorecard
from ..motor.tabla_comercial import ENTERO, MONEDA, PORCENTAJE
from .pdf_comercial import (COLOR_SEMAFORO, F, FB, FI, FONDO_CAJA, LINEA, MARGEN, ANCHO_UTIL, TEXTO, TEXTO_SUAVE,
                            VERDE_MARCA, Y_INICIO, _aviso, _columnas, _encabezado_tabla, _pagina, _registrar_fuentes,
                            _renglones)

TITULO = "Semáforos scorecard"
GRIS = HexColor("#9A9A9A")
FORMATOS = {sc.DINERO: MONEDA, sc.PORCENTAJE: PORCENTAJE, sc.NUMERO: ENTERO}
PALABRA = {"verde": "Verde", "naranja": "Naranja", "rojo": "Rojo"}
ALTO_FILA = 13.2


def _rango(p) -> str:
    if p.tipo == TipoPeriodo.MES:
        return f"{_MESES_ES[p.desde.month - 1].capitalize()} {p.desde.year}"
    mes = _MESES_ES[p.hasta.month - 1]
    return f"{p.desde.day} al {p.hasta.day} de {mes} de {p.hasta.year}"


def _titulo(c, r: ReporteScorecard, y: float) -> float:
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 15)
    nombre = r.nombre if r.nombre != "Consolidado" else f"Consolidado ({len(r.sucursales)} sucursales)"
    c.drawString(MARGEN, y, f"{TITULO} · {nombre}")
    y -= 15
    p = r.periodos
    c.setFillColor(TEXTO)
    c.setFont(F, 9)
    c.drawString(MARGEN, y, f"{'Mes cerrado' if p.actual.tipo == TipoPeriodo.MES else 'Mes en curso'}: "
                            f"{_rango(p.actual)}")
    y -= 11
    c.setFillColor(TEXTO_SUAVE)
    c.setFont(F, 7.5)
    c.drawString(MARGEN, y, f"Mes anterior: {_rango(p.mes_anterior)}  ·  Meta de ventas, cheque, ticket y clientes: "
                            f"{_rango(p.anio_anterior)} +5%")
    y -= 12
    if p.mes_cerrado:
        y = _aviso(c, "Primer lunes del mes: se reporta el mes anterior completo. Desde el próximo lunes, el mes en "
                      "curso.", y + 2)
    if r.meta_mes_anterior:
        y = _aviso(c, "Sin año anterior (sucursal nueva): su meta es el mes anterior +5%. "
                      + ", ".join(r.meta_mes_anterior) + ".", y + 2)
    if r.sin_meta:
        y = _aviso(c, "Sin año anterior ni mes anterior: fuera de las metas de ventas, cheque, ticket y clientes. "
                      + ", ".join(r.sin_meta) + ".", y + 2)
    return y


def _estado(c, x: float, base: float, fila: sc.Fila):
    clave = fila.kpi.clave
    if clave in sc.KPIS_SIN_FUENTE or fila.estado is None:
        c.setFillColor(GRIS)
        c.setFont(FI, 7.2)
        texto = ("sin fuente" if clave in sc.KPIS_SIN_FUENTE
                 else "pendiente" if clave not in sc.KPIS_VENTAS else "sin dato")
        c.drawString(x + 14, base, texto)
        return
    c.setFillColor(COLOR_SEMAFORO[fila.estado])
    c.circle(x + 7, base + 2.6, 3.6, fill=1, stroke=0)
    c.setFillColor(TEXTO)
    c.setFont(FB, 7.4)
    c.drawString(x + 14, base, PALABRA[fila.estado])


def _tabla(c, r: ReporteScorecard, y: float) -> float:
    x = _columnas([ANCHO_UTIL - 4 * 82, 82, 82, 82, 82])
    y = _encabezado_tabla(c, x, y, ["KPI", "Actual", "Mes anterior", "Meta", ""], 14)
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 7.4)
    c.setFillColor(HexColor("#FFFFFF"))
    c.drawString(x[4] + 14, y + 9, "Estado")
    for categoria in sc.CATEGORIAS:
        c.setFillColor(FONDO_CAJA)
        c.rect(MARGEN, y - ALTO_FILA + 3, ANCHO_UTIL, ALTO_FILA, fill=1, stroke=0)
        c.setFillColor(VERDE_MARCA)
        c.setFont(FB, 7.8)
        c.drawString(x[0] + 5, y - 6.5, categoria)
        y -= ALTO_FILA
        for fila in [f for f in r.filas if f.kpi.categoria == categoria]:
            base = y - 6.5
            leida = fila.kpi.clave in sc.KPIS_VENTAS
            fmt = FORMATOS[fila.kpi.tipo]
            c.setFillColor(TEXTO if leida else GRIS)
            c.setFont(F, 7.6)
            c.drawString(x[0] + 12, base, fila.kpi.nombre)
            valores = (fila.actual, fila.mes_anterior, fila.meta)
            for i, v in enumerate(valores, start=1):
                if v is None and not (i == 3 and fila.meta is not None):
                    texto = formato.SIN_DATO
                else:
                    texto = formato.valor(v, fmt)
                c.drawRightString(x[i + 1] - 5, base, texto)
            _estado(c, x[4], base, fila)
            c.setStrokeColor(LINEA)
            c.setLineWidth(0.3)
            c.line(MARGEN, y - ALTO_FILA + 3, MARGEN + ANCHO_UTIL, y - ALTO_FILA + 3)
            y -= ALTO_FILA
    return y - 6


def _notas(c, r: ReporteScorecard, y: float) -> None:
    notas = [
        "Ventas y cheque con IVA, de las cuentas de Wansoft. Cheque = venta / personas de todos los canales; "
        "ticket = venta / cuentas; clientes = personas de las órdenes de restaurante (sin delivery ni para llevar); "
        "mix = venta de bebidas / venta de alimentos y bebidas.",
        "Sin fuente: KPIs cuya fuente (Zenput, Excel de SharePoint, Google) aún no lee la Central de Reportes. "
        "Pendiente: costo y gastos, en construcción.",
    ]
    if r.nombre == "Consolidado":
        notas.append("Consolidado: el semáforo de ventas, cheque, ticket y clientes compara solo las sucursales con "
                     "meta (año anterior o, si son nuevas, mes anterior).")
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 8.5)
    c.drawString(MARGEN, y, "Notas")
    y -= 11
    c.setFillColor(TEXTO_SUAVE)
    for nota in notas:
        for renglon in _renglones(c, "• " + nota, F, 7, ANCHO_UTIL - 70):
            c.setFont(F, 7)
            c.drawString(MARGEN, y, renglon)
            y -= 9
        y -= 2


def _reglas(c, r: ReporteScorecard) -> None:
    y = Y_INICIO
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 13)
    c.drawString(MARGEN, y, f"Reglas de los semáforos · {r.nombre}")
    y -= 18
    for categoria in sc.CATEGORIAS:
        c.setFillColor(VERDE_MARCA)
        c.setFont(FB, 8.5)
        c.drawString(MARGEN, y, categoria)
        y -= 11
        for k in [k for k in sc.KPIS if k.categoria == categoria]:
            texto = sc.regla_texto(k) + (" (Sin fuente por ahora.)" if k.clave in sc.KPIS_SIN_FUENTE else "")
            renglones = _renglones(c, texto, F, 7, ANCHO_UTIL - 230)
            c.setFillColor(TEXTO)
            c.setFont(FB, 7)
            c.drawString(MARGEN + 6, y, k.nombre)
            c.setFont(F, 7)
            c.setFillColor(TEXTO_SUAVE)
            for renglon in renglones:
                c.drawString(MARGEN + 200, y, renglon)
                y -= 8.6
            y -= 2.5
        y -= 5


def generar(reportes: list[ReporteScorecard]) -> bytes:
    _registrar_fuentes()
    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=letter)
    c.setTitle(TITULO)
    c.setAuthor("Fonda Argentina · Central de Reportes")
    for r in reportes:
        _pagina(c)
        y = _titulo(c, r, Y_INICIO)
        y = _tabla(c, r, y)
        _notas(c, r, y)
        c.showPage()
        _pagina(c)
        _reglas(c, r)
        c.showPage()
    c.save()
    return salida.getvalue()
