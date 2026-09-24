from datetime import datetime, date
from decimal import Decimal

from django.test import SimpleTestCase

from .motor.fuentes import presupuestos as pp
from .motor.fuentes import wansoft as w

CV, GO = "Costo de Ventas", "Gasto Operativo"
TIPOS = {1: CV, 2: CV, 3: GO, 4: GO}


class DiaOperativoTests(SimpleTestCase):
    def test_cierre_antes_de_las_14_pertenece_al_dia_anterior(self):
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 6, 0, 57)), date(2026, 9, 5))
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 8, 12, 51)), date(2026, 9, 7))
        self.assertEqual(w.dia_operativo(datetime(2026, 8, 20, 9, 23)), date(2026, 8, 19))

    def test_cierre_de_la_noche_pertenece_al_mismo_dia(self):
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 7, 23, 29)), date(2026, 9, 7))
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 7, 19, 0)), date(2026, 9, 7))
        self.assertEqual(w.dia_operativo(datetime(2026, 9, 7, 14, 0)), date(2026, 9, 7))


class ResolverCostoVentasTests(SimpleTestCase):
    def test_solo_cuentan_los_tipos_explicitos_de_la_categoria(self):
        por_tipo = {1: Decimal("100"), 3: Decimal("50")}
        self.assertEqual(pp.resolver_costo_ventas_mensual(por_tipo, TIPOS, False), Decimal("100"))

    def test_el_sobrante_se_reparte_entre_tipos_sin_presupuesto_propio(self):
        # 4 tipos, tipo 1 explicito; sobrante 300 -> 3 tipos sin explicito, 100 c/u;
        # de esos, el tipo 2 es Costo de Ventas
        por_tipo = {1: Decimal("1000"), None: Decimal("300")}
        self.assertEqual(pp.resolver_costo_ventas_mensual(por_tipo, TIPOS, False), Decimal("1100.00"))

    def test_sin_clasificar_toma_una_parte_extra_del_sobrante(self):
        # 4 tipos sin explicito + 1 (sin clasificar) = 5 partes de 60
        por_tipo = {None: Decimal("300")}
        self.assertEqual(pp.resolver_costo_ventas_mensual(por_tipo, TIPOS, True), Decimal("120.00"))
        self.assertEqual(pp.resolver_costo_ventas_mensual(por_tipo, TIPOS, False), Decimal("150.00"))

    def test_sin_sobrante_no_agrega_nada(self):
        self.assertEqual(pp.resolver_costo_ventas_mensual({3: Decimal("9")}, TIPOS, True), Decimal("0"))

    def test_meses_del_rango(self):
        self.assertEqual(pp._meses(date(2026, 6, 29), date(2026, 7, 5)), [date(2026, 6, 1), date(2026, 7, 1)])
        self.assertEqual(pp._meses(date(2026, 12, 28), date(2027, 1, 3)), [date(2026, 12, 1), date(2027, 1, 1)])


class _Cursor:
    def __init__(self, filas):
        self.filas, self.sql, self.params = filas, None, None

    def execute(self, sql, params=()):
        self.sql, self.params = sql, params

    def fetchall(self):
        return self.filas


class ConsultasEnLoteTests(SimpleTestCase):
    """One query per period for all branches (the ticket table is scanned once)."""

    def test_detalle_agrupa_dias_y_canales_por_sucursal(self):
        cur = _Cursor([
            ("PUEBLA", "2026-09-14", "Restaurant", Decimal("100")),
            ("PUEBLA", "2026-09-14", "eCommerce", Decimal("20")),
            ("PUEBLA", "2026-09-15", "Restaurant", Decimal("50")),
            ("PUEBLA", "2026-09-15", "Raro", Decimal("5")),
            ("ACOXPA", "2026-09-14", "Para llevar", Decimal("7")),
        ])
        r = w.detalle_por_sucursal(cur, ["PUEBLA", "ACOXPA", None, "SIN DETALLE"], date(2026, 9, 14), date(2026, 9, 20))
        self.assertEqual(r["PUEBLA"], (2, {"salon": Decimal("150"), "plataformas": Decimal("20"), "otros": Decimal("5")}))
        self.assertEqual(r["ACOXPA"], (1, {"llevar": Decimal("7")}))
        self.assertNotIn("SIN DETALLE", r)
        self.assertEqual(cur.sql.count("%s"), 5)  # 3 names (None dropped) + 2 dates
        self.assertEqual(cur.params[-2:], ("2026-09-14", "2026-09-21"))

    def test_sin_sucursales_no_consulta(self):
        cur = _Cursor([])
        self.assertEqual(w.detalle_por_sucursal(cur, [None], date(2026, 9, 14), date(2026, 9, 20)), {})
        self.assertEqual(w.cierres_por_dia(cur, [], date(2026, 9, 14), date(2026, 9, 20)), {})
        self.assertIsNone(cur.sql)

    def test_cierres_por_sucursal_y_dia(self):
        fila = (7, date(2026, 9, 14)) + tuple(Decimal(i) for i in range(1, 10))
        r = w.cierres_por_dia(_Cursor([fila]), [7, 9], date(2026, 9, 14), date(2026, 9, 20))
        self.assertEqual(r[7][date(2026, 9, 14)]["venta_bruta"], Decimal(1))
        self.assertEqual(r[7][date(2026, 9, 14)]["descuentos"], Decimal(9))
        self.assertNotIn(9, r)
