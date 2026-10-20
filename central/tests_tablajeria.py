"""Butchery shrinkage of the commercial report (owner, 2026-10-20)."""

from datetime import date
from decimal import Decimal as D

from django.test import SimpleTestCase

from .motor import tablajeria as tb
from .motor.fuentes import wansoft

DIA = date(2026, 10, 4)  # a Sunday


class _Cursor:
    def __init__(self, filas):
        self.filas = filas

    def execute(self, sql, params):
        pass

    def fetchall(self):
        return self.filas


def _pieza(suc, producto, base, costo, merma, generado, fecha=DIA):
    return {"sucursal": suc, "fecha": fecha, "producto": producto, "base": D(base), "costo": D(costo),
            "merma": D(merma), "generado": D(generado)}


class PiezasTests(SimpleTestCase):
    def test_una_pieza_por_bloque_de_renglones(self):
        # one 2 kg loin repeated on its 3 generated products, then an IDENTICAL second loin
        lomo = (1, DIA, "Ana", "Lomo", D("2"), D("910"), D("0.2"))
        filas = [(1, *lomo, "Retazo", D("0.1")), (2, *lomo, "Lomo Limpio", D("1.2")), (3, *lomo, "Parrillada", D("0.5")),
                 (4, *lomo, "Retazo", D("0.1")), (5, *lomo, "Lomo Limpio", D("1.2")), (6, *lomo, "Parrillada", D("0.5"))]
        piezas = wansoft.piezas_tablajeria(_Cursor(filas), [1], DIA, DIA)
        self.assertEqual(len(piezas), 2)  # never 6 (the rows), never 1 (merging identical pieces)
        self.assertEqual(piezas[0]["generado"], D("1.8"))
        self.assertEqual(piezas[0]["base"], D("2"))


class TablajeriaTests(SimpleTestCase):
    NOMBRES = {1: "Acoxpa", 2: "Viaducto"}

    def _piezas(self):
        return [_pieza(1, "Lomo", 2, 900, "0.4", "1.6"), _pieza(1, "Arrachera", 4, 2000, 2, 2),
                _pieza(2, "Lomo", 2, 900, "0.2", "1.8"),
                _pieza(1, "Chorizo", 5, 1285, "4.68", 32), _pieza(2, "Chorizo", 5, 1285, "4.7", 30)]

    def test_porcionados_se_detectan_y_quedan_fuera_del_pct(self):
        self.assertEqual(tb.productos_porcionados(self._piezas()), {"Chorizo"})
        t = tb.construir(self._piezas(), [], self.NOMBRES, [1, 2], consolidado=True)
        acoxpa = next(f for f in t.filas if f.etiqueta == "Acoxpa")
        self.assertEqual((acoxpa.actual.base, acoxpa.actual.merma), (D(6), D("2.4")))  # no chorizo
        self.assertEqual(acoxpa.indice, D("0.4"))

    def test_consolidado_ordena_por_merma_y_compara_contra_el_grupo_y_el_anio(self):
        anio = [_pieza(1, "Lomo", 2, 900, "0.2", "1.8", date(2025, 10, 5))]
        t = tb.construir(self._piezas(), anio, self.NOMBRES, [1, 2], consolidado=True)
        self.assertEqual([f.etiqueta for f in t.filas], ["Acoxpa", "Viaducto"])  # 40% then 10%
        acoxpa, viaducto = t.filas
        self.assertEqual(t.total.indice, D("2.6") / D(8))  # group: 32.5%
        self.assertEqual(acoxpa.dif_grupo, D("0.4") - D("0.325"))
        self.assertEqual(acoxpa.var_anio.direccion, "sube")  # 10% -> 40%: worse
        self.assertEqual(acoxpa.var_anio.color, "rojo")
        self.assertIsNone(viaducto.indice_anio)  # no butchery last year: s/c, never 0

    def test_sucursal_compara_cada_producto_contra_todas(self):
        t = tb.construir(self._piezas(), [], self.NOMBRES, [1], consolidado=False)
        lomo = next(f for f in t.filas if f.etiqueta == "Lomo")
        self.assertEqual(lomo.indice, D("0.2"))
        self.assertEqual(lomo.indice_grupo, D("0.6") / D(4))  # both branches' loin: 15%
        self.assertEqual([f.etiqueta for f in t.porcionados], ["Chorizo"])
        self.assertEqual(t.porcionados[0].indice, D("6.4"))  # 32 pieces / 5 kg
        self.assertEqual([f.etiqueta for f in t.por_dia], ["Domingo"])

    def test_costo_de_la_merma_es_por_kg_de_la_pieza(self):
        t = tb.construir([_pieza(1, "Lomo", 2, 910, "0.2", "1.8")], [], self.NOMBRES, [1], consolidado=True)
        self.assertEqual(t.filas[0].actual.costo_merma, D("91"))  # 0.2 kg x $455/kg, not x $910

    def test_sucursal_sin_tablajeria(self):
        t = tb.construir(self._piezas(), [], {**self.NOMBRES, 3: "Puebla"}, [1, 2, 3], consolidado=True)
        self.assertEqual(t.sin_datos, ["Puebla"])
        self.assertTrue(any("Puebla" in n for n in tb.notas(t)))

    def test_esperado_segun_su_mezcla_de_cortes(self):
        # group: lomo 15% (0.6 / 4 kg), arrachera 50% (2 / 4). Acoxpa: 2 kg lomo + 4 kg arrachera
        t = tb.construir(self._piezas(), [], self.NOMBRES, [1, 2], consolidado=True)
        acoxpa, viaducto = t.filas
        self.assertEqual(acoxpa.esperado, (D(2) * D("0.15") + D(4) * D("0.5")) / D(6))  # 38.3%
        self.assertEqual(viaducto.esperado, D("0.15"))  # only loin
        self.assertEqual(viaducto.dif_esperado, D("0.1") - D("0.15"))  # better than its mix explains

    def test_back_rib_queda_fuera(self):
        piezas = self._piezas() + [_pieza(1, "Back Rib (Costillar)", 6, 900, 2, 4)]
        t = tb.construir(piezas, [], self.NOMBRES, [1], consolidado=False)
        self.assertNotIn("Back Rib (Costillar)", [f.etiqueta for f in t.filas])
        self.assertEqual(t.total.actual.base, D(6))  # lomo 2 + arrachera 4, no back rib
