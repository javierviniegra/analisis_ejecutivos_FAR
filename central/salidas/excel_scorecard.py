"""Excel workbook of the "Semáforos scorecard" (openpyxl).

Per report: Scorecard (header and the table with real numbers, the light in a
filled cell), Desglose (every cost and expense row by account and by
supplier, Wansoft / Odoo / total) and Reglas (every KPI's rule and the
notes). With several reports in one workbook, each sheet name starts with the
branch. Styles are the commercial workbook's (`excel_comercial`, reused as is).
"""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from ..motor import scorecard as sc
from ..motor.periodo import TipoPeriodo
from ..motor.reporte_scorecard import ReporteScorecard, nombre_base, notas
from ..motor.tabla_comercial import ENTERO, MONEDA, PORCENTAJE
from . import AVISO_AUTOMATICO, pie_excel
from .excel_comercial import (ENCABEZADO_F, ENCABEZADO_R, FONDO_SEMAFORO, FORMATO_VALOR, GRIS, PAR_R, SECCION_F,
                              SUAVE_F, TITULO_F)
from .pdf_scorecard import TITULO, _rango

FORMATOS = {sc.DINERO: MONEDA, sc.PORCENTAJE: PORCENTAJE, sc.NUMERO: ENTERO}
PALABRA = {"verde": "Verde", "naranja": "Naranja", "rojo": "Rojo"}
AVISO_F = Font(bold=True, color="B7791F")


def _hoja(wb: Workbook, r: ReporteScorecard, nombre: str, varios: bool):
    return wb.create_sheet((f"{r.nombre[:18]} · {nombre}" if varios else nombre)[:31])


def _encabezado(ws, fila: int, titulos: list[str]):
    for col, titulo in enumerate(titulos, start=1):
        celda = ws.cell(fila, col, titulo)
        celda.font, celda.fill = ENCABEZADO_F, ENCABEZADO_R


def _numero(ws, fila: int, col: int, valor, fmt: str):
    if valor is None:
        ws.cell(fila, col, "—").font = Font(color=GRIS)
        return
    celda = ws.cell(fila, col, float(valor))
    celda.number_format = FORMATO_VALOR[fmt]


def _scorecard(ws, r: ReporteScorecard):
    p = r.periodos
    nombre = r.nombre if r.nombre != "Consolidado" else f"Consolidado ({len(r.sucursales)} sucursales)"
    ws.cell(1, 1, f"{TITULO} · {nombre}").font = TITULO_F
    ws.cell(2, 1, f"{'Mes cerrado' if p.actual.tipo == TipoPeriodo.MES else 'Mes en curso'}: {_rango(p.actual)}")
    ws.cell(3, 1, f"Mes anterior: {_rango(p.mes_anterior)} · Meta de ventas, cheque, ticket y clientes: "
                  f"{_rango(p.anio_anterior)} +5%").font = SUAVE_F
    fila = 4
    avisos = []
    if p.mes_cerrado:
        avisos.append("Primer lunes del mes: se reporta el mes anterior completo.")
    if r.meta_mes_anterior:
        avisos.append("Sin año anterior (sucursal nueva), meta = mes anterior +5%: " + ", ".join(r.meta_mes_anterior))
    if r.sin_meta:
        avisos.append("Sin año anterior ni mes anterior (fuera de las metas): " + ", ".join(r.sin_meta))
    for aviso in avisos:
        ws.cell(fila, 1, aviso).font = AVISO_F
        fila += 1
    fila += 1
    _encabezado(ws, fila, ["KPI", "Actual", "Mes anterior", "Meta", "Estado", "Actual comparado"])
    for categoria in sc.CATEGORIAS:
        fila += 1
        ws.cell(fila, 1, categoria).font = SECCION_F
        for col in range(1, 7):
            ws.cell(fila, col).fill = PAR_R
        for f in [f for f in r.filas if f.kpi.categoria == categoria]:
            fila += 1
            leida = r.leida(f.kpi.clave)
            fmt = FORMATOS[f.kpi.tipo]
            ws.cell(fila, 1, f.kpi.nombre).font = Font() if leida else Font(color=GRIS)
            _numero(ws, fila, 2, f.actual, fmt)
            _numero(ws, fila, 3, f.mes_anterior, fmt)
            _numero(ws, fila, 4, f.meta, fmt)
            estado = ws.cell(fila, 5)
            if f.estado:
                estado.value = PALABRA[f.estado]
                estado.font = Font(bold=True)
                estado.fill = PatternFill("solid", fgColor=FONDO_SEMAFORO[f.estado])
            else:
                estado.value = "sin fuente" if f.kpi.clave in r.sin_fuente else "sin dato"
                estado.font = Font(italic=True, color=GRIS)
            if leida and f.actual_comparado != f.actual:
                _numero(ws, fila, 6, f.actual_comparado, fmt)
    ws.cell(fila + 2, 1, "Actual comparado: lo que el semáforo compara cuando alguna sucursal queda fuera de la meta "
                         "(consolidado).").font = SUAVE_F
    ws.cell(fila + 3, 1, AVISO_AUTOMATICO).font = SUAVE_F
    ws.column_dimensions["A"].width = 46
    for col in "BCDF":
        ws.column_dimensions[col].width = 17
    ws.column_dimensions["E"].width = 12


def _desglose(ws, r: ReporteScorecard):
    ws.cell(1, 1, f"De dónde sale cada costo y gasto · {_rango(r.periodos.actual)}").font = TITULO_F
    _encabezado(ws, 3, ["KPI", "Por", "Cuenta / proveedor", "Wansoft", "Odoo", "Total"])
    fila = 3
    for d in r.desglose:
        for por, componentes in (("Cuenta", d.cuentas), ("Proveedor", d.proveedores)):
            for c in componentes:
                fila += 1
                ws.cell(fila, 1, d.kpi.nombre)
                ws.cell(fila, 2, por)
                ws.cell(fila, 3, c.etiqueta)
                for col, sistema in ((4, sc.WANSOFT), (5, sc.ODOO)):
                    if sistema in c.por_sistema:
                        _numero(ws, fila, col, c.por_sistema[sistema], MONEDA)
                _numero(ws, fila, 6, c.total, MONEDA)
        if d.n_otros:
            fila += 1
            ws.cell(fila, 1, d.kpi.nombre)
            ws.cell(fila, 2, "Proveedor")
            ws.cell(fila, 3, f"Otros {d.n_otros} proveedores").font = Font(italic=True)
            _numero(ws, fila, 6, d.otros_proveedores, MONEDA)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 11
    ws.column_dimensions["C"].width = 60
    for col in "DEF":
        ws.column_dimensions[col].width = 16


def _reglas(ws, r: ReporteScorecard):
    ws.cell(1, 1, "Reglas de los semáforos").font = TITULO_F
    _encabezado(ws, 3, ["Categoría", "KPI", "Regla"])
    fila = 3
    for k in sc.KPIS:
        fila += 1
        ws.cell(fila, 1, k.categoria)
        ws.cell(fila, 2, k.nombre)
        texto = sc.regla_texto(k) + (" (Sin fuente por ahora.)" if k.clave in r.sin_fuente else "")
        ws.cell(fila, 3, texto).alignment = Alignment(wrap_text=True, vertical="top")
    fila += 2
    ws.cell(fila, 1, "Notas").font = SECCION_F
    for nota in notas(r):
        fila += 1
        celda = ws.cell(fila, 1, nota)
        celda.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=3)
        ws.row_dimensions[fila].height = 15 * (1 + len(nota) // 120)
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 42
    ws.column_dimensions["C"].width = 90


def generar(reportes: list[ReporteScorecard]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    varios = len(reportes) > 1
    for r in reportes:
        _scorecard(_hoja(wb, r, "Scorecard", varios), r)
        _desglose(_hoja(wb, r, "Desglose", varios), r)
        _reglas(_hoja(wb, r, "Reglas", varios), r)
    pie_excel(wb)
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def nombre_archivo(reportes: list[ReporteScorecard]) -> str:
    return nombre_base(reportes) + ".xlsx"
