"""The commercial report assembled for a branch selection and a period.

One place builds everything a commercial report shows -- Lectura, indicators
table, charts and footnotes -- so the console check (`probar_reporte`), the
PDF, the web screen and the automations all show exactly the same thing.

`armar` reads the sources (read-only) once for the whole selection and
returns one `ReporteComercial` per branch, or a single consolidated one.
"""

from dataclasses import dataclass, field

from . import metricas
from .fuentes import conexiones
from .graficas import Grafica, construir_graficas, ventana_tendencia
from .lectura import Lectura, construir_lectura
from .metricas import Comparacion, Metricas
from .notas import notas_cobertura, notas_reglas
from .periodo import Periodo, TipoPeriodo
from .tabla_comercial import Fila, construir_tabla

TITULO = "Reporte comercial"


@dataclass
class ReporteComercial:
    nombre: str  # branch name, or "Consolidado"
    sucursales: list[str]
    periodo: Periodo
    actual: Metricas
    anterior: Comparacion
    anio_anterior: Comparacion
    lectura: Lectura
    filas: list[Fila]
    graficas: list[Grafica]
    cobertura: list[str]  # footnotes about this period's data
    reglas: list[str]  # the rules and thresholds the report applies
    # Consolidated only: each branch's own period and previous period, for the detail page.
    por_sucursal: list[tuple[str, Metricas, Metricas | None]] = field(default_factory=list)

    @property
    def notas(self) -> list[str]:
        return self.cobertura + self.reglas


def _uno(nombre, sucursales, periodo, actual, anterior, anio_anterior, diario) -> ReporteComercial:
    return ReporteComercial(
        nombre=nombre,
        sucursales=sucursales,
        periodo=periodo,
        actual=actual,
        anterior=anterior,
        anio_anterior=anio_anterior,
        lectura=construir_lectura(periodo, actual, anterior, anio_anterior),
        filas=construir_tabla(actual, anterior, anio_anterior),
        graficas=construir_graficas(periodo, actual, anterior, anio_anterior, diario),
        cobertura=notas_cobertura(periodo, actual, anterior, anio_anterior),
        reglas=notas_reglas(periodo),
    )


def armar(sucursales: list, periodo: Periodo, consolidado: bool) -> list[ReporteComercial]:
    """Read the sources and build the report: one per branch, or one
    consolidated for the whole selection (as the report's `alcance` says)."""
    anterior = periodo.anterior()
    anio_ant = periodo.mismo_periodo_anio_anterior()
    with conexiones.abrir_wansoft() as cw, conexiones.abrir_presupuestos() as cp:
        ma = metricas.recolectar(cw, cp, sucursales, periodo)
        mp = metricas.recolectar(cw, cp, sucursales, anterior)
        if anio_ant == anterior:  # a year: both comparisons are the same period
            my = mp
        else:
            my = metricas.recolectar(cw, cp, sucursales, anio_ant) if anio_ant else None
        diario = None
        if periodo.tipo == TipoPeriodo.MES:  # the month trend chart needs 24 months of closings
            diario = metricas.recolectar_diario(cw, sucursales, *ventana_tendencia(periodo))

    nombres = [s.nombre for s in sucursales]
    if consolidado:
        r = _uno("Consolidado", nombres, periodo, metricas.consolidar(ma, periodo),
                 metricas.comparables(nombres, ma, mp, periodo, anterior),
                 metricas.comparables(nombres, ma, my, periodo, anio_ant), diario)
        r.por_sucursal = [(n, ma[i], mp[i]) for i, n in enumerate(nombres)]
        return [r]
    return [
        _uno(n, [n], periodo, ma[i],
             metricas.comparables([n], [ma[i]], [mp[i]], periodo, anterior),
             metricas.comparables([n], [ma[i]], [my[i]] if my else None, periodo, anio_ant),
             {n: diario[n]} if diario is not None else None)
        for i, n in enumerate(nombres)
    ]


def filas_visibles(filas: list[Fila]) -> list[Fila]:
    """A section with no value at all in the period (e.g. Costo de Ventas for a
    branch that is not in Presupuestos AP) is left out of every output."""
    vacias = {f.indicador.seccion for f in filas} - {f.indicador.seccion for f in filas if f.actual is not None}
    return [f for f in filas if f.indicador.seccion not in vacias]


def nombre_base(reportes: list[ReporteComercial]) -> str:
    """File name without extension: the branch (or "Consolidado"), or how many
    branches when one file holds several; then the period."""
    quien = reportes[0].nombre if len(reportes) == 1 else f"{len(reportes)} sucursales"
    limpio = "".join(ch if ch.isalnum() else "_" for ch in f"Reporte_Comercial_{quien}_{reportes[0].periodo.etiqueta()}")
    return "_".join(p for p in limpio.split("_") if p)
