from django.contrib import admin

from .models import Reporte


@admin.register(Reporte)
class ReporteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "periodicidad", "plantilla", "fuente", "estado", "activo")
    list_filter = ("categoria", "periodicidad", "estado", "fuente", "activo")
    search_fields = ("nombre", "clave", "descripcion")
    filter_horizontal = ("perfiles",)
