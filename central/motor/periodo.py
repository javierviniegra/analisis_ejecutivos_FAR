"""Open-ended period: the user (or an automation) may pick any kind of period.

Rules (owner, 2026-09-24): the user chooses the kind of period; only the
*definition* of each kind is fixed here. Weeks are Monday-Sunday; months,
bimesters, quarters, semesters and years are calendar blocks; a range is
whatever dates the user picks. Automations use exactly one kind, defined
per automation.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from .periodos import (
    misma_semana_anio_anterior,
    numero_semana,
    semana_anterior,
    semana_lunes_domingo,
)

_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


class TipoPeriodo(str, Enum):
    SEMANA = "semana"
    MES = "mes"
    BIMESTRE = "bimestre"
    TRIMESTRE = "trimestre"
    SEMESTRE = "semestre"
    ANIO = "anio"
    RANGO = "rango"


# Calendar blocks: months per block. Weeks use ISO weeks; a range is free.
_MESES_POR_BLOQUE = {TipoPeriodo.MES: 1, TipoPeriodo.BIMESTRE: 2, TipoPeriodo.TRIMESTRE: 3, TipoPeriodo.SEMESTRE: 6}


def _ultimo_dia(anio: int, mes: int) -> date:
    return (date(anio + (mes == 12), mes % 12 + 1, 1)) - timedelta(days=1)


def _restar_un_anio(d: date) -> date:
    """Same calendar date one year earlier (Feb 29 -> Feb 28)."""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def _corto(d: date) -> str:
    return f"{d.day} {_MESES_ES[d.month - 1][:3]}"


@dataclass(frozen=True)
class Periodo:
    """A period reports are computed over: [desde, hasta], both included."""

    tipo: TipoPeriodo
    desde: date
    hasta: date

    def __post_init__(self):
        if self.desde > self.hasta:
            raise ValueError("desde must not be after hasta")

    # -- constructors -------------------------------------------------
    @classmethod
    def semana_de(cls, fecha: date) -> "Periodo":
        lunes, domingo = semana_lunes_domingo(fecha)
        return cls(TipoPeriodo.SEMANA, lunes, domingo)

    @classmethod
    def semana(cls, anio_iso: int, numero: int) -> "Periodo":
        lunes = date.fromisocalendar(anio_iso, numero, 1)  # ValueError if the week does not exist
        return cls(TipoPeriodo.SEMANA, lunes, lunes + timedelta(days=6))

    @classmethod
    def bloque(cls, tipo: TipoPeriodo, anio: int, indice: int) -> "Periodo":
        """`indice` is 1-based within the year (month 1-12, bimester 1-6, quarter 1-4, semester 1-2)."""
        m = _MESES_POR_BLOQUE[tipo]
        if not 1 <= indice <= 12 // m:
            raise ValueError(f"{tipo.value} index must be 1..{12 // m}")
        primero = (indice - 1) * m + 1
        return cls(tipo, date(anio, primero, 1), _ultimo_dia(anio, primero + m - 1))

    @classmethod
    def anio_completo(cls, anio: int) -> "Periodo":
        return cls(TipoPeriodo.ANIO, date(anio, 1, 1), date(anio, 12, 31))

    @classmethod
    def rango(cls, desde: date, hasta: date) -> "Periodo":
        return cls(TipoPeriodo.RANGO, desde, hasta)

    @classmethod
    def de_fecha(cls, tipo: TipoPeriodo, fecha: date) -> "Periodo":
        """The period of kind `tipo` that contains `fecha` (used by automations)."""
        if tipo == TipoPeriodo.SEMANA:
            return cls.semana_de(fecha)
        if tipo == TipoPeriodo.ANIO:
            return cls.anio_completo(fecha.year)
        if tipo == TipoPeriodo.RANGO:
            raise ValueError("a custom range has no natural period for a date")
        return cls.bloque(tipo, fecha.year, (fecha.month - 1) // _MESES_POR_BLOQUE[tipo] + 1)

    # -- properties ---------------------------------------------------
    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1

    def _indice_bloque(self) -> int:
        return (self.desde.month - 1) // _MESES_POR_BLOQUE[self.tipo] + 1

    # -- comparison periods -------------------------------------------
    def anterior(self) -> "Periodo":
        """The period immediately before: previous week/block/year; for a
        custom range, the equally long range ending the day before it starts."""
        if self.tipo == TipoPeriodo.SEMANA:
            return Periodo(self.tipo, *semana_anterior(self.desde))
        if self.tipo == TipoPeriodo.ANIO:
            return Periodo.anio_completo(self.desde.year - 1)
        if self.tipo == TipoPeriodo.RANGO:
            fin = self.desde - timedelta(days=1)
            return Periodo.rango(fin - timedelta(days=self.dias - 1), fin)
        bloques = 12 // _MESES_POR_BLOQUE[self.tipo]
        i = self._indice_bloque()
        if i > 1:
            return Periodo.bloque(self.tipo, self.desde.year, i - 1)
        return Periodo.bloque(self.tipo, self.desde.year - 1, bloques)

    def mismo_periodo_anio_anterior(self) -> "Periodo | None":
        """Same period one year earlier. Week: same ISO week number of the
        previous ISO year (None if that year has no such week). Calendar
        blocks/year: same block of the previous year. Range: same dates one
        year earlier."""
        if self.tipo == TipoPeriodo.SEMANA:
            previa = misma_semana_anio_anterior(self.desde)
            return None if previa is None else Periodo(self.tipo, *previa)
        if self.tipo == TipoPeriodo.ANIO:
            return Periodo.anio_completo(self.desde.year - 1)
        if self.tipo == TipoPeriodo.RANGO:
            return Periodo.rango(_restar_un_anio(self.desde), _restar_un_anio(self.hasta))
        return Periodo.bloque(self.tipo, self.desde.year - 1, self._indice_bloque())

    # -- presentation -------------------------------------------------
    def etiqueta(self) -> str:
        d, h = self.desde, self.hasta
        if self.tipo == TipoPeriodo.SEMANA:
            return f"Semana {numero_semana(d)[1]} · {_corto(d)} – {_corto(h)} {h.year}"
        if self.tipo == TipoPeriodo.MES:
            return f"{_MESES_ES[d.month - 1].capitalize()} {d.year}"
        if self.tipo == TipoPeriodo.ANIO:
            return f"Año {d.year}"
        if self.tipo == TipoPeriodo.RANGO:
            if d.year != h.year:
                return f"{_corto(d)} {d.year} – {_corto(h)} {h.year}"
            return f"{_corto(d)} – {_corto(h)} {h.year}"
        nombre = {TipoPeriodo.BIMESTRE: "Bimestre", TipoPeriodo.TRIMESTRE: "Trimestre", TipoPeriodo.SEMESTRE: "Semestre"}[self.tipo]
        return f"{nombre} {self._indice_bloque()} · {_MESES_ES[d.month - 1][:3]}–{_MESES_ES[h.month - 1][:3]} {d.year}"
