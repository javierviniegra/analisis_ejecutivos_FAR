"""Excel workbook of the cash-flow report (asked by the accountant): the
statement as in the PDF, per company and per account, the largest
suppliers, every classified bank movement (so Contabilidad can trace each
figure) and the notes. One sheet group per report when several share a file."""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from ..motor import flujo_efectivo as fe
from ..motor.flujo_efectivo import ReporteFlujo, nombre_base
from . import AVISO_AUTOMATICO, pie_excel
from .excel_comercial import ENCABEZADO_F, ENCABEZADO_R, PAR_R, SECCION_F, SUAVE_F, TITULO_F
from .pdf_flujo import filas

PESOS = '"$"#,##0;[Red]-"$"#,##0'


def _hoja(wb: Workbook, r: ReporteFlujo, nombre: str, varios: bool):
    titulo = f"{r.nombre[:18]} · {nombre}" if varios else nombre
    return wb.create_sheet(titulo[:31])


def _encabezado(ws, fila: int, titulos: list[str]):
    for col, texto in enumerate(titulos, start=1):
        c = ws.cell(fila, col, texto)
        c.font, c.fill = ENCABEZADO_F, ENCABEZADO_R


def _pesos(ws, fila: int, col: int, valor, negrita: bool = False):
    c = ws.cell(fila, col, float(valor) if valor is not None else None)
    c.number_format = PESOS
    if negrita:
        c.font = Font(bold=True)
    return c


def _anchos(ws, anchos):
    for i, a in enumerate(anchos, start=1):
        ws.column_dimensions[chr(64 + i)].width = a


def _estado(ws, r: ReporteFlujo):
    p, nombre = r.periodo, (f"Consolidado ({len(r.empresas)} empresas)" if r.consolidado else r.nombre)
    ws["A1"] = f"{fe.TITULO} · {nombre}"
    ws["A1"].font = TITULO_F
    ws["A2"] = f"{p.etiqueta()} ({p.desde:%d/%m/%Y} al {p.hasta:%d/%m/%Y})"
    ant = p.anterior()
    ws["A3"] = (f"Comparado con: {ant.etiqueta()} ({ant.desde:%d/%m/%Y} al {ant.hasta:%d/%m/%Y})" if r.anteriores is not None
                else "Sin periodo anterior comparable")
    ws["A3"].font = SUAVE_F
    _encabezado(ws, 5, ["Concepto", "Periodo", "Anterior", "Variación"])
    fila = 6
    for etiqueta, a, b, estilo in filas(r):
        c = ws.cell(fila, 1, ("    " if estilo == "i" else "") + etiqueta)
        if estilo == "h":
            c.font = SECCION_F
        elif estilo == "i":
            c.font = SUAVE_F
        else:
            negrita = estilo == "t"
            c.font = Font(bold=negrita)
            if negrita:
                for col in range(1, 5):
                    ws.cell(fila, col).fill = PAR_R
            _pesos(ws, fila, 2, a, negrita)
            _pesos(ws, fila, 3, b, negrita)
            if b is not None and not etiqueta.startswith("Saldo"):
                _pesos(ws, fila, 4, a - b)
        if estilo == "i":
            _pesos(ws, fila, 2, a)
            _pesos(ws, fila, 3, b)
            if b is not None:
                _pesos(ws, fila, 4, a - b)
        fila += 1
    _anchos(ws, (52, 16, 16, 16))


def _por_empresa(ws, r: ReporteFlujo):
    ws["A1"] = "Por empresa"
    ws["A1"].font = SECCION_F
    rubros = fe.ENTRADAS + fe.SALIDAS + fe.NEUTROS
    _encabezado(ws, 3, ["Empresa", "Grupo", "Saldo inicial"] + [fe.ETIQUETAS[k] for k in rubros] + ["Saldo final"])
    fila = 4
    for e in r.empresas + [None]:
        empresas = r.empresas if e is None else [e]
        x = ReporteFlujo.cifras(empresas)
        ws.cell(fila, 1, "Total" if e is None else e.nombre).font = Font(bold=e is None)
        ws.cell(fila, 2, "" if e is None else e.grupo)
        _pesos(ws, fila, 3, x["saldo_inicial"], e is None)
        for i, k in enumerate(rubros, start=4):
            _pesos(ws, fila, i, x["rubros"][k], e is None)
        _pesos(ws, fila, 4 + len(rubros), x["saldo_final"], e is None)
        fila += 1
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 30, 22
    ws.freeze_panes = "C4"


def _cuentas(ws, r: ReporteFlujo):
    ws["A1"] = "Bancos e inversiones por cuenta"
    ws["A1"].font = SECCION_F
    _encabezado(ws, 3, ["Empresa", "Código", "Cuenta (diario)", "Saldo inicial", "Saldo final", "Cambio"])
    fila = 4
    for e in r.empresas:
        for cta in e.cuentas:
            ws.cell(fila, 1, e.nombre)
            ws.cell(fila, 2, cta.codigo)
            ws.cell(fila, 3, cta.nombre)
            _pesos(ws, fila, 4, cta.saldo_inicial)
            _pesos(ws, fila, 5, cta.saldo_final)
            _pesos(ws, fila, 6, cta.saldo_final - cta.saldo_inicial)
            fila += 1
    _anchos(ws, (30, 12, 34, 16, 16, 16))


def _proveedores(ws, r: ReporteFlujo):
    ws["A1"] = "Proveedores (incluye rentas y empresas del grupo)"
    ws["A1"].font = SECCION_F
    previos = dict(r.proveedores(r.anteriores, n=10_000)) if r.anteriores is not None else {}
    _encabezado(ws, 3, ["Proveedor", "Periodo", "Anterior"])
    for i, (s, v) in enumerate(r.proveedores(n=10_000), start=4):
        ws.cell(i, 1, s)
        _pesos(ws, i, 2, v)
        _pesos(ws, i, 3, previos.get(s) if r.anteriores is not None else None)
    _anchos(ws, (50, 16, 16))


def _movimientos(ws, r: ReporteFlujo):
    """Every classified piece of a bank movement of the period: what each figure is made of."""
    ws["A1"] = "Movimientos del periodo (cada movimiento bancario, clasificado)"
    ws["A1"].font = SECCION_F
    _encabezado(ws, 3, ["Empresa", "Fecha", "Cuenta (diario)", "Renglón", "Detalle", "Contraparte", "Referencia", "Monto"])
    nombres = {e.compania_id: e.nombre for e in r.empresas}
    movs = sorted((m for e in r.empresas for m in e.movimientos), key=lambda m: (nombres[m.compania_id], m.fecha, m.diario))
    for i, m in enumerate(movs, start=4):
        ws.cell(i, 1, nombres[m.compania_id])
        ws.cell(i, 2, m.fecha).number_format = "dd/mm/yyyy"
        ws.cell(i, 3, m.diario)
        ws.cell(i, 4, fe.ETIQUETAS[m.rubro])
        ws.cell(i, 5, m.detalle)
        ws.cell(i, 6, m.socio)
        ws.cell(i, 7, m.referencia)
        _pesos(ws, i, 8, m.monto)
    ws.auto_filter.ref = f"A3:H{max(3, len(movs) + 3)}"
    ws.freeze_panes = "A4"
    _anchos(ws, (28, 11, 24, 34, 34, 34, 44, 14))


def _notas(ws, r: ReporteFlujo):
    ws["A1"] = "Notas"
    ws["A1"].font = SECCION_F
    notas = fe.notas_de(r) if r.empresas else r.notas
    for i, nota in enumerate(notas, start=3):
        c = ws.cell(i, 1, "• " + nota)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 15 * (1 + len(nota) // 120)
    ws.cell(len(notas) + 4, 1, AVISO_AUTOMATICO).font = Font(italic=True, color="555555")
    ws.column_dimensions["A"].width = 130


def generar(reportes: list[ReporteFlujo]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    varios = len(reportes) > 1
    for r in reportes:
        if r.empresas:
            _estado(_hoja(wb, r, "Flujo", varios), r)
            if r.consolidado:
                _por_empresa(_hoja(wb, r, "Por empresa", varios), r)
            _cuentas(_hoja(wb, r, "Cuentas", varios), r)
            _proveedores(_hoja(wb, r, "Proveedores", varios), r)
            _movimientos(_hoja(wb, r, "Movimientos", varios), r)
        _notas(_hoja(wb, r, "Notas", varios), r)
    pie_excel(wb)
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def nombre_archivo(reportes: list[ReporteFlujo]) -> str:
    return nombre_base(reportes) + ".xlsx"
