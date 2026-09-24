import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render

from cuentas.models import puede_generar, sucursales_de

from .forms import CONSOLIDADO, GenerarForm
from .generadores import GENERADORES, tiene_generador
from .models import Reporte

log = logging.getLogger(__name__)


def _visible(request, clave) -> Reporte:
    # Same visibility rule everywhere: a report you may not see is a 404,
    # not a 403, so its existence is not disclosed.
    return get_object_or_404(Reporte.visibles_para(request.user), clave=clave)


@login_required
def catalogo(request):
    return render(request, "central/catalogo.html", {"reportes": Reporte.visibles_para(request.user)})


@login_required
def detalle(request, clave):
    reporte = _visible(request, clave)
    generable = tiene_generador(clave) and puede_generar(request.user)
    return render(request, "central/detalle.html", {"reporte": reporte, "generable": generable})


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
    form = GenerarForm(request.POST or None, reporte=reporte, sucursales=sucursales)
    error = None
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            archivo = GENERADORES[clave](list(datos["sucursales"]), datos["periodo"], datos["modo"] == CONSOLIDADO)
        except Exception:  # a source down or a query over the time cap: tell the user, keep the details in the log
            log.exception("Report generation failed: %s", clave)
            error = "No se pudo generar el reporte (fuente de datos no disponible o consulta demasiado larga). Intenta de nuevo o con un periodo más corto."
        else:
            respuesta = HttpResponse(archivo.contenido, content_type=archivo.tipo)
            respuesta["Content-Disposition"] = f'attachment; filename="{archivo.nombre}"'
            return respuesta
    return render(request, "central/generar.html", {"reporte": reporte, "form": form, "error": error})
