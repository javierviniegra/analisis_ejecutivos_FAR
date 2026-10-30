"""Footnotes of a report (pure: no I/O).

Two kinds, both printed at the foot of every report (owner, 2026-09-24):
- Coverage notes: missing cash closings, partial ticket detail, and why a
  comparison is "s/cf" (sin comparativo fiable).
- Rules and thresholds: every threshold the report applies is documented in
  the report itself. The texts are built from the same constants the code
  uses, so the documentation can never drift from the calculation.
"""

from decimal import Decimal

from . import lectura, scorecard, semaforos
from .comparativos import (NARANJA, ROJO, UMBRAL_COBERTURA_FIABLE, UMBRAL_IGUAL, VERDE, cobertura_fiable,
                           kpi_costo)
from .fuentes import presupuestos
from .fuentes.wansoft import HORA_CORTE_DIA
from .metricas import UMBRAL_FACTURADO_COMPLETO, Comparacion, Metricas, como_comparacion
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
                    anio_anterior: Comparacion | Metricas | None, incluir_costos: bool = True) -> list[str]:
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
    if actual.cortes_descartados:
        lista = "; ".join(f"{n} {d:%d/%m} (${t:,.0f})" for n, d, t in sorted(actual.cortes_descartados,
                                                                              key=lambda x: (x[1], x[0])))
        notas.append("Se descartaron cortes de caja que no coinciden con los tickets del día (otro corte del mismo "
                     f"día sí coincide): {lista}.")
    if actual.dias_por_tickets:
        lista = "; ".join(f"{n} {d:%d/%m} (${t:,.0f})" for n, d, t in sorted(actual.dias_por_tickets,
                                                                              key=lambda x: (x[1], x[0])))
        notas.append("Sin corte de caja en la base; la venta del día se tomó de los tickets (venta, tickets y "
                     f"clientes; sin cancelaciones, cortesías ni descuentos): {lista}.")
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
    if not incluir_costos:
        return notas
    notas += _notas_costo_preliminar(periodo, actual, comparaciones)
    notas += _notas_costo_estimado(actual, comparaciones)
    if periodo.tipo == TipoPeriodo.RANGO:
        notas.append("Costo total: no disponible en un rango libre (solo semana, mes o bloques de meses).")
    return notas


def _notas_costo_estimado(actual: Metricas, comparaciones) -> list[str]:
    notas = []
    if actual.costo_odoo_sin_leer:
        notas.append("No se pudo leer Odoo: el costo total de las sucursales con costo de Odoo puede estar "
                     "incompleto (facturación atrasada) y no se estimó.")
    # Said only when the cost IS estimated, with how (owner, 2026-10-05); a complete cost is just given.
    if actual.costo_estimado_odoo:
        pct = actual.pct_facturado_odoo
        cuanto = f"Odoo ha facturado el {pct * 100:.0f}% de la venta neta" if pct is not None else "Odoo no ha facturado"
        notas.append(f"Costo total estimado en sucursales con costo de Odoo: {cuanto} de esos días (las facturas "
                     "de venta, de las que sale su costo, se crean con atraso); mientras no llegue al "
                     f"{_pct(UMBRAL_FACTURADO_COMPLETO)}, su costo = costo de Odoo / facturado de Odoo x venta "
                     "neta de Wansoft.")
        if actual.costo_total is None:
            notas.append("Sin facturas en Odoo todavía para esos días: el costo total queda sin dato.")
    if actual.costo_estimado_wansoft:
        notas.append(f"Costo total estimado en sucursales con costo de Wansoft: Wansoft aún no descuenta del "
                     f"inventario ${actual.pendiente_wansoft:,.0f} del costo de lo vendido (pendiente de rebaja); "
                     "se suma a su costo hasta que el pendiente llegue a 0.")
    previos = [nombre for comp, nombre in comparaciones if comp.base is not None and comp.base.costo_total_estimado]
    if previos:
        notas.append(f"Costo total de {_lista(previos)} también estimado (aún incompleto).")
    return notas


def _notas_costo_preliminar(periodo: Periodo, actual: Metricas, comparaciones) -> list[str]:
    if actual.costo_preliminar:
        definitivo = presupuestos.fecha_definitiva(periodo.hasta)
        if actual.costo_ventas_real is None:
            return [f"Costo de Ventas real: aún no hay facturas registradas del periodo; "
                    f"será definitivo a partir del {definitivo:%d/%m/%Y}."]
        return [f"Costo de Ventas real preliminar (s/cf): será definitivo a partir del {definitivo:%d/%m/%Y}."]
    previos = [nombre for comp, nombre in comparaciones if comp.base is not None and comp.base.costo_preliminar]
    if previos:
        return [f"Costo de Ventas real de {_lista(previos)} aún preliminar: su comparativo es s/cf."]
    return []


# Owner, 2026-10-29: a highlighted legend under the indicators table saying what
# each dot means; built from the same constants as the lights.
TITULO_LEYENDA = "Qué significan las bolitas"
COLORES_LEYENDA = ((VERDE, "en meta"), (NARANJA, "alerta"), (ROJO, "fuera de meta"))


def leyenda_semaforos(incluir_costos: bool = True) -> list[str]:
    """One line per kind of light of the indicators table."""
    mix, costo = scorecard.POR_CLAVE["mix_bebidas"], kpi_costo()
    crece = _pct(scorecard.CRECIMIENTO_META - 1)
    lineas = [
        f"Venta bruta, clientes, cheque y ticket promedio: meta = mismo periodo del año anterior +{crece} (sin año "
        f"anterior, el periodo anterior +{crece}). Verde desde el {_pct(semaforos.PCT_META_VERDE)} de la meta, "
        f"naranja desde el {_pct(semaforos.PCT_META_NARANJA)}, rojo abajo del {_pct(semaforos.PCT_META_NARANJA)}.",
        f"Mix de bebidas: verde desde {_pct(mix.verde)}, naranja desde {_pct(mix.naranja)}, rojo abajo de "
        f"{_pct(mix.naranja)}.",
    ]
    if incluir_costos:
        lineas.append(f"Costo / venta neta: verde de {_pct(costo.verde)} a menos de {_pct(costo.naranja)}, naranja "
                      f"abajo de {_pct(costo.verde)} (se compró o se registró de menos), rojo {_pct(costo.naranja)} "
                      "o más.")
    lineas.append("Sin bolita: no hay meta (sin datos o sin comparativo fiable).")
    return lineas


def _reglas_semaforos() -> list[str]:
    """The scorecard lights of the indicators table, from the scorecard's constants (owner, 2026-10-29)."""
    mix = scorecard.POR_CLAVE["mix_bebidas"]
    return [
        f"Semáforos de venta bruta, clientes, cheque y ticket promedio (scorecard): meta = mismo periodo del año "
        f"anterior +{_num(scorecard.CRECIMIENTO_META - 1)}%; sin año anterior, el periodo inmediato anterior "
        f"+{_num(scorecard.CRECIMIENTO_META - 1)}%; solo sucursales comparables, y sin comparativo fiable no hay "
        f"meta ni color. Verde desde el {_pct(semaforos.PCT_META_VERDE)} de la meta, naranja desde el "
        f"{_pct(semaforos.PCT_META_NARANJA)}, rojo abajo.",
        f"Semáforo del mix de bebidas (venta de bebidas / venta de alimentos y bebidas): verde desde "
        f"{_pct(mix.verde)}, naranja desde {_pct(mix.naranja)}, rojo abajo.",
    ]


def notas_reglas(periodo: Periodo | None = None, incluir_costos: bool = True) -> list[str]:
    reglas = [
        f"Flechas: ▲ verde mejora, ▼ rojo empeora; «=» gris si el cambio está dentro de ±{_pct(UMBRAL_IGUAL)} "
        f"(±{_pp(UMBRAL_IGUAL)}, puntos porcentuales, en porcentajes). En cancelaciones, cortesías y descuentos subir es peor. "
        "Mezcla, canal y presupuesto se muestran siempre en gris.",
        f"s/c: sin comparativo (no hay datos). s/cf: sin comparativo fiable, cuando alguno de los periodos "
        f"tiene datos en menos del {_pct(UMBRAL_COBERTURA_FIABLE)} de los días esperados.",
        f"Sucursales comparables: la que no tiene datos en el {_pct(UMBRAL_COBERTURA_FIABLE)} de los días del "
        "periodo de comparación (nueva o sin operación) sale de ambos lados; la columna del periodo es el total.",
        f"Día operativo: un cierre de caja hecho antes de las {HORA_CORTE_DIA}:00 cuenta para el día anterior; "
        "los cierres duplicados (mismo día y mismos totales) se cuentan una sola vez; si un día tiene varios "
        "cierres y uno coincide con los tickets del día, solo cuenta ese; un día con tickets y sin cierre toma la "
        "venta de los tickets.",
        f"Lectura: controles solo si suben y pesan al menos {_pct(lectura.UMBRAL_PESO_CONTROL)} de la venta neta; "
        f"mezcla y canal solo si se mueven más de {_pp(lectura.UMBRAL_PUNTOS_MEZCLA)}"
        + ("; Costo de Ventas solo si supera el presupuesto prorrateado por días." if incluir_costos else "."),
    ]
    costos = [
        f"Costo de Ventas real: preliminar (s/cf) hasta {presupuestos.DIAS_CIERRE_MES} días después del cierre del "
        "mes del periodo, porque las facturas se siguen capturando en Odoo.",
        f"Meta de costo: de {_pct(kpi_costo().verde)} a menos de {_pct(kpi_costo().naranja)} de la venta neta "
        f"(verde); abajo de {_pct(kpi_costo().verde)} naranja (se compró o se registró de menos); "
        f"{_pct(kpi_costo().naranja)} o más rojo (se compró de más). Costo total = reporte de costos "
        "de Wansoft u Odoo (costo total menos consumo; el consumo se registra de forma irregular); costo facturado = "
        "facturas de Presupuestos AP (el flujo); la medición por mercancía recibida está pendiente.",
    ]
    reglas += _reglas_semaforos()
    reglas.append("Propina: la registrada en los pagos de las cuentas de salón de los meseros activos, sobre su "
                  "venta de salón (como en el reporte de meseros); se compara en puntos porcentuales.")
    if incluir_costos:
        reglas += costos
    if periodo is None or periodo.tipo == TipoPeriodo.SEMANA:
        reglas.insert(4, "Semana de lunes a domingo; la misma semana del año anterior es la misma semana ISO "
                         "del año anterior.")
    return reglas


def notas_pie(periodo: Periodo, actual: Metricas, anterior: Comparacion | Metricas | None,
              anio_anterior: Comparacion | Metricas | None) -> list[str]:
    return notas_cobertura(periodo, actual, anterior, anio_anterior) + notas_reglas(periodo)
