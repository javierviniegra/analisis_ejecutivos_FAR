"""Sales composition and waiters' productivity of the commercial report (owner, 2026-10-20)."""

from datetime import date
from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import composicion as k
from .motor.metricas import Comparacion, Metricas, consolidar
from .motor.periodo import Periodo, TipoPeriodo

SEM = Periodo.semana(2026, 42)
LY = SEM.mismo_periodo_anio_anterior()


def _m(periodo, horas=None, pagos=None, salon=0, meseros=0, dias=0):
    return Metricas(periodo=periodo, por_hora={h: {"venta": D(v), "tickets": D(1), "clientes": D(2)}
                                               for h, v in (horas or {}).items()},
                    pagos={a: D(b) for a, b in (pagos or {}).items()}, venta_salon=D(salon), meseros=meseros,
                    dias_mesero=D(dias), dias_con_cierre=periodo.dias, dias_con_detalle=periodo.dias)


class ComposicionTests(SimpleTestCase):
    def test_franjas_por_hora_de_cierre(self):
        actual = _m(SEM, {11: 100, 14: 300, 19: 500, 0: 100})  # 00:xx closes belong to the night
        c = k.construir(actual, Comparacion(actual, _m(LY, {11: 50, 14: 300, 19: 600})), "Año anterior")
        manana, tarde, noche = c.franjas
        self.assertEqual((manana.venta, tarde.venta, noche.venta), (D(100), D(300), D(600)))
        self.assertEqual(noche.pct, D("0.6"))
        self.assertEqual(manana.var_anio.direccion, "sube")
        self.assertEqual(noche.var_anio.direccion, "igual")  # 600 vs 600

    def test_formas_de_pago_agrupadas_y_plataformas(self):
        actual = _m(SEM, {14: 1}, {"Tarjeta de crédito": 500, "Efectivo": 300, "Dolares": 10, "Uber Eats": 80,
                                   "Ubereats": 20, "Rappi": 40, "Total Play": 5})
        c = k.construir(actual, Comparacion(actual, None), "Año anterior")
        pagos = {n: v for n, v, _ in dict((t, r) for t, r in c.pasteles)["Forma de pago"]}
        self.assertEqual(pagos["Efectivo"], D(310))  # dollars are cash
        self.assertEqual(pagos["Plataformas"], D(140))
        self.assertEqual(pagos["Otros"], D(5))
        plataformas = dict((t, r) for t, r in c.pasteles)["Plataformas"]
        self.assertEqual([(n, v) for n, v, _ in plataformas], [("Uber Eats", D(100)), ("Rappi", D(40))])

    def test_el_color_sigue_a_la_categoria(self):
        rebanadas = k._rebanadas({"Amex": D(900), "Efectivo": D(10)}, k.ORDEN_PAGOS)
        self.assertEqual([(n, slot) for n, _, slot in rebanadas], [("Efectivo", 2), ("Amex", 3)])  # order, not size

    def test_mas_de_cinco_rebanadas_se_juntan_en_otros(self):
        valores = {n: D(i + 1) for i, n in enumerate(k.ORDEN_PAGOS)}  # 6 categories
        rebanadas = k._rebanadas(valores, k.ORDEN_PAGOS)
        self.assertEqual(len(rebanadas), 5)
        self.assertEqual(rebanadas[-1][0], "Otros")
        self.assertEqual(sum(v for _, v, _ in rebanadas), sum(valores.values()))


class TardesTests(SimpleTestCase):
    def test_ranking_por_proporcion_de_la_tarde(self):
        a = _m(SEM, {14: 600, 19: 400})  # 60% afternoon
        b = _m(SEM, {14: 900, 19: 2100})  # 30% afternoon, more sales
        b_ant, b_anio = _m(SEM.anterior(), {14: 400, 19: 600}), _m(LY, {14: 300, 19: 700})
        filas = k.tardes([("A", a, None), ("B", b, b_anio)], [None, b_ant])
        self.assertEqual([f.sucursal for f in filas], ["A", "B"])  # by share, not by amount
        self.assertEqual(filas[0].pct_tarde, D("0.6"))
        self.assertEqual(filas[1].var_anterior.direccion, "baja")  # 40% -> 30%
        self.assertEqual(filas[1].var_anio.direccion, "igual")  # 30% -> 30%
        self.assertIsNone(filas[0].pct_tarde_anio)  # no data last year: s/c


class DiasTests(SimpleTestCase):
    def test_dia_promedio_por_franja_contra_anterior_y_anio(self):
        from datetime import date as d
        mes = Periodo.de_fecha(TipoPeriodo.MES, d(2026, 9, 1))
        actual = Metricas(periodo=mes, venta_dia_hora={d(2026, 9, 5): {14: D(1000), 20: D(1000)},  # two Saturdays
                                                        d(2026, 9, 12): {14: D(2000), 20: D(0)}})
        anterior = Metricas(periodo=mes.anterior(), venta_dia_hora={d(2026, 8, 1): {14: D(1000)}})
        filas = k.dias_horario(actual, anterior, None)
        sab = filas[0]
        self.assertEqual((sab.dia, sab.dias), ("Sábado", 2))
        self.assertEqual(sab.bandas, [D(0), D(1500), D(500)])  # average day
        self.assertEqual(sab.pct_tarde, D("0.75"))
        self.assertEqual(sab.var_anterior.direccion, "sube")  # 2,000 vs 1,000
        self.assertEqual(sab.var_anio.direccion, "sin_dato")


class ProductividadTests(SimpleTestCase):
    def test_venta_por_mesero_y_por_dia_trabajado(self):
        a = _m(SEM, salon=100000, meseros=4, dias=20)
        b = _m(SEM, salon=50000, meseros=1, dias=5)
        self.assertEqual(a.venta_por_mesero, D(25000))
        self.assertEqual(a.venta_por_mesero_dia, D(5000))
        t = consolidar([a, b], SEM)
        self.assertEqual((t.meseros, t.venta_salon, t.dias_mesero), (5, D(150000), D(25)))
        self.assertEqual(t.venta_por_mesero_dia, D(6000))
