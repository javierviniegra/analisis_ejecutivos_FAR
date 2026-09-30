from datetime import date
from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor.fuentes import presupuestos
from .motor.metricas import Metricas, consolidar
from .motor.notas import notas_cobertura, notas_reglas
from .motor.periodo import Periodo
from .motor.tabla_comercial import construir_tabla

SEM39 = Periodo.semana(2026, 39)  # 21-27 Sep 2026


def _m(periodo=SEM39, preliminar=False, real="16775"):
    return Metricas(periodo=periodo, venta_bruta=D("1000"), dias_con_cierre=periodo.dias,
                    dias_con_detalle=periodo.dias, costo_ventas_real=D(real), costo_preliminar=preliminar)


class CostoPreliminarTests(SimpleTestCase):
    def test_definitivo_diez_dias_despues_del_cierre_del_mes(self):
        self.assertEqual(presupuestos.DIAS_CIERRE_MES, 10)
        self.assertEqual(presupuestos.fecha_definitiva(date(2026, 9, 27)), date(2026, 10, 11))
        self.assertTrue(presupuestos.es_preliminar(date(2026, 9, 27), date(2026, 10, 10)))
        self.assertFalse(presupuestos.es_preliminar(date(2026, 9, 27), date(2026, 10, 11)))
        # a week ending in October belongs to October's close
        self.assertEqual(presupuestos.fecha_definitiva(date(2026, 10, 4)), date(2026, 11, 11))

    def test_tabla_scf_si_cualquier_lado_es_preliminar(self):
        ant = SEM39.anterior()
        filas = {f.indicador.clave: f for f in construir_tabla(_m(preliminar=True), _m(ant, real="233522"), None)}
        real = filas["costo_ventas_real"]
        self.assertEqual(real.actual, D("16775"))  # the value is still shown
        self.assertEqual(real.var_anterior.direccion, c.NO_FIABLE)  # no misleading -92.8%
        self.assertEqual(filas["venta_bruta"].var_anterior.direccion, c.IGUAL)  # sales are not affected
        filas = {f.indicador.clave: f for f in construir_tabla(_m(), _m(ant, preliminar=True, real="233522"), None)}
        self.assertEqual(filas["costo_ventas_real"].var_anterior.direccion, c.NO_FIABLE)
        filas = {f.indicador.clave: f for f in construir_tabla(_m(real="200"), _m(ant, real="100"), None)}
        self.assertEqual(filas["costo_ventas_real"].var_anterior.direccion, c.SUBE)  # both final: compared

    def test_consolidado_hereda(self):
        self.assertTrue(consolidar([_m(), _m(preliminar=True)], SEM39).costo_preliminar)

    def test_notas(self):
        notas = notas_cobertura(SEM39, _m(preliminar=True), _m(SEM39.anterior()), None)
        self.assertIn("será definitivo a partir del 11/10/2026", " ".join(notas))
        notas = notas_cobertura(SEM39, _m(), _m(SEM39.anterior(), preliminar=True), None)
        self.assertIn("Costo de Ventas real de la semana anterior aún preliminar", " ".join(notas))
        self.assertIn("10 días después del cierre del mes", " ".join(notas_reglas()))
        sin_facturas = Metricas(periodo=SEM39, dias_con_cierre=7, dias_con_detalle=7, costo_ventas_ppto=D("114315"),
                                n_con_presupuesto=1, costo_preliminar=True)  # La Esquina Coyoacán, week 39
        self.assertIn("aún no hay facturas registradas del periodo", " ".join(notas_cobertura(SEM39, sin_facturas, None, None)))
