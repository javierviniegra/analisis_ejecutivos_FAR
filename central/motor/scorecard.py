"""Scorecard of KPIs with traffic lights (report "Semáforos scorecard").

Replicates the Power BI SemaforosKPIs model, page "Resultados KPI's", read from
SemaforosKPIs-TI_01.pbix (2026-10-29): the KPI list is its table
`Scorecard KPI`, the targets its measure `KPI Meta` and the lights its measure
`KPI Estado`. This module holds that definition as data plus the rule that
paints each row; reading the values is done elsewhere.
"""

from dataclasses import dataclass
from decimal import Decimal

from . import semaforos as s

FINANCIERO, CGI, COMERCIAL = "Financiero", "CGI", "Comercial"
CATEGORIAS = (FINANCIERO, CGI, COMERCIAL)

DINERO, PORCENTAJE, NUMERO = "dinero", "porcentaje", "numero"

# How each KPI's target is obtained (Power BI `KPI Meta`).
META_FIJA = "fija"  # a constant (`meta`)
META_HISTORICA = "historica"  # same days last year +5%, or previous month +5% without last year
META_MES_ANTERIOR = "mes_anterior"  # the previous month's value
META_FUENTE = "fuente"  # read from the KPI's own source (inventory value target)

# Which light rule applies (Power BI `KPI Estado`).
REGLA_UMBRAL = "umbral"  # fixed thresholds `verde` / `naranja`
REGLA_PCT_META = "pct_meta"  # actual / target: >= 100% / >= 90%
REGLA_CERO = "cero"  # 0 green, above red
REGLA_SIGNO = "signo"  # > 0 green, 0 orange, < 0 red
REGLA_GENERAL = "general"  # against the target with 5% tolerance

# Historic targets: +5% over the base period (`_Base Meta ... Año Anterior +5%`).
CRECIMIENTO_META = Decimal("1.05")


@dataclass(frozen=True)
class Kpi:
    clave: str
    nombre: str
    categoria: str
    orden: int
    tipo: str
    mayor_mejor: bool
    tipo_meta: str
    regla: str
    meta: Decimal | None = None  # META_FIJA only
    verde: Decimal | None = None  # REGLA_UMBRAL only
    naranja: Decimal | None = None


def _d(texto: str) -> Decimal:
    return Decimal(texto)


# Power BI order (`Scorecard KPI`[Orden]). "Talento Humano" is left out: its
# only row is a placeholder ("Nombre KPI talento") with no measure behind it.
KPIS = (
    # Financiero
    Kpi("ventas", "Ventas vs presupuesto", FINANCIERO, 1, DINERO, True, META_HISTORICA, REGLA_PCT_META),
    Kpi("costo_venta", "Costo de venta", FINANCIERO, 2, PORCENTAJE, False, META_FIJA, REGLA_UMBRAL,
        meta=_d("0.37"), verde=_d("0.37"), naranja=_d("0.39")),
    Kpi("valor_inventario", "Valor de inventario mensual", FINANCIERO, 3, DINERO, False, META_FUENTE, REGLA_GENERAL),
    Kpi("limpieza", "Gastos de artículos de limpieza", FINANCIERO, 4, DINERO, False, META_MES_ANTERIOR, REGLA_GENERAL),
    Kpi("gastos_salon", "Gastos salón", FINANCIERO, 5, DINERO, False, META_MES_ANTERIOR, REGLA_GENERAL),
    Kpi("hielo", "Hielo", FINANCIERO, 6, DINERO, False, META_MES_ANTERIOR, REGLA_GENERAL),
    Kpi("empaque", "Material de empaque", FINANCIERO, 7, DINERO, False, META_MES_ANTERIOR, REGLA_GENERAL),
    Kpi("tortillas", "Tortillas", FINANCIERO, 8, DINERO, False, META_MES_ANTERIOR, REGLA_GENERAL),
    Kpi("carbon", "Carbón", FINANCIERO, 9, DINERO, False, META_MES_ANTERIOR, REGLA_GENERAL),
    Kpi("pan", "Pan", FINANCIERO, 10, DINERO, False, META_MES_ANTERIOR, REGLA_GENERAL),
    # CGI
    Kpi("auditoria_cgi", "Resultado auditoría CGI", CGI, 11, PORCENTAJE, True, META_FIJA, REGLA_UMBRAL,
        meta=_d("0.85"), verde=_d("0.85"), naranja=_d("0.80")),
    Kpi("zenput_a_tiempo", "% tareas Zenput cerradas en tiempo", CGI, 12, PORCENTAJE, True, META_FIJA, REGLA_GENERAL,
        meta=_d("0.85")),
    Kpi("diferencia_inventario", "Diferencia inventario físico vs sistema", CGI, 13, PORCENTAJE, False, META_FIJA,
        REGLA_GENERAL, meta=_d("0.015")),
    Kpi("rendimiento_carne", "Rendimiento de carne por sucursal", CGI, 14, PORCENTAJE, True, META_FIJA, REGLA_GENERAL,
        meta=_d("0.85")),
    Kpi("incumplimiento_procesos", "Incidencia de incumplimiento de procesos", CGI, 15, NUMERO, False, META_FIJA,
        REGLA_CERO, meta=_d("0")),
    # Comercial
    Kpi("mix_bebidas", "Mix de ventas", COMERCIAL, 20, PORCENTAJE, True, META_FIJA, REGLA_UMBRAL,
        meta=_d("0.30"), verde=_d("0.30"), naranja=_d("0.26")),
    Kpi("cheque", "Cheque promedio", COMERCIAL, 21, DINERO, True, META_HISTORICA, REGLA_PCT_META),
    Kpi("ticket", "Ticket promedio", COMERCIAL, 22, DINERO, True, META_HISTORICA, REGLA_PCT_META),
    Kpi("clientes", "Clientes", COMERCIAL, 23, NUMERO, True, META_HISTORICA, REGLA_PCT_META),
    Kpi("delivery_errores", "Delivery órdenes sin errores", COMERCIAL, 24, PORCENTAJE, False, META_FIJA, REGLA_CERO,
        meta=_d("0")),
    Kpi("google", "Calificación Google", COMERCIAL, 25, PORCENTAJE, True, META_FIJA, REGLA_GENERAL, meta=_d("0.90")),
    Kpi("mystery_shopper", "Calificación Mystery Shopper", COMERCIAL, 26, PORCENTAJE, True, META_FIJA, REGLA_UMBRAL,
        meta=_d("0.90"), verde=_d("0.90"), naranja=_d("0.80")),
    Kpi("estandares_marca", "Cumplimiento de estándares visuales de marca", COMERCIAL, 27, PORCENTAJE, True,
        META_FIJA, REGLA_UMBRAL, meta=_d("0.90"), verde=_d("0.90"), naranja=_d("0.80")),
    # Power BI's `KPI Meta` says 1 but its light only looks at the sign; the
    # rules text calls it "meta técnica 0".
    Kpi("nps", "NPS (nivel de recomendación clientes)", COMERCIAL, 28, NUMERO, True, META_FIJA, REGLA_SIGNO,
        meta=_d("0")),
)

POR_CLAVE = {k.clave: k for k in KPIS}


def meta_historica(anio_anterior, mes_anterior) -> Decimal | None:
    """Target of sales, check, ticket and guests: the same days last year +5%;
    a branch without last year (new, or zero) uses the same days of the
    previous month +5%; neither -> no target."""
    for base in (anio_anterior, mes_anterior):
        if base is not None and Decimal(base) != 0:
            return Decimal(base) * CRECIMIENTO_META
    return None


def estado(kpi: Kpi, actual, meta) -> str | None:
    """Traffic light of one KPI row (Power BI `KPI Estado`)."""
    if kpi.regla == REGLA_UMBRAL:
        return s.umbral(actual, kpi.verde, kpi.naranja, mayor_mejor=kpi.mayor_mejor)
    if kpi.regla == REGLA_PCT_META:
        return s.porcentaje_meta(actual, meta)
    if kpi.regla == REGLA_CERO:
        return s.cero_es_verde(actual)
    if kpi.regla == REGLA_SIGNO:
        return s.signo(actual)
    return s.contra_meta(actual, meta, mayor_mejor=kpi.mayor_mejor)
