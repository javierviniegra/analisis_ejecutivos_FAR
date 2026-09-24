from datetime import date
from unittest import mock

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from cuentas.models import PerfilUsuario, Sucursal

from .generadores import Archivo
from .models import Reporte
from .motor.periodo import Periodo
from .tests import PLAIN_STATIC

CLAVE = "comercial-semanal-gerentes"


@PLAIN_STATIC
class GenerarTests(TestCase):
    def setUp(self):
        self.gerentes = Group.objects.create(name="Gerente")
        self.gerentes.permissions.add(Permission.objects.get(codename="generar_reportes"))
        self.reporte = Reporte.objects.create(
            clave=CLAVE, nombre="Comercial", categoria="comercial", periodicidad="semanal",
            plantilla="ejecutiva", fuente="mixta", alcance=Reporte.Alcance.AMBOS)
        self.reporte.perfiles.add(self.gerentes)
        self.puebla = Sucursal.objects.create(clave="puebla", nombre="Puebla", wansoft_subsidiary_id=1)
        self.acoxpa = Sucursal.objects.create(clave="acoxpa", nombre="Acoxpa", wansoft_subsidiary_id=2)
        self.gerente = User.objects.create_user("g", password="x")
        self.gerente.groups.add(self.gerentes)
        PerfilUsuario.objects.create(usuario=self.gerente).sucursales.add(self.puebla)
        self.url = reverse("reporte_generar", args=[CLAVE])
        self.client.force_login(self.gerente)
        patcher = mock.patch.dict("central.generadores.GENERADORES", {CLAVE: mock.Mock(
            return_value=Archivo(b"%PDF-falso", "Reporte.pdf", "application/pdf"))})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _generador(self):
        from .generadores import GENERADORES
        return GENERADORES[CLAVE]

    def test_formulario_solo_muestra_sus_sucursales(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Puebla")
        self.assertNotContains(r, "Acoxpa")

    def test_genera_y_descarga_el_pdf(self):
        r = self.client.post(self.url, {"sucursales": [self.puebla.pk], "tipo": "semana",
                                        "fecha": "2026-09-16", "modo": "por_sucursal"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn('attachment; filename="Reporte.pdf"', r["Content-Disposition"])
        sucursales, periodo, consolidado, separados = self._generador().call_args.args
        self.assertEqual(sucursales, [self.puebla])
        self.assertEqual(periodo, Periodo.semana_de(date(2026, 9, 16)))
        self.assertFalse(consolidado)
        self.assertFalse(separados)  # one branch: nothing to ask

    def test_no_puede_pedir_una_sucursal_ajena(self):
        r = self.client.post(self.url, {"sucursales": [self.acoxpa.pk], "tipo": "mes",
                                        "fecha": "2026-08-01", "modo": "consolidado"})
        self.assertEqual(r.status_code, 200)  # the form comes back with an error
        self.assertFalse(self._generador().called)

    def test_rango_y_validaciones(self):
        base = {"sucursales": [self.puebla.pk], "modo": "consolidado"}
        r = self.client.post(self.url, {**base, "tipo": "rango", "desde": "2026-09-10", "hasta": "2026-09-01"})
        self.assertContains(r, "no puede ser posterior")
        r = self.client.post(self.url, {**base, "tipo": "semana", "fecha": "2099-01-05"})
        self.assertContains(r, "todavía no empieza")
        r = self.client.post(self.url, {**base, "tipo": "rango", "desde": "2026-09-01", "hasta": "2026-09-10"})
        self.assertEqual(r.status_code, 200)
        _, periodo, consolidado, _ = self._generador().call_args.args
        self.assertEqual((periodo.desde, periodo.hasta, consolidado), (date(2026, 9, 1), date(2026, 9, 10), True))

    def test_alcance_por_sucursal_no_ofrece_consolidado(self):
        self.reporte.alcance = Reporte.Alcance.POR_SUCURSAL
        self.reporte.save()
        self.assertNotContains(self.client.get(self.url), 'value="consolidado"')
        r = self.client.post(self.url, {"sucursales": [self.puebla.pk], "tipo": "mes",
                                        "fecha": "2026-08-01", "modo": "consolidado"})
        self.assertFalse(self._generador().called)
        self.assertEqual(r.status_code, 200)

    def test_sin_permiso_de_generar_es_403_y_sin_boton(self):
        self.gerentes.permissions.clear()
        self.gerente = User.objects.get(pk=self.gerente.pk)  # drop the permission cache
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertNotContains(self.client.get(reverse("reporte_detalle", args=[CLAVE])), "Generar reporte")

    def test_reporte_sin_generador_es_404(self):
        otro = Reporte.objects.create(clave="otro", nombre="Otro", categoria="comercial", periodicidad="semanal",
                                      plantilla="tabular", fuente="odoo", alcance="consolidado")
        otro.perfiles.add(self.gerentes)
        self.assertEqual(self.client.get(reverse("reporte_generar", args=["otro"])).status_code, 404)

    def test_error_de_fuente_se_informa(self):
        self._generador().side_effect = RuntimeError("fuente caida")
        with self.assertLogs("central.views", level="ERROR"):
            r = self.client.post(self.url, {"sucursales": [self.puebla.pk], "tipo": "semana",
                                            "fecha": "2026-09-16", "modo": "por_sucursal"})
        self.assertContains(r, "No se pudo generar el reporte")

    def test_varias_por_sucursal_siempre_pregunta_la_entrega(self):
        self.gerente.perfil.sucursales.add(self.acoxpa)
        base = {"sucursales": [self.puebla.pk, self.acoxpa.pk], "tipo": "semana", "fecha": "2026-09-16",
                "modo": "por_sucursal"}
        r = self.client.post(self.url, base)  # no answer: no default, the question comes back
        self.assertContains(r, "Elige si quieres todo en un PDF o un PDF por sucursal")
        self.assertFalse(self._generador().called)
        self.client.post(self.url, {**base, "entrega": "separados"})
        self.assertTrue(self._generador().call_args.args[3])
        self.client.post(self.url, {**base, "entrega": "un_archivo"})
        self.assertFalse(self._generador().call_args.args[3])
        self.client.post(self.url, {**base, "modo": "consolidado"})  # consolidated: one page, nothing to ask
        self.assertEqual(self._generador().call_args.args[2:], (True, False))


class ZipTests(TestCase):
    def test_zip_con_un_pdf_por_archivo(self):
        import io
        import zipfile

        from .generadores import _zip
        archivo = _zip([("A.pdf", b"%PDF-a"), ("B.pdf", b"%PDF-b")], "Reportes.zip")
        self.assertEqual((archivo.nombre, archivo.tipo), ("Reportes.zip", "application/zip"))
        with zipfile.ZipFile(io.BytesIO(archivo.contenido)) as z:
            self.assertEqual(z.namelist(), ["A.pdf", "B.pdf"])
            self.assertEqual(z.read("B.pdf"), b"%PDF-b")
