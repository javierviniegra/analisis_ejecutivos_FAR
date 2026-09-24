"""Costo de Ventas budget vs real spend, read from ControlPresupuestos_AP (read-only).

Reproduces that app's own logic so numbers agree with its dashboard:

- Budgets are captured monthly per branch and expense type. A row with NO
  expense type means "everything else": its amount is spread evenly across
  the expense types that have no explicit row that month, plus one extra
  share for the "sin clasificar" bucket when the branch has unclassified
  real spend that month (`_resolver_presupuestos_mensuales` in that app).
- A monthly budget is measured weekly by prorating it by days (a week
  spanning two months blends both months' daily rates).
- Real spend is `GastoReal.monto` keyed by `semana` (the Monday of the week
  it counts toward: goods-receipt week for PO-linked lines, payment week
  otherwise).

This module only covers the category "Costo de Ventas". Branches that are
not active in ControlPresupuestos_AP (only the Odoo-migrated ones are) have
no budget: functions return None, never zero.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from ..periodos import prorratear_mensual

CATEGORIA = "Costo de Ventas"


def _centavos(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def resolver_costo_ventas_mensual(
    por_tipo: dict[int | None, Decimal],
    categoria_de_tipo: dict[int, str],
    hay_sin_clasificar: bool,
    categoria: str = CATEGORIA,
) -> Decimal:
    """Monthly budget of `categoria` for one branch and month.

    `por_tipo` maps expense type id (None = "everything else" row) -> summed
    amount; `categoria_de_tipo` maps every expense type id -> its category
    name; `hay_sin_clasificar` is True when the branch has real spend without
    an expense type that month (it takes a share of the leftover).
    """
    explicitos = {t: m for t, m in por_tipo.items() if t is not None}
    total = sum((m for t, m in explicitos.items() if categoria_de_tipo.get(t) == categoria), Decimal("0"))
    sobrante = por_tipo.get(None)
    if sobrante:
        sin_explicito = [t for t in categoria_de_tipo if t not in explicitos]
        repartos = len(sin_explicito) + (1 if hay_sin_clasificar else 0)
        if repartos:
            parte = _centavos(Decimal(sobrante) / repartos)
            total += parte * sum(1 for t in sin_explicito if categoria_de_tipo[t] == categoria)
    return total


def _sucursal_id(cur, odoo_company_id: int) -> int | None:
    cur.execute(
        "SELECT id FROM presupuestos_sucursal WHERE odoo_company_id = %s AND activa = 1",
        (odoo_company_id,),
    )
    fila = cur.fetchone()
    return fila[0] if fila else None


def _meses(desde: date, hasta: date) -> list[date]:
    meses, d = [], desde.replace(day=1)
    while d <= hasta:
        meses.append(d)
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return meses


def presupuesto_costo_ventas(cur, odoo_company_id: int, desde: date, hasta: date) -> Decimal | None:
    """Costo de Ventas budget for [desde, hasta] (prorated by days), or None
    when the branch is not active there or any month of the range has no
    budget captured (a missing budget is not a zero target)."""
    sucursal = _sucursal_id(cur, odoo_company_id)
    if sucursal is None:
        return None
    meses = _meses(desde, hasta)

    cur.execute("SELECT t.id, c.nombre FROM presupuestos_tipogasto t JOIN presupuestos_categoria c ON c.id = t.categoria_id")
    categoria_de_tipo = {tid: nombre for tid, nombre in cur.fetchall()}

    mensual: dict[tuple[int, int], Decimal] = {}
    for mes in meses:
        cur.execute(
            "SELECT tipo_gasto_id, SUM(monto) FROM presupuestos_presupuesto "
            "WHERE sucursal_id = %s AND mes = %s GROUP BY tipo_gasto_id",
            (sucursal, mes),
        )
        por_tipo = {tid: Decimal(m) for tid, m in cur.fetchall()}
        if not por_tipo:
            return None
        cur.execute(
            "SELECT 1 FROM presupuestos_gastoreal WHERE sucursal_id = %s AND tipo_gasto_id IS NULL "
            "AND fecha_pago >= %s AND fecha_pago < %s LIMIT 1",
            (sucursal, mes, (mes.replace(day=28) + timedelta(days=4)).replace(day=1)),
        )
        hay_sin_clasificar = cur.fetchone() is not None
        mensual[(mes.year, mes.month)] = resolver_costo_ventas_mensual(por_tipo, categoria_de_tipo, hay_sin_clasificar)

    return prorratear_mensual(mensual, desde, hasta)


def gasto_real_costo_ventas(cur, odoo_company_id: int, desde: date, hasta: date) -> Decimal | None:
    """Real Costo de Ventas spend for [desde, hasta], or None when the branch
    is not active in ControlPresupuestos_AP or has no Costo de Ventas spend
    recorded in the period (e.g. before that app existed): no records is
    "no data", never a zero spend.

    The source keys spend by week (the Monday of the week it counts toward),
    so a period includes the weeks whose Monday falls inside it. For a
    Monday-Sunday week that is exactly that week; for longer periods (month,
    year, range) a week straddling a boundary counts entirely in the period
    that contains its Monday.
    """
    sucursal = _sucursal_id(cur, odoo_company_id)
    if sucursal is None:
        return None
    cur.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(g.monto), 0)
        FROM presupuestos_gastoreal g
        JOIN presupuestos_tipogasto t ON t.id = g.tipo_gasto_id
        JOIN presupuestos_categoria c ON c.id = t.categoria_id
        WHERE g.sucursal_id = %s AND g.semana >= %s AND g.semana <= %s AND c.nombre = %s
        """,
        (sucursal, desde, hasta, CATEGORIA),
    )
    registros, total = cur.fetchone()
    return Decimal(total) if registros else None
