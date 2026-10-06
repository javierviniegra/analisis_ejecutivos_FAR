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
        clave=clave, nombre=clave, categoria="marca", periodicidad="semanal",
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

    def test_filtro_por_categoria(self):
        cedis = Group.objects.create(name="CEDIS")
        self.gerente.groups.add(cedis)
        _reporte("oc-cedis", categoria="cedis").perfiles.add(cedis)
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("catalogo"))
        self.assertEqual([c for c, _ in r.context["categorias"]], ["cedis", "marca"])  # only what the user sees
        r = self.client.get(reverse("catalogo"), {"categoria": "cedis"})
        self.assertEqual([x.clave for x in r.context["reportes"]], ["oc-cedis"])
        r = self.client.get(reverse("catalogo"), {"categoria": "nomina"})  # not the user's: ignored
        self.assertEqual(r.context["elegida"], None)
        self.assertEqual(len(r.context["reportes"]), 2)

    def test_sin_filtro_con_una_sola_categoria(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("catalogo")).context["categorias"], [])

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
        from central.management.commands.cargar_catalogo import CATALOGO
        con_perfil = {d["clave"] for d in CATALOGO if d.get("perfiles_iniciales")}
        self.assertFalse(Reporte.objects.exclude(clave__in=con_perfil).filter(perfiles__isnull=False).exists())

    def test_reportes_de_cedis_solo_para_cedis(self):
        call_command("crear_perfiles", stdout=StringIO())
        call_command("cargar_catalogo", stdout=StringIO())
        cedis = User.objects.create_user("c", password="x")
        cedis.groups.add(Group.objects.get(name="CEDIS"))
        self.assertEqual(set(Reporte.visibles_para(cedis).values_list("clave", flat=True)),
                         {"oc-bodegon-empanadas-modificaciones", "oc-bodegon-empanadas-por-hora"})
        self.assertEqual(set(Reporte.visibles_para(cedis).values_list("categoria", flat=True)), {"cedis"})
        gerente = User.objects.create_user("g2", password="x")
        gerente.groups.add(Group.objects.get(name="Gerente"))
        self.assertEqual(set(Reporte.visibles_para(gerente).values_list("clave", flat=True)),
                         {"comercial-semanal-gerentes", "indicadores-operativos-semanal"})
        self.assertEqual(set(Reporte.visibles_para(gerente).values_list("categoria", flat=True)), {"sucursales"})

    def test_reporte_de_nomina_solo_para_noministas(self):
        call_command("crear_perfiles", stdout=StringIO())
        call_command("cargar_catalogo", stdout=StringIO())
        nomina = Reporte.objects.get(clave="incidencias-nomina")
        self.assertEqual(list(nomina.perfiles.values_list("name", flat=True)), ["Nominista"])
        nominista = User.objects.create_user("n", password="x")
        nominista.groups.add(Group.objects.get(name="Nominista"))
        director = User.objects.create_user("d", password="x")
        director.groups.add(Group.objects.get(name="Director"))
        self.assertEqual(list(Reporte.visibles_para(nominista).values_list("clave", flat=True)), ["incidencias-nomina"])
        self.assertNotIn(nomina, Reporte.visibles_para(director))  # not even the Director, unless assigned
        self.assertTrue(nominista.has_perm("cuentas.generar_reportes"))

    def test_perfil_inicial_solo_al_crear(self):
        call_command("crear_perfiles", stdout=StringIO())
        call_command("cargar_catalogo", stdout=StringIO())
        nomina = Reporte.objects.get(clave="incidencias-nomina")
        nomina.perfiles.clear()  # the admin removes it
        call_command("cargar_catalogo", stdout=StringIO())
        self.assertFalse(nomina.perfiles.exists())  # a re-run never re-assigns


@PLAIN_STATIC
class AyudaTests(TestCase):
    def test_ayuda_pide_sesion_y_usa_los_umbrales_del_motor(self):
        from django.contrib.auth.models import User
        self.assertEqual(self.client.get("/ayuda/").status_code, 302)  # login first
        self.client.force_login(User.objects.create_user("u"))
        r = self.client.get("/ayuda/")
        self.assertContains(r, "Ayuda")
        self.assertContains(r, "menos del 90% de sus días")  # comparativos.UMBRAL_COBERTURA_FIABLE
        self.assertContains(r, "al menos el 99.5%")  # metricas.UMBRAL_FACTURADO_COMPLETO
        self.assertContains(r, "antes de las 14:00")  # wansoft.HORA_CORTE_DIA
        self.assertNotContains(r, "Director y Administrador general)</a>")
