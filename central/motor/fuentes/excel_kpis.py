"""Hand-filled Excel files of the Semáforos scorecard (read-only).

The Power BI SemaforosKPIs model reads them from SharePoint (site Directores,
"Documentos compartidos/General/SemaforosKPis/"); here they are read from the
folder OneDrive syncs, `SEMAFOROS_KPIS_DIR` in config/.env. Without it (or
without the file) every KPI that depends on them shows "sin fuente".
"""

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..scorecard import normalizar

ARCHIVO_AUDITORIA = "Resultados de Auditoria CGI.xlsx"

# Branch names as the Excel files write them -> this app's `Sucursal.clave`,
# the same correspondence as the Power BI's fxSucursalKey (taquerías before
# their fonda namesakes; "Coyoacán" is La Esquina, "Tollocan" is Metepec).
# León, Lindavista and Perisur are not branches of this app.
_ALIAS = [
    ("taqueria-viaducto", ("T VIADUCTO", "TAQ VIADUCTO", "TAQUERIA VIADUCTO", "TAQUERIA V VIADUCTO", "TACOS VIADUCTO")),
    ("taqueria-parroquia", ("T PARROQUIA", "TAQ PARROQUIA", "TAQUERIA PARROQUIA", "TAQUERIA PRROQUIA",
                            "TACOS PARROQUIA", "PARROQUIA")),
    ("versalles", ("T EXHIBIMEX", "TAQ EXHIBIMEX", "TAQUERIA EXHIBIMEX", "TACOS EXHIBIMEX", "EXHIBIMEX", "VERSALLES",
                   "VERSAILLES")),
    ("acoxpa", ("ACOXPA",)),
    ("aeropuerto", ("AEROPUERTO",)),
    ("antenas", ("ANTENAS", "LAS ANTENAS")),
    ("cancun", ("CANCUN",)),
    ("la-esquina-coyoacan", ("COYOACAN", "LA ESQUINA", "LA ESQUINA COYOACAN")),
    ("isabel-la-catolica", ("ISABEL", "ISABEL LA CATOLICA")),
    ("metepec", ("METEPEC", "TOLLOCAN")),
    ("napoles", ("NAPOLES",)),
    ("oceania", ("OCEANIA", "ENCUENTRO OCEANIA")),
    ("playa-del-carmen", ("PLAYA", "PLAYA DEL CARMEN")),
    ("san-jeronimo", ("SAN JERONIMO",)),
    ("tepeyac", ("TEPEYAC",)),
    ("via-vallejo", ("VALLEJO", "VIA VALLEJO")),
    ("viaducto", ("VIADUCTO",)),
]


def clave_sucursal(nombre: str | None) -> str | None:
    """`Sucursal.clave` of a branch name written in the Excel files (None: not ours)."""
    texto = " ".join(normalizar(nombre or "").replace("-", " ").split())
    for prefijo in ("FONDA ARGENTINA ", "FA "):
        if texto.startswith(prefijo):
            texto = texto[len(prefijo):]
            break
    for clave, nombres in _ALIAS:
        if texto in nombres:
            return clave
    return None


def directorio() -> Path | None:
    valor = os.getenv("SEMAFOROS_KPIS_DIR", "").strip()
    return Path(valor) if valor and Path(valor).is_dir() else None


def _porcentaje(valor) -> Decimal | None:
    """A score as a share (0.85); "N/A", blanks and impossible values (below 0,
    or above 100) are no data. Power BI divides values above 1 by 100."""
    if not isinstance(valor, (int, float)):
        return None
    v = Decimal(str(round(valor, 6)))  # 0.8530000000000001 -> 0.853
    if v > 1:
        v = v / 100
    return v if 0 <= v <= 1 else None


def auditorias_cgi(carpeta: Path | None = None) -> list[dict] | None:
    """Rows of the CGI audit workbook (sheet Hoja1): {"mes": first day of the
    audit month, "clave": Sucursal.clave or None, "nombre": as written,
    "resultado": overall score, "marca": brand standards score}. None when
    the folder or the file is not available."""
    carpeta = carpeta or directorio()
    archivo = carpeta / ARCHIVO_AUDITORIA if carpeta else None
    if archivo is None or not archivo.is_file():
        return None
    from openpyxl import load_workbook
    filas = list(load_workbook(archivo, read_only=True, data_only=True)["Hoja1"].iter_rows(values_only=True))
    encabezado = next((list(f) for f in filas if "Mes" in f), None)
    if encabezado is None:
        return []
    col = {str(n).strip(): i for i, n in enumerate(encabezado) if n is not None}
    resultado = []
    for f in filas[filas.index(tuple(encabezado)) + 1:]:
        mes = f[col["Mes"]]
        if not hasattr(mes, "year"):
            continue
        nombre = f[col["sucursal"]]
        resultado.append({"mes": date(mes.year, mes.month, 1), "clave": clave_sucursal(nombre), "nombre": nombre,
                          "resultado": _porcentaje(f[col["Resultado"]]), "marca": _porcentaje(f[col["Marca"]])})
    return resultado
