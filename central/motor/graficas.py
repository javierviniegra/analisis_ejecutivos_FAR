"""Chart data of the commercial report (pure: no I/O, no drawing).

Both charts compare gross sales (con IVA: the owner measures the impact of
sales on gross) of the period, bucket by bucket, against a comparison
period: the previous period, and the same period last year. Each chart uses a `Comparacion`, so it follows the comparable-branches
rule like the table (branches left out are named in the chart's note).

Bucket size follows the period length (owner, 2026-09-24): one bar per day
up to 31 days, per 7-day block from 32 to 92 days, per calendar month
beyond. Buckets are matched to the comparison period by position (day 1
with day 1, block 1 with block 1). A bucket with no cash closing at all has
no value (None), never a zero bar.

Month reports are different (owner, 2026-09-24): day-by-day pairing of two
different months mixes in the day-of-week effect (Aug 1 2026 was a
Saturday, Aug 1 2025 a Friday), and a month should be measured as a
calendar month. So a month gets (1) its gross sales per day alone, and (2) a
12-month trend by calendar month vs the same months of the previous year.
The trend includes every branch (new branches show as empty/lower bars in
the months without data; the note says since when each has data), leaves
out source gaps, and compares a month in progress month-to-date (see
`grafica_tendencia_mensual`), while the table and the Lectura keep the
comparable-branches rule.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from . import lectura
from .comparativos import cobertura_fiable
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
        titulo=f"Venta bruta {_POR[gran]} vs {vs_corto}",
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
    """Gross sales per day of the period alone (no pairing with another period)."""
    rangos = cubetas(periodo, DIA)
    return Grafica(
        titulo="Venta bruta por día",
        etiquetas=[etiqueta(i, DIA, periodo.dias, False) for i, _ in rangos],
        actual=sumar(actual.venta_por_dia, rangos),
        base=[None] * len(rangos),
        nombre_actual=periodo.etiqueta(),
        nombre_base="",
        nota=None,
    )


def _dias_del_mes(mes: date) -> int:
    return ((mes.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day


def grafica_tendencia_mensual(periodo: Periodo, diario: dict[str, dict[date, Decimal]]) -> Grafica:
    """12 calendar months ending with the period's month vs the same months
    one year earlier. `diario` (metricas.recolectar_diario over the 24-month
    `ventana_tendencia`) is gross sales per branch and day.

    Rules (owner, 2026-09-24):
    - New branches are included: nothing before their first month with data,
      and their opening month counts as it is.
    - A branch-month with data on less than UMBRAL_COBERTURA_FIABLE of its
      days after the branch opened is a gap in the source (e.g. Nov-Dec 2024
      in Wansoft): that branch is left out of BOTH years of that month.
    - A month in progress is compared month-to-date: days 1..N of both years.
    """
    meses = meses_tendencia(periodo)
    ultimo = meses[-1]
    dias_ultimo = [d.day for por_dia in diario.values() for d in por_dia if d.replace(day=1) == ultimo]
    corte = max(dias_ultimo) if dias_ultimo and max(dias_ultimo) < periodo.dias else None

    def dentro(d: date, mes: date) -> bool:  # month-to-date cut applies to the last pair only
        return corte is None or mes != ultimo or d.day <= corte

    inicio = {n: min(p).replace(day=1) for n, p in diario.items() if p}

    def total_y_dias(nombre: str, mes: date, mes_par: date) -> tuple[Decimal, int]:
        valores = [v for d, v in diario[nombre].items() if d.replace(day=1) == mes and dentro(d, mes_par)]
        return sum(valores, Decimal("0")), len(valores)

    def hueco(nombre: str, mes: date, mes_par: date) -> bool:
        if nombre not in inicio or mes <= inicio[nombre]:
            return False  # not open yet, or its opening month
        _, dias = total_y_dias(nombre, mes, mes_par)
        esperados = corte if (corte and mes_par == ultimo) else _dias_del_mes(mes)
        return not cobertura_fiable(dias, esperados)

    actual, base, con_huecos = [], [], []
    for mes in meses:
        previo = _menos_un_anio(mes)
        fuera = [n for n in diario if hueco(n, mes, mes) or hueco(n, previo, mes)]
        if fuera:
            con_huecos.append(f"{_mes_corto(mes)} ({len(fuera)})")
        suma_a = [total_y_dias(n, mes, mes) for n in diario if n not in fuera]
        suma_b = [total_y_dias(n, previo, mes) for n in diario if n not in fuera]
        actual.append(sum((t for t, d in suma_a if d), Decimal("0")) if any(d for _, d in suma_a) else None)
        base.append(sum((t for t, d in suma_b if d), Decimal("0")) if any(d for _, d in suma_b) else None)

    notas = [f"{n} desde {_mes_corto(inicio[n])}" for n in sorted(inicio) if inicio[n] > _menos_un_anio(meses[0])]
    partes = []
    if notas:
        partes.append("Incluye sucursales nuevas: " + "; ".join(notas))
    if con_huecos and len(diario) == 1:
        partes.append("Meses sin comparar por datos incompletos en Wansoft: "
                      + ", ".join(h.split(" (")[0] for h in con_huecos))
    elif con_huecos:
        partes.append("Meses comparados sin las sucursales con datos incompletos en Wansoft (en ambos años): "
                      + ", ".join(con_huecos))
    if corte:
        partes.append(f"{_mes_corto(ultimo)} a la fecha: días 1 al {corte} de ambos años")
    return Grafica(
        titulo="Venta bruta mensual vs año anterior",
        etiquetas=[f"{_MESES_ES[m.month - 1][:3]}\n{m.year % 100:02d}" for m in meses],  # month over year
        actual=actual,
        base=base,
        nombre_actual=f"{_mes_corto(meses[0])} – {_mes_corto(meses[-1])}",
        nombre_base=f"{_mes_corto(_menos_un_anio(meses[0]))} – {_mes_corto(_menos_un_anio(meses[-1]))}",
        nota=". ".join(partes) + "." if partes else None,
        resaltar=len(meses) - 1,
    )


def ventana_tendencia(periodo: Periodo) -> tuple[date, date]:
    """Dates to read for the month trend: 24 months ending with the period."""
    return _menos_un_anio(meses_tendencia(periodo)[0]), periodo.hasta


def construir_graficas(periodo: Periodo, actual: Metricas, anterior: Comparacion | Metricas | None,
                       anio_anterior: Comparacion | Metricas | None,
                       diario: dict[str, dict[date, Decimal]] | None = None) -> list[Grafica]:
    """The report's two charts. A month: its sales per day and the 12-month
    trend (needs `diario`). Other periods: vs previous period and vs same
    period last year (for a year both are the same period: one chart)."""
    if periodo.tipo == TipoPeriodo.MES:
        if diario is None:
            raise ValueError("a month report needs the daily series (metricas.recolectar_diario)")
        return [grafica_por_dia(periodo, actual), grafica_tendencia_mensual(periodo, diario)]
    nombre = lectura.vs_anterior(periodo).split(" ", 1)[1]  # "semana anterior", "mes anterior", ...
    graficas = [construir_grafica(periodo, periodo.anterior(), como_comparacion(actual, anterior),
                                  lectura.vs_anterior(periodo), nombre)]
    if periodo.mismo_periodo_anio_anterior() != periodo.anterior():
        graficas.append(construir_grafica(periodo, periodo.mismo_periodo_anio_anterior(),
                                          como_comparacion(actual, anio_anterior), lectura.vs_anio(periodo),
                                          "año anterior"))
    return graficas
