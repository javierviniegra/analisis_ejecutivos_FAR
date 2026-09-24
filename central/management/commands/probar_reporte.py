"""Build the commercial report's indicators for any branches and any period
from the real (read-only) sources and print the Lectura box, the table and the footnotes. A verification tool.

    python manage.py probar_reporte puebla --tipo semana --fecha 2026-09-14
    python manage.py probar_reporte puebla acoxpa antenas --tipo mes --fecha 2026-08-15
    python manage.py probar_reporte todas --tipo bimestre --fecha 2026-08-15 --consolidado
    python manage.py probar_reporte puebla --tipo rango --desde 2026-09-01 --hasta 2026-09-20
    python manage.py probar_reporte puebla --tipo semana --fecha 2026-09-14 --graficas C:/temp/graficas
"""

import sys
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from central.motor import formato, metricas
from central.motor.graficas import construir_graficas, ventana_tendencia
from central.motor.graficas_png import dibujar
from central.motor.lectura import construir_lectura
from central.motor.notas import notas_pie
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
        parser.add_argument("--graficas", help="Folder where the charts are saved as PNG (optional)")

    def _periodo(self, tipo, fecha, desde, hasta) -> Periodo:
        if tipo == TipoPeriodo.RANGO:
            if not (desde and hasta):
                raise CommandError("tipo rango needs --desde and --hasta")
            return Periodo.rango(date.fromisoformat(desde), date.fromisoformat(hasta))
        return Periodo.de_fecha(tipo, date.fromisoformat(fecha) if fecha else date.today())

    def handle(self, *args, sucursales, tipo, fecha, desde, hasta, consolidado, graficas, **options):
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
                return metricas.recolectar(cw, cp, elegidas, p) if p else None

            ma, mp = leer(periodo), leer(anterior)
            my = mp if anio_ant == anterior else leer(anio_ant)  # a year: both comparisons are the same period
            diario = None
            if graficas and periodo.tipo == TipoPeriodo.MES:  # the month trend chart needs 24 months of closings
                diario = metricas.recolectar_diario(cw, elegidas, *ventana_tendencia(periodo))

        if consolidado:
            nombres = [s.nombre for s in elegidas]
            juntos = [("CONSOLIDADO (" + ", ".join(nombres) + ")",
                       metricas.consolidar(ma, periodo),
                       metricas.comparables(nombres, ma, mp, periodo, anterior),
                       metricas.comparables(nombres, ma, my, periodo, anio_ant))]
        else:
            juntos = [(s.nombre, ma[i],
                       metricas.comparables([s.nombre], [ma[i]], [mp[i]], periodo, anterior),
                       metricas.comparables([s.nombre], [ma[i]], [my[i]] if my else None, periodo, anio_ant))
                      for i, s in enumerate(elegidas)]

        for nombre, a, p, y in juntos:
            self.stdout.write(f"\n=== {nombre}")
            self.stdout.write(f"    cobertura: cierres {a.dias_con_cierre}/{a.dias_esperados} dias, "
                              f"detalle de tickets {a.dias_con_detalle}/{a.dias_esperados} dias")
            lectura = construir_lectura(periodo, a, p, y)
            self.stdout.write(f"  -- {lectura.titulo}")
            for o in lectura.observaciones:
                self.stdout.write(f"    [{o.tono}] {o.texto}")
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
            self.stdout.write("  -- Notas")
            for n in notas_pie(periodo, a, p, y):
                self.stdout.write(f"    * {n}")
            if graficas:
                carpeta = Path(graficas)
                carpeta.mkdir(parents=True, exist_ok=True)
                serie = {nombre: diario[nombre]} if diario is not None and not consolidado else diario
                for i, g in enumerate(construir_graficas(periodo, a, p, y, serie), start=1):
                    archivo = carpeta / f"{nombre.split(' (')[0].replace(' ', '_')}_{periodo.tipo.value}_{i}.png"
                    archivo.write_bytes(dibujar(g))
                    self.stdout.write(f"    grafica: {archivo}")
