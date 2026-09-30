from datetime import timedelta
from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import comparativos as c
from .motor import detalle
from .motor.metricas import Comparacion, Metricas, consolidar
from .motor.periodo import Periodo, TipoPeriodo
from .motor.reporte_comercial import _uno


def _m(periodo, venta="1000", dias=None, costo=None):
    dias = periodo.dias if dias is None else dias
    fechas = [periodo.desde + timedelta(i) for i in range(dias)]
    m = Metricas(periodo=periodo, venta_bruta=D(venta) * dias, venta_neta=D(venta) * dias, clientes=D("10") * dias,
                 dias_con_cierre=dias, dias_con_detalle=dias,
                 venta_por_dia={f: D(venta) for f in fechas}, tickets_por_dia={f: D("4") for f in fechas},
                 clientes_por_dia={f: D("10") for f in fechas})
    if costo is not None:
        m.costo_ventas_real, m.venta_neta_con_costo = D(costo), m.venta_neta
    return m


class DetalleTests(SimpleTestCase):
    SEM = Periodo.semana(2026, 39)

    def test_por_sucursal_ordena_y_respeta_comparables(self):
        ant = self.SEM.anterior()
        vieja, nueva = _m(self.SEM, "1000", costo="2730"), _m(self.SEM, "3000")
        r = _uno("Consolidado", ["Vieja", "Nueva"], self.SEM, consolidar([vieja, nueva], self.SEM),
                 Comparacion(vieja, _m(ant, "900")), Comparacion(vieja, None), None)
        r.por_sucursal = [("Vieja", vieja, _m(ant, "900")), ("Nueva", nueva, _m(ant, "900", dias=2))]
        filas, total = detalle.por_sucursal(r)
        self.assertEqual([f.nombre for f in filas], ["Nueva", "Vieja"])  # largest sales first
        self.assertEqual(filas[0].var_anterior.direccion, c.SIN_DATO)  # new branch: 2 of 7 days before, no comparison
        self.assertEqual(filas[1].semaforo, c.VERDE)  # 2730 / 7000 = 39%
        self.assertEqual(total.venta_bruta, D("28000"))
        self.assertEqual(total.var_anterior, next(f for f in r.filas if f.indicador.clave == "venta_bruta").var_anterior)

    def test_semana_compara_dia_contra_dia(self):
        ant = self.SEM.anterior()
        r = _uno("Puebla", ["Puebla"], self.SEM, _m(self.SEM), Comparacion(_m(self.SEM), _m(ant, "800")),
                 Comparacion(_m(self.SEM), None), None)
        filas = detalle.por_periodo(r)
        self.assertTrue(detalle.compara_con_anterior(r))
        self.assertEqual((len(filas), filas[0].etiqueta), (7, "Lun 21"))
        self.assertEqual((filas[0].venta_anterior, filas[0].cheque_promedio), (D("800"), D("100")))

    def test_mes_sin_columna_anterior(self):
        ago = Periodo.de_fecha(TipoPeriodo.MES, self.SEM.desde.replace(month=8, day=15))
        r = _uno("Puebla", ["Puebla"], ago, _m(ago), Comparacion(_m(ago), _m(ago.anterior())),
                 Comparacion(_m(ago), None), {"Puebla": {}})
        filas = detalle.por_periodo(r)
        self.assertFalse(detalle.compara_con_anterior(r))  # calendar month: no day-by-day pairing
        self.assertEqual((len(filas), filas[0].etiqueta), (31, "Sáb 1"))
        self.assertTrue(all(f.venta_anterior is None for f in filas))
