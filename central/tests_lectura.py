from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor.lectura import AVISO, NEGATIVO, NEUTRO, POSITIVO, construir_lectura, titulo
from .motor.notas import notas_cobertura, notas_pie, notas_reglas
from .motor.metricas import Metricas, comparables, consolidar
from .motor.periodo import Periodo, TipoPeriodo
from .motor.tabla_comercial import construir_tabla

SEM = Periodo.semana(2026, 39)


def _m(periodo=SEM, **kw):
    base = dict(periodo=periodo, venta_bruta=D("11600"), venta_neta=D("10000"), tickets=D("100"), clientes=D("250"),
                dias_con_cierre=periodo.dias, dias_con_detalle=periodo.dias,
                canal={"salon": D("900"), "llevar": D("100")}, mix={"Alimentos": D("750"), "Bebidas": D("250")})
    base.update(kw)
    return Metricas(**base)


def _textos(lectura):
    return [o.texto for o in lectura.observaciones]


class TituloTests(SimpleTestCase):
    def test_titulo_segun_tipo(self):
        self.assertEqual(titulo(SEM), "Lectura de la semana")
        self.assertEqual(titulo(Periodo.de_fecha(TipoPeriodo.MES, SEM.desde)), "Lectura del mes")
        self.assertEqual(titulo(Periodo.anio_completo(2026)), "Lectura del año")
        self.assertEqual(titulo(Periodo.rango(SEM.desde, SEM.hasta)), "Lectura del periodo")


class LecturaTests(SimpleTestCase):
    def test_sin_cambios_solo_la_venta(self):
        lec = construir_lectura(SEM, _m(), _m(), _m())
        self.assertEqual(len(lec.observaciones), 1)
        o = lec.observaciones[0]
        self.assertEqual(o.tono, NEUTRO)
        self.assertIn("La venta neta fue de $10,000", o.texto)
        self.assertIn("vs la semana anterior", o.texto)
        self.assertIn("vs la misma semana del año anterior", o.texto)

    def test_venta_sube_por_trafico(self):
        actual = _m(venta_bruta=D("12760"), venta_neta=D("11000"), clientes=D("300"))  # +20% guests, check -8.3%
        lec = construir_lectura(SEM, actual, _m(), None)
        venta, causa = lec.observaciones[0], lec.observaciones[1]
        self.assertEqual(venta.tono, POSITIVO)
        self.assertIn("▲ +10.0% (+$1,000)", venta.texto)
        self.assertIn("sin comparativo contra la misma semana del año anterior", venta.texto)
        self.assertIn("sobre todo del tráfico", causa.texto)

    def test_venta_baja_por_cheque(self):
        actual = _m(venta_bruta=D("10440"), venta_neta=D("9000"))  # same guests, check -10%
        lec = construir_lectura(SEM, actual, _m(), _m())
        self.assertEqual(lec.observaciones[0].tono, NEGATIVO)
        self.assertIn("-$1,000", lec.observaciones[0].texto)
        self.assertIn("sobre todo del cheque promedio", lec.observaciones[1].texto)

    def test_controles_solo_si_suben_y_pesan(self):
        actual = _m(cancelaciones=D("80"), cortesias=D("30"), descuentos=D("20"))
        anterior = _m(cancelaciones=D("40"), cortesias=D("10"), descuentos=D("30"))
        texto = " ".join(_textos(construir_lectura(SEM, actual, anterior, None)))
        self.assertIn("Cancelaciones $80", texto)  # up and 0.8% of net sales
        self.assertNotIn("Cortesías", texto)  # up but only 0.3% of net sales
        self.assertNotIn("Descuentos", texto)  # went down

    def test_mezcla_mas_de_dos_puntos(self):
        actual = _m(canal={"salon": D("850"), "llevar": D("100"), "plataformas": D("50")})  # salon -5 pp
        lec = construir_lectura(SEM, actual, _m(), None)
        mezcla = next(o for o in lec.observaciones if o.texto.startswith("Cambio en la mezcla"))
        self.assertEqual(mezcla.tono, NEUTRO)
        self.assertIn("Salón 85.0%", mezcla.texto)
        self.assertNotIn("Alimentos", mezcla.texto)  # food mix did not move

    def test_costo_ventas_sobre_presupuesto(self):
        actual = _m(costo_ventas_real=D("1200"), costo_ventas_ppto=D("1000"), costo_ventas_real_con_ppto=D("1200"),
                    n_con_presupuesto=1)
        texto = " ".join(_textos(construir_lectura(SEM, actual, _m(), None)))
        self.assertIn("120.0% ejercido", texto)
        dentro = _m(costo_ventas_real=D("900"), costo_ventas_ppto=D("1000"), costo_ventas_real_con_ppto=D("900"),
                    n_con_presupuesto=1)
        self.assertNotIn("ejercido", " ".join(_textos(construir_lectura(SEM, dentro, _m(), None))))

    def test_sin_cierres_solo_aviso(self):
        lec = construir_lectura(SEM, Metricas(periodo=SEM), _m(), None)
        self.assertEqual(len(lec.observaciones), 1)
        self.assertEqual(lec.observaciones[0].tono, AVISO)
        self.assertIn("No hay cierres", lec.observaciones[0].texto)

    def test_comparativo_no_fiable(self):
        anterior = _m(periodo=SEM.anterior(), venta_neta=D("1000"), dias_con_cierre=6)  # 6/7 = 86% < 90%
        lec = construir_lectura(SEM, _m(), anterior, _m())
        self.assertIn("sin comparativo fiable contra la semana anterior", lec.observaciones[0].texto)
        self.assertNotIn("%", lec.observaciones[0].texto.split(" y ")[0])  # no misleading percentage
        self.assertEqual(len(lec.observaciones), 1)  # no "causa" on an unreliable comparison

    def test_anio_no_repite_la_comparacion(self):
        anio, previo = Periodo.anio_completo(2026), Periodo.anio_completo(2025)
        lec = construir_lectura(anio, _m(anio), _m(previo), _m(previo))
        self.assertIn("vs el año anterior", lec.observaciones[0].texto)
        self.assertNotIn("del año anterior", lec.observaciones[0].texto)


class ReglaFiableTests(SimpleTestCase):
    def test_umbral_90(self):
        self.assertTrue(c.cobertura_fiable(9, 10))
        self.assertFalse(c.cobertura_fiable(8, 10))
        self.assertFalse(c.cobertura_fiable(0, 0))

    def test_tabla_marca_scf_y_conserva_valores(self):
        anterior = _m(periodo=SEM.anterior(), dias_con_cierre=6, dias_con_detalle=7)
        filas = {f.indicador.clave: f for f in construir_tabla(_m(), anterior, None)}
        venta = filas["venta_neta"]
        self.assertEqual(venta.var_anterior.direccion, c.NO_FIABLE)
        self.assertEqual(venta.var_anterior.simbolo, "s/cf")
        self.assertEqual(venta.anterior, D("10000"))  # the value is still shown
        self.assertEqual(filas["mix_alimentos"].var_anterior.direccion, c.IGUAL)  # detail is complete
        self.assertEqual(venta.var_anio.direccion, c.SIN_DATO)  # no data at all stays s/c

    def test_periodo_actual_parcial_tambien_es_scf(self):
        filas = {f.indicador.clave: f for f in construir_tabla(_m(dias_con_cierre=3), _m(), _m())}
        self.assertEqual(filas["venta_neta"].var_anterior.direccion, c.NO_FIABLE)
        self.assertEqual(filas["venta_neta"].var_anio.direccion, c.NO_FIABLE)

    def test_presupuesto_exento(self):
        actual = _m(dias_con_cierre=3, costo_ventas_real=D("100"))
        filas = {f.indicador.clave: f for f in construir_tabla(actual, _m(costo_ventas_real=D("50")), None)}
        self.assertEqual(filas["costo_ventas_real"].var_anterior.direccion, c.SUBE)


class NotasTests(SimpleTestCase):
    def test_notas_de_cobertura(self):
        actual = _m(dias_con_cierre=5, dias_con_detalle=3)
        anterior = _m(periodo=SEM.anterior(), dias_con_cierre=4)
        notas = notas_cobertura(SEM, actual, anterior, None)
        self.assertIn("El periodo tiene cierres de caja en 5 de 7 días: sus comparativos son s/cf.", notas)
        self.assertTrue(any("detalle de tickets cubre 3 de 7 días" in n for n in notas))
        self.assertIn("s/cf contra la semana anterior: tiene cierres de caja en 4 de 7 días.", notas)

    def test_completo_sin_notas_de_cobertura(self):
        self.assertEqual(notas_cobertura(SEM, _m(), _m(), _m()), [])

    def test_anio_no_repite_nota(self):
        anio, previo = Periodo.anio_completo(2026), Periodo.anio_completo(2025)
        notas = notas_cobertura(anio, _m(anio), _m(previo, dias_con_cierre=200), _m(previo, dias_con_cierre=200))
        self.assertEqual(sum("200 de 365" in n for n in notas), 1)

    def test_reglas_documentan_los_umbrales(self):
        texto = " ".join(notas_reglas())
        for fragmento in ("±1%", "±1 pp", "90%", "14:00", "0.5%", "2 pp", "lunes a domingo"):
            self.assertIn(fragmento, texto)
        self.assertEqual(notas_pie(SEM, _m(), _m(), _m()), notas_reglas())


class ComparablesTests(SimpleTestCase):
    """New branches (no full data in the comparison period) are left out of
    both sides of that comparison and named in the footnotes."""

    ANT = SEM.anterior()

    def _caso(self):
        nombres = ["Vieja", "Nueva"]
        actuales = [_m(), _m(venta_neta=D("5000"))]
        bases = [_m(self.ANT, venta_neta=D("9000")), Metricas(periodo=self.ANT)]  # Nueva did not exist
        return nombres, actuales, bases

    def test_excluye_de_ambos_lados(self):
        nombres, actuales, bases = self._caso()
        comp = comparables(nombres, actuales, bases, SEM, self.ANT)
        self.assertEqual(comp.excluidas, ["Nueva"])
        self.assertEqual(comp.actual.venta_neta, D("10000"))  # only Vieja
        self.assertEqual(comp.base.venta_neta, D("9000"))

    def test_tabla_muestra_total_y_compara_solo_comparables(self):
        nombres, actuales, bases = self._caso()
        total = consolidar(actuales, SEM)
        venta = {f.indicador.clave: f for f in construir_tabla(total, comparables(nombres, actuales, bases, SEM, self.ANT), None)}["venta_neta"]
        self.assertEqual(venta.actual, D("15000"))  # the whole selection
        self.assertEqual(venta.anterior, D("9000"))
        self.assertEqual(round(venta.var_anterior.porcentaje, 4), D("0.1111"))  # 10000 vs 9000, not 15000 vs 9000

    def test_lectura_y_nota(self):
        nombres, actuales, bases = self._caso()
        total = consolidar(actuales, SEM)
        comp = comparables(nombres, actuales, bases, SEM, self.ANT)
        texto = construir_lectura(SEM, total, comp, None).observaciones[0].texto
        self.assertIn("La venta neta fue de $15,000", texto)
        self.assertIn("▲ +11.1% (+$1,000) vs la semana anterior en sucursales comparables", texto)
        notas = notas_cobertura(SEM, total, comp, None)
        self.assertTrue(any("se excluye Nueva por no tener" in n for n in notas))

    def test_ninguna_comparable(self):
        comp = comparables(["Nueva"], [_m()], [Metricas(periodo=self.ANT)], SEM, self.ANT)
        self.assertIsNone(comp.base)
        self.assertIn("Sin comparativo contra la semana anterior: Nueva no tiene datos completos en ese periodo "
                      "(sucursal nueva o sin operación).", notas_cobertura(SEM, _m(), comp, None))
        venta = {f.indicador.clave: f for f in construir_tabla(_m(), comp, None)}["venta_neta"]
        self.assertEqual(venta.var_anterior.direccion, c.SIN_DATO)

    def test_sin_periodo_de_comparacion(self):
        comp = comparables(["A"], [_m()], None, SEM, None)
        self.assertIsNone(comp.base)
        self.assertEqual(comp.excluidas, [])
