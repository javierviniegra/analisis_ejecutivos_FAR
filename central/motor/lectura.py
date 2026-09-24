"""Rule-based "Lectura del periodo" box of the commercial report (pure: no I/O).

Every sentence is computed from the indicators table; nothing is invented.
The AI analyst (last phase) will later rewrite this same box without
changing the rest of the report.

Rules, in priority order (owner, 2026-09-24; thresholds are constants to be
tuned once real reports have been read):
1. Gross sales (con IVA; owner's choice to measure the impact of sales) vs
   previous period and vs same period last year. Always.
2. What drove the change vs the previous period: guests (traffic) or
   average check, whichever moved more. Only when sales moved.
3. Controls (cancellations, courtesies, discounts) that went up AND weigh at
   least UMBRAL_PESO_CONTROL of net sales.
4. Channel / food-beverage mix rows that moved more than UMBRAL_PUNTOS_MEZCLA.
5. Costo de Ventas above its prorated budget.
A comparison without enough coverage reads "sin comparativo fiable"; the
coverage details go to the report's footnotes (`notas.py`), not here.
"""

from dataclasses import dataclass
from decimal import Decimal

from . import formato
from .comparativos import BAJA, NO_FIABLE, SUBE
from .metricas import Comparacion, Metricas, como_comparacion
from .periodo import Periodo, TipoPeriodo
from .tabla_comercial import Fila, construir_tabla

UMBRAL_PESO_CONTROL = Decimal("0.005")  # 0.5% of net sales
UMBRAL_PUNTOS_MEZCLA = Decimal("0.02")  # 2 percentage points

POSITIVO, NEGATIVO, NEUTRO, AVISO = "positivo", "negativo", "neutro", "aviso"

# (noun, feminine?) per period kind
_NOMBRES = {
    TipoPeriodo.SEMANA: ("semana", True),
    TipoPeriodo.MES: ("mes", False),
    TipoPeriodo.BIMESTRE: ("bimestre", False),
    TipoPeriodo.TRIMESTRE: ("trimestre", False),
    TipoPeriodo.SEMESTRE: ("semestre", False),
    TipoPeriodo.ANIO: ("año", False),
    TipoPeriodo.RANGO: ("periodo", False),
}


@dataclass(frozen=True)
class Observacion:
    texto: str
    tono: str  # positivo / negativo / neutro / aviso


@dataclass(frozen=True)
class Lectura:
    titulo: str
    observaciones: list[Observacion]


def _nombre(periodo: Periodo) -> tuple[str, bool]:
    return _NOMBRES[periodo.tipo]


def titulo(periodo: Periodo) -> str:
    nombre, fem = _nombre(periodo)
    return f"Lectura {'de la' if fem else 'del'} {nombre}"


def vs_anterior(periodo: Periodo) -> str:
    nombre, fem = _nombre(periodo)
    return f"{'la' if fem else 'el'} {nombre} anterior"


def vs_anio(periodo: Periodo) -> str:
    nombre, fem = _nombre(periodo)
    return f"{'la misma' if fem else 'el mismo'} {nombre} del año anterior"


def _pesos(v: Decimal) -> str:
    return f"${v:,.0f}"


def _tono(var) -> str:
    return {"verde": POSITIVO, "rojo": NEGATIVO}.get(var.color, NEUTRO)


def _fila(filas: list[Fila], clave: str) -> Fila:
    return next(f for f in filas if f.indicador.clave == clave)


def _var(f: Fila, campo: str = "var_anterior") -> str:
    return formato.variacion(getattr(f, campo), f.indicador.formato)


def _sin_comparativo(var) -> str:
    return "sin comparativo fiable" if var.direccion == NO_FIABLE else "sin comparativo"


# -- rules ----------------------------------------------------------------
def _comparables(comp: Comparacion) -> str:
    return " en sucursales comparables" if comp.excluidas else ""


def _venta(periodo, filas, ant: Comparacion, anio: Comparacion) -> Observacion | None:
    f = _fila(filas, "venta_bruta")
    if f.actual is None:
        return None
    if f.var_anterior.porcentaje is None:
        vs_ant = f"{_sin_comparativo(f.var_anterior)} contra {vs_anterior(periodo)}"
    else:
        dif = ant.actual.venta_bruta - ant.base.venta_bruta  # comparable branches only
        vs_ant = (f"{_var(f)} ({'+' if dif >= 0 else '-'}{_pesos(abs(dif))}) vs {vs_anterior(periodo)}"
                  f"{_comparables(ant)}")
    texto = f"La venta bruta fue de {_pesos(f.actual)}, {vs_ant}"
    # For a year the previous period IS the same period last year: say it once.
    if periodo.tipo != TipoPeriodo.ANIO:
        if f.var_anio.porcentaje is None:
            texto += f" y {_sin_comparativo(f.var_anio)} contra {vs_anio(periodo)}"
        else:
            texto += f" y {_var(f, 'var_anio')} vs {vs_anio(periodo)}{_comparables(anio)}"
    return Observacion(texto + ".", _tono(f.var_anterior))


def _causa(periodo, filas) -> Observacion | None:
    venta = _fila(filas, "venta_bruta")
    if venta.var_anterior.direccion not in (SUBE, BAJA):
        return None
    cli, chq = _fila(filas, "clientes"), _fila(filas, "cheque_promedio")
    if cli.var_anterior.porcentaje is None or chq.var_anterior.porcentaje is None:
        return None
    if abs(cli.var_anterior.porcentaje) >= abs(chq.var_anterior.porcentaje):
        texto = (f"El cambio vs {vs_anterior(periodo)} viene sobre todo del tráfico: clientes {_var(cli)} "
                 f"({formato.valor(cli.actual, cli.indicador.formato)}), cheque promedio {_var(chq)}.")
    else:
        texto = (f"El cambio vs {vs_anterior(periodo)} viene sobre todo del cheque promedio: {_var(chq)} "
                 f"({formato.valor(chq.actual, chq.indicador.formato)}), clientes {_var(cli)}.")
    return Observacion(texto, _tono(venta.var_anterior))


def _controles(periodo, filas) -> Observacion | None:
    neta = _fila(filas, "venta_neta").actual
    if not neta:
        return None
    alertas = []
    for clave in ("cancelaciones", "cortesias", "descuentos"):
        f = _fila(filas, clave)
        if f.actual is None or f.var_anterior.direccion != SUBE:
            continue
        peso = f.actual / neta
        if peso >= UMBRAL_PESO_CONTROL:
            alertas.append(f"{f.indicador.etiqueta} {_pesos(f.actual)} ({_var(f)}, "
                           f"{peso * 100:.1f}% de la venta neta)")
    if not alertas:
        return None
    return Observacion(f"Controles al alza vs {vs_anterior(periodo)}: " + "; ".join(alertas) + ".", NEGATIVO)


def _mezcla(periodo, filas) -> Observacion | None:
    cambios = [
        f"{f.indicador.etiqueta.split(': ', 1)[-1]} {formato.valor(f.actual, f.indicador.formato)} ({_var(f)})"
        for f in filas
        if f.indicador.seccion == "Mezcla"
        and f.var_anterior.porcentaje is not None
        and abs(f.var_anterior.porcentaje) > UMBRAL_PUNTOS_MEZCLA
    ]
    if not cambios:
        return None
    return Observacion(f"Cambio en la mezcla vs {vs_anterior(periodo)}: " + "; ".join(cambios) + ".", NEUTRO)


def _costo_ventas(actual: Metricas) -> Observacion | None:
    ejercido = actual.ejercido_costo_ventas
    if ejercido is None or ejercido <= 1:
        return None
    texto = (f"El Costo de Ventas real ({_pesos(actual.costo_ventas_real_con_ppto)}) supera el presupuesto "
             f"prorrateado ({_pesos(actual.costo_ventas_ppto)}): {ejercido * 100:.1f}% ejercido")
    if actual.n_sucursales > 1:
        texto += f" ({actual.n_con_presupuesto} de {actual.n_sucursales} sucursales tienen presupuesto)"
    return Observacion(texto + ".", NEGATIVO)


def construir_lectura(periodo: Periodo, actual: Metricas, anterior: Comparacion | Metricas | None,
                      anio_anterior: Comparacion | Metricas | None) -> Lectura:
    ant, anio = como_comparacion(actual, anterior), como_comparacion(actual, anio_anterior)
    filas = construir_tabla(actual, ant, anio)
    candidatas = [
        _venta(periodo, filas, ant, anio),
        _causa(periodo, filas),
        _controles(periodo, filas),
        _mezcla(periodo, filas),
        _costo_ventas(actual),
    ]
    obs = [o for o in candidatas if o is not None]
    if actual.dias_con_cierre == 0:
        obs.insert(0, Observacion("No hay cierres de caja en el periodo.", AVISO))
    return Lectura(titulo(periodo), obs)
