"""Dining room without the platform / take-away users, and tips over card
payments (owner, 2026-11-17)."""

from datetime import date
from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor.fuentes import wansoft


class _Cursor:
    """Records the statements and answers each one with the next canned rows."""

    def __init__(self, *respuestas):
        self.respuestas, self.consultas = list(respuestas), []

    def execute(self, sql, params=()):
        self.consultas.append((sql, tuple(params)))

    def fetchall(self):
        return self.respuestas.pop(0)


class SalonTests(SimpleTestCase):
    def test_condicion_de_salon_deja_fuera_a_los_usuarios_de_plataformas(self):
        sql, params = wansoft._salon("v")
        self.assertIn("v.TipoOrden = %s AND UPPER(TRIM(COALESCE(v.Mesero, ''))) NOT IN", sql)
        self.assertEqual(params[0], "Restaurant")
        self.assertEqual(set(params[1:]), {"APPS LLEVAR", "APLICACIONES", "DELIVERY", "UBER/RAPPI", "LLEVAR",
                                           "CUENTAS PARA LLEVAR"})
        self.assertNotIn("PRUEBA", params)  # test and support users stay waiters
        self.assertEqual(sql.count("%s"), len(params))

    def test_ventas_de_meseros_usan_la_condicion(self):
        cur = _Cursor([("Acoxpa", "Ana", 3, 6, 3000, 2586, 1, 120, 3)])
        r = wansoft.ventas_meseros(cur, ["Acoxpa"], date(2026, 10, 1), date(2026, 10, 7))
        sql, params = cur.consultas[0]
        self.assertIn("NOT IN", sql)
        self.assertEqual(sql.count("%s"), len(params))
        self.assertEqual(r["Acoxpa"]["Ana"]["venta_bruta"], D(3000))

    def test_cuentas_de_salon_de_esos_usuarios_van_a_su_canal(self):
        totales = [("Acoxpa", "eCommerce", None, 10, 5000), ("Acoxpa", "Restaurant", "APPS LLEVAR", 2, 700),
                   ("Metepec", "Restaurant", "CUENTAS PARA LLEVAR", 1, 300), ("Metepec", "Para llevar", None, 4, 900)]
        lineas = [("Acoxpa", "Restaurant", "APPS LLEVAR", 50, 0)]
        cur = _Cursor(totales, lineas)
        r = wansoft.fuera_de_salon(cur, ["Acoxpa", "Metepec"], date(2026, 10, 1), date(2026, 10, 7))
        self.assertEqual((r["Acoxpa"]["plataformas"]["cuentas"], r["Acoxpa"]["plataformas"]["venta_bruta"]),
                         (D(12), D(5700)))
        self.assertEqual(r["Acoxpa"]["plataformas"]["descuentos"], D(50))
        self.assertEqual(r["Metepec"]["llevar"]["venta_bruta"], D(1200))
        for sql, params in cur.consultas:
            self.assertEqual(sql.count("%s"), len(params))


class PropinaTarjetaTests(SimpleTestCase):
    def test_propina_y_pago_con_tarjeta_por_mesero(self):
        cur = _Cursor([("Acoxpa", " Ana ", 800, 8000)])
        r = wansoft.propinas_meseros(cur, ["Acoxpa"], date(2026, 10, 1), date(2026, 10, 7))
        self.assertEqual(r, {"Acoxpa": {"Ana": {"propina": D(800), "tarjeta": D(8000)}}})
        sql, params = cur.consultas[0]
        self.assertIn("p.MetodoDePago IN", sql)
        self.assertEqual(params[-4:], ("Tarjeta de crédito", "Tarjeta de débito", "Amex", "CLIP"))
        self.assertEqual(sql.count("%s"), len(params))
