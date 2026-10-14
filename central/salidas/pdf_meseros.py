"""PDF of the waiters' report: the commercial report's template and layout
(page 1: title, Lectura, indicators table, two charts, notes; page 2:
detail and rules), reusing its drawing pieces. Page 2 is the waiters'
ranking for a branch, or one row per branch for a consolidated report."""

import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..motor import formato
from ..motor.meseros import nombre_corto
from ..motor.reporte_meseros import TITULO, ReporteMeseros, nombre_base
from ..motor.tabla_comercial import ENTERO, MONEDA, PORCENTAJE
from ..motor.comparativos import BAJA, SUBE
from .pdf_comercial import (ANCHO_UTIL, COLOR_SEMAFORO, COLOR_VAR, F, FB, FONDO_CAJA, GRIS_VAR, LINEA, MARGEN, TEXTO,
                            TEXTO_SUAVE, VERDE_MARCA, Y_INICIO, Y_MIN, _alto_notas, _columnas, _encabezado_tabla, _flecha,
                            _graficas, _lectura, _nueva_pagina, _notas, _pagina, _registrar_fuentes, _reglas, _tabla,
                            _titulo, _variacion)

TAM = 6.6  # the waiters' table has many columns
POR_RENGLON = 4  # panel cards per row
ALTO_REGLAS = 150  # room the rules block needs (two columns; ~140 pt measured)


def _pesos(v) -> str:
    """Whole pesos in the waiters' table ($115,543 instead of $115,543.00): it has many columns."""
    return f"${v:,.0f}" if v is not None else "—"


def _fila(c, x: list[float], base: float, valores: list, negrita: bool = False):
    c.setFillColor(TEXTO)
    c.setFont(FB if negrita else F, TAM)
    c.drawString(x[0] + 4, base, valores[0])
    for i, v in enumerate(valores[1:], start=1):
        if v is not None:
            c.drawRightString(x[i + 1] - 4, base, v)


def _punto(c, x_der: float, base: float, texto: str, color: str | None, negrita: bool):
    if color:
        c.setFillColor(COLOR_SEMAFORO[color])
        c.circle(x_der - c.stringWidth(texto, FB if negrita else F, TAM) - 5, base + 2.4, 2.1, fill=1, stroke=0)


def _panel(c, r: ReporteMeseros, y: float) -> float:
    """Big cards with the main figures and their arrow vs the previous period,
    POR_RENGLON cards per row (7 cards: 4 + 3)."""
    sep, alto = 8, 46
    ancho = (ANCHO_UTIL - sep * (POR_RENGLON - 1)) / POR_RENGLON
    for i, f in enumerate(r.panel):
        if i and i % POR_RENGLON == 0:
            y -= alto + 6
        x = MARGEN + (i % POR_RENGLON) * (ancho + sep)
        c.setFillColor(FONDO_CAJA)
        c.roundRect(x, y - alto, ancho, alto, 6, fill=1, stroke=0)
        c.setFillColor(VERDE_MARCA)
        c.rect(x, y - alto + 6, 2.5, alto - 12, fill=1, stroke=0)
        c.setFillColor(TEXTO_SUAVE)
        c.setFont(F, 6.8)
        c.drawString(x + 9, y - 12, f.etiqueta)
        texto = _pesos(f.actual) if f.indicador.formato == MONEDA else formato.valor(f.actual, f.indicador.formato)
        c.setFillColor(VERDE_MARCA)
        c.setFont(FB, 14 if c.stringWidth(texto, FB, 14) < ancho - 14 else 11.5)
        c.drawString(x + 9, y - 28, texto)
        var = f.var_anterior
        base = y - alto + 8
        if var.direccion in (SUBE, BAJA):
            _flecha(c, x + 9, base, var.direccion, COLOR_VAR.get(var.color, GRIS_VAR))
            c.setFillColor(COLOR_VAR.get(var.color, GRIS_VAR))
            c.setFont(FB, 7.6)
            cifra = f"{var.porcentaje * 100:+.1f}%"
            c.drawString(x + 18, base, cifra)
            c.setFillColor(TEXTO_SUAVE)
            c.setFont(F, 6)
            c.drawString(x + 21 + c.stringWidth(cifra, FB, 7.6), base, "vs anterior")
        else:
            c.setFillColor(GRIS_VAR)
            c.setFont(F, 7)
            c.drawString(x + 9, base, formato.variacion(var, f.indicador.formato))
    return y - alto - 10


def _detalle_meseros(c, r: ReporteMeseros, y: float) -> float:
    alto = 10.2
    x = _columnas([94, 22, 30, 30, 50, 44, 46, 32, 30, 38, 32, 22, 46])  # = ANCHO_UTIL (516)
    y = _encabezado_tabla(c, x, y, ["Mesero", "Días", "Mesas", "Pers.", "Venta", "Venta/día", "Cheque",
                                    "% Beb.", "Prop.", "Cortesías", "Desc.", "Min.", "Var."], alto)
    total = r.actual.total
    filas = [(f.nombre[:23], f.m, f.semaforo_cheque, f.var_venta_dia) for f in r.detalle]
    for i, (nombre, m, sem, var) in enumerate(filas + [("Total", total, None, None)]):
        es_total = nombre == "Total" and m is total
        if y - alto < Y_MIN:
            y = _nueva_pagina(c)
        if es_total:
            c.setStrokeColor(LINEA)
            c.line(MARGEN, y + 2.5, MARGEN + ANCHO_UTIL, y + 2.5)
        elif i % 2:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - alto + 2.5, ANCHO_UTIL, alto, fill=1, stroke=0)
        base = y - 6.4
        cheque = _pesos(m.cheque_promedio)
        _fila(c, x, base, [nombre, formato.valor(m.dias, ENTERO) if not es_total else "", formato.valor(m.cuentas, ENTERO),
                           formato.valor(m.personas, ENTERO), _pesos(m.venta_bruta), _pesos(m.venta_por_dia), cheque, formato.valor(m.pct_bebidas, PORCENTAJE),
                           formato.valor(m.pct_propina, PORCENTAJE), _pesos(m.cortesias), _pesos(m.descuentos),
                           formato.valor(m.tiempo_mesa, ENTERO), None], negrita=es_total)
        _punto(c, x[7] - 4, base, cheque, sem, es_total)
        if var is not None:
            _variacion(c, x[13] - 4, base, var, MONEDA)
        y -= alto
    c.setFillColor(TEXTO_SUAVE)
    c.setFont(F, 6.2)
    c.drawString(MARGEN, y - 3, "Venta/día = venta ÷ días trabajados · Var. = venta por día vs el periodo anterior · "
                 "Min. = tiempo promedio de mesa · Cortesías a precio de venta · Desc. = descuentos.")
    c.drawString(MARGEN, y - 11, "Punto del cheque: verde igual o arriba del promedio de la sucursal, naranja abajo, "
                 "rojo más de 10% abajo.")
    return y - 22


def _detalle_sucursales(c, r: ReporteMeseros, y: float) -> float:
    alto = 10.6
    x = _columnas([104, 40, 38, 72, 66, 52, 40, 36, 68])  # = ANCHO_UTIL (516)
    y = _encabezado_tabla(c, x, y, ["Sucursal", "Meseros", "Mesas", "Venta salón", "Venta/mes./día", "Cheque",
                                    "% Beb.", "Prop.", "Mejor mesero"], alto)
    for i, f in enumerate(r.por_sucursal):
        if i % 2:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - alto + 2.5, ANCHO_UTIL, alto, fill=1, stroke=0)
        t = f.d.total
        mejor = nombre_corto(f.mejor) if f.mejor else "—"
        _fila(c, x, y - 6.6, [f.nombre[:26], str(f.d.plantilla), formato.valor(t.cuentas, ENTERO),
                              formato.valor(t.venta_bruta, MONEDA), formato.valor(f.d.venta_por_mesero_dia, MONEDA),
                              formato.valor(t.cheque_promedio, MONEDA), formato.valor(t.pct_bebidas, PORCENTAJE),
                              formato.valor(t.pct_propina, PORCENTAJE), mejor])
        y -= alto
    t = r.actual.total
    c.setStrokeColor(LINEA)
    c.line(MARGEN, y + 2.5, MARGEN + ANCHO_UTIL, y + 2.5)
    _fila(c, x, y - 6.6, ["Total", str(r.actual.plantilla), formato.valor(t.cuentas, ENTERO),
                          formato.valor(t.venta_bruta, MONEDA), formato.valor(r.actual.venta_por_mesero_dia, MONEDA),
                          formato.valor(t.cheque_promedio, MONEDA), formato.valor(t.pct_bebidas, PORCENTAJE),
                          formato.valor(t.pct_propina, PORCENTAJE), ""], negrita=True)
    return y - alto - 8


def _pagina_detalle(c, r: ReporteMeseros, notas_pendientes: list[str] = ()) -> None:
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
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 9)
    c.drawString(MARGEN, y, "Por sucursal" if r.por_sucursal else "Por mesero (de mayor a menor venta)")
    y -= 6
    y = _detalle_sucursales(c, r, y) if r.por_sucursal else _detalle_meseros(c, r, y)
    if r.graficas:  # the charts live on page 2 (page 1 has the panel)
        if y - 150 < Y_MIN:
            y = _nueva_pagina(c)
        y = _graficas(c, r, y - 4)
    if notas_pendientes:  # page 1's notes that did not fit
        if y - _alto_notas(c, list(notas_pendientes)) < Y_MIN:
            y = _nueva_pagina(c)
        _notas(c, r, y - 4, list(notas_pendientes), "Notas (continuación)")
        y -= _alto_notas(c, list(notas_pendientes)) + 4
    if y - ALTO_REGLAS < Y_MIN:  # a long roster: the rules go whole to the next page, never their title alone
        y = _nueva_pagina(c)
    _reglas(c, r, y - 6)


def generar(reportes: list[ReporteMeseros]) -> bytes:
    _registrar_fuentes()
    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=letter)
    c.setTitle(TITULO)
    c.setAuthor("Fonda Argentina · Central de Reportes")
    for r in reportes:
        _pagina(c)
        y = _titulo(c, r, Y_INICIO)
        y = _panel(c, r, y)
        y = _lectura(c, r, y)
        y = _tabla(c, r, y)
        pendientes = _notas(c, r, y)
        c.showPage()
        _pagina_detalle(c, r, pendientes)
        c.showPage()
    c.save()
    return salida.getvalue()


def nombre_archivo(reportes: list[ReporteMeseros]) -> str:
    return nombre_base(reportes) + ".pdf"

