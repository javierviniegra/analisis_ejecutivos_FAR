"""When an automation sends, and which period it sends (pure: no I/O).

An automation is bound to ONE period kind and always sends the last CLOSED
period of that kind, `dias_despues` days after it closes, at `hora`
(1 = the day after the close: Monday for a week, the 1st for a month).
"""

from datetime import datetime, time, timedelta

from .periodo import Periodo, TipoPeriodo

# Kinds an automation can use (a free range has no natural "last period").
TIPOS_AUTOMATIZABLES = [t for t in TipoPeriodo if t != TipoPeriodo.RANGO]
MAX_DIAS_DESPUES = {TipoPeriodo.SEMANA: 7}  # any other kind: up to 28 days after its close
MAX_DIAS_DESPUES_DEFAULT = 28


def max_dias_despues(tipo: TipoPeriodo) -> int:
    return MAX_DIAS_DESPUES.get(tipo, MAX_DIAS_DESPUES_DEFAULT)


def fecha_envio(periodo: Periodo, dias_despues: int, hora: time) -> datetime:
    return datetime.combine(periodo.hasta + timedelta(days=dias_despues), hora)


def periodo_a_enviar(tipo: TipoPeriodo, dias_despues: int, hora: time, ahora: datetime) -> Periodo:
    """The most recent closed period whose send time has arrived by `ahora`.
    (Whether it was already sent is the send log's business.)"""
    p = Periodo.de_fecha(tipo, ahora.date()).anterior()
    while fecha_envio(p, dias_despues, hora) > ahora:
        p = p.anterior()
    return p


def proximo_envio(tipo: TipoPeriodo, dias_despues: int, hora: time, ahora: datetime) -> tuple[Periodo, datetime]:
    """The next period to be sent after `ahora` and when (for the screen)."""
    p = periodo_a_enviar(tipo, dias_despues, hora, ahora)
    siguiente = Periodo.de_fecha(tipo, p.hasta + timedelta(days=1))
    return siguiente, fecha_envio(siguiente, dias_despues, hora)
