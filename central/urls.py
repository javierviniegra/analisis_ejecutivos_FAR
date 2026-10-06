from django.urls import path

from . import views

urlpatterns = [
    path("", views.catalogo, name="catalogo"),
    path("<slug:clave>/", views.detalle, name="reporte_detalle"),
    path("<slug:clave>/generar/", views.generar, name="reporte_generar"),
    path("<slug:clave>/correo/<str:token>/", views.correo_previa, name="correo_previa"),
    path("<slug:clave>/correo/<str:token>/adjunto/<int:n>/", views.correo_adjunto, name="correo_adjunto"),
    path("<slug:clave>/automatizaciones/nueva/", views.automatizacion, name="automatizacion_nueva"),
    path("<slug:clave>/automatizaciones/<int:pk>/", views.automatizacion, name="automatizacion_editar"),
    path("<slug:clave>/automatizaciones/<int:pk>/pausar/", views.automatizacion_pausar, name="automatizacion_pausar"),
]
