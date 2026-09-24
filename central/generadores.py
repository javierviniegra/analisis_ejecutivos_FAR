"""Reports that can be generated from the web, keyed by `Reporte.clave`.

A report appears with a "Generar" button only when its key is registered
here; the rest of the catalog stays descriptive until its generator exists.
Each generator receives the branches, the period, whether to consolidate and
whether to deliver one file per branch, and returns the file to download.
"""

import io
import zipfile
from dataclasses import dataclass
from typing import Callable

from .motor import reporte_comercial
from .motor.periodo import Periodo
from .salidas import pdf_comercial


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


def _comercial(sucursales: list, periodo: Periodo, consolidado: bool, separados: bool) -> Archivo:
    reportes = reporte_comercial.armar(sucursales, periodo, consolidado)
    if separados:  # one PDF per branch, downloaded together in a .zip
        pdfs = [(pdf_comercial.nombre_archivo([r]), pdf_comercial.generar([r])) for r in reportes]
        return _zip(pdfs, pdf_comercial.nombre_archivo(reportes)[:-4] + ".zip")
    return Archivo(pdf_comercial.generar(reportes), pdf_comercial.nombre_archivo(reportes), "application/pdf")


# (branches, period, consolidated, one file per branch) -> file to download
GENERADORES: dict[str, Callable[[list, Periodo, bool, bool], Archivo]] = {
    "comercial-semanal-gerentes": _comercial,
}


def tiene_generador(clave: str) -> bool:
    return clave in GENERADORES
