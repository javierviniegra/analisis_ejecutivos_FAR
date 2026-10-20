"""Inflation addendum page of the monthly commercial PDF (owner, 2026-10-19)."""

from ..motor import formato
from ..motor.inflacion import Addendum, _nombre_mes
from .pdf_comercial import (ANCHO_UTIL, F, FB, FONDO_CAJA, LINEA, MARGEN, TEXTO, TEXTO_SUAVE, VERDE_MARCA, Y_INICIO,
                            Y_MIN, _aviso, _celdas, _columnas, _encabezado_tabla, _nota, _nueva_pagina, _pagina,
                            _renglones, _variacion)

ALTO = 11.5


def _lectura(c, a: Addendum, y: float) -> float:
    tam, interlinea = 8, 10
    bloques = [_renglones(c, t, F, tam, ANCHO_UTIL - 34) for t in a.lectura]
    alto = 22 + sum(len(b) * interlinea + 3 for b in bloques)
    c.setFillColor(FONDO_CAJA)
    c.roundRect(MARGEN, y - alto, ANCHO_UTIL, alto, 6, fill=1, stroke=0)
    c.setFillColor(VERDE_MARCA)
    c.rect(MARGEN, y - alto, 3, alto, fill=1, stroke=0)
    c.setFont(FB, 9.5)
    c.drawString(MARGEN + 12, y - 14, "Lectura")
    yy = y - 28
    for renglones in bloques:
        c.setFillColor(VERDE_MARCA)
        c.circle(MARGEN + 16, yy + 2.8, 2.2, fill=1, stroke=0)
        c.setFillColor(TEXTO)
        c.setFont(F, tam)
        for r in renglones:
            c.drawString(MARGEN + 24, yy, r)
            yy -= interlinea
        yy -= 3
    return y - alto - 12


def _tabla(c, a: Addendum, y: float) -> float:
    x = _columnas([170, 100, 100, 73, 73])  # = ANCHO_UTIL
    y = _encabezado_tabla(c, x, y, ["Indicador", _nombre_mes(a.mes).capitalize(), _nombre_mes(a.mes_anio).capitalize(),
                                    "Var. nominal", "Var. real"], ALTO)
    for i, f in enumerate(a.filas):
        if i % 2:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - ALTO + 2.5, ANCHO_UTIL, ALTO, fill=1, stroke=0)
        base = y - 7
        _celdas(c, x, base, [f.etiqueta, formato.valor(f.actual, f.formato), formato.valor(f.base, f.formato), None,
                             None if f.real is not None else "volumen"])
        _variacion(c, x[4] - 5, base, f.nominal, f.formato)
        if f.real is not None:
            _variacion(c, x[5] - 5, base, f.real, f.formato)
        y -= ALTO
    c.setStrokeColor(LINEA)
    c.line(MARGEN, y + 1, MARGEN + ANCHO_UTIL, y + 1)
    return y - 6


def _sucursales(c, a: Addendum, y: float) -> float:
    x = _columnas([236, 140, 140])  # = ANCHO_UTIL
    y = _encabezado_tabla(c, x, y, ["Sucursal", "Venta: var. nominal", "Venta: var. real"], ALTO)
    for i, s in enumerate(a.por_sucursal):
        if y - ALTO < Y_MIN:
            y = _nueva_pagina(c)
        if i % 2:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - ALTO + 2.5, ANCHO_UTIL, ALTO, fill=1, stroke=0)
        base = y - 7
        _celdas(c, x, base, [s.nombre, None, None])
        _variacion(c, x[2] - 5, base, s.nominal, "moneda")
        _variacion(c, x[3] - 5, base, s.real, "moneda")
        y -= ALTO
    return y - 6


def pagina(c, r) -> None:
    """The addendum page of a monthly report (call after a showPage)."""
    a: Addendum = r.addendum
    _pagina(c)
    y = Y_INICIO
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 13)
    nombre = r.nombre if r.nombre != "Consolidado" else f"Consolidado ({len(r.sucursales)} sucursales)"
    c.drawString(MARGEN, y, f"Addendum: crecimiento contra inflación · {nombre}")
    c.setFillColor(TEXTO)
    c.setFont(F, 9)
    c.drawString(MARGEN, y - 14, f"{_nombre_mes(a.mes).capitalize()} contra {_nombre_mes(a.mes_anio)}   ·   "
                                 f"Inflación anual: {a.inflacion * 100:.2f}%")
    y -= 26
    y = _aviso(c, a.nota.split(" Inflación anual =")[0], y)
    y = _lectura(c, a, y)
    y = _tabla(c, a, y)
    if a.excluidas:
        y = _nota(c, "Sucursales comparables (sin " + ", ".join(a.excluidas) + "): las que no operaron completo el "
                  "mismo mes del año anterior quedan fuera de la comparación.", MARGEN, y, ANCHO_UTIL - 70, 6.2, 7.2) - 4
    if a.por_sucursal:
        c.setFillColor(VERDE_MARCA)
        c.setFont(FB, 9)
        c.drawString(MARGEN, y - 4, "Por sucursal (de mayor a menor crecimiento real)")
        y = _sucursales(c, a, y - 10)
    c.setFillColor(TEXTO_SUAVE)
    _nota(c, "Inflación anual =" + a.nota.split(" Inflación anual =")[1], MARGEN, y - 2, ANCHO_UTIL - 70, 6.2, 7.2)
