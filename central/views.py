import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from cuentas.models import Sucursal, puede_automatizar, puede_generar, sucursales_de

from . import envios, previas
from .forms import CONSOLIDADO, AutomatizacionForm, GenerarForm
from .generadores import GENERADORES, opciones_de, tiene_generador
from .models import Automatizacion, EnvioManual, Reporte
from .motor.fuentes import conexiones
from .motor.periodo import TipoPeriodo
from .motor.programacion import proximo_envio

log = logging.getLogger(__name__)


def _visible(request, clave) -> Reporte:
    # Same visibility rule everywhere: a report you may not see is a 404,
    # not a 403, so its existence is not disclosed.
    return get_object_or_404(Reporte.visibles_para(request.user), clave=clave)


@login_required
def catalogo(request):
    """The user's reports, filterable by category. Only the categories of the
    reports the user may see are offered (a user who sees one category gets
    no filter); a category the user cannot see is ignored, never disclosed."""
    visibles = Reporte.visibles_para(request.user)
    etiquetas = dict(Reporte.Categoria.choices)
    presentes = sorted(set(visibles.values_list("categoria", flat=True)), key=lambda c: etiquetas.get(c, c))
    categorias = [(c, etiquetas.get(c, c)) for c in presentes]
    elegida = request.GET.get("categoria")
    if elegida not in presentes:
        elegida = None
    reportes = visibles.filter(categoria=elegida) if elegida else visibles
    return render(request, "central/catalogo.html",
                  {"reportes": reportes, "categorias": categorias if len(categorias) > 1 else [], "elegida": elegida})


@login_required
def detalle(request, clave):
    reporte = _visible(request, clave)
    generable = tiene_generador(clave) and puede_generar(request.user)
    automatiza = generable and puede_automatizar(request.user)
    automatizaciones = []
    if automatiza:
        ahora = timezone.localtime().replace(tzinfo=None)
        activas = Sucursal.objects.filter(activa=True).prefetch_related("destinatarios")
        for a in reporte.automatizaciones.prefetch_related("consolidado_destinatarios", "particulares_destinatarios",
                                                           "sucursales"):
            periodo, cuando = proximo_envio(TipoPeriodo(a.tipo), a.dias_despues, a.hora, ahora)
            sin_destino = []
            if a.enviar_particulares and a.particulares_a_sucursal:
                elegidas = activas if a.todas_las_sucursales else a.sucursales.filter(activa=True)
                sin_destino = [s.nombre for s in elegidas if not s.correos and not s.destinatarios.all()]
            automatizaciones.append({"a": a, "proximo_periodo": periodo, "proximo": cuando,
                                     "ultimo": a.envios.first(), "sin_destino": sin_destino})
    return render(request, "central/detalle.html", {"reporte": reporte, "generable": generable,
                                                    "automatiza": automatiza, "automatizaciones": automatizaciones})


def _automatizable(request, clave) -> Reporte:
    """Same visibility rule as the report, plus a generator and the
    `gestionar_envios` permission (Director, Administrador general)."""
    reporte = _visible(request, clave)
    if not tiene_generador(clave):
        raise Http404
    if not puede_automatizar(request.user):
        raise PermissionDenied
    return reporte


@login_required
def automatizacion(request, clave, pk=None):
    """Create (pk None) or edit an automation of this report."""
    reporte = _automatizable(request, clave)
    instancia = get_object_or_404(Automatizacion, pk=pk, reporte=reporte) if pk else None
    usuarios = get_user_model().objects.filter(is_active=True).order_by("first_name", "username")
    inicial, origen = {}, None
    if instancia is None and request.GET.get("desde_envio", "").isdigit():
        origen = EnvioManual.objects.filter(pk=request.GET["desde_envio"], reporte=reporte).first()
        inicial = desde_envio(origen) if origen else {}
    form = AutomatizacionForm(request.POST or None, instance=instancia, reporte=reporte, initial=inicial,
                              sucursales=Sucursal.objects.filter(activa=True), usuarios=usuarios,
                              opciones=opciones_de(clave))
    if request.method == "POST" and form.is_valid():
        nueva = form.save(commit=False)
        if instancia is None:
            nueva.creada_por = request.user
        nueva.save()
        form.save_m2m()
        return redirect("reporte_detalle", clave=clave)
    return render(request, "central/automatizacion.html", {"reporte": reporte, "form": form, "instancia": instancia,
                                                           "origen": origen})


def desde_envio(envio: EnvioManual) -> dict:
    """Initial values of an automation that repeats a one-off e-mail: same
    branches, presentation, format, options, and the same people receiving
    every file (so per-branch files go to them, not to each branch's list).
    The user only picks how often and when."""
    p = envio.parametros or {}
    consolidado = p.get("modo") == "consolidado"
    correos = "\n".join(p.get("correos", []))
    tipo = p.get("tipo") if p.get("tipo") in Automatizacion.Tipo.values else Automatizacion.Tipo.SEMANA
    inicial = {"nombre": f"{envio.reporte.nombre} · {Automatizacion.Tipo(tipo).label.lower()}", "tipo": tipo,
               "titulo": p.get("titulo", ""),
               "todas_las_sucursales": False, "sucursales": p.get("sucursales", []),
               "enviar_consolidado": consolidado, "enviar_particulares": not consolidado,
               "formato": p.get("formato") or Automatizacion.Formato.PDF, "particulares_a_sucursal": False,
               "particulares_solo_sus_sucursales": False}
    if consolidado:
        inicial.update(consolidado_destinatarios=p.get("usuarios", []), consolidado_correos=correos)
    else:
        inicial.update(particulares_destinatarios=p.get("usuarios", []), particulares_correos=correos)
    for nombre, valor in (p.get("opciones") or {}).items():
        inicial[nombre] = valor
    return inicial


@login_required
@require_POST
def automatizacion_pausar(request, clave, pk):
    """Pause / resume (toggle `activa`)."""
    reporte = _automatizable(request, clave)
    a = get_object_or_404(Automatizacion, pk=pk, reporte=reporte)
    a.activa = not a.activa
    a.save(update_fields=["activa", "actualizada"])
    return redirect("reporte_detalle", clave=clave)


@login_required
def generar(request, clave):
    """On-demand generation: branches (only the user's), any period, per
    branch or consolidated as the report's scope allows; returns the file."""
    reporte = _visible(request, clave)
    if not tiene_generador(clave):
        raise Http404
    if not puede_generar(request.user):
        raise PermissionDenied
    sucursales = sucursales_de(request.user).filter(wansoft_subsidiary_id__isnull=False)
    usuarios = get_user_model().objects.filter(is_active=True).exclude(email="").order_by("first_name", "username")
    form = GenerarForm(request.POST or None, reporte=reporte, sucursales=sucursales, opciones=opciones_de(clave),
                       usuarios=usuarios)
    error = None
    por_correo = request.POST.get("accion") == "correo"
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            archivo = GENERADORES[clave](list(datos["sucursales"]), datos["periodo"],
                                         datos["modo"] == CONSOLIDADO, datos["separados"], datos["formatos"],
                                         datos["opciones"])
        except Exception:  # a source down or a query over the time cap: tell the user, keep the details in the log
            log.exception("Report generation failed: %s", clave)
            error = "No se pudo generar el reporte (fuente de datos no disponible o consulta demasiado larga). Intenta de nuevo o con un periodo más corto."
        else:
            if not por_correo:
                respuesta = HttpResponse(archivo.contenido, content_type=archivo.tipo)
                respuesta["Content-Disposition"] = f'attachment; filename="{archivo.nombre}"'
                return respuesta
            token = previas.guardar(request.user.pk, {
                "clave": clave, "periodo": datos["periodo"], "para": datos["para"], "mensaje": datos["mensaje"],
                "titulo": datos["titulo"], "adjuntos": envios.adjuntos_de(archivo),
                "parametros": {"tipo": datos["periodo"].tipo.value, "sucursales": [s.pk for s in datos["sucursales"]],
                               "modo": datos["modo"], "formato": request.POST.get("formato"),
                               "opciones": datos["opciones"],
                               "usuarios": [u.pk for u in datos["destinatarios"]],
                               "correos": datos["otros_correos"], "titulo": datos["titulo"]}})
            return redirect("correo_previa", clave=clave, token=token)
    envio = None
    if request.GET.get("envio", "").isdigit():
        envio = EnvioManual.objects.filter(pk=request.GET["envio"], usuario=request.user, reporte=reporte).first()
    return render(request, "central/generar.html", {"reporte": reporte, "form": form, "error": error,
                                                    "envio": envio, "automatiza": puede_automatizar(request.user),
                                                    "abrir_correo": por_correo,
                                                    "bases": conexiones.bases()})


def _previa(request, clave, token) -> tuple[Reporte, dict]:
    reporte = _visible(request, clave)
    if not puede_generar(request.user):
        raise PermissionDenied
    datos = previas.cargar(token, request.user.pk)
    if datos is None or datos["clave"] != clave:
        raise Http404  # expired, already sent, or someone else's
    return reporte, datos


@login_required
def correo_previa(request, clave, token):
    """Preview of a one-off e-mail (recipients, subject, text, attachments with
    the PDF shown); "Enviar" sends exactly that."""
    reporte, datos = _previa(request, clave, token)
    correo = envios.correo_manual(reporte, datos["periodo"], datos["adjuntos"], datos["para"], datos["mensaje"],
                                  datos.get("titulo", ""))
    error = None
    if request.method == "POST":
        try:
            envio = envios.enviar_manual(request.user, reporte, datos["periodo"], datos["adjuntos"], datos["para"],
                                         datos["mensaje"], datos.get("parametros"), datos.get("titulo", ""))
        except Exception:
            log.exception("Manual e-mail failed: %s", clave)
            error = "No se pudo enviar el correo. Revisa la configuración de correo e intenta de nuevo."
        else:
            previas.borrar(token)
            return redirect(f"{reverse('reporte_generar', args=[clave])}?envio={envio.pk}")
    adjuntos = [{"n": i, "nombre": n, "pdf": t == "application/pdf", "kb": len(c) // 1024 or 1}
                for i, (n, c, t) in enumerate(datos["adjuntos"])]
    return render(request, "central/correo_previa.html", {
        "reporte": reporte, "token": token, "correo": correo, "adjuntos": adjuntos, "error": error,
        "primer_pdf": next((a for a in adjuntos if a["pdf"]), None)})


@login_required
@xframe_options_sameorigin  # shown inside the preview page (the default DENY left the viewer blank)
def correo_adjunto(request, clave, token, n):
    """One attachment of a preview: a PDF opens in the browser, anything else downloads."""
    _, datos = _previa(request, clave, token)
    if not 0 <= n < len(datos["adjuntos"]):
        raise Http404
    nombre, contenido, tipo = datos["adjuntos"][n]
    respuesta = HttpResponse(contenido, content_type=tipo)
    modo = "inline" if tipo == "application/pdf" else "attachment"
    respuesta["Content-Disposition"] = f'{modo}; filename="{nombre}"'
    return respuesta
