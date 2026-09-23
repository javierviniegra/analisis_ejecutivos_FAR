from datetime import datetime, date
from decimal import Decimal

from django.test import SimpleTestCase

from .motor.fuentes import presupuestos as pp
from .motor.fuentes import wansoft as w

CV, GO = "Costo de Ventas", "Gasto Operativo"
TIPOS = {1: CV, 2: CV, 3: GO, 4: GO}


class DiaOperativoTests(SimpleTestCase):
    def test_cierre_antes_de_las_14_pertenece_al_dia_anterior(self):
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 6, 0, 57)), date(2026, 9, 5))
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 8, 12, 51)), date(2026, 9, 7))
        self.assertEqual(w.dia_operativo(datetime(2026, 8, 20, 9, 23)), date(2026, 8, 19))

    def test_cierre_de_la_noche_pertenece_al_mismo_dia(self):
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 7, 23, 29)), date(2026, 9, 7))
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 7, 19, 0)), date(2026, 9, 7))
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 7, 14, 0)), date(2026, 9, 7))


class ResolverCostoVentasTests(SimpleTestCase):
    def test_solo_cuentan_los_tipos_explicitos_de_la_categoria(self):
        por_tipo = {1: Decimal("100"), 3: Decimal("50")}
        self.assertEqual(pp.resolver_costo_ventas_mensual(por_tipo, TIPOS, False), Decimal("100"))

    def test_el_sobrante_se_reparte_entre_tipos_sin_presupuesto_propio(self):
        # 4 tipos, tipo 1 explicito; sobrante 300 -> 3 tipos sin explicito, 100 c/u;
        # de esos, el tipo 2 es Costo de Ventas
        por_tipo = {1: Decimal("1000"), None: Decimal("300")}
        self.assertEqual(pp.resolver_costo_ventas_mensual(por_tipo, TIPOS, False), Decimal("1100.00"))

    def test_sin_clasificar_toma_una_parte_extra_del_sobrante(self):
        # 4 tipos sin explicito + 1 (sin clasificar) = 5 partes de 60
        por_tipo = {None: Decimal("300")}
        self.assertEqual(pp.resolver_costo_ventas_mensual(por_tipo, TIPOS, True), Decimal("120.00"))
        self.assertEqual(pp.resolver_costo_ventas_mensual(por_tipo, TIPOS, False), Decimal("150.00"))

    def test_sin_sobrante_no_agrega_nada(self):
        self.assertEqual(pp.resolver_costo_ventas_mensual({3: Decimal("9")}, TIPOS, True), Decimal("0"))

    def test_meses_del_rango(self):
        self.assertEqual(pp._meses(date(2026, 6, 29), date(2026, 7, 5)), [date(2026, 6, 1), date(2026, 7, 1)])
        self.assertEqual(pp._meses(date(2026, 12, 28), date(2027, 1, 3)), [date(2026, 12, 1), date(2027, 1, 1)])
