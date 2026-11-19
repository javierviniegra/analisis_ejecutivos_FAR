import io
from datetime import date, datetime
from decimal import Decimal as D

import openpyxl
from django.db import connection
from django.test import SimpleTestCase, TestCase

from .motor import reporte_cedis as rc
from .motor.fuentes import odoo
from .salidas import excel_cedis


def _msg(id, fecha_utc, cuerpo="", autor="Katia Moreno"):
    return {"id": id, "date": fecha_utc, "author_id": [1, autor], "body": cuerpo}


def _orden(nombre="P10276", sucursal="Antenas", proveedor=rc.BODEGON, final="11471.1", creada=datetime(2026, 6, 1, 10, 11)):
    return rc.Orden(nombre, sucursal, proveedor, "purchase", creada, datetime(2026, 6, 1, 11, 15, 20), D(final))


LINEAS = {"Queso Gouda": dict(precio=D("154"), pedida=D("0"), recibida=D("0")),
          "Gouda Polaco Recorte": dict(precio=D("140"), pedida=D("5"), recibida=D("5"))}


class InterpretarTests(SimpleTestCase):
    """Real P10276 (Antenas -> El Bodegón), from Odoo's chatter."""

    def _p10276(self):
        mensajes = [
            _msg(1, "2026-06-01 16:49:37"),  # before confirming: ignored
            _msg(2, "2026-06-01 19:00:57", "<p>Se actualizó la cantidad ordenada.</p><p>Queso Gouda: Cantidad ordenada: "
                                           "5.0 -&gt; 0.0 Cantidad facturada: 0.0</p>"),
            _msg(3, "2026-06-01 19:00:57", "<p>Linea extra con Gouda Polaco Recorte</p>"),
            _msg(4, "2026-06-01 19:00:57"),
        ]
        montos = {1: (D("0"), D("7580")), 4: (D("13069"), D("11471.1"))}
        return rc.interpretar(_orden(), mensajes, montos, LINEAS, odoo.a_cdmx)

    def test_solo_despues_de_confirmar(self):
        o = self._p10276()
        self.assertEqual(len(o.montos), 1)  # the pre-confirmation amount change is ignored
        self.assertEqual((o.monto_al_confirmar, o.diferencia), (D("13069.0"), D("-1597.9")))

    def test_cambio_de_cantidad_y_linea_extra(self):
        o = self._p10276()
        c = o.cantidades[0]
        self.assertEqual((c.producto, c.anterior, c.nueva, c.tipo, c.impacto), ("Queso Gouda", D("5.0"), D("0.0"), rc.DISMINUCION, D("-770.00")))
        self.assertEqual(c.fecha, datetime(2026, 6, 1, 13, 0, 57))  # UTC-6
        self.assertEqual(o.horas_despues(c.fecha), 1.8)
        e = o.extras[0]
        self.assertEqual((e.producto, e.pedida, e.subtotal), ("Gouda Polaco Recorte", D("5"), D("700")))

    def test_dos_definiciones_de_modificada(self):
        solo_cantidad = rc.interpretar(_orden("P12527", final="2400"), [_msg(1, "2026-06-02 10:00:00",
                                        "Se actualizó la cantidad ordenada. Te Sencha: Cantidad ordenada: 20.0 -> 80.0")],
                                       {}, {}, odoo.a_cdmx)
        self.assertTrue(solo_cantidad.modificada)  # "modificaciones": any change
        self.assertFalse(solo_cantidad.modificada_subtotal)  # "por hora": amount or extra line only
        self.assertIsNone(solo_cantidad.cantidades[0].impacto)  # no line price found: no invented impact

    def test_hora_cdmx(self):
        self.assertEqual(odoo.a_cdmx("2026-06-01 16:11:12"), datetime(2026, 6, 1, 10, 11, 12))
        self.assertEqual(odoo.limite_utc(date(2026, 6, 1)), "2026-06-01 06:00:00")


class TablasTests(SimpleTestCase):
    def _datos(self):
        a = InterpretarTests()._p10276()
        b = _orden("P2", "Antenas", rc.EMPANADAS, "2900", datetime(2026, 6, 1, 10, 21))
        c = _orden("P3", "Puebla", rc.BODEGON, "500", datetime(2026, 6, 2, 14, 5))
        return rc.DatosCedis(date(2026, 6, 1), date(2026, 9, 22), [a, b, c], ["Antenas", "Puebla"],
                             {"Antenas": date(2026, 6, 1), "Puebla": date(2026, 6, 10)}, 45, datetime(2026, 9, 30, 12, 0))

    def test_resumen_y_por_hora(self):
        d = self._datos()
        r = {(f["proveedor"], f["sucursal"]): f for f in rc.resumen(d)}
        f = r[(rc.BODEGON, "Antenas")]
        self.assertEqual((f["ordenes"], f["modificadas"], f["con_cantidad"], f["con_extras"], f["con_monto"], f["diferencia"]),
                         (1, 1, 1, 1, 1, D("-1597.9")))
        horas = rc.por_hora(d)
        self.assertEqual((horas[10]["Antenas"], horas[14]["Puebla"]), (2, 1))
        self.assertEqual(rc.por_hora(d, rc.EMPANADAS)[10]["Antenas"], 1)
        self.assertEqual(rc.detalle_cambios(d.ordenes[0]), "Monto 13,069.00 -> 11,471.10 | Linea extra con Gouda Polaco Recorte")  # as the owner's Excel

    def test_libros_con_las_hojas_originales(self):
        d = self._datos()
        m = openpyxl.load_workbook(io.BytesIO(excel_cedis.modificaciones(d)))
        self.assertEqual(m.sheetnames, ["Resumen", "Ordenes modificadas", "Cambios de cantidad", "Lineas extra",
                                        "Cambios de monto", "Productos mas cambiados", "Notas"])
        self.assertEqual(m["Resumen"]["K2"].value, -1597.9)
        self.assertEqual(m["Resumen"]["I1"].value, "Modificadas por la sucursal")
        self.assertEqual([m["Resumen"].cell(i, 2).value for i in range(2, 7)], ["Antenas", "Puebla", "Total", "Antenas", "Total"])
        self.assertIn("Se excluyen 45 órdenes generadas automáticamente", m["Notas"]["A5"].value)
        h = openpyxl.load_workbook(io.BytesIO(excel_cedis.por_hora(d)))
        self.assertEqual(h.sheetnames, ["Ordenes por hora", "% Modificaciones", "% Modif. por hora", "Por hora - Bodegon",
                                        "Por hora - Empanadas", "Detalle", "Notas"])
        self.assertEqual(h["Ordenes por hora"]["A26"].value, "Total")
        self.assertEqual(h["Ordenes por hora"]["D26"].value, 3)  # 3 orders in total


class QuienYClientesTests(SimpleTestCase):
    def test_hecho_por_la_sucursal_o_el_cedis(self):
        mensajes = [_msg(2, "2026-06-01 19:00:57", "Se actualizó la cantidad ordenada. Queso Gouda: Cantidad ordenada: 5.0 -> 0.0"),
                    _msg(3, "2026-06-01 20:00:00", "Linea adicional con Gouda Polaco Recorte")]  # sales-order wording
        mensajes[1]["author_id"] = [99, "Lilia Arredondo"]
        o = rc.interpretar(_orden(), mensajes, {}, LINEAS, odoo.a_cdmx, lambda autor: rc.CEDIS if autor == 99 else rc.SUCURSAL)
        self.assertEqual((o.cantidades[0].hecho_por, o.extras[0].hecho_por), (rc.SUCURSAL, rc.CEDIS))
        self.assertTrue(o.modificada_por(rc.CEDIS) and o.modificada_por(rc.SUCURSAL))

    def test_la_direccion_de_entrega_manda_sobre_el_cliente(self):
        F = rc.FilaCliente
        clientes = {1: F(1, "aeropuerto"), 2: F(2, "taqueria-viaducto"), 3: F(3, excluir=True), 4: F(4)}
        pedido = lambda cliente, entrega: {"partner_id": [cliente, "x"], "partner_shipping_id": [entrega, "y"] if entrega else False}  # noqa: E731
        self.assertEqual(rc._cliente_de(pedido(1, 2), clientes).sucursal_clave, "taqueria-viaducto")
        self.assertEqual(rc._cliente_de(pedido(1, 1), clientes).sucursal_clave, "aeropuerto")
        self.assertTrue(rc._cliente_de(pedido(3, None), clientes).excluir)
        self.assertIsNone(rc._cliente_de(pedido(4, 5), clientes))  # unassigned: reported in the notes


class _Suc:
    """A branch as a consumer without Central's models passes it."""

    def __init__(self, clave, nombre, odoo_company_id=None, ticket=None):
        self.clave, self.nombre, self.odoo_company_id, self.wansoft_ticket_nombre = clave, nombre, odoo_company_id, ticket


def _pedido(id, cliente, entrega=None, nombre=None):
    return {"id": id, "name": nombre or f"S{id:05d}", "company_id": [50, "El Bodegón"], "state": "sale",
            "create_date": "2026-11-10 15:00:00", "date_order": "2026-11-10 15:05:00", "amount_untaxed": 1000.0,
            "auto_purchase_order_id": False, "partner_id": [cliente, f"Cliente {cliente}"],
            "partner_shipping_id": [entrega, f"Entrega {entrega}"] if entrega else False}


class LeerConMapeoTests(SimpleTestCase):
    """`leer` with the mapping and the active branches passed in (no Central
    models): the CEDIS-captured orders go to the selected branches by `clave`."""

    PEDIDOS = [_pedido(1, 10), _pedido(2, 11, entrega=12), _pedido(3, 13), _pedido(4, 14), _pedido(5, 15)]
    CLIENTES = [rc.FilaCliente(10, "acoxpa", nota="Entrega interna"), rc.FilaCliente(11, "aeropuerto"),
                rc.FilaCliente(12, "taqueria-viaducto"), rc.FilaCliente(13, etiqueta="Perisur"),
                rc.FilaCliente(14, excluir=True)]  # 15: not mapped
    ACTIVAS = {"acoxpa", "aeropuerto", "taqueria-viaducto"}

    def _leer(self, sucursales, activas=ACTIVAS):
        from contextlib import nullcontext
        from unittest import mock
        cli = mock.Mock()
        cli.llamar.return_value = [{"id": 50, "name": "El Bodegón"}]
        with mock.patch("central.motor.fuentes.conexiones.abrir_wansoft", return_value=nullcontext(None)), \
                mock.patch.multiple("central.motor.fuentes.wansoft", inicio_compras_odoo=lambda cur: {},
                                    inicio_proveedores_internos=lambda cur: {}), \
                mock.patch.multiple("central.motor.fuentes.odoo", abrir_odoo=lambda: cli,
                                    proveedores_internos=lambda c: {900: "El Bodegón"},
                                    companias_de=lambda c, ids: [50],
                                    pedidos_venta=lambda c, comp, d, h: self.PEDIDOS,
                                    ordenes_por_id=lambda c, ids: [], mensajes_de=lambda c, m, ids: [],
                                    cambios_de_monto=lambda c, ids: [], compania_de_autores=lambda c, ids: {},
                                    lineas=lambda c, ids: [], lineas_venta=lambda c, ids: []):
            return rc.leer(sucursales, date(2026, 11, 9), date(2026, 11, 15), clientes=self.CLIENTES, activas=activas)

    def test_solo_las_sucursales_elegidas_por_clave(self):
        d = self._leer([_Suc("acoxpa", "Acoxpa"), _Suc("taqueria-viaducto", "Taquería Viaducto")])
        # order 2: the delivery address (Taquería Viaducto) wins over the customer (Aeropuerto)
        self.assertEqual([(o.nombre, o.sucursal) for o in d.ordenes], [("S00001", "Acoxpa"), ("S00002", "Taquería Viaducto")])
        self.assertEqual(d.sucursales, ["Acoxpa", "Taquería Viaducto"])
        self.assertEqual((d.excluidas_cliente, d.sin_asignar), (1, {"Cliente 15": 1}))
        self.assertEqual(d.notas_clientes, ["Entrega interna"])

    def test_el_nombre_es_el_de_la_sucursal_que_pasa_quien_llama(self):
        d = self._leer([_Suc("acoxpa", "FA Acoxpa")])
        self.assertEqual([o.sucursal for o in d.ordenes], ["FA Acoxpa"])

    def test_clientes_que_no_son_sucursal_solo_con_todas(self):
        todas = [_Suc("acoxpa", "Acoxpa"), _Suc("aeropuerto", "Aeropuerto"), _Suc("taqueria-viaducto", "Taquería Viaducto")]
        self.assertIn("Perisur", self._leer(todas).sucursales)
        self.assertNotIn("Perisur", self._leer(todas[:2]).sucursales)
        self.assertNotIn("Perisur", self._leer(todas, activas=self.ACTIVAS | {"napoles"}).sucursales)

    def test_fila_de_la_consulta(self):
        f = rc.fila_cliente({"odoo_partner_id": "7", "sucursal_clave": None, "etiqueta": "León", "excluir": 0,
                             "nota": None})
        self.assertEqual(f, rc.FilaCliente(7, None, "León", False, ""))
        self.assertTrue(f.asignado)
        self.assertFalse(rc.FilaCliente(8).asignado)
        self.assertIn("central_clientecedis", rc.CONSULTA_CLIENTES)


class LeerDesdeCentralTests(TestCase):
    """Inside Central, the defaults read the `ClienteCedis` table and the active
    branches, as before the mapping could be passed in."""

    def test_mapeo_y_activas_de_las_tablas_de_central(self):
        from cuentas.models import Sucursal

        from .models import ClienteCedis
        acoxpa = Sucursal.objects.create(clave="acoxpa", nombre="Acoxpa")
        Sucursal.objects.create(clave="vieja", nombre="Vieja", activa=False)
        ClienteCedis.objects.create(odoo_partner_id=10, nombre_odoo="FA ACOXPA", sucursal=acoxpa, nota="n")
        ClienteCedis.objects.create(odoo_partner_id=13, nombre_odoo="PERISUR", etiqueta="Perisur")
        self.assertEqual(sorted(rc.clientes_de_central(), key=lambda f: f.odoo_partner_id),
                         [rc.FilaCliente(10, "acoxpa", "", False, "n"), rc.FilaCliente(13, None, "Perisur", False, "")])
        self.assertEqual(rc.activas_de_central(), {"acoxpa"})
        with connection.cursor() as cur:  # the documented query reads the same table
            cur.execute(rc.CONSULTA_CLIENTES)
            columnas = [c[0] for c in cur.description]
            filas = sorted((rc.fila_cliente(dict(zip(columnas, f))) for f in cur.fetchall()),
                           key=lambda f: f.odoo_partner_id)
            cur.execute(rc.CONSULTA_ACTIVAS)
            activas = {f[0] for f in cur.fetchall()}
        self.assertEqual(filas, [rc.FilaCliente(10, "acoxpa", "", False, "n"), rc.FilaCliente(13, None, "Perisur", False, "")])
        self.assertEqual(activas, {"acoxpa"})
