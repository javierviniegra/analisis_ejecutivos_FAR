"""Butchery page of the commercial PDF (owner, 2026-10-20): shrinkage per
branch (consolidated) or per base product and per day of the week (branch),
against every branch and against the same period last year."""

from ..motor import formato
from ..motor.tabla_comercial import ENTERO, PORCENTAJE
from ..motor.tablajeria import (LEYENDA_DIAS, LEYENDA_PORCIONADOS, LEYENDA_PRODUCTOS, LEYENDA_SUCURSALES,
                                Tablajeria, notas)
from .pdf_comercial import (ANCHO_UTIL, COLOR_VAR, F, FB, FONDO_CAJA, GRIS_VAR, LINEA, MARGEN, TEXTO, TEXTO_SUAVE,
                            VERDE_MARCA, Y_INICIO, Y_MIN, _celdas, _columnas, _encabezado_tabla, _nota, _nueva_pagina,
                            _pagina, _variacion)
from ..motor.comparativos import ROJO, VERDE

ALTO = 11.0
UMBRAL_GRUPO = 0.01  # 1 point above / below the group is coloured


def _kg(v) -> str:
    return "—" if v is None else f"{v:,.1f}"


def _pct(v) -> str:
    return formato.valor(v, PORCENTAJE)


def _pesos(v) -> str:
    return "—" if v is None else f"${v:,.0f}"


def _dif(c, x_der, base, dif):
    """Points above (red) or below (green) the group."""
    if dif is None:
        c.setFillColor(GRIS_VAR)
        c.setFont(F, 7.6)
        c.drawRightString(x_der, base, "—")
        return
    puntos = round(float(dif) * 100, 1) + 0  # + 0 turns -0.0 into 0.0
    color = COLOR_VAR[ROJO] if dif > UMBRAL_GRUPO else COLOR_VAR[VERDE] if dif < -UMBRAL_GRUPO else TEXTO
    c.setFillColor(color)
    c.setFont(FB if color is not TEXTO else F, 7.6)
    c.drawRightString(x_der, base, f"{puntos:+.1f} pp" if puntos else "0.0 pp")


def _leyenda(c, texto: str, y: float) -> float:
    """The line under a table that explains its columns."""
    return _nota(c, texto, MARGEN, y + 3, ANCHO_UTIL - 70, 6.2, 7.2) - 9


def _subtitulo(c, texto: str, y: float) -> float:
    if y - 40 < Y_MIN:
        y = _nueva_pagina(c)
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 9)
    c.drawString(MARGEN, y, texto)
    return y - 6


def _renglon(c, x, y, i, total, valores, pinta=None) -> float:
    if y - ALTO < Y_MIN:
        y = _nueva_pagina(c)
    if total:
        c.setStrokeColor(LINEA)
        c.line(MARGEN, y + 1, MARGEN + ANCHO_UTIL, y + 1)
    elif i % 2:
        c.setFillColor(FONDO_CAJA)
        c.rect(MARGEN, y - ALTO + 2.5, ANCHO_UTIL, ALTO, fill=1, stroke=0)
    base = y - 6.5
    _celdas(c, x, base, valores, negrita=total)
    if pinta:
        pinta(base)
    return y - ALTO


def _sucursales(c, t: Tablajeria, filas, y: float) -> float:
    """Consolidated: one row per branch, with its expected % for its mix of cuts."""
    costos = t.incluir_costos
    anchos = [94, 46, 44, 44, 48, 50, 48, 48, 46, 48]
    titulos = ["Sucursal", "Kg base", "Merma", "% merma", "Esperado", "Vs esp.", "Año ant.", "Var.", "Vs grupo",
               "$ merma"]
    if not costos:
        anchos[0] += anchos.pop()
        titulos.pop()
    x = _columnas(anchos)
    y = _encabezado_tabla(c, x, y, titulos, ALTO)
    for i, f in enumerate(filas):
        a = f.actual
        valores = [f.etiqueta, _kg(a.base), _kg(a.merma), _pct(f.indice), _pct(f.esperado), None,
                   _pct(f.indice_anio), None, None] + ([_pesos(a.costo_merma)] if costos else [])

        def pinta(base, f=f):
            if not f.total:
                _dif(c, x[6] - 5, base, f.dif_esperado)
                _dif(c, x[9] - 5, base, f.dif_grupo)
            _variacion(c, x[8] - 5, base, f.var_anio, PORCENTAJE)
        y = _renglon(c, x, y, i, f.total, valores, pinta)
    return y - 8


def _merma(c, t: Tablajeria, filas, y: float, primera: str, con_grupo: bool, vs: str = "Vs grupo") -> float:
    """Rows of kg products: base, shrinkage, % merma, vs group, vs last year, cost."""
    costos = t.incluir_costos
    if con_grupo:
        anchos = [112, 48, 50, 46, 46, 52, 52, 56, 54]
        titulos = [primera, "Kg base", "Merma kg", "% merma", "% grupo", "Vs grupo", "% año ant.", "Var.", "$ merma"]
    else:
        anchos = [120, 56, 56, 52, 58, 58, 60, 56]
        titulos = [primera, "Kg base", "Merma kg", "% merma", "% año ant.", "Var.", vs, "$ merma"]
    if not costos:
        anchos[0] += anchos.pop()
        titulos.pop()
    x = _columnas(anchos)
    y = _encabezado_tabla(c, x, y, titulos, ALTO)
    for i, f in enumerate(filas):
        a = f.actual
        if con_grupo:
            valores = [f.etiqueta, _kg(a.base), _kg(a.merma), _pct(f.indice), _pct(f.indice_grupo), None,
                       _pct(f.indice_anio), None] + ([_pesos(a.costo_merma)] if costos else [])

            def pinta(base, f=f):
                _dif(c, x[6] - 5, base, f.dif_grupo)
                _variacion(c, x[8] - 5, base, f.var_anio, PORCENTAJE)
        else:
            valores = [f.etiqueta, _kg(a.base), _kg(a.merma), _pct(f.indice), _pct(f.indice_anio), None, None] \
                + ([_pesos(a.costo_merma)] if costos else [])

            def pinta(base, f=f):
                _variacion(c, x[6] - 5, base, f.var_anio, PORCENTAJE)
                if not f.total:
                    _dif(c, x[7] - 5, base, f.dif_grupo)
        y = _renglon(c, x, y, i, f.total, valores, pinta)
    return y - 8


def _porcionados(c, t: Tablajeria, y: float) -> float:
    x = _columnas([150, 62, 62, 60, 60, 62, 60])
    y = _encabezado_tabla(c, x, y, ["Producto", "Kg base", "Piezas", "Pzas/kg", "Grupo", "Año ant.", "Var."], ALTO)
    for i, f in enumerate(t.porcionados):
        valores = [f.etiqueta, _kg(f.actual.base), formato.valor(f.actual.generado, ENTERO), _kg2(f.indice),
                   _kg2(f.indice_grupo), _kg2(f.indice_anio), None]
        y = _renglon(c, x, y, i, False, valores,
                     lambda base, f=f: _variacion(c, x[7] - 5, base, f.var_anio, ENTERO))
    return y - 8


def _kg2(v) -> str:
    return "—" if v is None else f"{v:,.2f}"


def pagina(c, r) -> None:
    """The butchery page of one report (call after a showPage)."""
    t: Tablajeria = r.tablajeria
    _pagina(c)
    y = Y_INICIO
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 13)
    nombre = r.nombre if r.nombre != "Consolidado" else f"Consolidado ({len(r.sucursales)} sucursales)"
    c.drawString(MARGEN, y, f"Tablajería · {nombre}")
    c.setFillColor(TEXTO_SUAVE)
    c.setFont(F, 8)
    anio = r.periodo.mismo_periodo_anio_anterior()
    c.drawString(MARGEN, y - 12, r.periodo.etiqueta() + (f"   ·   Contra: {anio.etiqueta()}" if anio else ""))
    y -= 28
    if t.consolidado:
        y = _subtitulo(c, "Merma por sucursal (de mayor a menor)", y)
        y = _sucursales(c, t, t.filas + ([t.total] if t.total else []), y)
        y = _leyenda(c, LEYENDA_SUCURSALES, y)
    else:
        y = _subtitulo(c, "Por producto base (de mayor a menor merma; grupo = el mismo producto en todas las sucursales)", y)
        y = _merma(c, t, t.filas + ([t.total] if t.total else []), y, "Producto", con_grupo=True)
        y = _leyenda(c, LEYENDA_PRODUCTOS, y)
        if t.porcionados:
            y = _subtitulo(c, "Porcionados (se cuentan en piezas: piezas por kg de base)", y)
            y = _porcionados(c, t, y)
            y = _leyenda(c, LEYENDA_PORCIONADOS, y)
        if t.por_dia:
            y = _subtitulo(c, "Por día de la semana", y)
            y = _merma(c, t, t.por_dia, y, "Día", con_grupo=False, vs="Vs su prom.")
            y = _leyenda(c, LEYENDA_DIAS, y)
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 7)
    if y - 30 < Y_MIN:
        y = _nueva_pagina(c)
    c.drawString(MARGEN, y, "Cómo se calcula")
    y -= 9
    for n in notas(t):
        if y - 14 < Y_MIN:
            y = _nueva_pagina(c)
        y = _nota(c, n, MARGEN, y, ANCHO_UTIL - 70, 5.9, 6.8)
