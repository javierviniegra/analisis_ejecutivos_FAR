from django.contrib import admin

from .models import ClienteCedis, Reporte


@admin.register(Reporte)
class ReporteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "periodicidad", "plantilla", "fuente", "estado", "activo")
    list_filter = ("categoria", "periodicidad", "estado", "fuente", "activo")
    search_fields = ("nombre", "clave", "descripcion")
    filter_horizontal = ("perfiles",)


@admin.register(ClienteCedis)
class ClienteCedisAdmin(admin.ModelAdmin):
    list_display = ("nombre_odoo", "odoo_partner_id", "sucursal", "etiqueta", "excluir", "nota")
    list_filter = ("excluir", "sucursal")
    search_fields = ("nombre_odoo", "etiqueta")
