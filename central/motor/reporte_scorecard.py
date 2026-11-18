"""Assembles the "Semáforos scorecard" for a branch selection (read-only).

The definition (KPIs, targets, lights, periods) lives in `scorecard.py`; this
module reads the sources for the three periods and hands them to it.
"""

from dataclasses import dataclass, field
from datetime import date

from . import scorecard as sc
from .fuentes import excel_kpis, wansoft
from .periodo import _MESES_ES, Periodo


def leer_ventas(cur_wansoft, sucursales: list, periodo: Periodo) -> list[sc.Ventas]:
    """Sales of each branch (`cuentas.Sucursal`, same order) in `periodo`."""
    nombres = [s.wansoft_ticket_nombre for s in sucursales]
    tickets = wansoft.ventas_tickets(cur_wansoft, nombres, periodo.desde, periodo.hasta)
    mix = wansoft.mix_alimentos_bebidas(cur_wansoft, [n for n in nombres if n in tickets], periodo.desde, periodo.hasta)
    resultado = []
    for nombre in nombres:
        t, m = tickets.get(nombre), mix.get(nombre, {})
        v = sc.Ventas(dias_esperados=periodo.dias)
        if t:
            v.dias, v.venta, v.tickets, v.venta_neta = t["dias"], t["venta"], t["tickets"], t["venta_neta"]
            v.personas, v.personas_restaurante = t["personas"], t["personas_restaurante"]
            v.alimentos, v.bebidas = m.get("Alimentos", sc.CERO), m.get("Bebidas", sc.CERO)
        resultado.append(v)
    return resultado


def leer_gastos(cur_wansoft, sucursales: list, periodo: Periodo, inicio_odoo: dict[str, date],
                dobles: list | None = None) -> list[sc.Gastos]:
    """Invoiced cost and expenses of each branch (same order) in `periodo`.
    Bread and tortillas: `scorecard.pan_tortillas` (Wansoft entries every day
    plus Odoo purchases from the day the branch buys in Odoo, `inicio_odoo` by
    short key); each (branch, department, day) present in both sources is
    appended to `dobles`."""
    d, h = periodo.desde, periodo.hasta
    claves = [s.wansoft_ticket_nombre for s in sucursales]
    facturas = wansoft.facturas_gasto(cur_wansoft, claves, d, h)
    entradas = wansoft.entradas_factura_por_dia(
        cur_wansoft, [s.wansoft_subsidiary_id for s in sucursales if s.wansoft_subsidiary_id is not None], d, h)
    con_odoo = [c for c in claves if c in inicio_odoo and inicio_odoo[c] <= h]
    compras = wansoft.compras_odoo_pan_tortillas_por_dia(cur_wansoft, con_odoo, d, h)
    resultado = []
    for s in sucursales:
        montos, ambas = sc.pan_tortillas(entradas.get(s.wansoft_subsidiary_id, {}),
                                         compras.get(s.wansoft_ticket_nombre, {}),
                                         inicio_odoo.get(s.wansoft_ticket_nombre))
        if dobles is not None:
            dobles.extend((s.nombre, depto, dia) for depto, dia in ambas)
        resultado.append(sc.gastos_de(facturas.get(s.wansoft_ticket_nombre, {}), montos))
    return resultado


def bloque_ventas(cur_wansoft, sucursales: list, hasta: date) -> tuple[sc.PeriodosScorecard, sc.BloqueVentas]:
    """The sales rows of the report ending `hasta`, for all of `sucursales`
    together (one branch = that branch's report)."""
    p = sc.periodos(hasta)
    leidos = [leer_ventas(cur_wansoft, sucursales, x) for x in (p.actual, p.mes_anterior, p.anio_anterior)]
    return p, sc.filas_ventas([s.nombre for s in sucursales], *leidos)


@dataclass
class ReporteScorecard:
    nombre: str  # branch name, or "Consolidado"
    sucursales: list
    periodos: sc.PeriodosScorecard
    filas: list[sc.Fila]  # every KPI, in the catalog's order
    meta_mes_anterior: list[str]
    sin_meta: list[str]
    sin_costo: list[str] = field(default_factory=list)
    sin_meta_gastos: list[str] = field(default_factory=list)
    pan_dobles: list = field(default_factory=list)  # (branch, department, day) in Wansoft AND Odoo, current period
    pan_parcial: list[str] = field(default_factory=list)  # branches whose Odoo bread/tortillas are partly unmapped
    desglose: list = field(default_factory=list)  # scorecard.Desglose of every cost and expense row
    sin_fuente: set = field(default_factory=lambda: set(sc.KPIS_SIN_FUENTE))  # KPIs shown grey "sin fuente"
    auditoria_meses: list = field(default_factory=list)  # months of the CGI audits shown
    auditoria_previos: list = field(default_factory=list)

    def leida(self, clave: str) -> bool:
        return clave in sc.KPIS_LEIDOS or (clave in sc.KPIS_AUDITORIA and clave not in self.sin_fuente)


@dataclass
class _Leido:
    """Everything read for a branch selection, aligned by branch."""
    periodos: sc.PeriodosScorecard
    ventas: list  # [current, previous month, last year], each a list of Ventas
    gastos: list  # [current, previous month], each a list of Gastos
    dobles: list  # (branch, department, day) of the current period
    auditorias: list | None = None  # CGI audit rows (None: the Excel is not available)


def _leer(cur_wansoft, sucursales: list, hasta: date) -> _Leido:
    p = sc.periodos(hasta)
    ventas = [leer_ventas(cur_wansoft, sucursales, x) for x in (p.actual, p.mes_anterior, p.anio_anterior)]
    inicio_odoo = wansoft.inicio_compras_odoo(cur_wansoft)
    dobles = []
    gastos = [leer_gastos(cur_wansoft, sucursales, p.actual, inicio_odoo, dobles),
              leer_gastos(cur_wansoft, sucursales, p.mes_anterior, inicio_odoo)]
    return _Leido(p, ventas, gastos, dobles, excel_kpis.auditorias_cgi())


def _construir(leido: _Leido, sucursales: list, indices: list[int], nombre: str) -> ReporteScorecard:
    """The scorecard of the branches `indices` of what was read (every KPI row;
    those without a source carry no value)."""
    de = lambda lista: [lista[i] for i in indices]
    elegidas = de(sucursales)
    nombres = [s.nombre for s in elegidas]
    ventas, gastos = [de(v) for v in leido.ventas], [de(g) for g in leido.gastos]
    bv = sc.filas_ventas(nombres, *ventas)
    bg = sc.filas_gastos(nombres, ventas[0], ventas[1], gastos[0], gastos[1])
    sin_fuente = set(sc.KPIS_SIN_FUENTE)
    ba = None
    if leido.auditorias is not None:
        ba = sc.filas_auditoria([s.clave for s in elegidas], leido.auditorias, leido.periodos.actual.hasta)
        sin_fuente -= set(sc.KPIS_AUDITORIA)
    leidas = {f.kpi.clave: f for f in bv.filas + bg.filas + (ba.filas if ba else [])}
    filas = [leidas.get(k.clave) or sc.Fila(k, None, None, k.meta, None, None) for k in sc.KPIS]
    parcial = [s.nombre for s in elegidas if s.wansoft_ticket_nombre in sc.PAN_TORTILLAS_PARCIAL]
    dobles = [d for d in leido.dobles if d[0] in nombres]
    return ReporteScorecard(nombre, elegidas, leido.periodos, filas, bv.meta_mes_anterior, bv.sin_meta, bg.sin_costo,
                            bg.sin_meta, dobles, parcial, sc.desglose(bg.detalle, bg.proveedores), sin_fuente,
                            ba.meses if ba else [], ba.meses_previos if ba else [])


def armar(cur_wansoft, sucursales: list, hasta: date, consolidado: bool = False) -> ReporteScorecard:
    """The scorecard of `sucursales` together (one branch = that branch's report)."""
    nombre = "Consolidado" if consolidado else sucursales[0].nombre
    return _construir(_leer(cur_wansoft, sucursales, hasta), sucursales, list(range(len(sucursales))), nombre)


def armar_varios(sucursales: list, periodo, consolidado: bool) -> list[ReporteScorecard]:
    """For the web and the automations: the report whose cut is the LAST day of
    `periodo` (a week -> the month to date up to its Sunday; a month -> that
    month), consolidated or one per branch. Reads once for every branch."""
    from .fuentes.conexiones import abrir_wansoft
    with abrir_wansoft() as cur:
        leido = _leer(cur, sucursales, periodo.hasta)
    if consolidado:
        return [_construir(leido, sucursales, list(range(len(sucursales))), "Consolidado")]
    return [_construir(leido, sucursales, [i], s.nombre) for i, s in enumerate(sucursales)]


def nombre_base(reportes: list[ReporteScorecard]) -> str:
    r = reportes[0]
    quien = r.nombre if len(reportes) == 1 else f"{len(reportes)}_sucursales"
    p = r.periodos.actual
    return "_".join(["Semaforos_Scorecard", *quien.split(), f"{p.desde:%Y%m%d}_{p.hasta:%Y%m%d}"])


def notas(r: ReporteScorecard) -> list[str]:
    """The report's notes (PDF and Excel say the same)."""
    resultado = [
        "Ventas y cheque con IVA, de las cuentas de Wansoft. Cheque = venta / personas de todos los canales; "
        "ticket = venta / cuentas; clientes = personas de las órdenes de restaurante (sin delivery ni para llevar); "
        "mix = venta de bebidas / venta de alimentos y bebidas.",
        "Costo de venta y gastos: facturas de proveedor de Wansoft y Odoo, por fecha de factura, sin IVA. Costo de "
        "venta = facturas de Costo Operativo / venta neta (sin IVA) de las mismas sucursales. Pan y tortillas: "
        "entradas de inventario por factura de Wansoft, más las compras en Odoo de las sucursales que compran en "
        "Odoo. Las facturas de los últimos días pueden no estar capturadas todavía.",
        "Sin fuente: KPIs cuya fuente (Zenput, Excel de SharePoint, Google) aún no lee la Central de Reportes.",
    ]
    if r.auditoria_meses:
        def mes(d):
            return f"{_MESES_ES[d.month - 1]} {d.year}"
        texto = ("Auditoría CGI y estándares visuales de marca: última auditoría hasta la fecha del reporte, "
                 + ", ".join(mes(d) for d in r.auditoria_meses))
        if r.auditoria_previos:
            texto += " (columna Mes anterior: la auditoría previa, " + ", ".join(mes(d) for d in r.auditoria_previos) + ")"
        resultado.append(texto + "; del Excel de resultados de auditoría CGI, capturado a mano.")
    if r.nombre == "Consolidado":
        resultado.append("Consolidado: el semáforo de ventas, cheque, ticket y clientes compara solo las sucursales "
                         "con meta (año anterior o, si son nuevas, mes anterior); el de los gastos, las que operaron "
                         "el mes anterior.")
    if r.sin_costo:
        resultado.append("Sin facturas de costo en el periodo (fuera del costo de venta): " + ", ".join(r.sin_costo)
                         + ".")
    if r.pan_parcial:
        resultado.append("Pan y tortillas parciales: " + ", ".join(r.pan_parcial) + " compran en Odoo productos que "
                         "el catálogo aún no clasifica como Pan o Tortillas (por ejemplo Bolillo, Tortilla de Harina).")
    if r.pan_dobles:
        dias = sorted({f"{dia:%d/%m}" for _, _, dia in r.pan_dobles})
        resultado.append("Revisar: pan o tortillas capturados en Wansoft y en Odoo el mismo día (pueden contarse dos "
                         "veces): " + ", ".join(sorted({n for n, _, _ in r.pan_dobles})) + " (" + ", ".join(dias)
                         + ").")
    return resultado
