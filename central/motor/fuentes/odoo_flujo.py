"""Read-only Odoo queries behind the cash-flow report (flujo de efectivo).

Everything goes through `OdooLectura` (search_read / read only). The report
needs, for a set of companies and a date range:

- the bank and investment accounts of each company (codes 102 / 103 of the
  chart; 101 is cash on hand and stays out, owner and accountant 2026-11-04)
  and the journal that uses each one (its name is what people know: account
  names were copied between companies, e.g. Puebla's "Banorte 3289 corpo");
- every posted line on those accounts up to the end of the range (balances)
  and, for the lines inside the range, what they were booked or reconciled
  against: the move's other lines, the lines those were matched with, the
  payments behind them and the accounts of the bills those payments paid.

The classification itself is pure and lives in `motor/flujo_efectivo.py`.
"""

from datetime import date

from .odoo import LOTE, OdooLectura

CAMPOS_LINEA = ["company_id", "account_id", "journal_id", "date", "balance", "move_id", "name", "partner_id"]
CAMPOS_CONTRA = ["move_id", "account_id", "balance", "name", "partner_id", "matched_debit_ids", "matched_credit_ids"]
CAMPOS_OTRO_LADO = ["move_id", "account_id", "partner_id", "payment_id", "statement_line_id", "move_type"]


def _por_lotes(cli: OdooLectura, modelo: str, ids: list[int], campos: list[str], campo_id: str = "id") -> list[dict]:
    salida, ids = [], sorted(set(ids))
    for i in range(0, len(ids), LOTE):
        salida += cli.leer_todo(modelo, [[campo_id, "in", ids[i:i + LOTE]]], campos)
    return salida


def codigo(cuenta: dict) -> str:
    """Account code: `code` in the company's context, else the first word of
    `placeholder_code` ("102.01.05 (FONDA ARGENTINA PUEBLA)"), which Odoo 18
    fills for accounts shared across companies."""
    return (cuenta.get("code") or (cuenta.get("placeholder_code") or "").split(" ")[0] or "").strip()


def cuentas_de_efectivo(cli: OdooLectura, company_ids: list[int]) -> list[dict]:
    """Liquidity accounts (type asset_cash) of each company with their code
    and the bank/cash journal that uses each one: one dict per company and
    account {company_id, account_id, codigo, cuenta, diario}."""
    salida = []
    for cia in company_ids:
        contexto = {**cli._contexto, "allowed_company_ids": [cia]}
        cuentas = cli.llamar("account.account", "search_read", [["account_type", "=", "asset_cash"]],
                             fields=["code", "placeholder_code", "name"], context=contexto)
        diarios = cli.llamar("account.journal", "search_read", [["company_id", "=", cia], ["type", "in", ["bank", "cash"]]],
                             fields=["name", "default_account_id"], context=contexto)
        diario_de = {d["default_account_id"][0]: d["name"] for d in diarios if d["default_account_id"]}
        for c in cuentas:
            salida.append({"company_id": cia, "account_id": c["id"], "codigo": codigo(c), "cuenta": c["name"],
                           "diario": diario_de.get(c["id"])})
    return salida


def lineas_de_cuentas(cli: OdooLectura, company_ids: list[int], account_ids: list[int], hasta: date) -> list[dict]:
    """Every posted line on these accounts up to `hasta` (balances need the whole history)."""
    if not account_ids:
        return []
    return cli.leer_todo("account.move.line", [
        ["company_id", "in", company_ids], ["account_id", "in", sorted(set(account_ids))],
        ["parent_state", "=", "posted"], ["date", "<=", str(hasta)],
    ], CAMPOS_LINEA)


def detalle_de_movimientos(cli: OdooLectura, move_ids: list[int], cuentas_excluidas: set[int]) -> dict:
    """What the moves of the period's bank lines were booked or reconciled
    against. Returns raw records keyed by kind (see module docstring)."""
    movimientos = _por_lotes(cli, "account.move", move_ids, ["move_type", "ref", "statement_line_id", "origin_payment_id"])
    extractos = _por_lotes(cli, "account.bank.statement.line",
                           [m["statement_line_id"][0] for m in movimientos if m["statement_line_id"]], ["payment_ref"])
    contra = [l for l in _por_lotes(cli, "account.move.line", move_ids, CAMPOS_CONTRA, "move_id")
              if l["account_id"][0] not in cuentas_excluidas]
    parciales = _por_lotes(cli, "account.partial.reconcile",
                           [p for l in contra for p in l["matched_debit_ids"] + l["matched_credit_ids"]],
                           ["debit_move_id", "credit_move_id", "amount"])
    otro_lado = _por_lotes(cli, "account.move.line",
                           [x for p in parciales for x in (p["debit_move_id"][0], p["credit_move_id"][0])], CAMPOS_OTRO_LADO)
    # plain journal entries on the other side: their lines tell what they are (payroll, taxes, transfers...)
    asientos = {l["move_id"][0] for l in otro_lado if not l["payment_id"] and not l["statement_line_id"] and l["move_type"] == "entry"}
    lineas_asiento = _por_lotes(cli, "account.move.line", list(asientos), ["move_id", "account_id", "balance"], "move_id")
    pagos = _por_lotes(cli, "account.payment",
                       [l["payment_id"][0] for l in otro_lado if l["payment_id"]] + [m["origin_payment_id"][0] for m in movimientos if m["origin_payment_id"]],
                       ["payment_type", "partner_type", "memo", "partner_id", "reconciled_bill_ids"])
    facturas = [b for p in pagos for b in p["reconciled_bill_ids"]] + [
        l["move_id"][0] for l in otro_lado if l["move_type"] in ("in_invoice", "in_refund")]  # bills paid without a payment
    lineas_factura = _por_lotes(cli, "account.move.line", facturas, ["move_id", "account_id", "balance", "display_type"], "move_id")
    lineas_factura = [l for l in lineas_factura if l["display_type"] == "product"]
    cuentas = _por_lotes(cli, "account.account",
                         [l["account_id"][0] for grupo in (contra, otro_lado, lineas_asiento, lineas_factura) for l in grupo],
                         ["code", "placeholder_code", "name", "account_type"])
    socios = _por_lotes(cli, "res.partner",
                        [p["partner_id"][0] for p in pagos if p["partner_id"]] + [l["partner_id"][0] for l in contra if l["partner_id"]],
                        ["commercial_partner_id"])
    return {"movimientos": movimientos, "extractos": extractos, "contra": contra, "parciales": parciales,
            "otro_lado": otro_lado, "lineas_asiento": lineas_asiento, "pagos": pagos, "lineas_factura": lineas_factura,
            "cuentas": cuentas, "socios": socios}


def cuentas_por_codigo(cli: OdooLectura, company_ids: list[int], prefijo: str) -> dict[int, list[int]]:
    """Accounts of each company whose code starts with `prefijo` (e.g. the
    106.01 "CxC bancos": sales recorded but not yet deposited)."""
    salida = {}
    for cia in company_ids:
        contexto = {**cli._contexto, "allowed_company_ids": [cia]}
        cuentas = cli.llamar("account.account", "search_read", [["code", "=like", f"{prefijo}%"]],
                             fields=["code", "placeholder_code"], context=contexto)
        salida[cia] = [c["id"] for c in cuentas if codigo(c).startswith(prefijo)]
    return salida


def socios_del_grupo(cli: OdooLectura) -> dict[int, str]:
    """Partner id of every Odoo company of the group -> company name (to tell
    payments between group companies from payments to third parties)."""
    return {c["partner_id"][0]: c["name"] for c in cli.llamar("res.company", "search_read", [], fields=["name", "partner_id"])
            if c["partner_id"]}
