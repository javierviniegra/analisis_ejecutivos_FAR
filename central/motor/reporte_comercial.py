"""The commercial report assembled for a branch selection and a period.

One place builds everything a commercial report shows -- Lectura, indicators
table, charts and footnotes -- so the console check (`probar_reporte`), the
PDF, the web screen and the automations all show exactly the same thing.

`armar` reads the sources (read-only) once for the whole selection and
returns one `ReporteComercial` per branch, or a single consolidated one.
"""

import logging
from dataclasses import dataclass, field

from . import composicion, inflacion, metricas, tablajeria
from .fuentes import conexiones, odoo, wansoft
from .graficas import Grafica, construir_graficas, ventana_tendencia
from .lectura import Lectura, construir_lectura
from .metricas import Comparacion, Metricas, como_comparacion
from .notas import notas_cobertura, notas_reglas
from .periodo import Periodo, TipoPeriodo
from .tabla_comercial import Fila, construir_tabla, filas_por_formato

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
    # Consolidated only: each branch's own period and the same period last year, for the detail page.
    por_sucursal: list[tuple[str, Metricas, Metricas | None]] = field(default_factory=list)
    incluir_costos: bool = True  # option of the generation screen / automation (default on)
    # Owner, 2026-10-14: the commercial report compares against the same period last
    # year (table, charts, detail); the previous period only in the Lectura.
    solo_anio: bool = True
    # Owner, 2026-10-20: butchery shrinkage vs every branch and last year (None: could not be read).
    tablajeria: "tablajeria.Tablajeria | None" = None
    # Owner, 2026-10-20: sales by time band, payment method, platform, weekday and hour.
    composicion: "composicion.Composicion | None" = None
    # Periods of a month or more (owner, 2026-10-19/20): growth against inflation, of its published months.
    addendum: "inflacion.Addendum | None" = None

    @property
    def notas(self) -> list[str]:
        return self.cobertura + self.reglas

    @property
    def aviso_comparables(self) -> str | None:
        """Consolidated only (owner, 2026-10-20): a visible notice at the top that
        every comparison against last year uses comparable branches only."""
        if self.nombre != "Consolidado" or not self.solo_anio or self.anio_anterior.base is None:
            return None
        texto = ("Comparativos contra el año anterior solo con sucursales comparables (las que operaron completo "
                 "ambos periodos).")
        fuera = self.anio_anterior.excluidas
        if not fuera:
            return texto + " Este periodo todas las sucursales son comparables."
        return texto + f" Fuera de la comparación: {', '.join(fuera)}."


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
        composicion=_composicion(actual, anio_anterior),
    )


def _composicion(actual, anio_anterior):
    try:
        return composicion.construir(actual, como_comparacion(actual, anio_anterior), "Año anterior")
    except Exception:  # never break the report over its composition page
        log.exception("Composición de la venta no disponible")
        return None


# Format of each branch (cuentas.Sucursal.formato) as shown in the report, in this order.
FORMATOS = [("fonda", "Fondas"), ("taqueria", "Taquerías"), ("esquina", "La Esquina")]


def _grupos_formato(sucursales, ma, mp, my, periodo, anterior, anio_ant):
    """Per format present in the selection: (label, current, vs previous, vs
    last year); empty when the selection has a single format (nothing to split)."""
    grupos = []
    for clave, etiqueta in FORMATOS:
        idx = [i for i, s in enumerate(sucursales) if getattr(s, "formato", "fonda") == clave]
        if not idx:
            continue
        nombres = [sucursales[i].nombre for i in idx]
        actuales = [ma[i] for i in idx]
        grupos.append((etiqueta, metricas.consolidar(actuales, periodo),
                       metricas.comparables(nombres, actuales, [mp[i] for i in idx], periodo, anterior),
                       metricas.comparables(nombres, actuales, [my[i] for i in idx] if my else None, periodo, anio_ant)))
    return grupos if len(grupos) > 1 else []


def _con_formatos(filas: list[Fila], por_formato: list[Fila]) -> list[Fila]:
    """The format rows right after the Ventas section."""
    if not por_formato:
        return filas
    ultima = max(i for i, f in enumerate(filas) if f.indicador.seccion == "Ventas")
    return filas[:ultima + 1] + por_formato + filas[ultima + 1:]


def _todas_las_sucursales(sucursales) -> list:
    """Every active branch: the butchery benchmark is against all of them,
    whatever the selection. Falls back to the selection outside Django."""
    try:
        from cuentas.models import Sucursal
        return list(Sucursal.objects.filter(activa=True, wansoft_subsidiary_id__isnull=False))
    except Exception:
        return list(sucursales)


def _leer_tablajeria(cw, sucursales, periodo, anio_ant):
    """The butchery pieces of EVERY branch for the period and last year, read
    once: (actual, anio, names). None (and a log line) if they cannot be read,
    so the butchery section never breaks the report."""
    try:
        todas = list(_todas_las_sucursales(sucursales)) + list(sucursales)
        nombres = {s.wansoft_subsidiary_id: s.nombre for s in todas if getattr(s, "wansoft_subsidiary_id", None)}
        ids = sorted(nombres)
        actual = wansoft.piezas_tablajeria(cw, ids, periodo.desde, periodo.hasta)
        anio = wansoft.piezas_tablajeria(cw, ids, anio_ant.desde, anio_ant.hasta) if anio_ant else []
        return actual, anio, nombres
    except Exception:
        log.exception("Tablajería no disponible")
        return None


def _tablajeria(leida, sucursales, consolidado: bool, incluir_costos: bool):
    """The butchery section of one report (a branch, or the consolidated selection)."""
    if leida is None:
        return None
    actual, anio, nombres = leida
    seleccion = [s.wansoft_subsidiary_id for s in sucursales if getattr(s, "wansoft_subsidiary_id", None)]
    return tablajeria.construir(actual, anio, nombres, seleccion, consolidado, incluir_costos)


def _serie_inflacion():
    """The stored INPC (fetching missing months from Banxico); None outside Django or on failure."""
    try:
        from django.conf import settings
        return inflacion.serie(getattr(settings, "BANXICO_TOKEN", ""))
    except Exception:
        log.exception("INPC no disponible")
        return None


def _addendum(mes, comp, infl, periodo, por_sucursal=None):
    try:
        return inflacion.construir(mes, comp, infl, periodo, por_sucursal)
    except Exception:  # never break the report over its addendum
        log.exception("Addendum de inflación no disponible")
        return None


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
    inpc = _serie_inflacion() if periodo.tipo in inflacion.TIPOS else None
    mes_infl = inflacion.periodo_analizado(periodo, inpc) if inpc else None
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
        carne = _leer_tablajeria(cw, sucursales, periodo, anio_ant)
        # The addendum's month: the report's own (reuse what was read) or an earlier one (read it and its year).
        mi = my_i = None
        if mes_infl is not None and mes_infl == periodo:
            mi, my_i = ma, my
        elif mes_infl is not None:
            try:
                mi, my_i = leer(mes_infl), leer(mes_infl.mismo_periodo_anio_anterior())
            except Exception:
                log.exception("No se pudo leer el mes del addendum de inflación")
                mes_infl = None
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
        r.filas = _con_formatos(r.filas, filas_por_formato(
            _grupos_formato(sucursales, ma, mp, my, periodo, anterior, anio_ant)))
        r.por_sucursal = [(n, ma[i], my[i] if my else None) for i, n in enumerate(nombres)]  # base: last year
        r.tablajeria = _tablajeria(carne, sucursales, True, incluir_costos)
        if mes_infl is not None:
            infl = inflacion.del_periodo(inpc, mes_infl)
            ly_i = mes_infl.mismo_periodo_anio_anterior()
            cada = [(n, mi[i], metricas.comparables([n], [mi[i]], [my_i[i]], mes_infl, ly_i).base)
                    for i, n in enumerate(nombres)]
            r.addendum = _addendum(mes_infl, metricas.comparables(nombres, mi, my_i, mes_infl, ly_i), infl, periodo,
                                   cada)
        if r.composicion is not None:
            r.composicion.tardes = composicion.tardes(r.por_sucursal, mp)
            r.composicion.vs_anterior = {TipoPeriodo.MES: "mes ant.", TipoPeriodo.SEMANA: "sem. ant."}.get(
                periodo.tipo, "periodo ant.")
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
    reportes = [
        _uno(n, [n], periodo, ma[i],
             metricas.comparables([n], [ma[i]], [mp[i]], periodo, anterior),
             metricas.comparables([n], [ma[i]], [my[i]] if my else None, periodo, anio_ant),
             {n: diario[n]} if diario is not None else None,
             incluir_costos and getattr(sucursales[i], "considerar_costo", True))  # Metepec: no cost section
        for i, n in enumerate(nombres)
    ]
    vs = {TipoPeriodo.MES: "mes ant.", TipoPeriodo.SEMANA: "sem. ant."}.get(periodo.tipo, "periodo ant.")
    for i, (r, s) in enumerate(zip(reportes, sucursales)):  # one butchery section per branch, from the same reading
        r.tablajeria = _tablajeria(carne, [s], False, r.incluir_costos)
        if mes_infl is not None:
            ly_i = mes_infl.mismo_periodo_anio_anterior()
            r.addendum = _addendum(mes_infl, metricas.comparables([nombres[i]], [mi[i]], [my_i[i]], mes_infl, ly_i),
                                   inflacion.del_periodo(inpc, mes_infl), periodo)
        if r.composicion is not None:
            r.composicion.vs_anterior = vs
            r.composicion.dias = composicion.dias_horario(ma[i], r.anterior.base, r.anio_anterior.base)
    return reportes


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
