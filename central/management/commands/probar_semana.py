"""Print, for one branch and one week, everything the weekly commercial
report reads from its sources (read-only). A verification tool: use it to
check the numbers against the source systems before trusting the report.

    python manage.py probar_semana puebla 2026-09-14
    python manage.py probar_semana acoxpa            # week of today
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from cuentas.models import Sucursal
from central.motor import periodos
from central.motor.fuentes import conexiones, presupuestos, wansoft


class Command(BaseCommand):
    help = "Show the weekly report inputs for a branch (read-only verification)."

    def add_arguments(self, parser):
        parser.add_argument("clave", help="Branch key, e.g. puebla")
        parser.add_argument("fecha", nargs="?", help="Any date inside the week (YYYY-MM-DD); default today")

    def handle(self, *args, clave, fecha=None, **options):
        try:
            suc = Sucursal.objects.get(clave=clave)
        except Sucursal.DoesNotExist:
            raise CommandError(f"Unknown branch '{clave}'. Run: manage.py cargar_sucursales")
        ref = date.fromisoformat(fecha) if fecha else date.today()
        lunes, domingo = periodos.semana_lunes_domingo(ref)
        ant = periodos.semana_anterior(lunes)
        anio = periodos.misma_semana_anio_anterior(lunes)
        periodos_a_ver = [("Semana", (lunes, domingo)), ("Semana anterior", ant), ("Misma semana anio anterior", anio)]

        self.stdout.write(f"\n{suc.nombre}")
        with conexiones.abrir_wansoft() as cur:
            for etiqueta, rango in periodos_a_ver:
                if rango is None:
                    self.stdout.write(f"\n== {etiqueta}: sin equivalente (semana 53)")
                    continue
                d, h = rango
                self.stdout.write(f"\n== {etiqueta}: {d} a {h}")
                por_dia = wansoft.cierres_por_dia(cur, suc.wansoft_subsidiary_id, d, h)
                total = sum((x["venta_bruta"] for x in por_dia.values()), 0)
                neta = sum((x["venta_neta"] for x in por_dia.values()), 0)
                self.stdout.write(f"   cierres: {len(por_dia)}/7 dias con cierre, venta bruta {total:,.2f}, neta {neta:,.2f}")
                for dia in sorted(por_dia):
                    self.stdout.write(f"     {dia} {por_dia[dia]['venta_bruta']:>12,.2f}")
                n = wansoft.dias_con_detalle(cur, suc.wansoft_ticket_nombre, d, h)
                self.stdout.write(f"   detalle de tickets: {n}/7 dias")
                self.stdout.write(f"   canal: { {k: float(v) for k, v in wansoft.venta_por_canal(cur, suc.wansoft_ticket_nombre, d, h).items()} }")
                self.stdout.write(f"   mix: { {k: float(v) for k, v in wansoft.mix_alimentos_bebidas(cur, suc.wansoft_ticket_nombre, d, h).items()} }")

        self.stdout.write("\n== Costo de Ventas (Presupuestos AP)")
        if suc.odoo_company_id is None:
            self.stdout.write("   sucursal sin odoo_company_id: sin presupuesto")
            return
        with conexiones.abrir_presupuestos() as cur:
            real = presupuestos.gasto_real_costo_ventas(cur, suc.odoo_company_id, lunes)
            ppto = presupuestos.presupuesto_costo_ventas(cur, suc.odoo_company_id, lunes, domingo)
        self.stdout.write(f"   real de la semana: {real if real is None else f'{real:,.2f}'}")
        self.stdout.write(f"   presupuesto prorrateado: {ppto if ppto is None else f'{ppto:,.2f}'}")
