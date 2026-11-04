from collections import Counter
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from .motor import flujo_efectivo as fe
from .motor.periodo import Periodo, TipoPeriodo

SEP = Periodo.bloque(TipoPeriodo.MES, 2026, 9)
ACOXPA = 7
BANCO, OTRO_BANCO = 100, 101


def _cuenta(id, code, name, tipo="asset_current"):
    return {"id": id, "code": code, "placeholder_code": False, "name": name, "account_type": tipo}


def _banco(id, move, monto, fecha="2026-09-10", cuenta=BANCO):
    return {"id": id, "company_id": [ACOXPA, "FONDA COSTA NERA"], "account_id": [cuenta, "BBVA 9168"], "journal_id": [1, "BBVA 9168"],
            "date": fecha, "balance": monto, "move_id": [move, "BNK/1"], "name": "", "partner_id": False}


def _contra(id, move, cuenta, nombre, monto, parciales=(), socio=False):
    return {"id": id, "move_id": [move, "x"], "account_id": [cuenta, nombre], "balance": monto, "name": "", "partner_id": socio,
            "matched_debit_ids": list(parciales), "matched_credit_ids": []}


def _crudo(**partes):
    base = {k: [] for k in ("movimientos", "extractos", "contra", "parciales", "otro_lado", "lineas_asiento", "pagos",
                            "lineas_factura", "cuentas", "socios")}
    base.update(partes)
    return base


class ReglasTests(SimpleTestCase):
    def test_forma_de_pago_del_memo(self):
        self.assertEqual(fe.forma_de_pago("Wansoft 8834 - Tarjeta de crédito"), "Tarjeta de crédito")
        # numeric code = Wansoft's payment-method code + the account's last 4 digits
        self.assertEqual(fe.forma_de_pago("Wansoft 182354 - 42682"), "Tarjeta de crédito")
        self.assertEqual(fe.forma_de_pago("Wansoft 1 - 52682"), "Tarjeta de débito")
        self.assertEqual(fe.forma_de_pago("Wansoft 1 - 122682"), "Didi")
        self.assertIsNone(fe.forma_de_pago("Factura F-123"))

    def test_solo_bancos_e_inversiones(self):
        self.assertTrue(fe.es_cuenta_de_efectivo("102.01.05"))
        self.assertTrue(fe.es_cuenta_de_efectivo("103.01.02"))
        self.assertFalse(fe.es_cuenta_de_efectivo("101.01.03"))  # caja chica: out (accountant)
        self.assertFalse(fe.es_cuenta_de_efectivo("102.01.05P"))  # pagos pendientes: a bridge

    def test_rubro_por_codigo(self):
        casos = {("210.01.01", "Provision of wages and salaries to pay"): fe.NOMINA,
                 ("216.12.02", "Cesantia y vejez"): fe.SEGURIDAD_SOCIAL,
                 ("205.06.02", "Infonavit"): fe.SEGURIDAD_SOCIAL,
                 ("213.04.01", "Impuesto sobre nómina"): fe.IMPUESTOS,
                 ("208.01.01", "VAT carried forward collected"): fe.IMPUESTOS,
                 ("701.10.01", "Comisiones Bancarias"): fe.COMISIONES,
                 ("504.01.13", "Comisiones Plataformas"): fe.COMISIONES,
                 ("106.01.04", "CxC Amex"): fe.POR_DEPOSITAR,
                 ("102.01.07", "Banorte 2266"): fe.TRASPASOS}
        for (codigo, nombre), rubro in casos.items():
            self.assertEqual(fe.por_cuenta(codigo, nombre, D("-100"))[0], rubro, codigo)
        self.assertIsNone(fe.por_cuenta("102.01.05P", "Pagos Pendientes BBVA 9168", D("-1")))
        self.assertEqual(fe.por_cuenta("301.03.10", "AP FA SAI Estudios", D("500"))[0], fe.APORTACIONES)
        self.assertEqual(fe.por_cuenta("101.01.03", "Caja Chica", D("-20"))[1], "Caja y caja chica")

    def test_grupos_de_gasto(self):
        self.assertEqual(fe.grupo_gasto("Management Administrativo"), "Administración y regalías (Rodiva)")
        self.assertEqual(fe.grupo_gasto("Gas"), "Insumos y mercancía")
        self.assertEqual(fe.grupo_gasto("Gastos de Instalacion y/o remodelacion"), "Mantenimiento e instalaciones")  # not "gas"
        self.assertEqual(fe.grupo_gasto("Arrendamiento PM"), fe.GRUPO_RENTAS)
        self.assertEqual(fe.grupo_gasto("Cuenta rara"), fe.OTROS_GASTOS)

    def test_texto_de_lineas_sin_conciliar(self):
        self.assertEqual(fe.por_texto("REGISTRO ENTRECUENTAS SEP-26")[0], fe.TRASPASOS)
        self.assertEqual(fe.por_texto("REGISTRO DE COMISIONES BANCARIAS Y PLATAFORMAS SEP-26")[0], fe.COMISIONES)
        self.assertEqual(fe.por_texto("PAGO DE IMSS AGO-26")[0], fe.SEGURIDAD_SOCIAL)
        self.assertEqual(fe.por_texto("REGISTRO PAGO CREDITO BANAMEX")[0], fe.SIN_IDENTIFICAR)

    def test_rentas_renglon_propio_y_grupo_como_proveedor(self):
        pago = {"payment_type": "outbound", "partner_type": "supplier", "partner_id": [9, "EL BODEGON DE FITO"]}
        self.assertEqual(fe.por_pago(pago, "EL BODEGON DE FITO", Counter({"Arrendamiento PM": 10})), (fe.RENTAS, fe.GRUPO_RENTAS))
        self.assertEqual(fe.por_pago(pago, None, Counter({"Goods Received - No Invoices": 10}))[1], "Insumos y mercancía")
        cobro = {"payment_type": "inbound", "partner_type": "customer", "memo": "S00012", "partner_id": [3, "FONDA COSTA NERA"]}
        self.assertEqual(fe.por_pago(cobro, "FONDA COSTA NERA", Counter())[0], fe.COBROS_GRUPO)
        self.assertEqual(fe.por_pago({**cobro, "partner_id": [4, "GASTRONOMIA MUNDO E"]}, None, Counter())[0], fe.VENTAS_FACTURA)


class ClasificarTests(SimpleTestCase):
    def _clasificar(self, lineas, **crudo):
        return fe.clasificar(lineas, _crudo(**crudo), {50: "EL BODEGON DE FITO"}, {})

    def test_deposito_conciliado_con_tickets_y_cxc(self):
        """A 1,000 deposit = two ticket payments (700 + 200) + 100 moved to CxC bancos."""
        cuentas = [_cuenta(1, "102.01.05R", "Recibos Pendientes BBVA 9168"), _cuenta(2, "106.01.02", "CxC BBVA", "asset_receivable")]
        movs = self._clasificar(
            [_banco(10, 1, 1000)],
            movimientos=[{"id": 1, "move_type": "entry", "ref": "", "statement_line_id": [5, "x"], "origin_payment_id": False}],
            extractos=[{"id": 5, "payment_ref": "DEPOSITO TPV"}],
            contra=[_contra(20, 1, 1, "Recibos Pendientes BBVA 9168", -900, [71, 72]), _contra(21, 1, 2, "CxC BBVA", -100)],
            parciales=[{"id": 71, "debit_move_id": [30, ""], "credit_move_id": [20, ""], "amount": 700},
                       {"id": 72, "debit_move_id": [31, ""], "credit_move_id": [20, ""], "amount": 200}],
            otro_lado=[{"id": 30, "move_id": [3, ""], "account_id": [1, ""], "partner_id": False, "payment_id": [80, ""],
                        "statement_line_id": False, "move_type": "entry"},
                       {"id": 31, "move_id": [4, ""], "account_id": [1, ""], "partner_id": False, "payment_id": [81, ""],
                        "statement_line_id": False, "move_type": "entry"}],
            pagos=[{"id": 80, "payment_type": "inbound", "partner_type": "customer", "memo": "Wansoft 1 - 42682",
                    "partner_id": [7, "Público En general"], "reconciled_bill_ids": []},
                   {"id": 81, "payment_type": "inbound", "partner_type": "customer", "memo": "Wansoft 2 - Efectivo",
                    "partner_id": [7, "Público En general"], "reconciled_bill_ids": []}],
            cuentas=cuentas)
        por = {(m.rubro, m.detalle): m.monto for m in movs}
        self.assertEqual(por[(fe.VENTAS, "Tarjeta de crédito")], D("700"))
        self.assertEqual(por[(fe.VENTAS, "Efectivo")], D("200"))
        self.assertEqual(por[(fe.POR_DEPOSITAR, "CxC BBVA")], D("100"))
        self.assertEqual(sum(m.monto for m in movs), D("1000"))  # the pieces add up to the bank line

    def test_pago_a_proveedor_por_cuenta_de_factura(self):
        movs = self._clasificar(
            [_banco(10, 1, -500)],
            movimientos=[{"id": 1, "move_type": "entry", "ref": "", "statement_line_id": False, "origin_payment_id": [90, ""]}],
            pagos=[{"id": 90, "payment_type": "outbound", "partner_type": "supplier", "memo": "", "partner_id": [8, "SIGMA"],
                    "reconciled_bill_ids": [60]}],
            lineas_factura=[{"move_id": [60, ""], "account_id": [3, "Goods Received - No Invoices"], "balance": 500, "display_type": "product"}],
            cuentas=[_cuenta(3, "115.01.01", "Goods Received - No Invoices")])
        self.assertEqual([(m.rubro, m.detalle, m.socio, m.monto) for m in movs],
                         [(fe.PROVEEDORES, "Insumos y mercancía", "SIGMA", D("-500"))])

    def test_traspaso_entre_bancos_suma_cero(self):
        movs = self._clasificar([_banco(10, 1, -300), _banco(11, 1, 300, cuenta=OTRO_BANCO)],
                                movimientos=[{"id": 1, "move_type": "entry", "ref": "", "statement_line_id": False, "origin_payment_id": False}])
        self.assertEqual({m.rubro for m in movs}, {fe.TRASPASOS})
        self.assertEqual(sum(m.monto for m in movs), 0)

    def test_linea_contra_pendiente_sin_conciliar_va_por_su_texto(self):
        movs = self._clasificar(
            [_banco(10, 1, -40)],
            movimientos=[{"id": 1, "move_type": "entry", "ref": "", "statement_line_id": [5, ""], "origin_payment_id": False}],
            extractos=[{"id": 5, "payment_ref": "REGISTRO DE COMISIONES BANCARIAS Y PLATAFORMAS SEP-26"}],
            contra=[_contra(20, 1, 1, "Pagos Pendientes 5734", 40)],
            cuentas=[_cuenta(1, "102.01.06P", "Pagos Pendientes 5734")])
        self.assertEqual([(m.rubro, m.monto) for m in movs], [(fe.COMISIONES, D("-40"))])

    def test_asiento_de_nomina(self):
        """Bank line matched to a payroll entry: the entry's other account decides."""
        movs = self._clasificar(
            [_banco(10, 1, -1000)],
            movimientos=[{"id": 1, "move_type": "entry", "ref": "", "statement_line_id": [5, ""], "origin_payment_id": False}],
            extractos=[{"id": 5, "payment_ref": "SPEI"}],
            contra=[_contra(20, 1, 1, "Pagos Pendientes", 1000, [71])],
            parciales=[{"id": 71, "debit_move_id": [20, ""], "credit_move_id": [30, ""], "amount": 1000}],
            otro_lado=[{"id": 30, "move_id": [3, ""], "account_id": [1, ""], "partner_id": False, "payment_id": False,
                        "statement_line_id": False, "move_type": "entry"}],
            lineas_asiento=[{"move_id": [3, ""], "account_id": [1, ""], "balance": -1000},
                            {"move_id": [3, ""], "account_id": [4, ""], "balance": 1000}],
            cuentas=[_cuenta(1, "102.01.05P", "Pagos Pendientes"), _cuenta(4, "210.01.01", "Provision of wages and salaries to pay")])
        self.assertEqual([(m.rubro, m.monto) for m in movs], [(fe.NOMINA, D("-1000"))])


class EmpresaTests(SimpleTestCase):
    def test_saldos_sin_caja_y_cuadre(self):
        cuentas = [{"company_id": ACOXPA, "account_id": BANCO, "codigo": "102.01.05", "cuenta": "BBVA 9168", "diario": "BBVA 9168"},
                   {"company_id": ACOXPA, "account_id": 200, "codigo": "101.01.03", "cuenta": "Caja Chica", "diario": None}]
        lineas = [_banco(1, 1, 1000, "2026-08-20"), _banco(2, 2, -300, "2026-09-05"),
                  {**_banco(3, 3, 50, "2026-08-01"), "account_id": [200, "Caja Chica"]}]
        movs = [fe.Movimiento(ACOXPA, date(2026, 9, 5), "BBVA 9168", fe.PROVEEDORES, "Insumos y mercancía", "SIGMA", D("-300"))]
        cxc = [{"company_id": [ACOXPA, ""], "date": "2026-08-31", "balance": 80}, {"company_id": [ACOXPA, ""], "date": "2026-09-30", "balance": 20}]
        e = fe.empresa(ACOXPA, "Acoxpa", fe.SUCURSAL, SEP, cuentas, lineas, movs, cxc)
        self.assertEqual((e.saldo_inicial, e.saldo_final), (D("1000"), D("700")))  # petty cash left out
        self.assertEqual(e.saldo_inicial + sum(m.monto for m in e.movimientos), e.saldo_final)
        self.assertEqual((e.por_depositar_inicial, e.por_depositar_final), (D("80"), D("100")))

    def test_depositos_son_ventas_mas_cambio_de_cxc(self):
        e = fe.FlujoEmpresa(ACOXPA, "Acoxpa", fe.SUCURSAL, SEP, movimientos=[
            fe.Movimiento(ACOXPA, date(2026, 9, 1), "b", fe.VENTAS, "Efectivo", "-", D("1000")),
            fe.Movimiento(ACOXPA, date(2026, 9, 30), "b", fe.POR_DEPOSITAR, "CxC Banorte", "-", D("-150"))])
        cifras = fe.ReporteFlujo.cifras([e])
        self.assertEqual(cifras["depositos"], D("850"))
        self.assertEqual(cifras["entradas"], D("850"))


def _reporte(periodo=SEP, consolidado=False, con_anterior=True):
    def emp(p, ventas):
        e = fe.FlujoEmpresa(ACOXPA, "Acoxpa", fe.SUCURSAL, p, cuentas=[fe.Cuenta(ACOXPA, "102.01.05", "BBVA 9168", D("1000"), D("1000") + ventas - 450)])
        e.movimientos = [fe.Movimiento(ACOXPA, p.desde, "BBVA 9168", fe.VENTAS, "Tarjeta de crédito", "Público", ventas),
                         fe.Movimiento(ACOXPA, p.desde, "BBVA 9168", fe.POR_DEPOSITAR, "CxC BBVA", "-", D("-50")),
                         fe.Movimiento(ACOXPA, p.hasta, "BBVA 9168", fe.PROVEEDORES, "Insumos y mercancía", "SIGMA", D("-300")),
                         fe.Movimiento(ACOXPA, p.hasta, "BBVA 9168", fe.RENTAS, fe.GRUPO_RENTAS, "FIDEICOMISO", D("-100"))]
        return e
    return fe.ReporteFlujo("Acoxpa", periodo, [emp(periodo, D("900"))], [emp(periodo.anterior(), D("800"))] if con_anterior else None,
                           consolidado)


class SalidasTests(SimpleTestCase):
    def test_estado_con_depositos_y_rentas(self):
        from .salidas import pdf_flujo
        f = {etiqueta: (a, b) for etiqueta, a, b, _ in pdf_flujo.filas(_reporte())}
        self.assertEqual(f["Depósitos de ventas"], (D("850"), D("750")))
        self.assertEqual(f[fe.ETIQUETAS[fe.RENTAS]], (D("-100"), D("-100")))
        self.assertEqual(f["Saldo final de bancos e inversiones"][0], D("1450"))
        self.assertIn("Se depositaron $850 de ventas", " ".join(pdf_flujo.lectura(_reporte())))

    def test_pdf_y_excel(self):
        import io as _io
        import openpyxl
        from .salidas import excel_flujo, pdf_flujo
        self.assertTrue(pdf_flujo.generar([_reporte(consolidado=True), _reporte(con_anterior=False)]).startswith(b"%PDF"))
        libro = openpyxl.load_workbook(_io.BytesIO(excel_flujo.generar([_reporte()])))
        self.assertEqual(libro.sheetnames, ["Flujo", "Cuentas", "Proveedores", "Movimientos", "Notas"])
        self.assertEqual(libro["Movimientos"].max_row, 3 + 4)
        self.assertEqual(pdf_flujo.nombre_archivo([_reporte()]), "Flujo_de_efectivo_Acoxpa_Septiembre_2026.pdf")

    def test_nota_de_cierre_solo_si_no_termina_en_fin_de_mes(self):
        semana = Periodo.semana_de(date(2026, 10, 28))
        self.assertIn(fe.NOTA_CIERRE, fe.notas_de(_reporte(semana)))
        self.assertNotIn(fe.NOTA_CIERRE, fe.notas_de(_reporte()))


class ArmarTests(SimpleTestCase):
    def test_alcance_y_notas(self):
        sucursales = [SimpleNamespace(nombre="Acoxpa", odoo_company_id=7), SimpleNamespace(nombre="Aeropuerto", odoo_company_id=None),
                      SimpleNamespace(nombre="Isabel La Católica", odoo_company_id=5)]
        with mock.patch.object(fe, "leer", side_effect=lambda empresas, periodo: (
                [fe.FlujoEmpresa(c, n, g, periodo) for c, n, g in empresas], [])) as leer:
            reportes = fe.armar(sucursales, SEP, consolidado=True)
        empresas = leer.call_args[0][0]
        self.assertEqual([e[0] for e in empresas], [7, 2, 3, 1])  # Isabel starts in October; corporate companies added
        notas = " ".join(reportes[0].notas)
        self.assertIn("Aeropuerto", notas)
        self.assertIn("Isabel La Católica (desde 01/10/2026)", notas)
        self.assertIsNone(reportes[0].anteriores)  # August is before the accounting start: no comparison

    def test_uno_por_empresa_sin_corporativo(self):
        with mock.patch.object(fe, "leer", side_effect=lambda empresas, periodo: (
                [fe.FlujoEmpresa(c, n, g, periodo) for c, n, g in empresas], [])):
            reportes = fe.armar([SimpleNamespace(nombre="Acoxpa", odoo_company_id=7)], SEP, False, incluir_corporativo=False)
        self.assertEqual([r.nombre for r in reportes], ["Acoxpa"])
