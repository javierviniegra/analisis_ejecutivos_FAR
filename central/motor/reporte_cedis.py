"""CEDIS reports: purchase orders from the branches to the internal providers
(El Bodegón de Fito, Las Empanadas de María Eva) and how they change after
being confirmed. Reproduces the owner's two Excel reports (2026-09-23):
"modificaciones" and "por hora".

Rules (from those reports' Notes sheets, now code):
- only confirmed orders ('purchase'/'done'); no drafts, RFQs or cancelled;
  orders Odoo generated automatically from the provider's sales order are
  excluded (the branch did not send them);
- each branch counts only from the date it started buying in Odoo (Wansoft
  project's `dim_company_analytical`, read live);
- only changes recorded in Odoo AFTER the order was confirmed count:
  quantity changes (note "Se actualizó la cantidad ordenada", old -> new per
  product), extra lines ("Línea extra con ...": a product that was not in the
  order), and changes of the untaxed amount (tracked field);
- "modified" has two definitions, as in the owner's two reports: in
  "modificaciones" any change after confirming (quantity, extra line or
  amount); in "por hora" a change of the order's amount or an extra line;
- changes are counted up to the moment the report is read (the notes say
  when; checked 2026-09-30 against the owner's Excel cut at 22-Sep 17:16:
  same figures, including the amounts, for 5 of 6 branches and one order off
  in the sixth, a change within the cut minute);
- hours are Mexico City time; the hour of an order is its creation hour.

`leer` reads the sources (read-only); everything else is pure.
"""

import html
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

BODEGON, EMPANADAS = "EL BODEGON DE FITO", "LAS EMPANADAS DE MARIA EVA"
SUCURSAL, CEDIS = "Sucursal", "CEDIS"
DE_OC, DIRECTO = "OC de sucursal (Odoo)", "Captura del CEDIS"
AUMENTO, DISMINUCION = "Aumento", "Disminucion"

_CANTIDAD = re.compile(r"([^:]+?):\s*Cantidad ordenada:\s*([\d.,]+)\s*->\s*([\d.,]+)")
_LINEA_EXTRA = re.compile(r"L[ií]nea (?:extra|adicional) con\s+(.+)")


@dataclass
class CambioCantidad:
    fecha: datetime
    usuario: str
    producto: str
    anterior: Decimal
    nueva: Decimal
    precio: Decimal | None
    hecho_por: str = ""  # SUCURSAL / CEDIS

    @property
    def diferencia(self) -> Decimal:
        return self.nueva - self.anterior

    @property
    def tipo(self) -> str:
        return AUMENTO if self.diferencia > 0 else DISMINUCION

    @property
    def impacto(self) -> Decimal | None:
        return self.diferencia * self.precio if self.precio is not None else None


@dataclass
class LineaExtra:
    fecha: datetime
    usuario: str
    producto: str
    pedida: Decimal | None
    recibida: Decimal | None
    precio: Decimal | None
    hecho_por: str = ""

    @property
    def subtotal(self) -> Decimal | None:
        return self.pedida * self.precio if self.pedida is not None and self.precio is not None else None


@dataclass
class CambioMonto:
    fecha: datetime
    usuario: str
    anterior: Decimal
    nuevo: Decimal
    hecho_por: str = ""

    @property
    def diferencia(self) -> Decimal:
        return self.nuevo - self.anterior


@dataclass
class Orden:
    nombre: str
    sucursal: str
    proveedor: str
    estado: str
    creada: datetime
    confirmada: datetime | None
    monto_final: Decimal
    cantidades: list[CambioCantidad] = field(default_factory=list)
    extras: list[LineaExtra] = field(default_factory=list)
    montos: list[CambioMonto] = field(default_factory=list)
    origen: str = DE_OC  # the branch's purchase order, or captured directly by the CEDIS

    def cambios(self):
        return [*self.cantidades, *self.extras, *self.montos]

    def modificada_por(self, quien: str) -> bool:
        return any(c.hecho_por == quien for c in self.cambios())

    @property
    def modificada(self) -> bool:
        """"modificaciones" definition: any change after confirming."""
        return bool(self.cantidades or self.extras or self.montos)

    @property
    def modificada_subtotal(self) -> bool:
        """"por hora" definition: its amount changed or an extra line was added."""
        return bool(self.montos or self.extras)

    @property
    def monto_al_confirmar(self) -> Decimal:
        return self.monto_final - sum((m.diferencia for m in self.montos), Decimal("0"))

    @property
    def diferencia(self) -> Decimal:
        return self.monto_final - self.monto_al_confirmar

    def horas_despues(self, fecha: datetime) -> float | None:
        return round((fecha - self.confirmada).total_seconds() / 3600, 1) if self.confirmada else None


@dataclass
class DatosCedis:
    desde: date
    hasta: date
    ordenes: list[Orden]
    sucursales: list[str]  # in display order
    inicio_por_sucursal: dict[str, date]
    auto_generadas: int  # excluded orders generated from the provider's sales order
    leido_en: datetime | None = None  # when Odoo was read (Mexico City time)
    antes_de_inicio: int = 0  # orders left out because they predate their branch's Odoo start
    excluidas_cliente: int = 0  # provider orders of excluded customers (Público general, CEDIS to CEDIS)
    sin_asignar: dict[str, int] = field(default_factory=dict)  # Odoo customer -> orders, not mapped yet
    notas_clientes: list[str] = field(default_factory=list)  # e.g. internal deliveries


def _numero(texto: str) -> Decimal:
    return Decimal(texto.replace(",", ""))


def _texto(cuerpo: str | bool) -> str:
    """Odoo message body (HTML) -> plain text on one line."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", cuerpo or "")).split())


def interpretar(orden: Orden, mensajes: list[dict], montos: dict[int, tuple[Decimal, Decimal]],
                lineas_por_producto: dict[str, dict], a_cdmx, quien=lambda autor_id: "") -> Orden:
    """Fill the order's post-confirmation changes from its chatter.
    `montos`: message id -> (old, new) untaxed amount; `lineas_por_producto`:
    product name -> order line (price, ordered and received quantity)."""
    for msg in mensajes:
        fecha = a_cdmx(msg["date"])
        if orden.confirmada is None or fecha <= orden.confirmada:
            continue  # only changes after confirming count
        usuario = msg["author_id"][1] if msg.get("author_id") else ""
        hecho_por = quien(msg["author_id"][0] if msg.get("author_id") else None)
        texto = _texto(msg.get("body"))
        if "cantidad ordenada" in texto.lower():
            cuerpo = texto.split(".", 1)[1] if "." in texto else texto
            for producto, anterior, nueva in _CANTIDAD.findall(cuerpo):
                producto = producto.strip()
                linea = lineas_por_producto.get(producto, {})
                orden.cantidades.append(CambioCantidad(fecha, usuario, producto, _numero(anterior), _numero(nueva),
                                                       linea.get("precio"), hecho_por))
        elif (extra := _LINEA_EXTRA.search(texto)):
            producto = extra.group(1).strip()
            linea = lineas_por_producto.get(producto, {})
            orden.extras.append(LineaExtra(fecha, usuario, producto, linea.get("pedida"), linea.get("recibida"),
                                           linea.get("precio"), hecho_por))
        if msg["id"] in montos:
            anterior, nuevo = montos[msg["id"]]
            orden.montos.append(CambioMonto(fecha, usuario, anterior, nuevo, hecho_por))
    return orden


# -- tables of the "modificaciones" workbook --------------------------------------
def resumen(datos: DatosCedis) -> list[dict]:
    grupos = defaultdict(list)
    for o in datos.ordenes:
        grupos[(o.proveedor, o.sucursal)].append(o)
    filas = []
    for proveedor in (BODEGON, EMPANADAS):
        for suc in datos.sucursales:
            ords = grupos.get((proveedor, suc))
            if not ords:
                continue
            mods = [o for o in ords if o.modificada]
            filas.append(dict(proveedor=proveedor, sucursal=suc, ordenes=len(ords), modificadas=len(mods),
                              pct=Decimal(len(mods)) / len(ords),
                              con_cantidad=sum(1 for o in ords if o.cantidades),
                              con_extras=sum(1 for o in ords if o.extras),
                              con_monto=sum(1 for o in ords if o.montos),
                              por_sucursal=sum(1 for o in ords if o.modificada_por(SUCURSAL)),
                              por_cedis=sum(1 for o in ords if o.modificada_por(CEDIS)),
                              diferencia=sum((o.diferencia for o in mods), Decimal("0"))))
    return filas


def total_resumen(filas: list[dict]) -> dict:
    """Total row of a provider's block (or of any set of summary rows)."""
    ordenes, modificadas = sum(f["ordenes"] for f in filas), sum(f["modificadas"] for f in filas)
    return dict(proveedor=None, sucursal="Total", ordenes=ordenes, modificadas=modificadas,
                pct=Decimal(modificadas) / ordenes if ordenes else None,
                con_cantidad=sum(f["con_cantidad"] for f in filas), con_extras=sum(f["con_extras"] for f in filas),
                con_monto=sum(f["con_monto"] for f in filas), por_sucursal=sum(f["por_sucursal"] for f in filas),
                por_cedis=sum(f["por_cedis"] for f in filas), diferencia=sum((f["diferencia"] for f in filas), Decimal("0")))


def productos_mas_cambiados(datos: DatosCedis) -> list[dict]:
    acumulado = defaultdict(lambda: dict(cambios=0, aumentos=0, disminuciones=0, impacto=Decimal("0")))
    for o in datos.ordenes:
        for c in o.cantidades:
            a = acumulado[(o.proveedor, c.producto, "Cambio de cantidad")]
            a["cambios"] += 1
            a["aumentos" if c.tipo == AUMENTO else "disminuciones"] += 1
            a["impacto"] += c.impacto or 0
        for e in o.extras:
            a = acumulado[(o.proveedor, e.producto, "Linea extra")]
            a["cambios"] += 1
            a["aumentos"] += 1
            a["impacto"] += e.subtotal or 0
    filas = [dict(proveedor=p, producto=prod, tipo=t, **v) for (p, prod, t), v in acumulado.items()]
    return sorted(filas, key=lambda f: (-f["cambios"], f["producto"]))


# -- tables of the "por hora" workbook -------------------------------------------
HORAS = list(range(24))


def etiqueta_hora(h: int) -> str:
    return f"{h:02d}:00 - {h:02d}:59"


def por_hora(datos: DatosCedis, proveedor: str | None = None, solo_modificadas: bool = False) -> dict[int, dict[str, int]]:
    """Orders per creation hour and branch (optionally one provider / only modified)."""
    tabla = {h: defaultdict(int) for h in HORAS}
    for o in datos.ordenes:
        if (proveedor and o.proveedor != proveedor) or (solo_modificadas and not o.modificada_subtotal):
            continue
        tabla[o.creada.hour][o.sucursal] += 1
    return tabla


def pct_modificaciones(datos: DatosCedis) -> list[dict]:
    filas = []
    for suc in datos.sucursales:
        ords = [o for o in datos.ordenes if o.sucursal == suc]
        if not ords:
            continue
        b = [o for o in ords if o.proveedor == BODEGON]
        e = [o for o in ords if o.proveedor == EMPANADAS]
        mb, me = sum(o.modificada_subtotal for o in b), sum(o.modificada_subtotal for o in e)
        filas.append(dict(sucursal=suc, ordenes=len(ords), modificadas=mb + me, pct=Decimal(mb + me) / len(ords),
                          ordenes_bodegon=len(b), modif_bodegon=mb, ordenes_empanadas=len(e), modif_empanadas=me,
                          pct_bodegon=Decimal(mb) / len(b) if b else None, pct_empanadas=Decimal(me) / len(e) if e else None))
    return filas


def total_pct_modificaciones(filas: list[dict]) -> dict:
    suma = {k: sum(f[k] for f in filas) for k in ("ordenes", "modificadas", "ordenes_bodegon", "modif_bodegon",
                                                  "ordenes_empanadas", "modif_empanadas")}
    razon = lambda a, b: Decimal(a) / b if b else None  # noqa: E731
    return dict(sucursal="Total", **suma, pct=razon(suma["modificadas"], suma["ordenes"]),
                pct_bodegon=razon(suma["modif_bodegon"], suma["ordenes_bodegon"]),
                pct_empanadas=razon(suma["modif_empanadas"], suma["ordenes_empanadas"]))


def detalle_cambios(o: Orden) -> str | None:
    """One text with the order's changes after confirming (newest first)."""
    partes = [(m.fecha, f"Monto {m.anterior:,.2f} -> {m.nuevo:,.2f}") for m in o.montos]
    partes += [(e.fecha, f"Linea extra con {e.producto}") for e in o.extras]
    return " | ".join(t for _, t in sorted(partes, key=lambda p: p[0], reverse=True)) or None


def notas(datos: DatosCedis, libro: str) -> list[str]:
    """Notes of each workbook ("modificaciones" or "por hora"), as in the owner's reports."""
    inicios = "; ".join(f"{s} desde {d:%d/%m/%Y}" for s, d in sorted(datos.inicio_por_sucursal.items()))
    leido = f" Datos de Odoo al {datos.leido_en:%d/%m/%Y %H:%M} (CDMX)." if datos.leido_en else ""
    comunes = [
        f"Periodo: órdenes creadas del {datos.desde:%d/%m/%Y} al {datos.hasta:%d/%m/%Y} (hora de la Ciudad de México); "
        f"cada sucursal cuenta desde su inicio de compras en Odoo: {inicios}.{leido}",
        f"Proveedores: {BODEGON} y {EMPANADAS}.",
        "Solo órdenes confirmadas (estado 'purchase' o 'done'); se excluyen borradores, solicitudes de cotización y canceladas.",
        f"Se excluyen {datos.auto_generadas} órdenes generadas automáticamente desde un pedido de venta del proveedor "
        "(no las envió la sucursal).",
        f"Se excluyen {datos.antes_de_inicio} órdenes creadas antes de la fecha de inicio en Odoo de su sucursal, y "
        f"{datos.excluidas_cliente} pedidos de clientes excluidos (Público general, ventas entre CEDIS).",
        f"Todas las sucursales, desde el lado del proveedor: las que compran en Odoo con su orden de compra "
        f"({DE_OC}); las demás, con el pedido que captura el CEDIS ({DIRECTO}), asignado a la sucursal por el "
        "cliente o la dirección de entrega (tabla editable en el admin). Cada orden se cuenta una vez.",
        "Hecho por: CEDIS si el usuario de Odoo que hizo el cambio pertenece a El Bodegón o Las Empanadas; "
        "si no, la sucursal.",
    ] + datos.notas_clientes + ([
        "Clientes de Odoo sin asignar a una sucursal (fuera del reporte hasta asignarlos en el admin): "
        + "; ".join(f"{n} ({k} pedidos)" for n, k in sorted(datos.sin_asignar.items())) + "."] if datos.sin_asignar else [])
    if libro == "por_hora":
        return comunes + [
            "Hora = hora de creación de la orden, convertida de UTC a la Ciudad de México (UTC-6).",
            "Modificada = después de confirmar la orden cambió su subtotal o se le agregó una 'línea extra'.",
            "Fuente: Odoo, solo lectura.",
        ]
    return comunes + [
        "Solo cuentan los cambios registrados en Odoo DESPUÉS de confirmar la orden; modificada = cualquier cambio "
        "(cantidad, línea extra o monto).",
        "Cambios de cantidad: nota de Odoo 'Se actualizó la cantidad ordenada' por producto (anterior -> nueva); "
        "impacto = diferencia × precio unitario de la línea (sin IVA).",
        "Líneas extra: producto que no venía en la orden y se agregó después ('Línea extra con ...').",
        "Cambios de monto: cambios del subtotal sin IVA de la orden; diferencia neta = monto final - monto al confirmar.",
        "Usuario = quien hizo el cambio, tal como lo registra Odoo. Fuente: Odoo, solo lectura.",
    ]


# -- reading (read-only) -----------------------------------------------------------
def _cliente_de(pedido: dict, clientes: dict):
    """The mapping row that decides the order: the delivery address wins over
    the customer; None when neither is mapped (nor excluded)."""
    for campo in ("partner_shipping_id", "partner_id"):
        pid = pedido[campo][0] if pedido[campo] else None
        fila = clientes.get(pid)
        if fila is not None and (fila.excluir or fila.nombre_reporte):
            return fila
    return None


def leer(sucursales: list, desde: date, hasta: date) -> DatosCedis:
    """Read, from the provider side, every order to El Bodegón / Las Empanadas
    created in [desde, hasta] for these branches (`cuentas.Sucursal`), and
    their change history (read-only on Odoo and Wansoft).

    - A sales order generated from a branch's purchase order (branches on Odoo)
      is read from that purchase order, as the owner's original report; the
      branch counts only from its Odoo purchases start.
    - Any other sales order was captured by the CEDIS: its branch comes from the
      delivery address or the customer (`ClienteCedis`). Customers that are not
      one of our branches (e.g. Perisur, León) appear only when every active
      branch is selected.
    """
    from central.models import ClienteCedis
    from cuentas.models import Sucursal

    from .fuentes import conexiones, odoo, wansoft

    with conexiones.abrir_wansoft() as cur:
        inicios = wansoft.inicio_compras_odoo(cur)
        inicio_proveedor = wansoft.inicio_proveedores_internos(cur)
    elegidas = {s.pk for s in sucursales}
    todas = elegidas >= set(Sucursal.objects.filter(activa=True).values_list("pk", flat=True))
    por_compania = {s.odoo_company_id: s for s in sucursales if s.odoo_company_id and s.wansoft_ticket_nombre in inicios}
    datos = DatosCedis(desde, hasta, [], [], {s.nombre: inicios[s.wansoft_ticket_nombre] for s in por_compania.values()}, 0)

    cli = odoo.abrir_odoo()
    datos.leido_en = datetime.utcnow() + odoo.UTC_A_CDMX
    proveedores = odoo.proveedores_internos(cli)
    companias = odoo.companias_de(cli, list(proveedores))
    nombre_compania = {c["id"]: c["name"] for c in cli.llamar("res.company", "read", companias, fields=["name"])}
    clientes = {c.odoo_partner_id: c for c in ClienteCedis.objects.select_related("sucursal")}

    de_oc, directos = [], []
    for p in odoo.pedidos_venta(cli, companias, desde, hasta):
        proveedor = nombre_compania[p["company_id"][0]]
        if proveedor in inicio_proveedor and odoo.a_cdmx(p["create_date"]).date() < inicio_proveedor[proveedor]:
            continue  # before the provider started in Odoo
        (de_oc if p["auto_purchase_order_id"] else directos).append(p)

    # 1) orders generated from a branch's purchase order: read the purchase order
    crudas = odoo.ordenes_por_id(cli, [p["auto_purchase_order_id"][0] for p in de_oc]) if de_oc else []
    en_seleccion = [o for o in crudas if o["company_id"][0] in por_compania]
    validas = [o for o in en_seleccion if odoo.a_cdmx(o["create_date"]).date()
               >= datos.inicio_por_sucursal[por_compania[o["company_id"][0]].nombre]]
    datos.antes_de_inicio = len(en_seleccion) - len(validas)

    # 2) orders captured by the CEDIS: branch by delivery address, else customer
    asignados = []
    for p in directos:
        cliente = _cliente_de(p, clientes)
        if cliente is None:
            nombre = p["partner_shipping_id"][1] if p["partner_shipping_id"] else p["partner_id"][1]
            datos.sin_asignar[nombre] = datos.sin_asignar.get(nombre, 0) + 1
        elif cliente.excluir:
            datos.excluidas_cliente += 1
        elif (cliente.sucursal and cliente.sucursal.pk in elegidas) or (not cliente.sucursal and todas):
            asignados.append((p, cliente))
            if cliente.nota and cliente.nota not in datos.notas_clientes:
                datos.notas_clientes.append(cliente.nota)

    # history, amounts, lines and authors
    msgs_oc = odoo.mensajes_de(cli, "purchase.order", [o["id"] for o in validas])
    msgs_so = odoo.mensajes_de(cli, "sale.order", [p["id"] for p, _ in asignados])
    montos = {t["mail_message_id"][0]: (Decimal(str(t["old_value_float"])), Decimal(str(t["new_value_float"])))
              for t in odoo.cambios_de_monto(cli, [m["id"] for m in msgs_oc + msgs_so if m["tracking_value_ids"]])}
    autores = odoo.compania_de_autores(cli, list({m["author_id"][0] for m in msgs_oc + msgs_so if m.get("author_id")}))

    def quien(autor_id):
        return CEDIS if autores.get(autor_id) in companias else SUCURSAL

    def por_producto(lineas, pedida, recibida):
        salida = defaultdict(dict)
        for ln in lineas:
            nombre = (ln["product_id"][1] if ln["product_id"] else ln["name"] or "").strip()
            salida[ln["order_id"][0]][nombre] = dict(precio=Decimal(str(ln["price_unit"])), pedida=Decimal(str(ln[pedida])),
                                                     recibida=Decimal(str(ln[recibida])))
        return salida

    lineas_oc = por_producto(odoo.lineas(cli, [o["id"] for o in validas]), "product_qty", "qty_received")
    lineas_so = por_producto(odoo.lineas_venta(cli, [p["id"] for p, _ in asignados]), "product_uom_qty", "qty_delivered")
    agrupar = defaultdict(list)
    for m in msgs_oc:
        agrupar[("oc", m["res_id"])].append(m)
    for m in msgs_so:
        agrupar[("so", m["res_id"])].append(m)

    for o in validas:
        orden = Orden(o["name"], por_compania[o["company_id"][0]].nombre, proveedores[o["partner_id"][0]], o["state"],
                      odoo.a_cdmx(o["create_date"]), odoo.a_cdmx(o["date_approve"]), Decimal(str(o["amount_untaxed"])),
                      origen=DE_OC)
        datos.ordenes.append(interpretar(orden, agrupar[("oc", o["id"])], montos, lineas_oc[o["id"]], odoo.a_cdmx, quien))
    for p, cliente in asignados:
        orden = Orden(p["name"], cliente.nombre_reporte, nombre_compania[p["company_id"][0]], p["state"],
                      odoo.a_cdmx(p["create_date"]), odoo.a_cdmx(p["date_order"]), Decimal(str(p["amount_untaxed"])),
                      origen=DIRECTO)
        datos.ordenes.append(interpretar(orden, agrupar[("so", p["id"])], montos, lineas_so[p["id"]], odoo.a_cdmx, quien))
    datos.ordenes.sort(key=lambda o: (o.creada, o.nombre))
    datos.sucursales = sorted({o.sucursal for o in datos.ordenes})
    return datos
