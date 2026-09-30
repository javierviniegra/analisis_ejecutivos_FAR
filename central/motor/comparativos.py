"""Variation and arrow logic for comparison columns (pure functions).

Arrow rule (owner, 2026-09-23): up-green if better, down-red if worse, grey
"=" when the relative change is within +-1%. For metrics where an increase is
bad (cancellations, courtesies, discounts) the meaning is inverted.
"""

from dataclasses import dataclass
from decimal import Decimal

UMBRAL_IGUAL = Decimal("0.01")
# Project rule (owner, 2026-09-24): a comparison is only reliable when BOTH
# periods have data on at least 90% of the expected days; otherwise it is
# shown as "s/cf" (sin comparativo fiable) and explained in a footnote.
UMBRAL_COBERTURA_FIABLE = Decimal("0.90")

SUBE, BAJA, IGUAL, SIN_DATO, NO_FIABLE = "sube", "baja", "igual", "sin_dato", "no_fiable"
VERDE, ROJO, GRIS, NARANJA = "verde", "rojo", "gris", "naranja"

# Business rule (owner, 2026-09-30): Costo de Ventas must be 38.0%-39.9% of
# net sales, per week and per month. Below 38% orange (bought too little or
# did not capture purchases); 40% or more red (bought too much).
META_COSTO_MIN = Decimal("0.38")
META_COSTO_TOPE = Decimal("0.40")


def semaforo_costo(pct: Decimal | None) -> str | None:
    """Traffic light of Costo de Ventas as a share of net sales."""
    if pct is None:
        return None
    if pct < META_COSTO_MIN:
        return NARANJA
    return VERDE if pct < META_COSTO_TOPE else ROJO
SIMBOLOS = {SUBE: "▲", BAJA: "▼", IGUAL: "=", SIN_DATO: "s/c", NO_FIABLE: "s/cf"}
NO_COMPARABLE = (SIN_DATO, NO_FIABLE)


@dataclass(frozen=True)
class Variacion:
    porcentaje: Decimal | None  # relative change, 0.05 = +5%; None if not computable
    direccion: str  # sube / baja / igual / sin_dato
    color: str  # verde / rojo / gris
    simbolo: str


def variacion(actual, base, *, mejor_si_sube: bool = True, umbral: Decimal = UMBRAL_IGUAL) -> Variacion:
    """Compare `actual` with `base`.

    No comparison (`sin_dato`, grey) when either value is missing or the base
    is zero: a relative change against zero is undefined, and inventing one
    would mislead. Within +-`umbral` counts as unchanged.
    """
    if actual is None or base is None or Decimal(base) == 0:
        return Variacion(None, SIN_DATO, GRIS, SIMBOLOS[SIN_DATO])
    pct = (Decimal(actual) - Decimal(base)) / abs(Decimal(base))
    if abs(pct) <= umbral:
        return Variacion(pct, IGUAL, GRIS, SIMBOLOS[IGUAL])
    direccion = SUBE if pct > 0 else BAJA
    es_bueno = (direccion == SUBE) == mejor_si_sube
    return Variacion(pct, direccion, VERDE if es_bueno else ROJO, SIMBOLOS[direccion])


def cobertura_fiable(dias_con_dato: int, dias_esperados: int) -> bool:
    return dias_esperados > 0 and Decimal(dias_con_dato) / dias_esperados >= UMBRAL_COBERTURA_FIABLE


def no_fiable() -> Variacion:
    return Variacion(None, NO_FIABLE, GRIS, SIMBOLOS[NO_FIABLE])


def porcentaje_de_meta(actual, meta) -> Decimal | None:
    """Progress against a target (1.0 = 100%); None when there is no target."""
    if actual is None or meta is None or Decimal(meta) == 0:
        return None
    return Decimal(actual) / Decimal(meta)
