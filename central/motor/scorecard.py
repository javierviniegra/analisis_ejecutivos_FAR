"""Scorecard of KPIs with traffic lights (report "Semáforos scorecard").

Replicates the Power BI SemaforosKPIs model, page "Resultados KPI's", read from
SemaforosKPIs-TI_01.pbix (2026-10-29): the KPI list is its table
`Scorecard KPI`, the targets its measure `KPI Meta` and the lights its measure
`KPI Estado`. This module holds that definition as data plus the rule that
paints each row; reading the values is done elsewhere.
"""

import unicodedata
from dataclasses import dataclass, field
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
    venta_neta: Decimal = CERO  # without IVA: the cost of sales' denominator (Power BI: Ventas[Subtotal])

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


# -- cost of sales and expenses (block 3) -----------------------------------
KPIS_GASTO = ("limpieza", "gastos_salon", "hielo", "empaque", "tortillas", "carbon", "pan")
KPIS_COSTO_GASTOS = ("costo_venta",) + KPIS_GASTO
KPIS_LEIDOS = KPIS_VENTAS + KPIS_COSTO_GASTOS
# Power BI `_Base Limpieza` ... `_Base Carbon`: the subcuentas (upper case, no
# accents) that make each expense line. "Contiene" also takes e.g. "Eq para
# Salón" into Gastos salón and both "Artículos de Limpieza" accounts, as Power BI.
SUBCUENTAS = {"limpieza": ("contiene", "LIMPIEZA"), "gastos_salon": ("contiene", "SALON"),
              "hielo": ("contiene", "HIELO"), "empaque": ("contiene", "EMPAQUE"), "carbon": ("igual", "CARBON")}


def normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sin_acentos.strip().upper()


WANSOFT, ODOO = "wansoft", "odoo"


@dataclass
class Componente:
    """One account (or source) summed into a row, with its amount per system."""
    etiqueta: str  # e.g. "Gastos de venta / Gastos de Salón (salsas de sobre, etc)"
    por_sistema: dict[str, Decimal] = field(default_factory=dict)

    @property
    def total(self) -> Decimal:
        return sum(self.por_sistema.values(), CERO)


@dataclass
class Gastos:
    """Invoiced cost and expenses of one branch (or several, summed) in one period."""
    costo_operativo: Decimal = CERO
    montos: dict[str, Decimal] = field(default_factory=dict)  # expense KPI clave -> amount
    # Where each row's amount comes from (owner, 2026-10-30: shown under the
    # table): KPI clave -> {account key (no accents) -> Componente}, and the
    # same per supplier for the invoice-based expense rows.
    detalle: dict[str, dict[str, Componente]] = field(default_factory=dict)
    proveedores: dict[str, dict[str, Componente]] = field(default_factory=dict)


def _agregar(detalle: dict, clave: str, etiqueta: str, sistema: str, monto: Decimal) -> None:
    c = detalle.setdefault(clave, {}).setdefault(normalizar(etiqueta), Componente(etiqueta))
    c.por_sistema[sistema] = c.por_sistema.get(sistema, CERO) + monto


def gastos_de(lineas: dict[tuple, Decimal], pan_tortillas_por_fuente: dict[tuple, Decimal]) -> Gastos:
    """`lineas`: {(cuenta, subcuenta, system, is Costo Operativo, supplier): subtotal}
    of the supplier invoices; `pan_tortillas_por_fuente`: {(department, system): amount}."""
    g = Gastos(montos={clave: CERO for clave in KPIS_GASTO})
    for (cuenta, subcuenta, sistema, operativo, proveedor), monto in lineas.items():
        etiqueta = f"{cuenta or 'Sin cuenta'} / {subcuenta or 'Sin subcuenta'}"
        if operativo:
            g.costo_operativo += monto
            _agregar(g.detalle, "costo_venta", subcuenta or "Sin subcuenta", sistema, monto)
        nombre = normalizar(subcuenta)
        for clave, (modo, texto) in SUBCUENTAS.items():
            if (texto in nombre) if modo == "contiene" else (nombre == texto):
                g.montos[clave] += monto
                _agregar(g.detalle, clave, etiqueta, sistema, monto)
                _agregar(g.proveedores, clave, proveedor or "Sin proveedor", sistema, monto)
    for (depto, sistema), monto in pan_tortillas_por_fuente.items():
        clave = "pan" if depto == PAN else "tortillas"
        g.montos[clave] += monto
        _agregar(g.detalle, clave, "Entradas por factura" if sistema == WANSOFT else "Compras", sistema, monto)
    return g


PAN, TORTILLAS = "PAN", "TORTILLAS"
# Owner, 2026-10-29: in Odoo these branches buy bread and tortillas that the
# product catalogue (dim_product, Wansoft project) has not mapped to a
# department yet (Bolillo, Tortilla de Harina...: ~$18.5k in September 2026),
# so their bread and tortillas are partial until it does. By short key.
PAN_TORTILLAS_PARCIAL = ("CentroMyJ", "Puebla")


def pan_tortillas(entradas: dict, compras_odoo: dict, inicio_odoo: date | None) -> tuple[dict[tuple, Decimal], list]:
    """Bread and tortillas of one branch (owner, 2026-10-29): Wansoft's invoiced
    entries EVERY day -- the branches buying in Odoo still capture bread in
    Wansoft and buy none in Odoo -- plus its Odoo purchases from the day it
    buys in Odoo (earlier Odoo activity is pilot noise). Both maps are
    {(department, day): amount}; returns {(department, system): amount} and
    the (department, day) found in both sources, which might be counted twice
    and are reported."""
    montos: dict[tuple, Decimal] = {}
    for (depto, _dia), monto in entradas.items():
        montos[(depto, WANSOFT)] = montos.get((depto, WANSOFT), CERO) + monto
    dobles = []
    if inicio_odoo is not None:
        for (depto, dia), monto in compras_odoo.items():
            if dia >= inicio_odoo:
                montos[(depto, ODOO)] = montos.get((depto, ODOO), CERO) + monto
                if entradas.get((depto, dia)):
                    dobles.append((depto, dia))
    return montos, sorted(dobles, key=lambda x: (x[1], x[0]))


def sumar_gastos(lista: list[Gastos]) -> Gastos:
    total = Gastos(montos={clave: CERO for clave in KPIS_GASTO})
    for g in lista:
        total.costo_operativo += g.costo_operativo
        for clave, monto in g.montos.items():
            total.montos[clave] = total.montos.get(clave, CERO) + monto
        for destino, origen in ((total.detalle, g.detalle), (total.proveedores, g.proveedores)):
            for clave, componentes in origen.items():
                for c in componentes.values():
                    for sistema, monto in c.por_sistema.items():
                        _agregar(destino, clave, c.etiqueta, sistema, monto)
    return total


def pct_costo(ventas: list[Ventas], gastos: list[Gastos]) -> Decimal | None:
    """Invoiced Costo Operativo over the net sales of the SAME branches: a
    branch with no invoice in the period is no data (never 0%) and its sales
    stay out of the denominator."""
    con_costo = [i for i, g in enumerate(gastos) if g.costo_operativo > 0]
    venta = sum((ventas[i].venta_neta for i in con_costo), CERO)
    return _razon(sum((gastos[i].costo_operativo for i in con_costo), CERO), venta)


@dataclass(frozen=True)
class BloqueGastos:
    filas: list[Fila]
    sin_costo: list[str]  # branches without invoiced cost in the period
    sin_meta: list[str]  # branches without a reliable previous month: out of the expense targets
    detalle: dict[str, dict[str, Componente]] = field(default_factory=dict)  # current period, every branch
    proveedores: dict[str, dict[str, Componente]] = field(default_factory=dict)


def filas_gastos(nombres: list[str], ventas: list[Ventas], ventas_previo: list[Ventas],
                 gastos: list[Gastos], gastos_previo: list[Gastos]) -> BloqueGastos:
    """Cost of sales and the seven expense rows (lists aligned by branch).
    Expense targets are the same days of the previous month; a branch that did
    not operate that period reliably (its sales, the project's 90% rule) is
    left out of the target and of the actual compared with it."""
    k = POR_CLAVE["costo_venta"]
    actual_costo = pct_costo(ventas, gastos)
    filas = [Fila(k, actual_costo, pct_costo(ventas_previo, gastos_previo), k.meta, estado(k, actual_costo, k.meta),
                  actual_costo)]
    con_base = [i for i, v in enumerate(ventas_previo) if v.fiable]
    total, total_previo = sumar_gastos(gastos), sumar_gastos(gastos_previo)
    comparado = sumar_gastos([gastos[i] for i in con_base])
    base = sumar_gastos([gastos_previo[i] for i in con_base])
    for clave in KPIS_GASTO:
        kpi = POR_CLAVE[clave]
        meta = base.montos[clave] if con_base else None
        valor_comparado = comparado.montos[clave] if con_base else None
        filas.append(Fila(kpi, total.montos[clave], total_previo.montos[clave], meta,
                          estado(kpi, valor_comparado, meta), valor_comparado))
    filas.sort(key=lambda f: f.kpi.orden)
    return BloqueGastos(filas, [nombres[i] for i, g in enumerate(gastos) if g.costo_operativo <= 0],
                        [nombres[i] for i in range(len(nombres)) if i not in con_base], total.detalle,
                        total.proveedores)


PROVEEDORES_EN_DESGLOSE = 3


@dataclass(frozen=True)
class Desglose:
    kpi: Kpi
    cuentas: list[Componente]  # largest first
    proveedores: list[Componente]  # the largest PROVEEDORES_EN_DESGLOSE
    otros_proveedores: Decimal  # the rest of the suppliers together
    n_otros: int


def desglose(detalle: dict[str, dict[str, Componente]],
             proveedores: dict[str, dict[str, Componente]]) -> list[Desglose]:
    """Where every cost and expense row comes from (owner, 2026-10-30, under
    the table): its accounts (or sources) with their amount per system, and
    its largest suppliers, in the catalogue's order; rows without amount out."""
    resultado = []
    for kpi in KPIS:
        if kpi.clave not in KPIS_COSTO_GASTOS:
            continue
        cuentas = sorted(detalle.get(kpi.clave, {}).values(), key=lambda c: -c.total)
        if not any(c.total for c in cuentas):
            continue
        por_proveedor = sorted(proveedores.get(kpi.clave, {}).values(), key=lambda c: -c.total)
        resto = por_proveedor[PROVEEDORES_EN_DESGLOSE:]
        resultado.append(Desglose(kpi, cuentas, por_proveedor[:PROVEEDORES_EN_DESGLOSE],
                                  sum((c.total for c in resto), CERO), len(resto)))
    return resultado


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
