"""Tip share in the commercial report (owner, 2026-10-29; over card payments since 2026-11-17)."""

from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor.metricas import Metricas, consolidar
from .motor.notas import notas_reglas
from .motor.periodo import Periodo
from .motor.tabla_comercial import construir_tabla

SEM = Periodo.semana(2026, 38)
LY = Periodo.semana(2025, 38)


def _m(periodo=SEM, tarjeta="10000", propina="800"):
    return Metricas(periodo=periodo, venta_bruta=D("12000"), venta_neta=D("10345"), dias_con_cierre=7,
                    dias_con_detalle=7, venta_salon=D("12500"), meseros=4, propina_salon=D(propina),
                    tarjeta_salon=D(tarjeta))


class PropinaTests(SimpleTestCase):
    def test_porcentaje_sobre_pago_con_tarjeta(self):
        self.assertEqual(_m().pct_propina, D("0.08"))
        self.assertIsNone(_m(tarjeta="0").pct_propina)  # nothing paid by card: no share

    def test_consolidado_suma_propinas_y_venta(self):
        t = consolidar([_m(tarjeta="10000", propina="800"), _m(tarjeta="30000", propina="3000")], SEM)
        self.assertEqual(t.pct_propina, D("0.095"))

    def test_renglon_en_puntos(self):
        f = {x.indicador.clave: x for x in construir_tabla(_m(), None, _m(LY, propina="600"))}["propina_pct"]
        self.assertEqual((f.indicador.seccion, f.actual, f.anio_anterior), ("Productividad", D("0.08"), D("0.06")))
        self.assertEqual((f.var_anio.porcentaje, f.var_anio.color), (D("0.02"), c.VERDE))  # +2 points
        self.assertIsNone(f.semaforo)

    def test_regla_documentada(self):
        self.assertIn("Propina: la de los pagos con tarjeta (crédito, débito, Amex y CLIP)", " ".join(notas_reglas()))
