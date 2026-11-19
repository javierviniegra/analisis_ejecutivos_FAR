"""Fill rate of the CEDIS (El Bodegón, Las Empanadas) to the branches (pure).

Definition (owner, 2026-11-18/19):
- **Ordered = what the branch ordered:** the quantity of each product as the
  order stands when read, with the CEDIS's own changes after confirming taken
  back out (a CEDIS cut does not lower what the branch ordered; the branch's
  own changes do count). Products the CEDIS added (extra lines made by the
  CEDIS) were not ordered and stay out. Who made each change comes from the
  order's history, as in the CEDIS workbooks (`reporte_cedis`).
- **Delivered** = the provider's sales order `qty_delivered`, matched to the
  branch's purchase line by product, its variants together
  (`reporte_cedis.producto_base`: "X Ind", the branch's indirect kit, is the
  CEDIS's "X"; internal codes "[...]" and " copia" ignored).
- **Per product over the period:** for each product (per provider), delivered
  / ordered adding every order of the period, capped at 100%; the fill rate of
  a group (a provider, a branch, everything) is the simple average of its
  products. Quantities are never added across products (kg, pieces, boxes).
- Orders as the CEDIS workbooks read them: confirmed, created in the period
  (Mexico City days), each branch from its Odoo start.
- **Traffic light (owner's draft):** green >= 98.0%, orange (amarillo) 95.0% to
  97.9%, red below 95.0%.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from . import semaforos
from .reporte_cedis import CEDIS, DatosCedis, Orden, producto_base

FILL_VERDE = Decimal("0.98")
FILL_NARANJA = Decimal("0.95")
CERO, UNO = Decimal("0"), Decimal("1")


def estado(valor) -> str | None:
    return semaforos.umbral(valor, FILL_VERDE, FILL_NARANJA, mayor_mejor=True)


def pedido_por_sucursal(orden: Orden) -> list[tuple[str, str, Decimal, Decimal]]:
    """(base product, name, ordered by the branch, delivered) of each product of the order
    the branch ordered (pure). Ordered = the quantity now minus the CEDIS's
    changes to that product; products the CEDIS added and products left at
    zero (or below) by the branch are not ordered."""
    agregados_cedis = {e.producto for e in orden.extras if e.hecho_por == CEDIS}
    cambio_cedis = defaultdict(lambda: CERO)
    for c in orden.cantidades:
        if c.hecho_por == CEDIS:
            cambio_cedis[c.producto] += c.diferencia
    salida = []
    for ln in orden.lineas:
        if ln.producto in agregados_cedis:
            continue
        pedida = ln.pedida - cambio_cedis[ln.producto]
        if pedida > 0:
            salida.append((ln.base or producto_base(ln.producto), ln.producto, pedida, ln.entregada))
    return salida


@dataclass(frozen=True)
class FillProducto:
    proveedor: str
    producto: str
    pedida: Decimal
    entregada: Decimal
    pedidos: int  # orders of the period with this product

    @property
    def fill(self) -> Decimal:
        return min(self.entregada / self.pedida, UNO)

    @property
    def faltante(self) -> Decimal:
        return max(self.pedida - self.entregada, CERO)


def por_producto(ordenes: list[Orden]) -> list[FillProducto]:
    """Every product (per provider, its variants together: "X Ind" = "X") of
    these orders, ordered and delivered over all of them (pure)."""
    pedida, entregada, pedidos, nombre = defaultdict(lambda: CERO), defaultdict(lambda: CERO), defaultdict(int), {}
    for o in ordenes:
        for base, n, q, e in pedido_por_sucursal(o):
            clave = (o.proveedor, base)
            nombre.setdefault(clave, n)
            pedida[clave] += q
            entregada[clave] += e
            pedidos[clave] += 1
    return sorted((FillProducto(k[0], nombre[k], pedida[k], entregada[k], pedidos[k]) for k in pedida),
                  key=lambda f: (f.proveedor, f.producto))


@dataclass(frozen=True)
class Fill:
    grupo: str  # provider, branch or "Total"
    fill: Decimal | None  # simple average of the products' fill; None without products
    productos: int
    completos: int  # products delivered in full
    pedidos: int  # orders with at least one product ordered by the branch

    @property
    def estado(self) -> str | None:
        return estado(self.fill)


def fill(grupo: str, ordenes: list[Orden]) -> Fill:
    productos = por_producto(ordenes)
    valor = sum((p.fill for p in productos), CERO) / len(productos) if productos else None
    pedidos = sum(1 for o in ordenes if pedido_por_sucursal(o))
    return Fill(grupo, valor, len(productos), sum(1 for p in productos if p.fill >= UNO), pedidos)


@dataclass(frozen=True)
class ResumenFill:
    total: Fill
    por_proveedor: list[Fill]
    por_sucursal: list[Fill]
    sin_entrega: int  # orders with products ordered and nothing delivered yet (may still be on their way)


def resumen(datos: DatosCedis) -> ResumenFill:
    """The fill rate of everything read, per provider and per branch (pure)."""
    ordenes = datos.ordenes
    proveedores = sorted({o.proveedor for o in ordenes})
    sin_entrega = sum(1 for o in ordenes if (ped := pedido_por_sucursal(o)) and not any(e > 0 for *_, e in ped))
    return ResumenFill(
        fill("Total", ordenes),
        [fill(p, [o for o in ordenes if o.proveedor == p]) for p in proveedores],
        [fill(s, [o for o in ordenes if o.sucursal == s]) for s in datos.sucursales],
        sin_entrega,
    )
