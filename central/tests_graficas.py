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
        self.assertEqual(gr.titulo, "Venta bruta por día vs semana anterior")
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
        self.assertEqual([x.titulo for x in dos], ["Venta bruta por día vs semana anterior",
                                                   "Venta bruta por día vs año anterior"])

    def test_dibuja_png(self):
        gr = g.construir_grafica(self.SEM, None, Comparacion(_diaria(self.SEM), None), "x", "x")
        self.assertTrue(dibujar(gr).startswith(b"\x89PNG"))


def _dias(desde, hasta, valor=D("10"), faltan=()):
    out, d = {}, desde
    while d <= hasta:
        if d not in faltan:
            out[d] = valor
        d += timedelta(1)
    return out


class MesTests(SimpleTestCase):
    """A month: its sales per day alone plus a 12-month calendar trend."""

    AGO = Periodo.bloque(TipoPeriodo.MES, 2026, 8)

    def _diario(self):
        vieja = _dias(date(2024, 9, 1), date(2026, 8, 31))
        for d in list(vieja):  # a source gap: Dec 2024 only has 1 day
            if d.year == 2024 and d.month == 12 and d.day > 1:
                del vieja[d]
        return {"Vieja": vieja, "Nueva": _dias(date(2026, 7, 20), date(2026, 8, 31), D("1"))}

    def test_ventana_de_24_meses(self):
        self.assertEqual(g.meses_tendencia(self.AGO)[0], date(2025, 9, 1))
        self.assertEqual(g.ventana_tendencia(self.AGO), (date(2024, 9, 1), date(2026, 8, 31)))

    def test_tendencia(self):
        gr = g.grafica_tendencia_mensual(self.AGO, self._diario())
        self.assertEqual(gr.titulo, "Venta bruta mensual vs año anterior")
        self.assertEqual((len(gr.etiquetas), gr.etiquetas[-1], gr.resaltar), (12, "ago\n26", 11))
        self.assertEqual(gr.actual[-1], D("341"))  # 31 x 10 + 31 x 1: the new branch is included
        self.assertEqual(gr.base[-1], D("310"))  # Aug 2025: only the old branch existed
        self.assertEqual(gr.actual[-2], D("322"))  # Jul 2026: 31 x 10 + 12 opening days of the new one
        dic = gr.etiquetas.index("dic\n25")
        self.assertIsNone(gr.actual[dic])  # Dec 2024 is a gap: the branch leaves both years of December
        self.assertIsNone(gr.base[dic])
        self.assertIn("Nueva desde jul 26", gr.nota)
        self.assertIn("datos incompletos en Wansoft (en ambos años): dic 25 (1)", gr.nota)

    def test_mes_a_la_fecha(self):
        sep = Periodo.bloque(TipoPeriodo.MES, 2026, 9)
        diario = {"A": {**_dias(date(2025, 9, 1), date(2025, 9, 30)), **_dias(date(2026, 9, 1), date(2026, 9, 23))}}
        gr = g.grafica_tendencia_mensual(sep, diario)
        self.assertEqual((gr.actual[-1], gr.base[-1]), (D("230"), D("230")))  # days 1-23 of both years
        self.assertIn("sep 26 a la fecha: días 1 al 23 de ambos años", gr.nota)

    def test_una_sucursal_con_hueco(self):
        gr = g.grafica_tendencia_mensual(self.AGO, {"Vieja": self._diario()["Vieja"]})
        self.assertIn("Meses sin comparar por datos incompletos en Wansoft: dic 25", gr.nota)

    def test_mes_usa_sus_dos_graficas(self):
        dos = g.construir_graficas(self.AGO, _diaria(self.AGO), None, None, self._diario())
        self.assertEqual([x.titulo for x in dos], ["Venta bruta por día", "Venta bruta mensual vs año anterior"])
        self.assertTrue(all(v is None for v in dos[0].base))  # the day chart is not paired with another month
        with self.assertRaises(ValueError):
            g.construir_graficas(self.AGO, _diaria(self.AGO), None, None)
        for gr in dos:
            self.assertTrue(dibujar(gr).startswith(b"\x89PNG"))
