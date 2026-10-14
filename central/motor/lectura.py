"""Rule-based "Lectura del periodo" box of the commercial report (pure: no I/O).

Every sentence is computed from the indicators table; nothing is invented.
The AI analyst (last phase) will later rewrite this same box without
changing the rest of the report.

Rules, in priority order (owner, 2026-09-24; thresholds are constants to be
tuned once real reports have been read):
Owner, 2026-10-14: the Lectura comes in blocks -- first against the same
period last year (the main comparison), then against the immediately
previous period (each naming the period), then what is about the period
itself (cost vs target, budget). In each comparison block:
1. Gross sales (con IVA; owner's choice to measure the impact of sales). Always.
2. What drove the change: guests (traffic) or average check, whichever moved
   more. Only when sales moved.
3. Controls (cancellations, courtesies, discounts) that went up AND weigh at
   least UMBRAL_PESO_CONTROL of net sales.
4. Channel / food-beverage mix rows that moved more than UMBRAL_PUNTOS_MEZCLA.
5. Costo de Ventas above its prorated budget.
A comparison without enough coverage reads "sin comparativo fiable"; the
coverage details go to the report's footnotes (`notas.py`), not here.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from . import formato
from .comparativos import (BAJA, META_COSTO_MIN, META_COSTO_TOPE, NARANJA, NO_FIABLE, ROJO, SUBE, VERDE,
                           semaforo_costo)
from .metricas import Comparacion, Metricas, como_comparacion
from .periodo import Periodo, TipoPeriodo
from .tabla_comercial import Fila, construir_tabla

UMBRAL_PESO_CONTROL = Decimal("0.005")  # 0.5% of net sales
UMBRAL_PUNTOS_MEZCLA = Decimal("0.02")  # 2 percentage points

POSITIVO, NEGATIVO, NEUTRO, AVISO = "positivo", "negativo", "neutro", "aviso"

# (noun, feminine?) per period kind
_NOMBRES = {
    TipoPeriodo.SEMANA: ("semana", True),
    TipoPeriodo.MES: ("mes", False),
    TipoPeriodo.BIMESTRE: ("bimestre", False),
    TipoPeriodo.TRIMESTRE: ("trimestre", False),
    TipoPeriodo.SEMESTRE: ("semestre", False),
    TipoPeriodo.ANIO: ("año", False),
    TipoPeriodo.RANGO: ("periodo", False),
}


@dataclass(frozen=True)
class Observacion:
    texto: str
    tono: str  # positivo / negativo / neutro / aviso


@dataclass(frozen=True)
class Bloque:
    subtitulo: str  # e.g. "Contra el año anterior · Semana 41 · 6 oct – 12 oct 2025"
    observaciones: list[Observacion]


@dataclass(frozen=True)
class Lectura:
    titulo: str
    observaciones: list[Observacion]  # all of them, in order
    bloques: list[Bloque] = field(default_factory=list)  # the same, grouped (commercial); empty = one list


def _nombre(periodo: Periodo) -> tuple[str, bool]:
    return _NOMBRES[periodo.tipo]


def titulo(periodo: Periodo) -> str:
    nombre, fem = _nombre(periodo)
    return f"Lectura {'de la' if fem else 'del'} {nombre}"


def vs_anterior(periodo: Periodo) -> str:
    nombre, fem = _nombre(periodo)
    return f"{'la' if fem else 'el'} {nombre} anterior"


def vs_anio(periodo: Periodo) -> str:
    nombre, fem = _nombre(periodo)
    return f"{'la misma' if fem else 'el mismo'} {nombre} del año anterior"


def _pesos(v: Decimal) -> str:
    return f"${v:,.0f}"


def _tono(var) -> str:
    return {"verde": POSITIVO, "rojo": NEGATIVO}.get(var.color, NEUTRO)


def _fila(filas: list[Fila], clave: str) -> Fila:
    return next(f for f in filas if f.indicador.clave == clave)


def _var(f: Fila, campo: str = "var_anterior") -> str:
    return formato.variacion(getattr(f, campo), f.indicador.formato)


def _sin_comparativo(var) -> str:
    return "sin comparativo fiable" if var.direccion == NO_FIABLE else "sin comparativo"


# -- rules (one comparison at a time: `campo` is "var_anio" or "var_anterior") ----------------
def _comparables(comp: Comparacion) -> str:
    return " en sucursales comparables" if comp.excluidas else ""


def _venta(filas, comp: Comparacion, campo: str) -> Observacion | None:
    f = _fila(filas, "venta_bruta")
    if f.actual is None:
        return None
    var = getattr(f, campo)
    if var.porcentaje is None:
        return Observacion(f"La venta bruta fue de {_pesos(f.actual)}, {_sin_comparativo(var)}.", NEUTRO)
    dif = comp.actual.venta_bruta - comp.base.venta_bruta  # comparable branches only
    return Observacion(f"La venta bruta fue de {_pesos(f.actual)}: {_var(f, campo)} "
                       f"({'+' if dif >= 0 else '-'}{_pesos(abs(dif))}){_comparables(comp)}.", _tono(var))


def _causa(filas, campo: str) -> Observacion | None:
    venta = _fila(filas, "venta_bruta")
    if getattr(venta, campo).direccion not in (SUBE, BAJA):
        return None
    cli, chq = _fila(filas, "clientes"), _fila(filas, "cheque_promedio")
    vc, vq = getattr(cli, campo), getattr(chq, campo)
    if vc.porcentaje is None or vq.porcentaje is None:
        return None
    if abs(vc.porcentaje) >= abs(vq.porcentaje):
        texto = (f"El cambio viene sobre todo del tráfico: clientes {_var(cli, campo)} "
                 f"({formato.valor(cli.actual, cli.indicador.formato)}), cheque promedio {_var(chq, campo)}.")
    else:
        texto = (f"El cambio viene sobre todo del cheque promedio: {_var(chq, campo)} "
                 f"({formato.valor(chq.actual, chq.indicador.formato)}), clientes {_var(cli, campo)}.")
    return Observacion(texto, _tono(getattr(venta, campo)))


def _controles(filas, campo: str) -> Observacion | None:
    neta = _fila(filas, "venta_neta").actual
    if not neta:
        return None
    alertas = []
    for clave in ("cancelaciones", "cortesias", "descuentos"):
        f = _fila(filas, clave)
        if f.actual is None or getattr(f, campo).direccion != SUBE:
            continue
        peso = f.actual / neta
        if peso >= UMBRAL_PESO_CONTROL:
            alertas.append(f"{f.indicador.etiqueta} {_pesos(f.actual)} ({_var(f, campo)}, "
                           f"{peso * 100:.1f}% de la venta neta)")
    if not alertas:
        return None
    return Observacion("Controles al alza: " + "; ".join(alertas) + ".", NEGATIVO)


def _mezcla(filas, campo: str) -> Observacion | None:
    cambios = [
        f"{f.indicador.etiqueta.split(': ', 1)[-1]} {formato.valor(f.actual, f.indicador.formato)} ({_var(f, campo)})"
        for f in filas
        if f.indicador.seccion == "Mezcla"
        and getattr(f, campo).porcentaje is not None
        and abs(getattr(f, campo).porcentaje) > UMBRAL_PUNTOS_MEZCLA
    ]
    if not cambios:
        return None
    return Observacion("Cambio en la mezcla: " + "; ".join(cambios) + ".", NEUTRO)


def _comparativas(filas, comp: Comparacion, campo: str) -> list[Observacion]:
    return [o for o in (_venta(filas, comp, campo), _causa(filas, campo), _controles(filas, campo),
                        _mezcla(filas, campo)) if o is not None]


def subtitulo_anio(periodo: Periodo) -> str:
    base = periodo.mismo_periodo_anio_anterior()
    return f"Contra el año anterior · {base.etiqueta() if base else 'sin periodo comparable'}"


def subtitulo_anterior(periodo: Periodo) -> str:
    return f"Contra el periodo inmediato anterior · {periodo.anterior().etiqueta()}"


def _costo_ventas(actual: Metricas) -> Observacion | None:
    ejercido = actual.ejercido_costo_ventas
    if ejercido is None or ejercido <= 1:
        return None
    texto = (f"El Costo de Ventas real ({_pesos(actual.costo_ventas_real_con_ppto)}) supera el presupuesto "
             f"prorrateado ({_pesos(actual.costo_ventas_ppto_con_real)}): {ejercido * 100:.1f}% ejercido")
    if actual.n_sucursales > 1:
        texto += f" ({actual.n_con_presupuesto} de {actual.n_sucursales} sucursales tienen presupuesto)"
    if actual.costo_preliminar:  # already over budget with invoices still arriving: it can only grow
        texto += "; cifra preliminar, las facturas del periodo se siguen registrando"
    return Observacion(texto + ".", NEGATIVO)


def _costo_meta(actual: Metricas) -> Observacion | None:
    """Both costs vs the 38.0%-39.9% target (business rule, per week and month):
    total cost (Wansoft/Odoo) and invoiced cost (Presupuestos AP)."""
    donde = {VERDE: "dentro de la meta", NARANJA: "abajo de la meta", ROJO: "arriba de la meta"}
    partes, colores = [], []
    for nombre, pct in (("total", actual.pct_costo_total), ("facturado", actual.pct_costo_ventas)):
        color = semaforo_costo(pct)
        if color is None:
            continue
        colores.append(color)
        texto = f"{nombre} {pct * 100:.1f}%, {donde[color]}"
        if nombre == "total" and actual.costo_total_estimado:
            texto += " (estimado, ver notas)"
        if nombre == "facturado" and actual.costo_preliminar:
            texto += " (preliminar, pueden faltar facturas)"
        partes.append(texto)
    if not partes:
        return None
    rango = f"{META_COSTO_MIN * 100:.1f}-{(META_COSTO_TOPE * 100) - Decimal('0.1'):.1f}%"
    return Observacion(f"Costo sobre la venta neta (meta {rango}): " + "; ".join(partes) + ".",
                       POSITIVO if all(c == VERDE for c in colores) else NEGATIVO)


def construir_lectura(periodo: Periodo, actual: Metricas, anterior: Comparacion | Metricas | None,
                      anio_anterior: Comparacion | Metricas | None) -> Lectura:
    ant, anio = como_comparacion(actual, anterior), como_comparacion(actual, anio_anterior)
    filas = construir_tabla(actual, ant, anio)
    if actual.dias_con_cierre == 0:
        aviso = Observacion("No hay cierres de caja en el periodo.", AVISO)
        return Lectura(titulo(periodo), [aviso], [Bloque("", [aviso])])
    bloques = [Bloque(subtitulo_anio(periodo), _comparativas(filas, anio, "var_anio"))]
    if periodo.tipo != TipoPeriodo.ANIO:  # for a year the previous period IS the same period last year
        bloques.append(Bloque(subtitulo_anterior(periodo), _comparativas(filas, ant, "var_anterior")))
    bloques.append(Bloque("Del periodo", [o for o in (_costo_meta(actual), _costo_ventas(actual)) if o is not None]))
    bloques = [b for b in bloques if b.observaciones]
    return Lectura(titulo(periodo), [o for b in bloques for o in b.observaciones], bloques)
