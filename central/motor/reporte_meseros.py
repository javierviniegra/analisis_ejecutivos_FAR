"""The waiters' report (reporte de meseros), built like the commercial one
(owner, 2026-10-13): same periods, per branch or consolidated, comparisons
against the previous period and the same period last year with the same
arrow / s/c / s/cf rules, a rule-based Lectura, two charts, notes, a detail
page and the rules written in the report.

What it adds to the commercial: the staff (waiters with at least one
account), sales per waiter and per day worked, tips, table time, courtesies
and the share of drinks per waiter, and a ranking of the waiters.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from . import meseros as datos_meseros
from .comparativos import UMBRAL_COBERTURA_FIABLE, UMBRAL_IGUAL, cobertura_fiable, variacion
from .fuentes import conexiones, wansoft
from .fuentes.wansoft import HORA_CORTE_DIA, MINUTOS_MESA_MAX, MINUTOS_MESA_MIN
from .graficas import Grafica
from .lectura import AVISO, NEGATIVO, NEUTRO, POSITIVO, Lectura, Observacion, titulo, vs_anio, vs_anterior
from .meseros import DatosMeseros, Mesero, nombre_corto
from .metricas import Comparacion
from .periodo import Periodo, TipoPeriodo
from .tabla_comercial import DECIMAL, ENTERO, MONEDA, PORCENTAJE, Fila, Indicador, _columna, _valor

TITULO = "Reporte de meseros"

# A waiter enters the best/lowest-check sentences only with at least this many
# accounts in the period (a substitute with 2 tables would distort them).
MIN_CUENTAS_LECTURA = 10
# Check below this share of the branch average: red in the detail and named in the Lectura.
UMBRAL_CHEQUE_BAJO = Decimal("0.90")
# The top 3 waiters' share of sales that the Lectura reports as concentration.
UMBRAL_CONCENTRACION = Decimal("0.50")
# Waiters drawn in the charts (largest sales first).
MAX_MESEROS_GRAFICA = 12

NARANJA, VERDE, ROJO = "naranja", "verde", "rojo"


def _t(m: DatosMeseros) -> Mesero:
    return m.total


INDICADORES = [
    Indicador("venta_bruta", "Venta de meseros (salón, con IVA)", "Ventas de meseros", MONEDA,
              lambda m: _t(m).venta_bruta, True),
    Indicador("venta_neta", "Venta neta (sin IVA)", "Ventas de meseros", MONEDA, lambda m: _t(m).venta_neta, True),
    Indicador("cuentas", "Mesas atendidas (cuentas)", "Ventas de meseros", ENTERO, lambda m: _t(m).cuentas, True),
    Indicador("personas", "Personas", "Ventas de meseros", ENTERO, lambda m: _t(m).personas, True),
    Indicador("personas_mesa", "Personas por mesa", "Ventas de meseros", DECIMAL, lambda m: _t(m).personas_por_mesa, None),
    Indicador("cheque", "Cheque promedio (venta / persona)", "Ventas de meseros", MONEDA,
              lambda m: _t(m).cheque_promedio, True),
    Indicador("venta_mesa", "Venta por mesa", "Ventas de meseros", MONEDA, lambda m: _t(m).venta_por_mesa, True),
    Indicador("plantilla", "Meseros activos (plantilla)", "Plantilla", ENTERO, lambda m: Decimal(m.plantilla), None),
    Indicador("venta_mesero", "Venta por mesero", "Plantilla", MONEDA, lambda m: m.venta_por_mesero, True),
    Indicador("venta_mesero_dia", "Venta por mesero por día trabajado", "Plantilla", MONEDA,
              lambda m: m.venta_por_mesero_dia, True),
    Indicador("mix_alimentos", "Mix: Alimentos", "Mezcla", PORCENTAJE, lambda m: _t(m).pct_alimentos, None,
              requiere_detalle=True),
    Indicador("mix_bebidas", "Mix: Bebidas", "Mezcla", PORCENTAJE, lambda m: _t(m).pct_bebidas, None,
              requiere_detalle=True),
    Indicador("propina", "Propina (% de la venta)", "Servicio", PORCENTAJE, lambda m: _t(m).pct_propina, True),
    Indicador("tiempo_mesa", "Tiempo promedio de mesa (min)", "Servicio", ENTERO, lambda m: _t(m).tiempo_mesa, None),
    Indicador("cortesias", "Cortesías (a precio de lista)", "Control", MONEDA, lambda m: _t(m).cortesias, False),
    Indicador("cancelaciones", "Cancelaciones (sucursal)", "Control", MONEDA, lambda m: m.cancelaciones, False),
    Indicador("anulaciones", "Anulaciones (sucursal)", "Control", MONEDA, lambda m: m.anulaciones, False),
    Indicador("fuera_salon", "Venta sin mesero (plataformas y para llevar)", "Fuera de salón", MONEDA,
              lambda m: m.fuera_salon_venta, None),
]


def construir_tabla(actual: DatosMeseros, anterior: Comparacion, anio: Comparacion) -> list[Fila]:
    """Each comparison column over the comparable branches only (same rule as
    the commercial report); the period column is the whole selection."""
    filas = []
    for ind in INDICADORES:
        p, var_p = _columna(ind, anterior)
        y, var_y = _columna(ind, anio)
        filas.append(Fila(ind, _valor(ind, actual), p, var_p, y, var_y))
    return filas


def comparables(nombres: list[str], actuales: list[DatosMeseros], bases: list[DatosMeseros] | None,
                periodo: Periodo, periodo_base: Periodo | None) -> Comparacion:
    """A branch without data on UMBRAL_COBERTURA_FIABLE of the comparison
    period's days (new, or no data) leaves BOTH sides of that comparison, as in
    the commercial report (`metricas.comparables`)."""
    if bases is None or periodo_base is None:
        return Comparacion(datos_meseros.consolidar(actuales, periodo, nombres if len(nombres) > 1 else None), None)
    dentro = [i for i, b in enumerate(bases) if cobertura_fiable(b.dias_con_cierre, b.dias_esperados)]
    excluidas = [nombres[i] for i in range(len(nombres)) if i not in dentro]
    varias = len(nombres) > 1
    if not dentro:
        return Comparacion(datos_meseros.consolidar(actuales, periodo, nombres if varias else None), None, excluidas)
    sub = [nombres[i] for i in dentro]
    return Comparacion(datos_meseros.consolidar([actuales[i] for i in dentro], periodo, sub if varias else None),
                       datos_meseros.consolidar([bases[i] for i in dentro], periodo_base, sub if varias else None),
                       excluidas)


# -- detail ---------------------------------------------------------------------
@dataclass(frozen=True)
class FilaMesero:
    nombre: str
    m: Mesero
    semaforo_cheque: str | None  # verde >= branch average, naranja below, rojo < UMBRAL_CHEQUE_BAJO of it
    var_venta_dia: object  # Variacion of sales per day worked vs the waiter's previous period


@dataclass(frozen=True)
class FilaSucursal:
    nombre: str
    d: DatosMeseros
    mejor: str | None  # waiter with the most sales


def semaforo_cheque(cheque: Decimal | None, promedio: Decimal | None) -> str | None:
    if cheque is None or not promedio:
        return None
    if cheque >= promedio:
        return VERDE
    return ROJO if cheque < promedio * UMBRAL_CHEQUE_BAJO else NARANJA


def filas_meseros(actual: DatosMeseros, anterior: DatosMeseros | None) -> list[FilaMesero]:
    promedio = actual.total.cheque_promedio
    previos = anterior.meseros if anterior else {}
    return [FilaMesero(m.nombre, m, semaforo_cheque(m.cheque_promedio, promedio),
                       variacion(m.venta_por_dia, previos[m.nombre].venta_por_dia if m.nombre in previos else None))
            for m in actual.ranking()]


# -- Lectura ----------------------------------------------------------------------
def _pesos(v) -> str:
    return f"${v:,.0f}"


def _var_texto(var) -> str:
    if var.porcentaje is None:
        return "sin comparativo" if var.simbolo == "s/c" else "sin comparativo fiable"
    return f"{var.simbolo} {var.porcentaje * 100:+.1f}%"


def construir_lectura(periodo: Periodo, actual: DatosMeseros, filas: list[Fila], detalle: list[FilaMesero],
                      consolidado: bool, ramas: list[tuple[str, DatosMeseros]] | None = None) -> Lectura:
    por = {f.indicador.clave: f for f in filas}
    obs = []
    t = actual.total
    if not t.cuentas:
        return Lectura(titulo(periodo), [Observacion("No hay cuentas de salón en el periodo.", AVISO)])
    v = por["venta_bruta"]
    tono = {VERDE: POSITIVO, ROJO: NEGATIVO}.get(v.var_anterior.color, NEUTRO)
    obs.append(Observacion(
        f"La venta de meseros (salón) fue de {_pesos(t.venta_bruta)}, {_var_texto(v.var_anterior)} vs "
        f"{vs_anterior(periodo)} y {_var_texto(v.var_anio)} vs {vs_anio(periodo)}; {t.cuentas:,.0f} mesas y "
        f"{t.personas:,.0f} personas, cheque promedio {_pesos(t.cheque_promedio or 0)}.", tono))
    vd = por["venta_mesero_dia"]
    obs.append(Observacion(
        f"{actual.plantilla} meseros activos{' (suma de sucursales)' if consolidado else ''}; cada uno vendió en "
        f"promedio {_pesos(actual.venta_por_mesero_dia or 0)} por día trabajado ({_var_texto(vd.var_anterior)} vs "
        f"{vs_anterior(periodo)}).", {VERDE: POSITIVO, ROJO: NEGATIVO}.get(vd.var_anterior.color, NEUTRO)))
    if consolidado:  # waiters of different branches are not compared with each other: branches are
        return Lectura(titulo(periodo), obs + _lectura_sucursales(periodo, por, ramas))
    elegibles = [f for f in detalle if f.m.cuentas >= MIN_CUENTAS_LECTURA and f.m.cheque_promedio is not None]
    if len(elegibles) >= 2:
        mejor = max(elegibles, key=lambda f: f.m.cheque_promedio)
        peor = min(elegibles, key=lambda f: f.m.cheque_promedio)
        obs.append(Observacion(
            f"Mejor cheque promedio: {mejor.nombre} ({_pesos(mejor.m.cheque_promedio)}); el más bajo: {peor.nombre} "
            f"({_pesos(peor.m.cheque_promedio)}), contra {_pesos(t.cheque_promedio or 0)} de promedio.", NEUTRO))
        bajos = [f for f in elegibles if f.semaforo_cheque == ROJO]
        if bajos:
            nombres = ", ".join(f"{f.nombre} ({_pesos(f.m.cheque_promedio)})" for f in bajos[:3])
            extra = f" y {len(bajos) - 3} más" if len(bajos) > 3 else ""
            obs.append(Observacion(
                f"Cheque más de {(1 - UMBRAL_CHEQUE_BAJO) * 100:.0f}% abajo del promedio: {nombres}{extra}.", NEGATIVO))
    ranking = actual.ranking()
    if len(ranking) > 3 and t.venta_bruta:
        top = sum((m.venta_bruta for m in ranking[:3]), Decimal("0")) / t.venta_bruta
        if top >= UMBRAL_CONCENTRACION:
            obs.append(Observacion(f"Los 3 meseros con más venta concentran el {top * 100:.0f}% de la venta de salón.",
                                   AVISO))
    return Lectura(titulo(periodo), obs + _lectura_control(periodo, por, "de la sucursal"))


def _lectura_control(periodo: Periodo, por: dict, de: str) -> list[Observacion]:
    obs = []
    for clave, nombre in (("cancelaciones", "cancelaciones"), ("anulaciones", "anulaciones")):
        f = por[clave]
        if f.actual and f.var_anterior.color == ROJO:
            obs.append(Observacion(f"Las {nombre} {de} subieron a {_pesos(f.actual)} "
                                   f"({_var_texto(f.var_anterior)}); no se pueden atribuir a un mesero.", NEGATIVO))
    p = por["propina"]
    if p.actual is not None:
        obs.append(Observacion(f"Propina: {p.actual * 100:.1f}% de la venta ({_var_texto_pp(p.var_anterior)} vs "
                               f"{vs_anterior(periodo)}).", NEUTRO))
    return obs


def _lectura_sucursales(periodo: Periodo, por: dict, ramas: list[tuple[str, DatosMeseros]]) -> list[Observacion]:
    obs = []
    con_venta = [(n, d) for n, d in ramas if d.venta_por_mesero_dia]
    if len(con_venta) >= 2:
        alta = max(con_venta, key=lambda x: x[1].venta_por_mesero_dia)
        baja = min(con_venta, key=lambda x: x[1].venta_por_mesero_dia)
        obs.append(Observacion(f"Venta por mesero por día más alta: {alta[0]} ({_pesos(alta[1].venta_por_mesero_dia)}); "
                               f"la más baja: {baja[0]} ({_pesos(baja[1].venta_por_mesero_dia)}).", NEUTRO))
        cheques = [(n, d) for n, d in con_venta if d.total.cheque_promedio]
        alta = max(cheques, key=lambda x: x[1].total.cheque_promedio)
        baja = min(cheques, key=lambda x: x[1].total.cheque_promedio)
        obs.append(Observacion(f"Cheque promedio más alto: {alta[0]} ({_pesos(alta[1].total.cheque_promedio)}); "
                               f"el más bajo: {baja[0]} ({_pesos(baja[1].total.cheque_promedio)}).", NEUTRO))
    return obs + _lectura_control(periodo, por, "de las sucursales")


def _var_texto_pp(var) -> str:
    if var.porcentaje is None:
        return "sin comparativo" if var.simbolo == "s/c" else "sin comparativo fiable"
    return f"{var.simbolo} {var.porcentaje * 100:+.1f} pp"


# -- charts -----------------------------------------------------------------------
def construir_graficas(periodo: Periodo, actual: DatosMeseros, anterior: DatosMeseros | None,
                       por_sucursal: list[tuple[str, DatosMeseros, DatosMeseros | None]]) -> list[Grafica]:
    base_nombre = periodo.anterior().etiqueta()
    if por_sucursal:  # consolidated: one bar per branch
        etiquetas = [n for n, _, _ in por_sucursal]
        return [
            Grafica("Venta por mesero por día, por sucursal", etiquetas,
                    [d.venta_por_mesero_dia for _, d, _ in por_sucursal],
                    [p.venta_por_mesero_dia if p else None for _, _, p in por_sucursal],
                    periodo.etiqueta(), base_nombre, None, rotar=True),
            Grafica("Cheque promedio por sucursal", etiquetas,
                    [d.total.cheque_promedio for _, d, _ in por_sucursal],
                    [p.total.cheque_promedio if p else None for _, _, p in por_sucursal],
                    periodo.etiqueta(), base_nombre, None, rotar=True),
        ]
    top = actual.ranking()[:MAX_MESEROS_GRAFICA]
    previos = anterior.meseros if anterior else {}
    etiquetas = [nombre_corto(m.nombre) for m in top]
    nota = (f"Los {MAX_MESEROS_GRAFICA} meseros con más venta." if len(actual.ranking()) > MAX_MESEROS_GRAFICA
            else None)
    return [
        Grafica("Venta por mesero", etiquetas, [m.venta_bruta for m in top],
                [previos[m.nombre].venta_bruta if m.nombre in previos else None for m in top],
                periodo.etiqueta(), base_nombre, nota, rotar=True),
        Grafica("Cheque promedio por mesero", etiquetas, [m.cheque_promedio for m in top],
                [previos[m.nombre].cheque_promedio if m.nombre in previos else None for m in top],
                periodo.etiqueta(), base_nombre, nota, rotar=True),
    ]


# -- notes and rules ----------------------------------------------------------------
def notas_cobertura(actual: DatosMeseros, anterior: DatosMeseros | None,
                    comparaciones: list[tuple[Comparacion, str]] = (), consolidado: bool = False) -> list[str]:
    notas = []
    for comp, nombre in comparaciones:
        if comp.excluidas and comp.base is None:
            notas.append(f"Sin comparativo contra {nombre}: {', '.join(comp.excluidas)} sin datos completos en ese "
                         "periodo (sucursal nueva o sin operación).")
        elif comp.excluidas:
            notas.append(f"Comparativo contra {nombre} solo con sucursales comparables: se excluye(n) "
                         f"{', '.join(comp.excluidas)} por no tener datos completos en ese periodo.")
    if actual.dias_con_cierre < actual.dias_esperados:
        notas.append(f"El periodo tiene cierres de caja en {actual.dias_con_cierre} de {actual.dias_esperados} días.")
    if actual.fuera_salon_venta:
        notas.append(f"No incluye {_pesos(actual.fuera_salon_venta)} de venta sin mesero "
                     f"({actual.fuera_salon_cuentas:,.0f} cuentas de plataformas y para llevar).")
    pocos = [m for m in actual.ranking() if m.cuentas < MIN_CUENTAS_LECTURA]
    if pocos and not consolidado:  # the consolidated Lectura compares branches, not waiters
        notas.append(f"{len(pocos)} mesero(s) con menos de {MIN_CUENTAS_LECTURA} cuentas (suplentes o pocos días) "
                     "aparecen en el detalle pero no en el mejor/peor cheque de la Lectura.")
    if anterior is not None and not anterior.total.cuentas:
        notas.append("Sin cuentas de salón en el periodo anterior: sin comparativo.")
    return notas


def notas_reglas(periodo: Periodo) -> list[str]:
    reglas = [
        "Venta de meseros = cuentas de salón (tipo de orden «Restaurant»); plataformas y para llevar se muestran "
        "aparte como venta sin mesero.",
        "Plantilla = meseros con al menos una cuenta en el periodo. Venta por día trabajado = venta ÷ días en que "
        "el mesero tuvo cuentas.",
        "Cheque promedio = venta ÷ personas. En el detalle: verde igual o arriba del promedio de la sucursal, "
        f"naranja abajo, rojo más de {(1 - UMBRAL_CHEQUE_BAJO) * 100:.0f}% abajo.",
        f"Lectura: mejor/peor cheque solo entre meseros con al menos {MIN_CUENTAS_LECTURA} cuentas; concentración "
        f"si los 3 primeros suman {UMBRAL_CONCENTRACION * 100:.0f}% o más de la venta.",
        f"Tiempo de mesa = de la apertura al cierre de la cuenta; se excluyen tiempos fuera de {MINUTOS_MESA_MIN} a "
        f"{MINUTOS_MESA_MAX} minutos (cuentas olvidadas abiertas).",
        "Propina: la registrada en los pagos de las cuentas de salón. Cortesías: a precio de lista.",
        "Cancelaciones y anulaciones: totales de la sucursal del corte de caja; Wansoft las quita del ticket y no "
        "trae el mesero.",
        f"Sucursales comparables: la que no tiene datos en el {UMBRAL_COBERTURA_FIABLE * 100:.0f}% de los días del "
        "periodo de comparación sale de ambos lados; en el consolidado se comparan sucursales, no meseros entre sí.",
        f"Flechas: ▲ verde mejora, ▼ rojo empeora; «=» gris dentro de ±{UMBRAL_IGUAL * 100:.0f}%. s/c: sin "
        f"comparativo; s/cf: algún periodo con datos en menos del {UMBRAL_COBERTURA_FIABLE * 100:.0f}% de los días.",
        f"Día operativo: un cierre antes de las {HORA_CORTE_DIA}:00 cuenta para el día anterior.",
    ]
    if periodo.tipo == TipoPeriodo.SEMANA:
        reglas.append("Semana de lunes a domingo; la misma semana del año anterior es la misma semana ISO.")
    return reglas


# -- assembly -------------------------------------------------------------------------
@dataclass
class ReporteMeseros:
    nombre: str
    sucursales: list[str]
    periodo: Periodo
    actual: DatosMeseros
    anterior: DatosMeseros | None
    lectura: Lectura
    filas: list[Fila]
    graficas: list[Grafica]
    cobertura: list[str]
    reglas: list[str]
    detalle: list[FilaMesero] = field(default_factory=list)  # branch report: one row per waiter
    por_sucursal: list[FilaSucursal] = field(default_factory=list)  # consolidated: one row per branch
    titulo: str = TITULO
    incluir_costos: bool = False  # (shared PDF code reads it)

    @property
    def notas(self) -> list[str]:
        return self.cobertura + self.reglas


def _uno(nombre, sucursales, periodo, actual, anterior, comp_ant, comp_anio, por_sucursal=None) -> ReporteMeseros:
    filas = construir_tabla(actual, comp_ant, comp_anio)
    detalle = filas_meseros(actual, anterior)
    consolidado = bool(por_sucursal)
    comparaciones = [(comp_ant, vs_anterior(periodo))]
    if periodo.tipo != TipoPeriodo.ANIO:
        comparaciones.append((comp_anio, vs_anio(periodo)))
    r = ReporteMeseros(
        nombre=nombre, sucursales=sucursales, periodo=periodo, actual=actual, anterior=anterior,
        lectura=construir_lectura(periodo, actual, filas, detalle, consolidado,
                                  [(n, d) for n, d, _ in por_sucursal or []]), filas=filas,
        graficas=construir_graficas(periodo, actual, anterior, por_sucursal or []),
        cobertura=notas_cobertura(actual, anterior, comparaciones, consolidado), reglas=notas_reglas(periodo),
        detalle=[] if consolidado else detalle,
    )
    if por_sucursal:
        r.por_sucursal = [FilaSucursal(n, d, d.ranking()[0].nombre if d.ranking() else None) for n, d, _ in por_sucursal]
    return r


def armar(sucursales: list, periodo: Periodo, consolidado: bool) -> list[ReporteMeseros]:
    """Read the sources (read-only) once for the whole selection and build one
    report per branch, or one consolidated."""
    anterior, anio = periodo.anterior(), periodo.mismo_periodo_anio_anterior()
    with conexiones.abrir_wansoft() as cur:
        ma = datos_meseros.recolectar(cur, sucursales, periodo)
        mp = datos_meseros.recolectar(cur, sucursales, anterior)
        my = (mp if anio == anterior else datos_meseros.recolectar(cur, sucursales, anio)) if anio else None
    nombres = [s.nombre for s in sucursales]
    if consolidado:
        actual = datos_meseros.consolidar(ma, periodo, nombres)
        return [_uno("Consolidado", nombres, periodo, actual, datos_meseros.consolidar(mp, anterior, nombres),
                     comparables(nombres, ma, mp, periodo, anterior), comparables(nombres, ma, my, periodo, anio),
                     list(zip(nombres, ma, mp)))]
    return [_uno(n, [n], periodo, ma[i], mp[i], comparables([n], [ma[i]], [mp[i]], periodo, anterior),
                 comparables([n], [ma[i]], [my[i]] if my else None, periodo, anio)) for i, n in enumerate(nombres)]


def nombre_base(reportes: list[ReporteMeseros]) -> str:
    quien = reportes[0].nombre if len(reportes) == 1 else f"{len(reportes)} sucursales"
    limpio = "".join(ch if ch.isalnum() else "_" for ch in f"Reporte_Meseros_{quien}_{reportes[0].periodo.etiqueta()}")
    return "_".join(p for p in limpio.split("_") if p)
