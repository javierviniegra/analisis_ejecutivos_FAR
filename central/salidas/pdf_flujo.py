"""PDF of the cash-flow report on the Fonda Argentina template (reportlab).

Per report: page 1 = title, Lectura and the statement (opening balance,
inflows, outflows, transfers, closing balance) against the previous period;
page 2 = per company and accounts (consolidated) or accounts and largest
suppliers (one company); a consolidated report adds its largest suppliers;
the last page has the notes and rules. Drawing pieces (background, fonts,
notice band) come from the commercial report's template.
"""

import io

from reportlab.lib.colors import white
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..motor import flujo_efectivo as fe
from ..motor.flujo_efectivo import ReporteFlujo, nombre_base
from .pdf_comercial import (ANCHO_NOTAS, ANCHO_UTIL, F, FB, FONDO_CAJA, LINEA, MARGEN, TEXTO, TEXTO_SUAVE, VERDE_MARCA,
                            Y_INICIO, Y_MIN, _pagina, _registrar_fuentes, _renglones)

ALTO_FILA, ALTO_TITULO_SECCION = 9.4, 11
MAX_GRUPOS, MAX_OTROS = 6, 2  # expense groups and "other" items shown in the statement (the rest grouped)


def _m(v, signo: bool = False) -> str:
    if v is None:
        return "–"
    texto = f"${abs(v):,.0f}"
    return ("−" if v < -0.5 else ("+" if signo and v > 0.5 else "")) + texto


def _pct(a, b) -> str:
    return f"{a / b * 100:.0f}%" if b else "–"


# -- statement rows ----------------------------------------------------------------
def _det(cifras, rubro, clave):
    return cifras["detalle"].get(rubro, {}).get(clave, fe.CERO) if cifras else None


def _con_detalle(a, b, rubro, etiqueta, maximo, resto="Resto"):
    """A row and its largest items (by this period), the rest grouped."""
    total_a, total_b = a["rubros"][rubro], (b["rubros"][rubro] if b else None)
    if not total_a and not total_b:
        return []
    claves = set(a["detalle"].get(rubro, {})) | set(b["detalle"].get(rubro, {}) if b else ())
    orden = sorted(claves, key=lambda k: -abs(_det(a, rubro, k)))
    filas = [(etiqueta, total_a, total_b, "s")]
    for k in orden[:maximo]:
        filas.append((k[:52], _det(a, rubro, k), _det(b, rubro, k), "i"))
    if len(orden) > maximo:
        filas.append((resto, sum(_det(a, rubro, k) for k in orden[maximo:]),
                      sum(_det(b, rubro, k) for k in orden[maximo:]) if b else None, "i"))
    return filas


def filas(r: ReporteFlujo) -> list[tuple]:
    """(label, this period, previous, style) -- style: t total, h heading, s row, i item."""
    a, b = r.actual, r.anterior
    g = lambda c, k: c[k] if c else None  # noqa: E731
    rub = lambda c, k: c["rubros"][k] if c else None  # noqa: E731
    out = [("Saldo inicial de bancos e inversiones", a["saldo_inicial"], g(b, "saldo_inicial"), "t"), ("ENTRADAS", None, None, "h")]
    if a["depositos"] or (b and b["depositos"]):
        out.append(("Depósitos de ventas", a["depositos"], g(b, "depositos"), "s"))
        formas = set(a["detalle"].get(fe.VENTAS, {})) | set(b["detalle"].get(fe.VENTAS, {}) if b else ())
        orden = [f for f in fe.ORDEN_FORMAS if f in formas] + sorted(formas - set(fe.ORDEN_FORMAS))
        for f in orden:
            out.append((f, _det(a, fe.VENTAS, f), _det(b, fe.VENTAS, f), "i"))
        out.append(("Ajuste por ventas aún no depositadas (CxC bancos)", rub(a, fe.POR_DEPOSITAR), rub(b, fe.POR_DEPOSITAR), "i"))
    for rubro in (fe.VENTAS_FACTURA, fe.COBROS_GRUPO, fe.APORTACIONES):
        if a["rubros"][rubro] or (b and b["rubros"][rubro]):
            out.append((fe.ETIQUETAS[rubro], rub(a, rubro), rub(b, rubro), "s"))
    out += _con_detalle(a, b, fe.OTRAS_ENTRADAS, fe.ETIQUETAS[fe.OTRAS_ENTRADAS], MAX_OTROS)
    out += [("Total entradas", a["entradas"], g(b, "entradas"), "t"), ("SALIDAS", None, None, "h")]
    out += _con_detalle(a, b, fe.PROVEEDORES, fe.ETIQUETAS[fe.PROVEEDORES], MAX_GRUPOS, "Resto de gastos")
    for rubro in (fe.RENTAS, fe.NOMINA, fe.SEGURIDAD_SOCIAL, fe.IMPUESTOS, fe.COMISIONES):
        if a["rubros"][rubro] or (b and b["rubros"][rubro]):
            out.append((fe.ETIQUETAS[rubro], rub(a, rubro), rub(b, rubro), "s"))
    out += _con_detalle(a, b, fe.OTRAS_SALIDAS, fe.ETIQUETAS[fe.OTRAS_SALIDAS], MAX_OTROS)
    out.append(("Total salidas", a["salidas"], g(b, "salidas"), "t"))
    for rubro in fe.NEUTROS:
        if a["rubros"][rubro] or (b and b["rubros"][rubro]):
            out.append((fe.ETIQUETAS[rubro], rub(a, rubro), rub(b, rubro), "s"))
    out += [("Flujo neto del periodo", a["neto"], g(b, "neto"), "t"),
            ("Saldo final de bancos e inversiones", a["saldo_final"], g(b, "saldo_final"), "t")]
    return out


def lectura(r: ReporteFlujo) -> list[str]:
    a, b = r.actual, r.anterior
    out = [f"El saldo de bancos e inversiones pasó de {_m(a['saldo_inicial'])} a {_m(a['saldo_final'])} "
           f"({_m(a['neto'], True)})" + (f"; en el periodo anterior el cambio fue {_m(b['neto'], True)}." if b else ".")]
    if a["depositos"]:
        ventas = a["rubros"][fe.VENTAS]
        top = sorted(a["detalle"].get(fe.VENTAS, {}).items(), key=lambda x: -x[1])[:3]
        frase = (f"Se depositaron {_m(a['depositos'])} de ventas (tickets {_m(ventas)}: "
                 + ", ".join(f"{f.lower()} {_pct(v, ventas)}" for f, v in top) + ")")
        if b and b["depositos"]:
            frase += f", {'arriba' if a['depositos'] > b['depositos'] else 'abajo'} del periodo anterior ({_m(b['depositos'])})"
        out.append(frase + ".")
    otras = [(fe.ETIQUETAS[k].lower(), a["rubros"][k]) for k in (fe.VENTAS_FACTURA, fe.COBROS_GRUPO, fe.APORTACIONES) if a["rubros"][k]]
    if otras:
        out.append("Otras entradas: " + ", ".join(f"{n} {_m(v)}" for n, v in otras) + ".")
    grupos = sorted(a["detalle"].get(fe.PROVEEDORES, {}).items(), key=lambda x: x[1])[:2]
    if a["salidas"]:
        frase = f"Salieron {_m(-a['salidas'])}; a proveedores {_m(-a['rubros'][fe.PROVEEDORES])}"
        if grupos:
            frase += " (sobre todo " + " y ".join(f"{k.lower()} {_m(-v)}" for k, v in grupos) + ")"
        out.append(frase + ".")
    fijos = [(fe.ETIQUETAS[k].lower(), a["rubros"][k]) for k in (fe.RENTAS, fe.NOMINA, fe.SEGURIDAD_SOCIAL, fe.IMPUESTOS)
             if a["rubros"][k]]
    if fijos:
        out.append("Además: " + ", ".join(f"{n} {_m(-v)}" for n, v in fijos) + ".")
    if a["rubros"][fe.SIN_IDENTIFICAR]:
        out.append(f"Quedan {_m(abs(a['rubros'][fe.SIN_IDENTIFICAR]))} de movimientos bancarios sin identificar (ver notas).")
    return out


# -- drawing -----------------------------------------------------------------------
def _titulo(c, r: ReporteFlujo, texto: str, y: float) -> float:
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 15)
    c.drawString(MARGEN, y, texto)
    y -= 15
    p = r.periodo
    c.setFillColor(TEXTO)
    c.setFont(F, 9)
    c.drawString(MARGEN, y, f"{p.etiqueta()}  ({p.desde:%d/%m/%Y} al {p.hasta:%d/%m/%Y})")
    y -= 11
    ant = p.anterior()
    c.setFillColor(TEXTO_SUAVE)
    c.setFont(F, 7.5)
    c.drawString(MARGEN, y, f"Comparado con: {ant.etiqueta()}  ({ant.desde:%d/%m/%Y} al {ant.hasta:%d/%m/%Y})"
                 if r.anteriores is not None else "Sin periodo anterior comparable")
    return y - 14


def _nombre(r: ReporteFlujo) -> str:
    return f"Consolidado ({len(r.empresas)} empresas)" if r.consolidado else r.nombre


def _caja(c, renglones: list[str], y: float) -> float:
    tam, il = 8, 10.5
    lineas = [l for t in renglones for l in _renglones(c, "• " + t, F, tam, ANCHO_UTIL - 24)]
    alto = 22 + len(lineas) * il
    c.setFillColor(FONDO_CAJA)
    c.roundRect(MARGEN, y - alto, ANCHO_UTIL, alto, 5, fill=1, stroke=0)
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 8.5)
    c.drawString(MARGEN + 10, y - 12, "Lectura")
    c.setFillColor(TEXTO)
    c.setFont(F, tam)
    yy = y - 24
    for l in lineas:
        c.drawString(MARGEN + 12, yy, l)
        yy -= il
    return y - alto - 10


def _encabezado(c, y: float, columnas: list[tuple[str, float]], ancho: float = ANCHO_UTIL) -> float:
    """Green header band; columns = (title, right edge x) with the first one left-aligned at MARGEN."""
    c.setFillColor(VERDE_MARCA)
    c.rect(MARGEN, y - 13, ancho, 14, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FB, 7.4)
    c.drawString(MARGEN + 4, y - 9, columnas[0][0])
    for titulo, x in columnas[1:]:
        c.drawRightString(x, y - 9, titulo)
    return y - 13


def _nueva(c) -> float:
    c.showPage()
    _pagina(c)
    return Y_INICIO


def _estado(c, r: ReporteFlujo, y: float) -> float:
    ancho = ANCHO_UTIL - 40
    xs = [MARGEN + 330, MARGEN + 400, MARGEN + 470]
    cols = [("Concepto", 0), ("Periodo", xs[0]), ("Anterior", xs[1]), ("Variación", xs[2])]
    y = _encabezado(c, y, cols, ancho)
    for etiqueta, a, b, estilo in filas(r):
        alto = ALTO_TITULO_SECCION if estilo == "h" else ALTO_FILA
        if y - alto < Y_MIN + 6:
            y = _encabezado(c, _nueva(c), cols, ancho)
        if estilo == "t":
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - alto, ancho, alto, fill=1, stroke=0)
        c.setFillColor(VERDE_MARCA if estilo == "h" else (TEXTO_SUAVE if estilo == "i" else TEXTO))
        c.setFont(FB if estilo in ("t", "h") else F, 7 if estilo == "i" else 7.4)
        base = y - alto + 2.8
        c.drawString(MARGEN + (16 if estilo == "i" else 4), base, etiqueta)
        if estilo != "h":
            c.drawRightString(xs[0], base, _m(a))
            c.drawRightString(xs[1], base, _m(b))
            if b is not None and not etiqueta.startswith("Saldo"):
                c.setFillColor(TEXTO_SUAVE)
                c.drawRightString(xs[2], base, _m(a - b, True))
        c.setStrokeColor(LINEA)
        c.setLineWidth(0.3)
        c.line(MARGEN, y - alto, MARGEN + ancho, y - alto)
        y -= alto
    return y - 10


def _notas(c, textos: list[str], y: float, titulo: str = "Notas") -> float:
    if y < Y_MIN + 40:
        y = _nueva(c)
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 8)
    c.drawString(MARGEN, y, titulo)
    y -= 10
    c.setFont(F, 6.9)
    for t in textos:
        renglones = _renglones(c, "• " + t, F, 6.9, ANCHO_NOTAS)
        if y - 8.6 * len(renglones) < Y_MIN:
            y = _nueva(c)
            c.setFont(F, 6.9)
        c.setFillColor(TEXTO_SUAVE)
        for l in renglones:
            c.drawString(MARGEN, y, l)
            y -= 8.6
        y -= 2
    return y


def _tabla_simple(c, y: float, columnas: list[tuple[str, float]], renglones: list[tuple[list[str], bool]]) -> float:
    """Rows of text: (values, bold). Breaks pages, repeating the header."""
    y = _encabezado(c, y, columnas)
    for valores, negrita in renglones:
        if y - 11.5 < Y_MIN + 6:
            y = _encabezado(c, _nueva(c), columnas)
        if negrita:
            c.setFillColor(FONDO_CAJA)
            c.rect(MARGEN, y - 11.5, ANCHO_UTIL, 11.5, fill=1, stroke=0)
        c.setFillColor(TEXTO)
        c.setFont(FB if negrita else F, 7.1)
        c.drawString(MARGEN + 4, y - 8.3, valores[0])
        for v, (_, x) in zip(valores[1:], columnas[1:]):
            c.drawRightString(x, y - 8.3, v)
        c.setStrokeColor(LINEA)
        c.setLineWidth(0.3)
        c.line(MARGEN, y - 11.5, MARGEN + ANCHO_UTIL, y - 11.5)
        y -= 11.5
    return y - 12


def _seccion(c, texto: str, y: float) -> float:
    if y < Y_MIN + 60:
        y = _nueva(c)
    c.setFillColor(VERDE_MARCA)
    c.setFont(FB, 10)
    c.drawString(MARGEN, y, texto)
    return y - 6


def _cuentas(c, r: ReporteFlujo, y: float) -> float:
    cols = [("Empresa · cuenta" if r.consolidado else "Cuenta", 0), ("Inicial", MARGEN + 350), ("Final", MARGEN + 420),
            ("Cambio", MARGEN + 490)]
    renglones = []
    for e in r.empresas:
        for cta in e.cuentas:
            nombre = f"{e.nombre} · {cta.nombre}" if r.consolidado else cta.nombre
            renglones.append(([f"{nombre[:60]}  ({cta.codigo})", _m(cta.saldo_inicial), _m(cta.saldo_final),
                               _m(cta.saldo_final - cta.saldo_inicial, True)], False))
    a = r.actual
    renglones.append((["Total bancos e inversiones", _m(a["saldo_inicial"]), _m(a["saldo_final"]), _m(a["neto"], True)], True))
    return _tabla_simple(c, _seccion(c, "Bancos e inversiones por cuenta", y), cols, renglones)


def _por_empresa(c, r: ReporteFlujo, y: float) -> float:
    xs = [MARGEN + 230, MARGEN + 285, MARGEN + 340, MARGEN + 395, MARGEN + 450, MARGEN + 510]
    cols = [("Empresa", 0)] + list(zip(["Inicial", "Entradas", "Salidas", "Traspasos", "Final", "Cambio"], xs))

    def valores(nombre, empresas):
        x = ReporteFlujo.cifras(empresas)
        neutros = x["rubros"][fe.TRASPASOS] + x["rubros"][fe.SIN_IDENTIFICAR]
        return [nombre, _m(x["saldo_inicial"]), _m(x["entradas"]), _m(-x["salidas"]), _m(neutros, True), _m(x["saldo_final"]),
                _m(x["neto"], True)]

    renglones = []
    for grupo in (fe.SUCURSAL, fe.CORPORATIVO_GRUPO):
        es = [e for e in r.empresas if e.grupo == grupo]
        if not es:
            continue
        renglones += [(valores(e.nombre, [e]), False) for e in es]
        renglones.append((valores(f"Subtotal {grupo.lower()}", es), True))
    renglones.append((valores("Total", r.empresas), True))
    return _tabla_simple(c, _seccion(c, "Por empresa", y), cols, renglones)


def _proveedores(c, r: ReporteFlujo, y: float, n: int) -> float:
    actuales = r.proveedores(n=n)
    previos = dict(r.proveedores(r.anteriores, n=10_000)) if r.anteriores is not None else {}
    total = sum(-m.monto for e in r.empresas for m in e.movimientos if m.rubro in (fe.PROVEEDORES, fe.RENTAS))
    cols = [("Proveedor", 0), ("Periodo", MARGEN + 350), ("Anterior", MARGEN + 420), ("% del total", MARGEN + 490)]
    renglones = [([f"{i}. {s[:58]}", _m(v), _m(previos.get(s)) if r.anteriores is not None else "–", _pct(v, total)], False)
                 for i, (s, v) in enumerate(actuales, start=1)]
    renglones.append((["Total pagado a proveedores y rentas", _m(total), "", ""], True))
    return _tabla_simple(c, _seccion(c, f"Proveedores con más pagos (incluye rentas y empresas del grupo)", y), cols, renglones)


def _reporte(c, r: ReporteFlujo):
    _pagina(c)
    y = _titulo(c, r, f"{fe.TITULO} · {_nombre(r)}", Y_INICIO)
    if not r.empresas:
        _notas(c, r.notas, y)
        return
    y = _caja(c, lectura(r), y)
    y = _estado(c, r, y)
    y = _nueva(c)
    if r.consolidado:
        y = _por_empresa(c, r, y)
        y = _cuentas(c, r, y)
        y = _nueva(c)
        y = _proveedores(c, r, y, 25)
    else:
        y = _cuentas(c, r, y)
        y = _proveedores(c, r, y, 15)
    _notas(c, fe.notas_de(r), y)


def generar(reportes: list[ReporteFlujo]) -> bytes:
    _registrar_fuentes()
    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=letter)
    c.setTitle(nombre_base(reportes).replace("_", " "))
    for i, r in enumerate(reportes):
        if i:
            c.showPage()
        _reporte(c, r)
    c.save()
    return salida.getvalue()


def nombre_archivo(reportes: list[ReporteFlujo]) -> str:
    return nombre_base(reportes) + ".pdf"
