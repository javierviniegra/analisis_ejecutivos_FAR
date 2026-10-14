"""Waiters' report (owner, 2026-10-13): metrics, Lectura, comparable branches, outputs."""

from datetime import date
from decimal import Decimal as D
from unittest import mock

from django.test import SimpleTestCase

from .motor import reporte_meseros as rm
from .motor.meseros import DatosMeseros, Mesero, consolidar, nombre_corto
from .motor.periodo import Periodo

SEM = Periodo.semana_de(date(2026, 10, 8))


def _mesero(nombre, venta, personas, cuentas=20, dias=5, bebidas=None, propina=0, cortesias=0, descuentos=0):
    bebidas = D(venta) * D("0.25") if bebidas is None else D(bebidas)
    return Mesero(nombre, cuentas=D(cuentas), personas=D(personas), venta_bruta=D(venta), venta_neta=D(venta) / D("1.16"),
                  dias=D(dias), minutos_mesa=D(cuentas * 100), mesas_con_tiempo=D(cuentas),
                  alimentos=D(venta) - bebidas, bebidas=bebidas, propina=D(propina), cortesias=D(cortesias),
                  descuentos=D(descuentos))


def _datos(periodo=SEM, dias=7, **meseros):
    d = DatosMeseros(periodo=periodo, dias_con_cierre=dias, dias_con_detalle=dias)
    for m in meseros.values():
        d.meseros[m.nombre] = m
    return d


class MeseroTests(SimpleTestCase):
    def test_indicadores_del_mesero(self):
        m = _mesero("Ana", 100000, 100, cuentas=40, dias=5, bebidas=25000, propina=10000)
        self.assertEqual(m.cheque_promedio, D(1000))
        self.assertEqual(m.venta_por_dia, D(20000))
        self.assertEqual(m.personas_por_mesa, D("2.5"))
        self.assertEqual(m.pct_bebidas, D("0.25"))
        self.assertEqual(m.pct_propina, D("0.1"))
        self.assertEqual(m.tiempo_mesa, D(100))

    def test_cortesias_y_descuentos(self):
        m = _mesero("Ana", 90000, 100, cortesias=6000, descuentos=4000)
        self.assertEqual(m.control, D(10000))
        self.assertEqual(m.pct_control, D("0.1"))  # 10,000 / (90,000 + 10,000)

    def test_plantilla_sin_pseudousuarios_en_cero(self):
        d = _datos(a=_mesero("Ana", 1000, 2), b=_mesero("Apps Llevar", 0, 1, cuentas=1))
        self.assertEqual(d.plantilla, 1)  # $0 accounts: not a waiter
        self.assertEqual([m.nombre for m in d.ranking()], ["Ana"])

    def test_consolidado_suma_plantillas_y_separa_meseros_por_sucursal(self):
        a, b = _datos(x=_mesero("Ana", 1000, 2)), _datos(x=_mesero("Ana", 3000, 3))
        t = consolidar([a, b], SEM, ["Acoxpa", "Puebla"])
        self.assertEqual(t.plantilla, 2)
        self.assertEqual(set(t.meseros), {"Acoxpa · Ana", "Puebla · Ana"})
        self.assertEqual(t.total.venta_bruta, D(4000))

    def test_nombre_corto(self):
        self.assertEqual(nombre_corto("Jose Luis Borja Ausencio"), "Jose L. B.")
        self.assertEqual(nombre_corto("Acoxpa · Ana"), "Ana")


class LecturaYReglasTests(SimpleTestCase):
    def _reporte(self, actual, anterior):
        return rm._uno("Acoxpa", ["Acoxpa"], SEM, actual, anterior,
                       rm.comparables(["Acoxpa"], [actual], [anterior], SEM, SEM.anterior()),
                       rm.comparables(["Acoxpa"], [actual], None, SEM, None))

    def test_semaforo_de_cheque_y_lectura(self):
        actual = _datos(a=_mesero("Ana Ruiz", 120000, 100), b=_mesero("Beto Paz", 60000, 100, cortesias=9000),
                        c=_mesero("Caro Gil", 100000, 100), d=_mesero("Suplente Uno", 5000, 5, cuentas=3))
        anterior = _datos(periodo=SEM.anterior(), a=_mesero("Ana Ruiz", 100000, 100))
        r = self._reporte(actual, anterior)
        # average check = 285,000 / 305 = 934: Ana 1,200 green, Beto 600 red, Caro 1,000 green
        sem = {f.nombre: f.semaforo_cheque for f in r.detalle}
        self.assertEqual((sem["Ana Ruiz"], sem["Beto Paz"], sem["Caro Gil"]), ("verde", "rojo", "verde"))
        textos = " ".join(o.texto for o in r.lectura.observaciones)
        self.assertIn("Mejor cheque promedio: Ana Ruiz ($1,200)", textos)
        self.assertIn("Beto Paz ($600)", textos)
        self.assertNotIn("Suplente", textos)  # under MIN_CUENTAS_LECTURA accounts
        self.assertIn("Más cortesías y descuentos: Beto Paz ($9,000", textos)
        self.assertTrue(any("menos de 10 cuentas" in n for n in r.cobertura))
        self.assertTrue(any("Plantilla = meseros con al menos una cuenta" in x for x in r.reglas))

    def test_sucursal_sin_datos_completos_sale_del_comparativo(self):
        actual = _datos(a=_mesero("Ana", 1000, 2))
        nueva = _datos(periodo=SEM.anterior(), dias=2, a=_mesero("Ana", 900, 2))  # 2 of 7 days
        comp = rm.comparables(["Puebla"], [actual], [nueva], SEM, SEM.anterior())
        self.assertIsNone(comp.base)
        self.assertEqual(comp.excluidas, ["Puebla"])


class SalidasTests(SimpleTestCase):
    def test_panel_y_apartado_de_aplicaciones(self):
        actual = _datos(a=_mesero("Ana Ruiz", 100000, 100, cortesias=1000, descuentos=500))
        actual.fuera = {"plataformas": {"cuentas": D(30), "venta_bruta": D(20000), "descuentos": D(800), "cortesias": D(0)},
                        "llevar": {"cuentas": D(10), "venta_bruta": D(5000), "descuentos": D(200), "cortesias": D(100)}}
        anterior = _datos(periodo=SEM.anterior(), a=_mesero("Ana Ruiz", 90000, 100))
        r = rm._uno("Acoxpa", ["Acoxpa"], SEM, actual, anterior,
                    rm.comparables(["Acoxpa"], [actual], [anterior], SEM, SEM.anterior()),
                    rm.comparables(["Acoxpa"], [actual], None, SEM, None))
        panel = {f.indicador.clave: f for f in r.panel}
        self.assertEqual(panel["p_venta"].actual, D(125000))  # dining room + apps + take-away
        self.assertEqual(panel["p_cortesias"].actual, D(1100))
        self.assertEqual(panel["p_descuentos"].actual, D(1500))
        self.assertEqual(panel["p_venta"].var_anterior.direccion, "sube")
        self.assertIn("p_cancelaciones", panel)
        self.assertIn("p_anulaciones", panel)
        filas = {f.indicador.clave: f for f in r.filas}
        self.assertEqual((filas["apps_venta"].actual, filas["apps_descuentos"].actual), (D(20000), D(800)))
        self.assertTrue(any(o.texto.startswith("Fuera de salón: aplicaciones $20,000") for o in r.lectura.observaciones))

    def test_pdf_y_excel_se_generan(self):
        from .salidas import excel_meseros, pdf_meseros
        actual = _datos(a=_mesero("Ana Ruiz", 120000, 100), b=_mesero("Beto Paz", 60000, 100))
        anterior = _datos(periodo=SEM.anterior(), a=_mesero("Ana Ruiz", 100000, 100))
        with mock.patch.object(rm.datos_meseros, "recolectar", side_effect=[[actual], [anterior], [anterior]]), \
                mock.patch.object(rm.conexiones, "abrir_wansoft") as abrir:
            abrir.return_value.__enter__.return_value = None
            from types import SimpleNamespace
            reportes = rm.armar([SimpleNamespace(nombre="Acoxpa")], SEM, False)
        self.assertTrue(pdf_meseros.generar(reportes).startswith(b"%PDF"))
        libro_bytes = excel_meseros.generar(reportes)
        self.assertTrue(libro_bytes.startswith(b"PK"))
        import io
        from openpyxl import load_workbook
        from .salidas import AVISO_AUTOMATICO
        libro = load_workbook(io.BytesIO(libro_bytes))
        self.assertTrue(all(ws.oddFooter.left.text == AVISO_AUTOMATICO for ws in libro.worksheets))  # every sheet
        self.assertEqual(pdf_meseros.nombre_archivo(reportes), "Reporte_Meseros_Acoxpa_Semana_41_5_oct_11_oct_2026.pdf")
