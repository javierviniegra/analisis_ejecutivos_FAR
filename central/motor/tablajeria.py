"""Butchery shrinkage (tablajería) of the commercial report (owner, 2026-10-20;
pure: no I/O). What matters most to the owner in this report: how much of
each base piece is lost, compared against every other branch and against
the same period last year.

Rules (each one checked against Wansoft's rows, Acoxpa 2026-10-04):
- One piece counted ONCE (see fuentes.wansoft.piezas_tablajeria): the Power
  BI table sums Wansoft's rows, which repeat the piece once per generated
  product (that day: 336 kg instead of 178 kg of base product).
- % merma = shrinkage kg / base kg.
- Cost of the shrinkage = shrinkage kg x the piece's cost PER KG (Wansoft's
  ProductBaseCost is the cost of the whole piece).
- Portioned products (chorizo, salmon...: Wansoft counts what they generate
  in pieces, not kg) have no meaningful shrinkage: they are shown apart in
  pieces per kg and left out of every % merma and every total.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from .comparativos import Variacion, variacion
from .tabla_comercial import variacion_puntos

CERO = Decimal("0")
# A piece that "generates" more than its own weight is counted in pieces.
FACTOR_PORCIONADO = Decimal("1.02")
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
KG, PIEZAS = "kg", "pzas"


@dataclass
class Acumulado:
    piezas: int = 0
    base: Decimal = CERO
    merma: Decimal = CERO
    generado: Decimal = CERO
    costo: Decimal = CERO
    costo_merma: Decimal = CERO

    def sumar(self, p: dict) -> None:
        self.piezas += 1
        self.base += p["base"]
        self.merma += p["merma"]
        self.generado += p["generado"]
        self.costo += p["costo"]
        if p["base"]:
            self.costo_merma += p["merma"] * p["costo"] / p["base"]

    @property
    def pct_merma(self) -> Decimal | None:
        return self.merma / self.base if self.base else None

    @property
    def por_kg(self) -> Decimal | None:
        """Pieces generated per kg of base product (portioned products)."""
        return self.generado / self.base if self.base else None


@dataclass
class FilaTablajeria:
    etiqueta: str
    unidad: str  # KG or PIEZAS (what the generated products are counted in)
    actual: Acumulado
    anio: Acumulado | None  # same period last year (None: no data then)
    grupo: Acumulado | None  # the same product / all branches, for comparison
    total: bool = False
    # Consolidated (owner, 2026-10-20): the % this branch would lose with ITS mix of
    # cuts if each cut lost what the group loses on it (mollejas lose ~50%, rib eye ~8%).
    esperado: Decimal | None = None

    @property
    def dif_esperado(self) -> Decimal | None:
        """Points above (+: loses more than its mix explains) or below the expected %."""
        if self.esperado is None or self.indice is None:
            return None
        return self.indice - self.esperado

    @property
    def porcionado(self) -> bool:
        return self.unidad == PIEZAS

    @property
    def indice(self) -> Decimal | None:
        """% merma (kg products) or pieces per kg (portioned)."""
        return self.actual.por_kg if self.porcionado else self.actual.pct_merma

    @property
    def indice_anio(self) -> Decimal | None:
        if self.anio is None:
            return None
        return self.anio.por_kg if self.porcionado else self.anio.pct_merma

    @property
    def indice_grupo(self) -> Decimal | None:
        if self.grupo is None:
            return None
        return self.grupo.por_kg if self.porcionado else self.grupo.pct_merma

    @property
    def var_anio(self) -> Variacion:
        """Against last year: % merma in points (up = bad), pieces per kg relative (up = good)."""
        if self.porcionado:
            return variacion(self.indice, self.indice_anio, mejor_si_sube=True)
        return variacion_puntos(self.indice, self.indice_anio, mejor_si_sube=False)

    @property
    def dif_grupo(self) -> Decimal | None:
        """Points above (+) or below (-) the group's % merma."""
        if self.porcionado or self.indice is None or self.indice_grupo is None:
            return None
        return self.indice - self.indice_grupo


@dataclass
class Tablajeria:
    consolidado: bool
    filas: list[FilaTablajeria]  # consolidated: one per branch; branch: one per base product
    total: FilaTablajeria | None
    por_dia: list[FilaTablajeria] = field(default_factory=list)  # branch only: per day of the week
    porcionados: list[FilaTablajeria] = field(default_factory=list)  # branch only: in pieces per kg
    sin_datos: list[str] = field(default_factory=list)  # branches of the selection without butchery rows
    incluir_costos: bool = True

    @property
    def vacia(self) -> bool:
        return not self.filas and not self.porcionados


def productos_porcionados(*listas: list[dict]) -> set[str]:
    """Base products whose pieces mostly generate more than their own weight."""
    votos = defaultdict(lambda: [0, 0])
    for piezas in listas:
        for p in piezas:
            v = votos[p["producto"]]
            v[0] += p["generado"] > p["base"] * FACTOR_PORCIONADO
            v[1] += 1
    return {prod for prod, (pz, n) in votos.items() if pz * 2 > n}


def _acumular(piezas, clave) -> dict:
    por = defaultdict(Acumulado)
    for p in piezas:
        por[clave(p)].sumar(p)
    return por


def _total(piezas) -> Acumulado | None:
    if not piezas:
        return None
    t = Acumulado()
    for p in piezas:
        t.sumar(p)
    return t


def construir(actual: list[dict], anio: list[dict] | None, nombres: dict[int, str], seleccion: list[int],
              consolidado: bool, incluir_costos: bool = True) -> Tablajeria:
    """`actual` / `anio`: the pieces of EVERY branch (the comparison is
    against all of them) for the period and the same period last year;
    `nombres`: subsidiary_id -> branch name; `seleccion`: the report's branches."""
    anio = anio or []
    porc = productos_porcionados(actual, anio)

    def kg(piezas):
        return [p for p in piezas if p["producto"] not in porc]

    sel = set(seleccion)
    act_sel, anio_sel = [p for p in actual if p["sucursal"] in sel], [p for p in anio if p["sucursal"] in sel]
    con_datos = {p["sucursal"] for p in act_sel}
    sin_datos = [nombres[s] for s in seleccion if s not in con_datos]

    if consolidado:
        a, y = _acumular(kg(act_sel), lambda p: p["sucursal"]), _acumular(kg(anio_sel), lambda p: p["sucursal"])
        grupo = _total(kg(act_sel))
        pct_corte = {prod: acc.pct_merma for prod, acc in _acumular(kg(act_sel), lambda p: p["producto"]).items()}
        mezcla = _acumular(kg(act_sel), lambda p: (p["sucursal"], p["producto"]))

        def esperado(s):
            base = sum((acc.base for (suc, _), acc in mezcla.items() if suc == s), CERO)
            perdida = sum((acc.base * (pct_corte[prod] or CERO) for (suc, prod), acc in mezcla.items() if suc == s), CERO)
            return perdida / base if base else None

        filas = [FilaTablajeria(nombres[s], KG, a[s], y.get(s), grupo, esperado=esperado(s)) for s in a]
        filas.sort(key=lambda f: f.indice or CERO, reverse=True)  # the one that loses the most first
        total = FilaTablajeria("Total", KG, grupo, _total(kg(anio_sel)), None, total=True) if grupo else None
        return Tablajeria(True, filas, total, sin_datos=sin_datos, incluir_costos=incluir_costos)

    a = _acumular(act_sel, lambda p: p["producto"])
    y = _acumular(anio_sel, lambda p: p["producto"])
    g = _acumular(actual, lambda p: p["producto"])  # every branch: the benchmark of each product
    filas = [FilaTablajeria(prod, KG, a[prod], y.get(prod), g[prod]) for prod in a if prod not in porc]
    filas.sort(key=lambda f: f.indice or CERO, reverse=True)
    porcionados = sorted((FilaTablajeria(prod, PIEZAS, a[prod], y.get(prod), g[prod]) for prod in a if prod in porc),
                         key=lambda f: f.actual.base, reverse=True)
    actual_kg = _total(kg(act_sel))
    total = FilaTablajeria("Total", KG, actual_kg, _total(kg(anio_sel)), _total(kg(actual)), total=True) \
        if actual_kg else None
    dia = _acumular(kg(act_sel), lambda p: p["fecha"].weekday())
    dia_y = _acumular(kg(anio_sel), lambda p: p["fecha"].weekday())
    por_dia = [FilaTablajeria(DIAS[d], KG, dia[d], dia_y.get(d), actual_kg) for d in range(7) if d in dia]
    return Tablajeria(False, filas, total, por_dia, porcionados, sin_datos, incluir_costos)


def notas(t: Tablajeria) -> list[str]:
    """Footnotes of the butchery section (they explain its figures)."""
    n = ["Tablajería: cada pieza se cuenta una vez (Wansoft repite la pieza en cada producto que genera; "
         "sumar sus renglones, como el Power BI, la cuenta dos o tres veces). % merma = kg de merma / kg de base."]
    if t.incluir_costos:
        n.append("$ merma = costo de la merma = kg de merma x costo por kg de la pieza (el costo de Wansoft es el de la pieza "
                 "completa).")
    n.append("Productos porcionados (lo que generan se cuenta en piezas: chorizo, salmón…): van aparte en piezas "
             "por kg y quedan fuera del % de merma y de los totales.")
    if not t.consolidado:
        n.append("Grupo = el mismo producto en todas las sucursales con tablajería en el periodo.")
    else:
        n.append("% esperado = la merma que tendría la sucursal con su misma mezcla de cortes si cada corte mermara lo "
                 "que merma en el grupo (el grupo = las sucursales del consolidado).")
    if t.sin_datos:
        n.append("Sin tablajería en Wansoft en el periodo: " + ", ".join(t.sin_datos) + ".")
    return n


# One line under each table explaining its columns (owner, 2026-10-20).
LEYENDA_SUCURSALES = ("Merma en kg. Esperado: el % que mermaría la sucursal con sus mismos cortes si cada uno mermara como en el grupo. "
                      "Vs esp. en rojo = merma más de lo que explica su mezcla (tablajea peor); en verde = menos. "
                      "Var.: contra el año anterior, ▲ rojo = mermó más. Vs grupo: puntos contra el % del consolidado.")
LEYENDA_PRODUCTOS = ("% grupo: el mismo producto en todas las sucursales. Vs grupo en rojo = merma 1 punto o más arriba "
                     "del grupo; en verde = 1 punto o más abajo. Var.: contra el año anterior, ▲ rojo = mermó más.")
LEYENDA_PORCIONADOS = "Piezas que salen por cada kg de base: más piezas por kg = mejor aprovechamiento."
LEYENDA_DIAS = "Vs su prom.: puntos contra el % de merma de la sucursal en todo el periodo."
