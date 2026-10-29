"""Scorecard of KPIs with traffic lights (report "Semáforos scorecard").

Replicates the Power BI SemaforosKPIs model, page "Resultados KPI's", read from
SemaforosKPIs-TI_01.pbix (2026-10-29): the KPI list is its table
`Scorecard KPI`, the targets its measure `KPI Meta` and the lights its measure
`KPI Estado`. This module holds that definition as data plus the rule that
paints each row; reading the values is done elsewhere.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from . import semaforos as s
from .comparativos import cobertura_fiable
from .periodo import Periodo, TipoPeriodo

CERO = Decimal("0")

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

# Owner, 2026-10-29: the report covers the current month up to the Sunday,
# sent every Monday; when that is fewer than 7 days (first Monday of a month)
# it covers the whole previous month instead.
DIAS_MINIMOS_MES = 7


@dataclass(frozen=True)
class PeriodosScorecard:
    actual: Periodo
    mes_anterior: Periodo  # the same days of the previous month (owner, 2026-10-29)
    anio_anterior: Periodo  # the same dates last year
    mes_cerrado: bool  # the whole previous month is reported (first Monday of a month)


def _mes(fecha: date) -> Periodo:
    return Periodo.de_fecha(TipoPeriodo.MES, fecha)


def periodos(hasta: date) -> PeriodosScorecard:
    """Periods of the report whose last day is `hasta` (the Sunday before the send)."""
    ultimo_del_mes = (hasta.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    mes_cerrado = hasta.day < DIAS_MINIMOS_MES
    if mes_cerrado or hasta == ultimo_del_mes:
        actual = _mes(hasta.replace(day=1) - timedelta(days=1) if mes_cerrado else hasta)
        return PeriodosScorecard(actual, actual.anterior(), actual.mismo_periodo_anio_anterior(), mes_cerrado)
    actual = Periodo.rango(hasta.replace(day=1), hasta)
    previo = _mes(actual.desde - timedelta(days=1))
    # 1-30 March against 1-28 February: a shorter previous month is taken whole.
    fin_previo = previo.desde.replace(day=hasta.day) if hasta.day <= previo.hasta.day else previo.hasta
    mes_anterior = Periodo.rango(previo.desde, fin_previo)
    return PeriodosScorecard(actual, mes_anterior, actual.mismo_periodo_anio_anterior(), False)


ANIO_ANTERIOR, MES_ANTERIOR = "anio_anterior", "mes_anterior"
KPIS_VENTAS = ("ventas", "cheque", "ticket", "clientes", "mix_bebidas")
# v1 (owner, 2026-10-29): sources the app does not read yet; shown grey as "sin fuente".
KPIS_SIN_FUENTE = ("valor_inventario", "auditoria_cgi", "zenput_a_tiempo", "diferencia_inventario",
                   "rendimiento_carne", "incumplimiento_procesos", "delivery_errores", "google",
                   "mystery_shopper", "estandares_marca", "nps")


def _pct(v: Decimal) -> str:
    return f"{(v * 100).normalize():f}%"  # 0.05 -> "5%", 0.015 -> "1.5%"


def regla_texto(kpi: Kpi) -> str:
    """The KPI's target and light in words, built from its own constants."""
    if kpi.regla == REGLA_PCT_META:
        return (f"Meta: mismos días del año anterior +{_pct(CRECIMIENTO_META - 1)} (sin año anterior fiable: "
                f"mismos días del mes anterior +{_pct(CRECIMIENTO_META - 1)}). Verde >= {_pct(s.PCT_META_VERDE)} "
                f"de la meta, naranja >= {_pct(s.PCT_META_NARANJA)}, rojo debajo.")
    if kpi.regla == REGLA_UMBRAL:
        if kpi.mayor_mejor:
            return f"Verde >= {_pct(kpi.verde)}, naranja >= {_pct(kpi.naranja)}, rojo debajo."
        return f"Verde <= {_pct(kpi.verde)}, naranja menor a {_pct(kpi.naranja)}, rojo {_pct(kpi.naranja)} o más."
    if kpi.regla == REGLA_CERO:
        return "Meta 0: verde en 0, rojo arriba de 0."
    if kpi.regla == REGLA_SIGNO:
        return "Verde arriba de 0, naranja en 0, rojo debajo de 0."
    meta = {META_MES_ANTERIOR: "mismos días del mes anterior", META_FUENTE: "la de su fuente"}.get(
        kpi.tipo_meta, _pct(kpi.meta) if kpi.meta is not None else "")
    lado = "abajo" if kpi.mayor_mejor else "arriba"
    return (f"Meta: {meta}. Verde si la cumple, naranja hasta {_pct(s.TOLERANCIA_GENERAL)} {lado} de la meta, "
            f"rojo más allá.")


def _razon(a: Decimal, b: Decimal) -> Decimal | None:
    return a / b if b else None


@dataclass
class Ventas:
    """Sales of one branch (or several, summed) in one period, from the tickets."""
    dias: int = 0  # days with tickets, summed over branches
    dias_esperados: int = 0
    venta: Decimal = CERO
    tickets: Decimal = CERO
    personas: Decimal = CERO
    personas_restaurante: Decimal = CERO
    alimentos: Decimal = CERO
    bebidas: Decimal = CERO

    @property
    def fiable(self) -> bool:
        """Project rule: data on at least 90% of the expected days."""
        return cobertura_fiable(self.dias, self.dias_esperados) and self.venta > 0

    def valor(self, clave: str) -> Decimal | None:
        if not self.dias:
            return None
        if clave == "ventas":
            return self.venta
        if clave == "cheque":  # Power BI: Total / Personas, every channel
            return _razon(self.venta, self.personas)
        if clave == "ticket":  # Power BI: average Total per ticket
            return _razon(self.venta, self.tickets)
        if clave == "clientes":  # restaurant orders only (owner, 2026-10-29)
            return self.personas_restaurante
        if clave == "mix_bebidas":  # drinks / drinks + food (no other group exists; same as Power BI's subtotal share)
            return _razon(self.bebidas, self.alimentos + self.bebidas)
        raise KeyError(clave)


def sumar(lista: list[Ventas]) -> Ventas:
    total = Ventas()
    for v in lista:
        for campo in Ventas.__dataclass_fields__:
            setattr(total, campo, getattr(total, campo) + getattr(v, campo))
    return total


def elegir_base(anio_anterior: Ventas | None, mes_anterior: Ventas | None) -> tuple[Ventas | None, str | None]:
    """Base of the historic targets (sales, check, ticket, guests): the same
    days last year; without a reliable last year (new branch, or data on less
    than 90% of its days) the same days of the previous month, as Power BI
    falls back when last year is blank; neither -> no target."""
    if anio_anterior is not None and anio_anterior.fiable:
        return anio_anterior, ANIO_ANTERIOR
    if mes_anterior is not None and mes_anterior.fiable:
        return mes_anterior, MES_ANTERIOR
    return None, None


def meta_desde_base(base: Decimal | None) -> Decimal | None:
    """Historic target: the base +5% (`_Base Meta ... Año Anterior +5%`)."""
    return None if not base else base * CRECIMIENTO_META


@dataclass(frozen=True)
class Fila:
    kpi: Kpi
    actual: Decimal | None  # every branch of the selection
    mes_anterior: Decimal | None  # same days of the previous month, every branch
    meta: Decimal | None
    estado: str | None
    actual_comparado: Decimal | None  # what the light compares: branches with a target only


@dataclass(frozen=True)
class BloqueVentas:
    filas: list[Fila]
    meta_mes_anterior: list[str]  # branches whose target comes from the previous month
    sin_meta: list[str]  # branches without a reliable base: out of the historic targets


def filas_ventas(nombres: list[str], actuales: list[Ventas], mes_anterior: list[Ventas],
                 anio_anterior: list[Ventas]) -> BloqueVentas:
    """The five sales rows for one branch or a consolidated selection (lists
    aligned by branch). Historic targets follow the comparable-branches rule:
    each branch brings its own base (last year, else previous month); a
    branch without one is left out of both the target and the actual it is
    compared with, so a new branch never inflates the result."""
    bases = [elegir_base(a, m) for a, m in zip(anio_anterior, mes_anterior)]
    con_base = [i for i, (b, _) in enumerate(bases) if b is not None]
    total, total_previo = sumar(actuales), sumar(mes_anterior)
    comparado = sumar([actuales[i] for i in con_base])
    base = sumar([bases[i][0] for i in con_base]) if con_base else None
    filas = []
    for clave in KPIS_VENTAS:
        kpi = POR_CLAVE[clave]
        if kpi.tipo_meta == META_HISTORICA:
            meta = meta_desde_base(base.valor(clave)) if base else None
            valor_comparado = comparado.valor(clave) if con_base else None
        else:
            meta, valor_comparado = kpi.meta, total.valor(clave)
        filas.append(Fila(kpi, total.valor(clave), total_previo.valor(clave), meta,
                          estado(kpi, valor_comparado, meta), valor_comparado))
    return BloqueVentas(filas,
                        [nombres[i] for i in con_base if bases[i][1] == MES_ANTERIOR],
                        [nombres[i] for i in range(len(nombres)) if i not in con_base])


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
