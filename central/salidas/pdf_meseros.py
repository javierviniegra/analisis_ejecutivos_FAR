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
from .pdf_comercial import (ANCHO_UTIL, COLOR_SEMAFORO, F, FB, FONDO_CAJA, LINEA, MARGEN, TEXTO, TEXTO_SUAVE,
                            VERDE_MARCA, Y_INICIO, Y_MIN, _columnas, _encabezado_tabla, _graficas, _lectura,
                            _nueva_pagina, _notas, _pagina, _registrar_fuentes, _reglas, _tabla, _titulo, _variacion)

TAM = 6.8  # the waiters' table has many columns


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


def _detalle_meseros(c, r: ReporteMeseros, y: float) -> float:
    alto = 10.2
    x = _columnas([96, 22, 30, 30, 58, 52, 52, 32, 32, 40, 24, 48])  # = ANCHO_UTIL (516)
    y = _encabezado_tabla(c, x, y, ["Mesero", "Días", "Mesas", "Pers.", "Venta", "Venta/día", "Cheque",
                                    "% Beb.", "Prop.", "Cortesías", "Min.", "Var."], alto)
    total = r.actual.total
    filas = [(f.nombre[:22], f.m, f.semaforo_cheque, f.var_venta_dia) for f in r.detalle]
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
        cheque = formato.valor(m.cheque_promedio, MONEDA)
        _fila(c, x, base, [nombre, formato.valor(m.dias, ENTERO) if not es_total else "", formato.valor(m.cuentas, ENTERO),
                           formato.valor(m.personas, ENTERO), formato.valor(m.venta_bruta, MONEDA),
                           formato.valor(m.venta_por_dia, MONEDA), cheque, formato.valor(m.pct_bebidas, PORCENTAJE),
                           formato.valor(m.pct_propina, PORCENTAJE), formato.valor(m.cortesias, MONEDA),
                           formato.valor(m.tiempo_mesa, ENTERO), None], negrita=es_total)
        _punto(c, x[7] - 4, base, cheque, sem, es_total)
        if var is not None:
            _variacion(c, x[12] - 4, base, var, MONEDA)
        y -= alto
    c.setFillColor(TEXTO_SUAVE)
    c.setFont(F, 6.2)
    c.drawString(MARGEN, y - 3, "Venta/día = venta ÷ días trabajados · Var. = venta por día vs el periodo anterior · "
                 "Min. = tiempo promedio de mesa.")
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


def _pagina_detalle(c, r: ReporteMeseros) -> None:
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
    _reglas(c, r, y - 8)


def generar(reportes: list[ReporteMeseros]) -> bytes:
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


def nombre_archivo(reportes: list[ReporteMeseros]) -> str:
    return nombre_base(reportes) + ".pdf"

