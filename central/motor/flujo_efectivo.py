"""Cash-flow report of the companies in Odoo (flujo de efectivo, Contabilidad).

Designed with the owner and the accountant (Tomás) on the September 2026 demo
(answers received 2026-11-04):

- Balance = bank and investment accounts (chart codes 102 / 103). Cash on
  hand and petty cash (101) stay out.
- Every posted line on those accounts inside the period is classified by
  what it was booked or reconciled against: the payment behind it (ticket
  sales by payment method, invoices, suppliers, group companies), the
  account of the journal entry (payroll, social security, taxes,
  commissions, partners) or, for bank lines booked straight against a
  "pagos / recibos pendientes" account, the text of the bank line.
- Sales are shown as real deposits: ticket sales plus the change of the
  "CxC bancos" accounts (106.01, sales recorded but not yet deposited), which
  the accountant books at the reconciliation.
- Payments of the branches to El Bodegón, Las Empanadas and Rodiva (royalties,
  equipment lease, supplies) are suppliers; those three companies are shown
  together, apart from the branches.
- Opening balance + inflows - outflows +- transfers = closing balance, to the
  peso, for every company: nothing is left out of the classification.

Pure logic (classification and assembly) is separated from the Odoo reads
(`fuentes/odoo_flujo.py`) so it can be tested without Odoo.
"""

import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from .fuentes.odoo_flujo import codigo
from .periodo import Periodo

TITULO = "Flujo de efectivo"
CERO = Decimal("0")

# -- scope ---------------------------------------------------------------------
# Odoo accounting is reliable from September 2026 for every company (owner,
# 2026-10-26); Isabel La Católica, San Jerónimo and Vía Vallejo started their
# accounting in Odoo in October 2026.
INICIO_CONTABLE = date(2026, 9, 1)
INICIO_POR_COMPANIA = {5: date(2026, 10, 1), 6: date(2026, 10, 1), 17: date(2026, 10, 1)}

# The group's non-restaurant companies, shown together (accountant: Rodiva is
# the branches' administrator and goes with El Bodegón and Las Empanadas).
CORPORATIVO = {2: "El Bodegón de Fito", 3: "Las Empanadas de María Eva", 1: "Grupo Hospitalario Rodiva"}
SUCURSAL, CORPORATIVO_GRUPO = "Sucursales", "CEDIS y administradora"

# -- rows of the statement (rubros) --------------------------------------------
VENTAS = "ventas"                    # ticket sales, detail = payment method
POR_DEPOSITAR = "por_depositar"      # change of the CxC bancos (106.01)
VENTAS_FACTURA = "ventas_factura"    # invoices to third parties (Rodiva, Bodegón)
COBROS_GRUPO = "cobros_grupo"        # collected from other group companies
APORTACIONES = "aportaciones"        # shareholder contributions (equity 301)
OTRAS_ENTRADAS = "otras_entradas"
PROVEEDORES = "proveedores"          # detail = expense group of the bills paid
RENTAS = "rentas"                    # own row (accountant, 2026-11-04)
NOMINA = "nomina"
SEGURIDAD_SOCIAL = "seguridad_social"
IMPUESTOS = "impuestos"
COMISIONES = "comisiones"
OTRAS_SALIDAS = "otras_salidas"
TRASPASOS = "traspasos"              # between own bank accounts
SIN_IDENTIFICAR = "sin_identificar"

ENTRADAS = [VENTAS, POR_DEPOSITAR, VENTAS_FACTURA, COBROS_GRUPO, APORTACIONES, OTRAS_ENTRADAS]
SALIDAS = [PROVEEDORES, RENTAS, NOMINA, SEGURIDAD_SOCIAL, IMPUESTOS, COMISIONES, OTRAS_SALIDAS]
NEUTROS = [TRASPASOS, SIN_IDENTIFICAR]
ETIQUETAS = {
    VENTAS: "Ventas de tickets (Wansoft)",
    POR_DEPOSITAR: "Ventas por depositar (CxC bancos)",
    VENTAS_FACTURA: "Ventas con factura",
    COBROS_GRUPO: "Cobros a empresas del grupo",
    APORTACIONES: "Aportaciones de socios",
    OTRAS_ENTRADAS: "Otras entradas",
    PROVEEDORES: "Proveedores",
    RENTAS: "Rentas y arrendamientos",
    NOMINA: "Nómina",
    SEGURIDAD_SOCIAL: "Seguridad social (IMSS, Infonavit)",
    IMPUESTOS: "Impuestos",
    COMISIONES: "Comisiones bancarias y de plataformas",
    OTRAS_SALIDAS: "Otras salidas",
    TRASPASOS: "Traspasos entre cuentas propias (neto)",
    SIN_IDENTIFICAR: "Movimientos bancarios sin identificar",
}

# Wansoft payment-method codes in the memo of Odoo's ticket payments
# ("Wansoft 182354 - 42682" = code 4 + the last digits of the account).
FORMAS_WANSOFT = {"1": "Efectivo", "2": "Dólares", "4": "Tarjeta de crédito", "5": "Tarjeta de débito", "6": "Amex",
                  "7": "CLIP", "8": "Uber Eats", "9": "Rappi", "11": "Transferencia", "12": "Didi", "14": "Total Play"}
ORDEN_FORMAS = ["Tarjeta de crédito", "Tarjeta de débito", "Efectivo", "Amex", "Uber Eats", "Rappi", "Didi"]

# Supplier expense groups by the name of the bill's account (accepted by the
# accountant). Rentas is matched first: it is its own row.
GRUPO_RENTAS = "Rentas y arrendamientos"
GRUPOS_GASTO = [
    (GRUPO_RENTAS, ("arrendamiento", "renta", "deposito en garant", "depósito en garant")),
    ("Insumos y mercancía", ("goods received", "carbon", "carbón", "hielo", "tortilla", "sin alcohol", "gastos de salon",
                             "gastos de salón", "empaque", "manteletas", "gas", "abarrote", "carne", "bebida", "cerveza",
                             "vino", "licor", "verdura", "pan", "inventario", "mercancía", "mercancia", "costo de venta")),
    # Rodiva's brand royalties and administration are billed as "Management Administrativo".
    ("Administración y regalías (Rodiva)", ("management", "regal", "administrativ")),
    ("Mantenimiento e instalaciones", ("mtto", "manten", "fumiga", "instalacion", "instalación", "remodel")),
    ("Servicios (luz, agua, teléfono, seguros, vigilancia)", ("energia", "energía", "agua", "telefono", "teléfono", "seguro",
                                                              "vigilancia", "soporte", "licencia", "internet", "logistica",
                                                              "logística")),
    ("Limpieza y artículos de operación", ("limpieza", "botiquin", "botiquín", "utencilio", "utensilio", "papeleria",
                                           "papelería")),
    ("Honorarios y asesorías", ("honorario", "asesor")),
    ("Publicidad", ("publicidad",)),
    ("Personal externo, uniformes y capacitación", ("suministro de personal", "uniforme", "curso", "vales", "capacita")),
    ("Equipo y activo fijo", ("equipo",)),
    ("Anticipos a proveedores", ("advance", "anticipo")),
]
OTROS_GASTOS = "Otros gastos"
SIN_FACTURA = "Pagos sin factura ligada"

# Bank lines booked straight against a pending account: their text says what they are.
TEXTOS = [
    (("ENTRECUENTA", "TRASPASO", "RECLASIFIC", "MORRALLA"), TRASPASOS, "Entre cuentas propias"),
    (("COMISION",), COMISIONES, "Comisiones bancarias y de plataformas"),
    (("IMSS", "INFONAVIT"), SEGURIDAD_SOCIAL, "IMSS e Infonavit"),
    (("NOMINA", "NÓMINA"), NOMINA, "Nómina"),
    (("IMPUEST", "SAT "), IMPUESTOS, "Impuestos"),
    (("INGRESO",), POR_DEPOSITAR, "Ingresos por conciliación"),
]


# -- classification (pure) -----------------------------------------------------
def forma_de_pago(memo: str | None) -> str | None:
    """Payment method of an Odoo ticket payment ("Wansoft <folio> - <forma>"),
    or None when the payment is not a Wansoft ticket."""
    texto = (memo or "").strip()
    if not texto.startswith("Wansoft") or " - " not in texto:
        return None
    forma = texto.split(" - ", 1)[1].strip()
    if forma.isdigit():
        return FORMAS_WANSOFT.get(forma[:-4], f"Código {forma}") if len(forma) > 4 else f"Código {forma}"
    return forma or "Sin forma de pago"


def grupo_gasto(nombre_cuenta: str) -> str:
    n = (nombre_cuenta or "").lower()
    for grupo, claves in GRUPOS_GASTO:
        # short keys are whole words ("gas" must not catch "gastos"), longer ones are word starts ("manten...")
        if any(re.search(rf"\b{re.escape(k)}\b" if len(k) <= 3 else rf"\b{re.escape(k)}", n) for k in claves):
            return grupo
    return OTROS_GASTOS


def es_pendiente(codigo: str, nombre: str) -> bool:
    """The bank's "pagos / recibos pendientes" and suspense accounts (102.01.05P,
    102.01.05R, 102.01.05T...): bridges, not a destination."""
    n = (nombre or "").lower()
    return bool(re.match(r"^10[23][\d.]*[A-Za-z]$", codigo or "")) or any(
        k in n for k in ("pendiente", "outstanding", "transitoria", "suspense"))


def por_cuenta(codigo: str, nombre: str, monto: Decimal) -> tuple[str, str] | None:
    """Row of a movement booked against this account (chart of accounts code
    first; names only where one code holds different things). None for the
    pending / bridge accounts: what is behind them decides."""
    c, n = codigo or "", (nombre or "").lower()
    if es_pendiente(c, nombre):
        return None
    if c.startswith(("102", "103")):
        return TRASPASOS, "Entre cuentas propias"
    if c.startswith("101"):
        return (OTRAS_ENTRADAS if monto > 0 else OTRAS_SALIDAS), "Caja y caja chica"
    if c.startswith("106.01"):
        return POR_DEPOSITAR, nombre
    if c.startswith("105"):
        return VENTAS_FACTURA, nombre
    if "infonavit" in n or "imss" in n or "cesant" in n or c.startswith(("216.11", "216.12", "601.26")):
        return SEGURIDAD_SOCIAL, nombre
    if c.startswith(("504.01.13", "701.10", "601.84.20")) or "comisi" in n:
        return COMISIONES, nombre
    if c.startswith(("210", "601.31", "601.84.10")) or re.match(r"^601\.(0\d|1[0-3])\.", c):
        return NOMINA, nombre
    if c.startswith(("109", "110", "113", "114", "118", "119", "208", "209", "213", "216", "601.29", "601.59")):
        return IMPUESTOS, nombre
    if c.startswith("201"):
        return PROVEEDORES, SIN_FACTURA
    if c.startswith("3"):
        return (APORTACIONES, nombre) if monto > 0 else (OTRAS_SALIDAS, f"Socios: {nombre}")
    return (OTRAS_ENTRADAS if monto > 0 else OTRAS_SALIDAS), nombre


def por_texto(texto: str | None) -> tuple[str, str]:
    t = (texto or "").upper()
    for claves, rubro, detalle in TEXTOS:
        if any(k in t for k in claves):
            return rubro, detalle
    return SIN_IDENTIFICAR, (texto or "Sin texto").strip()


def por_pago(pago: dict, socio_grupo: str | None, cuentas_factura: Counter) -> tuple[str, str]:
    """Row of a payment: inbound = sales (by payment method), invoices or
    group companies; outbound = suppliers by the account of the bills paid
    (group companies included: accountant, 2026-11-04)."""
    if pago["payment_type"] == "inbound":
        if socio_grupo:
            return COBROS_GRUPO, socio_grupo
        forma = forma_de_pago(pago.get("memo"))
        if forma:
            return VENTAS, forma
        if pago.get("partner_type") == "supplier":
            return OTRAS_ENTRADAS, "Reembolsos de proveedores"
        return VENTAS_FACTURA, (pago["partner_id"][1] if pago.get("partner_id") else "Sin cliente")
    if pago.get("partner_type") == "customer" and not socio_grupo:
        return OTRAS_SALIDAS, "Devoluciones a clientes"
    if not cuentas_factura:
        return PROVEEDORES, SIN_FACTURA
    grupo = grupo_gasto(cuentas_factura.most_common(1)[0][0])
    return (RENTAS, GRUPO_RENTAS) if grupo == GRUPO_RENTAS else (PROVEEDORES, grupo)


# -- data ----------------------------------------------------------------------
@dataclass(frozen=True)
class Movimiento:
    compania_id: int
    fecha: date
    diario: str
    rubro: str
    detalle: str
    socio: str
    monto: Decimal  # + into the bank, - out of it
    referencia: str = ""


@dataclass
class Cuenta:
    compania_id: int
    codigo: str
    nombre: str  # journal name when a journal uses it (account names were copied between companies)
    saldo_inicial: Decimal = CERO
    saldo_final: Decimal = CERO


@dataclass
class FlujoEmpresa:
    """One company in one period."""
    compania_id: int
    nombre: str
    grupo: str
    periodo: Periodo
    cuentas: list[Cuenta] = field(default_factory=list)
    movimientos: list[Movimiento] = field(default_factory=list)
    por_depositar_inicial: Decimal = CERO  # CxC bancos balance the day before
    por_depositar_final: Decimal = CERO
    ultimo_movimiento: date | None = None  # last bank line up to the period's end (statements loaded until then)

    @property
    def saldo_inicial(self) -> Decimal:
        return sum((c.saldo_inicial for c in self.cuentas), CERO)

    @property
    def saldo_final(self) -> Decimal:
        return sum((c.saldo_final for c in self.cuentas), CERO)


def _suma(empresas, rubros) -> Decimal:
    return sum((m.monto for e in empresas for m in e.movimientos if m.rubro in rubros), CERO)


@dataclass
class ReporteFlujo:
    """A report: one company, or several consolidated. `anteriores` holds the
    same companies in the previous period; None when it has no data (before
    the company's accounting start in Odoo)."""
    nombre: str
    periodo: Periodo
    empresas: list[FlujoEmpresa]
    anteriores: list[FlujoEmpresa] | None
    consolidado: bool = False
    notas: list[str] = field(default_factory=list)

    titulo = TITULO

    # figures of a list of companies (actual or previous)
    @staticmethod
    def cifras(empresas: list[FlujoEmpresa] | None) -> dict | None:
        if empresas is None:
            return None
        rubros = {r: _suma(empresas, [r]) for r in ENTRADAS + SALIDAS + NEUTROS}
        detalle = defaultdict(lambda: defaultdict(lambda: CERO))
        for e in empresas:
            for m in e.movimientos:
                detalle[m.rubro][m.detalle] += m.monto
        inicial = sum((e.saldo_inicial for e in empresas), CERO)
        final = sum((e.saldo_final for e in empresas), CERO)
        return {
            "saldo_inicial": inicial, "saldo_final": final, "neto": final - inicial,
            "entradas": sum((rubros[r] for r in ENTRADAS), CERO), "salidas": sum((rubros[r] for r in SALIDAS), CERO),
            "depositos": rubros[VENTAS] + rubros[POR_DEPOSITAR],
            "rubros": rubros, "detalle": {r: dict(d) for r, d in detalle.items()},
            "por_depositar_inicial": sum((e.por_depositar_inicial for e in empresas), CERO),
            "por_depositar_final": sum((e.por_depositar_final for e in empresas), CERO),
        }

    @property
    def actual(self) -> dict:
        return self.cifras(self.empresas)

    @property
    def anterior(self) -> dict | None:
        return self.cifras(self.anteriores)

    def proveedores(self, empresas=None, n: int = 25) -> list[tuple[str, Decimal]]:
        """Largest suppliers paid (suppliers and rentas rows), as positive amounts."""
        t = Counter()
        for e in empresas if empresas is not None else self.empresas:
            for m in e.movimientos:
                if m.rubro in (PROVEEDORES, RENTAS):
                    t[m.socio] += -m.monto
        return [(s, Decimal(v)) for s, v in t.most_common(n)]


# -- assembly from Odoo's raw records (pure) -------------------------------------
def _id(valor):
    return valor[0] if valor else None


class _Indice:
    """Lookups over the raw records of `odoo_flujo.detalle_de_movimientos`."""

    def __init__(self, crudo: dict, socios_grupo: dict[int, str]):
        self.movimientos = {m["id"]: m for m in crudo["movimientos"]}
        self.texto_extracto = {e["id"]: e.get("payment_ref") or "" for e in crudo["extractos"]}
        self.contra = defaultdict(list)
        for l in crudo["contra"]:
            self.contra[l["move_id"][0]].append(l)
        self.otro_lado = {l["id"]: l for l in crudo["otro_lado"]}
        self.parciales = defaultdict(list)
        for p in crudo["parciales"]:
            a, b, monto = p["debit_move_id"][0], p["credit_move_id"][0], Decimal(str(p["amount"]))
            self.parciales[a].append((b, monto))
            self.parciales[b].append((a, monto))
        self.lineas_asiento = defaultdict(list)
        for l in crudo["lineas_asiento"]:
            self.lineas_asiento[l["move_id"][0]].append(l)
        self.pagos = {p["id"]: p for p in crudo["pagos"]}
        self.cuentas_factura = defaultdict(Counter)
        self.cuentas = {c["id"]: c for c in crudo["cuentas"]}
        for l in crudo["lineas_factura"]:
            self.cuentas_factura[l["move_id"][0]][self.nombre_cuenta(l["account_id"][0], l["account_id"][1])] += abs(l["balance"])
        comercial = {s["id"]: _id(s["commercial_partner_id"]) for s in crudo["socios"]}
        self.socios_grupo = socios_grupo
        self.comercial = comercial

    def nombre_cuenta(self, cuenta_id: int, defecto: str = "") -> str:
        c = self.cuentas.get(cuenta_id)
        return c["name"] if c else defecto

    def codigo_cuenta(self, cuenta_id: int) -> str:
        c = self.cuentas.get(cuenta_id)
        return codigo(c) if c else ""

    def grupo_de(self, socio) -> str | None:
        """Group company name of a partner (or of its commercial partner)."""
        sid = _id(socio)
        if sid is None:
            return None
        return self.socios_grupo.get(sid) or self.socios_grupo.get(self.comercial.get(sid))

    def texto(self, movimiento: dict, linea: dict | None = None) -> str:
        sl = _id(movimiento.get("statement_line_id"))
        return self.texto_extracto.get(sl) or movimiento.get("ref") or (linea or {}).get("name") or ""

    def de_pago(self, pago_id: int) -> tuple[str, str, str]:
        p = self.pagos[pago_id]
        cuentas = Counter()
        for b in p.get("reconciled_bill_ids") or []:
            cuentas.update(self.cuentas_factura.get(b, {}))
        rubro, detalle = por_pago(p, self.grupo_de(p.get("partner_id")), cuentas)
        return rubro, detalle, (p["partner_id"][1] if p.get("partner_id") else "-")

    def de_cuenta(self, linea: dict, monto: Decimal, movimiento: dict) -> tuple[str, str]:
        cid, nombre = linea["account_id"][0], linea["account_id"][1]
        r = por_cuenta(self.codigo_cuenta(cid), self.nombre_cuenta(cid, nombre), monto)
        return r if r is not None else por_texto(self.texto(movimiento, linea))

    def del_otro_lado(self, otra: dict, monto: Decimal, movimiento: dict, linea: dict) -> tuple[str, str, str]:
        """Explain a piece of a bank movement by the line it was reconciled with."""
        socio = otra["partner_id"][1] if otra.get("partner_id") else "-"
        if otra.get("payment_id") and otra["payment_id"][0] in self.pagos:
            return self.de_pago(otra["payment_id"][0])
        if otra.get("statement_line_id"):
            return TRASPASOS, "Entre cuentas propias", "-"
        tipo = otra.get("move_type")
        if tipo in ("in_invoice", "in_refund"):
            cuentas = self.cuentas_factura.get(otra["move_id"][0], Counter())
            grupo = grupo_gasto(cuentas.most_common(1)[0][0]) if cuentas else SIN_FACTURA
            return ((RENTAS, GRUPO_RENTAS) if grupo == GRUPO_RENTAS else (PROVEEDORES, grupo)) + (socio,)
        if tipo in ("out_invoice", "out_refund"):
            grupo = self.grupo_de(otra.get("partner_id"))
            return (COBROS_GRUPO, grupo, socio) if grupo else (VENTAS_FACTURA, socio, socio)
        # a plain journal entry: its other accounts tell what it is
        otras = [l for l in self.lineas_asiento.get(otra["move_id"][0], [])
                 if l["account_id"][0] not in (otra["account_id"][0], linea["account_id"][0])]
        for l in sorted(otras, key=lambda l: -abs(l["balance"])):
            r = por_cuenta(self.codigo_cuenta(l["account_id"][0]), self.nombre_cuenta(l["account_id"][0], l["account_id"][1]), monto)
            if r is not None:
                return r + ("-",)
        return por_texto(self.texto(movimiento, linea)) + ("-",)


def clasificar(lineas_banco: list[dict], crudo: dict, socios_grupo: dict[int, str], diario_de: dict) -> list[Movimiento]:
    """Split every bank line of the period into classified movements. A move's
    bank lines share its other lines in proportion to their amounts, and each
    other line in proportion to what it was reconciled with, so the pieces of
    a bank line always add up to it."""
    ix = _Indice(crudo, socios_grupo)
    banco_por_mov = defaultdict(list)
    for l in lineas_banco:
        banco_por_mov[l["move_id"][0]].append(l)
    salida = []
    for mov_id, bancos in banco_por_mov.items():
        mov = ix.movimientos.get(mov_id, {"id": mov_id})
        total_banco = sum((Decimal(str(l["balance"])) for l in bancos), CERO)
        contras = ix.contra.get(mov_id, [])
        for b in bancos:
            monto_b = Decimal(str(b["balance"]))
            base = dict(compania_id=b["company_id"][0], fecha=date.fromisoformat(b["date"]),
                        diario=diario_de.get((b["company_id"][0], b["account_id"][0]), b["journal_id"][1]),
                        referencia=ix.texto(mov, b)[:120])
            if not contras or total_banco == 0:
                if mov.get("origin_payment_id") and mov["origin_payment_id"][0] in ix.pagos:
                    rubro, detalle, socio = ix.de_pago(mov["origin_payment_id"][0])
                else:
                    rubro, detalle, socio = TRASPASOS, "Entre cuentas propias", "-"
                salida.append(Movimiento(rubro=rubro, detalle=detalle, socio=socio, monto=monto_b, **base))
                continue
            factor = monto_b / total_banco
            for c in contras:
                pieza = -Decimal(str(c["balance"])) * factor
                if pieza == 0:
                    continue
                saldo_c = abs(Decimal(str(c["balance"])))
                parciales = ix.parciales.get(c["id"], [])
                conciliado = min(sum((a for _, a in parciales), CERO), saldo_c)
                for otra_id, a in parciales:
                    otra = ix.otro_lado.get(otra_id)
                    if otra is None or saldo_c == 0:
                        continue
                    parte = pieza * a / saldo_c
                    rubro, detalle, socio = ix.del_otro_lado(otra, parte, mov, c)
                    salida.append(Movimiento(rubro=rubro, detalle=detalle, socio=socio, monto=parte, **base))
                resto = pieza * (1 - conciliado / saldo_c) if saldo_c else pieza
                if resto:
                    rubro, detalle = ix.de_cuenta(c, resto, mov)
                    socio = c["partner_id"][1] if c.get("partner_id") else "-"
                    salida.append(Movimiento(rubro=rubro, detalle=detalle, socio=socio, monto=resto, **base))
    return salida


def es_cuenta_de_efectivo(codigo: str) -> bool:
    """Bank and investment accounts count (102, 103); cash on hand (101) does not."""
    return (codigo or "").startswith(("102", "103")) and not es_pendiente(codigo, "")


def inicio_de(compania_id: int) -> date:
    return INICIO_POR_COMPANIA.get(compania_id, INICIO_CONTABLE)


def empresa(compania_id: int, nombre: str, grupo: str, periodo: Periodo, cuentas: list[dict], lineas: list[dict],
            movimientos: list[Movimiento], lineas_cxc: list[dict]) -> FlujoEmpresa:
    """A company's figures in one period from its accounts, all its bank lines
    up to the end of the period, its classified movements and its CxC lines."""
    ce = {c["account_id"]: c for c in cuentas if c["company_id"] == compania_id and es_cuenta_de_efectivo(c["codigo"])}
    saldos = {aid: [CERO, CERO] for aid in ce}
    ultimo = None
    for l in lineas:
        if l["company_id"][0] != compania_id or l["account_id"][0] not in saldos:
            continue
        d, v = date.fromisoformat(l["date"]), Decimal(str(l["balance"]))
        if d <= periodo.hasta and (ultimo is None or d > ultimo):
            ultimo = d
        if d < periodo.desde:
            saldos[l["account_id"][0]][0] += v
        if d <= periodo.hasta:
            saldos[l["account_id"][0]][1] += v
    lista = [Cuenta(compania_id, ce[aid]["codigo"], ce[aid]["diario"] or ce[aid]["cuenta"], s0, s1)
             for aid, (s0, s1) in saldos.items() if s0 or s1]
    lista.sort(key=lambda c: c.codigo)
    cxc0 = sum((Decimal(str(l["balance"])) for l in lineas_cxc
                if l["company_id"][0] == compania_id and date.fromisoformat(l["date"]) < periodo.desde), CERO)
    cxc1 = sum((Decimal(str(l["balance"])) for l in lineas_cxc
                if l["company_id"][0] == compania_id and date.fromisoformat(l["date"]) <= periodo.hasta), CERO)
    movs = [m for m in movimientos if m.compania_id == compania_id and periodo.desde <= m.fecha <= periodo.hasta]
    return FlujoEmpresa(compania_id, nombre, grupo, periodo, lista, movs, cxc0, cxc1, ultimo)


REGLAS = [
    "Fuente: Odoo, lectura en vivo (solo lectura). Saldo = cuentas de bancos e inversiones (códigos 102 y 103 del catálogo) al "
    "cierre del día; la caja y la caja chica (101) no se incluyen. Cada cuenta se muestra con el nombre de su diario.",
    "Entradas y salidas = cada movimiento de esas cuentas en el periodo, clasificado por lo que concilia: el pago (cliente, "
    "proveedor, empresa del grupo), la cuenta del asiento (nómina 210/601, seguridad social 216.11-216.12 e Infonavit, "
    "impuestos, comisiones 504.01.13/701.10, socios 301) o, si la línea del banco se registró directo contra 'pagos / recibos "
    "pendientes', su texto (ej. 'ENTRECUENTAS' = traspaso). Saldo inicial + entradas − salidas ± traspasos = saldo final.",
    "Depósitos de ventas = ventas de tickets de Wansoft (el pago de cada ticket que Odoo registra, por forma de pago) más el "
    "cambio de las cuentas por cobrar bancos (106.01: ventas registradas que el banco aún no deposita). Las propinas no están en "
    "la contabilidad y no se muestran.",
    "Proveedores: por la cuenta contable de las facturas que pagan; las rentas y arrendamientos van en su renglón. Los pagos de "
    "las sucursales a El Bodegón, Las Empanadas y Rodiva (insumos, arrendamiento de equipo, regalías) son proveedores; en el "
    "consolidado cuentan como salida de una empresa y entrada de otra, no se eliminan.",
    "Comparación: contra el periodo anterior (la contabilidad en Odoo empieza en septiembre de 2026; no hay año anterior).",
]
# A company whose last bank movement is more than this many days before the
# period's end probably has its statements not loaded yet (reconciliation is
# on Tuesdays, accountant 2026-11-04): the report says so.
DIAS_ATRASO = 3
NOTA_CIERRE = ("El periodo no termina en un cierre de mes: las comisiones bancarias y de plataformas y el ajuste de ventas "
               "por depositar se registran al cierre del mes, así que aún pueden faltar.")


def notas_de(r: ReporteFlujo) -> list[str]:
    """The report's notes: what applies to this report, then the standing rules."""
    notas = list(r.notas)
    fin_de_mes = (r.periodo.hasta.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if r.periodo.hasta != fin_de_mes:
        notas.append(NOTA_CIERRE)
    atrasadas = [e for e in r.empresas if e.ultimo_movimiento is None or (r.periodo.hasta - e.ultimo_movimiento).days > DIAS_ATRASO]
    if atrasadas:
        notas.append("Bancos posiblemente sin cargar al cierre del periodo (último movimiento bancario en Odoo): " + ", ".join(
            f"{e.nombre} ({e.ultimo_movimiento:%d/%m/%Y})" if e.ultimo_movimiento else f"{e.nombre} (ninguno)" for e in atrasadas) + ".")
    a = r.actual
    if a["rubros"][SIN_IDENTIFICAR]:
        notas.append(f"Movimientos bancarios sin identificar: líneas de banco registradas contra 'pagos / recibos pendientes' "
                     f"que no concilian con nada y cuyo texto no dice qué son (neto {a['rubros'][SIN_IDENTIFICAR]:,.0f}).")
    if a["por_depositar_final"]:
        notas.append(f"Ventas por depositar al cierre (cuentas por cobrar bancos): ${a['por_depositar_final']:,.0f}; "
                     f"al inicio ${a['por_depositar_inicial']:,.0f}.")
    if r.anteriores is None:
        notas.append("Sin periodo anterior comparable (antes del inicio de la contabilidad en Odoo).")
    return notas + REGLAS


def nombre_base(reportes: list[ReporteFlujo]) -> str:
    quien = reportes[0].nombre if len(reportes) == 1 else f"{len(reportes)} empresas"
    limpio = "".join(ch if ch.isalnum() else "_" for ch in f"Flujo_de_efectivo_{quien}_{reportes[0].periodo.etiqueta()}")
    return "_".join(p for p in limpio.split("_") if p)


# -- reading Odoo -----------------------------------------------------------------
def empresas_de(sucursales: list, incluir_corporativo: bool = True) -> tuple[list[tuple[int, str, str]], list[str]]:
    """(company id, name, group) of the branches with an Odoo company, then the
    corporate companies; and the names of the branches left out (no Odoo company)."""
    elegidas, fuera = [], []
    for s in sucursales:
        if s.odoo_company_id:
            elegidas.append((s.odoo_company_id, s.nombre, SUCURSAL))
        else:
            fuera.append(s.nombre)
    if incluir_corporativo:
        elegidas += [(cid, nombre, CORPORATIVO_GRUPO) for cid, nombre in CORPORATIVO.items()
                     if cid not in {e[0] for e in elegidas}]
    return elegidas, fuera


# An automation builds the consolidated and the per-company files of the same
# period one after the other; reading Odoo takes minutes, so a read is reused
# for a short while (same companies and period).
CACHE_SEGUNDOS = 600
_cache: dict[tuple, tuple[float, tuple]] = {}


def leer(empresas: list[tuple[int, str, str]], periodo: Periodo) -> tuple[list[FlujoEmpresa], list[FlujoEmpresa]]:
    """`_leer` with a short-lived cache."""
    clave = (tuple(sorted(empresas)), periodo)
    guardado = _cache.get(clave)
    if guardado and time.monotonic() - guardado[0] < CACHE_SEGUNDOS:
        return guardado[1]
    for k in [k for k, (t, _) in _cache.items() if time.monotonic() - t >= CACHE_SEGUNDOS]:
        del _cache[k]
    resultado = _leer(empresas, periodo)
    _cache[clave] = (time.monotonic(), resultado)
    return resultado


def _leer(empresas: list[tuple[int, str, str]], periodo: Periodo) -> tuple[list[FlujoEmpresa], list[FlujoEmpresa]]:
    """Read Odoo once for the period and the previous one; return each
    company's figures in both (previous = [] for companies without data)."""
    from .fuentes import odoo, odoo_flujo

    anterior = periodo.anterior()
    ids = [e[0] for e in empresas]
    cli = odoo.abrir_odoo()
    cuentas = odoo_flujo.cuentas_de_efectivo(cli, ids)
    efectivo = [c for c in cuentas if es_cuenta_de_efectivo(c["codigo"])]
    diario_de = {(c["company_id"], c["account_id"]): c["diario"] or c["cuenta"] for c in efectivo}
    lineas = odoo_flujo.lineas_de_cuentas(cli, ids, [c["account_id"] for c in efectivo], periodo.hasta)
    del_rango = [l for l in lineas if anterior.desde <= date.fromisoformat(l["date"]) <= periodo.hasta]
    excluidas = {c["account_id"] for c in efectivo}
    crudo = odoo_flujo.detalle_de_movimientos(cli, [l["move_id"][0] for l in del_rango], excluidas)
    movimientos = clasificar(del_rango, crudo, odoo_flujo.socios_del_grupo(cli), diario_de)
    cxc_ids = odoo_flujo.cuentas_por_codigo(cli, ids, "106.01")
    lineas_cxc = odoo_flujo.lineas_de_cuentas(cli, ids, [a for v in cxc_ids.values() for a in v], periodo.hasta)
    actuales, previas = [], []
    for cid, nombre, grupo in empresas:
        actuales.append(empresa(cid, nombre, grupo, periodo, cuentas, lineas, movimientos, lineas_cxc))
        if anterior.desde >= inicio_de(cid):
            previas.append(empresa(cid, nombre, grupo, anterior, cuentas, lineas, movimientos, lineas_cxc))
    return actuales, previas


def armar(sucursales: list, periodo: Periodo, consolidado: bool, incluir_corporativo: bool = True) -> list[ReporteFlujo]:
    """The reports for these branches (plus El Bodegón, Las Empanadas and
    Rodiva unless left out): one consolidated, or one per company."""
    empresas, fuera = empresas_de(sucursales, incluir_corporativo)
    notas = []
    if fuera:
        notas.append(f"Sin contabilidad en Odoo, no incluidas: {', '.join(fuera)}.")
    tarde = [e for e in empresas if inicio_de(e[0]) > periodo.hasta]
    if tarde:
        notas.append("Aún sin contabilidad en Odoo en este periodo: "
                     + ", ".join(f"{n} (desde {inicio_de(c):%d/%m/%Y})" for c, n, _ in tarde) + ".")
    empresas = [e for e in empresas if e not in tarde]
    if not empresas:
        return [ReporteFlujo("Sin empresas", periodo, [], None, consolidado, notas)]
    actuales, previas = leer(empresas, periodo)
    previa_de = {e.compania_id: e for e in previas}
    if consolidado:
        anteriores = previas if len(previas) == len(actuales) else None
        if anteriores is None and previas:
            notas.append("Sin periodo anterior comparable para todas las empresas: la columna anterior no se muestra.")
        return [ReporteFlujo("Consolidado", periodo, actuales, anteriores, True, notas)]
    return [ReporteFlujo(e.nombre, periodo, [e], [previa_de[e.compania_id]] if e.compania_id in previa_de else None,
                         False, list(notas)) for e in actuales]
