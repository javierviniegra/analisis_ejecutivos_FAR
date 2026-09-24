"""Variation and arrow logic for comparison columns (pure functions).

Arrow rule (owner, 2026-09-23): up-green if better, down-red if worse, grey
"=" when the relative change is within +-1%. For metrics where an increase is
bad (cancellations, courtesies, discounts) the meaning is inverted.
"""

from dataclasses import dataclass
from decimal import Decimal

UMBRAL_IGUAL = Decimal("0.01")

SUBE, BAJA, IGUAL, SIN_DATO = "sube", "baja", "igual", "sin_dato"
VERDE, ROJO, GRIS = "verde", "rojo", "gris"
SIMBOLOS = {SUBE: "▲", BAJA: "▼", IGUAL: "=", SIN_DATO: "s/c"}


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


def porcentaje_de_meta(actual, meta) -> Decimal | None:
    """Progress against a target (1.0 = 100%); None when there is no target."""
    if actual is None or meta is None or Decimal(meta) == 0:
        return None
    return Decimal(actual) / Decimal(meta)
