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

    def test_correos_extra(self):
        self.assertEqual(self._auto(correos_extra="a@x.com, b@x.com\n\n c@x.com ").correos,
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
