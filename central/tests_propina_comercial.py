"""Tip share in the commercial report (owner, 2026-10-29)."""

from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor.metricas import Metricas, consolidar
from .motor.notas import notas_reglas
from .motor.periodo import Periodo
from .motor.tabla_comercial import construir_tabla

SEM = Periodo.semana(2026, 38)
LY = Periodo.semana(2025, 38)


def _m(periodo=SEM, salon="10000", propina="800"):
    return Metricas(periodo=periodo, venta_bruta=D("12000"), venta_neta=D("10345"), dias_con_cierre=7,
                    dias_con_detalle=7, venta_salon=D(salon), meseros=4, propina_salon=D(propina))


class PropinaTests(SimpleTestCase):
    def test_porcentaje_sobre_venta_de_salon(self):
        self.assertEqual(_m().pct_propina, D("0.08"))
        self.assertIsNone(_m(salon="0").pct_propina)  # no dining-room sales: no share

    def test_consolidado_suma_propinas_y_venta(self):
        t = consolidar([_m(salon="10000", propina="800"), _m(salon="30000", propina="3000")], SEM)
        self.assertEqual(t.pct_propina, D("0.095"))

    def test_renglon_en_puntos(self):
        f = {x.indicador.clave: x for x in construir_tabla(_m(), None, _m(LY, propina="600"))}["propina_pct"]
        self.assertEqual((f.indicador.seccion, f.actual, f.anio_anterior), ("Productividad", D("0.08"), D("0.06")))
        self.assertEqual((f.var_anio.porcentaje, f.var_anio.color), (D("0.02"), c.VERDE))  # +2 points
        self.assertIsNone(f.semaforo)

    def test_regla_documentada(self):
        self.assertIn("Propina: la registrada en los pagos de las cuentas de salón", " ".join(notas_reglas()))
