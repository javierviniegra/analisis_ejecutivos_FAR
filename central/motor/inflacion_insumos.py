"""Price inflation of the top-20 critical inputs (owner, 2026-11-19).

Definition:
- **Source:** the Wansoft project's unified purchase lines
  (`analytics_purchase_order_lines`, Wansoft + Odoo, business view), of the
  selected branches, every supplier (El Bodegón and Las Empanadas included),
  by order date. A product is its `product_analytical_key`.
- **The 20 inputs:** the 20 products with the largest spend (`price_subtotal`,
  without IVA) in the 12 months before the period starts; recomputed for every
  period and selection, never a fixed list.
- **Price** of a product in a period = its spend / its quantity (weighted
  average unit price).
- **Inflation** = Laspeyres index against the same period last year:
  sum(price now x quantity last year) / sum(price last year x quantity last
  year) - 1, over the inputs bought in both periods (the others are named).
- **Traffic light, against Mexico's INPC (Banxico):** green when the inflation
  is at or below the year-on-year INPC of the period's last month, orange
  (amarillo) up to the INPC + 2 percentage points, red above. When that month
  is not published yet, the latest published month (up to 3 back) is used and
  named.

`leer_compras` and `calcular` read (read-only); the rest is pure.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from .comparativos import NARANJA, ROJO, VERDE
from .inflacion import anual
from .periodo import Periodo

TOP = 20
VENTANA_MESES = 12
MARGEN_INPC = Decimal("0.02")  # orange up to the INPC + 2 pp
MESES_INPC_ATRAS = 3
CERO = Decimal("0")

@dataclass(frozen=True)
class Compra:
    """What was bought of one product in a period (every branch selected)."""
    clave: str  # product_analytical_key
    nombre: str
    gasto: Decimal
    cantidad: Decimal

    @property
    def precio(self) -> Decimal | None:
        return self.gasto / self.cantidad if self.cantidad > 0 and self.gasto > 0 else None


def _mes_menos(d: date, meses: int) -> date:
    total = d.year * 12 + d.month - 1 - meses
    return date(total // 12, total % 12 + 1, 1)


def ventana(desde: date) -> tuple[date, date]:
    """The 12 months before `desde`: from the same day a year earlier (day 29-31
    -> 28) to the day before `desde`."""
    inicio = _mes_menos(date(desde.year, desde.month, 1), VENTANA_MESES).replace(day=min(desde.day, 28))
    return inicio, desde - timedelta(days=1)


def top(compras: dict[str, Compra], n: int = TOP) -> list[str]:
    """The `n` products with the largest spend (ties by name)."""
    return [c.clave for c in sorted(compras.values(), key=lambda c: (-c.gasto, c.nombre))[:n]]


@dataclass(frozen=True)
class FilaInsumo:
    clave: str
    nombre: str
    gasto_ventana: Decimal  # spend in the 12 months that chose it
    precio: Decimal | None  # period
    precio_base: Decimal | None  # same period last year
    cantidad_base: Decimal | None

    @property
    def variacion(self) -> Decimal | None:
        return self.precio / self.precio_base - 1 if self.precio and self.precio_base else None


@dataclass
class InflacionInsumos:
    periodo: Periodo
    base: Periodo | None
    ventana: tuple[date, date]
    filas: list[FilaInsumo]
    inflacion: Decimal | None  # Laspeyres, None without a comparable input
    inpc: Decimal | None = None  # year-on-year INPC used for the light
    inpc_mes: date | None = None
    sin_comparar: list[str] = field(default_factory=list)  # inputs not bought in one of the periods

    @property
    def estado(self) -> str | None:
        return estado(self.inflacion, self.inpc)


def laspeyres(filas: list[FilaInsumo]) -> Decimal | None:
    """sum(p1 q0) / sum(p0 q0) - 1 over the inputs with both prices (pure)."""
    comparables = [f for f in filas if f.precio and f.precio_base and f.cantidad_base]
    base = sum((f.precio_base * f.cantidad_base for f in comparables), CERO)
    if not comparables or base <= 0:
        return None
    return sum((f.precio * f.cantidad_base for f in comparables), CERO) / base - 1


def estado(inflacion, inpc) -> str | None:
    """Green <= INPC, orange <= INPC + 2 pp, red above; no light without either."""
    if inflacion is None or inpc is None:
        return None
    if inflacion <= inpc:
        return VERDE
    return NARANJA if inflacion <= inpc + MARGEN_INPC else ROJO


def inpc_referencia(serie: dict[date, Decimal], hasta: date) -> tuple[date, Decimal] | None:
    """(month, year-on-year INPC) of the month of `hasta`, or of the latest
    published month up to 3 months back; None if none is published."""
    mes = date(hasta.year, hasta.month, 1)
    for atras in range(MESES_INPC_ATRAS + 1):
        m = _mes_menos(mes, atras)
        valor = anual(serie, m)
        if valor is not None:
            return m, valor
    return None


def construir(periodo: Periodo, base: Periodo | None, ventana_: tuple[date, date], en_ventana: dict[str, Compra],
              actual: dict[str, Compra], anterior: dict[str, Compra], serie_inpc: dict[date, Decimal] | None = None
              ) -> InflacionInsumos:
    """The result from what was read (pure)."""
    filas = []
    for clave in top(en_ventana):
        a, b = actual.get(clave), anterior.get(clave)
        filas.append(FilaInsumo(clave, en_ventana[clave].nombre, en_ventana[clave].gasto, a.precio if a else None,
                                b.precio if b else None, b.cantidad if b else None))
    resultado = InflacionInsumos(periodo, base, ventana_, filas, laspeyres(filas),
                                 sin_comparar=[f.nombre for f in filas if not (f.precio and f.precio_base)])
    referencia = inpc_referencia(serie_inpc or {}, periodo.hasta)
    if referencia:
        resultado.inpc_mes, resultado.inpc = referencia
    return resultado


# -- reading (read-only) -----------------------------------------------------------
def leer_compras(cur, claves: list[str], desde: date, hasta: date) -> dict[str, Compra]:
    """Spend and quantity per product of these branches (short keys, our
    `wansoft_ticket_nombre` = `company_source_key`) ordered in [desde, hasta]."""
    from .fuentes import wansoft
    return {clave: Compra(clave, (nombre or clave).strip(), Decimal(str(gasto or 0)), Decimal(str(cantidad or 0)))
            for clave, nombre, gasto, cantidad in wansoft.compras_por_producto(cur, claves, desde, hasta)}


def calcular(cur, sucursales: list, periodo: Periodo, serie_inpc: dict[date, Decimal] | None = None
             ) -> InflacionInsumos:
    """The top-20 input inflation of `sucursales` (objects with
    `wansoft_ticket_nombre`) in `periodo`. `serie_inpc`: {month: INPC}, e.g.
    Central's `inflacion.serie()`; without it there is no light."""
    claves = [s.wansoft_ticket_nombre for s in sucursales]
    base = periodo.mismo_periodo_anio_anterior()
    v = ventana(periodo.desde)
    en_ventana = leer_compras(cur, claves, *v)
    actual = leer_compras(cur, claves, periodo.desde, periodo.hasta)
    anterior = leer_compras(cur, claves, base.desde, base.hasta) if base else {}
    return construir(periodo, base, v, en_ventana, actual, anterior, serie_inpc)
