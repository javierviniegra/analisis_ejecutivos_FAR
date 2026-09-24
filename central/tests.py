from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Reporte

# The production static storage (WhiteNoise manifest) needs `collectstatic`;
# tests render pages that use {% static %}, so they use the plain storage.
PLAIN_STATIC = override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)


def _reporte(clave, **kw):
    datos = dict(
        clave=clave, nombre=clave, categoria="comercial", periodicidad="semanal",
        plantilla="tabular", fuente="odoo", alcance="consolidado",
    )
    datos.update(kw)
    return Reporte.objects.create(**datos)


@PLAIN_STATIC
class VisibilidadTests(TestCase):
    def setUp(self):
        self.gerentes = Group.objects.create(name="Gerente")
        self.otros = Group.objects.create(name="Otros")
        self.gerente = User.objects.create_user("g", password="x")
        self.gerente.groups.add(self.gerentes)
        self.staff = User.objects.create_user("s", password="x", is_staff=True)
        self.visible = _reporte("visible")
        self.visible.perfiles.add(self.gerentes)
        self.sin_perfiles = _reporte("sin-perfiles")
        self.de_otros = _reporte("de-otros")
        self.de_otros.perfiles.add(self.otros)
        self.inactivo = _reporte("inactivo", activo=False)
        self.inactivo.perfiles.add(self.gerentes)

    def test_usuario_solo_ve_los_de_su_perfil_y_activos(self):
        claves = set(Reporte.visibles_para(self.gerente).values_list("clave", flat=True))
        self.assertEqual(claves, {"visible"})

    def test_reporte_sin_perfiles_no_lo_ve_nadie_salvo_staff(self):
        self.assertNotIn(self.sin_perfiles, Reporte.visibles_para(self.gerente))
        self.assertIn(self.sin_perfiles, Reporte.visibles_para(self.staff))

    def test_staff_ve_todos_los_activos_pero_no_los_inactivos(self):
        claves = set(Reporte.visibles_para(self.staff).values_list("clave", flat=True))
        self.assertEqual(claves, {"visible", "sin-perfiles", "de-otros"})

    def test_detalle_de_reporte_ajeno_es_404(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("reporte_detalle", args=["de-otros"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("reporte_detalle", args=["visible"])).status_code, 200)

    def test_catalogo_requiere_login(self):
        resp = self.client.get(reverse("catalogo"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])


class CargarCatalogoTests(TestCase):
    def test_es_idempotente_y_no_pisa_ediciones(self):
        call_command("cargar_catalogo", stdout=StringIO())
        total = Reporte.objects.count()
        self.assertGreaterEqual(total, 7)
        r = Reporte.objects.get(clave="indicadores-operativos-semanal")
        r.notas = "editado en admin"
        r.save()
        call_command("cargar_catalogo", stdout=StringIO())
        self.assertEqual(Reporte.objects.count(), total)
        r.refresh_from_db()
        self.assertEqual(r.notas, "editado en admin")

    def test_reportes_nuevos_nacen_sin_perfiles(self):
        call_command("cargar_catalogo", stdout=StringIO())
        self.assertFalse(Reporte.objects.filter(perfiles__isnull=False).exists())
