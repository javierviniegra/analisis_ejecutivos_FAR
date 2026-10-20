"""Sales composition page of the commercial PDF (owner, 2026-10-20): sales by
time band, donuts of time band / payment method / platform, and bars by
weekday and by hour, against the same period last year."""

import io

from reportlab.lib.utils import ImageReader

from ..motor import formato
from ..motor.composicion import Composicion
from ..motor.graficas_png import dibujar, dibujar_dona
from ..motor.tabla_comercial import ENTERO, MONEDA, PORCENTAJE
from .pdf_comercial import (ANCHO_UTIL, F, FB, FONDO_CAJA, LINEA, MARGEN, TEXTO_SUAVE, VERDE_MARCA, Y_INICIO, Y_MIN,
                            _celdas, _columnas, _encabezado_tabla, _nota, _nueva_pagina, _pagina, _variacion)

ALTO = 11.0


def _franjas(c, k: Composicion, y: float) -> float:
    x = _columnas([62, 76, 78, 46, 48, 50, 48, 48, 60])  # = ANCHO_UTIL
    y = _encabezado_tabla(c, x, y, ["Horario", "Horas (cierre)", "Venta bruta", "% venta", "Tickets", "Clientes",
                                    "Cheque", "Ticket", "Var."], ALTO)
    for i, f in enumerate(k.franjas):
        if i % 2:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - ALTO + 2.5, ANCHO_UTIL, ALTO, fill=1, stroke=0)
        base = y - 6.5
        _celdas(c, x, base, [f.etiqueta, None, f"${f.venta:,.0f}", formato.valor(f.pct, PORCENTAJE),
                             formato.valor(f.tickets, ENTERO), formato.valor(f.clientes, ENTERO),
                             _pesos(f.cheque), _pesos(f.ticket), None])
        c.setFillColor(TEXTO_SUAVE)
        c.setFont(F, 7)
        c.drawString(x[1] + 5, base, f.horario)
        _variacion(c, x[9] - 5, base, f.var_anio, MONEDA)
        y -= ALTO
    c.setStrokeColor(LINEA)
    c.line(MARGEN, y + 1, MARGEN + ANCHO_UTIL, y + 1)
    return y - 4


def _tardes(c, k: Composicion, y: float) -> float:
    """Consolidated: branches ranked by the share of their sales made in the afternoon."""
    x = _columnas([132, 78, 56, 70, 70, 55, 55])  # = ANCHO_UTIL
    y = _encabezado_tabla(c, x, y, ["Sucursal", "Venta tarde", "% tarde", f"Vs {k.vs_anterior}", "Vs año ant.",
                                    "% mañana", "% noche"], ALTO)
    for i, f in enumerate(k.tardes):
        if y - ALTO < Y_MIN:
            y = _nueva_pagina(c)
        if i % 2:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - ALTO + 2.5, ANCHO_UTIL, ALTO, fill=1, stroke=0)
        base = y - 6.5
        _celdas(c, x, base, [f.sucursal, f"${f.venta_tarde:,.0f}", formato.valor(f.pct_tarde, PORCENTAJE), None, None,
                             formato.valor(f.pct_manana, PORCENTAJE), formato.valor(f.pct_noche, PORCENTAJE)])
        _variacion(c, x[4] - 5, base, f.var_anterior, PORCENTAJE)
        _variacion(c, x[5] - 5, base, f.var_anio, PORCENTAJE)
        y -= ALTO
    return y - 4


def _dias(c, k: Composicion, y: float) -> float:
    """Branch: an average day of each weekday by band, vs previous period and last year."""
    x = _columnas([64, 28, 54, 64, 64, 68, 50, 62, 62])  # = ANCHO_UTIL
    y = _encabezado_tabla(c, x, y, ["Día", "Días", "Mañana", "Tarde", "Noche", "Total", "% tarde", f"Vs {k.vs_anterior}",
                                    "Vs año ant."], ALTO)
    for i, f in enumerate(k.dias):
        if i % 2:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - ALTO + 2.5, ANCHO_UTIL, ALTO, fill=1, stroke=0)
        base = y - 6.5
        _celdas(c, x, base, [f.dia, str(f.dias)] + [_pesos(v) for v in f.bandas]
                + [_pesos(f.total), formato.valor(f.pct_tarde, PORCENTAJE), None, None])
        _variacion(c, x[8] - 5, base, f.var_anterior, MONEDA)
        _variacion(c, x[9] - 5, base, f.var_anio, MONEDA)
        y -= ALTO
    return y - 4


def _pesos(v) -> str:
    return "—" if v is None else f"${v:,.0f}"


def _imagenes(c, pngs: list[bytes], y: float, separacion: float = 10) -> float:
    ancho = (ANCHO_UTIL - separacion * (len(pngs) - 1)) / len(pngs)
    altos = []
    for png in pngs:
        iw, ih = ImageReader(io.BytesIO(png)).getSize()
        altos.append(ancho * ih / iw)
    if altos and y - max(altos) < Y_MIN:  # a row of charts never splits: next page
        y = _nueva_pagina(c)
    alto_max = 0
    for i, png in enumerate(pngs):
        imagen = ImageReader(io.BytesIO(png))
        iw, ih = imagen.getSize()
        alto = ancho * ih / iw
        alto_max = max(alto_max, alto)
        c.drawImage(imagen, MARGEN + i * (ancho + separacion), y - alto, width=ancho, height=alto)
    return y - alto_max - 6


def pagina(c, r, con_graficas: bool = False) -> None:
    """The composition page of one report (call after a showPage); with
    `con_graficas` it first draws page 1's charts, which did not fit there."""
    k: Composicion = r.composicion
    _pagina(c)
    y = Y_INICIO
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 13)
    nombre = r.nombre if r.nombre != "Consolidado" else f"Consolidado ({len(r.sucursales)} sucursales)"
    c.drawString(MARGEN, y, f"Composición de la venta · {nombre}")
    c.setFillColor(TEXTO_SUAVE)
    c.setFont(F, 8)
    anio = r.periodo.mismo_periodo_anio_anterior()
    c.drawString(MARGEN, y - 12, r.periodo.etiqueta() + (f"   ·   Contra: {anio.etiqueta()}" if anio else ""))
    y -= 28
    if con_graficas:
        y = _imagenes(c, [dibujar(g) for g in r.graficas[:2]], y + 4, 12)
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 9)
    c.drawString(MARGEN, y, "Venta por horario")
    y = _franjas(c, k, y - 6)
    y = _nota(c, "Por la hora en que se cerró (cobró) el ticket, todos los canales. Var.: venta contra el año anterior "
                 "en sucursales comparables.", MARGEN, y, ANCHO_UTIL - 70, 6.2, 7.2) - 6
    if k.dias:
        c.setFillColor(VERDE_MARCA)
        c.setFont(FB, 9)
        c.drawString(MARGEN, y, "Por día de la semana (promedio por día)")
        y = _dias(c, k, y - 6)
        y = _nota(c, f"Venta bruta de un día promedio de cada día de la semana (el periodo tiene 4 o 5 de cada uno en un "
                     f"mes). Vs {k.vs_anterior} y vs año anterior: el total del día contra el día promedio del mismo nombre "
                     "en ese periodo.", MARGEN, y, ANCHO_UTIL - 70, 6.2, 7.2) - 6
    if k.tardes:
        c.setFillColor(VERDE_MARCA)
        c.setFont(FB, 9)
        c.drawString(MARGEN, y, "Quién vende mejor en las tardes (13:00 a 18:00), en proporción a su venta")
        y = _tardes(c, k, y - 6)
        y = _nota(c, f"% tarde = venta cerrada de 13:00 a 18:00 / venta bruta de la sucursal. Vs {k.vs_anterior} y vs "
                     "año anterior: puntos contra su propio % de ese periodo (▲ verde = vende más en la tarde).",
                  MARGEN, y, ANCHO_UTIL - 70, 6.2, 7.2) - 6
    y = _imagenes(c, [dibujar_dona(t, rebanadas) for t, rebanadas in k.pasteles if rebanadas], y)
    y = _imagenes(c, [dibujar(g) for g in k.barras], y, 12)
    _nota(c, "Forma de pago: monto cobrado sin propina (tabla de pagos de Wansoft); plataformas = Uber Eats, Rappi y "
             "Didi. Día de la semana: venta de todos los días de ese nombre en el periodo.", MARGEN, y, ANCHO_UTIL - 70,
          6.2, 7.2)
