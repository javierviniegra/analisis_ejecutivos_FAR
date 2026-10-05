"""Metrics of a period for one branch or several (consolidated).

`recolectar` reads the sources (read-only) for several branches and ONE
period, one batched query per source table; `consolidar` adds several
branches together. Everything else here is pure.

Coverage is tracked explicitly (days with cash closing / with ticket detail
out of the days expected) so reports can flag partial data instead of
presenting a partial sum as if it were complete.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from .comparativos import cobertura_fiable
from .fuentes import odoo as odoo_fuente
from .fuentes import presupuestos, wansoft
from .periodo import Periodo, TipoPeriodo

CERO = Decimal("0")


def _razon(numerador, denominador) -> Decimal | None:
    if numerador is None or not denominador:
        return None
    return Decimal(numerador) / Decimal(denominador)


@dataclass
class Metricas:
    periodo: Periodo
    n_sucursales: int = 1
    venta_bruta: Decimal = CERO
    venta_neta: Decimal = CERO
    tickets: Decimal = CERO
    clientes: Decimal = CERO
    mesas: Decimal = CERO
    cortesias: Decimal = CERO
    cancelaciones: Decimal = CERO
    anulaciones: Decimal = CERO
    descuentos: Decimal = CERO
    canal: dict[str, Decimal] = field(default_factory=dict)  # salon / llevar / plataformas / otros
    mix: dict[str, Decimal] = field(default_factory=dict)  # Alimentos / Bebidas
    venta_por_dia: dict[date, Decimal] = field(default_factory=dict)  # gross sales (con IVA) per operating day, for the charts
    tickets_por_dia: dict[date, Decimal] = field(default_factory=dict)  # for the detail page
    clientes_por_dia: dict[date, Decimal] = field(default_factory=dict)
    dias_con_cierre: int = 0  # summed over branches
    dias_con_detalle: int = 0  # summed over branches
    costo_ventas_real: Decimal | None = None  # None = not available (never zero)
    costo_ventas_ppto: Decimal | None = None  # shown even when no real spend is recorded yet
    # "% ejercido" only over the branches that have BOTH budget and real spend,
    # so the ratio never mixes branches with and without budget, nor counts a
    # budget whose spend has not been recorded yet as 0% spent.
    costo_ventas_real_con_ppto: Decimal | None = None
    costo_ventas_ppto_con_real: Decimal | None = None
    n_con_presupuesto: int = 0
    # Real spend still being captured (presupuestos.es_preliminar): shown, not compared.
    costo_preliminar: bool = False
    # Net sales of the branches that have real Costo de Ventas: the base of
    # "cost % of net sales", so branches without cost data never dilute it.
    venta_neta_con_costo: Decimal | None = None
    # Total cost (Wansoft or Odoo cost report, the data guide's "Costo Total":
    # CostoTotal - consumption), with the net sales of the branches that have it.
    costo_total: Decimal | None = None
    venta_neta_con_costo_total: Decimal | None = None
    # Branches with Odoo cost (see estimar_costo_odoo): Wansoft net sales of their
    # Odoo-cost days and what Odoo has invoiced of them; while not fully
    # invoiced the total cost is an estimate.
    costo_estimado_odoo: bool = False
    venta_dias_odoo: Decimal | None = None
    facturado_odoo: Decimal | None = None
    costo_odoo_sin_leer: bool = False  # Odoo could not be read: Odoo-cost days may be partial
    # Branches with Wansoft cost: cost of what was sold not yet discounted from
    # inventory (added to the cost while above 0, which makes it an estimate).
    pendiente_wansoft: Decimal | None = None

    @property
    def costo_estimado_wansoft(self) -> bool:
        return bool(self.pendiente_wansoft)

    @property
    def costo_total_estimado(self) -> bool:
        return self.costo_estimado_odoo or self.costo_estimado_wansoft

    @property
    def dias_esperados(self) -> int:
        return self.periodo.dias * self.n_sucursales

    @property
    def cheque_promedio(self) -> Decimal | None:
        return _razon(self.venta_bruta, self.clientes)

    @property
    def ticket_promedio(self) -> Decimal | None:
        return _razon(self.venta_bruta, self.tickets)

    def pct_canal(self, canal: str) -> Decimal | None:
        return _razon(self.canal.get(canal, CERO), sum(self.canal.values(), CERO)) if self.canal else None

    def pct_mix(self, grupo: str) -> Decimal | None:
        return _razon(self.mix.get(grupo, CERO), sum(self.mix.values(), CERO)) if self.mix else None

    @property
    def ejercido_costo_ventas(self) -> Decimal | None:
        """Real Costo de Ventas as a share of its budget (1.0 = 100%)."""
        return _razon(self.costo_ventas_real_con_ppto, self.costo_ventas_ppto_con_real)

    @property
    def pct_costo_total(self) -> Decimal | None:
        """Total cost (Wansoft/Odoo) as a share of the net sales of the same branches."""
        return _razon(self.costo_total, self.venta_neta_con_costo_total)

    @property
    def pct_facturado_odoo(self) -> Decimal | None:
        """Share of the Odoo-cost days' net sales already invoiced in Odoo."""
        return _razon(self.facturado_odoo, self.venta_dias_odoo)

    @property
    def pct_costo_ventas(self) -> Decimal | None:
        """Real (invoiced) Costo de Ventas as a share of the net sales of the
        same branches (0.385 = 38.5%)."""
        return _razon(self.costo_ventas_real, self.venta_neta_con_costo)


def _meses(desde: date, hasta: date) -> list[tuple[date, date]]:
    tramos, d = [], desde.replace(day=1)
    while d <= hasta:
        siguiente = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        tramos.append((d, siguiente - timedelta(days=1)))
        d = siguiente
    return tramos


def costos_totales(cur_wansoft, subsidiary_ids: list[int], periodo: Periodo) -> dict[int, Decimal] | None:
    """Total cost per branch for the period, from the cost snapshots: a week
    from the weekly table, a month from the monthly table, a bimester / quarter
    / semester / year as the sum of its months. A free range cannot be built
    without mixing definitions (the daily table includes consumption): None.
    A branch whose cost is 0 has no data (e.g. a branch born on Odoo before its
    cost history is loaded), never a 0% cost."""
    if periodo.tipo == TipoPeriodo.RANGO:
        return None
    if periodo.tipo == TipoPeriodo.SEMANA:
        costos = wansoft.costo_total_semana(cur_wansoft, subsidiary_ids, periodo.desde)
    else:
        costos: dict[int, Decimal] = {}
        for primero, ultimo in _meses(periodo.desde, periodo.hasta):
            for sid, v in wansoft.costo_total_mes(cur_wansoft, subsidiary_ids, primero, ultimo).items():
                costos[sid] = costos.get(sid, CERO) + v
    return {sid: v for sid, v in costos.items() if v}


def pendientes_rebaja(cur_wansoft, subsidiary_ids: list[int], periodo: Periodo) -> dict[int, Decimal]:
    """Cost not yet discounted by Wansoft per branch, from the same snapshots as
    `costos_totales` (business rule, owner 2026-10-05): only branches with some."""
    if periodo.tipo == TipoPeriodo.RANGO or not subsidiary_ids:
        return {}
    if periodo.tipo == TipoPeriodo.SEMANA:
        pendientes = wansoft.costo_total_semana(cur_wansoft, subsidiary_ids, periodo.desde, wansoft.PENDIENTE_REBAJA)
    else:
        pendientes = {}
        for primero, ultimo in _meses(periodo.desde, periodo.hasta):
            for sid, v in wansoft.costo_total_mes(cur_wansoft, subsidiary_ids, primero, ultimo,
                                                  wansoft.PENDIENTE_REBAJA).items():
                pendientes[sid] = pendientes.get(sid, CERO) + v
    return {sid: v for sid, v in pendientes.items() if v > 0}


# Odoo's cost of a day comes from that day's customer invoices (the Wansoft
# sales passed to Odoo), created with a lag: in September 2026, 40-70% one day
# later, 70-100% after 7 days, all of it at the month-end close. A period is
# fully invoiced at this share of its net sales (owner, 2026-10-05: not 100%
# exactly; Puebla 28-Sep stayed at 89% for a week).
UMBRAL_FACTURADO_COMPLETO = Decimal("0.995")


@dataclass(frozen=True)
class CostoOdoo:
    costo: Decimal | None  # total cost of the period to show (None: cannot be told)
    estimado: bool
    venta: Decimal  # Wansoft net sales of the Odoo-cost days
    facturado: Decimal  # invoiced in Odoo for those days


def estimar_costo_odoo(costo_periodo: Decimal | None, dias_odoo: list[date], costo_dia: dict[date, Decimal],
                       facturado_dia: dict[date, Decimal], venta_dia: dict[date, Decimal]) -> CostoOdoo:
    """Business rule "B2" (owner, 2026-10-05). While Odoo has not invoiced the
    Odoo-cost days of the period, their cost is estimated as (Odoo cost /
    Odoo invoiced) x Wansoft net sales of those days -- the cost per invoiced
    peso is stable (35-38% in September) while the invoiced share is not. The
    Wansoft-cost days of the period keep their real cost. Fully invoiced: the
    real cost, unchanged."""
    venta = sum((venta_dia.get(x, CERO) for x in dias_odoo), CERO)
    facturado = sum((facturado_dia.get(x, CERO) for x in dias_odoo), CERO)
    if costo_periodo is None or not venta or facturado >= venta * UMBRAL_FACTURADO_COMPLETO:
        return CostoOdoo(costo_periodo, False, venta, facturado)
    if facturado <= 0:
        return CostoOdoo(None, True, venta, facturado)  # nothing invoiced yet: no basis to estimate
    costo_odoo = sum((costo_dia.get(x, CERO) for x in dias_odoo), CERO)
    estimado = costo_odoo / facturado * venta
    return CostoOdoo(costo_periodo - costo_odoo + estimado, True, venta, facturado)


def recolectar(cur_wansoft, cur_presupuestos, sucursales: list, periodo: Periodo, hoy: date | None = None,
               odoo=None, incluir_costos: bool = True) -> list[Metricas]:
    """Read every metric of `periodo` for each branch (`cuentas.Sucursal`),
    in the same order as `sucursales`. `hoy` (default today) decides whether
    the real Costo de Ventas is still preliminary. `odoo` (a read-only
    client, or None when Odoo cannot be read) gives the invoiced sales behind
    the estimated cost. Without `incluir_costos` no cost is read at all."""
    d, h = periodo.desde, periodo.hasta
    preliminar = presupuestos.es_preliminar(h, hoy or date.today())
    # Branches whose cost is not taken into account (cuentas.Sucursal.considerar_costo) get no cost at all.
    con_costo = [s for s in sucursales if incluir_costos and getattr(s, "considerar_costo", True)]
    cierres = wansoft.cierres_por_dia(
        cur_wansoft, [s.wansoft_subsidiary_id for s in sucursales if s.wansoft_subsidiary_id is not None], d, h)
    nombres = [s.wansoft_ticket_nombre for s in sucursales]
    detalle = wansoft.detalle_por_sucursal(cur_wansoft, nombres, d, h)
    mix = wansoft.mix_alimentos_bebidas(cur_wansoft, [n for n in nombres if n in detalle], d, h)
    costos = (costos_totales(cur_wansoft, [s.wansoft_subsidiary_id for s in con_costo
                                           if s.wansoft_subsidiary_id is not None], periodo) or {}) if con_costo else {}
    pendientes = pendientes_rebaja(cur_wansoft, list(costos), periodo) if costos else {}
    inicios = wansoft.inicio_costos_odoo(cur_wansoft, con_costo) if costos else {}
    inicios = {k: v for k, v in inicios.items() if v <= h}
    costo_dia, facturado = {}, {}
    if inicios and odoo is not None:
        desde_odoo = max(d, min(inicios.values()))
        con_odoo = [s for s in sucursales if s.wansoft_ticket_nombre in inicios]
        costo_dia = wansoft.costo_diario(cur_wansoft, [s.wansoft_subsidiary_id for s in con_odoo], desde_odoo, h)
        facturado = odoo_fuente.facturado_por_dia(odoo, [s.odoo_company_id for s in con_odoo], desde_odoo, h)

    resultado = []
    for sucursal in sucursales:
        m = Metricas(periodo=periodo)
        dias = cierres.get(sucursal.wansoft_subsidiary_id, {})
        for t in dias.values():
            m.venta_bruta += t["venta_bruta"]
            m.venta_neta += t["venta_neta"]
            m.tickets += t["tickets"]
            m.clientes += t["clientes"]
            m.mesas += t["mesas"]
            m.cortesias += t["cortesias"]
            m.cancelaciones += t["cancelaciones"]
            m.anulaciones += t["anulaciones"]
            m.descuentos += t["descuentos"]
        m.venta_por_dia = {dia: t["venta_bruta"] for dia, t in dias.items()}
        m.tickets_por_dia = {dia: t["tickets"] for dia, t in dias.items()}
        m.clientes_por_dia = {dia: t["clientes"] for dia, t in dias.items()}
        m.dias_con_cierre = len(dias)
        if sucursal.wansoft_subsidiary_id in costos:
            m.costo_total = costos[sucursal.wansoft_subsidiary_id]
            m.venta_neta_con_costo_total = m.venta_neta
            pendiente = pendientes.get(sucursal.wansoft_subsidiary_id)
            if pendiente:  # Wansoft has not discounted all of it yet: estimated (owner, 2026-10-05)
                m.costo_total += pendiente
                m.pendiente_wansoft = pendiente
        inicio = inicios.get(sucursal.wansoft_ticket_nombre)
        if inicio is not None and odoo is None:
            m.costo_odoo_sin_leer = True
        elif inicio is not None:
            dias_odoo = [x for x in dias if x >= inicio]
            c = estimar_costo_odoo(m.costo_total, dias_odoo, costo_dia.get(sucursal.wansoft_subsidiary_id, {}),
                                   facturado.get(sucursal.odoo_company_id, {}),
                                   {x: t["venta_neta"] for x, t in dias.items()})
            m.costo_total, m.costo_estimado_odoo = c.costo, c.estimado
            m.venta_dias_odoo, m.facturado_odoo = c.venta, c.facturado
            m.venta_neta_con_costo_total = m.venta_neta if c.costo is not None else None

        nombre = sucursal.wansoft_ticket_nombre
        if nombre in detalle:
            m.dias_con_detalle, m.canal = detalle[nombre]
            m.mix = mix.get(nombre, {})

        if sucursal in con_costo and sucursal.odoo_company_id is not None:
            real = presupuestos.gasto_real_costo_ventas(cur_presupuestos, sucursal.odoo_company_id, d, h)
            ppto = presupuestos.presupuesto_costo_ventas(cur_presupuestos, sucursal.odoo_company_id, d, h)
            m.costo_ventas_real = real
            if real is not None:
                m.venta_neta_con_costo = m.venta_neta
            # only where there is something to show (spend recorded, or a budget awaiting it)
            m.costo_preliminar = preliminar and (real is not None or ppto is not None)
            if ppto is not None:  # a budget is shown even before any real spend is recorded
                m.costo_ventas_ppto, m.n_con_presupuesto = ppto, 1
                if real is not None:
                    m.costo_ventas_real_con_ppto, m.costo_ventas_ppto_con_real = real, ppto
        resultado.append(m)
    return resultado


def recolectar_diario(cur_wansoft, sucursales: list, desde: date, hasta: date) -> dict[str, dict[date, Decimal]]:
    """Gross sales per branch (by name) and operating day from the cash
    closing only (small table: 24 months for every branch is one fast query).
    Used by the month trend chart."""
    ids = [s.wansoft_subsidiary_id for s in sucursales if s.wansoft_subsidiary_id is not None]
    cierres = wansoft.cierres_por_dia(cur_wansoft, ids, desde, hasta)
    return {s.nombre: {d: t["venta_bruta"] for d, t in cierres.get(s.wansoft_subsidiary_id, {}).items()}
            for s in sucursales}


def consolidar(lista: list[Metricas], periodo: Periodo) -> Metricas:
    """Add several branches' metrics into one. Budget figures are summed over
    the branches that have them only (`n_con_presupuesto` says how many)."""
    total = Metricas(periodo=periodo, n_sucursales=len(lista))
    for m in lista:
        for campo in ("venta_bruta", "venta_neta", "tickets", "clientes", "mesas", "cortesias",
                      "cancelaciones", "anulaciones", "descuentos"):
            setattr(total, campo, getattr(total, campo) + getattr(m, campo))
        for k, v in m.canal.items():
            total.canal[k] = total.canal.get(k, CERO) + v
        for k, v in m.mix.items():
            total.mix[k] = total.mix.get(k, CERO) + v
        for campo in ("venta_por_dia", "tickets_por_dia", "clientes_por_dia"):
            suma = getattr(total, campo)
            for dia, v in getattr(m, campo).items():
                suma[dia] = suma.get(dia, CERO) + v
        total.dias_con_cierre += m.dias_con_cierre
        total.dias_con_detalle += m.dias_con_detalle
        if m.costo_ventas_real is not None:
            total.costo_ventas_real = (total.costo_ventas_real or CERO) + m.costo_ventas_real
            total.venta_neta_con_costo = (total.venta_neta_con_costo or CERO) + (m.venta_neta_con_costo or CERO)
        if m.costo_total is not None:
            total.costo_total = (total.costo_total or CERO) + m.costo_total
            total.venta_neta_con_costo_total = (total.venta_neta_con_costo_total or CERO) + (m.venta_neta_con_costo_total or CERO)
        total.costo_estimado_odoo = total.costo_estimado_odoo or m.costo_estimado_odoo
        if m.pendiente_wansoft:
            total.pendiente_wansoft = (total.pendiente_wansoft or CERO) + m.pendiente_wansoft
        total.costo_odoo_sin_leer = total.costo_odoo_sin_leer or m.costo_odoo_sin_leer
        if m.venta_dias_odoo is not None:
            total.venta_dias_odoo = (total.venta_dias_odoo or CERO) + m.venta_dias_odoo
            total.facturado_odoo = (total.facturado_odoo or CERO) + m.facturado_odoo
        if m.costo_ventas_ppto is not None:
            total.costo_ventas_ppto = (total.costo_ventas_ppto or CERO) + m.costo_ventas_ppto
            total.n_con_presupuesto += 1
        if m.costo_ventas_real_con_ppto is not None:
            total.costo_ventas_real_con_ppto = (total.costo_ventas_real_con_ppto or CERO) + m.costo_ventas_real_con_ppto
            total.costo_ventas_ppto_con_real = (total.costo_ventas_ppto_con_real or CERO) + m.costo_ventas_ppto_con_real
        total.costo_preliminar = total.costo_preliminar or m.costo_preliminar
    return total


@dataclass
class Comparacion:
    """One comparison column of a report (previous period or same period last
    year) under the comparable-branches rule: `actual` is the current period
    restricted to the branches being compared, `base` the comparison period
    for those same branches (None when there is nothing to compare), and
    `excluidas` the branches left out."""

    actual: Metricas
    base: Metricas | None
    excluidas: list[str] = field(default_factory=list)


def como_comparacion(actual: Metricas, x: "Comparacion | Metricas | None") -> Comparacion:
    """Accept a plain Metricas (no branch excluded) where a Comparacion is expected."""
    return x if isinstance(x, Comparacion) else Comparacion(actual, x)


def comparables(nombres: list[str], actuales: list[Metricas], bases: list[Metricas] | None,
                periodo: Periodo, periodo_base: Periodo | None) -> Comparacion:
    """Business rule (owner, 2026-09-24): a branch that did not operate the
    comparison period fully (new branch, or no data: cash closings on less
    than UMBRAL_COBERTURA_FIABLE of its days) is left out of BOTH sides of
    that comparison, so new branches never inflate the change. Only values
    that exist are compared; the report lists the branches left out."""
    if bases is None or periodo_base is None:
        return Comparacion(consolidar(actuales, periodo), None)
    dentro = [i for i, b in enumerate(bases) if cobertura_fiable(b.dias_con_cierre, b.dias_esperados)]
    excluidas = [nombres[i] for i in range(len(nombres)) if i not in dentro]
    if not dentro:
        return Comparacion(consolidar(actuales, periodo), None, excluidas)
    return Comparacion(consolidar([actuales[i] for i in dentro], periodo),
                       consolidar([bases[i] for i in dentro], periodo_base), excluidas)


def sin_presupuesto(m: Metricas | None) -> None:
    """Drop the Costo de Ventas budget figures from a metrics object (the
    consolidated report shows no budget unless every branch has one)."""
    if m is None:
        return
    m.costo_ventas_ppto = m.costo_ventas_real_con_ppto = m.costo_ventas_ppto_con_real = None
    m.n_con_presupuesto = 0
