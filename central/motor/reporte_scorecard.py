"""Assembles the "Semáforos scorecard" for a branch selection (read-only).

The definition (KPIs, targets, lights, periods) lives in `scorecard.py`; this
module reads the sources for the three periods and hands them to it.
"""

from dataclasses import dataclass
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
            v.dias, v.venta, v.tickets = t["dias"], t["venta"], t["tickets"]
            v.personas, v.personas_restaurante = t["personas"], t["personas_restaurante"]
            v.alimentos, v.bebidas = m.get("Alimentos", sc.CERO), m.get("Bebidas", sc.CERO)
        resultado.append(v)
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


def armar(cur_wansoft, sucursales: list, hasta: date, consolidado: bool = False) -> ReporteScorecard:
    """The whole scorecard (every KPI row; those not read yet carry no value)."""
    p, ventas = bloque_ventas(cur_wansoft, sucursales, hasta)
    leidas = {f.kpi.clave: f for f in ventas.filas}
    filas = [leidas.get(k.clave) or sc.Fila(k, None, None, k.meta, None, None) for k in sc.KPIS]
    nombre = "Consolidado" if consolidado else sucursales[0].nombre
    return ReporteScorecard(nombre, sucursales, p, filas, ventas.meta_mes_anterior, ventas.sin_meta)
