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

from .motor import flujo_efectivo, reporte_cedis, reporte_comercial, reporte_meseros, reporte_scorecard
from .motor.periodo import Periodo
from .salidas import (excel_cedis, excel_comercial, excel_flujo, excel_meseros, excel_scorecard,
                      pdf_comercial, pdf_flujo, pdf_meseros, pdf_scorecard)


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


def _archivos_meseros(grupo: list, formatos: set[str]) -> list[tuple[str, bytes, str]]:
    archivos = []
    if PDF in formatos:
        archivos.append((pdf_meseros.nombre_archivo(grupo), pdf_meseros.generar(grupo), "application/pdf"))
    if EXCEL in formatos:
        archivos.append((excel_meseros.nombre_archivo(grupo), excel_meseros.generar(grupo), XLSX))
    return archivos


def _meseros(sucursales: list, periodo: Periodo, consolidado: bool, separados: bool, formatos: set[str],
             opciones: dict | None = None) -> Archivo:
    reportes = reporte_meseros.armar(sucursales, periodo, consolidado)
    grupos = [[r] for r in reportes] if separados else [reportes]
    archivos = [a for grupo in grupos for a in _archivos_meseros(grupo, formatos)]
    if len(archivos) == 1:
        nombre, contenido, tipo = archivos[0]
        return Archivo(contenido, nombre, tipo)
    return _zip([(n, c) for n, c, _ in archivos], reporte_meseros.nombre_base(reportes) + ".zip")


def _archivos_scorecard(grupo: list, formatos: set[str]) -> list[tuple[str, bytes, str]]:
    archivos = []
    if PDF in formatos:
        archivos.append((pdf_scorecard.nombre_archivo(grupo), pdf_scorecard.generar(grupo), "application/pdf"))
    if EXCEL in formatos:
        archivos.append((excel_scorecard.nombre_archivo(grupo), excel_scorecard.generar(grupo), XLSX))
    return archivos


def _scorecard(sucursales: list, periodo: Periodo, consolidado: bool, separados: bool, formatos: set[str],
               opciones: dict | None = None) -> Archivo:
    """Semáforos scorecard: the cut is the period's last day (a week -> the
    month to date up to its Sunday, as the weekly send; a month -> that month)."""
    reportes = reporte_scorecard.armar_varios(sucursales, periodo, consolidado)
    grupos = [[r] for r in reportes] if separados else [reportes]
    archivos = [a for grupo in grupos for a in _archivos_scorecard(grupo, formatos)]
    if len(archivos) == 1:
        nombre, contenido, tipo = archivos[0]
        return Archivo(contenido, nombre, tipo)
    return _zip([(n, c) for n, c, _ in archivos], reporte_scorecard.nombre_base(reportes) + ".zip")


def _archivos_flujo(grupo: list, formatos: set[str]) -> list[tuple[str, bytes, str]]:
    archivos = []
    if PDF in formatos:
        archivos.append((pdf_flujo.nombre_archivo(grupo), pdf_flujo.generar(grupo), "application/pdf"))
    if EXCEL in formatos:
        archivos.append((excel_flujo.nombre_archivo(grupo), excel_flujo.generar(grupo), XLSX))
    return archivos


def _flujo(sucursales: list, periodo: Periodo, consolidado: bool, separados: bool, formatos: set[str],
           opciones: dict | None = None) -> Archivo:
    """Cash flow: the selected branches with accounting in Odoo plus El Bodegón,
    Las Empanadas and Rodiva (always: they are the report's other half)."""
    reportes = flujo_efectivo.armar(sucursales, periodo, consolidado)
    grupos = [[r] for r in reportes] if separados else [reportes]
    archivos = [a for grupo in grupos for a in _archivos_flujo(grupo, formatos)]
    if len(archivos) == 1:
        nombre, contenido, tipo = archivos[0]
        return Archivo(contenido, nombre, tipo)
    return _zip([(n, c) for n, c, _ in archivos], flujo_efectivo.nombre_base(reportes) + ".zip")


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
    "meseros": _meseros,
    "semaforos-scorecard-semanal": _scorecard,
    "oc-bodegon-empanadas-modificaciones": _cedis("modificaciones", excel_cedis.modificaciones),
    "oc-bodegon-empanadas-por-hora": _cedis("por_hora", excel_cedis.por_hora),
    "flujo-efectivo-odoo": _flujo,
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


def _grupos_meseros(sucursales, periodo, consolidado, formatos, opciones) -> list[GrupoArchivos]:
    reportes = reporte_meseros.armar(sucursales, periodo, consolidado)
    if consolidado:
        return [GrupoArchivos(None, _archivos_meseros(reportes, formatos))]
    return [GrupoArchivos(s, _archivos_meseros([r], formatos)) for s, r in zip(sucursales, reportes)]


def _grupos_scorecard(sucursales, periodo, consolidado, formatos, opciones) -> list[GrupoArchivos]:
    reportes = reporte_scorecard.armar_varios(sucursales, periodo, consolidado)
    if consolidado:
        return [GrupoArchivos(None, _archivos_scorecard(reportes, formatos))]
    return [GrupoArchivos(s, _archivos_scorecard([r], formatos)) for s, r in zip(sucursales, reportes)]


def _grupos_flujo(sucursales, periodo, consolidado, formatos, opciones) -> list[GrupoArchivos]:
    reportes = flujo_efectivo.armar(sucursales, periodo, consolidado)
    if consolidado:
        return [GrupoArchivos(None, _archivos_flujo(reportes, formatos))]
    # per branch: only the branches (El Bodegón, Las Empanadas and Rodiva are not
    # a Sucursal; they travel in the consolidated file)
    por_compania = {r.empresas[0].compania_id: r for r in reportes if r.empresas}
    return [GrupoArchivos(s, _archivos_flujo([por_compania[s.odoo_company_id]], formatos))
            for s in sucursales if s.odoo_company_id in por_compania]


def _grupos_cedis(tipo, construir):
    def grupos(sucursales, periodo, consolidado, formatos, opciones) -> list[GrupoArchivos]:
        datos = reporte_cedis.leer(sucursales, periodo.desde, periodo.hasta)
        return [GrupoArchivos(None, [(excel_cedis.nombre_archivo(tipo, datos), construir(datos), XLSX)])]
    return grupos


# (branches, period, consolidated, formats, options) -> files per branch / consolidated
GRUPOS: dict[str, Callable[..., list[GrupoArchivos]]] = {
    "comercial-semanal-gerentes": _grupos_comercial,
    "meseros": _grupos_meseros,
    "semaforos-scorecard-semanal": _grupos_scorecard,
    "oc-bodegon-empanadas-modificaciones": _grupos_cedis("modificaciones", excel_cedis.modificaciones),
    "oc-bodegon-empanadas-por-hora": _grupos_cedis("por_hora", excel_cedis.por_hora),
    "flujo-efectivo-odoo": _grupos_flujo,
}
