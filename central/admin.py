from django.contrib import admin

from .models import Automatizacion, ClienteCedis, EnvioAutomatico, EnvioManual, Reporte


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


@admin.register(Automatizacion)
class AutomatizacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "reporte", "tipo", "dias_despues", "hora", "formato", "activa")
    list_filter = ("activa", "tipo", "reporte")
    search_fields = ("nombre",)
    filter_horizontal = ("sucursales", "consolidado_destinatarios", "particulares_destinatarios")


@admin.register(EnvioAutomatico)
class EnvioAutomaticoAdmin(admin.ModelAdmin):
    list_display = ("automatizacion", "desde", "hasta", "programado_para", "enviado_en", "estado", "intentos")
    list_filter = ("estado",)
    readonly_fields = [f.name for f in EnvioAutomatico._meta.fields]


@admin.register(EnvioManual)
class EnvioManualAdmin(admin.ModelAdmin):
    list_display = ("reporte", "periodo", "usuario", "enviado_en", "error")
    readonly_fields = [f.name for f in EnvioManual._meta.fields]
