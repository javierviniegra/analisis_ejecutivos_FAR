"""Excel workbook of the waiters' report: Resumen (Lectura + indicators, as
the commercial one), one sheet per chart, the waiters' (or branches') detail
and the notes. Reuses the commercial workbook's pieces."""

import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from ..motor.reporte_meseros import ReporteMeseros, nombre_base
from ..motor.tabla_comercial import ENTERO, MONEDA, PORCENTAJE
from .excel_comercial import (FONDO_SEMAFORO, SECCION_F, _datos_grafica, _encabezado, _hoja, _notas, _numero,
                              _resumen, _variacion)


def _detalle(ws, r: ReporteMeseros):
    if r.por_sucursal:
        ws["A1"] = "Detalle por sucursal"
        ws["A1"].font = SECCION_F
        _encabezado(ws, 3, ["Sucursal", "Meseros", "Mesas", "Personas", "Venta salón", "Venta por mesero por día",
                            "Cheque prom.", "% Bebidas", "Propina %", "Cortesías", "Mejor mesero"])
        for i, f in enumerate(r.por_sucursal, start=4):
            t = f.d.total
            ws.cell(i, 1, f.nombre)
            ws.cell(i, 2, f.d.plantilla)
            for col, v, fmt in ((3, t.cuentas, ENTERO), (4, t.personas, ENTERO), (5, t.venta_bruta, MONEDA),
                                (6, f.d.venta_por_mesero_dia, MONEDA), (7, t.cheque_promedio, MONEDA),
                                (8, t.pct_bebidas, PORCENTAJE), (9, t.pct_propina, PORCENTAJE),
                                (10, t.cortesias, MONEDA)):
                _numero(ws, i, col, v, fmt)
            ws.cell(i, 11, f.mejor or "—")
        anchos = (30, 10, 10, 10, 16, 16, 14, 11, 11, 13, 30)
    else:
        ws["A1"] = "Detalle por mesero (de mayor a menor venta)"
        ws["A1"].font = SECCION_F
        _encabezado(ws, 3, ["Mesero", "Días", "Mesas", "Personas", "Venta", "Venta por día", "Cheque prom.",
                            "Personas/mesa", "% Bebidas", "Propina", "Propina %", "Cortesías", "Min. por mesa",
                            "Var. venta/día", ""])
        for i, f in enumerate(r.detalle, start=4):
            m = f.m
            ws.cell(i, 1, f.nombre)
            for col, v, fmt in ((2, m.dias, ENTERO), (3, m.cuentas, ENTERO), (4, m.personas, ENTERO),
                                (5, m.venta_bruta, MONEDA), (6, m.venta_por_dia, MONEDA), (7, m.cheque_promedio, MONEDA),
                                (9, m.pct_bebidas, PORCENTAJE), (10, m.propina, MONEDA), (11, m.pct_propina, PORCENTAJE),
                                (12, m.cortesias, MONEDA), (13, m.tiempo_mesa, ENTERO)):
                _numero(ws, i, col, v, fmt)
            c = ws.cell(i, 8, float(m.personas_por_mesa) if m.personas_por_mesa is not None else None)
            c.number_format = "0.0"
            if f.semaforo_cheque:
                ws.cell(i, 7).fill = PatternFill("solid", fgColor=FONDO_SEMAFORO[f.semaforo_cheque])
            _variacion(ws, i, 14, f.var_venta_dia, MONEDA)
        fila = 4 + len(r.detalle)
        t = r.actual.total
        ws.cell(fila, 1, "Total").font = Font(bold=True)
        for col, v, fmt in ((3, t.cuentas, ENTERO), (4, t.personas, ENTERO), (5, t.venta_bruta, MONEDA),
                            (6, r.actual.venta_por_mesero_dia, MONEDA), (7, t.cheque_promedio, MONEDA),
                            (9, t.pct_bebidas, PORCENTAJE), (10, t.propina, MONEDA), (11, t.pct_propina, PORCENTAJE),
                            (12, t.cortesias, MONEDA), (13, t.tiempo_mesa, ENTERO)):
            _numero(ws, fila, col, v, fmt)
            ws.cell(fila, col).font = Font(bold=True)
        anchos = (32, 7, 8, 9, 14, 14, 13, 12, 10, 12, 10, 12, 12, 12, 4)
    for col, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[ws.cell(1, col).column_letter].width = ancho


def generar(reportes: list[ReporteMeseros]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    varios = len(reportes) > 1
    for r in reportes:
        _resumen(_hoja(wb, r, "Resumen", varios), r)
        for g, nombre in zip(r.graficas, ["Venta", "Cheque"]):
            _datos_grafica(_hoja(wb, r, nombre, varios), g)
        _detalle(_hoja(wb, r, "Meseros" if not r.por_sucursal else "Sucursales", varios), r)
        _notas(_hoja(wb, r, "Notas", varios), r)
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def nombre_archivo(reportes: list[ReporteMeseros]) -> str:
    return nombre_base(reportes) + ".xlsx"
