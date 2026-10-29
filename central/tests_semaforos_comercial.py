"""Scorecard traffic lights on the commercial report's indicators table (owner, 2026-10-29)."""

from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor.lectura import NEGATIVO, construir_lectura
from .motor.metricas import Comparacion, Metricas
from .motor.notas import leyenda_semaforos, notas_reglas
from .motor.periodo import Periodo
from .motor.tabla_comercial import META_ANIO, META_ANTERIOR, construir_tabla

SEM = Periodo.semana(2026, 38)
ANT = Periodo.semana(2026, 37)
LY = Periodo.semana(2025, 38)


def _m(periodo=SEM, clientes="100", venta="10000", dias=7, mix=None):
    m = Metricas(periodo=periodo, venta_bruta=D(venta), venta_neta=D(venta) / D("1.16"), tickets=D("50"),
                 clientes=D(clientes), dias_con_cierre=dias, dias_con_detalle=dias)
    if mix:
        m.mix = {"Alimentos": D(mix[0]), "Bebidas": D(mix[1])}
    return m


def _fila(actual, anterior, anio, clave):
    return {f.indicador.clave: f for f in construir_tabla(actual, anterior, anio)}[clave]


class SemaforosHistoricosTests(SimpleTestCase):
    def test_contra_anio_anterior_mas_5(self):
        # target = 100 x 1.05 = 105 guests
        for clientes, color in (("105", c.VERDE), ("95", c.NARANJA), ("94", c.ROJO)):
            f = _fila(_m(clientes=clientes), None, _m(LY), "clientes")
            self.assertEqual((f.semaforo, f.meta_contra), (color, META_ANIO), clientes)
        f = _fila(_m(clientes="105"), None, _m(LY), "clientes")
        self.assertEqual(f.logro, D("1"))

    def test_sin_anio_anterior_usa_el_periodo_anterior(self):
        f = _fila(_m(clientes="100"), _m(ANT, clientes="100"), None, "clientes")
        self.assertEqual((f.semaforo, f.meta_contra), (c.NARANJA, META_ANTERIOR))  # 100 / 105 = 95.2%

    def test_sin_comparativo_fiable_no_hay_color(self):
        # last year exists but with closings on 3 of 7 days: no target, and no fallback
        f = _fila(_m(), _m(ANT), _m(LY, dias=3), "clientes")
        self.assertEqual((f.semaforo, f.logro), (None, None))
        self.assertIsNone(_fila(_m(), None, None, "clientes").semaforo)  # nothing to compare

    def test_solo_sucursales_comparables(self):
        # the whole selection has 200 guests, but only the comparable branch (100) is set against its target
        comparables = Comparacion(_m(clientes="100"), _m(LY, clientes="100"), ["Nueva"])
        f = _fila(_m(clientes="200"), None, comparables, "clientes")
        self.assertEqual((f.actual, f.semaforo, f.logro), (D("200"), c.NARANJA, D("100") / D("105")))

    def test_venta_cheque_y_ticket(self):
        filas = {f.indicador.clave: f for f in construir_tabla(_m(venta="10500"), None, _m(LY))}
        self.assertEqual(filas["venta_bruta"].semaforo, c.VERDE)
        self.assertEqual(filas["cheque_promedio"].semaforo, c.VERDE)  # 105 vs 100 x 1.05
        self.assertEqual(filas["ticket_promedio"].semaforo, c.VERDE)
        self.assertIsNone(filas["venta_neta"].semaforo)  # one light for sales: the gross row
        self.assertIsNone(filas["tickets"].semaforo)


class SemaforoMixTests(SimpleTestCase):
    def test_umbral_fijo(self):
        for bebidas, color in (("30", c.VERDE), ("27", c.NARANJA), ("25", c.ROJO)):
            f = _fila(_m(mix=(str(100 - int(bebidas)), bebidas)), None, None, "mix_bebidas")
            self.assertEqual(f.semaforo, color, bebidas)
        self.assertIsNone(_fila(_m(), None, None, "mix_bebidas").semaforo)  # no ticket detail: no light


class LecturaYNotasTests(SimpleTestCase):
    def test_frase_de_rojos(self):
        lectura = construir_lectura(SEM, _m(clientes="90", mix=("75", "25")), None, _m(LY))
        rojo = next(o for o in lectura.observaciones if o.texto.startswith("En rojo"))
        self.assertEqual(rojo.texto, "En rojo contra la meta: clientes 85.7% de la meta (año anterior +5%); "
                                     "mix de bebidas 25.0% (meta 30%).")
        self.assertEqual(rojo.tono, NEGATIVO)
        verde = construir_lectura(SEM, _m(clientes="105", venta="10500", mix=("70", "30")), None, _m(LY))
        self.assertFalse([o for o in verde.observaciones if o.texto.startswith("En rojo")])

    def test_leyenda(self):
        lineas = leyenda_semaforos()
        self.assertEqual(lineas[2], "Costo / venta neta: verde de 37% a menos de 39%, naranja abajo de 37% (se compró "
                                    "o se registró de menos), rojo 39% o más.")
        self.assertIn("Verde desde el 100% de la meta, naranja desde el 90%, rojo abajo del 90%.", lineas[0])
        self.assertFalse([t for t in leyenda_semaforos(incluir_costos=False) if t.startswith("Costo")])

    def test_banda(self):
        from .motor.semaforos import banda
        self.assertEqual([banda(D(v), D("0.37"), D("0.39")) for v in ("0.3699", "0.37", "0.3899", "0.39")],
                         [c.NARANJA, c.VERDE, c.VERDE, c.ROJO])
        self.assertIsNone(banda(None, D("0.37"), D("0.39")))

    def test_reglas(self):
        texto = " ".join(notas_reglas(incluir_costos=False))
        self.assertIn("meta = mismo periodo del año anterior +5%; sin año anterior, el periodo inmediato anterior +5%",
                      texto)
        self.assertIn("Verde desde el 100% de la meta, naranja desde el 90%, rojo abajo.", texto)
        self.assertIn("verde desde 30%, naranja desde 26%, rojo abajo.", texto)
