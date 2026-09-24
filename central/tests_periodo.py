from datetime import date

from django.test import SimpleTestCase

from .motor.periodo import Periodo, TipoPeriodo as T


class PeriodoTests(SimpleTestCase):
    def test_semana_de_una_fecha_y_por_numero(self):
        self.assertEqual(Periodo.semana_de(date(2026, 9, 23)), Periodo.semana(2026, 39))
        self.assertEqual(Periodo.semana(2026, 39).desde, date(2026, 9, 21))
        with self.assertRaises(ValueError):
            Periodo.semana(2025, 53)  # 2025 has no week 53

    def test_bloques_calendario(self):
        feb = Periodo.bloque(T.MES, 2026, 2)
        self.assertEqual((feb.desde, feb.hasta), (date(2026, 2, 1), date(2026, 2, 28)))
        bim = Periodo.bloque(T.BIMESTRE, 2026, 3)
        self.assertEqual((bim.desde, bim.hasta), (date(2026, 5, 1), date(2026, 6, 30)))
        sem = Periodo.bloque(T.SEMESTRE, 2026, 2)
        self.assertEqual((sem.desde, sem.hasta), (date(2026, 7, 1), date(2026, 12, 31)))
        dic = Periodo.bloque(T.MES, 2026, 12)
        self.assertEqual(dic.hasta, date(2026, 12, 31))
        with self.assertRaises(ValueError):
            Periodo.bloque(T.SEMESTRE, 2026, 3)

    def test_de_fecha_devuelve_el_periodo_que_la_contiene(self):
        f = date(2026, 9, 24)
        self.assertEqual(Periodo.de_fecha(T.MES, f), Periodo.bloque(T.MES, 2026, 9))
        self.assertEqual(Periodo.de_fecha(T.BIMESTRE, f).desde, date(2026, 9, 1))
        self.assertEqual(Periodo.de_fecha(T.TRIMESTRE, f).desde, date(2026, 7, 1))
        self.assertEqual(Periodo.de_fecha(T.SEMESTRE, f).desde, date(2026, 7, 1))
        self.assertEqual(Periodo.de_fecha(T.SEMANA, f), Periodo.semana(2026, 39))
        with self.assertRaises(ValueError):
            Periodo.de_fecha(T.RANGO, f)

    def test_anterior_de_cada_tipo(self):
        self.assertEqual(Periodo.semana(2026, 39).anterior(), Periodo.semana(2026, 38))
        self.assertEqual(Periodo.bloque(T.MES, 2026, 1).anterior(), Periodo.bloque(T.MES, 2025, 12))
        self.assertEqual(Periodo.bloque(T.BIMESTRE, 2026, 1).anterior(), Periodo.bloque(T.BIMESTRE, 2025, 6))
        self.assertEqual(Periodo.bloque(T.SEMESTRE, 2026, 2).anterior(), Periodo.bloque(T.SEMESTRE, 2026, 1))
        self.assertEqual(Periodo.anio_completo(2026).anterior(), Periodo.anio_completo(2025))

    def test_anterior_de_un_rango_es_igual_de_largo_y_termina_el_dia_previo(self):
        r = Periodo.rango(date(2026, 9, 10), date(2026, 9, 20))  # 11 days
        a = r.anterior()
        self.assertEqual((a.desde, a.hasta), (date(2026, 8, 30), date(2026, 9, 9)))
        self.assertEqual(a.dias, r.dias)

    def test_mismo_periodo_anio_anterior(self):
        self.assertEqual(Periodo.semana(2026, 39).mismo_periodo_anio_anterior(), Periodo.semana(2025, 39))
        self.assertIsNone(Periodo.semana(2026, 53).mismo_periodo_anio_anterior())
        self.assertEqual(Periodo.bloque(T.MES, 2026, 9).mismo_periodo_anio_anterior(), Periodo.bloque(T.MES, 2025, 9))
        self.assertEqual(Periodo.bloque(T.BIMESTRE, 2026, 4).mismo_periodo_anio_anterior(), Periodo.bloque(T.BIMESTRE, 2025, 4))
        r = Periodo.rango(date(2026, 2, 27), date(2026, 3, 3)).mismo_periodo_anio_anterior()
        self.assertEqual((r.desde, r.hasta), (date(2025, 2, 27), date(2025, 3, 3)))

    def test_rango_con_29_de_febrero_se_ajusta(self):
        r = Periodo.rango(date(2024, 2, 29), date(2024, 3, 5)).mismo_periodo_anio_anterior()
        self.assertEqual((r.desde, r.hasta), (date(2023, 2, 28), date(2023, 3, 5)))

    def test_rango_invalido(self):
        with self.assertRaises(ValueError):
            Periodo.rango(date(2026, 9, 2), date(2026, 9, 1))

    def test_etiquetas(self):
        self.assertEqual(Periodo.semana(2026, 39).etiqueta(), "Semana 39 · 21 sep – 27 sep 2026")
        self.assertEqual(Periodo.bloque(T.MES, 2026, 9).etiqueta(), "Septiembre 2026")
        self.assertEqual(Periodo.bloque(T.BIMESTRE, 2026, 3).etiqueta(), "Bimestre 3 · may–jun 2026")
        self.assertEqual(Periodo.anio_completo(2026).etiqueta(), "Año 2026")
        self.assertEqual(Periodo.rango(date(2026, 9, 1), date(2026, 9, 15)).etiqueta(), "1 sep – 15 sep 2026")
