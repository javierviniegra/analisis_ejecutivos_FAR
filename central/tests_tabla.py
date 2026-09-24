from datetime import date
from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor.metricas import Metricas, consolidar
from .motor.periodo import Periodo
from .motor.tabla_comercial import PORCENTAJE, construir_tabla, variacion_puntos

SEM = Periodo.semana(2026, 39)


def _m(**kw):
    base = dict(periodo=SEM, venta_bruta=D("1000"), venta_neta=D("862"), tickets=D("10"), clientes=D("25"),
                dias_con_cierre=7, dias_con_detalle=7,
                canal={"salon": D("900"), "llevar": D("100")}, mix={"Alimentos": D("750"), "Bebidas": D("250")})
    base.update(kw)
    return Metricas(**base)


def _fila(filas, clave):
    return next(f for f in filas if f.indicador.clave == clave)


class MetricasTests(SimpleTestCase):
    def test_promedios_y_porcentajes(self):
        m = _m()
        self.assertEqual(m.cheque_promedio, D("40"))
        self.assertEqual(m.ticket_promedio, D("100"))
        self.assertEqual(m.pct_mix("Alimentos"), D("0.75"))
        self.assertEqual(m.pct_canal("salon"), D("0.9"))
        self.assertIsNone(m.pct_canal("plataformas") if not m.canal else None)

    def test_sin_denominador_devuelve_none(self):
        m = _m(clientes=D("0"), tickets=D("0"), canal={}, mix={})
        self.assertIsNone(m.cheque_promedio)
        self.assertIsNone(m.ticket_promedio)
        self.assertIsNone(m.pct_mix("Alimentos"))

    def test_consolidar_suma_y_lleva_la_cobertura(self):
        a = _m(costo_ventas_real=D("10"), costo_ventas_ppto=D("20"), costo_ventas_real_con_ppto=D("10"),
               n_con_presupuesto=1, venta_por_dia={date(2026, 9, 21): D("100")})
        b = _m(venta_bruta=D("500"), dias_con_detalle=0, canal={}, mix={}, venta_por_dia={date(2026, 9, 21): D("50")})
        t = consolidar([a, b], SEM)
        self.assertEqual(t.venta_bruta, D("1500"))
        self.assertEqual(t.n_sucursales, 2)
        self.assertEqual(t.dias_esperados, 14)
        self.assertEqual((t.dias_con_cierre, t.dias_con_detalle), (14, 7))
        self.assertEqual(t.venta_por_dia[date(2026, 9, 21)], D("150"))
        # budget only from the branch that has it
        self.assertEqual((t.costo_ventas_real, t.costo_ventas_ppto, t.n_con_presupuesto), (D("10"), D("20"), 1))

    def test_ejercido_no_mezcla_sucursales_con_y_sin_presupuesto(self):
        con = _m(costo_ventas_real=D("90"), costo_ventas_ppto=D("100"), costo_ventas_real_con_ppto=D("90"), n_con_presupuesto=1)
        sin = _m(costo_ventas_real=D("500"))  # spends 500 but has no budget
        t = consolidar([con, sin], SEM)
        self.assertEqual(t.costo_ventas_real, D("590"))
        self.assertEqual(t.ejercido_costo_ventas, D("0.9"))  # 90/100, the branch without budget is excluded

    def test_consolidar_sin_ninguna_sucursal_con_presupuesto_deja_none(self):
        t = consolidar([_m(), _m()], SEM)
        self.assertIsNone(t.costo_ventas_real)
        self.assertEqual(t.n_con_presupuesto, 0)


class TablaTests(SimpleTestCase):
    def test_variacion_contra_periodo_anterior_y_anio_anterior(self):
        filas = construir_tabla(_m(venta_bruta=D("1100")), _m(venta_bruta=D("1000")), _m(venta_bruta=D("1200")))
        f = _fila(filas, "venta_bruta")
        self.assertEqual((f.var_anterior.direccion, f.var_anterior.color), (c.SUBE, c.VERDE))
        self.assertEqual((f.var_anio.direccion, f.var_anio.color), (c.BAJA, c.ROJO))

    def test_metricas_donde_subir_es_malo(self):
        filas = construir_tabla(_m(cancelaciones=D("200")), _m(cancelaciones=D("100")), None)
        self.assertEqual(_fila(filas, "cancelaciones").var_anterior.color, c.ROJO)

    def test_periodo_de_comparacion_sin_datos_da_sin_comparativo(self):
        vacio = _m(dias_con_cierre=0, venta_bruta=D("0"))
        f = _fila(construir_tabla(_m(), vacio, None), "venta_bruta")
        self.assertIsNone(f.anterior)
        self.assertEqual(f.var_anterior.direccion, c.SIN_DATO)
        self.assertEqual(f.var_anio.direccion, c.SIN_DATO)

    def test_sin_detalle_de_tickets_no_hay_mezcla_ni_canal(self):
        sin_detalle = _m(dias_con_detalle=0, canal={}, mix={})
        filas = construir_tabla(sin_detalle, _m(), None)
        self.assertIsNone(_fila(filas, "mix_alimentos").actual)
        self.assertIsNone(_fila(filas, "canal_salon").actual)
        self.assertIsNotNone(_fila(filas, "venta_bruta").actual)

    def test_mezcla_se_compara_en_puntos_y_siempre_en_gris(self):
        # Alimentos 75% vs 70% = +5 points; no good/bad direction -> grey
        actual = _m(mix={"Alimentos": D("750"), "Bebidas": D("250")})
        previo = _m(mix={"Alimentos": D("700"), "Bebidas": D("300")})
        v = _fila(construir_tabla(actual, previo, None), "mix_alimentos").var_anterior
        self.assertEqual((v.direccion, v.color), (c.SUBE, c.GRIS))
        self.assertEqual(v.porcentaje, D("0.05"))

    def test_puntos_umbral_de_un_punto(self):
        self.assertEqual(variacion_puntos(D("0.755"), D("0.75")).direccion, c.IGUAL)
        self.assertEqual(variacion_puntos(D("0.77"), D("0.75")).direccion, c.SUBE)
        self.assertEqual(variacion_puntos(None, D("0.75")).direccion, c.SIN_DATO)

    def test_presupuesto_ausente_no_aparece_como_cero(self):
        filas = construir_tabla(_m(), _m(), None)
        for clave in ("costo_ventas_real", "costo_ventas_ppto", "costo_ventas_ejercido"):
            self.assertIsNone(_fila(filas, clave).actual)

    def test_gasto_real_se_muestra_aunque_falte_el_presupuesto(self):
        filas = construir_tabla(_m(costo_ventas_real=D("13058")), None, None)
        self.assertEqual(_fila(filas, "costo_ventas_real").actual, D("13058"))
        self.assertIsNone(_fila(filas, "costo_ventas_ppto").actual)
        self.assertIsNone(_fila(filas, "costo_ventas_ejercido").actual)

    def test_costo_de_ventas_ejercido(self):
        m = _m(costo_ventas_real=D("90"), costo_ventas_ppto=D("100"), costo_ventas_real_con_ppto=D("90"), n_con_presupuesto=1)
        f = _fila(construir_tabla(m, None, None), "costo_ventas_ejercido")
        self.assertEqual(f.actual, D("0.9"))
        self.assertEqual(f.indicador.formato, PORCENTAJE)
