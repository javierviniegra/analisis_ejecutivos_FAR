"""Seed the report catalog with the reports agreed so far.

Idempotent and non-destructive: a report that already exists (by `clave`) is
left untouched, so anything edited in the admin (profiles, notes, state) is
never overwritten. New keys are created with no profiles assigned, meaning
nobody but staff sees them until access is granted in the admin.
"""

from django.core.management.base import BaseCommand

from reportes.models import Reporte

C, P, F, S = Reporte.Categoria, Reporte.Periodicidad, Reporte.Plantilla, Reporte.Fuente
A, E = Reporte.Alcance, Reporte.Estado

CATALOGO = [
    dict(
        clave="resumen-ejecutivo-sucursal",
        nombre="Resumen ejecutivo por sucursal",
        descripcion="Ventas y costos de cada sucursal (plantilla ejecutiva estandar Fonda). "
        "Hoy existe como script (scripts/build_executive_pdf_all.py), 19 sucursales.",
        categoria=C.EJECUTIVO, periodicidad=P.MENSUAL, plantilla=F.EJECUTIVA, fuente=S.MIXTA,
        alcance=A.POR_SUCURSAL, admite_pdf=True, estado=E.DEFINIDO,
        notas="Semanal y anual con comparativos (vs periodo anterior y vs mismo periodo del anio anterior, con flechas) pendientes.",
    ),
    dict(
        clave="comercial-semanal-gerentes",
        nombre="Reporte comercial semanal para gerentes",
        descripcion="Reporte comercial semanal dirigido a gerentes.",
        categoria=C.COMERCIAL, periodicidad=P.SEMANAL, plantilla=F.EJECUTIVA, fuente=S.MIXTA,
        alcance=A.POR_SUCURSAL, admite_pdf=True, estado=E.PENDIENTE,
        notas="Contenido y metricas aun no definidos.",
    ),
    dict(
        clave="inversionistas-corto-mensual",
        nombre="Reporte corto de inversionistas",
        descripcion="Informe financiero, operativo y comercial de una pagina: venta neta vs meta, costo de insumos, "
        "EBITDA, utilidad neta y estado de resultados presupuesto vs real.",
        categoria=C.INVERSIONISTAS, periodicidad=P.MENSUAL, plantilla=F.EJECUTIVA, fuente=S.MIXTA,
        alcance=A.POR_SUCURSAL, admite_pdf=True, estado=E.DEFINIDO,
        notas="Ejemplo en docs/Ejemplos (no versionado). Presupuesto: Presupuestos AP y Odoo; real: Odoo.",
    ),
    dict(
        clave="financiero-operativo-socios-mensual",
        nombre="Informe financiero y operativo para socios",
        descripcion="Informe mensual en PDF para los socios.",
        categoria=C.FINANCIERO, periodicidad=P.MENSUAL, plantilla=F.FINANCIERA, fuente=S.MIXTA,
        alcance=A.CONSOLIDADO, admite_pdf=True, estado=E.PENDIENTE,
        notas="Requiere disenar la plantilla nueva (colores y logo Fonda Argentina). Contenido por definir.",
    ),
    dict(
        clave="oc-bodegon-empanadas-modificaciones",
        nombre="OC Bodegon/Empanadas: modificaciones",
        descripcion="Ordenes de compra a proveedores internos modificadas despues de confirmar: cambios de cantidad, "
        "lineas extra y cambios de monto, por sucursal.",
        categoria=C.COMPRAS, periodicidad=P.SEMANAL, plantilla=F.TABULAR, fuente=S.ODOO,
        alcance=A.CONSOLIDADO, admite_excel=True, estado=E.DEFINIDO,
        notas="Ejemplo generado en el repo Wansoft (reports/ordenes_compra_proveedores_internos).",
    ),
    dict(
        clave="oc-bodegon-empanadas-por-hora",
        nombre="OC Bodegon/Empanadas: ordenes por hora",
        descripcion="Ordenes de compra a proveedores internos por hora de creacion y porcentaje de modificaciones, por sucursal.",
        categoria=C.COMPRAS, periodicidad=P.SEMANAL, plantilla=F.TABULAR, fuente=S.ODOO,
        alcance=A.CONSOLIDADO, admite_excel=True, estado=E.DEFINIDO,
        notas="Ejemplo generado en el repo Wansoft (reports/ordenes_compra_proveedores_internos).",
    ),
    dict(
        clave="rentabilidad-plataformas-mensual",
        nombre="Rentabilidad por plataforma (Uber, Didi y demas)",
        descripcion="Reporte mensual para saber si cada plataforma de reparto (Uber, Didi y las demas) es rentable "
        "despues de comisiones y costos.",
        categoria=C.COMERCIAL, periodicidad=P.MENSUAL, plantilla=F.EJECUTIVA, fuente=S.MIXTA,
        alcance=A.CONSOLIDADO, admite_pdf=True, admite_excel=True, estado=E.PENDIENTE,
        notas="Por definir: lista de plataformas; de donde salen ventas por plataforma (Wansoft: canal de la orden) y "
        "comisiones/costos (Odoo); si se calcula por sucursal o consolidado; formula de rentabilidad (comisiones, "
        "empaque, costo de producto, descuentos/promociones).",
    ),
    dict(
        clave="indicadores-operativos-semanal",
        nombre="Indicadores operativos semanal",
        descripcion="Tabla semanal de indicadores operativos (tabla de Carlos en Power BI) con semaforos.",
        categoria=C.OPERATIVO, periodicidad=P.SEMANAL, plantilla=F.SEMAFOROS, fuente=S.MYSQL_PROD,
        alcance=A.POR_SUCURSAL, admite_pdf=True, admite_excel=True, estado=E.PENDIENTE,
        notas="Faltan: estructura de la tabla, metricas y reglas de los semaforos (umbrales y colores) del Power BI.",
    ),
]


class Command(BaseCommand):
    help = "Load the initial report catalog (idempotent, never overwrites existing reports)."

    def handle(self, *args, **options):
        for datos in CATALOGO:
            _, creado = Reporte.objects.get_or_create(clave=datos["clave"], defaults=datos)
            estado = "Creado" if creado else "Ya existia (sin cambios)"
            self.stdout.write(f"{estado}: {datos['nombre']}")
