from datetime import date

from django.test import SimpleTestCase

from .motor.fuentes import presupuestos, verificacion, wansoft


class VerificacionTests(SimpleTestCase):
    def test_faltantes(self):
        requeridas = {"a": ["x", "y"], "b": ["z"], "c": ["w"]}
        existentes = {"a": {"x", "y", "extra"}, "b": set()}
        self.assertEqual(verificacion.faltantes(requeridas, existentes), {"b": ["z"], "c": ["w"]})
        self.assertEqual(verificacion.faltantes({"a": ["x"]}, {"a": {"x"}}), {})

    def test_atrasadas_con_tolerancia_de_dos_dias(self):
        hoy = date(2026, 10, 1)
        ultimo = {"Al día": date(2026, 9, 30), "Antes de la carga": date(2026, 9, 29),
                  "Atrasada": date(2026, 9, 28), "Sin datos": None}
        self.assertEqual(verificacion.atrasadas(ultimo, hoy),
                         [("Atrasada", date(2026, 9, 28)), ("Sin datos", None)])

    def test_puede_escribir(self):
        solo_lectura = ["GRANT USAGE ON *.* TO `central_reportes`@`%`",
                        "GRANT SELECT ON `wansoft`.`getglobalcashclosing` TO `central_reportes`@`%`",
                        "GRANT SELECT, SHOW VIEW ON `presupuestos_ap`.* TO `x`@`%`"]
        self.assertFalse(verificacion.puede_escribir(solo_lectura))
        self.assertTrue(verificacion.puede_escribir(
            ["GRANT USAGE ON *.* TO `wansoftuser`@`%`", "GRANT ALL PRIVILEGES ON `wansoft`.* TO `wansoftuser`@`%`"]))
        self.assertTrue(verificacion.puede_escribir(["GRANT SELECT, INSERT ON `wansoft`.* TO `x`@`%`"]))

    def test_columnas_declaradas(self):
        # the declared requirements cover the tables each source module queries
        self.assertEqual(set(wansoft.COLUMNAS_REQUERIDAS),
                         {"getglobalcashclosing", "getallordenesbyday_new_venta", "getallordenesbyday_new_detalleventa",
                          "costeomensual", "costeomensual_semanapyq", "dim_company_analytical"})
        self.assertIn("presupuestos_gastoreal", presupuestos.COLUMNAS_REQUERIDAS)
