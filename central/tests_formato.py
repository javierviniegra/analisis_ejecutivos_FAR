"""Ticket and check per branch format in the consolidated commercial report (owner, 2026-10-19)."""

from decimal import Decimal as D
from types import SimpleNamespace

from django.test import SimpleTestCase

from .motor import reporte_comercial as rc
from .motor.metricas import Metricas
from .motor.periodo import Periodo
from .motor.tabla_comercial import SECCION_FORMATO, filas_por_formato

SEM = Periodo.semana(2026, 42)
LY = SEM.mismo_periodo_anio_anterior()


def _m(periodo, venta, tickets, clientes, dias=None):
    dias = periodo.dias if dias is None else dias
    return Metricas(periodo=periodo, venta_bruta=D(venta), venta_neta=D(venta), tickets=D(tickets), clientes=D(clientes),
                    dias_con_cierre=dias, dias_con_detalle=dias)


def _suc(nombre, formato):
    return SimpleNamespace(nombre=nombre, formato=formato)


class FormatoTests(SimpleTestCase):
    def test_ticket_y_cheque_por_formato_contra_el_anio(self):
        sucs = [_suc("Acoxpa", "fonda"), _suc("Parroquia", "taqueria"), _suc("Esquina", "esquina")]
        ma = [_m(SEM, 22000, 10, 22), _m(SEM, 8000, 10, 16), _m(SEM, 6000, 5, 10)]
        my = [_m(LY, 20000, 10, 20), _m(LY, 7000, 10, 14), _m(LY, 0, 0, 0, dias=0)]  # La Esquina did not exist
        filas = filas_por_formato(rc._grupos_formato(sucs, ma, ma, my, SEM, SEM.anterior(), LY))
        por = {f.indicador.clave: f for f in filas}
        self.assertEqual([f.etiqueta for f in filas][:4], ["Ticket promedio · Fondas", "Cheque promedio · Fondas",
                                                          "Ticket promedio · Taquerías", "Cheque promedio · Taquerías"])
        self.assertEqual((por["ticket_fondas"].actual, por["ticket_fondas"].anio_anterior), (D(2200), D(2000)))
        self.assertEqual(por["ticket_taquerías"].var_anio.direccion, "sube")  # 800 vs 700
        self.assertIsNone(por["ticket_la_esquina"].anio_anterior)  # new: no comparison, never a zero
        self.assertTrue(all(f.indicador.seccion == SECCION_FORMATO for f in filas))

    def test_un_solo_formato_no_se_separa(self):
        sucs = [_suc("Acoxpa", "fonda"), _suc("Viaducto", "fonda")]
        ma = [_m(SEM, 1000, 1, 2)] * 2
        self.assertEqual(rc._grupos_formato(sucs, ma, ma, ma, SEM, SEM.anterior(), LY), [])

    def test_filas_despues_de_ventas(self):
        sucs = [_suc("Acoxpa", "fonda"), _suc("Parroquia", "taqueria")]
        ma = [_m(SEM, 1000, 1, 2)] * 2
        tabla = rc.construir_tabla(ma[0], None, None)
        filas = rc._con_formatos(tabla, filas_por_formato(rc._grupos_formato(sucs, ma, ma, ma, SEM, SEM.anterior(), LY)))
        secciones = [f.indicador.seccion for f in filas]
        ventas = max(i for i, s in enumerate(secciones) if s == "Ventas")
        self.assertEqual(secciones[ventas + 1], SECCION_FORMATO)


class AvisoComparablesTests(SimpleTestCase):
    """Owner, 2026-10-20: a visible notice at the top of the consolidated report."""

    def test_consolidado_dice_quien_queda_fuera(self):
        from .motor.metricas import Comparacion
        actual, base = _m(SEM, 1000, 1, 2), _m(LY, 900, 1, 2)
        r = rc._uno("Consolidado", ["Acoxpa", "Puebla"], SEM, actual, Comparacion(actual, None),
                    Comparacion(actual, base, ["Puebla"]), None)
        self.assertIn("solo con sucursales comparables", r.aviso_comparables)
        self.assertTrue(r.aviso_comparables.endswith("Fuera de la comparación: Puebla."))
        sucursal = rc._uno("Acoxpa", ["Acoxpa"], SEM, actual, Comparacion(actual, None), Comparacion(actual, base), None)
        self.assertIsNone(sucursal.aviso_comparables)  # one branch: nothing to say
