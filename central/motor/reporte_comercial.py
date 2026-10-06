"""The commercial report assembled for a branch selection and a period.

One place builds everything a commercial report shows -- Lectura, indicators
table, charts and footnotes -- so the console check (`probar_reporte`), the
PDF, the web screen and the automations all show exactly the same thing.

`armar` reads the sources (read-only) once for the whole selection and
returns one `ReporteComercial` per branch, or a single consolidated one.
"""

import logging
from dataclasses import dataclass, field

from . import metricas
from .fuentes import conexiones, odoo
from .graficas import Grafica, construir_graficas, ventana_tendencia
from .lectura import Lectura, construir_lectura
from .metricas import Comparacion, Metricas
from .notas import notas_cobertura, notas_reglas
from .periodo import Periodo, TipoPeriodo
from .tabla_comercial import Fila, construir_tabla

TITULO = "Reporte comercial"

log = logging.getLogger(__name__)

# Budget rows of the indicators table (left out of a consolidated report without a complete budget).
FILAS_PRESUPUESTO = {"costo_ventas_ppto", "costo_ventas_ejercido"}
# Invoiced cost rows (left out of a consolidated report unless every branch has invoices).
FILAS_COSTO_FACTURADO = {"costo_ventas_real", "costo_ventas_pct"}


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
    incluir_costos: bool = True  # option of the generation screen / automation (default on)

    @property
    def notas(self) -> list[str]:
        return self.cobertura + self.reglas


def _uno(nombre, sucursales, periodo, actual, anterior, anio_anterior, diario, incluir_costos=True) -> ReporteComercial:
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
        cobertura=notas_cobertura(periodo, actual, anterior, anio_anterior, incluir_costos),
        reglas=notas_reglas(periodo, incluir_costos),
        incluir_costos=incluir_costos,
    )


def _abrir_odoo():
    """Odoo client for the invoiced sales behind the estimated cost; None when
    Odoo cannot be reached (the report still comes out, with a note)."""
    try:
        return odoo.abrir_odoo()
    except Exception:  # network / credentials: degrade, never break the report
        log.exception("Odoo no disponible para el costo estimado")
        return None


def armar(sucursales: list, periodo: Periodo, consolidado: bool, incluir_costos: bool = True) -> list[ReporteComercial]:
    """Read the sources and build the report: one per branch, or one
    consolidated for the whole selection (as the report's `alcance` says).
    Without `incluir_costos` the report carries no cost at all (not read,
    not shown, no cost rules)."""
    anterior = periodo.anterior()
    anio_ant = periodo.mismo_periodo_anio_anterior()
    cli = _abrir_odoo() if incluir_costos and any(s.odoo_company_id for s in sucursales) else None
    with conexiones.abrir_wansoft() as cw, conexiones.abrir_presupuestos() as cp:
        def leer(p):
            return metricas.recolectar(cw, cp, sucursales, p, odoo=cli, incluir_costos=incluir_costos)
        ma = leer(periodo)
        mp = leer(anterior)
        if anio_ant == anterior:  # a year: both comparisons are the same period
            my = mp
        else:
            my = leer(anio_ant) if anio_ant else None
        diario = None
        if periodo.tipo == TipoPeriodo.MES:  # the month trend chart needs 24 months of closings
            diario = metricas.recolectar_diario(cw, sucursales, *ventana_tendencia(periodo))

    nombres = [s.nombre for s in sucursales]
    if consolidado:
        actual = metricas.consolidar(ma, periodo)
        comp_ant = metricas.comparables(nombres, ma, mp, periodo, anterior)
        comp_anio = metricas.comparables(nombres, ma, my, periodo, anio_ant)
        # Owner, 2026-10-05: the budget is shown in the consolidated only when every
        # branch has one; a partial budget would stain the whole report.
        # Each period on its own: a period with a budget / invoiced cost for only
        # some of its branches loses it (the invoiced cost: owner, same day).
        presupuesto_incompleto = facturado_incompleto = False
        for m in (actual, comp_ant.actual, comp_ant.base, comp_anio.actual, comp_anio.base):
            if m is not None and 0 < m.n_con_presupuesto < m.n_sucursales:
                metricas.sin_presupuesto(m)
                presupuesto_incompleto = True
            if m is not None and 0 < m.n_con_costo_ventas < m.n_sucursales:
                metricas.sin_costo_facturado(m)
                facturado_incompleto = True
        r = _uno("Consolidado", nombres, periodo, actual, comp_ant, comp_anio, diario, incluir_costos)
        fuera = (FILAS_PRESUPUESTO if actual.costo_ventas_ppto is None else set()) |             (FILAS_COSTO_FACTURADO if actual.costo_ventas_real is None else set())
        r.filas = [f for f in r.filas if f.indicador.clave not in fuera]  # no rows of dashes
        r.por_sucursal = [(n, ma[i], mp[i]) for i, n in enumerate(nombres)]
        sin_considerar = [s.nombre for s in sucursales if not getattr(s, "considerar_costo", True)]
        if incluir_costos and sin_considerar:
            r.cobertura.append(f"No se considera el costo de {', '.join(sin_considerar)} (así está configurada la "
                               "sucursal): sus ventas quedan fuera de los porcentajes de costo.")
        if incluir_costos and presupuesto_incompleto:
            r.cobertura.append("El presupuesto de Costo de Ventas no se muestra en el consolidado: no todas las "
                               "sucursales lo tienen capturado (se ve en el reporte de cada sucursal).")
        if incluir_costos and facturado_incompleto:
            r.cobertura.append("El costo facturado (Presupuestos AP) no se muestra en el consolidado: no todas las "
                               "sucursales tienen facturas registradas (se ve en el reporte de cada sucursal).")
        sin_costo = [n for (n, m, _), s in zip(r.por_sucursal, sucursales)
                     if m.costo_total is None and m.dias_con_cierre and getattr(s, "considerar_costo", True)]
        if incluir_costos and sin_costo and periodo.tipo != TipoPeriodo.RANGO:
            r.cobertura.append("Costo total sin dato en el reporte de costos (fuera de su porcentaje): "
                               + ", ".join(sin_costo) + ".")
        estimadas = [n + (f" ({m.pct_facturado_odoo * 100:.0f}% facturado en Odoo)" if m.costo_estimado_odoo
                          and m.pct_facturado_odoo is not None else f" (${m.pendiente_wansoft:,.0f} pendiente en Wansoft)")
                     for n, m, _ in r.por_sucursal if m.costo_total_estimado]
        if estimadas:
            r.cobertura.append("Sucursales con costo total estimado: " + ", ".join(estimadas) + ".")
        return [r]
    return [
        _uno(n, [n], periodo, ma[i],
             metricas.comparables([n], [ma[i]], [mp[i]], periodo, anterior),
             metricas.comparables([n], [ma[i]], [my[i]] if my else None, periodo, anio_ant),
             {n: diario[n]} if diario is not None else None,
             incluir_costos and getattr(sucursales[i], "considerar_costo", True))  # Metepec: no cost section
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
