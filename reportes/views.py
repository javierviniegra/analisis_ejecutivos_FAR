from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .models import Reporte


@login_required
def catalogo(request):
    return render(request, "reportes/catalogo.html", {"reportes": Reporte.visibles_para(request.user)})


@login_required
def detalle(request, clave):
    # Same visibility rule as the list: a report you may not see is a 404,
    # not a 403, so its existence is not disclosed.
    reporte = get_object_or_404(Reporte.visibles_para(request.user), clave=clave)
    return render(request, "reportes/detalle.html", {"reporte": reporte})
