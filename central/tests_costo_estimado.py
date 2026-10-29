"""Estimated total cost while Odoo invoicing is behind (rule B2, 2026-10-05)."""

from datetime import date, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from django.test import SimpleTestCase

from .motor import metricas
from .motor.fuentes import wansoft
from .motor.metricas import Metricas, consolidar, estimar_costo_odoo
from .motor.notas import notas_cobertura, notas_reglas
from .motor.periodo import Periodo
from .motor.tabla_comercial import construir_tabla

LUNES = date(2026, 9, 28)
DIAS = [LUNES + timedelta(days=i) for i in range(7)]
# Acoxpa, week 40 (real figures read 2026-10-05): Wansoft cost 28-30 Sep, Odoo cost from 1-Oct.
VENTA = dict(zip(DIAS, [D(69676), D(72213), D(107182), D(134984), D(254495), D(428100), D(243707)]))
COSTO = dict(zip(DIAS, [D("26542.34"), D("25308.01"), D("39092.50"), D("27940.49"), D("65457.91"),
                        D("47552.49"), D("27075.55")]))
FACTURADO = dict(zip(DIAS, [D(69676), D(72213), D(107182), D(88955), D(190317), D(135699), D(79764)]))
DIAS_ODOO = DIAS[3:]


class EstimarCostoTests(SimpleTestCase):
    def test_acoxpa_semana_40(self):
        c = estimar_costo_odoo(sum(COSTO.values()), DIAS_ODOO, COSTO, FACTURADO, VENTA)
        self.assertTrue(c.estimado)
        # Wansoft days real (90,942.85) + Odoo days 168,026.44 / 494,735 x 1,061,286
        esperado = D("90942.85") + D("168026.44") / D(494735) * D(1061286)
        self.assertAlmostEqual(c.costo, esperado, places=2)
        self.assertAlmostEqual(float(c.costo / sum(VENTA.values())), 0.344, places=3)
        self.assertEqual(c.facturado, D(494735))

    def test_facturado_completo_deja_el_costo_real(self):
        completo = {d: v * D("0.996") for d, v in VENTA.items()}
        c = estimar_costo_odoo(D(1000), DIAS_ODOO, COSTO, completo, VENTA)
        self.assertFalse(c.estimado)
        self.assertEqual(c.costo, D(1000))

    def test_sin_facturas_no_se_puede_estimar(self):
        c = estimar_costo_odoo(D(1000), DIAS_ODOO, COSTO, {}, VENTA)
        self.assertTrue(c.estimado)
        self.assertIsNone(c.costo)

    def test_sin_dias_de_odoo_no_cambia(self):
        c = estimar_costo_odoo(D(1000), [], COSTO, {}, VENTA)
        self.assertFalse(c.estimado)
        self.assertEqual(c.costo, D(1000))


class _Cursor:
    def __init__(self, *resultados):
        self.resultados = list(resultados)

    def execute(self, sql, params=()):
        self.actual = self.resultados.pop(0)

    def fetchall(self):
        return self.actual


def _suc(nombre, odoo_id):
    return SimpleNamespace(wansoft_ticket_nombre=nombre, odoo_company_id=odoo_id)


class RuteoCostosTests(SimpleTestCase):
    def test_tabla_publicada_por_el_pipeline(self):
        cur = _Cursor([(1,)], [("Acoxpa", date(2026, 10, 1)), ("Puebla", date(2026, 6, 10))])
        inicios = wansoft.inicio_costos_odoo(cur, [_suc("Acoxpa", 7), _suc("Antenas", 9), _suc("Viaducto", None)])
        self.assertEqual(inicios, {"Acoxpa": date(2026, 10, 1)})

    def test_respaldo_politica_excepcion_y_cambio_automatico(self):
        cur = _Cursor([(0,)], [(7, date(2026, 10, 1)), (5, date(2026, 10, 1)), (6, date(2026, 10, 1))],
                      [("Isabel La Católica", date(2026, 10, 6))])
        inicios = wansoft.inicio_costos_odoo(cur, [
            _suc("Acoxpa", 7), _suc("Antenas", 9), _suc("Isabel La Católica", 5), _suc("San Jeronimo", 6),
            _suc("Viaducto", None)])
        # Acoxpa from its policy date; Antenas excepted; Isabel from its switch; San Jeronimo not switched yet
        self.assertEqual(inicios, {"Acoxpa": date(2026, 10, 1), "Isabel La Católica": date(2026, 10, 6)})


class SalidasCostoEstimadoTests(SimpleTestCase):
    def _metricas(self, estimado=True):
        m = Metricas(periodo=Periodo.semana_de(LUNES), venta_neta=D(1000), dias_con_cierre=7,
                     costo_total=D(344), venta_neta_con_costo_total=D(1000), costo_estimado_odoo=estimado,
                     venta_dias_odoo=D(800), facturado_odoo=D(400))
        return m

    def test_etiqueta_y_nota(self):
        m = self._metricas()
        filas = {f.indicador.clave: f for f in construir_tabla(m, None, None)}
        self.assertEqual(filas["costo_total"].etiqueta, "Costo total (Wansoft/Odoo), estimado")
        self.assertEqual(filas["costo_total_pct"].semaforo, "naranja")  # 34.4%: still traffic-lighted
        self.assertFalse(filas["costo_ventas_real"].estimado)
        notas = notas_cobertura(m.periodo, m, None, None)
        self.assertTrue(any("Odoo ha facturado el 50%" in n for n in notas))

    def test_consolidado_propaga_estimado(self):
        total = consolidar([self._metricas(), self._metricas(estimado=False)], Periodo.semana_de(LUNES))
        self.assertTrue(total.costo_total_estimado)
        self.assertEqual(total.pct_facturado_odoo, D(800) / D(1600))

    def test_sin_costos_quita_reglas_y_notas_de_costo(self):
        m = self._metricas()
        self.assertFalse([r for r in notas_reglas(m.periodo, incluir_costos=False) if "osto" in r.split(":")[0]])
        self.assertFalse([n for n in notas_cobertura(m.periodo, m, None, None, incluir_costos=False) if "osto" in n])
        # the estimate is explained in the notes when it happens, never as a standing rule
        self.assertFalse(any("estimado" in r for r in notas_reglas(m.periodo)))

    def test_pendiente_de_wansoft(self):
        m = self._metricas(estimado=False)
        self.assertFalse(m.costo_total_estimado)
        self.assertFalse([n for n in notas_cobertura(m.periodo, m, None, None) if "estimado" in n])  # complete: silent
        m.pendiente_wansoft = D("20054")
        self.assertTrue(m.costo_total_estimado)
        filas = {f.indicador.clave: f for f in construir_tabla(m, None, None)}
        self.assertTrue(filas["costo_total"].estimado)
        self.assertTrue(any("pendiente de rebaja" in n and "$20,054" in n
                            for n in notas_cobertura(m.periodo, m, None, None)))

    def test_umbral(self):
        self.assertEqual(metricas.UMBRAL_FACTURADO_COMPLETO, D("0.995"))


class ConsiderarCostoYPresupuestoTests(SimpleTestCase):
    """Owner, 2026-10-05: a branch whose cost is not considered (Metepec) shows no
    cost in its report and is reported as left out in the consolidated; a
    partial budget is not shown in the consolidated."""

    def _armar(self, consolidado):
        from contextlib import nullcontext
        from unittest import mock

        from .motor import reporte_comercial

        def metricas_de(cur_w, cur_p, sucursales, periodo, **kw):
            salida = []
            for s in sucursales:
                m = Metricas(periodo=periodo, venta_bruta=D(1160), venta_neta=D(1000), dias_con_cierre=periodo.dias)
                if s.considerar_costo:
                    m.costo_total, m.venta_neta_con_costo_total = D(385), D(1000)
                if s.nombre == "Acoxpa":
                    m.costo_ventas_ppto, m.n_con_presupuesto = D(400), 1
                    m.costo_ventas_real, m.venta_neta_con_costo, m.n_con_costo_ventas = D(390), D(1000), 1
                salida.append(m)
            return salida

        sucursales = [SimpleNamespace(nombre="Acoxpa", odoo_company_id=7, considerar_costo=True),
                      SimpleNamespace(nombre="Metepec", odoo_company_id=None, considerar_costo=False)]
        with mock.patch.object(reporte_comercial.conexiones, "abrir_wansoft", return_value=nullcontext()), \
                mock.patch.object(reporte_comercial.conexiones, "abrir_presupuestos", return_value=nullcontext()), \
                mock.patch.object(reporte_comercial, "_abrir_odoo", return_value=None), \
                mock.patch.object(reporte_comercial.metricas, "recolectar", side_effect=metricas_de):
            return reporte_comercial.armar(sucursales, Periodo.semana_de(LUNES), consolidado)

    def test_reporte_de_metepec_sin_costos(self):
        acoxpa, metepec = self._armar(False)
        self.assertTrue(acoxpa.incluir_costos)
        self.assertFalse(metepec.incluir_costos)
        self.assertFalse(any("osto" in r.split(":")[0] for r in metepec.reglas))

    def test_consolidado_avisa_y_quita_presupuesto_parcial(self):
        (r,) = self._armar(True)
        self.assertTrue(any(n.startswith("No se considera el costo de Metepec") for n in r.cobertura))
        self.assertTrue(any("presupuesto de Costo de Ventas no se muestra" in n for n in r.cobertura))
        self.assertIsNone(r.actual.costo_ventas_ppto)
        self.assertIsNone(r.anterior.base.costo_ventas_ppto)  # the comparison periods too
        self.assertFalse([f for f in r.filas if f.indicador.clave in ("costo_ventas_ppto", "costo_ventas_real")])
        self.assertIsNone(r.actual.pct_costo_ventas)
        self.assertTrue(any(n.startswith("El costo facturado (Presupuestos AP) no se muestra") for n in r.cobertura))
        self.assertEqual(r.lectura.observaciones[-1].texto.count("facturado"), 0)
        self.assertEqual(r.actual.pct_costo_total, D("0.385"))  # Acoxpa only: Metepec's sales out of the base
        self.assertFalse(any("sin dato" in n for n in r.cobertura))  # Metepec is not "missing", it is excluded
