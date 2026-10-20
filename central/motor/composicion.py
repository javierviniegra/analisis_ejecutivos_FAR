"""Sales composition of the commercial report (owner, 2026-10-20; pure: no I/O):
sales by time band (morning / afternoon / night, by the hour the ticket
CLOSED), the share of each payment method and delivery platform, and sales
by weekday and by hour -- each against the same period last year over the
comparable branches.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from .comparativos import Variacion, variacion
from .graficas import Grafica
from .metricas import Comparacion, Metricas

CERO = Decimal("0")
# (label, hours shown, closing hours). Night runs past midnight (00:00-04:59 closes belong to it).
FRANJAS = [("Mañana", "antes de 13:00", range(5, 13)),
           ("Tarde", "13:00 a 18:00", range(13, 18)),
           ("Noche", "desde 18:00", list(range(18, 24)) + list(range(0, 5)))]
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
DIAS_LARGO = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
HORAS = list(range(8, 24)) + [0, 1]  # the bars: 8 am to 1 am, in service order

# Wansoft payment method -> group (names vary: "Uber Eats" / "Ubereats", two transfer spellings...).
_PAGO = {"efectivo": "Efectivo", "dolares": "Efectivo", "tarjeta de crédito": "Tarjeta de crédito",
         "tarjeta de débito": "Tarjeta de débito", "amex": "Amex", "clip": "Tarjeta de crédito",
         "transferencia de fondos": "Transferencia"}
_PLATAFORMA = {"uber eats": "Uber Eats", "ubereats": "Uber Eats", "rappi": "Rappi", "didi": "Didi",
               "didi food": "Didi"}
MAX_REBANADAS = 5  # more slices fold into "Otros"
# Fixed order of each donut (colour follows the category, never its size).
ORDEN_PAGOS = ["Tarjeta de crédito", "Tarjeta de débito", "Efectivo", "Amex", "Plataformas", "Transferencia"]
ORDEN_PLATAFORMAS = ["Uber Eats", "Rappi", "Didi"]


def grupo_pago(metodo: str) -> str:
    m = metodo.strip().lower()
    if m in _PLATAFORMA:
        return "Plataformas"
    return _PAGO.get(m, "Otros")


def _franja(m: Metricas | None, horas) -> dict[str, Decimal] | None:
    if m is None or not m.por_hora:
        return None
    suma = {"venta": CERO, "tickets": CERO, "clientes": CERO}
    for h in horas:
        for k in suma:
            suma[k] += m.por_hora.get(h, {}).get(k, CERO)
    return suma


@dataclass
class FilaFranja:
    etiqueta: str
    horario: str
    venta: Decimal
    tickets: Decimal
    clientes: Decimal
    pct: Decimal | None  # share of the period's sales
    var_anio: Variacion  # sales vs last year (comparable branches)

    @property
    def cheque(self) -> Decimal | None:
        return self.venta / self.clientes if self.clientes else None

    @property
    def ticket(self) -> Decimal | None:
        return self.venta / self.tickets if self.tickets else None


@dataclass
class FilaTarde:
    """Consolidated (owner, 2026-10-20): a branch's afternoon sales as a share of its gross sales."""
    sucursal: str
    venta_tarde: Decimal
    pct_manana: Decimal | None
    pct_tarde: Decimal | None
    pct_noche: Decimal | None
    pct_tarde_anio: Decimal | None  # its own share last year (None: no data then)
    pct_tarde_anterior: Decimal | None = None  # its own share in the previous period (month / week)

    @property
    def var_anio(self) -> Variacion:
        from .tabla_comercial import variacion_puntos
        return variacion_puntos(self.pct_tarde, self.pct_tarde_anio, mejor_si_sube=True)

    @property
    def var_anterior(self) -> Variacion:
        from .tabla_comercial import variacion_puntos
        return variacion_puntos(self.pct_tarde, self.pct_tarde_anterior, mejor_si_sube=True)


def _participacion(m: Metricas | None) -> tuple | None:
    """(morning, afternoon, night) share of the branch's sales, and its afternoon sales."""
    if m is None or not m.por_hora:
        return None
    total = sum((v["venta"] for v in m.por_hora.values()), CERO)
    if not total:
        return None
    ventas = [_franja(m, horas)["venta"] for _, _, horas in FRANJAS]
    return tuple(v / total for v in ventas) + (ventas[1],)


def tardes(por_sucursal, anteriores=None) -> list["FilaTarde"]:
    """Branches ranked by the share of their sales made in the afternoon
    (13:00-18:00 closes), each against its own share in the previous period
    (`anteriores`, same order) and last year."""
    filas = []
    for i, (nombre, actual, anio) in enumerate(por_sucursal):
        p = _participacion(actual)
        if p is None:
            continue
        y = _participacion(anio)
        a = _participacion(anteriores[i]) if anteriores else None
        filas.append(FilaTarde(nombre, p[3], p[0], p[1], p[2], y[1] if y else None, a[1] if a else None))
    return sorted(filas, key=lambda f: f.pct_tarde or CERO, reverse=True)


@dataclass
class FilaDia:
    """Branch report (owner, 2026-10-20): an average day of this weekday in the
    period (a month has 4 or 5 of each), split in the three bands."""
    dia: str
    dias: int  # how many of this weekday the period had (with sales)
    bandas: list[Decimal]  # morning, afternoon, night: average gross sales per day
    total_anterior: Decimal | None  # average day of this weekday in the previous period
    total_anio: Decimal | None  # ... and in the same period last year

    @property
    def total(self) -> Decimal:
        return sum(self.bandas, CERO)

    @property
    def pct_tarde(self) -> Decimal | None:
        return self.bandas[1] / self.total if self.total else None

    @property
    def var_anterior(self) -> Variacion:
        return variacion(self.total, self.total_anterior)

    @property
    def var_anio(self) -> Variacion:
        return variacion(self.total, self.total_anio)


def _promedios_dia(m: Metricas | None) -> dict[int, tuple[int, list[Decimal]]]:
    """weekday -> (days, average sales per band)."""
    if m is None or not m.venta_dia_hora:
        return {}
    suma: dict[int, list] = {}
    for dia, horas in m.venta_dia_hora.items():
        s = suma.setdefault(dia.weekday(), [0, [CERO, CERO, CERO]])
        s[0] += 1
        for i, (_, _, rango) in enumerate(FRANJAS):
            s[1][i] += sum((horas.get(h, CERO) for h in rango), CERO)
    return {d: (n, [v / n for v in bandas]) for d, (n, bandas) in suma.items()}


def dias_horario(actual: Metricas, anterior: Metricas | None, anio: Metricas | None) -> list[FilaDia]:
    """Monday to Sunday: an average day of each in the period, by band, against
    the average day of the same weekday in the previous period and last year."""
    a, p, y = _promedios_dia(actual), _promedios_dia(anterior), _promedios_dia(anio)
    filas = []
    for d in range(7):
        if d not in a:
            continue
        n, bandas = a[d]
        filas.append(FilaDia(DIAS_LARGO[d], n, bandas, sum(p[d][1], CERO) if d in p else None,
                             sum(y[d][1], CERO) if d in y else None))
    return filas


@dataclass
class Composicion:
    franjas: list[FilaFranja]
    pasteles: list[tuple[str, list[tuple[str, Decimal, int]]]] = field(default_factory=list)  # (title, slices)
    barras: list[Grafica] = field(default_factory=list)
    tardes: list[FilaTarde] = field(default_factory=list)  # consolidated only
    vs_anterior: str = "periodo ant."  # how the previous period is called in the table ("mes ant.", "sem. ant.")
    dias: list[FilaDia] = field(default_factory=list)  # branch report only

    @property
    def vacia(self) -> bool:
        return not any(f.venta for f in self.franjas)


def _rebanadas(valores: dict[str, Decimal], orden: list[str]) -> list[tuple[str, Decimal, int]]:
    """(name, value, colour slot) in the fixed `orden`; the categories past
    MAX_REBANADAS - 1 (by size), unknown ones and "Otros" fold into "Otros",
    last. The slot is the category's place in `orden`, so it keeps its colour."""
    presentes = [(k, valores[k]) for k in orden if valores.get(k, CERO) > 0]
    otros = sum((v for k, v in valores.items() if k not in orden), CERO)
    if len(presentes) > MAX_REBANADAS - (1 if otros > 0 else 0):
        quedan = {k for k, _ in sorted(presentes, key=lambda kv: kv[1], reverse=True)[:MAX_REBANADAS - 1]}
        otros += sum((v for k, v in presentes if k not in quedan), CERO)
        presentes = [(k, v) for k, v in presentes if k in quedan]
    return [(k, v, orden.index(k)) for k, v in presentes] + ([("Otros", otros, -1)] if otros > 0 else [])


def _por_dia_semana(m: Metricas | None) -> list[Decimal | None]:
    if m is None or not m.venta_por_dia:
        return [None] * 7
    suma = [CERO] * 7
    for dia, v in m.venta_por_dia.items():
        suma[dia.weekday()] += v
    return suma


def construir(actual: Metricas, anio: Comparacion, nombre_base: str) -> Composicion:
    """`anio`: the comparison against last year (comparable branches)."""
    total = sum((v["venta"] for v in actual.por_hora.values()), CERO)
    franjas = []
    for etiqueta, horario, horas in FRANJAS:
        f = _franja(actual, horas)
        a, b = _franja(anio.actual, horas), _franja(anio.base, horas)
        franjas.append(FilaFranja(etiqueta, horario, f["venta"] if f else CERO, f["tickets"] if f else CERO,
                                  f["clientes"] if f else CERO, (f["venta"] / total) if f and total else None,
                                  variacion(a["venta"] if a else None, b["venta"] if b else None)))
    pagos, plataformas = {}, {}
    for metodo, monto in actual.pagos.items():
        g = grupo_pago(metodo)
        pagos[g] = pagos.get(g, CERO) + monto
        if g == "Plataformas":
            p = _PLATAFORMA[metodo.strip().lower()]
            plataformas[p] = plataformas.get(p, CERO) + monto
    pasteles = [("Venta por horario", _rebanadas({f.etiqueta: f.venta for f in franjas}, [x[0] for x in FRANJAS])),
                ("Forma de pago", _rebanadas(pagos, ORDEN_PAGOS))]
    if plataformas:
        pasteles.append(("Plataformas", _rebanadas(plataformas, ORDEN_PLATAFORMAS)))
    nota = ("Sucursales comparables (sin " + ", ".join(anio.excluidas) + ")") if anio.excluidas and anio.base else \
        (None if anio.base else "Sin comparativo del año anterior")
    hora = lambda m, h: (m.por_hora.get(h, {}).get("venta", CERO) if m and m.por_hora else None)  # noqa: E731
    barras = [
        Grafica("Venta por día de la semana vs año anterior", DIAS, _por_dia_semana(anio.actual),
                _por_dia_semana(anio.base), "Periodo", nombre_base, nota),
        Grafica("Venta por hora de cierre vs año anterior", [f"{h}" for h in HORAS],
                [hora(anio.actual, h) for h in HORAS], [hora(anio.base, h) for h in HORAS], "Periodo", nombre_base, nota),
    ]
    return Composicion(franjas, pasteles, barras)
