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
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from . import lectura
from .metricas import Comparacion, Metricas, como_comparacion
from .periodo import _MESES_ES, Periodo

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


def construir_graficas(periodo: Periodo, actual: Metricas, anterior: Comparacion | Metricas | None,
                       anio_anterior: Comparacion | Metricas | None) -> list[Grafica]:
    """The report's two charts: vs previous period and vs same period last
    year. For a year both are the same period, so only one chart."""
    nombre = lectura.vs_anterior(periodo).split(" ", 1)[1]  # "semana anterior", "mes anterior", ...
    graficas = [construir_grafica(periodo, periodo.anterior(), como_comparacion(actual, anterior),
                                  lectura.vs_anterior(periodo), nombre)]
    if periodo.mismo_periodo_anio_anterior() != periodo.anterior():
        graficas.append(construir_grafica(periodo, periodo.mismo_periodo_anio_anterior(),
                                          como_comparacion(actual, anio_anterior), lectura.vs_anio(periodo),
                                          "año anterior"))
    return graficas
