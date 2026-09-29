"""Checks that the report sources still fit the engine (read-only).

Written for the 2026-10-01 Wansoft cutover (new schema and pipeline on the
live `wansoft`), and reusable after any source change: every table/column
the engine reads exists, the account cannot write, and the data is fresh.
The judgement functions are pure (tested); the `leer_*` ones only run
SELECTs against information_schema and the source tables.
"""

import re
from datetime import date, datetime, timedelta

from .wansoft import dia_operativo

# Data is loaded once a day (~01:30) through the previous day; between
# midnight and the load the newest day can be two days old.
DIAS_TOLERANCIA = 2
PRIVILEGIOS_LECTURA = {"SELECT", "USAGE", "SHOW VIEW"}


def faltantes(requeridas: dict[str, list[str]], existentes: dict[str, set[str]]) -> dict[str, list[str]]:
    """Columns the engine needs that the schema lacks, per table (a missing
    table lists all its columns)."""
    return {tabla: [c for c in cols if c not in existentes.get(tabla, set())]
            for tabla, cols in requeridas.items()
            if any(c not in existentes.get(tabla, set()) for c in cols)}


def atrasadas(ultimo_dia: dict[str, date | None], hoy: date, tolerancia: int = DIAS_TOLERANCIA) -> list[tuple[str, date | None]]:
    """Branches whose newest day of data is older than `hoy - tolerancia` (or none)."""
    limite = hoy - timedelta(days=tolerancia)
    return sorted(((n, d) for n, d in ultimo_dia.items() if d is None or d < limite), key=lambda x: x[0])


def puede_escribir(grants: list[str]) -> bool:
    """True if any grant of the account gives more than read access."""
    for g in grants:
        m = re.match(r"GRANT (.+?) ON ", g)
        if not m:
            continue
        privilegios = {p.strip().split("(")[0].strip() for p in m.group(1).split(",")}
        if privilegios - PRIVILEGIOS_LECTURA:
            return True
    return False


# -- read-only queries ------------------------------------------------------
def leer_columnas(cur, tablas: list[str]) -> dict[str, set[str]]:
    marcas = ", ".join(["%s"] * len(tablas))
    cur.execute(
        f"SELECT table_name, column_name FROM information_schema.columns "
        f"WHERE table_schema = DATABASE() AND table_name IN ({marcas})", tablas)
    existentes: dict[str, set[str]] = {}
    for tabla, columna in cur.fetchall():
        existentes.setdefault(tabla, set()).add(columna)
    return existentes


def leer_grants(cur) -> list[str]:
    cur.execute("SHOW GRANTS")
    return [fila[0] for fila in cur.fetchall()]


def leer_llave_unica_cierres(cur) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() "
        "AND table_name = 'getglobalcashclosing' AND index_name = 'uq_subsidiary_fecha_corte'")
    return cur.fetchone()[0] > 0


def leer_ultimo_cierre(cur, subsidiary_ids: list[int], hoy: date) -> dict[int, date]:
    """Newest operating day with a cash closing per branch (last 60 days)."""
    marcas = ", ".join(["%s"] * len(subsidiary_ids))
    cur.execute(
        f"SELECT subsidiary_id, MAX(fecha_corte) FROM getglobalcashclosing "
        f"WHERE subsidiary_id IN ({marcas}) AND fecha_corte >= %s GROUP BY subsidiary_id",
        (*subsidiary_ids, datetime.combine(hoy - timedelta(days=60), datetime.min.time())))
    return {s: dia_operativo(f) for s, f in cur.fetchall()}


def leer_ultimo_ticket(cur, nombres: list[str], hoy: date) -> dict[str, date]:
    """Newest day with ticket detail per branch (last 30 days). One scan of
    the ticket table (unindexed on Sucursal/Fecha): a few seconds."""
    marcas = ", ".join(["%s"] * len(nombres))
    cur.execute(
        f"SELECT Sucursal, MAX(LEFT(Fecha, 10)) FROM getallordenesbyday_new_venta "
        f"WHERE Sucursal IN ({marcas}) AND Fecha >= %s GROUP BY Sucursal",
        (*nombres, (hoy - timedelta(days=30)).isoformat()))
    return {s: date.fromisoformat(d) for s, d in cur.fetchall() if d}
