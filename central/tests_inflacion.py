"""Inflation addendum of the monthly commercial report (owner, 2026-10-19)."""

from datetime import date
from decimal import Decimal as D
from unittest import mock

from django.test import SimpleTestCase, TestCase

from .models import Inflacion
from .motor import inflacion as inf
from .motor.metricas import Comparacion, Metricas
from .motor.periodo import Periodo, TipoPeriodo

SEP, OCT = Periodo.de_fecha(TipoPeriodo.MES, date(2026, 9, 1)), Periodo.de_fecha(TipoPeriodo.MES, date(2026, 10, 1))
INPC = {date(2025, 9, 1): D("141.197"), date(2026, 9, 1): D("146.075"), date(2025, 10, 1): D("141.708")}


def _m(periodo, venta, clientes, tickets):
    return Metricas(periodo=periodo, venta_bruta=D(venta), clientes=D(clientes), tickets=D(tickets),
                    dias_con_cierre=periodo.dias)


class InflacionTests(SimpleTestCase):
    def test_inflacion_anual(self):
        self.assertAlmostEqual(float(inf.anual(INPC, date(2026, 9, 1))), 0.03455, places=4)  # INEGI: 3.45%
        self.assertIsNone(inf.anual(INPC, date(2026, 10, 1)))  # October 2026 not published

    def test_mes_analizado_es_el_ultimo_publicado(self):
        self.assertEqual(inf.mes_analizado(SEP, INPC), SEP)  # its own month when published
        self.assertEqual(inf.mes_analizado(OCT, INPC), SEP)  # October sent on Nov 1st: September
        self.assertIsNone(inf.mes_analizado(Periodo.semana(2026, 40), INPC))  # monthly only

    def test_solo_periodos_de_un_mes_o_mas(self):
        self.assertIsNone(inf.periodo_analizado(Periodo.rango(date(2026, 9, 1), date(2026, 9, 20)), INPC))

    def test_varios_meses_promedio_y_meses_publicados(self):
        inpc = {date(2025, m, 1): D(100 + m) for m in range(1, 13)}
        inpc.update({date(2026, m, 1): D(104 + m) for m in range(1, 10)})  # up to September 2026
        tri3 = Periodo.bloque(TipoPeriodo.TRIMESTRE, 2026, 3)  # jul-sep: all published
        self.assertEqual(inf.periodo_analizado(tri3, inpc), tri3)
        self.assertEqual(inf.del_periodo(inpc, tri3), D(111 + 112 + 113) / D(107 + 108 + 109) - 1)
        tri4 = Periodo.bloque(TipoPeriodo.TRIMESTRE, 2026, 4)  # oct-dec: none published, no addendum
        self.assertIsNone(inf.periodo_analizado(tri4, inpc))
        bim5 = Periodo.bloque(TipoPeriodo.BIMESTRE, 2026, 5)  # sep-oct: only September
        self.assertEqual(inf.periodo_analizado(bim5, inpc), SEP)
        anio = Periodo.anio_completo(2026)  # Jan-Sep published: a range of whole months
        parcial = inf.periodo_analizado(anio, inpc)
        self.assertEqual((parcial.desde, parcial.hasta), (date(2026, 1, 1), date(2026, 9, 30)))
        a = inf.construir(parcial, Comparacion(_m(parcial, 1, 1, 1), None), D("0.04"), anio)
        self.assertIn("Se analiza enero – septiembre 2026, los meses del periodo con inflación publicada", a.nota)
        self.assertIn("octubre a diciembre 2026", a.nota)

    def test_crecimiento_real_y_lectura(self):
        ly = SEP.mismo_periodo_anio_anterior()
        comp = Comparacion(_m(SEP, 1040, 95, 50), _m(ly, 1000, 100, 50))  # +4% sales, -5% guests
        a = inf.construir(SEP, comp, D("0.04"), OCT)
        venta, ticket, cheque, clientes, _ = a.filas
        self.assertEqual(venta.nominal.porcentaje, D("0.04"))
        self.assertEqual(venta.real.porcentaje, D(0))  # all of it was inflation
        self.assertIsNone(clientes.real)  # volume: no inflation
        self.assertGreater(cheque.real.porcentaje, 0)  # 10.95 vs 10 per guest: +9.5% nominal, beats 4%
        self.assertIn("Se analiza septiembre 2026 y no octubre 2026", a.nota)
        self.assertIn("en términos reales", a.lectura[0])

    def test_sin_anio_anterior(self):
        a = inf.construir(SEP, Comparacion(_m(SEP, 1000, 10, 5), None), D("0.03"), SEP)
        self.assertEqual(a.lectura, ["Sin comparativo de septiembre 2025: no se puede separar el crecimiento de la "
                                     "inflación."])
        self.assertIn("ya está publicada", a.nota)
        self.assertIn("Es la anual porque se compara contra el mismo periodo del año anterior", a.nota)


class SerieTests(TestCase):
    def test_trae_de_banxico_los_meses_que_faltan(self):
        Inflacion.objects.all().delete()
        Inflacion.objects.create(mes=date(2026, 8, 1), inpc=D("145.462"))
        with mock.patch("central.motor.fuentes.banxico.inpc", return_value={date(2026, 9, 1): D("146.075")}) as api:
            serie = inf.serie("token", hoy=date(2026, 10, 20))
        api.assert_called_once()
        self.assertEqual(serie[date(2026, 9, 1)], D("146.075"))
        self.assertTrue(Inflacion.objects.filter(mes=date(2026, 9, 1), fuente="banxico").exists())

    def test_sin_token_o_si_falla_usa_lo_guardado(self):
        Inflacion.objects.all().delete()
        Inflacion.objects.create(mes=date(2026, 8, 1), inpc=D("145.462"))
        self.assertEqual(list(inf.serie("", hoy=date(2026, 10, 20))), [date(2026, 8, 1)])
        with mock.patch("central.motor.fuentes.banxico.inpc", side_effect=OSError("sin red")):
            self.assertEqual(list(inf.serie("token", hoy=date(2026, 10, 20))), [date(2026, 8, 1)])

    def test_precarga_de_la_migracion(self):
        self.assertTrue(Inflacion.objects.filter(mes=date(2026, 9, 1), inpc=D("146.075")).exists())
