"""Queries against the Wansoft warehouse (read-only), for any period.

Every function takes an open cursor (see conexiones.abrir_wansoft) so the
caller controls the connection and can run several queries on one.

**Batched by branch:** each function reads ALL requested branches of one
period in a single query (`IN (...)`, grouped by branch). The ticket table
(`getallordenesbyday_new_venta`, 1.2 M rows in production) has no index on
(Sucursal, Fecha), so every query scans it fully; one scan per period for
all branches instead of one per branch took 19 branches x 3 periods from
~6 min 40 s down (see docs/DECISIONS.md).

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

# Every table/column the queries below read; `manage.py verificar_fuentes`
# checks them against the live schema (keep in sync when a query changes).
COLUMNAS_REQUERIDAS = {
    "getglobalcashclosing": [
        "id", "subsidiary_id", "fecha_corte", "total_ventas", "subtotal", "no_ordenes", "total_personas",
        "total_mesas_atendidas", "cortesias_en_cuentas", "cortesias_en_platillos", "cancelaciones_en_cuentas",
        "cancelaciones_en_platillos", "anulaciones_en_cuentas", "anulaciones_en_platillos",
        "descuentos_en_cuentas", "descuentos_en_platillos",
    ],
    "getallordenesbyday_new_venta": ["Sucursal", "Fecha", "TipoOrden", "Total", "Movimento"],
    "getallordenesbyday_new_detalleventa": ["Movimiento_Id", "Sucursal", "TipoGrupo", "Total"],
    "costeomensual": ["id", "subsidiary_id", "created_at", "CostoTotal", "CostoDeConsumo"],
    "costeomensual_semanapyq": ["id", "subsidiary_id", "created_at", "CostoTotal", "CostoDeConsumo"],
}


def dia_operativo(fecha_corte: datetime) -> date:
    """Operating day a cash closing belongs to (see module docstring)."""
    return (fecha_corte - timedelta(hours=HORA_CORTE_DIA)).date()


def _limites_cierre(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """[start, end) of `fecha_corte` values whose operating day is in the range."""
    inicio = datetime.combine(desde, time(HORA_CORTE_DIA))
    fin = datetime.combine(hasta + timedelta(days=1), time(HORA_CORTE_DIA))
    return inicio, fin


def _marcadores(valores) -> str:
    return ", ".join(["%s"] * len(valores))


def cierres_por_dia(cur, subsidiary_ids: list[int], desde: date, hasta: date) -> dict[int, dict[date, dict]]:
    """Daily totals from the cash closing, per branch and operating day,
    deduplicated: {subsidiary_id: {day: totals}}.

    Amounts are as recorded by the POS: `venta_bruta` includes IVA,
    `venta_neta` does not; cortesias / cancelaciones / anulaciones /
    descuentos are valued at sale price (not ingredient cost).
    """
    if not subsidiary_ids:
        return {}
    inicio, fin = _limites_cierre(desde, hasta)
    cur.execute(
        f"""
        SELECT subsidiary_id, dia,
               SUM(total_ventas), SUM(subtotal), SUM(no_ordenes), SUM(total_personas), SUM(total_mesas_atendidas),
               SUM(cortesias_en_cuentas + cortesias_en_platillos),
               SUM(cancelaciones_en_cuentas + cancelaciones_en_platillos),
               SUM(anulaciones_en_cuentas + anulaciones_en_platillos),
               SUM(descuentos_en_cuentas + descuentos_en_platillos)
        FROM (
            SELECT g.*, DATE(fecha_corte - INTERVAL %s HOUR) AS dia,
                   ROW_NUMBER() OVER (
                       PARTITION BY subsidiary_id, DATE(fecha_corte - INTERVAL %s HOUR),
                                    total_ventas, subtotal, no_ordenes, total_personas
                       ORDER BY fecha_corte, id) AS rn
            FROM getglobalcashclosing g
            WHERE subsidiary_id IN ({_marcadores(subsidiary_ids)}) AND fecha_corte >= %s AND fecha_corte < %s
        ) x
        WHERE rn = 1
        GROUP BY subsidiary_id, dia
        """,
        (HORA_CORTE_DIA, HORA_CORTE_DIA, *subsidiary_ids, inicio, fin),
    )
    claves = ("venta_bruta", "venta_neta", "tickets", "clientes", "mesas", "cortesias", "cancelaciones", "anulaciones", "descuentos")
    resultado: dict[int, dict[date, dict]] = {}
    for fila in cur.fetchall():
        resultado.setdefault(fila[0], {})[fila[1]] = dict(zip(claves, (Decimal(v or 0) for v in fila[2:])))
    return resultado


def _rango_fecha_texto(desde: date, hasta: date) -> tuple[str, str]:
    """Order detail stores `Fecha` as ISO text ('2026-09-21T00:00:00'); text
    comparison against [desde, hasta+1) is correct for that format."""
    return desde.isoformat(), (hasta + timedelta(days=1)).isoformat()


def detalle_por_sucursal(cur, nombres: list[str], desde: date, hasta: date) -> dict[str, tuple[int, dict[str, Decimal]]]:
    """From the ticket detail, per branch (ticket-table name): how many
    distinct days of the range have data, and gross sales by channel
    (salon / llevar / plataformas / otros, from the order type). One scan for
    both. Branches with no detail are absent from the result."""
    nombres = [n for n in nombres if n]
    if not nombres:
        return {}
    a, b = _rango_fecha_texto(desde, hasta)
    cur.execute(
        f"SELECT Sucursal, LEFT(Fecha, 10), TipoOrden, SUM(CAST(Total AS DECIMAL(14,2))) "
        f"FROM getallordenesbyday_new_venta "
        f"WHERE Sucursal IN ({_marcadores(nombres)}) AND Fecha >= %s AND Fecha < %s "
        f"GROUP BY Sucursal, LEFT(Fecha, 10), TipoOrden",
        (*nombres, a, b),
    )
    dias: dict[str, set] = {}
    canales: dict[str, dict[str, Decimal]] = {}
    for sucursal, dia, tipo, total in cur.fetchall():
        dias.setdefault(sucursal, set()).add(dia)
        canal = CANALES.get(tipo, CANAL_OTROS)
        por_canal = canales.setdefault(sucursal, {})
        por_canal[canal] = por_canal.get(canal, Decimal("0")) + Decimal(total or 0)
    return {s: (len(dias[s]), canales[s]) for s in dias}


def _tramos_mensuales(desde: date, hasta: date) -> list[tuple[date, date]]:
    """[desde, hasta] cut at calendar-month boundaries."""
    tramos, inicio = [], desde
    while inicio <= hasta:
        fin = min((inicio.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), hasta)
        tramos.append((inicio, fin))
        inicio = fin + timedelta(days=1)
    return tramos


def mix_alimentos_bebidas(cur, nombres: list[str], desde: date, hasta: date) -> dict[str, dict[str, Decimal]]:
    """Gross sales of Alimentos and Bebidas from the order lines, per branch
    (ticket-table name). Branches with no detail are absent.

    Run one statement per calendar month and add them up: the join to the
    12 M-row order-line table costs 4-19 s per month for all branches in
    production, while a whole semester in one statement exceeded the 120 s
    cap (conexiones.LIMITE_SEGUNDOS_CONSULTA)."""
    nombres = [n for n in nombres if n]
    if not nombres:
        return {}
    resultado: dict[str, dict[str, Decimal]] = {}
    for inicio, fin in _tramos_mensuales(desde, hasta):
        a, b = _rango_fecha_texto(inicio, fin)
        cur.execute(
            f"""
            SELECT v.Sucursal, d.TipoGrupo, SUM(CAST(d.Total AS DECIMAL(14,2)))
            FROM getallordenesbyday_new_venta v
            JOIN getallordenesbyday_new_detalleventa d
              ON d.Movimiento_Id = v.Movimento AND d.Sucursal = v.Sucursal
            WHERE v.Sucursal IN ({_marcadores(nombres)}) AND v.Fecha >= %s AND v.Fecha < %s
            GROUP BY v.Sucursal, d.TipoGrupo
            """,
            (*nombres, a, b),
        )
        for sucursal, grupo, total in cur.fetchall():
            if grupo in ("Alimentos", "Bebidas"):
                por_grupo = resultado.setdefault(sucursal, {})
                por_grupo[grupo] = por_grupo.get(grupo, Decimal("0")) + Decimal(total or 0)
    return resultado


def _costo_ultima_foto(cur, tabla: str, subsidiary_ids: list[int], desde: date, hasta: date) -> dict[int, Decimal]:
    """Cost of the latest snapshot per branch with capture date in [desde, hasta]:
    `CostoTotal - COALESCE(CostoDeConsumo, 0)` (the data guide's "Costo Total";
    COALESCE because Odoo rows leave consumption NULL). The capture date is
    read from `created_at` (present before and after the 2026-10-01
    migration, which adds `created_date` = its date); the latest capture wins."""
    marcas = ", ".join(["%s"] * len(subsidiary_ids))
    cur.execute(
        f"""
        SELECT subsidiary_id, CostoTotal - COALESCE(CostoDeConsumo, 0)
        FROM (
            SELECT t.*, ROW_NUMBER() OVER (PARTITION BY subsidiary_id ORDER BY created_at DESC, id DESC) AS rn
            FROM {tabla} t
            WHERE subsidiary_id IN ({marcas}) AND created_at >= %s AND created_at < %s
        ) x
        WHERE rn = 1
        """,
        (*subsidiary_ids, datetime.combine(desde, time.min), datetime.combine(hasta + timedelta(days=1), time.min)),
    )
    return {s: Decimal(v) for s, v in cur.fetchall() if v is not None}


def costo_total_semana(cur, subsidiary_ids: list[int], lunes: date) -> dict[int, Decimal]:
    """Monday-Sunday week from `costeomensual_semanapyq`. A row accumulates from
    Monday through the day BEFORE its capture date, so the complete week is the
    row captured the next Monday (checked: Isabel 21-Sep row = sum of daily
    cost 14-20 Sep); for a week in progress, the latest row so far."""
    if not subsidiary_ids:
        return {}
    return _costo_ultima_foto(cur, "costeomensual_semanapyq", subsidiary_ids,
                              lunes + timedelta(days=1), lunes + timedelta(days=7))


def costo_total_mes(cur, subsidiary_ids: list[int], primero: date, ultimo: date) -> dict[int, Decimal]:
    """Calendar month from `costeomensual` (month-to-date from the 1st through the
    capture date): the latest row of the month."""
    if not subsidiary_ids:
        return {}
    return _costo_ultima_foto(cur, "costeomensual", subsidiary_ids, primero, ultimo)
