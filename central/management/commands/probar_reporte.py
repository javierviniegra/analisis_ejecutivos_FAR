"""Build the commercial report for any branches and any period from the real
(read-only) sources and print it: Lectura, indicators table and footnotes.
Optionally save the charts as PNG and the PDF. A verification tool.

    python manage.py probar_reporte puebla --tipo semana --fecha 2026-09-14
    python manage.py probar_reporte puebla acoxpa antenas --tipo mes --fecha 2026-08-15
    python manage.py probar_reporte todas --tipo bimestre --fecha 2026-08-15 --consolidado
    python manage.py probar_reporte puebla --tipo rango --desde 2026-09-01 --hasta 2026-09-20
    python manage.py probar_reporte puebla --tipo semana --fecha 2026-09-14 --graficas C:/temp/graficas --pdf C:/temp/pdf
"""

import sys
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from central.motor import formato, reporte_comercial
from central.motor.graficas_png import dibujar
from central.motor.periodo import Periodo, TipoPeriodo
from central.salidas import pdf_comercial
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
        parser.add_argument("--pdf", help="Folder where the PDF is saved, one per report (optional)")

    def _periodo(self, tipo, fecha, desde, hasta) -> Periodo:
        if tipo == TipoPeriodo.RANGO:
            if not (desde and hasta):
                raise CommandError("tipo rango needs --desde and --hasta")
            return Periodo.rango(date.fromisoformat(desde), date.fromisoformat(hasta))
        return Periodo.de_fecha(tipo, date.fromisoformat(fecha) if fecha else date.today())

    def handle(self, *args, sucursales, tipo, fecha, desde, hasta, consolidado, graficas, pdf, **options):
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

        self.stdout.write(f"\nPeriodo: {periodo.etiqueta()}  ({periodo.desde} a {periodo.hasta}, {periodo.dias} dias)")
        reportes = reporte_comercial.armar(elegidas, periodo, consolidado)
        for r in reportes:
            a = r.actual
            self.stdout.write(f"\n=== {r.nombre} ({', '.join(r.sucursales)})" if r.nombre == "Consolidado" else f"\n=== {r.nombre}")
            self.stdout.write(f"    cobertura: cierres {a.dias_con_cierre}/{a.dias_esperados} dias, "
                              f"detalle de tickets {a.dias_con_detalle}/{a.dias_esperados} dias")
            self.stdout.write(f"  -- {r.lectura.titulo}")
            for o in r.lectura.observaciones:
                self.stdout.write(f"    [{o.tono}] {o.texto}")
            seccion = None
            for f in r.filas:
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
            for n in r.notas:
                self.stdout.write(f"    * {n}")
            if graficas:
                carpeta = Path(graficas)
                carpeta.mkdir(parents=True, exist_ok=True)
                for i, g in enumerate(r.graficas, start=1):
                    archivo = carpeta / f"{r.nombre.replace(' ', '_')}_{periodo.tipo.value}_{i}.png"
                    archivo.write_bytes(dibujar(g))
                    self.stdout.write(f"    grafica: {archivo}")
            if pdf:
                carpeta = Path(pdf)
                carpeta.mkdir(parents=True, exist_ok=True)
                archivo = carpeta / pdf_comercial.nombre_archivo([r])
                archivo.write_bytes(pdf_comercial.generar([r]))
                self.stdout.write(f"    pdf: {archivo}")
