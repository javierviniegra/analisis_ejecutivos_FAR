"""Automations (Phase 5): which period is sent and when; model rules."""

from datetime import date, datetime, time

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from cuentas.models import puede_automatizar

from .models import Automatizacion, EnvioAutomatico, Reporte
from .motor.periodo import Periodo, TipoPeriodo
from .motor.programacion import fecha_envio, periodo_a_enviar, proximo_envio

OCHO = time(8, 0)


class ProgramacionTests(SimpleTestCase):
    def test_semana_se_manda_el_martes_siguiente(self):
        s40 = Periodo.semana_de(date(2026, 10, 1))
        self.assertEqual(fecha_envio(s40, 2, OCHO), datetime(2026, 10, 6, 8, 0))  # martes
        # martes 6 a las 8:00 ya toca la semana 40; a las 7:59 todavía la 39
        self.assertEqual(periodo_a_enviar(TipoPeriodo.SEMANA, 2, OCHO, datetime(2026, 10, 6, 8, 0)), s40)
        self.assertEqual(periodo_a_enviar(TipoPeriodo.SEMANA, 2, OCHO, datetime(2026, 10, 6, 7, 59)), s40.anterior())

    def test_mes_cinco_dias_despues(self):
        sep = Periodo.de_fecha(TipoPeriodo.MES, date(2026, 9, 1))
        self.assertEqual(periodo_a_enviar(TipoPeriodo.MES, 5, OCHO, datetime(2026, 10, 5, 9)), sep)
        self.assertEqual(periodo_a_enviar(TipoPeriodo.MES, 5, OCHO, datetime(2026, 10, 4, 9)), sep.anterior())

    def test_proximo_envio(self):
        periodo, cuando = proximo_envio(TipoPeriodo.SEMANA, 2, OCHO, datetime(2026, 10, 6, 9))
        self.assertEqual(periodo, Periodo.semana_de(date(2026, 10, 8)))
        self.assertEqual(cuando, datetime(2026, 10, 13, 8, 0))


class AutomatizacionModeloTests(TestCase):
    def setUp(self):
        self.reporte = Reporte.objects.create(
            clave="comercial", nombre="Comercial", categoria="sucursales", periodicidad="semanal",
            plantilla="ejecutiva", fuente="mixta", alcance=Reporte.Alcance.AMBOS, admite_pdf=True, admite_excel=True)

    def _auto(self, **kw):
        return Automatizacion(reporte=self.reporte, nombre="Semanal", **kw)

    def test_valida_lo_que_se_manda_formato_y_dias(self):
        self._auto().full_clean()
        with self.assertRaises(ValidationError):
            self._auto(enviar_particulares=False).full_clean()  # nothing to send
        with self.assertRaises(ValidationError):
            self._auto(dias_despues=8).full_clean()  # a week: up to 7
        self._auto(tipo="mes", dias_despues=10).full_clean()
        self.reporte.admite_excel = False
        with self.assertRaises(ValidationError):
            self._auto(formato="ambos").full_clean()

    def test_respeta_el_alcance_del_reporte(self):
        self.reporte.alcance = Reporte.Alcance.CONSOLIDADO
        with self.assertRaises(ValidationError):
            self._auto().full_clean()  # one per branch not available
        self._auto(enviar_consolidado=True, enviar_particulares=False).full_clean()

    def test_correos(self):
        self.assertEqual(self._auto(consolidado_correos="a@x.com, b@x.com\n\n c@x.com ").correos_consolidado,
                         ["a@x.com", "b@x.com", "c@x.com"])

    def test_un_envio_por_periodo(self):
        a = self._auto()
        a.save()
        datos = dict(automatizacion=a, desde=date(2026, 9, 28), hasta=date(2026, 10, 4),
                     programado_para=datetime(2026, 10, 6, 8), estado="enviado")
        EnvioAutomatico.objects.create(**datos)
        with self.assertRaises(IntegrityError):
            EnvioAutomatico.objects.create(**datos)

    def test_permiso_gestionar_envios(self):
        director = User.objects.create_user("d")
        gerente = User.objects.create_user("g")
        g = Group.objects.create(name="Director")
        g.permissions.add(Permission.objects.get(codename="gestionar_envios"))
        director.groups.add(g)
        self.assertTrue(puede_automatizar(User.objects.get(pk=director.pk)))
        self.assertFalse(puede_automatizar(gerente))


from django.urls import reverse  # noqa: E402

from cuentas.models import Sucursal  # noqa: E402

from .tests import PLAIN_STATIC  # noqa: E402


@PLAIN_STATIC
class AutomatizacionWebTests(TestCase):
    CLAVE = "comercial-semanal-gerentes"

    def setUp(self):
        self.reporte = Reporte.objects.create(
            clave=self.CLAVE, nombre="Comercial", categoria="sucursales", periodicidad="semanal",
            plantilla="ejecutiva", fuente="mixta", alcance=Reporte.Alcance.AMBOS, admite_pdf=True, admite_excel=True)
        self.director = User.objects.create_user("d", email="d@x.com")
        g = Group.objects.create(name="Director")
        g.permissions.add(*Permission.objects.filter(codename__in=["generar_reportes", "gestionar_envios"]))
        self.director.groups.add(g)
        self.reporte.perfiles.add(g)
        self.gerente = User.objects.create_user("g")
        gg = Group.objects.create(name="Gerente")
        gg.permissions.add(Permission.objects.get(codename="generar_reportes"))
        self.gerente.groups.add(gg)
        self.reporte.perfiles.add(gg)
        self.puebla = Sucursal.objects.create(clave="puebla", nombre="Puebla", wansoft_subsidiary_id=1)
        self.nueva = reverse("automatizacion_nueva", args=[self.CLAVE])

    def _datos(self, **kw):
        datos = {"nombre": "Semanal gerentes", "activa": "on", "tipo": "semana", "dias_despues": 2, "hora": "08:00",
                 "todas_las_sucursales": "on", "enviar_particulares": "on", "formato": "pdf",
                 "particulares_a_sucursal": "on", "particulares_solo_sus_sucursales": "on", "incluir_costos": "on"}
        datos.update(kw)
        return {k: v for k, v in datos.items() if v is not None}

    def test_director_crea_ve_y_pausa(self):
        self.client.force_login(self.director)
        r = self.client.post(self.nueva, self._datos(incluir_costos=None, enviar_consolidado="on",
                                                     consolidado_destinatarios=[self.director.pk]))
        self.assertEqual(r.status_code, 302)
        a = Automatizacion.objects.get()
        self.assertEqual((a.creada_por, a.opciones, a.enviar_consolidado), (self.director, {"incluir_costos": False}, True))
        r = self.client.get(reverse("reporte_detalle", args=[self.CLAVE]))
        self.assertContains(r, "Semanal gerentes")
        self.assertContains(r, "sin costos")
        self.assertContains(r, "Sin destinatarios: Puebla")  # Puebla has no default recipients yet
        self.client.post(reverse("automatizacion_pausar", args=[self.CLAVE, a.pk]))
        a.refresh_from_db()
        self.assertFalse(a.activa)

    def test_sin_sucursales_ni_todas_es_error(self):
        self.client.force_login(self.director)
        r = self.client.post(self.nueva, self._datos(todas_las_sucursales=None))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Automatizacion.objects.exists())
        r = self.client.post(self.nueva, self._datos(todas_las_sucursales=None, sucursales=[self.puebla.pk]))
        self.assertEqual(r.status_code, 302)

    def test_gerente_no_ve_ni_crea(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("reporte_detalle", args=[self.CLAVE]))
        self.assertNotContains(r, "Automatizaciones")
        self.assertEqual(self.client.get(self.nueva).status_code, 403)
        self.assertEqual(self.client.post(self.nueva, self._datos()).status_code, 403)

    def test_consolidado_y_particulares_necesitan_destinatarios(self):
        self.client.force_login(self.director)
        # consolidated without anyone
        r = self.client.post(self.nueva, self._datos(enviar_consolidado="on"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Elige a quién se manda el consolidado.")
        # per branch with neither the branches' recipients nor people
        r = self.client.post(self.nueva, self._datos(particulares_a_sucursal=None))
        self.assertContains(r, "Elige a quién se mandan los reportes por sucursal")
        r = self.client.post(self.nueva, self._datos(particulares_a_sucursal=None, particulares_correos="sup@x.com"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Automatizacion.objects.get().correos_particulares, ["sup@x.com"])

    def test_destinatarios_por_defecto_de_la_sucursal(self):
        self.assertFalse(self.puebla.tiene_destinatarios)
        self.puebla.correos_reporte = "gerente.puebla@x.com"
        self.assertEqual(self.puebla.correos, ["gerente.puebla@x.com"])
        self.assertTrue(self.puebla.tiene_destinatarios)

    def test_automatizar_un_correo_enviado(self):
        from .models import EnvioManual
        envio = EnvioManual.objects.create(
            usuario=self.director, reporte=self.reporte, periodo="Semana 40", desde=date(2026, 9, 28),
            hasta=date(2026, 10, 4), destinatarios="d@x.com\nexterno@y.com",
            parametros={"tipo": "mes", "sucursales": [self.puebla.pk], "modo": "por_sucursal", "formato": "pdf",
                        "opciones": {"incluir_costos": False}, "usuarios": [self.director.pk],
                        "correos": ["externo@y.com"]})
        self.client.force_login(self.director)
        r = self.client.get(self.nueva + f"?desde_envio={envio.pk}")
        self.assertContains(r, "A partir del correo enviado")
        inicial = r.context["form"].initial
        self.assertEqual((inicial["tipo"], inicial["sucursales"], inicial["particulares_destinatarios"],
                          inicial["particulares_correos"], inicial["incluir_costos"], inicial["particulares_a_sucursal"]),
                         ("mes", [self.puebla.pk], [self.director.pk], "externo@y.com", False, False))
