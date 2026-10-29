from datetime import date
from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import scorecard as sc
from .motor import semaforos as s
from .motor.comparativos import NARANJA, ROJO, VERDE


class SemaforosTests(SimpleTestCase):
    def test_umbral_mayor_es_mejor_bordes_incluidos(self):
        f = lambda v: s.umbral(v, D("0.30"), D("0.26"), mayor_mejor=True)
        self.assertEqual(f(D("0.30")), VERDE)
        self.assertEqual(f(D("0.2999")), NARANJA)
        self.assertEqual(f(D("0.26")), NARANJA)
        self.assertEqual(f(D("0.2599")), ROJO)

    def test_umbral_menor_es_mejor_como_el_costo_de_power_bi(self):
        # green <= 37%, orange < 39%, red >= 39%
        f = lambda v: s.umbral(v, D("0.37"), D("0.39"), mayor_mejor=False)
        self.assertEqual(f(D("0.37")), VERDE)
        self.assertEqual(f(D("0.3701")), NARANJA)
        self.assertEqual(f(D("0.3899")), NARANJA)
        self.assertEqual(f(D("0.39")), ROJO)

    def test_porcentaje_meta(self):
        self.assertEqual(s.porcentaje_meta(105, 105), VERDE)
        self.assertEqual(s.porcentaje_meta(90, 100), NARANJA)
        self.assertEqual(s.porcentaje_meta(D("89.99"), 100), ROJO)

    def test_cero_y_signo(self):
        self.assertEqual(s.cero_es_verde(0), VERDE)
        self.assertEqual(s.cero_es_verde(D("0.001")), ROJO)
        self.assertEqual(s.signo(D("0.2")), VERDE)
        self.assertEqual(s.signo(0), NARANJA)
        self.assertEqual(s.signo(-1), ROJO)

    def test_contra_meta_con_tolerancia_de_5_por_ciento(self):
        self.assertEqual(s.contra_meta(100, 100, mayor_mejor=True), VERDE)
        self.assertEqual(s.contra_meta(95, 100, mayor_mejor=True), NARANJA)
        self.assertEqual(s.contra_meta(D("94.9"), 100, mayor_mejor=True), ROJO)
        self.assertEqual(s.contra_meta(100, 100, mayor_mejor=False), VERDE)
        self.assertEqual(s.contra_meta(105, 100, mayor_mejor=False), NARANJA)
        self.assertEqual(s.contra_meta(D("105.1"), 100, mayor_mejor=False), ROJO)

    def test_sin_dato_no_lleva_luz_nunca_se_toma_como_cero(self):
        self.assertIsNone(s.umbral(None, D("0.3"), D("0.26"), mayor_mejor=True))
        self.assertIsNone(s.cero_es_verde(None))
        self.assertIsNone(s.signo(None))
        self.assertIsNone(s.porcentaje_meta(100, None))
        self.assertIsNone(s.porcentaje_meta(100, 0))
        self.assertIsNone(s.contra_meta(100, None, mayor_mejor=True))
        self.assertIsNone(s.contra_meta(100, 0, mayor_mejor=False))


class ScorecardTests(SimpleTestCase):
    def test_catalogo_como_power_bi(self):
        self.assertEqual(len(sc.KPIS), 24)  # 25 rows minus the Talento Humano placeholder
        self.assertEqual(len(sc.POR_CLAVE), len(sc.KPIS))
        por_categoria = {c: [k.orden for k in sc.KPIS if k.categoria == c] for c in sc.CATEGORIAS}
        self.assertEqual([len(v) for v in por_categoria.values()], [10, 5, 9])
        for ordenes in por_categoria.values():
            self.assertEqual(ordenes, sorted(ordenes))

    def test_cada_kpi_tiene_lo_que_su_regla_necesita(self):
        for k in sc.KPIS:
            if k.regla == sc.REGLA_UMBRAL:
                self.assertIsNotNone(k.verde, k.clave)
                self.assertIsNotNone(k.naranja, k.clave)
            if k.tipo_meta == sc.META_FIJA:
                self.assertIsNotNone(k.meta, k.clave)

    def test_meta_desde_base(self):
        self.assertEqual(sc.meta_desde_base(D("100")), D("105.00"))
        self.assertIsNone(sc.meta_desde_base(None))
        self.assertIsNone(sc.meta_desde_base(D("0")))

    def test_estado_por_kpi(self):
        k = sc.POR_CLAVE
        self.assertEqual(sc.estado(k["costo_venta"], D("0.38"), k["costo_venta"].meta), NARANJA)
        self.assertEqual(sc.estado(k["ventas"], D("95"), D("105")), NARANJA)
        self.assertEqual(sc.estado(k["clientes"], D("90"), D("105")), ROJO)
        self.assertEqual(sc.estado(k["hielo"], D("1040"), D("1000")), NARANJA)
        self.assertEqual(sc.estado(k["auditoria_cgi"], D("0.84"), None), NARANJA)
        self.assertEqual(sc.estado(k["incumplimiento_procesos"], 0, 0), VERDE)
        self.assertEqual(sc.estado(k["nps"], 0, 0), NARANJA)
        self.assertEqual(sc.estado(k["diferencia_inventario"], D("0.02"), k["diferencia_inventario"].meta), ROJO)
        self.assertIsNone(sc.estado(k["google"], None, k["google"].meta))


class PeriodosScorecardTests(SimpleTestCase):
    def test_mes_en_curso_hasta_el_domingo(self):
        p = sc.periodos(date(2026, 11, 8))
        self.assertEqual((p.actual.desde, p.actual.hasta), (date(2026, 11, 1), date(2026, 11, 8)))
        # the same days of the previous month (owner, 2026-10-29), not the whole of it
        self.assertEqual((p.mes_anterior.desde, p.mes_anterior.hasta), (date(2026, 10, 1), date(2026, 10, 8)))
        self.assertEqual((p.anio_anterior.desde, p.anio_anterior.hasta), (date(2025, 11, 1), date(2025, 11, 8)))
        self.assertFalse(p.mes_cerrado)

    def test_primer_lunes_del_mes_manda_el_mes_anterior_cerrado(self):
        # Monday 2 Nov 2026: the month to date would be Sunday the 1st only
        p = sc.periodos(date(2026, 11, 1))
        self.assertTrue(p.mes_cerrado)
        self.assertEqual((p.actual.desde, p.actual.hasta), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual((p.mes_anterior.desde, p.mes_anterior.hasta), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual((p.anio_anterior.desde, p.anio_anterior.hasta), (date(2025, 10, 1), date(2025, 10, 31)))
        self.assertTrue(sc.periodos(date(2026, 11, 6)).mes_cerrado)
        self.assertFalse(sc.periodos(date(2026, 11, 7)).mes_cerrado)

    def test_ultimo_dia_del_mes_es_el_mes_completo(self):
        p = sc.periodos(date(2026, 10, 31))
        self.assertFalse(p.mes_cerrado)
        self.assertEqual((p.mes_anterior.desde, p.mes_anterior.hasta), (date(2026, 9, 1), date(2026, 9, 30)))

    def test_mes_anterior_mas_corto_se_toma_completo(self):
        p = sc.periodos(date(2027, 3, 30))
        self.assertEqual((p.mes_anterior.desde, p.mes_anterior.hasta), (date(2027, 2, 1), date(2027, 2, 28)))


def _v(venta, dias=30, esperados=30, tickets=10, personas=40, restaurante=30, alimentos=75, bebidas=25):
    return sc.Ventas(dias, esperados, D(venta), D(tickets), D(personas), D(restaurante), D(alimentos), D(bebidas))


class VentasScorecardTests(SimpleTestCase):
    def test_valores(self):
        v = _v(1000)
        self.assertEqual(v.valor("ventas"), D("1000"))
        self.assertEqual(v.valor("cheque"), D("25"))  # every channel's guests
        self.assertEqual(v.valor("ticket"), D("100"))
        self.assertEqual(v.valor("clientes"), D("30"))  # restaurant orders only
        self.assertEqual(v.valor("mix_bebidas"), D("0.25"))
        self.assertIsNone(sc.Ventas(dias_esperados=30).valor("ventas"))

    def test_base_ano_anterior_y_respaldo_mes_anterior(self):
        anio, mes = _v(100), _v(80)
        self.assertEqual(sc.elegir_base(anio, mes), (anio, sc.ANIO_ANTERIOR))
        # last year with data on less than 90% of its days is not reliable
        self.assertEqual(sc.elegir_base(_v(100, dias=26), mes), (mes, sc.MES_ANTERIOR))
        self.assertEqual(sc.elegir_base(_v(0), mes), (mes, sc.MES_ANTERIOR))
        self.assertEqual(sc.elegir_base(_v(100, dias=0), _v(80, dias=0)), (None, None))

    def test_filas_de_una_sucursal(self):
        b = sc.filas_ventas(["A"], [_v(1000)], [_v(900)], [_v(1000)])
        f = {r.kpi.clave: r for r in b.filas}
        self.assertEqual(f["ventas"].meta, D("1050.00"))
        self.assertEqual(f["ventas"].estado, NARANJA)  # 1000 / 1050 = 95.2%
        self.assertEqual(f["ventas"].mes_anterior, D("900"))
        self.assertEqual(f["mix_bebidas"].estado, ROJO)  # 25% < 26%
        self.assertEqual((b.meta_mes_anterior, b.sin_meta), ([], []))

    def test_consolidado_deja_fuera_a_la_sucursal_sin_base(self):
        # B is new: no last year and no previous month -> out of the target and of the actual compared
        b = sc.filas_ventas(["A", "B"], [_v(1000), _v(500)], [_v(900), _v(0, dias=0)],
                            [_v(1000), _v(0, dias=0)])
        f = {r.kpi.clave: r for r in b.filas}["ventas"]
        self.assertEqual(f.actual, D("1500"))
        self.assertEqual(f.actual_comparado, D("1000"))
        self.assertEqual(f.meta, D("1050.00"))
        self.assertEqual(b.sin_meta, ["B"])

    def test_consolidado_suma_la_base_de_cada_sucursal(self):
        # C has no reliable last year: its base is its previous month
        b = sc.filas_ventas(["A", "C"], [_v(1000), _v(400)], [_v(900), _v(300)],
                            [_v(1000), _v(100, dias=10)])
        f = {r.kpi.clave: r for r in b.filas}["ventas"]
        self.assertEqual(f.meta, D("1365.00"))  # (1000 + 300) x 1.05
        self.assertEqual(f.estado, VERDE)  # 1400 >= 1365
        self.assertEqual(b.meta_mes_anterior, ["C"])


class PdfScorecardTests(SimpleTestCase):
    def _reporte(self, hasta=date(2026, 10, 25), consolidado=False):
        from types import SimpleNamespace
        from .motor.reporte_scorecard import ReporteScorecard
        b = sc.filas_ventas(["A"], [_v(1000)], [_v(900)], [_v(1000)])
        leidas = {f.kpi.clave: f for f in b.filas}
        filas = [leidas.get(k.clave) or sc.Fila(k, None, None, k.meta, None, None) for k in sc.KPIS]
        sucursales = [SimpleNamespace(nombre="Acoxpa"), SimpleNamespace(nombre="Puebla")]
        return ReporteScorecard("Consolidado" if consolidado else "Acoxpa", sucursales, sc.periodos(hasta), filas,
                                ["Puebla"] if consolidado else [], [])

    def test_genera_dos_paginas_por_reporte(self):
        from .salidas import pdf_scorecard
        pdf = pdf_scorecard.generar([self._reporte(), self._reporte(date(2026, 11, 1), consolidado=True)])
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page\r"), 4)  # scorecard + rules each

    def test_texto_de_las_reglas_sale_de_las_constantes(self):
        k = sc.POR_CLAVE
        self.assertEqual(sc.regla_texto(k["costo_venta"]), "Verde <= 37%, naranja menor a 39%, rojo 39% o más.")
        self.assertEqual(sc.regla_texto(k["mix_bebidas"]), "Verde >= 30%, naranja >= 26%, rojo debajo.")
        self.assertIn("1.5%", sc.regla_texto(k["diferencia_inventario"]))
        self.assertIn("+5%", sc.regla_texto(k["ventas"]))
        self.assertIn("mismos días del mes anterior", sc.regla_texto(k["hielo"]))
