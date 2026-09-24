"""Footnotes of a report (pure: no I/O).

Two kinds, both printed at the foot of every report (owner, 2026-09-24):
- Coverage notes: missing cash closings, partial ticket detail, and why a
  comparison is "s/cf" (sin comparativo fiable).
- Rules and thresholds: every threshold the report applies is documented in
  the report itself. The texts are built from the same constants the code
  uses, so the documentation can never drift from the calculation.
"""

from decimal import Decimal

from . import lectura
from .comparativos import UMBRAL_COBERTURA_FIABLE, UMBRAL_IGUAL, cobertura_fiable
from .fuentes.wansoft import HORA_CORTE_DIA
from .metricas import Comparacion, Metricas, como_comparacion
from .periodo import Periodo, TipoPeriodo


def _num(v: Decimal) -> str:
    return f"{(Decimal(v) * 100).normalize():f}"


def _pct(v: Decimal) -> str:
    return f"{_num(v)}%"


def _pp(v: Decimal) -> str:
    return f"{_num(v)} pp"


def _lista(nombres: list[str]) -> str:
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def notas_cobertura(periodo: Periodo, actual: Metricas, anterior: Comparacion | Metricas | None,
                    anio_anterior: Comparacion | Metricas | None) -> list[str]:
    notas = []
    esperados = actual.dias_esperados
    if actual.dias_con_cierre < esperados:
        extra = "" if cobertura_fiable(actual.dias_con_cierre, esperados) else ": sus comparativos son s/cf"
        notas.append(f"El periodo tiene cierres de caja en {actual.dias_con_cierre} de {esperados} días{extra}.")
    if actual.dias_con_cierre and actual.dias_con_detalle == 0:
        notas.append("No hay detalle de tickets en el periodo: no se muestran mezcla ni canal.")
    elif 0 < actual.dias_con_detalle < esperados:
        extra = "" if cobertura_fiable(actual.dias_con_detalle, esperados) else " y sus comparativos s/cf"
        notas.append(f"El detalle de tickets cubre {actual.dias_con_detalle} de {esperados} días: "
                     f"mezcla y canal son parciales{extra}.")
    comparaciones = [(como_comparacion(actual, anterior), lectura.vs_anterior(periodo))]
    if periodo.tipo != TipoPeriodo.ANIO:  # for a year both comparisons are the same period
        comparaciones.append((como_comparacion(actual, anio_anterior), lectura.vs_anio(periodo)))
    for comp, nombre in comparaciones:
        if comp.excluidas and comp.base is None:
            verbo = "no tiene" if len(comp.excluidas) == 1 else "no tienen"
            notas.append(f"Sin comparativo contra {nombre}: {_lista(comp.excluidas)} {verbo} datos completos "
                         "en ese periodo (sucursal nueva o sin operación).")
        elif comp.excluidas:
            verbo = "se excluye" if len(comp.excluidas) == 1 else "se excluyen"
            notas.append(f"Comparativo contra {nombre} solo con sucursales comparables: {verbo} "
                         f"{_lista(comp.excluidas)} por no tener datos completos en ese periodo "
                         "(sucursal nueva o sin operación).")
        m = comp.base
        if m is None or m.dias_con_cierre == 0:
            continue  # no data at all: plain "s/c", nothing to explain
        if not cobertura_fiable(m.dias_con_cierre, m.dias_esperados):
            notas.append(f"s/cf contra {nombre}: tiene cierres de caja en {m.dias_con_cierre} de "
                         f"{m.dias_esperados} días.")
        elif not cobertura_fiable(m.dias_con_detalle, m.dias_esperados) and m.dias_con_detalle:
            notas.append(f"Mezcla y canal s/cf contra {nombre}: el detalle de tickets cubre "
                         f"{m.dias_con_detalle} de {m.dias_esperados} días.")
    return notas


def notas_reglas() -> list[str]:
    return [
        f"Flechas: ▲ verde mejora, ▼ rojo empeora; «=» gris si el cambio está dentro de ±{_pct(UMBRAL_IGUAL)} "
        f"(±{_pp(UMBRAL_IGUAL)}, puntos porcentuales, en porcentajes). En cancelaciones, cortesías y descuentos subir es peor. "
        "Mezcla, canal y presupuesto se muestran siempre en gris.",
        f"s/c: sin comparativo (no hay datos). s/cf: sin comparativo fiable, cuando alguno de los periodos "
        f"tiene datos en menos del {_pct(UMBRAL_COBERTURA_FIABLE)} de los días esperados.",
        f"Sucursales comparables: una sucursal sin datos en al menos el {_pct(UMBRAL_COBERTURA_FIABLE)} de los "
        "días del periodo de comparación (nueva o sin operación) se excluye de ambos lados de esa comparación; "
        "la columna del periodo muestra siempre el total de todas las sucursales elegidas.",
        f"Día operativo: un cierre de caja hecho antes de las {HORA_CORTE_DIA}:00 cuenta para el día anterior; "
        "los cierres duplicados (mismo día y mismos totales) se cuentan una sola vez.",
        "Semana de lunes a domingo; el mismo periodo del año anterior de una semana es la misma semana ISO "
        "del año anterior.",
        f"Lectura: controles solo si suben y pesan al menos {_pct(lectura.UMBRAL_PESO_CONTROL)} de la venta neta; "
        f"mezcla y canal solo si se mueven más de {_pp(lectura.UMBRAL_PUNTOS_MEZCLA)}; Costo de Ventas solo si "
        "supera el presupuesto prorrateado por días.",
    ]


def notas_pie(periodo: Periodo, actual: Metricas, anterior: Comparacion | Metricas | None,
              anio_anterior: Comparacion | Metricas | None) -> list[str]:
    return notas_cobertura(periodo, actual, anterior, anio_anterior) + notas_reglas()
