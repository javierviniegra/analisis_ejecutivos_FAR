"""CEDIS metrics: fill rate to the branches and the top-20 input inflation."""

from datetime import date, datetime
from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import fill_rate as fr
from .motor import inflacion_insumos as ii
from .motor import reporte_cedis as rc
from .motor.comparativos import NARANJA, ROJO, VERDE
from .motor.periodo import Periodo, TipoPeriodo

AHORA = datetime(2026, 11, 10, 9, 0)


def _orden(nombre, lineas, cantidades=(), extras=(), sucursal="Acoxpa", proveedor=rc.BODEGON):
    o = rc.Orden(nombre, sucursal, proveedor, "purchase", AHORA, AHORA, D("0"))
    o.lineas = [rc.LineaPedido(p, D(q), D(e), rc.producto_base(p)) for p, q, e in lineas]
    o.cantidades = [rc.CambioCantidad(AHORA, "u", p, D(a), D(n), None, quien) for p, a, n, quien in cantidades]
    o.extras = [rc.LineaExtra(AHORA, "u", p, None, None, None, quien) for p, quien in extras]
    return o


class ProductoBaseTests(SimpleTestCase):
    def test_variantes_del_mismo_producto(self):
        base = rc.producto_base("Contenedor Kraft 45x33.5 cm")
        for variante in ("Contenedor Kraft 45x33.5 cm Ind", "[5100-1] Contenedor  kraft 45x33.5 cm",
                         "Contenedor Kraft 45x33.5 cm copia", "Contenedor Kraft 45x33.5 cm (copia)"):
            self.assertEqual(rc.producto_base(variante), base)
        self.assertNotEqual(rc.producto_base("Salsa Inglesa 2.2 Lt Ind"), rc.producto_base("Salsa Tipo Inglesa 3.9 Lt Ind"))


class LineasPedidoTests(SimpleTestCase):
    def test_oc_de_sucursal_contra_lo_entregado_en_su_pedido_de_venta(self):
        oc = [{"order_id": [1, "P1"], "product_id": [7705, "Contenedor Kraft 45x33.5 cm Ind"], "name": "", "product_qty": 200},
              {"order_id": [1, "P1"], "product_id": [60, "Jarabe de Horchata .750 lt"], "name": "", "product_qty": 1.5}]
        so = [{"order_id": [9, "S9"], "product_id": [4810, "Contenedor Kraft 45x33.5 cm"], "name": "",
               "product_uom_qty": 200, "qty_delivered": 180},
              {"order_id": [8, "S8"], "product_id": [5, "Chorizo"], "name": "", "product_uom_qty": 4.7, "qty_delivered": 4.7},
              {"order_id": [8, "S8"], "product_id": [5, "Chorizo"], "name": "", "product_uom_qty": 1, "qty_delivered": 0}]
        salida = rc.lineas_pedido(oc, so, {1: 9})
        self.assertEqual(salida[("oc", 1)], [
            rc.LineaPedido("Contenedor Kraft 45x33.5 cm Ind", D("200"), D("180"), "contenedor kraft 45x33.5 cm"),
            rc.LineaPedido("Jarabe de Horchata .750 lt", D("1.5"), D("0"), "jarabe de horchata .750 lt")])
        self.assertEqual(salida[("so", 8)], [rc.LineaPedido("Chorizo", D("5.7"), D("4.7"), "chorizo")])
        self.assertNotIn(("so", 9), salida)  # read through its purchase order


class FillRateTests(SimpleTestCase):
    def test_lo_que_pidio_la_sucursal(self):
        o = _orden("P1", [("Queso Gouda", "8", "8"), ("Chorizo", "5", "5"), ("Pan", "10", "10"), ("Sal", "0", "0")],
                   cantidades=[("Queso Gouda", "10", "8", rc.CEDIS),  # CEDIS cut: the branch ordered 10
                               ("Chorizo", "3", "5", rc.SUCURSAL)],  # the branch's own change counts
                   extras=[("Pan", rc.CEDIS)])  # added by the CEDIS: not ordered
        self.assertEqual(fr.pedido_por_sucursal(o), [("queso gouda", "Queso Gouda", D("10"), D("8")),
                                                     ("chorizo", "Chorizo", D("5"), D("5"))])

    def test_por_producto_en_el_periodo_y_promedio_simple(self):
        ordenes = [_orden("P1", [("Queso Gouda Ind", "10", "8"), ("Chorizo", "5", "6")]),
                   _orden("P2", [("Queso Gouda", "10", "10")], sucursal="Tepeyac"),
                   _orden("S3", [("Empanada de Carne", "100", "90")], proveedor=rc.EMPANADAS)]
        productos = {(p.proveedor, p.producto): p for p in fr.por_producto(ordenes)}
        gouda = productos[(rc.BODEGON, "Queso Gouda Ind")]  # both variants together, over both orders
        self.assertEqual((gouda.pedida, gouda.entregada, gouda.fill, gouda.pedidos), (D("20"), D("18"), D("0.9"), 2))
        self.assertEqual(productos[(rc.BODEGON, "Chorizo")].fill, D("1"))  # capped at 100%
        r = fr.resumen(rc.DatosCedis(date(2026, 11, 9), date(2026, 11, 15), ordenes, ["Acoxpa", "Tepeyac"], {}, 0))
        self.assertEqual(r.total.fill, (D("0.9") + D("1") + D("0.9")) / 3)
        self.assertEqual([(f.grupo, f.fill) for f in r.por_proveedor], [(rc.BODEGON, D("0.95")), (rc.EMPANADAS, D("0.9"))])
        self.assertEqual([(f.grupo, f.fill) for f in r.por_sucursal], [("Acoxpa", (D("0.8") + D("1") + D("0.9")) / 3),
                                                                       ("Tepeyac", D("1"))])
        self.assertEqual(r.sin_entrega, 0)

    def test_semaforo(self):
        self.assertEqual([fr.estado(D(v)) for v in ("0.98", "0.979", "0.95", "0.9499")], [VERDE, NARANJA, NARANJA, ROJO])
        self.assertIsNone(fr.estado(None))
        self.assertIsNone(fr.fill("Vacío", []).fill)


class InflacionInsumosTests(SimpleTestCase):
    def test_top_por_gasto_y_laspeyres(self):
        en_ventana = {k: ii.Compra(k, n, D(g), D("1")) for k, n, g in
                      (("a", "Rib Eye", "300"), ("b", "Arrachera", "200"), ("c", "Sal", "1"), ("d", "Lomo", "100"))}
        actual = {"a": ii.Compra("a", "Rib Eye", D("1100"), D("10")), "b": ii.Compra("b", "Arrachera", D("400"), D("2")),
                  "d": ii.Compra("d", "Lomo", D("50"), D("1"))}
        anterior = {"a": ii.Compra("a", "Rib Eye", D("2000"), D("20")), "b": ii.Compra("b", "Arrachera", D("800"), D("5"))}
        p = Periodo.bloque(TipoPeriodo.MES, 2026, 10)
        self.assertEqual(ii.top(en_ventana, 3), ["a", "b", "d"])
        r = ii.construir(p, p.mismo_periodo_anio_anterior(), ii.ventana(p.desde), en_ventana, actual, anterior)
        # Laspeyres over the inputs with both prices: (110x20 + 200x5) / (100x20 + 160x5) - 1
        self.assertEqual(r.inflacion, D(110 * 20 + 200 * 5) / D(100 * 20 + 160 * 5) - 1)
        self.assertEqual(r.sin_comparar, ["Lomo", "Sal"])
        self.assertEqual(r.filas[0].variacion, D("0.1"))

    def test_ventana_de_12_meses(self):
        self.assertEqual(ii.ventana(date(2026, 10, 1)), (date(2025, 10, 1), date(2026, 9, 30)))
        self.assertEqual(ii.ventana(date(2026, 11, 9)), (date(2025, 11, 9), date(2026, 11, 8)))

    def test_semaforo_contra_el_inpc(self):
        inpc = D("0.0345")
        self.assertEqual([ii.estado(D(v), inpc) for v in ("-0.03", "0.0345", "0.0545", "0.0546")],
                         [VERDE, VERDE, NARANJA, ROJO])
        self.assertIsNone(ii.estado(None, inpc))
        self.assertIsNone(ii.estado(D("0.01"), None))

    def test_inpc_del_mes_o_el_ultimo_publicado(self):
        serie = {date(2025, 9, 1): D("100"), date(2026, 9, 1): D("103.45")}
        self.assertEqual(ii.inpc_referencia(serie, date(2026, 10, 31)), (date(2026, 9, 1), D("103.45") / D("100") - 1))
        self.assertIsNone(ii.inpc_referencia(serie, date(2027, 3, 31)))  # more than 3 months back
