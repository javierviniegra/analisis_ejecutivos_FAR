from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor.lectura import NEGATIVO, POSITIVO, construir_lectura
from .motor.metricas import Metricas, consolidar
from .motor.notas import notas_reglas
from .motor.periodo import Periodo
from .motor.tabla_comercial import construir_tabla

SEM = Periodo.semana(2026, 38)


def _m(neta="10000", costo=None, preliminar=False):
    m = Metricas(periodo=SEM, venta_bruta=D(neta) * D("1.16"), venta_neta=D(neta), dias_con_cierre=7, dias_con_detalle=7,
                 costo_preliminar=preliminar)
    if costo is not None:
        m.costo_ventas_real, m.venta_neta_con_costo = D(costo), D(neta)
    return m


class MetaCostoTests(SimpleTestCase):
    def test_semaforo(self):
        self.assertEqual(c.semaforo_costo(D("0.3799")), c.NARANJA)
        self.assertEqual(c.semaforo_costo(D("0.38")), c.VERDE)
        self.assertEqual(c.semaforo_costo(D("0.3999")), c.VERDE)
        self.assertEqual(c.semaforo_costo(D("0.40")), c.ROJO)
        self.assertIsNone(c.semaforo_costo(None))

    def test_renglon_de_la_tabla(self):
        fila = {f.indicador.clave: f for f in construir_tabla(_m(costo="3850"), None, None)}["costo_ventas_pct"]
        self.assertEqual(fila.indicador.etiqueta, "Costo facturado / venta neta")
        self.assertEqual((fila.actual, fila.semaforo), (D("0.385"), c.VERDE))
        sin = {f.indicador.clave: f for f in construir_tabla(_m(), None, None)}["costo_ventas_pct"]
        self.assertEqual((sin.actual, sin.semaforo), (None, None))  # no cost data: no light

    def test_consolidado_no_diluye(self):
        # a branch without cost data does not dilute the share
        t = consolidar([_m("10000", "4200"), _m("30000")], SEM)
        self.assertEqual(t.pct_costo_ventas, D("0.42"))

    def test_lectura(self):
        textos = {o.texto: o.tono for o in construir_lectura(SEM, _m(costo="3500"), None, None).observaciones}
        frase = next(t for t in textos if t.startswith("El costo facturado"))
        self.assertIn("35.0% de la venta neta: abajo de la meta (38.0-39.9%)", frase)
        self.assertEqual(textos[frase], NEGATIVO)
        verde = next(o for o in construir_lectura(SEM, _m(costo="3900"), None, None).observaciones
                     if o.texto.startswith("El costo facturado"))
        self.assertEqual(verde.tono, POSITIVO)
        prelim = next(o for o in construir_lectura(SEM, _m(costo="4500", preliminar=True), None, None).observaciones
                      if o.texto.startswith("El costo facturado"))
        self.assertIn("arriba de la meta", prelim.texto)
        self.assertIn("cifra preliminar", prelim.texto)

    def test_regla_documentada(self):
        texto = " ".join(notas_reglas())
        self.assertIn("Meta de costo: 38% a 39.9% de la venta neta (verde)", texto)
        self.assertIn("40% o más rojo", texto)
