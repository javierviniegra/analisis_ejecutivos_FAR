"""Reports that can be generated from the web, keyed by `Reporte.clave`.

A report appears with a "Generar" button only when its key is registered
here; the rest of the catalog stays descriptive until its generator exists.
Each generator receives the branches, the period, whether to consolidate,
whether to deliver one file per branch, the formats (PDF / Excel) and the
report's own options (`OPCIONES`), and returns the file to download (a .zip
when that makes several files). The same call serves the web screen and,
later, the automations, where each option is saved as a rule.
"""

import io
import zipfile
from dataclasses import dataclass
from typing import Callable

from .motor import reporte_cedis, reporte_comercial
from .motor.periodo import Periodo
from .salidas import excel_cedis, excel_comercial, pdf_comercial


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
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Options a report admits beyond branches / period / format, with their default.
INCLUIR_COSTOS = "incluir_costos"
OPCIONES: dict[str, dict[str, bool]] = {
    "comercial-semanal-gerentes": {INCLUIR_COSTOS: True},
}


def opciones_de(clave: str) -> dict[str, bool]:
    return dict(OPCIONES.get(clave, {}))


def _archivos_comercial(grupo: list, formatos: set[str]) -> list[tuple[str, bytes, str]]:
    archivos = []
    if PDF in formatos:
        archivos.append((pdf_comercial.nombre_archivo(grupo), pdf_comercial.generar(grupo), "application/pdf"))
    if EXCEL in formatos:
        archivos.append((excel_comercial.nombre_archivo(grupo), excel_comercial.generar(grupo), XLSX))
    return archivos


def _comercial(sucursales: list, periodo: Periodo, consolidado: bool, separados: bool, formatos: set[str],
               opciones: dict | None = None) -> Archivo:
    incluir_costos = (opciones or {}).get(INCLUIR_COSTOS, True)
    reportes = reporte_comercial.armar(sucursales, periodo, consolidado, incluir_costos)
    grupos = [[r] for r in reportes] if separados else [reportes]  # one file per branch, or all together
    archivos = [a for grupo in grupos for a in _archivos_comercial(grupo, formatos)]
    if len(archivos) == 1:
        nombre, contenido, tipo = archivos[0]
        return Archivo(contenido, nombre, tipo)
    # several files (one per branch and/or PDF + Excel): downloaded together in a .zip
    return _zip([(n, c) for n, c, _ in archivos], reporte_comercial.nombre_base(reportes) + ".zip")


def _cedis(tipo: str, construir):
    """CEDIS workbooks: one workbook for the selected branches (the report's
    scope is consolidated), Excel only, reproducing the owner's originals."""
    def generar(sucursales: list, periodo: Periodo, consolidado: bool, separados: bool, formatos: set[str],
                opciones: dict | None = None) -> Archivo:
        datos = reporte_cedis.leer(sucursales, periodo.desde, periodo.hasta)
        return Archivo(construir(datos), excel_cedis.nombre_archivo(tipo, datos), XLSX)
    return generar


# (branches, period, consolidated, one file per branch, formats, options) -> file to download
GENERADORES: dict[str, Callable[..., Archivo]] = {
    "comercial-semanal-gerentes": _comercial,
    "oc-bodegon-empanadas-modificaciones": _cedis("modificaciones", excel_cedis.modificaciones),
    "oc-bodegon-empanadas-por-hora": _cedis("por_hora", excel_cedis.por_hora),
}


def tiene_generador(clave: str) -> bool:
    return clave in GENERADORES


# -- automations: the files of one send, grouped by who they are about --------
@dataclass(frozen=True)
class GrupoArchivos:
    sucursal: object | None  # cuentas.Sucursal of a per-branch report; None = consolidated
    archivos: list[tuple[str, bytes, str]]  # (file name, content, MIME type), attached as they are


def _grupos_comercial(sucursales, periodo, consolidado, formatos, opciones) -> list[GrupoArchivos]:
    incluir_costos = (opciones or {}).get(INCLUIR_COSTOS, True)
    reportes = reporte_comercial.armar(sucursales, periodo, consolidado, incluir_costos)
    if consolidado:
        return [GrupoArchivos(None, _archivos_comercial(reportes, formatos))]
    return [GrupoArchivos(s, _archivos_comercial([r], formatos)) for s, r in zip(sucursales, reportes)]


def _grupos_cedis(tipo, construir):
    def grupos(sucursales, periodo, consolidado, formatos, opciones) -> list[GrupoArchivos]:
        datos = reporte_cedis.leer(sucursales, periodo.desde, periodo.hasta)
        return [GrupoArchivos(None, [(excel_cedis.nombre_archivo(tipo, datos), construir(datos), XLSX)])]
    return grupos


# (branches, period, consolidated, formats, options) -> files per branch / consolidated
GRUPOS: dict[str, Callable[..., list[GrupoArchivos]]] = {
    "comercial-semanal-gerentes": _grupos_comercial,
    "oc-bodegon-empanadas-modificaciones": _grupos_cedis("modificaciones", excel_cedis.modificaciones),
    "oc-bodegon-empanadas-por-hora": _grupos_cedis("por_hora", excel_cedis.por_hora),
}
