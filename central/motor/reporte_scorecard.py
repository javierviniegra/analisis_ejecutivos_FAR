"""Assembles the "Semáforos scorecard" for a branch selection (read-only).

The definition (KPIs, targets, lights, periods) lives in `scorecard.py`; this
module reads the sources for the three periods and hands them to it.
"""

from dataclasses import dataclass, field
from datetime import date

from . import scorecard as sc
from .fuentes import wansoft
from .periodo import Periodo


def leer_ventas(cur_wansoft, sucursales: list, periodo: Periodo) -> list[sc.Ventas]:
    """Sales of each branch (`cuentas.Sucursal`, same order) in `periodo`."""
    nombres = [s.wansoft_ticket_nombre for s in sucursales]
    tickets = wansoft.ventas_tickets(cur_wansoft, nombres, periodo.desde, periodo.hasta)
    mix = wansoft.mix_alimentos_bebidas(cur_wansoft, [n for n in nombres if n in tickets], periodo.desde, periodo.hasta)
    resultado = []
    for nombre in nombres:
        t, m = tickets.get(nombre), mix.get(nombre, {})
        v = sc.Ventas(dias_esperados=periodo.dias)
        if t:
            v.dias, v.venta, v.tickets, v.venta_neta = t["dias"], t["venta"], t["tickets"], t["venta_neta"]
            v.personas, v.personas_restaurante = t["personas"], t["personas_restaurante"]
            v.alimentos, v.bebidas = m.get("Alimentos", sc.CERO), m.get("Bebidas", sc.CERO)
        resultado.append(v)
    return resultado


def leer_gastos(cur_wansoft, sucursales: list, periodo: Periodo, inicio_odoo: dict[str, date],
                dobles: list | None = None) -> list[sc.Gastos]:
    """Invoiced cost and expenses of each branch (same order) in `periodo`.
    Bread and tortillas: `scorecard.pan_tortillas` (Wansoft entries every day
    plus Odoo purchases from the day the branch buys in Odoo, `inicio_odoo` by
    short key); each (branch, department, day) present in both sources is
    appended to `dobles`."""
    d, h = periodo.desde, periodo.hasta
    claves = [s.wansoft_ticket_nombre for s in sucursales]
    facturas = wansoft.facturas_gasto(cur_wansoft, claves, d, h)
    entradas = wansoft.entradas_factura_por_dia(
        cur_wansoft, [s.wansoft_subsidiary_id for s in sucursales if s.wansoft_subsidiary_id is not None], d, h)
    con_odoo = [c for c in claves if c in inicio_odoo and inicio_odoo[c] <= h]
    compras = wansoft.compras_odoo_pan_tortillas_por_dia(cur_wansoft, con_odoo, d, h)
    resultado = []
    for s in sucursales:
        montos, ambas = sc.pan_tortillas(entradas.get(s.wansoft_subsidiary_id, {}),
                                         compras.get(s.wansoft_ticket_nombre, {}),
                                         inicio_odoo.get(s.wansoft_ticket_nombre))
        if dobles is not None:
            dobles.extend((s.nombre, depto, dia) for depto, dia in ambas)
        resultado.append(sc.gastos_de(facturas.get(s.wansoft_ticket_nombre, {}), montos))
    return resultado


def bloque_ventas(cur_wansoft, sucursales: list, hasta: date) -> tuple[sc.PeriodosScorecard, sc.BloqueVentas]:
    """The sales rows of the report ending `hasta`, for all of `sucursales`
    together (one branch = that branch's report)."""
    p = sc.periodos(hasta)
    leidos = [leer_ventas(cur_wansoft, sucursales, x) for x in (p.actual, p.mes_anterior, p.anio_anterior)]
    return p, sc.filas_ventas([s.nombre for s in sucursales], *leidos)


@dataclass
class ReporteScorecard:
    nombre: str  # branch name, or "Consolidado"
    sucursales: list
    periodos: sc.PeriodosScorecard
    filas: list[sc.Fila]  # every KPI, in the catalog's order
    meta_mes_anterior: list[str]
    sin_meta: list[str]
    sin_costo: list[str] = field(default_factory=list)
    sin_meta_gastos: list[str] = field(default_factory=list)
    pan_dobles: list = field(default_factory=list)  # (branch, department, day) in Wansoft AND Odoo, current period
    pan_parcial: list[str] = field(default_factory=list)  # branches whose Odoo bread/tortillas are partly unmapped
    desglose: list = field(default_factory=list)  # scorecard.Desglose of every cost and expense row


def armar(cur_wansoft, sucursales: list, hasta: date, consolidado: bool = False) -> ReporteScorecard:
    """The whole scorecard (every KPI row; those without a source carry no value)."""
    p = sc.periodos(hasta)
    nombres = [s.nombre for s in sucursales]
    ventas = [leer_ventas(cur_wansoft, sucursales, x) for x in (p.actual, p.mes_anterior, p.anio_anterior)]
    inicio_odoo = wansoft.inicio_compras_odoo(cur_wansoft)
    dobles = []
    gastos = [leer_gastos(cur_wansoft, sucursales, p.actual, inicio_odoo, dobles),
              leer_gastos(cur_wansoft, sucursales, p.mes_anterior, inicio_odoo)]
    bv = sc.filas_ventas(nombres, *ventas)
    bg = sc.filas_gastos(nombres, ventas[0], ventas[1], gastos[0], gastos[1])
    leidas = {f.kpi.clave: f for f in bv.filas + bg.filas}
    filas = [leidas.get(k.clave) or sc.Fila(k, None, None, k.meta, None, None) for k in sc.KPIS]
    nombre = "Consolidado" if consolidado else sucursales[0].nombre
    parcial = [s.nombre for s in sucursales if s.wansoft_ticket_nombre in sc.PAN_TORTILLAS_PARCIAL]
    return ReporteScorecard(nombre, sucursales, p, filas, bv.meta_mes_anterior, bv.sin_meta, bg.sin_costo, bg.sin_meta,
                            dobles, parcial, sc.desglose(bg.detalle, bg.proveedores))
