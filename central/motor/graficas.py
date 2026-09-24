"""Chart data of the commercial report (pure: no I/O, no drawing).

Both charts compare net sales (sin IVA) of the period, bucket by bucket,
against a comparison period: the previous period, and the same period last
year. Each chart uses a `Comparacion`, so it follows the comparable-branches
rule like the table (branches left out are named in the chart's note).

Bucket size follows the period length (owner, 2026-09-24): one bar per day
up to 31 days, per 7-day block from 32 to 92 days, per calendar month
beyond. Buckets are matched to the comparison period by position (day 1
with day 1, block 1 with block 1). A bucket with no cash closing at all has
no value (None), never a zero bar.

Month reports are different (owner, 2026-09-24): day-by-day pairing of two
different months mixes in the day-of-week effect (Aug 1 2026 was a
Saturday, Aug 1 2025 a Friday), and a month should be measured as a
calendar month. So a month gets (1) its net sales per day alone, and (2) a
12-month trend by calendar month vs the same months of the previous year.
The trend includes every branch (new branches show as empty/lower bars in
the months without data; the note says since when each has data), while
the table and the Lectura keep the comparable-branches rule.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from . import lectura
from .metricas import Comparacion, Metricas, como_comparacion
from .periodo import _MESES_ES, Periodo, TipoPeriodo

DIA, SEMANA, MES = "dia", "semana", "mes"
MAX_DIAS_POR_DIA = 31
MAX_DIAS_POR_SEMANA = 92

_DIAS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
_POR = {DIA: "por día", SEMANA: "por semana", MES: "por mes"}


def granularidad(periodo: Periodo) -> str:
    if periodo.dias <= MAX_DIAS_POR_DIA:
        return DIA
    if periodo.dias <= MAX_DIAS_POR_SEMANA:
        return SEMANA
    return MES


def cubetas(periodo: Periodo, gran: str) -> list[tuple[date, date]]:
    """[start, end] of each bucket of `periodo`, in order."""
    d, h = periodo.desde, periodo.hasta
    if gran == DIA:
        return [(d + timedelta(i), d + timedelta(i)) for i in range(periodo.dias)]
    if gran == SEMANA:
        return [(d + timedelta(i), min(d + timedelta(i + 6), h)) for i in range(0, periodo.dias, 7)]
    salida, inicio = [], d
    while inicio <= h:
        sig_mes = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
        fin = min(sig_mes - timedelta(days=1), h)
        salida.append((inicio, fin))
        inicio = fin + timedelta(days=1)
    return salida


def etiqueta(inicio: date, gran: str, dias_periodo: int, varios_anios: bool) -> str:
    if gran == DIA:
        return f"{_DIAS_ES[inicio.weekday()]} {inicio.day}" if dias_periodo <= 7 else str(inicio.day)
    if gran == SEMANA:
        return f"{inicio.day} {_MESES_ES[inicio.month - 1][:3]}"
    mes = _MESES_ES[inicio.month - 1][:3]
    return f"{mes} {inicio.year % 100:02d}" if varios_anios else mes


def sumar(venta_por_dia: dict[date, Decimal], rangos: list[tuple[date, date]]) -> list[Decimal | None]:
    valores = []
    for inicio, fin in rangos:
        dias = [v for dia, v in venta_por_dia.items() if inicio <= dia <= fin]
        valores.append(sum(dias, Decimal("0")) if dias else None)
    return valores


@dataclass(frozen=True)
class Grafica:
    titulo: str
    etiquetas: list[str]
    actual: list[Decimal | None]
    base: list[Decimal | None]
    nombre_actual: str
    nombre_base: str
    nota: str | None  # comparable branches / no comparison
    resaltar: int | None = None  # index of the bucket to highlight (the report's month in a trend)


def construir_grafica(periodo: Periodo, periodo_base: Periodo | None, comp: Comparacion, vs: str,
                      vs_corto: str) -> Grafica:
    """`vs` names the comparison in notes; `vs_corto` in the (space-limited) title."""
    gran = granularidad(periodo)
    rangos = cubetas(periodo, gran)
    etiquetas = [etiqueta(i, gran, periodo.dias, periodo.desde.year != periodo.hasta.year) for i, _ in rangos]
    actual = sumar(comp.actual.venta_por_dia, rangos)
    base: list[Decimal | None] = [None] * len(rangos)
    if comp.base is not None and periodo_base is not None:
        valores = sumar(comp.base.venta_por_dia, cubetas(periodo_base, gran))
        base = (valores + [None] * len(rangos))[:len(rangos)]  # match by position
    if all(v is None for v in base):
        notas = [f"Sin comparativo contra {vs}"]  # the footnotes say why
    elif comp.excluidas:
        notas = ["Sucursales comparables (sin " + ", ".join(comp.excluidas) + ")"]
    else:
        notas = []
    return Grafica(
        titulo=f"Venta neta {_POR[gran]} vs {vs_corto}",
        etiquetas=etiquetas,
        actual=actual,
        base=base,
        nombre_actual=periodo.etiqueta(),
        nombre_base=periodo_base.etiqueta() if periodo_base else "—",
        nota=". ".join(notas) + "." if notas else None,
    )


def _mes_corto(d: date) -> str:
    return f"{_MESES_ES[d.month - 1][:3]} {d.year % 100:02d}"


def _menos_un_anio(d: date) -> date:
    return d.replace(year=d.year - 1)


def meses_tendencia(periodo: Periodo, n: int = 12) -> list[date]:
    """First days of the `n` calendar months ending with the period's month."""
    meses, d = [], periodo.desde.replace(day=1)
    for _ in range(n):
        meses.append(d)
        d = (d - timedelta(days=1)).replace(day=1)
    return meses[::-1]


def grafica_por_dia(periodo: Periodo, actual: Metricas) -> Grafica:
    """Net sales per day of the period alone (no pairing with another period)."""
    rangos = cubetas(periodo, DIA)
    return Grafica(
        titulo="Venta neta por día",
        etiquetas=[etiqueta(i, DIA, periodo.dias, False) for i, _ in rangos],
        actual=sumar(actual.venta_por_dia, rangos),
        base=[None] * len(rangos),
        nombre_actual=periodo.etiqueta(),
        nombre_base="",
        nota=None,
    )


def grafica_tendencia_mensual(periodo: Periodo, mensual: dict[str, dict[date, tuple[Decimal, int]]]) -> Grafica:
    """12 calendar months ending with the period's month vs the same months
    one year earlier, every branch included. `mensual` comes from
    metricas.recolectar_mensual over both windows (24 months)."""
    meses = meses_tendencia(periodo)

    def total(mes):
        valores = [m[mes][0] for m in mensual.values() if mes in m]
        return sum(valores, Decimal("0")) if valores else None

    notas = []
    inicio = _menos_un_anio(meses[0])
    for nombre, por_mes in sorted(mensual.items()):
        con_datos = sorted(por_mes)
        if con_datos and con_datos[0] > inicio:
            notas.append(f"{nombre} desde {_mes_corto(con_datos[0])}")
    ultimo = periodo.desde.replace(day=1)
    dias_ultimo = [m[ultimo][1] for m in mensual.values() if ultimo in m]
    if dias_ultimo and max(dias_ultimo) < periodo.dias:
        notas.append(f"{_mes_corto(ultimo)} parcial ({max(dias_ultimo)} de {periodo.dias} días)")
    return Grafica(
        titulo="Venta neta mensual vs año anterior",
        etiquetas=[f"{_MESES_ES[m.month - 1][:3]}\n{m.year % 100:02d}" for m in meses],  # month over year
        actual=[total(m) for m in meses],
        base=[total(_menos_un_anio(m)) for m in meses],
        nombre_actual=f"{_mes_corto(meses[0])} – {_mes_corto(meses[-1])}",
        nombre_base=f"{_mes_corto(_menos_un_anio(meses[0]))} – {_mes_corto(_menos_un_anio(meses[-1]))}",
        nota=("Incluye sucursales nuevas: " + "; ".join(notas) + ".") if notas else None,
        resaltar=len(meses) - 1,
    )


def ventana_tendencia(periodo: Periodo) -> tuple[date, date]:
    """Dates to read for the month trend: 24 months ending with the period."""
    return _menos_un_anio(meses_tendencia(periodo)[0]), periodo.hasta


def construir_graficas(periodo: Periodo, actual: Metricas, anterior: Comparacion | Metricas | None,
                       anio_anterior: Comparacion | Metricas | None,
                       mensual: dict[str, dict[date, tuple[Decimal, int]]] | None = None) -> list[Grafica]:
    """The report's two charts. A month: its sales per day and the 12-month
    trend (needs `mensual`). Other periods: vs previous period and vs same
    period last year (for a year both are the same period: one chart)."""
    if periodo.tipo == TipoPeriodo.MES:
        if mensual is None:
            raise ValueError("a month report needs the monthly series (metricas.recolectar_mensual)")
        return [grafica_por_dia(periodo, actual), grafica_tendencia_mensual(periodo, mensual)]
    nombre = lectura.vs_anterior(periodo).split(" ", 1)[1]  # "semana anterior", "mes anterior", ...
    graficas = [construir_grafica(periodo, periodo.anterior(), como_comparacion(actual, anterior),
                                  lectura.vs_anterior(periodo), nombre)]
    if periodo.mismo_periodo_anio_anterior() != periodo.anterior():
        graficas.append(construir_grafica(periodo, periodo.mismo_periodo_anio_anterior(),
                                          como_comparacion(actual, anio_anterior), lectura.vs_anio(periodo),
                                          "año anterior"))
    return graficas
