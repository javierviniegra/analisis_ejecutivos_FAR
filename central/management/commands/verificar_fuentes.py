"""Check the report sources against what the engine needs (read-only).

Run it right after any change on the source side (first of all the
2026-10-01 Wansoft cutover) and after changing the source accounts in
config/.env:

    python manage.py verificar_fuentes
    python manage.py verificar_fuentes --hoy 2026-10-01

Each line is PASS, WARN or FAIL; the command exits with an error if any FAIL.
FAIL = the engine cannot work (missing table/column, no connection).
WARN = it works, but something needs attention (an account that can write,
stale data for some branch, the cutover migration not applied yet).
"""

import sys
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from central.motor.fuentes import conexiones, presupuestos, verificacion, wansoft
from cuentas.models import Sucursal


class Command(BaseCommand):
    help = "Check that the report sources fit the engine (read-only): schema, account rights, freshness."

    def add_arguments(self, parser):
        parser.add_argument("--hoy", help="Reference date for freshness (YYYY-MM-DD); default today")
        parser.add_argument("--sin-tickets", action="store_true",
                            help="Skip the ticket freshness check (it scans the large ticket table)")

    def _linea(self, estado: str, texto: str):
        estilo = {"PASS": self.style.SUCCESS, "WARN": self.style.WARNING, "FAIL": self.style.ERROR}[estado]
        self.stdout.write(f"{estilo(estado)}  {texto}")
        self.resultados.append(estado)

    def _esquema(self, cur, requeridas, base):
        falta = verificacion.faltantes(requeridas, verificacion.leer_columnas(cur, list(requeridas)))
        if falta:
            for tabla, cols in falta.items():
                self._linea("FAIL", f"{base}.{tabla}: faltan columnas {', '.join(cols)}")
        else:
            self._linea("PASS", f"{base}: existen las {len(requeridas)} tablas y todas las columnas que usa el motor")

    def _cuenta(self, cur, base):
        if verificacion.puede_escribir(verificacion.leer_grants(cur)):
            self._linea("WARN", f"{base}: la cuenta configurada tiene permisos de escritura; usar el usuario de solo "
                                "lectura central_reportes (deploy/sql/create_central_reportes_readonly_user.sql)")
        else:
            self._linea("PASS", f"{base}: la cuenta configurada es de solo lectura")

    def handle(self, *args, hoy, sin_tickets, **options):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        self.resultados = []
        hoy = date.fromisoformat(hoy) if hoy else date.today()
        sucursales = list(Sucursal.objects.filter(activa=True, wansoft_subsidiary_id__isnull=False))
        self.stdout.write(f"Fuentes: {conexiones.origen()} · referencia {hoy} · {len(sucursales)} sucursales activas\n")

        try:
            with conexiones.abrir_wansoft() as cur:
                cur.execute("SELECT DATABASE()")
                base = cur.fetchone()[0]
                self._linea("PASS", f"conexión a Wansoft ({base}), sesión de solo lectura")
                self._esquema(cur, wansoft.COLUMNAS_REQUERIDAS, base)
                self._cuenta(cur, base)
                if verificacion.leer_llave_unica_cierres(cur):
                    self._linea("PASS", f"{base}.getglobalcashclosing tiene la llave única de la migración")
                else:
                    self._linea("WARN", f"{base}.getglobalcashclosing sin llave única: migración del corte no aplicada aún")

                ultimos = verificacion.leer_ultimo_cierre(cur, [s.wansoft_subsidiary_id for s in sucursales], hoy)
                self._frescura("cierres de caja", {s.nombre: ultimos.get(s.wansoft_subsidiary_id) for s in sucursales}, hoy)
                if not sin_tickets:
                    con_detalle = [s for s in sucursales if s.wansoft_ticket_nombre]
                    tickets = verificacion.leer_ultimo_ticket(cur, [s.wansoft_ticket_nombre for s in con_detalle], hoy)
                    self._frescura("detalle de tickets", {s.nombre: tickets.get(s.wansoft_ticket_nombre) for s in con_detalle}, hoy)
        except Exception as e:  # no connection / no rights: the engine cannot work
            self._linea("FAIL", f"Wansoft: {type(e).__name__}: {e}")

        try:
            with conexiones.abrir_presupuestos() as cur:
                cur.execute("SELECT DATABASE()")
                base = cur.fetchone()[0]
                self._linea("PASS", f"conexión a Presupuestos AP ({base}), sesión de solo lectura")
                self._esquema(cur, presupuestos.COLUMNAS_REQUERIDAS, base)
                self._cuenta(cur, base)
        except Exception as e:
            self._linea("FAIL", f"Presupuestos AP: {type(e).__name__}: {e}")

        fallas, avisos = self.resultados.count("FAIL"), self.resultados.count("WARN")
        self.stdout.write(f"\nResultado: {len(self.resultados)} revisiones, {fallas} FAIL, {avisos} WARN")
        if fallas:
            raise CommandError("Hay revisiones en FAIL: el motor no puede trabajar con estas fuentes.")

    def _frescura(self, que: str, ultimo: dict, hoy: date):
        viejas = verificacion.atrasadas(ultimo, hoy)
        mas_reciente = max((d for d in ultimo.values() if d), default=None)
        if not viejas:
            self._linea("PASS", f"{que}: todas las sucursales tienen datos al {mas_reciente}")
            return
        detalle = "; ".join(f"{n} {d or 'sin datos en el periodo revisado'}" for n, d in viejas)
        self._linea("WARN", f"{que}: {len(viejas)} sucursal(es) atrasadas (último día): {detalle}")
