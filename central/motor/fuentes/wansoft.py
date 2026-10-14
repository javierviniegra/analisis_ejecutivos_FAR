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
    "getallordenesbyday_new_venta": ["Sucursal", "Fecha", "TipoOrden", "Total", "Movimento", "Subtotal", "Personas",
                                     "Mesero", "HoraApertura", "HoraCierre"],
    "getallordenesbyday_new_detalleventa": ["Movimiento_Id", "Sucursal", "TipoGrupo", "Total", "Cortesia", "Cantidad",
                                            "PrecioUnitario", "Descuento"],
    "getallordenesbyday_new_pago": ["Movimiento_Id", "Sucursal", "Propina"],
    "costeomensual": ["id", "subsidiary_id", "created_at", "CostoTotal", "CostoDeConsumo",
                      "CostoIdealDeProductosPendientesDeRebaja"],
    "costeomensual_semanapyq": ["id", "subsidiary_id", "created_at", "CostoTotal", "CostoDeConsumo",
                                "CostoIdealDeProductosPendientesDeRebaja"],
    "dim_company_analytical": ["company_source_key", "purchases_source_system", "operational_start_date"],
    "gettotalcostbydate": ["subsidiary_id", "created_date", "CostoTotalVenta"],
    "odoo_company_migration_policy": ["odoo_company_id", "operational_start_date", "is_active"],
    "costs_odoo_switch": ["company_source_key", "switch_date"],
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


CLAVES_CIERRE = ("venta_bruta", "venta_neta", "tickets", "clientes", "mesas", "cortesias", "cancelaciones",
                 "anulaciones", "descuentos")
TOLERANCIA_TICKETS = Decimal("1")  # pesos: a closing "matches" the day's tickets within this


def cierres_por_dia(cur, subsidiary_ids: list[int], desde: date, hasta: date,
                    tickets_de: dict[int, str] | None = None,
                    descartados: list | None = None,
                    por_tickets: list | None = None) -> dict[int, dict[date, dict]]:
    """Daily totals from the cash closing, per branch and operating day,
    deduplicated: {subsidiary_id: {day: totals}}.

    Amounts are as recorded by the POS: `venta_bruta` includes IVA,
    `venta_neta` does not; cortesias / cancelaciones / anulaciones /
    descuentos are valued at sale price (not ingredient cost).

    **Several closings in one day (owner, 2026-10-06).** When a branch has
    more than one distinct closing for a day and exactly the sum of that day's
    tickets equals ONE of them, only that one counts; the others are partial
    or spurious (an afternoon closing repeated by the cumulative night one,
    a stray one-order closing after midnight, the 1-Oct morning re-closing of
    the October wave) -- 13 days in 2026, every one matching one closing to
    the peso. Without a match, or without ticket detail, all are added as
    before (two real shifts match their sum). `tickets_de` maps
    subsidiary_id -> ticket `Sucursal` name; each discarded closing is
    appended to `descartados` as (subsidiary_id, day, total_ventas).

    **A day with tickets but no cash closing (owner, 2026-10-12)** -- e.g. La
    Esquina Coyoacán, Sunday 11-Oct: the closing exists in Wansoft (22:09) but
    did not reach the database -- takes the day's sales from the tickets:
    gross, net, tickets and guests (they match the closing to the peso);
    tables, courtesies, cancellations, voids and discounts stay 0. Each such
    day is appended to `por_tickets` as (subsidiary_id, day, venta_bruta).
    """
    if not subsidiary_ids:
        return {}
    inicio, fin = _limites_cierre(desde, hasta)
    cur.execute(
        f"""
        SELECT subsidiary_id, dia, total_ventas, subtotal, no_ordenes, total_personas, total_mesas_atendidas,
               cortesias_en_cuentas + cortesias_en_platillos,
               cancelaciones_en_cuentas + cancelaciones_en_platillos,
               anulaciones_en_cuentas + anulaciones_en_platillos,
               descuentos_en_cuentas + descuentos_en_platillos
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
        """,
        (HORA_CORTE_DIA, HORA_CORTE_DIA, *subsidiary_ids, inicio, fin),
    )
    cortes: dict[tuple[int, date], list[dict]] = {}
    for fila in cur.fetchall():
        cortes.setdefault((fila[0], fila[1]), []).append(
            dict(zip(CLAVES_CIERRE, (Decimal(v or 0) for v in fila[2:]))))

    varios = [k for k, lista in cortes.items() if len(lista) > 1 and tickets_de and k[0] in tickets_de]
    if varios:
        tickets = _tickets_por_dia(cur, {tickets_de[sid] for sid, _ in varios},
                                   min(d for _, d in varios), max(d for _, d in varios))
        for sid, dia in varios:
            del_dia = tickets.get((tickets_de[sid], dia))
            if del_dia is None:
                continue
            total = del_dia["venta_bruta"]
            iguales = [c for c in cortes[(sid, dia)] if abs(c["venta_bruta"] - total) <= TOLERANCIA_TICKETS]
            if len(iguales) == 1:
                if descartados is not None:
                    descartados += [(sid, dia, c["venta_bruta"]) for c in cortes[(sid, dia)] if c is not iguales[0]]
                cortes[(sid, dia)] = iguales

    resultado: dict[int, dict[date, dict]] = {}
    for (sid, dia), lista in cortes.items():
        resultado.setdefault(sid, {})[dia] = {k: sum((c[k] for c in lista), Decimal("0")) for k in CLAVES_CIERRE}

    con_tickets = {sid: n for sid, n in (tickets_de or {}).items() if sid in subsidiary_ids}
    if con_tickets:
        dias = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
        faltan = {sid: [x for x in dias if x not in resultado.get(sid, {})] for sid in con_tickets}
        faltan = {sid: xs for sid, xs in faltan.items() if xs}
        if faltan:
            tickets = _tickets_por_dia(cur, {con_tickets[sid] for sid in faltan},
                                       min(min(xs) for xs in faltan.values()), max(max(xs) for xs in faltan.values()))
            for sid, xs in faltan.items():
                for dia in xs:
                    del_dia = tickets.get((con_tickets[sid], dia))
                    if del_dia is None or not del_dia["venta_bruta"]:
                        continue
                    resultado.setdefault(sid, {})[dia] = {k: del_dia.get(k, Decimal("0")) for k in CLAVES_CIERRE}
                    if por_tickets is not None:
                        por_tickets.append((sid, dia, del_dia["venta_bruta"]))
    return resultado


def _tickets_por_dia(cur, nombres: set[str], desde: date, hasta: date) -> dict[tuple[str, date], dict]:
    """The day's tickets per branch name: gross (`Total`, as `total_ventas`),
    net (`Subtotal`), ticket count and guests (`Personas`). Checked against
    the cash closings, 5-10 Oct 2026: 113 of 114 branch-days equal to the
    peso in gross, net and tickets. Discounts, courtesies and cancellations
    are NOT in this table the way the closing has them."""
    nombres = sorted(nombres)
    cur.execute(
        f"SELECT Sucursal, DATE(Fecha), SUM(Total), SUM(Subtotal), COUNT(*), SUM(Personas) "
        f"FROM getallordenesbyday_new_venta "
        f"WHERE Sucursal IN ({_marcadores(nombres)}) AND Fecha >= %s AND Fecha < %s GROUP BY Sucursal, DATE(Fecha)",
        (*nombres, datetime.combine(desde, time.min), datetime.combine(hasta + timedelta(days=1), time.min)),
    )
    return {(n, d): {"venta_bruta": Decimal(str(t)), "venta_neta": Decimal(str(s or 0)), "tickets": Decimal(c),
                     "clientes": Decimal(str(p or 0))}
            for n, d, t, s, c, p in cur.fetchall() if t is not None}


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


COSTO_TOTAL = "CostoTotal - COALESCE(CostoDeConsumo, 0)"
# Cost of what was sold that Wansoft has not yet discounted from inventory: while
# above 0 the row's cost is not final (Wansoft recalculates it; rows inside the
# pipeline's 10-day window are rewritten every night).
PENDIENTE_REBAJA = "COALESCE(CostoIdealDeProductosPendientesDeRebaja, 0)"


def _costo_ultima_foto(cur, tabla: str, subsidiary_ids: list[int], desde: date, hasta: date,
                       expresion: str = COSTO_TOTAL) -> dict[int, Decimal]:
    """A value (default the cost) of the latest snapshot per branch with capture
    date in [desde, hasta]. Cost = `CostoTotal - COALESCE(CostoDeConsumo, 0)`
    (the data guide's "Costo Total"; COALESCE because Odoo rows leave
    consumption NULL). The capture date is read from `created_at` (present
    before and after the 2026-10-01 migration, which adds `created_date` = its
    date); the latest capture wins."""
    marcas = ", ".join(["%s"] * len(subsidiary_ids))
    cur.execute(
        f"""
        SELECT subsidiary_id, {expresion}
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


def costo_total_semana(cur, subsidiary_ids: list[int], lunes: date, expresion: str = COSTO_TOTAL) -> dict[int, Decimal]:
    """Monday-Sunday week from `costeomensual_semanapyq`. A row accumulates from
    Monday through the day BEFORE its capture date, so the complete week is the
    row captured the next Monday (checked: Isabel 21-Sep row = sum of daily
    cost 14-20 Sep); for a week in progress, the latest row so far."""
    if not subsidiary_ids:
        return {}
    return _costo_ultima_foto(cur, "costeomensual_semanapyq", subsidiary_ids,
                              lunes + timedelta(days=1), lunes + timedelta(days=7), expresion)


def costo_total_mes(cur, subsidiary_ids: list[int], primero: date, ultimo: date,
                    expresion: str = COSTO_TOTAL) -> dict[int, Decimal]:
    """Calendar month from `costeomensual` (month-to-date from the 1st through the
    capture date): the latest row of the month."""
    if not subsidiary_ids:
        return {}
    return _costo_ultima_foto(cur, "costeomensual", subsidiary_ids, primero, ultimo, expresion)


# Purchases systems in `dim_company_analytical` that mean "buys in Odoo".
COMPRAS_EN_ODOO = ("odoo", "mixed_by_operational_start_date", "pending")


def inicio_compras_odoo(cur) -> dict[str, date]:
    """Date each branch started buying in Odoo, by its short key (the sales
    `Sucursal`, our `wansoft_ticket_nombre`), from the Wansoft project's
    governance table. Only branches whose purchases are in Odoo: earlier Odoo
    activity of the others (e.g. the 2024 pilot) is not real and stays out.
    Read live on every report, never hard-coded: the pipeline updates it when
    a branch migrates (Isabel, San Jeronimo and Vallejo on 2026-10-01)."""
    marcas = ", ".join(["%s"] * len(COMPRAS_EN_ODOO))
    cur.execute(
        f"SELECT company_source_key, operational_start_date FROM dim_company_analytical "
        f"WHERE purchases_source_system IN ({marcas}) AND operational_start_date IS NOT NULL "
        f"AND is_internal_provider = 0",
        COMPRAS_EN_ODOO,
    )
    return {clave: inicio for clave, inicio in cur.fetchall()}


def inicio_proveedores_internos(cur) -> dict[str, date]:
    """Odoo start date of the internal providers (El Bodegón, Las Empanadas), by
    their display name, from the same governance table."""
    cur.execute("SELECT display_name, operational_start_date FROM dim_company_analytical "
                "WHERE is_internal_provider = 1 AND operational_start_date IS NOT NULL")
    return {nombre: inicio for nombre, inicio in cur.fetchall()}


def costo_diario(cur, subsidiary_ids: list[int], desde: date, hasta: date) -> dict[int, dict[date, Decimal]]:
    """Total cost per branch and day from `gettotalcostbydate` (one row per
    branch and day, unique key). The weekly snapshot is the sum of these days
    (checked: Acoxpa week 40 = $258,969 both ways)."""
    if not subsidiary_ids:
        return {}
    cur.execute(
        f"SELECT subsidiary_id, created_date, CostoTotalVenta FROM gettotalcostbydate "
        f"WHERE subsidiary_id IN ({_marcadores(subsidiary_ids)}) AND created_date BETWEEN %s AND %s",
        (*subsidiary_ids, desde, hasta),
    )
    resultado: dict[int, dict[date, Decimal]] = {}
    for sid, dia, costo in cur.fetchall():
        if costo is not None:
            resultado.setdefault(sid, {})[dia] = Decimal(costo)
    return resultado


# The Wansoft pipeline publishes its cost routing every night in
# `costs_source_by_company` (since the run of 2026-10-06 ~02:00): first day on
# Odoo cost per branch, NULL = all Wansoft. Read it when it exists. Fallback
# while it does not: a mirror of the pipeline's code (extract/costs/cost_routing.py,
# core/config/companies.py):
# - Antenas stays on Wansoft costs while its Odoo cost data is repaired;
# - the October wave switches to Odoo costs by itself, from the date recorded
#   in `costs_odoo_switch` (none recorded = still on Wansoft).
TABLA_RUTA_COSTOS = "costs_source_by_company"
COSTOS_EXCEPCION_WANSOFT = {"Antenas"}
COSTOS_CAMBIO_AUTOMATICO = {"Isabel La Católica", "San Jeronimo", "Vía Vallejo"}


def inicio_costos_odoo(cur, sucursales: list) -> dict[str, date]:
    """First day each branch's total cost comes from Odoo, by its short key
    (`wansoft_ticket_nombre`); branches whose cost is all Wansoft are absent.
    Odoo's cost of a day is built from that day's customer invoices, which
    arrive late, so the report estimates those days (see metricas)."""
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
                (TABLA_RUTA_COSTOS,))
    if cur.fetchall()[0][0]:
        cur.execute(f"SELECT company_source_key, odoo_cost_start_date FROM {TABLA_RUTA_COSTOS} "
                    "WHERE odoo_cost_start_date IS NOT NULL")
        publicadas = dict(cur.fetchall())
        return {s.wansoft_ticket_nombre: publicadas[s.wansoft_ticket_nombre] for s in sucursales
                if s.wansoft_ticket_nombre in publicadas}
    con_odoo = [s for s in sucursales if s.odoo_company_id is not None
                and s.wansoft_ticket_nombre not in COSTOS_EXCEPCION_WANSOFT]
    if not con_odoo:
        return {}
    cur.execute(
        f"SELECT odoo_company_id, operational_start_date FROM odoo_company_migration_policy "
        f"WHERE is_active = 1 AND operational_start_date IS NOT NULL "
        f"AND odoo_company_id IN ({_marcadores(con_odoo)})",
        [s.odoo_company_id for s in con_odoo],
    )
    politica = dict(cur.fetchall())
    cur.execute("SELECT company_source_key, switch_date FROM costs_odoo_switch WHERE switch_date IS NOT NULL")
    cambios = dict(cur.fetchall())
    inicios = {}
    for s in con_odoo:
        inicio = politica.get(s.odoo_company_id)
        if inicio is None:
            continue  # no policy row: the pipeline keeps it on Wansoft
        if s.wansoft_ticket_nombre in COSTOS_CAMBIO_AUTOMATICO:
            cambio = cambios.get(s.wansoft_ticket_nombre)
            if cambio is None:
                continue
            inicio = max(inicio, cambio)
        inicios[s.wansoft_ticket_nombre] = inicio
    return inicios


# -- waiters (reporte de meseros) ---------------------------------------------
# Owner, 2026-10-13: the waiters' sales are the DINING-ROOM orders only; the
# pseudo-waiters of the other order types (APLICACIONES, Apps Llevar...) are
# reported apart as sales without a waiter.
TIPO_SALON = "Restaurant"
# A table is "open" from the ticket's opening to its closing; a time outside
# this range (a ticket left open, a clock reset) is left out of the average.
MINUTOS_MESA_MIN, MINUTOS_MESA_MAX = 1, 360


def ventas_meseros(cur, nombres: list[str], desde: date, hasta: date) -> dict[str, dict[str, dict]]:
    """Per branch (ticket-table name) and waiter, the dining-room tickets of the
    range: accounts (tables served), guests, gross and net sales, days worked
    and table time. {branch: {waiter: {...}}}."""
    nombres = [n for n in nombres if n]
    if not nombres:
        return {}
    a, b = _rango_fecha_texto(desde, hasta)
    cur.execute(
        f"""
        SELECT Sucursal, Mesero, COUNT(*), SUM(CAST(Personas AS DECIMAL(12,0))),
               SUM(CAST(Total AS DECIMAL(14,2))), SUM(CAST(Subtotal AS DECIMAL(14,2))),
               COUNT(DISTINCT LEFT(Fecha, 10)),
               SUM(CASE WHEN TIMESTAMPDIFF(MINUTE, HoraApertura, HoraCierre) BETWEEN %s AND %s
                        THEN TIMESTAMPDIFF(MINUTE, HoraApertura, HoraCierre) END),
               SUM(TIMESTAMPDIFF(MINUTE, HoraApertura, HoraCierre) BETWEEN %s AND %s)
        FROM getallordenesbyday_new_venta
        WHERE Sucursal IN ({_marcadores(nombres)}) AND Fecha >= %s AND Fecha < %s AND TipoOrden = %s
        GROUP BY Sucursal, Mesero
        """,
        (MINUTOS_MESA_MIN, MINUTOS_MESA_MAX, MINUTOS_MESA_MIN, MINUTOS_MESA_MAX, *nombres, a, b, TIPO_SALON),
    )
    claves = ("cuentas", "personas", "venta_bruta", "venta_neta", "dias", "minutos_mesa", "mesas_con_tiempo")
    resultado: dict[str, dict[str, dict]] = {}
    for sucursal, mesero, *valores in cur.fetchall():
        resultado.setdefault(sucursal, {})[(mesero or "").strip() or "(sin nombre)"] = dict(
            zip(claves, (Decimal(v or 0) for v in valores)))
    return resultado


def fuera_de_salon(cur, nombres: list[str], desde: date, hasta: date) -> dict[str, dict[str, dict]]:
    """The orders that are not dining room, per branch and channel
    (plataformas = platforms / apps, llevar = take-away, otros): accounts,
    gross sales, discounts and courtesies (same definitions as the waiters':
    discounts of the non-courtesy lines, courtesies at sale price; owner,
    2026-10-14: apps in their own section, to see their discounts).
    {branch: {canal: {"cuentas", "venta_bruta", "descuentos", "cortesias"}}}"""
    nombres = [n for n in nombres if n]
    if not nombres:
        return {}
    cero = Decimal("0")
    resultado: dict[str, dict[str, dict]] = {}

    def del_canal(sucursal, tipo):
        canal = CANALES.get(tipo, CANAL_OTROS)
        return resultado.setdefault(sucursal, {}).setdefault(canal, {
            "cuentas": cero, "venta_bruta": cero, "descuentos": cero, "cortesias": cero})

    a, b = _rango_fecha_texto(desde, hasta)
    cur.execute(
        f"SELECT Sucursal, TipoOrden, COUNT(*), SUM(CAST(Total AS DECIMAL(14,2))) FROM getallordenesbyday_new_venta "
        f"WHERE Sucursal IN ({_marcadores(nombres)}) AND Fecha >= %s AND Fecha < %s AND TipoOrden <> %s "
        f"GROUP BY Sucursal, TipoOrden",
        (*nombres, a, b, TIPO_SALON),
    )
    for sucursal, tipo, n, total in cur.fetchall():
        c = del_canal(sucursal, tipo)
        c["cuentas"] += Decimal(n or 0)
        c["venta_bruta"] += Decimal(total or 0)
    for inicio, fin_tramo in _tramos_mensuales(desde, hasta):  # the 12 M-row line table: per month
        a, b = _rango_fecha_texto(inicio, fin_tramo)
        cur.execute(
            f"""
            SELECT v.Sucursal, v.TipoOrden,
                   SUM(CASE WHEN d.Cortesia <> '1' THEN CAST(d.Descuento AS DECIMAL(14,2)) ELSE 0 END),
                   SUM(CASE WHEN d.Cortesia = '1'
                            THEN CAST(d.Cantidad AS DECIMAL(12,4)) * CAST(d.PrecioUnitario AS DECIMAL(14,4)) ELSE 0 END)
            FROM getallordenesbyday_new_venta v
            JOIN getallordenesbyday_new_detalleventa d
              ON d.Movimiento_Id = v.Movimento AND d.Sucursal = v.Sucursal
            WHERE v.Sucursal IN ({_marcadores(nombres)}) AND v.Fecha >= %s AND v.Fecha < %s AND v.TipoOrden <> %s
            GROUP BY v.Sucursal, v.TipoOrden
            """,
            (*nombres, a, b, TIPO_SALON),
        )
        for sucursal, tipo, descuento, cortesia in cur.fetchall():
            c = del_canal(sucursal, tipo)
            c["descuentos"] += Decimal(descuento or 0)
            c["cortesias"] += Decimal(cortesia or 0)
    return resultado


def mix_meseros(cur, nombres: list[str], desde: date, hasta: date) -> dict[str, dict[str, dict]]:
    """Per branch and waiter, from the order lines of the dining-room tickets:
    gross sales of Alimentos and Bebidas; courtesies at their SALE price
    (quantity x unit price -- the courtesy line keeps the dish's price, its
    total is 0; no cost involved); and discounts (`Descuento` of the lines
    that are not courtesies: a courtesy also shows as a 100% discount).
    September 2026, all branches: courtesies = the cash closings to the peso
    (19 of 19); discounts = the closings in 13 of 19 (the other 6 have round
    extra amounts in the detail). One statement per month, as
    `mix_alimentos_bebidas` (the 12 M-row line table)."""
    nombres = [n for n in nombres if n]
    if not nombres:
        return {}
    resultado: dict[str, dict[str, dict]] = {}
    for inicio, fin in _tramos_mensuales(desde, hasta):
        a, b = _rango_fecha_texto(inicio, fin)
        cur.execute(
            f"""
            SELECT v.Sucursal, v.Mesero, d.TipoGrupo, SUM(CAST(d.Total AS DECIMAL(14,2))),
                   SUM(CASE WHEN d.Cortesia = '1'
                            THEN CAST(d.Cantidad AS DECIMAL(12,4)) * CAST(d.PrecioUnitario AS DECIMAL(14,4)) ELSE 0 END),
                   SUM(CASE WHEN d.Cortesia <> '1' THEN CAST(d.Descuento AS DECIMAL(14,2)) ELSE 0 END)
            FROM getallordenesbyday_new_venta v
            JOIN getallordenesbyday_new_detalleventa d
              ON d.Movimiento_Id = v.Movimento AND d.Sucursal = v.Sucursal
            WHERE v.Sucursal IN ({_marcadores(nombres)}) AND v.Fecha >= %s AND v.Fecha < %s AND v.TipoOrden = %s
            GROUP BY v.Sucursal, v.Mesero, d.TipoGrupo
            """,
            (*nombres, a, b, TIPO_SALON),
        )
        for sucursal, mesero, grupo, total, cortesia, descuento in cur.fetchall():
            m = resultado.setdefault(sucursal, {}).setdefault((mesero or "").strip() or "(sin nombre)", {
                "alimentos": Decimal("0"), "bebidas": Decimal("0"), "cortesias": Decimal("0"),
                "descuentos": Decimal("0")})
            if grupo == "Alimentos":
                m["alimentos"] += Decimal(total or 0)
            elif grupo == "Bebidas":
                m["bebidas"] += Decimal(total or 0)
            m["cortesias"] += Decimal(cortesia or 0)
            m["descuentos"] += Decimal(descuento or 0)
    return resultado


def propinas_meseros(cur, nombres: list[str], desde: date, hasta: date) -> dict[str, dict[str, Decimal]]:
    """Tips per branch and waiter, from the payments of the dining-room tickets."""
    nombres = [n for n in nombres if n]
    if not nombres:
        return {}
    resultado: dict[str, dict[str, Decimal]] = {}
    for inicio, fin in _tramos_mensuales(desde, hasta):  # the payments join is slow (8 s for a week): per month
        a, b = _rango_fecha_texto(inicio, fin)
        cur.execute(
            f"""
            SELECT v.Sucursal, v.Mesero, SUM(CAST(p.Propina AS DECIMAL(14,2)))
            FROM getallordenesbyday_new_venta v
            JOIN getallordenesbyday_new_pago p ON p.Movimiento_Id = v.Movimento AND p.Sucursal = v.Sucursal
            WHERE v.Sucursal IN ({_marcadores(nombres)}) AND v.Fecha >= %s AND v.Fecha < %s AND v.TipoOrden = %s
            GROUP BY v.Sucursal, v.Mesero
            """,
            (*nombres, a, b, TIPO_SALON),
        )
        for sucursal, mesero, propina in cur.fetchall():
            por = resultado.setdefault(sucursal, {})
            clave = (mesero or "").strip() or "(sin nombre)"
            por[clave] = por.get(clave, Decimal("0")) + Decimal(propina or 0)
    return resultado
