"""Inflation addendum of the commercial report, periods of a month or more
(owner, 2026-10-19 / 20): month, bimester, quarter, semester, year.

How much the period grew against the same period last year, and how much of
that growth was inflation: nominal change, the inflation between the two
periods, and the real change ((1 + nominal) / (1 + inflation) - 1). Money
rows (sales, ticket, check) are deflated; guests and tickets are volume.

The comparison is against the SAME PERIOD LAST YEAR, so the inflation is the
year-on-year one (September vs September: INPC sep / INPC sep a year
before - 1), never the monthly one (that only measures August -> September).
For several months: average INPC of the months / average INPC of the same
months last year - 1.

INEGI publishes a month's INPC around the 9th of the next month, after the
report goes out: the addendum covers the months of the period that ARE
published (the whole period when generated later); a month whose own INPC
is not out yet analyses the most recent published month. It always says
which months and why; inflation is never estimated.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .comparativos import Variacion, variacion
from .metricas import Comparacion, Metricas
from .periodo import Periodo, TipoPeriodo, _MESES_ES
from .tabla_comercial import ENTERO, MONEDA

log = logging.getLogger(__name__)
UNO = Decimal("1")
MESES_ATRAS = 3  # how far back a monthly addendum looks for a month with published inflation
# Periods of a month or more (a week or a free range has no addendum).
TIPOS = {TipoPeriodo.MES, TipoPeriodo.BIMESTRE, TipoPeriodo.TRIMESTRE, TipoPeriodo.SEMESTRE, TipoPeriodo.ANIO}


def serie(token: str = "", hoy: date | None = None) -> dict[date, Decimal]:
    """{first day of month: INPC} from the database; months missing up to the
    last closed month are fetched from Banxico first (when there is a token).
    Any failure leaves the stored months (the addendum then says what it has)."""
    from ..models import Inflacion
    guardados = {i.mes: i.inpc for i in Inflacion.objects.all()}
    hoy = hoy or date.today()
    ultimo_cerrado = date(hoy.year, hoy.month, 1)
    if token and (not guardados or max(guardados) < _mes_menos(ultimo_cerrado, 1)):
        try:
            from .fuentes import banxico
            desde = _mes_menos(max(guardados), 12) if guardados else date(2023, 1, 1)
            for mes, valor in banxico.inpc(token, desde, hoy).items():
                if mes not in guardados:
                    Inflacion.objects.update_or_create(mes=mes, defaults={"inpc": valor,
                                                                           "fuente": Inflacion.Fuente.BANXICO})
                    guardados[mes] = valor
        except Exception:  # network / token: keep what is stored
            log.exception("No se pudo leer el INPC de Banxico")
    return guardados


def _mes_menos(d: date, meses: int) -> date:
    total = d.year * 12 + d.month - 1 - meses
    return date(total // 12, total % 12 + 1, 1)


def anual(inpc: dict[date, Decimal], mes: date) -> Decimal | None:
    """Year-on-year inflation of `mes` (first day), or None if either month is missing."""
    a, b = inpc.get(mes), inpc.get(_mes_menos(mes, 12))
    return a / b - UNO if a and b else None


def meses(p: Periodo) -> list[date]:
    """First day of every month of the period."""
    actual, fin, salida = date(p.desde.year, p.desde.month, 1), date(p.hasta.year, p.hasta.month, 1), []
    while actual <= fin:
        salida.append(actual)
        actual = _mes_menos(actual, -1)
    return salida


def del_periodo(inpc: dict[date, Decimal], p: Periodo) -> Decimal | None:
    """Inflation between the period and the same months a year earlier (average
    INPC / average INPC - 1; one month: the year-on-year inflation)."""
    ms = meses(p)
    if not all(inpc.get(m) and inpc.get(_mes_menos(m, 12)) for m in ms):
        return None
    return sum(inpc[m] for m in ms) / sum(inpc[_mes_menos(m, 12)] for m in ms) - UNO


def _ultimo_dia(m: date) -> date:
    return date.fromordinal(_mes_menos(m, -1).toordinal() - 1)


def periodo_analizado(periodo: Periodo, inpc: dict[date, Decimal]) -> Periodo | None:
    """The period itself when all its months are published; else its first
    months that are (a range of whole months); a month not published yet:
    the most recent previous month that is (at most MESES_ATRAS back)."""
    if periodo.tipo not in TIPOS:
        return None
    ms = meses(periodo)
    publicados = 0
    while publicados < len(ms) and anual(inpc, ms[publicados]) is not None:
        publicados += 1
    if publicados == len(ms):
        return periodo
    if publicados:
        hasta = ms[publicados - 1]
        if publicados == 1:
            return Periodo.de_fecha(TipoPeriodo.MES, hasta)
        return Periodo.rango(ms[0], _ultimo_dia(hasta))
    if periodo.tipo == TipoPeriodo.MES:
        for atras in range(1, MESES_ATRAS + 1):
            m = _mes_menos(ms[0], atras)
            if anual(inpc, m) is not None:
                return Periodo.de_fecha(TipoPeriodo.MES, m)
    return None


mes_analizado = periodo_analizado  # (name used before 2026-10-20)


def real(nominal: Decimal | None, inflacion: Decimal) -> Decimal | None:
    return (UNO + nominal) / (UNO + inflacion) - UNO if nominal is not None else None


@dataclass
class FilaInflacion:
    etiqueta: str
    formato: str
    actual: Decimal | None
    base: Decimal | None
    nominal: Variacion
    real: Variacion | None  # money rows only: the change once inflation is taken out


@dataclass
class SucursalInflacion:
    nombre: str
    nominal: Variacion
    real: Variacion


@dataclass
class Addendum:
    mes: Periodo
    mes_anio: Periodo
    inflacion: Decimal
    filas: list[FilaInflacion]
    lectura: list[str]
    nota: str
    excluidas: list[str] = field(default_factory=list)
    por_sucursal: list[SucursalInflacion] = field(default_factory=list)  # consolidated only


def _nombre_mes(p: Periodo) -> str:
    """"septiembre 2026", "julio – agosto 2026", or the period's label."""
    d, h = p.desde, p.hasta
    if p.tipo == TipoPeriodo.MES:
        return f"{_MESES_ES[d.month - 1]} {d.year}"
    if p.tipo == TipoPeriodo.RANGO and d.day == 1 and h == _ultimo_dia(date(h.year, h.month, 1)):
        inicio = _MESES_ES[d.month - 1] + ("" if d.year == h.year else f" {d.year}")
        return f"{inicio} – {_MESES_ES[h.month - 1]} {h.year}"
    return p.etiqueta()


INDICADORES = [  # (label, value, money?)
    ("Venta bruta", lambda m: m.venta_bruta, True),
    ("Ticket promedio", lambda m: m.ticket_promedio, True),
    ("Cheque promedio", lambda m: m.cheque_promedio, True),
    ("Clientes", lambda m: m.clientes, False),
    ("Tickets", lambda m: m.tickets, False),
]


def _valor(f, m: Metricas | None):
    return f(m) if m is not None and m.dias_con_cierre else None


def _real(actual, base, inflacion: Decimal) -> Variacion:
    """Change after deflating the period's amount by the year's inflation (same arrow rule)."""
    return variacion(actual / (UNO + inflacion) if actual is not None else None, base)


def _pct(v: Variacion) -> str:
    return f"{v.porcentaje * 100:+.1f}%" if v.porcentaje is not None else "s/c"


def construir(mes: Periodo, comp: Comparacion, inflacion: Decimal, periodo_reporte: Periodo,
              por_sucursal: list[tuple[str, Metricas, Metricas | None]] | None = None) -> Addendum:
    """`comp`: the analysed month against the same month last year (comparable branches)."""
    filas = []
    for etiqueta, f, dinero in INDICADORES:
        a, b = _valor(f, comp.actual), _valor(f, comp.base)
        filas.append(FilaInflacion(etiqueta, MONEDA if dinero else ENTERO, a, b, variacion(a, b),
                                   _real(a, b, inflacion) if dinero else None))
    venta, ticket, cheque, clientes, tickets = filas
    nm, na = _nombre_mes(mes), _nombre_mes(mes.mismo_periodo_anio_anterior())
    lectura = []
    if venta.nominal.porcentaje is not None:
        sentido = "creció" if venta.real.porcentaje > 0 else "bajó"
        lectura.append(f"La venta bruta de {nm} cambió {_pct(venta.nominal)} contra {na}. Con una inflación anual de "
                       f"{inflacion * 100:.2f}%, en términos reales {sentido} {abs(venta.real.porcentaje) * 100:.1f}%.")
        if cheque.real is not None and cheque.real.porcentaje is not None:
            gana = "le ganó a" if cheque.real.porcentaje > 0 else "quedó abajo de"
            lectura.append(f"El cheque promedio cambió {_pct(cheque.nominal)} ({_pct(cheque.real)} real): lo que gasta "
                           f"cada cliente {gana} la inflación.")
        if clientes.nominal.porcentaje is not None:
            lectura.append(f"Los clientes cambiaron {_pct(clientes.nominal)} y los tickets {_pct(tickets.nominal)}: es "
                           "el volumen, que no tiene inflación.")
    else:
        lectura.append(f"Sin comparativo de {na}: no se puede separar el crecimiento de la inflación.")
    pendientes = [m for m in meses(periodo_reporte) if m > mes.hasta]
    falta = ("" if not pendientes else f"{_MESES_ES[pendientes[0].month - 1]} {pendientes[0].year}"
             if len(pendientes) == 1 else
             f"{_MESES_ES[pendientes[0].month - 1]} a {_MESES_ES[pendientes[-1].month - 1]} {pendientes[-1].year}")
    if mes == periodo_reporte:
        nota = f"La inflación de {nm} ya está publicada por INEGI: el addendum cubre todo el periodo del reporte."
    elif mes.desde >= periodo_reporte.desde:
        nota = (f"Se analiza {nm}, los meses del periodo con inflación publicada: INEGI publica la inflación de cada mes "
                f"alrededor del día 9 del mes siguiente, y la de {falta} todavía no estaba publicada al generar este "
                "reporte.")
    else:
        nota = (f"Se analiza {nm} y no {_nombre_mes(periodo_reporte)}: INEGI publica la inflación de cada mes alrededor "
                f"del día 9 del mes siguiente, y la de {_nombre_mes(periodo_reporte)} todavía no estaba publicada al "
                "generar este reporte.")
    nota += (" Inflación anual = INPC general del mes / INPC del mismo mes del año anterior - 1; de varios meses, el "
             "promedio del INPC de esos meses / el de los mismos meses del año anterior - 1 (INEGI, vía Banxico, "
             "serie SP1). Es la anual porque se compara contra el mismo periodo del año anterior. "
             "Real = (1 + crecimiento) / (1 + inflación) - 1.")
    filas_suc = []
    for nombre, a, b in por_sucursal or []:
        va, vb = _valor(lambda m: m.venta_bruta, a), _valor(lambda m: m.venta_bruta, b)
        filas_suc.append(SucursalInflacion(nombre, variacion(va, vb), _real(va, vb, inflacion)))
    filas_suc.sort(key=lambda s: (s.real.porcentaje is not None, s.real.porcentaje or 0), reverse=True)
    return Addendum(mes, mes.mismo_periodo_anio_anterior(), inflacion, filas, lectura, nota, comp.excluidas, filas_suc)
