from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor.lectura import NEGATIVO, POSITIVO, construir_lectura
from .motor.metricas import Metricas, consolidar
from .motor.notas import notas_reglas
from .motor.periodo import Periodo, TipoPeriodo
from .motor.tabla_comercial import construir_tabla

SEM = Periodo.semana(2026, 38)


def _m(neta="10000", costo=None, preliminar=False):
    m = Metricas(periodo=SEM, venta_bruta=D(neta) * D("1.16"), venta_neta=D(neta), dias_con_cierre=7, dias_con_detalle=7,
                 costo_preliminar=preliminar)
    if costo is not None:
        m.costo_ventas_real, m.venta_neta_con_costo = D(costo), D(neta)
    return m


class MetaCostoTests(SimpleTestCase):
    @staticmethod
    def _con_total():
        m = _m(costo="3850")
        m.costo_total, m.venta_neta_con_costo_total = D("3520"), D("10000")
        return m

    def test_semaforo(self):
        self.assertEqual(c.semaforo_costo(D("0.3799")), c.NARANJA)
        self.assertEqual(c.semaforo_costo(D("0.38")), c.VERDE)
        self.assertEqual(c.semaforo_costo(D("0.3999")), c.VERDE)
        self.assertEqual(c.semaforo_costo(D("0.40")), c.ROJO)
        self.assertIsNone(c.semaforo_costo(None))

    def test_renglon_de_la_tabla(self):
        fila = {f.indicador.clave: f for f in construir_tabla(_m(costo="3850"), None, None)}["costo_ventas_pct"]
        self.assertEqual(fila.indicador.etiqueta, "Costo facturado / venta neta")
        total = {f.indicador.clave: f for f in construir_tabla(self._con_total(), None, None)}["costo_total_pct"]
        self.assertEqual((total.indicador.etiqueta, total.actual, total.semaforo),
                         ("Costo total / venta neta", D("0.352"), c.NARANJA))
        self.assertEqual((fila.actual, fila.semaforo), (D("0.385"), c.VERDE))
        sin = {f.indicador.clave: f for f in construir_tabla(_m(), None, None)}["costo_ventas_pct"]
        self.assertEqual((sin.actual, sin.semaforo), (None, None))  # no cost data: no light

    def test_consolidado_no_diluye(self):
        # a branch without cost data does not dilute the share
        t = consolidar([_m("10000", "4200"), _m("30000")], SEM)
        self.assertEqual(t.pct_costo_ventas, D("0.42"))

    def test_lectura(self):
        def frase(m):
            return next((o for o in construir_lectura(SEM, m, None, None).observaciones
                         if o.texto.startswith("Costo sobre la venta neta")), None)
        naranja = frase(_m(costo="3500"))
        self.assertEqual(naranja.texto, "Costo sobre la venta neta (meta 38.0-39.9%): facturado 35.0%, abajo de la meta.")
        self.assertEqual(naranja.tono, NEGATIVO)
        self.assertEqual(frase(_m(costo="3900")).tono, POSITIVO)
        prelim = frase(_m(costo="4500", preliminar=True))
        self.assertIn("facturado 45.0%, arriba de la meta (preliminar, pueden faltar facturas)", prelim.texto)
        ambos = _m(costo="3900")
        ambos.costo_total, ambos.venta_neta_con_costo_total = D("3520"), D("10000")
        f = frase(ambos)
        self.assertIn("total 35.2%, abajo de la meta; facturado 39.0%, dentro de la meta", f.texto)
        self.assertEqual(f.tono, NEGATIVO)  # not every cost is on target
        self.assertIsNone(frase(_m()))  # no cost data: no sentence

    def test_regla_documentada(self):
        texto = " ".join(notas_reglas())
        self.assertIn("Meta de costo: 38% a 39.9% de la venta neta (verde)", texto)
        self.assertIn("40% o más rojo", texto)


class CostoTotalTests(SimpleTestCase):
    """How the total cost is taken per period kind (queries mocked)."""

    def test_por_tipo_de_periodo(self):
        from datetime import date
        from unittest import mock

        from .motor import metricas
        semana = mock.patch("central.motor.fuentes.wansoft.costo_total_semana", return_value={1: D("100"), 2: D("0")})
        mes = mock.patch("central.motor.fuentes.wansoft.costo_total_mes", return_value={1: D("50")})
        with semana as s, mes as m:
            self.assertEqual(metricas.costos_totales(None, [1, 2], SEM), {1: D("100")})  # 0 = no data, dropped
            s.assert_called_once_with(None, [1, 2], SEM.desde)
            trimestre = Periodo.bloque(TipoPeriodo.TRIMESTRE, 2026, 3)
            self.assertEqual(metricas.costos_totales(None, [1], trimestre), {1: D("150")})  # sum of 3 months
            self.assertEqual(m.call_count, 3)
            self.assertIsNone(metricas.costos_totales(None, [1], Periodo.rango(date(2026, 9, 1), date(2026, 9, 10))))
