"""Automations dispatcher: who receives what, one e-mail per person, log and retries."""

from datetime import datetime, time
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from cuentas.models import PerfilUsuario, Sucursal

from . import envios
from .generadores import GrupoArchivos
from .models import Automatizacion, EnvioAutomatico, Reporte

CLAVE = "comercial-semanal-gerentes"
# Tuesday 2026-10-06 09:00: week 40 (28 Sep - 4 Oct) is due for "2 days after, 08:00".
MARTES = datetime(2026, 10, 6, 9, 0)


def _grupos(sucursales, periodo, consolidado, formatos, opciones):
    if consolidado:
        return [GrupoArchivos(None, [("Consolidado.pdf", b"%PDF-c", "application/pdf")])]
    return [GrupoArchivos(s, [(f"{s.nombre}.pdf", b"%PDF-s", "application/pdf")]) for s in sucursales]


@override_settings(CORREO_CONTACTO="")  # independent of the local .env
class EnviosTests(TestCase):
    def setUp(self):
        self.reporte = Reporte.objects.create(
            clave=CLAVE, nombre="Reporte comercial", categoria="sucursales", periodicidad="semanal",
            plantilla="ejecutiva", fuente="mixta", alcance=Reporte.Alcance.AMBOS, admite_pdf=True, admite_excel=True)
        self.puebla = Sucursal.objects.create(clave="puebla", nombre="Puebla", wansoft_subsidiary_id=1,
                                              correos_reporte="gerente.puebla@x.com")
        self.acoxpa = Sucursal.objects.create(clave="acoxpa", nombre="Acoxpa", wansoft_subsidiary_id=2)
        self.gerente = User.objects.create_user("ga", email="gerente.acoxpa@x.com")
        self.acoxpa.destinatarios.add(self.gerente)
        self.director = User.objects.create_user("d", email="director@x.com")
        self.supervisor = User.objects.create_user("s", email="super@x.com")
        PerfilUsuario.objects.create(usuario=self.supervisor).sucursales.add(self.acoxpa)
        self.a = Automatizacion.objects.create(
            reporte=self.reporte, nombre="Semanal", tipo="semana", dias_despues=2, hora=time(8, 0),
            enviar_consolidado=True, enviar_particulares=True, particulares_correos="externo@x.com")
        self.a.consolidado_destinatarios.add(self.director)
        self.a.particulares_destinatarios.add(self.supervisor)
        Automatizacion.objects.filter(pk=self.a.pk).update(creada=timezone.make_aware(datetime(2026, 10, 1)))
        self.a.refresh_from_db()
        patcher = mock.patch.dict("central.envios.GRUPOS", {CLAVE: _grupos})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _adjuntos(self):
        return {m.to[0]: sorted(n for n, _, _ in m.attachments) for m in mail.outbox}

    def test_cada_quien_recibe_lo_suyo_en_un_solo_correo(self):
        (envio,) = envios.despachar(MARTES)
        self.assertEqual(envio.estado, EnvioAutomatico.Estado.ENVIADO)
        self.assertEqual(self._adjuntos(), {
            "director@x.com": ["Consolidado.pdf"],
            "gerente.puebla@x.com": ["Puebla.pdf"],           # the branch's default recipients
            "gerente.acoxpa@x.com": ["Acoxpa.pdf"],
            "super@x.com": ["Acoxpa.pdf"],                     # only the branches of his profile
            "externo@x.com": ["Acoxpa.pdf", "Puebla.pdf"],     # outside e-mails: every branch
        })
        self.assertEqual(mail.outbox[0].subject,
                         "CENTRAL DE REPORTES -RODIVA- Reporte comercial · Semana 40 · 28 sep – 4 oct 2026")
        cuerpo = mail.outbox[0].body
        self.assertTrue(cuerpo.startswith("Este es un correo automático de Grupo Hospitalario Rodiva"))
        self.assertIn("Grupo Hospitalario Rodiva te comparte", cuerpo)
        self.assertTrue(cuerpo.rstrip().endswith(envios.disclaimer()))
        self.assertIn("CGI Inventarios", envios.pie_no_responder())
        self.assertEqual(mail.outbox[0].reply_to, [])  # no contact address configured in tests
        self.assertEqual(mail.outbox[0].extra_headers["Auto-Submitted"], "auto-generated")
        self.assertEqual(envio.desde.isoformat(), "2026-09-28")
        self.assertEqual(envios.despachar(MARTES), [])  # already sent: never twice

    def test_no_manda_antes_de_la_hora_ni_periodos_previos_a_la_automatizacion(self):
        self.assertEqual(envios.pendientes(datetime(2026, 10, 6, 7, 59)), [])  # week 39 predates the automation
        self.a.activa = False
        self.a.save()
        self.assertEqual(envios.pendientes(MARTES), [])

    def test_reintenta_solo_a_quien_fallo(self):
        original = envios._mensaje

        def falla_al_externo(a, periodo, correo, conexion):
            m = original(a, periodo, correo, conexion)
            if correo.para == "externo@x.com":
                m.send = mock.Mock(side_effect=OSError("buzón lleno"))
            return m

        with mock.patch.object(envios, "_mensaje", side_effect=falla_al_externo):
            (envio,) = envios.despachar(MARTES)
        self.assertEqual(envio.estado, EnvioAutomatico.Estado.ERROR)
        self.assertIn("buzón lleno", envio.error)
        self.assertEqual(len(mail.outbox), 4)
        mail.outbox.clear()
        (envio,) = envios.despachar(MARTES)  # next run: only the one that failed
        self.assertEqual([m.to[0] for m in mail.outbox], ["externo@x.com"])
        self.assertEqual((envio.estado, envio.intentos), (EnvioAutomatico.Estado.ENVIADO, 2))
        self.assertEqual(len(envio.destinatarios.splitlines()), 5)

    def test_sin_destinatarios(self):
        self.a.consolidado_destinatarios.clear()
        self.a.particulares_destinatarios.clear()
        self.a.particulares_correos = ""
        self.a.particulares_a_sucursal = False
        self.a.save()
        (envio,) = envios.despachar(MARTES)
        self.assertEqual(envio.estado, EnvioAutomatico.Estado.SIN_DESTINATARIOS)
        self.assertEqual(mail.outbox, [])

    def test_si_no_se_puede_generar_queda_en_error_y_se_reintenta(self):
        with mock.patch.dict("central.envios.GRUPOS", {CLAVE: mock.Mock(side_effect=RuntimeError("fuente caída"))}):
            (envio,) = envios.despachar(MARTES)
        self.assertEqual(envio.estado, EnvioAutomatico.Estado.ERROR)
        self.assertIn("fuente caída", envio.error)
        self.assertEqual(len(envios.pendientes(MARTES)), 1)
