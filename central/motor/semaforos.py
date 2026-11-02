"""Traffic-light rules shared by the scorecard-style reports (pure functions).

Each function answers one kind of rule found in the Power BI scorecards and
returns a colour from `comparativos` (VERDE / NARANJA / ROJO) or None. None
means "no light": the value or its target is missing. A missing value is never
treated as 0 -- Power BI coalesces missing KPIs to 0 and paints some of them
green; here the data layer passes None and the row shows no light.
"""

from decimal import Decimal

from .comparativos import NARANJA, ROJO, VERDE

# General rule of the Power BI scorecard (KPI Estado): green when the target is
# met, orange up to 5% worse than the target, red beyond.
TOLERANCIA_GENERAL = Decimal("0.05")
# Target reached as a share of the target (sales, check, ticket, guests).
PCT_META_VERDE = Decimal("1")
PCT_META_NARANJA = Decimal("0.90")


def _dec(valor) -> Decimal | None:
    return None if valor is None else Decimal(valor)


def umbral(valor, verde, naranja, *, mayor_mejor: bool) -> str | None:
    """Fixed thresholds.

    Higher is better: green >= `verde`, orange >= `naranja`, red below.
    Lower is better: green <= `verde`, orange < `naranja`, red from `naranja` on
    (Power BI's cost rule: green <= 37%, orange < 39%, red >= 39%).
    """
    v = _dec(valor)
    if v is None:
        return None
    if mayor_mejor:
        return VERDE if v >= verde else NARANJA if v >= naranja else ROJO
    return VERDE if v <= verde else NARANJA if v < naranja else ROJO


def banda(valor, desde, hasta) -> str | None:
    """Target band: green from `desde` up to below `hasta`, orange below `desde`,
    red from `hasta` on (the commercial report's cost, owner 2026-10-29: green
    37% to below 39%; below 37% bought or captured too little)."""
    v = _dec(valor)
    if v is None:
        return None
    return NARANJA if v < desde else VERDE if v < hasta else ROJO


def porcentaje_meta(actual, meta) -> str | None:
    """Actual as a share of its target: green >= 100%, orange >= 90%, red below."""
    a, m = _dec(actual), _dec(meta)
    if a is None or m is None or m == 0:
        return None
    return umbral(a / m, PCT_META_VERDE, PCT_META_NARANJA, mayor_mejor=True)


def cero_es_verde(valor) -> str | None:
    """Zero is the target (incidents, delivery errors): green at 0, red above."""
    v = _dec(valor)
    if v is None:
        return None
    return VERDE if v <= 0 else ROJO


def signo(valor) -> str | None:
    """Sign of the value (NPS): green above 0, orange at 0, red below."""
    v = _dec(valor)
    if v is None:
        return None
    return VERDE if v > 0 else NARANJA if v == 0 else ROJO


def contra_meta(actual, meta, *, mayor_mejor: bool, tolerancia: Decimal = TOLERANCIA_GENERAL) -> str | None:
    """General rule: green when the target is met, orange within `tolerancia`
    (relative to the target) on the wrong side, red beyond. No light without a
    target or with a zero target (a relative gap to zero is undefined)."""
    a, m = _dec(actual), _dec(meta)
    if a is None or m is None or m == 0:
        return None
    brecha = (a - m) / m
    if mayor_mejor:
        return VERDE if a >= m else NARANJA if brecha >= -tolerancia else ROJO
    return VERDE if a <= m else NARANJA if brecha <= tolerancia else ROJO
