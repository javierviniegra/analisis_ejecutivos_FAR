from django.urls import path

from . import views

urlpatterns = [
    path("", views.catalogo, name="catalogo"),
    path("<slug:clave>/", views.detalle, name="reporte_detalle"),
    path("<slug:clave>/generar/", views.generar, name="reporte_generar"),
]
