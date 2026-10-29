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

    def test_meta_historica(self):
        self.assertEqual(sc.meta_historica(D("100"), D("80")), D("105.00"))
        # no last year (new branch): previous month +5%
        self.assertEqual(sc.meta_historica(None, D("80")), D("84.00"))
        self.assertEqual(sc.meta_historica(D("0"), D("80")), D("84.00"))
        self.assertIsNone(sc.meta_historica(None, None))

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
