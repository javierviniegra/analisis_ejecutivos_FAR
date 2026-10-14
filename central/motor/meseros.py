"""Waiters' metrics (reporte de meseros) for a period, per branch.

Read from the ticket detail (dining-room orders only, owner 2026-10-13) and,
for what only the cash closing has (cancellations and voids, which Wansoft
removes from the tickets), from the closing at branch level.

Checked on Acoxpa, September 2026: dining room + other order types = the
cash closings to the cent ($5,793,222.90); Alimentos + Bebidas of each
waiter = his sales.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .fuentes import wansoft
from .periodo import Periodo

CERO = Decimal("0")


def _razon(a, b) -> Decimal | None:
    return Decimal(a) / Decimal(b) if a is not None and b else None


@dataclass
class Mesero:
    nombre: str
    cuentas: Decimal = CERO  # dining-room accounts = tables served
    personas: Decimal = CERO
    venta_bruta: Decimal = CERO
    venta_neta: Decimal = CERO
    dias: Decimal = CERO  # days with at least one account
    minutos_mesa: Decimal = CERO
    mesas_con_tiempo: Decimal = CERO
    alimentos: Decimal = CERO
    bebidas: Decimal = CERO
    cortesias: Decimal = CERO  # at sale price
    descuentos: Decimal = CERO  # discounts on the lines that are not courtesies
    propina: Decimal = CERO

    CAMPOS = ("cuentas", "personas", "venta_bruta", "venta_neta", "dias", "minutos_mesa", "mesas_con_tiempo",
              "alimentos", "bebidas", "cortesias", "descuentos", "propina")

    def sumar(self, otro: "Mesero") -> None:
        for c in self.CAMPOS:
            setattr(self, c, getattr(self, c) + getattr(otro, c))

    @property
    def cheque_promedio(self) -> Decimal | None:
        return _razon(self.venta_bruta, self.personas)

    @property
    def venta_por_mesa(self) -> Decimal | None:
        return _razon(self.venta_bruta, self.cuentas)

    @property
    def venta_por_dia(self) -> Decimal | None:
        return _razon(self.venta_bruta, self.dias)

    @property
    def personas_por_mesa(self) -> Decimal | None:
        return _razon(self.personas, self.cuentas)

    @property
    def pct_bebidas(self) -> Decimal | None:
        return _razon(self.bebidas, self.alimentos + self.bebidas)

    @property
    def pct_alimentos(self) -> Decimal | None:
        return _razon(self.alimentos, self.alimentos + self.bebidas)

    @property
    def control(self) -> Decimal:
        """Courtesies + discounts: what the waiter gave away."""
        return self.cortesias + self.descuentos

    @property
    def pct_control(self) -> Decimal | None:
        """Courtesies + discounts as a share of what would have been sold without them."""
        return _razon(self.control, self.venta_bruta + self.control)

    @property
    def pct_propina(self) -> Decimal | None:
        return _razon(self.propina, self.venta_bruta)

    @property
    def tiempo_mesa(self) -> Decimal | None:
        return _razon(self.minutos_mesa, self.mesas_con_tiempo)


@dataclass
class DatosMeseros:
    """One branch's (or several branches', consolidated) waiters in a period.
    Carries the same coverage fields as `metricas.Metricas`, so the indicators
    table, its arrows and its s/cf rule work unchanged."""

    periodo: Periodo
    n_sucursales: int = 1
    meseros: dict[str, Mesero] = field(default_factory=dict)
    # platforms (apps) / take-away / others: no waiter. {canal: {cuentas, venta_bruta, descuentos, cortesias}}
    fuera: dict[str, dict] = field(default_factory=dict)
    cancelaciones: Decimal = CERO  # branch level, from the cash closing
    anulaciones: Decimal = CERO
    dias_con_cierre: int = 0
    dias_con_detalle: int = 0
    plantilla_sumada: int | None = None  # consolidated: sum of each branch's staff
    costo_preliminar: bool = False  # (not used; the shared table code reads it)

    @property
    def dias_esperados(self) -> int:
        return self.periodo.dias * self.n_sucursales

    def _fuera(self, clave: str, canales=None) -> Decimal:
        return sum((v[clave] for c, v in self.fuera.items() if canales is None or c in canales), CERO)

    @property
    def fuera_salon_venta(self) -> Decimal:
        return self._fuera("venta_bruta")

    @property
    def fuera_salon_cuentas(self) -> Decimal:
        return self._fuera("cuentas")

    def canal(self, canal: str) -> dict:
        return self.fuera.get(canal, {"cuentas": CERO, "venta_bruta": CERO, "descuentos": CERO, "cortesias": CERO})

    @property
    def venta_total(self) -> Decimal:
        """Dining room + platforms + take-away: the branch's whole sales."""
        return self.total.venta_bruta + self.fuera_salon_venta

    @property
    def cortesias_total(self) -> Decimal:
        return self.total.cortesias + self._fuera("cortesias")

    @property
    def descuentos_total(self) -> Decimal:
        return self.total.descuentos + self._fuera("descuentos")

    @property
    def total(self) -> Mesero:
        t = Mesero("Total")
        for m in self.meseros.values():
            t.sumar(m)
        return t

    @property
    def plantilla(self) -> int:
        """Waiters with at least one account in the period (owner, 2026-10-13)."""
        if self.plantilla_sumada is not None:
            return self.plantilla_sumada
        return len(self.ranking())

    @property
    def venta_por_mesero(self) -> Decimal | None:
        return _razon(self.total.venta_bruta, self.plantilla)

    @property
    def venta_por_mesero_dia(self) -> Decimal | None:
        """Sales per waiter per day worked: the fair comparison between someone
        who worked 3 days and someone who worked 6."""
        t = self.total
        return _razon(t.venta_bruta, t.dias)

    def ranking(self) -> list[Mesero]:
        # a pseudo-user with $0 accounts (e.g. "Apps Llevar" on a dining-room order) is not a waiter
        return sorted((m for m in self.meseros.values() if m.cuentas > 0 and m.venta_bruta > 0),
                      key=lambda m: m.venta_bruta, reverse=True)


def recolectar(cur, sucursales: list, periodo: Periodo) -> list[DatosMeseros]:
    """Read the waiters of every branch (`cuentas.Sucursal`) for one period,
    one batched query per source, in the same order as `sucursales`."""
    d, h = periodo.desde, periodo.hasta
    nombres = [s.wansoft_ticket_nombre for s in sucursales if s.wansoft_ticket_nombre]
    ventas = wansoft.ventas_meseros(cur, nombres, d, h)
    fuera = wansoft.fuera_de_salon(cur, nombres, d, h)
    mix = wansoft.mix_meseros(cur, nombres, d, h)
    propinas = wansoft.propinas_meseros(cur, nombres, d, h)
    ids = [s.wansoft_subsidiary_id for s in sucursales if s.wansoft_subsidiary_id is not None]
    tickets_de = {s.wansoft_subsidiary_id: s.wansoft_ticket_nombre for s in sucursales
                  if s.wansoft_subsidiary_id is not None and s.wansoft_ticket_nombre}
    cierres = wansoft.cierres_por_dia(cur, ids, d, h, tickets_de=tickets_de)

    resultado = []
    for s in sucursales:
        datos = DatosMeseros(periodo=periodo)
        nombre = s.wansoft_ticket_nombre
        for mesero, v in ventas.get(nombre, {}).items():
            m = Mesero(mesero, **v)
            extra = mix.get(nombre, {}).get(mesero, {})
            m.alimentos, m.bebidas = extra.get("alimentos", CERO), extra.get("bebidas", CERO)
            m.cortesias = extra.get("cortesias", CERO)
            m.descuentos = extra.get("descuentos", CERO)
            m.propina = propinas.get(nombre, {}).get(mesero, CERO)
            datos.meseros[mesero] = m
        datos.fuera = {c: dict(v) for c, v in fuera.get(nombre, {}).items()}
        dias = cierres.get(s.wansoft_subsidiary_id, {})
        datos.dias_con_cierre = len(dias)
        datos.cancelaciones = sum((t["cancelaciones"] for t in dias.values()), CERO)
        datos.anulaciones = sum((t["anulaciones"] for t in dias.values()), CERO)
        datos.dias_con_detalle = datos.dias_con_cierre if datos.meseros else 0  # mix needs the ticket detail
        resultado.append(datos)
    return resultado


def consolidar(lista: list[DatosMeseros], periodo: Periodo, nombres: list[str] | None = None) -> DatosMeseros:
    """Several branches together. Waiters keep their branch in the key (a
    waiter is counted once per branch), and the staff is the sum of each
    branch's staff."""
    total = DatosMeseros(periodo=periodo, n_sucursales=len(lista), plantilla_sumada=sum(x.plantilla for x in lista))
    for i, x in enumerate(lista):
        prefijo = f"{nombres[i]} · " if nombres else ""
        for clave, m in x.meseros.items():
            copia = Mesero(prefijo + clave)
            copia.sumar(m)
            total.meseros[prefijo + clave] = copia
        for canal, v in x.fuera.items():
            suma = total.fuera.setdefault(canal, {k: CERO for k in v})
            for k, valor in v.items():
                suma[k] += valor
        total.cancelaciones += x.cancelaciones
        total.anulaciones += x.anulaciones
        total.dias_con_cierre += x.dias_con_cierre
        total.dias_con_detalle += x.dias_con_detalle
    return total


def nombre_corto(nombre: str) -> str:
    """'Jose Luis Borja Ausencio' -> 'Jose L. B.' (chart labels): first name and initials."""
    partes = nombre.split(" · ")[-1].split()
    if len(partes) <= 1:
        return " ".join(partes) or nombre
    return " ".join([partes[0]] + [p[0] + "." for p in partes[1:3]])
