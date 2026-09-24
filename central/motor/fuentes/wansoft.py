"""Weekly queries against the Wansoft warehouse (read-only).

Every function takes an open cursor (see conexiones.abrir_wansoft) so the
caller controls the connection and can run several queries on one.

Business rules baked in here (found by validating against real data):

- **Operating day of a cash closing.** `getglobalcashclosing.fecha_corte` is
  when the closing was done, not the day it belongs to. A closing before
  14:00 belongs to the PREVIOUS operating day (00:xx closings after a night
  shift, and late morning-after closings). Validated against the ticket
  detail: with this rule 30/30 days of a full month match to the cent.
- **Duplicate closings.** The same closing can be stored more than once (a
  re-issued closing: same operating day, identical totals -- e.g. three
  identical rows 13 seconds apart, or the previous night's closing repeated
  the next noon). Only one row per identical (day, totals) is counted.
- **Ticket detail is not always complete** (branches added late, or none at
  all). Functions that read it also return how many days of the range have
  data so the report can flag partial coverage instead of pretending.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

HORA_CORTE_DIA = 14  # closings before this hour belong to the previous operating day

CANALES = {"Restaurant": "salon", "Para llevar": "llevar", "eCommerce": "plataformas"}
CANAL_OTROS = "otros"


def dia_operativo(fecha_corte: datetime) -> date:
    """Operating day a cash closing belongs to (see module docstring)."""
    return (fecha_corte - timedelta(hours=HORA_CORTE_DIA)).date()


def _limites_cierre(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """[start, end) of `fecha_corte` values whose operating day is in the range."""
    inicio = datetime.combine(desde, time(HORA_CORTE_DIA))
    fin = datetime.combine(hasta + timedelta(days=1), time(HORA_CORTE_DIA))
    return inicio, fin


def cierres_por_dia(cur, subsidiary_id: int, desde: date, hasta: date) -> dict[date, dict]:
    """Daily totals from the cash closing, per operating day, deduplicated.

    Amounts are as recorded by the POS: `venta_bruta` includes IVA,
    `venta_neta` does not; cortesias / cancelaciones / anulaciones /
    descuentos are valued at sale price (not ingredient cost).
    """
    inicio, fin = _limites_cierre(desde, hasta)
    cur.execute(
        """
        SELECT dia,
               SUM(total_ventas), SUM(subtotal), SUM(no_ordenes), SUM(total_personas), SUM(total_mesas_atendidas),
               SUM(cortesias_en_cuentas + cortesias_en_platillos),
               SUM(cancelaciones_en_cuentas + cancelaciones_en_platillos),
               SUM(anulaciones_en_cuentas + anulaciones_en_platillos),
               SUM(descuentos_en_cuentas + descuentos_en_platillos)
        FROM (
            SELECT g.*, DATE(fecha_corte - INTERVAL %s HOUR) AS dia,
                   ROW_NUMBER() OVER (
                       PARTITION BY DATE(fecha_corte - INTERVAL %s HOUR),
                                    total_ventas, subtotal, no_ordenes, total_personas
                       ORDER BY fecha_corte, id) AS rn
            FROM getglobalcashclosing g
            WHERE subsidiary_id = %s AND fecha_corte >= %s AND fecha_corte < %s
        ) x
        WHERE rn = 1
        GROUP BY dia
        """,
        (HORA_CORTE_DIA, HORA_CORTE_DIA, subsidiary_id, inicio, fin),
    )
    claves = ("venta_bruta", "venta_neta", "tickets", "clientes", "mesas", "cortesias", "cancelaciones", "anulaciones", "descuentos")
    return {fila[0]: dict(zip(claves, (Decimal(v or 0) for v in fila[1:]))) for fila in cur.fetchall()}


def _rango_fecha_texto(desde: date, hasta: date) -> tuple[str, str]:
    """Order detail stores `Fecha` as ISO text ('2026-09-21T00:00:00'); text
    comparison against [desde, hasta+1) is correct for that format."""
    return desde.isoformat(), (hasta + timedelta(days=1)).isoformat()


def dias_con_detalle(cur, ticket_nombre: str, desde: date, hasta: date) -> int:
    """How many distinct days of the range have order detail for the branch."""
    if not ticket_nombre:
        return 0
    a, b = _rango_fecha_texto(desde, hasta)
    cur.execute(
        "SELECT COUNT(DISTINCT LEFT(Fecha, 10)) FROM getallordenesbyday_new_venta "
        "WHERE Sucursal = %s AND Fecha >= %s AND Fecha < %s",
        (ticket_nombre, a, b),
    )
    return int(cur.fetchone()[0] or 0)


def venta_por_canal(cur, ticket_nombre: str, desde: date, hasta: date) -> dict[str, Decimal]:
    """Gross sales by channel (salon / llevar / plataformas / otros) from the
    order type of each ticket. Empty dict when the branch has no detail."""
    if not ticket_nombre:
        return {}
    a, b = _rango_fecha_texto(desde, hasta)
    cur.execute(
        "SELECT TipoOrden, SUM(CAST(Total AS DECIMAL(14,2))) FROM getallordenesbyday_new_venta "
        "WHERE Sucursal = %s AND Fecha >= %s AND Fecha < %s GROUP BY TipoOrden",
        (ticket_nombre, a, b),
    )
    canales: dict[str, Decimal] = {}
    for tipo, total in cur.fetchall():
        canal = CANALES.get(tipo, CANAL_OTROS)
        canales[canal] = canales.get(canal, Decimal("0")) + Decimal(total or 0)
    return canales


def mix_alimentos_bebidas(cur, ticket_nombre: str, desde: date, hasta: date) -> dict[str, Decimal]:
    """Gross sales of Alimentos and Bebidas from the order lines. Empty dict
    when the branch has no detail."""
    if not ticket_nombre:
        return {}
    a, b = _rango_fecha_texto(desde, hasta)
    cur.execute(
        """
        SELECT d.TipoGrupo, SUM(CAST(d.Total AS DECIMAL(14,2)))
        FROM getallordenesbyday_new_venta v
        JOIN getallordenesbyday_new_detalleventa d
          ON d.Movimiento_Id = v.Movimento AND d.Sucursal = v.Sucursal
        WHERE v.Sucursal = %s AND v.Fecha >= %s AND v.Fecha < %s
        GROUP BY d.TipoGrupo
        """,
        (ticket_nombre, a, b),
    )
    return {grupo: Decimal(total or 0) for grupo, total in cur.fetchall() if grupo in ("Alimentos", "Bebidas")}
