"""Report outputs (PDF and Excel) built from the engine's assembled reports."""

# Footer of every report (owner, 2026-10-14): the report and its data are automatic.
AVISO_AUTOMATICO = ("Reporte generado de forma automática por la Central de Reportes. Los datos se extraen "
                    "automáticamente de Wansoft y Odoo.")


def pie_excel(wb) -> None:
    """The automatic-report notice as the printed footer of every sheet."""
    for ws in wb.worksheets:
        ws.oddFooter.left.text = AVISO_AUTOMATICO
        ws.oddFooter.left.size = 7
