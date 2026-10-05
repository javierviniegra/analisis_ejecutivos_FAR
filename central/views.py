import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas.models import Sucursal, puede_automatizar, puede_generar, sucursales_de

from .forms import CONSOLIDADO, AutomatizacionForm, GenerarForm
from .generadores import GENERADORES, opciones_de, tiene_generador
from .models import Automatizacion, Reporte
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
    form = AutomatizacionForm(request.POST or None, instance=instancia, reporte=reporte,
                              sucursales=Sucursal.objects.filter(activa=True), usuarios=usuarios,
                              opciones=opciones_de(clave))
    if request.method == "POST" and form.is_valid():
        nueva = form.save(commit=False)
        if instancia is None:
            nueva.creada_por = request.user
        nueva.save()
        form.save_m2m()
        return redirect("reporte_detalle", clave=clave)
    return render(request, "central/automatizacion.html", {"reporte": reporte, "form": form, "instancia": instancia})


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
    form = GenerarForm(request.POST or None, reporte=reporte, sucursales=sucursales, opciones=opciones_de(clave))
    error = None
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
            respuesta = HttpResponse(archivo.contenido, content_type=archivo.tipo)
            respuesta["Content-Disposition"] = f'attachment; filename="{archivo.nombre}"'
            return respuesta
    return render(request, "central/generar.html", {"reporte": reporte, "form": form, "error": error,
                                                    "bases": conexiones.bases()})
