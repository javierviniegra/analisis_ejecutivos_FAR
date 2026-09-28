"""Reports that can be generated from the web, keyed by `Reporte.clave`.

A report appears with a "Generar" button only when its key is registered
here; the rest of the catalog stays descriptive until its generator exists.
Each generator receives the branches, the period, whether to consolidate,
whether to deliver one file per branch and the formats (PDF / Excel), and
returns the file to download (a .zip when that makes several files).
"""

import io
import zipfile
from dataclasses import dataclass
from typing import Callable

from .motor import reporte_comercial
from .motor.periodo import Periodo
from .salidas import excel_comercial, pdf_comercial


@dataclass(frozen=True)
class Archivo:
    contenido: bytes
    nombre: str
    tipo: str  # MIME type


def _zip(archivos: list[tuple[str, bytes]], nombre: str) -> Archivo:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre_archivo, contenido in archivos:
            z.writestr(nombre_archivo, contenido)
    return Archivo(salida.getvalue(), nombre, "application/zip")


PDF, EXCEL = "pdf", "excel"


def _comercial(sucursales: list, periodo: Periodo, consolidado: bool, separados: bool, formatos: set[str]) -> Archivo:
    reportes = reporte_comercial.armar(sucursales, periodo, consolidado)
    grupos = [[r] for r in reportes] if separados else [reportes]  # one file per branch, or all together
    archivos = []
    for grupo in grupos:
        if PDF in formatos:
            archivos.append((pdf_comercial.nombre_archivo(grupo), pdf_comercial.generar(grupo), "application/pdf"))
        if EXCEL in formatos:
            archivos.append((excel_comercial.nombre_archivo(grupo), excel_comercial.generar(grupo),
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    if len(archivos) == 1:
        nombre, contenido, tipo = archivos[0]
        return Archivo(contenido, nombre, tipo)
    # several files (one per branch and/or PDF + Excel): downloaded together in a .zip
    return _zip([(n, c) for n, c, _ in archivos], reporte_comercial.nombre_base(reportes) + ".zip")


# (branches, period, consolidated, one file per branch, formats) -> file to download
GENERADORES: dict[str, Callable[[list, Periodo, bool, bool, set[str]], Archivo]] = {
    "comercial-semanal-gerentes": _comercial,
}


def tiene_generador(clave: str) -> bool:
    return clave in GENERADORES
