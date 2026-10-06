"""Automations dispatcher (Phase 5): which automations are due, who receives
what, the e-mails and the send log.

`despachar` is what the scheduled command runs every few minutes: for each
active automation, the last closed period whose send time has arrived is
sent once (the log `EnvioAutomatico` says whether it already was). Each
recipient gets ONE e-mail with all the files that are theirs:

- consolidated: the automation's consolidated recipients;
- per branch: each branch's default recipients (`cuentas.Sucursal`) get that
  branch's files; added users get the branches of their profile (or all, if
  so set); added outside e-mails get every branch.

A failed send is retried on the next runs (up to MAX_INTENTOS) and only to the
recipients that did not get it, so nobody receives the same report twice.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.utils import timezone

from cuentas.models import Sucursal, sucursales_de

from .generadores import EXCEL, GRUPOS, PDF, GrupoArchivos
from .models import Automatizacion, EnvioAutomatico
from .motor.periodo import Periodo, TipoPeriodo
from .motor.programacion import fecha_envio, periodo_a_enviar

log = logging.getLogger(__name__)

MAX_INTENTOS = 3
OK, FALLO = "ok", "error"

# Texts every e-mail carries (owner, 2026-10-06): sent by the organisation
# (never a person's name), the sending mailbox is not read, questions go to
# the contact team -- replies are routed to it when its address is set.
def _contacto() -> str:
    nombre, correo = settings.CORREO_CONTACTO_NOMBRE, settings.CORREO_CONTACTO
    return f"{nombre} ({correo})" if correo else nombre


def aviso_no_responder() -> str:
    return (f"Este es un correo automático de {settings.CORREO_REMITENTE}: no respondas a esta cuenta, no se "
            f"revisa. Si tienes dudas, comunícate con {_contacto()}.")


def pie_no_responder() -> str:
    return (f"NO RESPONDER: los mensajes enviados a esta dirección no se leen ni se atienden. Para dudas o "
            f"aclaraciones, comunícate con {_contacto()}.")


def disclaimer() -> str:
    return (f"AVISO DE CONFIDENCIALIDAD: Este correo y sus archivos adjuntos contienen información confidencial "
            f"de {settings.CORREO_REMITENTE}, para uso exclusivo de sus destinatarios. Si lo recibiste por error, "
            f"avísalo a {settings.CORREO_CONTACTO_NOMBRE} y elimínalo; queda prohibida su copia, distribución o "
            "uso sin autorización.")


def _cuerpo(texto: str) -> str:
    return (f"{aviso_no_responder()}\n\n{texto}\n\n"
            f"{'-' * 60}\n{pie_no_responder()}\n\n{disclaimer()}\n")


def _correo(asunto: str, cuerpo: str, para: list[str], conexion=None) -> EmailMessage:
    """Every e-mail of this app: replies to the contact team (if set), never to
    the unread sending mailbox; Auto-Submitted keeps out-of-office replies away."""
    asunto = f"{settings.CORREO_PREFIJO_ASUNTO} {asunto}".strip()
    return EmailMessage(asunto, cuerpo, to=para, connection=conexion,
                        reply_to=[settings.CORREO_CONTACTO] if settings.CORREO_CONTACTO else None,
                        headers={"Auto-Submitted": "auto-generated"})


def ahora_local() -> datetime:
    return timezone.localtime().replace(tzinfo=None)


def sucursales_de_automatizacion(a: Automatizacion) -> list[Sucursal]:
    """Active branches with sales data: all of them (new ones included) or the chosen ones."""
    qs = Sucursal.objects.filter(activa=True, wansoft_subsidiary_id__isnull=False)
    if not a.todas_las_sucursales:
        qs = qs.filter(pk__in=a.sucursales.values("pk"))
    return list(qs.prefetch_related("destinatarios"))


# -- recipients -----------------------------------------------------------------
def destinatarios_consolidado(a: Automatizacion) -> list[str]:
    correos = [u.email for u in a.consolidado_destinatarios.filter(is_active=True) if u.email]
    return list(dict.fromkeys(correos + a.correos_consolidado))


def destinatarios_particulares(a: Automatizacion, sucursales: list[Sucursal]) -> dict[str, list[int]]:
    """E-mail -> ids of the branches whose report that e-mail receives."""
    ids = [s.pk for s in sucursales]
    reparto: dict[str, list[int]] = {}

    def dar(correo, sucursales_ids):
        actuales = reparto.setdefault(correo, [])
        actuales += [i for i in sucursales_ids if i not in actuales]

    if a.particulares_a_sucursal:
        for s in sucursales:
            for u in s.destinatarios.all():
                if u.is_active and u.email:
                    dar(u.email, [s.pk])
            for correo in s.correos:
                dar(correo, [s.pk])
    for u in a.particulares_destinatarios.filter(is_active=True):
        if not u.email:
            continue
        if a.particulares_solo_sus_sucursales:
            suyas = set(sucursales_de(u).values_list("pk", flat=True))
            dar(u.email, [i for i in ids if i in suyas])
        else:
            dar(u.email, ids)
    for correo in a.correos_particulares:
        dar(correo, ids)
    return {c: v for c, v in reparto.items() if v}


@dataclass
class Correo:
    para: str
    archivos: list[tuple[str, bytes, str]] = field(default_factory=list)


def armar_correos(a: Automatizacion, consolidado: GrupoArchivos | None, particulares: list[GrupoArchivos],
                  sucursales: list[Sucursal]) -> list[Correo]:
    """One e-mail per recipient with every file that is theirs, consolidated first."""
    correos: dict[str, Correo] = {}
    if consolidado is not None:
        for c in destinatarios_consolidado(a):
            correos.setdefault(c, Correo(c)).archivos += consolidado.archivos
    if particulares:
        por_sucursal = {g.sucursal.pk: g.archivos for g in particulares}
        for c, ids in destinatarios_particulares(a, sucursales).items():
            for i in ids:
                correos.setdefault(c, Correo(c)).archivos += por_sucursal.get(i, [])
    return [c for c in correos.values() if c.archivos]


def _mensaje(a: Automatizacion, periodo: Periodo, correo: Correo, conexion) -> EmailMessage:
    lista = "\n".join(f"  - {nombre}" for nombre, _, _ in correo.archivos)
    titulo = a.titulo.strip() or a.reporte.nombre
    cuerpo = _cuerpo(f"Hola,\n\n{settings.CORREO_REMITENTE} te comparte «{titulo}», {periodo.etiqueta()} "
                     f"(del {periodo.desde:%d/%m/%Y} al {periodo.hasta:%d/%m/%Y}).\n\nArchivos adjuntos:\n{lista}")
    mensaje = _correo(f"{titulo} · {periodo.etiqueta()}", cuerpo, [correo.para], conexion)
    for nombre, contenido, tipo in correo.archivos:
        mensaje.attach(nombre, contenido, tipo)
    return mensaje


# -- one send ---------------------------------------------------------------------
def _formatos(a: Automatizacion) -> set[str]:
    return {PDF, EXCEL} if a.formato == Automatizacion.Formato.AMBOS else {a.formato}


def ejecutar(a: Automatizacion, periodo: Periodo,
             ya_enviados: set[str] | None = None) -> tuple[str, list[str], list[str], str]:
    """Generate and send one automation for one period, skipping the
    recipients in `ya_enviados`. Returns (state, lines per recipient
    "ok x" / "error x: why", file names, error); the log is the caller's."""
    ya_enviados = ya_enviados or set()
    sucursales = sucursales_de_automatizacion(a)
    grupos = GRUPOS[a.reporte.clave]
    consolidado = grupos(sucursales, periodo, True, _formatos(a), a.opciones)[0] if a.enviar_consolidado else None
    particulares = grupos(sucursales, periodo, False, _formatos(a), a.opciones) if a.enviar_particulares else []
    correos = [c for c in armar_correos(a, consolidado, particulares, sucursales) if c.para not in ya_enviados]
    archivos = sorted({n for c in correos for n, _, _ in c.archivos})
    lineas, errores = [f"{OK} {c}" for c in sorted(ya_enviados)], []
    if not correos and not ya_enviados:
        return EnvioAutomatico.Estado.SIN_DESTINATARIOS, [], archivos, "Nadie tiene correo para recibir este envío."
    conexion = get_connection()
    for c in correos:
        try:
            _mensaje(a, periodo, c, conexion).send()
            lineas.append(f"{OK} {c.para}")
        except Exception as e:  # one bad address or a server hiccup must not stop the others
            log.exception("Envío fallido a %s (automatización %s)", c.para, a.pk)
            lineas.append(f"{FALLO} {c.para}: {e}")
            errores.append(f"{c.para}: {e}")
    estado = EnvioAutomatico.Estado.ERROR if errores else EnvioAutomatico.Estado.ENVIADO
    return estado, lineas, archivos, "\n".join(errores)


def _registrar(a, periodo, programado, estado, lineas, archivos, error) -> EnvioAutomatico:
    envio, _ = EnvioAutomatico.objects.get_or_create(
        automatizacion=a, desde=periodo.desde,
        defaults={"hasta": periodo.hasta, "programado_para": timezone.make_aware(programado), "estado": estado})
    envio.hasta, envio.estado = periodo.hasta, estado
    envio.destinatarios, envio.archivos, envio.error = "\n".join(lineas), "\n".join(archivos), error
    envio.intentos += 1
    if estado == EnvioAutomatico.Estado.ENVIADO:
        envio.enviado_en = timezone.now()
    envio.save()
    return envio


def _ya_enviados(envio: EnvioAutomatico | None) -> set[str]:
    if envio is None:
        return set()
    return {linea[len(OK) + 1:] for linea in envio.destinatarios.splitlines() if linea.startswith(OK + " ")}


# -- what is due ----------------------------------------------------------------------
def pendientes(ahora: datetime) -> list[tuple[Automatizacion, Periodo, datetime, EnvioAutomatico | None]]:
    """Active automations whose last closed period is due and not sent yet. A
    period due before the automation was created is never sent (creating one
    must not mail old periods), and a failing one stops after MAX_INTENTOS."""
    salida = []
    for a in Automatizacion.objects.filter(activa=True, reporte__activo=True).select_related("reporte"):
        if a.reporte.clave not in GRUPOS:
            continue
        tipo = TipoPeriodo(a.tipo)
        periodo = periodo_a_enviar(tipo, a.dias_despues, a.hora, ahora)
        programado = fecha_envio(periodo, a.dias_despues, a.hora)
        if programado < timezone.localtime(a.creada).replace(tzinfo=None):
            continue
        envio = a.envios.filter(desde=periodo.desde).first()
        if envio and (envio.estado != EnvioAutomatico.Estado.ERROR or envio.intentos >= MAX_INTENTOS):
            continue
        salida.append((a, periodo, programado, envio))
    return salida


def despachar(ahora: datetime | None = None) -> list[EnvioAutomatico]:
    hechos = []
    for a, periodo, programado, envio in pendientes(ahora or ahora_local()):
        ya = _ya_enviados(envio)
        try:
            resultado = ejecutar(a, periodo, ya_enviados=ya)
        except Exception as e:  # a source down: logged, retried next run
            log.exception("Automatización %s falló al generar %s", a.pk, periodo.etiqueta())
            resultado = (EnvioAutomatico.Estado.ERROR, [f"{OK} {c}" for c in sorted(ya)], [],
                         f"No se pudo generar el reporte: {e}")
        hechos.append(_registrar(a, periodo, programado, *resultado))
    return hechos


# -- "Enviar por correo" from the generation screen ---------------------------------
def adjuntos_de(archivo) -> list[tuple[str, bytes, str]]:
    """The generated file as attachments: a .zip (several files) is opened so
    each PDF / Excel arrives on its own."""
    import io
    import mimetypes
    import zipfile

    if archivo.tipo != "application/zip":
        return [(archivo.nombre, archivo.contenido, archivo.tipo)]
    with zipfile.ZipFile(io.BytesIO(archivo.contenido)) as z:
        return [(n, z.read(n), mimetypes.guess_type(n)[0] or "application/octet-stream") for n in z.namelist()]


def correo_manual(reporte, periodo: Periodo, adjuntos: list[tuple[str, bytes, str]], para: list[str],
                  mensaje: str = "", titulo: str = "") -> EmailMessage:
    """The e-mail of a one-off send, exactly as it will leave (the preview shows
    this same object). Sent in the organisation's name, not the user's."""
    lista = "\n".join(f"  - {n}" for n, _, _ in adjuntos)
    titulo = (titulo or "").strip() or reporte.nombre
    cuerpo = _cuerpo(f"Hola,\n\n{settings.CORREO_REMITENTE} te comparte «{titulo}», {periodo.etiqueta()} "
                     f"(del {periodo.desde:%d/%m/%Y} al {periodo.hasta:%d/%m/%Y}).\n\n"
                     + (f"{mensaje.strip()}\n\n" if mensaje.strip() else "")
                     + f"Archivos adjuntos:\n{lista}")
    correo = _correo(f"{titulo} · {periodo.etiqueta()}", cuerpo, para)
    for nombre, contenido, tipo in adjuntos:
        correo.attach(nombre, contenido, tipo)
    return correo


def enviar_manual(usuario, reporte, periodo: Periodo, adjuntos: list[tuple[str, bytes, str]], para: list[str],
                  mensaje: str = "", parametros: dict | None = None, titulo: str = ""):
    """Send a previewed one-off e-mail and keep it in the audit log (with what
    was chosen, so it can be turned into an automation)."""
    from .models import EnvioManual

    correo = correo_manual(reporte, periodo, adjuntos, para, mensaje, titulo)
    registro = EnvioManual(usuario=usuario, reporte=reporte, periodo=periodo.etiqueta(), desde=periodo.desde,
                           hasta=periodo.hasta, destinatarios="\n".join(para),
                           archivos="\n".join(n for n, _, _ in adjuntos), mensaje=mensaje,
                           parametros=parametros or {})
    try:
        correo.send()
    except Exception as e:
        registro.error = str(e)
        registro.save()
        raise
    registro.save()
    return registro
