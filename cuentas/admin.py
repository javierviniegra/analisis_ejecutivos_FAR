from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import PerfilUsuario, Sucursal


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "clave", "activa")
    list_filter = ("activa",)
    search_fields = ("nombre", "clave")


class PerfilInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    filter_horizontal = ("sucursales",)


class UserAdmin(BaseUserAdmin):
    inlines = [PerfilInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
