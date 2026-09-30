"""Detail tables of the commercial report's second page (pure: no I/O).

Owner, 2026-09-30: the report takes two pages so it reads better; the second
page carries more information, not only the rules:
- consolidated report: one row per branch (sales, change vs its previous
  period, guests, average check, invoiced cost share with its traffic light),
  largest sales first, plus a total row;
- single branch: one row per day (per 7-day block or month on longer periods,
  the same buckets as the charts) with sales, tickets, guests, average check
  and the previous period's sales at the same position -- except in a month:
  pairing two months day by day mixes in the day-of-week effect (the reason
  the month charts measure calendar months), so a month's days carry their
  weekday and no previous-period column.
"""

from dataclasses import dataclass
from decimal import Decimal

from .comparativos import Variacion, cobertura_fiable, semaforo_costo, variacion
from .graficas import _DIAS_ES, DIA, cubetas, etiqueta, granularidad  # noqa: F401 (granularidad re-exported)
from .periodo import TipoPeriodo
from .metricas import Metricas
from .reporte_comercial import ReporteComercial

CERO = Decimal("0")


def _razon(a, b) -> Decimal | None:
    return Decimal(a) / Decimal(b) if a is not None and b else None


@dataclass(frozen=True)
class FilaSucursal:
    nombre: str
    venta_bruta: Decimal
    var_anterior: Variacion
    clientes: Decimal
    cheque_promedio: Decimal | None
    pct_costo: Decimal | None
    semaforo: str | None


@dataclass(frozen=True)
class FilaPeriodo:
    etiqueta: str
    venta_bruta: Decimal | None
    tickets: Decimal | None
    clientes: Decimal | None
    cheque_promedio: Decimal | None
    venta_anterior: Decimal | None
    var_anterior: Variacion


def _fila_sucursal(nombre: str, m: Metricas, var: Variacion) -> FilaSucursal:
    return FilaSucursal(nombre, m.venta_bruta, var, m.clientes, m.cheque_promedio,
                        m.pct_costo_ventas, semaforo_costo(m.pct_costo_ventas))


def _var_sucursal(m: Metricas, previo: Metricas | None) -> Variacion:
    """Same comparable rule as the table: a branch without full data in the
    previous period (new, or no data) has no comparison."""
    fiable = previo is not None and cobertura_fiable(previo.dias_con_cierre, previo.dias_esperados)
    return variacion(m.venta_bruta, previo.venta_bruta if fiable else None)


def por_sucursal(r: ReporteComercial) -> tuple[list[FilaSucursal], FilaSucursal]:
    """Rows per branch (largest sales first) and the total row, whose change
    is the table's own (comparable branches)."""
    filas = [_fila_sucursal(n, m, _var_sucursal(m, p)) for n, m, p in r.por_sucursal]
    filas.sort(key=lambda f: f.venta_bruta, reverse=True)
    venta = next(f for f in r.filas if f.indicador.clave == "venta_bruta")
    return filas, _fila_sucursal("Total", r.actual, venta.var_anterior)


def _suma(por_dia: dict, inicio, fin) -> Decimal | None:
    valores = [v for d, v in por_dia.items() if inicio <= d <= fin]
    return sum(valores, CERO) if valores else None


def compara_con_anterior(r: ReporteComercial) -> bool:
    return r.periodo.tipo != TipoPeriodo.MES and r.anterior.base is not None


def por_periodo(r: ReporteComercial) -> list[FilaPeriodo]:
    """Rows per day / 7-day block / month of the period, with the previous
    period's sales at the same position (comparable branches only; not in a
    month, see the module docstring)."""
    p, m = r.periodo, r.actual
    gran = granularidad(p)
    rangos = cubetas(p, gran)
    rangos_base = cubetas(p.anterior(), gran) if compara_con_anterior(r) else []
    filas = []
    for i, (inicio, fin) in enumerate(rangos):
        venta = _suma(m.venta_por_dia, inicio, fin)
        clientes = _suma(m.clientes_por_dia, inicio, fin)
        anterior = _suma(r.anterior.base.venta_por_dia, *rangos_base[i]) if i < len(rangos_base) else None
        texto = (f"{_DIAS_ES[inicio.weekday()]} {inicio.day}" if gran == DIA
                 else etiqueta(inicio, gran, p.dias, p.desde.year != p.hasta.year))
        filas.append(FilaPeriodo(
            etiqueta=texto, venta_bruta=venta, tickets=_suma(m.tickets_por_dia, inicio, fin), clientes=clientes,
            cheque_promedio=_razon(venta, clientes), venta_anterior=anterior, var_anterior=variacion(venta, anterior)))
    return filas
