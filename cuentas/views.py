from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    perfil = getattr(request.user, "perfil", None)
    sucursales = perfil.sucursales_visibles() if perfil else []
    return render(request, "cuentas/home.html", {"sucursales": sucursales})
