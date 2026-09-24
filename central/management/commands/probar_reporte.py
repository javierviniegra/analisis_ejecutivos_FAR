"""Build the commercial report's indicators for any branches and any period
from the real (read-only) sources and print the table. A verification tool.

    python manage.py probar_reporte puebla --tipo semana --fecha 2026-09-14
    python manage.py probar_reporte puebla acoxpa antenas --tipo mes --fecha 2026-08-15
    python manage.py probar_reporte todas --tipo bimestre --fecha 2026-08-15 --consolidado
    python manage.py probar_reporte puebla --tipo rango --desde 2026-09-01 --hasta 2026-09-20
"""

import sys
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from central.motor import formato, metricas
from central.motor.fuentes import conexiones
from central.motor.periodo import Periodo, TipoPeriodo
from central.motor.tabla_comercial import construir_tabla
from cuentas.models import Sucursal


class Command(BaseCommand):
    help = "Print the commercial report indicators for branches and a period (read-only verification)."

    def add_arguments(self, parser):
        parser.add_argument("sucursales", nargs="+", help="Branch keys (e.g. puebla acoxpa) or 'todas'")
        parser.add_argument("--tipo", default="semana", choices=[t.value for t in TipoPeriodo])
        parser.add_argument("--fecha", help="A date inside the period (YYYY-MM-DD); default today")
        parser.add_argument("--desde", help="Range start (tipo rango)")
        parser.add_argument("--hasta", help="Range end (tipo rango)")
        parser.add_argument("--consolidado", action="store_true", help="Add the selected branches into one report")

    def _periodo(self, tipo, fecha, desde, hasta) -> Periodo:
        if tipo == TipoPeriodo.RANGO:
            if not (desde and hasta):
                raise CommandError("tipo rango needs --desde and --hasta")
            return Periodo.rango(date.fromisoformat(desde), date.fromisoformat(hasta))
        return Periodo.de_fecha(tipo, date.fromisoformat(fecha) if fecha else date.today())

    def handle(self, *args, sucursales, tipo, fecha, desde, hasta, consolidado, **options):
        # Windows consoles default to cp1252, which cannot print the arrows.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        periodo = self._periodo(TipoPeriodo(tipo), fecha, desde, hasta)
        if sucursales == ["todas"]:
            elegidas = list(Sucursal.objects.filter(activa=True, wansoft_subsidiary_id__isnull=False))
        else:
            elegidas = list(Sucursal.objects.filter(clave__in=sucursales))
            faltan = set(sucursales) - {s.clave for s in elegidas}
            if faltan:
                raise CommandError(f"Unknown branches: {sorted(faltan)}. Run: manage.py cargar_sucursales")

        anterior = periodo.anterior()
        anio_ant = periodo.mismo_periodo_anio_anterior()
        self.stdout.write(f"\nPeriodo: {periodo.etiqueta()}  ({periodo.desde} a {periodo.hasta}, {periodo.dias} dias)")
        self.stdout.write(f"Anterior: {anterior.etiqueta()}")
        self.stdout.write(f"Mismo periodo anio anterior: {anio_ant.etiqueta() if anio_ant else 'sin equivalente'}")

        with conexiones.abrir_wansoft() as cw, conexiones.abrir_presupuestos() as cp:
            def leer(p):
                return [metricas.recolectar(cw, cp, s, p) for s in elegidas] if p else None

            ma, mp, my = leer(periodo), leer(anterior), leer(anio_ant)

        if consolidado:
            juntos = [("CONSOLIDADO (" + ", ".join(s.nombre for s in elegidas) + ")",
                       metricas.consolidar(ma, periodo),
                       metricas.consolidar(mp, anterior),
                       metricas.consolidar(my, anio_ant) if my else None)]
        else:
            juntos = [(s.nombre, ma[i], mp[i], my[i] if my else None) for i, s in enumerate(elegidas)]

        for nombre, a, p, y in juntos:
            self.stdout.write(f"\n=== {nombre}")
            self.stdout.write(f"    cobertura: cierres {a.dias_con_cierre}/{a.dias_esperados} dias, "
                              f"detalle de tickets {a.dias_con_detalle}/{a.dias_esperados} dias")
            seccion = None
            for f in construir_tabla(a, p, y):
                if f.indicador.seccion != seccion:
                    seccion = f.indicador.seccion
                    self.stdout.write(f"  -- {seccion}")
                fm = f.indicador.formato
                self.stdout.write(
                    f"    {f.indicador.etiqueta:<36} {formato.valor(f.actual, fm):>16} | "
                    f"ant {formato.valor(f.anterior, fm):>16} {formato.variacion(f.var_anterior, fm):>12} | "
                    f"a.ant {formato.valor(f.anio_anterior, fm):>16} {formato.variacion(f.var_anio, fm):>12}"
                )
