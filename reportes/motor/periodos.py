"""Period rules shared by every report (pure functions, no I/O).

Business rules (owner, 2026-09-23):
- A week is Monday to Sunday.
- "Same week last year" is the same ISO week number of the previous ISO
  year. If that year has no such week (week 53) there is no comparison.
- Months are calendar months.
- A monthly budget is prorated across the days of its month, so a week that
  spans two months blends both months' daily rates.
"""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal


def semana_lunes_domingo(fecha: date) -> tuple[date, date]:
    """Monday and Sunday of the week that contains `fecha`."""
    lunes = fecha - timedelta(days=fecha.weekday())
    return lunes, lunes + timedelta(days=6)


def semana_anterior(lunes: date) -> tuple[date, date]:
    """The week immediately before the one starting at `lunes`."""
    ant = lunes - timedelta(days=7)
    return ant, ant + timedelta(days=6)


def numero_semana(fecha: date) -> tuple[int, int]:
    """(ISO year, ISO week number). The ISO year can differ from the calendar
    year around New Year, so always carry both."""
    iso = fecha.isocalendar()
    return iso[0], iso[1]


def misma_semana_anio_anterior(lunes: date) -> tuple[date, date] | None:
    """Monday-Sunday of the same ISO week number in the previous ISO year, or
    None when that year has no such week (only possible for week 53)."""
    anio, semana = numero_semana(lunes)
    try:
        lunes_prev = date.fromisocalendar(anio - 1, semana, 1)
    except ValueError:
        return None
    return lunes_prev, lunes_prev + timedelta(days=6)


def dias(desde: date, hasta: date):
    """Every date from `desde` to `hasta`, both included."""
    d = desde
    while d <= hasta:
        yield d
        d += timedelta(days=1)


def prorratear_mensual(monto_por_mes: dict[tuple[int, int], Decimal], desde: date, hasta: date) -> Decimal:
    """Share of monthly amounts that falls in [desde, hasta].

    `monto_por_mes` maps (year, month) -> full monthly amount. Each day counts
    monthly_amount / days_in_that_month. A month with no entry contributes 0
    (a missing budget is not an implicit zero target -- callers must decide
    how to show "no budget"; see `hay_meta`).
    """
    total = Decimal("0")
    for d in dias(desde, hasta):
        monto = monto_por_mes.get((d.year, d.month))
        if monto is not None:
            total += Decimal(monto) / monthrange(d.year, d.month)[1]
    return total


def hay_meta(monto_por_mes: dict[tuple[int, int], Decimal], desde: date, hasta: date) -> bool:
    """True only if EVERY month touched by the range has a budget entry."""
    return all((d.year, d.month) in monto_por_mes for d in dias(desde, hasta))
