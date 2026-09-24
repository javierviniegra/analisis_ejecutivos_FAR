"""Display formatting shared by every output (console, PDF, Excel, web)."""

from decimal import Decimal

from .tabla_comercial import ENTERO, MONEDA, PORCENTAJE

SIN_DATO = "—"


def valor(v: Decimal | None, formato: str) -> str:
    if v is None:
        return SIN_DATO
    if formato == MONEDA:
        return f"${v:,.2f}"
    if formato == ENTERO:
        return f"{v:,.0f}"
    if formato == PORCENTAJE:
        return f"{v * 100:.1f}%"
    raise ValueError(f"unknown format {formato!r}")


def variacion(var, formato: str) -> str:
    """Arrow plus size of the change: relative % for amounts and counts,
    percentage points for shares. 's/c' when there is nothing to compare."""
    if var.porcentaje is None:
        return var.simbolo
    cifra = round(var.porcentaje * 100, 1) + 0  # + 0 turns -0.0 into 0.0
    signo = "+" if cifra > 0 else ""
    unidad = " pp" if formato == PORCENTAJE else "%"
    return f"{var.simbolo} {signo}{cifra:.1f}{unidad}"
