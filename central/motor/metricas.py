"""Metrics of a period for one branch or several (consolidated).

`recolectar` reads the sources (read-only) for several branches and ONE
period, one batched query per source table; `consolidar` adds several
branches together. Everything else here is pure.

Coverage is tracked explicitly (days with cash closing / with ticket detail
out of the days expected) so reports can flag partial data instead of
presenting a partial sum as if it were complete.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .comparativos import cobertura_fiable
from .fuentes import presupuestos, wansoft
from .periodo import Periodo

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
    venta_por_dia: dict[date, Decimal] = field(default_factory=dict)  # net sales (sin IVA) per operating day
    dias_con_cierre: int = 0  # summed over branches
    dias_con_detalle: int = 0  # summed over branches
    costo_ventas_real: Decimal | None = None  # None = not available (never zero)
    costo_ventas_ppto: Decimal | None = None
    # Real spend only of the branches that also have a budget: the base for
    # "% ejercido", so the ratio never mixes branches with and without budget.
    costo_ventas_real_con_ppto: Decimal | None = None
    n_con_presupuesto: int = 0

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
        return _razon(self.costo_ventas_real_con_ppto, self.costo_ventas_ppto)


def recolectar(cur_wansoft, cur_presupuestos, sucursales: list, periodo: Periodo) -> list[Metricas]:
    """Read every metric of `periodo` for each branch (`cuentas.Sucursal`),
    in the same order as `sucursales`."""
    d, h = periodo.desde, periodo.hasta
    cierres = wansoft.cierres_por_dia(
        cur_wansoft, [s.wansoft_subsidiary_id for s in sucursales if s.wansoft_subsidiary_id is not None], d, h)
    nombres = [s.wansoft_ticket_nombre for s in sucursales]
    detalle = wansoft.detalle_por_sucursal(cur_wansoft, nombres, d, h)
    mix = wansoft.mix_alimentos_bebidas(cur_wansoft, [n for n in nombres if n in detalle], d, h)

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
        m.venta_por_dia = {dia: t["venta_neta"] for dia, t in dias.items()}
        m.dias_con_cierre = len(dias)

        nombre = sucursal.wansoft_ticket_nombre
        if nombre in detalle:
            m.dias_con_detalle, m.canal = detalle[nombre]
            m.mix = mix.get(nombre, {})

        if sucursal.odoo_company_id is not None:
            real = presupuestos.gasto_real_costo_ventas(cur_presupuestos, sucursal.odoo_company_id, d, h)
            ppto = presupuestos.presupuesto_costo_ventas(cur_presupuestos, sucursal.odoo_company_id, d, h)
            m.costo_ventas_real = real
            if real is not None and ppto is not None:
                m.costo_ventas_ppto, m.costo_ventas_real_con_ppto, m.n_con_presupuesto = ppto, real, 1
        resultado.append(m)
    return resultado


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
        for dia, v in m.venta_por_dia.items():
            total.venta_por_dia[dia] = total.venta_por_dia.get(dia, CERO) + v
        total.dias_con_cierre += m.dias_con_cierre
        total.dias_con_detalle += m.dias_con_detalle
        if m.costo_ventas_real is not None:
            total.costo_ventas_real = (total.costo_ventas_real or CERO) + m.costo_ventas_real
        if m.costo_ventas_ppto is not None:
            total.costo_ventas_ppto = (total.costo_ventas_ppto or CERO) + m.costo_ventas_ppto
            total.costo_ventas_real_con_ppto = (total.costo_ventas_real_con_ppto or CERO) + (m.costo_ventas_real_con_ppto or CERO)
            total.n_con_presupuesto += 1
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
