"""Read-only client of Banxico's SIE API: Mexico's INPC (INEGI), series SP1.

A free query token (BANXICO_TOKEN in config/.env) goes in the Bmx-Token
header; dates are dd/mm/yyyy, values strings ("146.075000000000", or "N/E"
while not published).
"""

import json
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation

URL = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/SP1/datos/{desde}/{hasta}"


def inpc(token: str, desde: date, hasta: date, timeout: int = 20) -> dict[date, Decimal]:
    """{first day of the month: INPC} for the published months of the range."""
    peticion = urllib.request.Request(URL.format(desde=desde.isoformat(), hasta=hasta.isoformat()),
                                      headers={"Bmx-Token": token, "Accept": "application/json"})
    with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
        datos = json.load(respuesta)
    resultado = {}
    for serie in datos.get("bmx", {}).get("series", []):
        for punto in serie.get("datos", []):
            dia, mes, anio = (int(x) for x in punto["fecha"].split("/"))
            try:
                resultado[date(anio, mes, 1)] = Decimal(punto["dato"].replace(",", ""))
            except (InvalidOperation, AttributeError):
                continue  # "N/E": not published yet
    return resultado
