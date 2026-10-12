"""Send the automations that are due (run every 15 minutes by Task Scheduler).

    python manage.py enviar_automatizaciones                 # what is due now
    python manage.py enviar_automatizaciones --pendientes    # only list what is due, send nothing
    python manage.py enviar_automatizaciones --probar 3      # automation 3 now, for its last closed
                                                             # period, without touching the send log
    python manage.py enviar_automatizaciones --forzar 3      # resend automation 3's last closed period
                                                             # to everyone, recorded in the send log

How mail leaves depends on CORREO_MODO in config/.env: in dev the e-mails are
saved as .eml files under logs/correos/ (nothing is sent).
"""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from central import envios
from central.models import Automatizacion
from central.motor.periodo import TipoPeriodo
from central.motor.programacion import periodo_a_enviar


class Command(BaseCommand):
    help = "Send the scheduled report e-mails that are due."

    def add_arguments(self, parser):
        parser.add_argument("--pendientes", action="store_true", help="List what is due without sending")
        parser.add_argument("--probar", type=int, metavar="ID", help="Send this automation now (test; no log)")
        parser.add_argument("--forzar", type=int, metavar="ID",
                            help="Resend this automation's last closed period to everyone (recorded in the log)")

    def handle(self, *args, pendientes, probar, forzar, **options):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        ahora = envios.ahora_local()
        self.stdout.write(f"{ahora:%Y-%m-%d %H:%M} · correo: {settings.CORREO_MODO}")
        if forzar:
            try:
                a = Automatizacion.objects.select_related("reporte").get(pk=forzar)
            except Automatizacion.DoesNotExist:
                raise CommandError(f"No existe la automatizacion {forzar}")
            envio = envios.forzar(a, ahora)
            self.stdout.write(f"  REENVIO FORZADO {a} · {envio.desde:%d/%m/%Y}: {envio.get_estado_display()}")
            if envio.error:
                self.stdout.write(f"    {envio.error}")
            return
        if probar:
            try:
                a = Automatizacion.objects.select_related("reporte").get(pk=probar)
            except Automatizacion.DoesNotExist:
                raise CommandError(f"No existe la automatización {probar}")
            periodo = periodo_a_enviar(TipoPeriodo(a.tipo), a.dias_despues, a.hora, ahora)
            estado, lineas, archivos, error = envios.ejecutar(a, periodo)
            self._informe(a, periodo, estado, lineas, archivos, error)
            return
        if pendientes:
            for a, periodo, programado, envio in envios.pendientes(ahora):
                intento = f" (reintento {envio.intentos + 1})" if envio else ""
                self.stdout.write(f"  {a} · {periodo.etiqueta()} · programado {programado:%d/%m %H:%M}{intento}")
            return
        for envio in envios.despachar(ahora):
            a = envio.automatizacion
            self.stdout.write(f"  {a} · {envio.desde:%d/%m/%Y}: {envio.get_estado_display()} (intento {envio.intentos})")
            if envio.error:
                self.stdout.write(f"    {envio.error}")

    def _informe(self, a, periodo, estado, lineas, archivos, error):
        self.stdout.write(f"  {a} · {periodo.etiqueta()}: {estado}")
        for linea in lineas:
            self.stdout.write(f"    {linea}")
        self.stdout.write(f"    archivos: {len(archivos)}")
        if error:
            self.stdout.write(f"    {error}")
