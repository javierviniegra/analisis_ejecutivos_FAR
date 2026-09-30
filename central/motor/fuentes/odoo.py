"""Read-only access to Odoo (XML-RPC) for the CEDIS purchase-order reports.

Read-only by construction: the client only lets the query methods through
(`search_read`, `read`, `search_count`, `fields_get`), so no code path can
create, write or delete in Odoo, whatever account is configured. Credentials
come from config/.env (ODOO_URL, ODOO_DB_NAME, ODOO_USER, ODOO_PASSWORD);
a dedicated read-only Odoo user is still recommended.

Odoo stores datetimes in UTC; Mexico City has been UTC-6 all year since 2022
(no daylight saving), so conversions use a fixed offset.
"""

import os
import xmlrpc.client
from datetime import date, datetime, timedelta

METODOS_PERMITIDOS = {"search_read", "read", "search_count", "fields_get"}
UTC_A_CDMX = timedelta(hours=-6)
LOTE = 500  # records per search_read call

# The internal providers the CEDIS reports are about (Odoo partner names).
PROVEEDORES_INTERNOS = ["EL BODEGON DE FITO", "LAS EMPANADAS DE MARIA EVA"]


class OdooLectura:
    def __init__(self, url: str, base: str, usuario: str, clave: str):
        url = url.rstrip("/")
        self._base, self._clave = base, clave
        self._uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(base, usuario, clave, {})
        if not self._uid:
            raise RuntimeError("Odoo authentication failed (check ODOO_* in config/.env)")
        self._objetos = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        companias = self.llamar("res.users", "read", [self._uid], fields=["company_ids"])[0]["company_ids"]
        # Read across every company the account can see (multi-company Odoo).
        self._contexto = {"allowed_company_ids": companias}

    def llamar(self, modelo: str, metodo: str, *args, **kwargs):
        if metodo not in METODOS_PERMITIDOS:
            raise PermissionError(f"Odoo method {metodo!r} is not allowed: this client is read-only")
        if hasattr(self, "_contexto"):
            kwargs.setdefault("context", self._contexto)
        return self._objetos.execute_kw(self._base, self._uid, self._clave, modelo, metodo, list(args), kwargs)

    def leer_todo(self, modelo: str, dominio: list, campos: list[str], orden: str = "id") -> list[dict]:
        """search_read in batches (large result sets). Keeps paging until an
        EMPTY page: Odoo can return a short page while more records remain
        (access rules applied after the limit) -- stopping at the first short
        page lost 10,469 of 17,611 order messages (found 2026-09-30)."""
        salida, vistos, desplazamiento = [], set(), 0
        while True:
            lote = self.llamar(modelo, "search_read", dominio, fields=campos, order=orden, limit=LOTE,
                               offset=desplazamiento)
            if not lote:
                return salida
            for registro in lote:
                if registro["id"] not in vistos:
                    vistos.add(registro["id"])
                    salida.append(registro)
            desplazamiento += LOTE


def abrir_odoo() -> OdooLectura:
    faltan = [v for v in ("ODOO_URL", "ODOO_DB_NAME", "ODOO_USER", "ODOO_PASSWORD") if not os.getenv(v)]
    if faltan:
        raise RuntimeError(f"Odoo is not configured in config/.env: {', '.join(faltan)}")
    return OdooLectura(os.getenv("ODOO_URL"), os.getenv("ODOO_DB_NAME"), os.getenv("ODOO_USER"), os.getenv("ODOO_PASSWORD"))


# -- dates ------------------------------------------------------------------
def a_cdmx(texto_utc: str | bool) -> datetime | None:
    """Odoo UTC datetime text ('2026-06-01 16:11:12') -> Mexico City time."""
    if not texto_utc:
        return None
    return datetime.strptime(texto_utc, "%Y-%m-%d %H:%M:%S") + UTC_A_CDMX


def limite_utc(dia: date) -> str:
    """Start of a Mexico City day, as Odoo UTC text (for domains)."""
    return (datetime.combine(dia, datetime.min.time()) - UTC_A_CDMX).strftime("%Y-%m-%d %H:%M:%S")


# -- queries ----------------------------------------------------------------
def proveedores_internos(cli: OdooLectura) -> dict[int, str]:
    socios = cli.llamar("res.partner", "search_read", [["name", "in", PROVEEDORES_INTERNOS]], fields=["name"])
    return {p["id"]: p["name"] for p in socios}


def ordenes(cli: OdooLectura, company_ids: list[int], proveedores: list[int], desde: date, hasta: date) -> list[dict]:
    """Confirmed orders ('purchase'/'done') of these branches to these
    providers CREATED in [desde, hasta] (Mexico City days), excluding the ones
    Odoo generated automatically from the provider's sales order."""
    return cli.leer_todo("purchase.order", [
        ["company_id", "in", company_ids], ["partner_id", "in", proveedores],
        ["state", "in", ["purchase", "done"]], ["auto_generated", "=", False],
        ["create_date", ">=", limite_utc(desde)], ["create_date", "<", limite_utc(hasta + timedelta(days=1))],
    ], ["name", "company_id", "partner_id", "state", "create_date", "date_approve", "amount_untaxed"])


def ordenes_auto_generadas(cli: OdooLectura, company_ids: list[int], proveedores: list[int], desde: date, hasta: date) -> int:
    return cli.llamar("purchase.order", "search_count", [
        ["company_id", "in", company_ids], ["partner_id", "in", proveedores],
        ["state", "in", ["purchase", "done"]], ["auto_generated", "=", True],
        ["create_date", ">=", limite_utc(desde)], ["create_date", "<", limite_utc(hasta + timedelta(days=1))],
    ])


def mensajes(cli: OdooLectura, order_ids: list[int]) -> list[dict]:
    """Chatter of the orders (notes and tracked changes), oldest first."""
    salida = []
    for i in range(0, len(order_ids), LOTE):
        salida += cli.leer_todo("mail.message", [["model", "=", "purchase.order"], ["res_id", "in", order_ids[i:i + LOTE]]],
                                ["res_id", "date", "author_id", "body", "tracking_value_ids"], orden="date asc, id asc")
    return salida


def cambios_de_monto(cli: OdooLectura, message_ids: list[int]) -> list[dict]:
    """Tracked changes of the untaxed amount (old -> new) of those messages."""
    salida = []
    for i in range(0, len(message_ids), LOTE):
        salida += cli.leer_todo("mail.tracking.value", [["mail_message_id", "in", message_ids[i:i + LOTE]],
                                                        ["field_id.name", "=", "amount_untaxed"]],
                                ["mail_message_id", "old_value_float", "new_value_float"])
    return salida


def lineas(cli: OdooLectura, order_ids: list[int]) -> list[dict]:
    salida = []
    for i in range(0, len(order_ids), LOTE):
        salida += cli.leer_todo("purchase.order.line", [["order_id", "in", order_ids[i:i + LOTE]]],
                                ["order_id", "product_id", "name", "product_qty", "qty_received", "price_unit"])
    return salida
