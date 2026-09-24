from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor import periodos as p


class PeriodosTests(SimpleTestCase):
    def test_semana_es_lunes_a_domingo(self):
        # 2026-09-23 is a Wednesday
        self.assertEqual(p.semana_lunes_domingo(date(2026, 9, 23)), (date(2026, 9, 21), date(2026, 9, 27)))
        # a Sunday belongs to the week that ENDS on it, a Monday starts a new one
        self.assertEqual(p.semana_lunes_domingo(date(2026, 9, 27))[0], date(2026, 9, 21))
        self.assertEqual(p.semana_lunes_domingo(date(2026, 9, 28))[0], date(2026, 9, 28))

    def test_semana_anterior(self):
        self.assertEqual(p.semana_anterior(date(2026, 9, 21)), (date(2026, 9, 14), date(2026, 9, 20)))

    def test_misma_semana_del_anio_anterior_por_numero_iso(self):
        self.assertEqual(p.numero_semana(date(2026, 9, 21)), (2026, 39))
        self.assertEqual(p.misma_semana_anio_anterior(date(2026, 9, 21)), (date(2025, 9, 22), date(2025, 9, 28)))

    def test_semana_53_sin_equivalente_devuelve_none(self):
        # 2026 has an ISO week 53 (Dec 28 2026 - Jan 3 2027); 2025 does not.
        self.assertEqual(p.numero_semana(date(2026, 12, 28)), (2026, 53))
        self.assertIsNone(p.misma_semana_anio_anterior(date(2026, 12, 28)))

    def test_semana_que_cruza_de_anio_usa_el_anio_iso(self):
        # Dec 29 2025 is ISO week 1 of 2026 -> same week of ISO 2025
        self.assertEqual(p.numero_semana(date(2025, 12, 29)), (2026, 1))
        self.assertEqual(p.misma_semana_anio_anterior(date(2025, 12, 29)), (date(2024, 12, 30), date(2025, 1, 5)))

    def test_prorrateo_dentro_de_un_mes(self):
        # September has 30 days: a full 7-day week is 7/30 of the month
        monto = p.prorratear_mensual({(2026, 9): Decimal("3000000")}, date(2026, 9, 21), date(2026, 9, 27))
        self.assertEqual(monto, Decimal("700000"))

    def test_prorrateo_semana_que_cruza_dos_meses(self):
        # Mon Jun 29 - Sun Jul 5 2026: 2 days of June (30d) + 5 days of July (31d)
        meses = {(2026, 6): Decimal("3000000"), (2026, 7): Decimal("3100000")}
        monto = p.prorratear_mensual(meses, date(2026, 6, 29), date(2026, 7, 5))
        self.assertEqual(monto, Decimal("2") * Decimal("3000000") / 30 + Decimal("5") * Decimal("3100000") / 31)

    def test_hay_meta_exige_todos_los_meses(self):
        meses = {(2026, 6): Decimal("1")}
        self.assertTrue(p.hay_meta(meses, date(2026, 6, 1), date(2026, 6, 30)))
        self.assertFalse(p.hay_meta(meses, date(2026, 6, 29), date(2026, 7, 5)))


class ComparativosTests(SimpleTestCase):
    def test_sube_es_verde_si_mas_es_mejor(self):
        v = c.variacion(105, 100)
        self.assertEqual((v.direccion, v.color, v.simbolo), (c.SUBE, c.VERDE, "▲"))
        self.assertEqual(v.porcentaje, Decimal("0.05"))

    def test_baja_es_roja_si_mas_es_mejor(self):
        v = c.variacion(90, 100)
        self.assertEqual((v.direccion, v.color, v.simbolo), (c.BAJA, c.ROJO, "▼"))

    def test_metricas_donde_subir_es_malo_se_invierten(self):
        self.assertEqual(c.variacion(120, 100, mejor_si_sube=False).color, c.ROJO)
        self.assertEqual(c.variacion(80, 100, mejor_si_sube=False).color, c.VERDE)

    def test_umbral_de_igual_es_mas_menos_1_por_ciento_inclusivo(self):
        self.assertEqual(c.variacion(101, 100).direccion, c.IGUAL)
        self.assertEqual(c.variacion(99, 100).direccion, c.IGUAL)
        self.assertEqual(c.variacion(Decimal("101.01"), 100).direccion, c.SUBE)
        self.assertEqual(c.variacion(100, 100).color, c.GRIS)

    def test_sin_base_o_base_cero_no_inventa_variacion(self):
        for base in (None, 0):
            v = c.variacion(50, base)
            self.assertEqual((v.direccion, v.porcentaje, v.color, v.simbolo), (c.SIN_DATO, None, c.GRIS, "s/c"))
        self.assertEqual(c.variacion(None, 100).direccion, c.SIN_DATO)

    def test_porcentaje_de_meta(self):
        self.assertEqual(c.porcentaje_de_meta(96, 100), Decimal("0.96"))
        self.assertIsNone(c.porcentaje_de_meta(96, None))
        self.assertIsNone(c.porcentaje_de_meta(96, 0))
