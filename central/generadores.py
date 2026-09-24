"""Reports that can be generated from the web, keyed by `Reporte.clave`.

A report appears with a "Generar" button only when its key is registered
here; the rest of the catalog stays descriptive until its generator exists.
Each generator receives the branches, the period and whether to consolidate,
and returns the file to download.
"""

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


def _comercial(sucursales: list, periodo: Periodo, consolidado: bool) -> Archivo:
    reportes = reporte_comercial.armar(sucursales, periodo, consolidado)
    return Archivo(pdf_comercial.generar(reportes), pdf_comercial.nombre_archivo(reportes), "application/pdf")


GENERADORES: dict[str, Callable[[list, Periodo, bool], Archivo]] = {
    "comercial-semanal-gerentes": _comercial,
}


def tiene_generador(clave: str) -> bool:
    return clave in GENERADORES
