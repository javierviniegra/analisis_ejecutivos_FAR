"""Indicators table of the commercial report (pure: no I/O).

Each row compares the period against the previous period and against the
same period of the previous year, with the approved arrow rule (+-1%). A
comparison period with no data yields "s/c" (never an invented zero).

Metrics that are shares (mix, channel, budget execution) are compared in
percentage POINTS (threshold: 1 point) since a relative change of a share is
hard to read. Metrics with no good/bad direction (mix, channel, budget) keep
their arrow but always in grey.

A comparison is "s/cf" (sin comparativo fiable) when either period has data
on less than UMBRAL_COBERTURA_FIABLE of its expected days: cash closings for
sales rows, ticket detail for mix/channel rows. Budget rows do not depend on
the cash closings and are exempt. The values are still shown.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Callable

from .comparativos import GRIS, IGUAL, cobertura_fiable, no_fiable, SIMBOLOS, SIN_DATO, SUBE, BAJA, VERDE, ROJO, UMBRAL_IGUAL, Variacion, variacion
from .metricas import Metricas

MONEDA, ENTERO, PORCENTAJE = "moneda", "entero", "porcentaje"


@dataclass(frozen=True)
class Indicador:
    clave: str
    etiqueta: str
    seccion: str
    formato: str
    valor: Callable[[Metricas], Decimal | None]
    mejor_si_sube: bool | None  # None = no good/bad direction (arrow always grey)
    requiere_detalle: bool = False  # needs ticket detail (channel / mix)
    usa_cierres: bool = True  # False: not built from cash closings (budget rows), no coverage rule


def _pct_canal(canal):
    return lambda m: m.pct_canal(canal)


def _pct_mix(grupo):
    return lambda m: m.pct_mix(grupo)


INDICADORES = [
    Indicador("venta_bruta", "Venta bruta (con IVA)", "Ventas", MONEDA, lambda m: m.venta_bruta, True),
    Indicador("venta_neta", "Venta neta (sin IVA)", "Ventas", MONEDA, lambda m: m.venta_neta, True),
    Indicador("tickets", "Tickets", "Ventas", ENTERO, lambda m: m.tickets, True),
    Indicador("clientes", "Clientes", "Ventas", ENTERO, lambda m: m.clientes, True),
    Indicador("cheque_promedio", "Cheque promedio (venta / cliente)", "Ventas", MONEDA, lambda m: m.cheque_promedio, True),
    Indicador("ticket_promedio", "Ticket promedio (venta / ticket)", "Ventas", MONEDA, lambda m: m.ticket_promedio, True),
    Indicador("mix_alimentos", "Mix: Alimentos", "Mezcla", PORCENTAJE, _pct_mix("Alimentos"), None, requiere_detalle=True),
    Indicador("mix_bebidas", "Mix: Bebidas", "Mezcla", PORCENTAJE, _pct_mix("Bebidas"), None, requiere_detalle=True),
    Indicador("canal_salon", "Canal: Salón", "Mezcla", PORCENTAJE, _pct_canal("salon"), None, requiere_detalle=True),
    Indicador("canal_llevar", "Canal: Para llevar", "Mezcla", PORCENTAJE, _pct_canal("llevar"), None, requiere_detalle=True),
    Indicador("canal_plataformas", "Canal: Plataformas", "Mezcla", PORCENTAJE, _pct_canal("plataformas"), None, requiere_detalle=True),
    Indicador("cancelaciones", "Cancelaciones", "Control (a precio de venta)", MONEDA, lambda m: m.cancelaciones, False),
    Indicador("cortesias", "Cortesías", "Control (a precio de venta)", MONEDA, lambda m: m.cortesias, False),
    Indicador("descuentos", "Descuentos", "Control (a precio de venta)", MONEDA, lambda m: m.descuentos, False),
    Indicador("costo_ventas_real", "Costo de Ventas real", "Costo de Ventas vs presupuesto", MONEDA,
              lambda m: m.costo_ventas_real, False, usa_cierres=False),
    Indicador("costo_ventas_ppto", "Costo de Ventas presupuestado", "Costo de Ventas vs presupuesto", MONEDA,
              lambda m: m.costo_ventas_ppto, None, usa_cierres=False),
    Indicador("costo_ventas_ejercido", "% ejercido del presupuesto", "Costo de Ventas vs presupuesto", PORCENTAJE,
              lambda m: m.ejercido_costo_ventas, None, usa_cierres=False),
]


@dataclass(frozen=True)
class Fila:
    indicador: Indicador
    actual: Decimal | None
    anterior: Decimal | None
    var_anterior: Variacion
    anio_anterior: Decimal | None
    var_anio: Variacion


def variacion_puntos(actual, base, *, mejor_si_sube: bool = True, umbral: Decimal = UMBRAL_IGUAL) -> Variacion:
    """Change of a share in percentage points (0.02 = +2 points)."""
    if actual is None or base is None:
        return Variacion(None, SIN_DATO, GRIS, SIMBOLOS[SIN_DATO])
    dif = Decimal(actual) - Decimal(base)
    if abs(dif) <= umbral:
        return Variacion(dif, IGUAL, GRIS, SIMBOLOS[IGUAL])
    direccion = SUBE if dif > 0 else BAJA
    bueno = (direccion == SUBE) == mejor_si_sube
    return Variacion(dif, direccion, VERDE if bueno else ROJO, SIMBOLOS[direccion])


def _valor(ind: Indicador, m: Metricas | None) -> Decimal | None:
    """Value of an indicator for a period, or None when that period has no
    data for it (no closings, no ticket detail, or no budget)."""
    if m is None or m.dias_con_cierre == 0:
        return None
    if ind.requiere_detalle and m.dias_con_detalle == 0:
        return None
    return ind.valor(m)


def fiable(ind: Indicador, m: Metricas | None) -> bool:
    """Whether period `m` has enough coverage for this indicator's comparisons."""
    if not ind.usa_cierres or m is None:
        return True
    dias = m.dias_con_detalle if ind.requiere_detalle else m.dias_con_cierre
    return cobertura_fiable(dias, m.dias_esperados)


def _comparar(ind: Indicador, actual, base, fiables: bool = True) -> Variacion:
    if not fiables and actual is not None and base is not None:
        return no_fiable()
    direccion_buena = True if ind.mejor_si_sube is None else ind.mejor_si_sube
    if ind.formato == PORCENTAJE:
        v = variacion_puntos(actual, base, mejor_si_sube=direccion_buena)
    else:
        v = variacion(actual, base, mejor_si_sube=direccion_buena)
    return replace(v, color=GRIS) if ind.mejor_si_sube is None else v


def construir_tabla(actual: Metricas, anterior: Metricas | None, anio_anterior: Metricas | None) -> list[Fila]:
    filas = []
    for ind in INDICADORES:
        a, p, y = _valor(ind, actual), _valor(ind, anterior), _valor(ind, anio_anterior)
        ok = fiable(ind, actual)
        filas.append(Fila(ind, a, p, _comparar(ind, a, p, ok and fiable(ind, anterior)),
                          y, _comparar(ind, a, y, ok and fiable(ind, anio_anterior))))
    return filas
