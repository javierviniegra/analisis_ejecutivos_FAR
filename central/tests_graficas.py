from datetime import date, timedelta
from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import graficas as g
from .motor.graficas_png import dibujar
from .motor.metricas import Comparacion, Metricas
from .motor.periodo import Periodo, TipoPeriodo


def _diaria(periodo, valor=D("100"), faltan=()):
    dias = [periodo.desde + timedelta(i) for i in range(periodo.dias)]
    return Metricas(periodo=periodo, venta_por_dia={d: valor for d in dias if d not in faltan}, dias_con_cierre=len(dias))


class GranularidadTests(SimpleTestCase):
    def test_cortes(self):
        self.assertEqual(g.granularidad(Periodo.semana(2026, 38)), g.DIA)
        self.assertEqual(g.granularidad(Periodo.bloque(TipoPeriodo.MES, 2026, 8)), g.DIA)  # 31 days
        self.assertEqual(g.granularidad(Periodo.bloque(TipoPeriodo.BIMESTRE, 2026, 4)), g.SEMANA)
        self.assertEqual(g.granularidad(Periodo.bloque(TipoPeriodo.TRIMESTRE, 2026, 3)), g.SEMANA)  # 92 days
        self.assertEqual(g.granularidad(Periodo.bloque(TipoPeriodo.SEMESTRE, 2026, 1)), g.MES)
        self.assertEqual(g.granularidad(Periodo.anio_completo(2026)), g.MES)

    def test_cubetas_semanales_y_mensuales(self):
        bim = Periodo.bloque(TipoPeriodo.BIMESTRE, 2026, 4)  # jul-ago, 62 days
        c = g.cubetas(bim, g.SEMANA)
        self.assertEqual(len(c), 9)
        self.assertEqual(c[0], (date(2026, 7, 1), date(2026, 7, 7)))
        self.assertEqual(c[-1], (date(2026, 8, 26), date(2026, 8, 31)))  # last block is shorter
        rango = Periodo.rango(date(2026, 1, 15), date(2026, 6, 10))
        m = g.cubetas(rango, g.MES)
        self.assertEqual((m[0], m[-1]), ((date(2026, 1, 15), date(2026, 1, 31)), (date(2026, 6, 1), date(2026, 6, 10))))

    def test_etiquetas(self):
        self.assertEqual(g.etiqueta(date(2026, 9, 14), g.DIA, 7, False), "Lun 14")
        self.assertEqual(g.etiqueta(date(2026, 9, 14), g.DIA, 30, False), "14")
        self.assertEqual(g.etiqueta(date(2026, 7, 8), g.SEMANA, 62, False), "8 jul")
        self.assertEqual(g.etiqueta(date(2025, 12, 1), g.MES, 200, True), "dic 25")


class GraficaTests(SimpleTestCase):
    SEM = Periodo.semana(2026, 38)

    def test_por_posicion_y_sin_dato_no_es_cero(self):
        ant = self.SEM.anterior()
        comp = Comparacion(_diaria(self.SEM, faltan={date(2026, 9, 16)}), _diaria(ant, D("80")))
        gr = g.construir_grafica(self.SEM, ant, comp, "la semana anterior", "semana anterior")
        self.assertEqual(gr.titulo, "Venta neta por día vs semana anterior")
        self.assertEqual(gr.etiquetas[0], "Lun 14")
        self.assertIsNone(gr.actual[2])  # Wednesday without closing: no bar, not zero
        self.assertEqual(gr.base, [D("80")] * 7)
        self.assertIsNone(gr.nota)

    def test_base_mas_corta_se_rellena(self):
        ago, jun = Periodo.bloque(TipoPeriodo.MES, 2026, 8), Periodo.bloque(TipoPeriodo.MES, 2026, 6)  # 31 vs 30 days
        gr = g.construir_grafica(ago, jun, Comparacion(_diaria(ago), _diaria(jun)), "x", "x")
        self.assertEqual(len(gr.base), 31)
        self.assertIsNone(gr.base[30])

    def test_notas(self):
        ant = self.SEM.anterior()
        sin = g.construir_grafica(self.SEM, ant, Comparacion(_diaria(self.SEM), None, ["Puebla"]), "la semana anterior", "x")
        self.assertEqual(sin.nota, "Sin comparativo contra la semana anterior.")  # not "comparables (sin Puebla)"
        con = g.construir_grafica(self.SEM, ant, Comparacion(_diaria(self.SEM), _diaria(ant), ["Puebla"]), "x", "x")
        self.assertEqual(con.nota, "Sucursales comparables (sin Puebla).")

    def test_anio_una_sola_grafica(self):
        anio = Periodo.anio_completo(2026)
        self.assertEqual(len(g.construir_graficas(anio, _diaria(anio), _diaria(anio.anterior()), None)), 1)
        dos = g.construir_graficas(self.SEM, _diaria(self.SEM), _diaria(self.SEM.anterior()), None)
        self.assertEqual([x.titulo for x in dos], ["Venta neta por día vs semana anterior",
                                                   "Venta neta por día vs año anterior"])

    def test_dibuja_png(self):
        gr = g.construir_grafica(self.SEM, None, Comparacion(_diaria(self.SEM), None), "x", "x")
        self.assertTrue(dibujar(gr).startswith(b"\x89PNG"))
