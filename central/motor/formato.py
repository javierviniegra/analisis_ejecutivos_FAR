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
    signo = "+" if var.porcentaje > 0 else ""
    if formato == PORCENTAJE:
        return f"{var.simbolo} {signo}{var.porcentaje * 100:.1f} pp"
    return f"{var.simbolo} {signo}{var.porcentaje * 100:.1f}%"
