from django.conf import settings
from django.db import models


class Sucursal(models.Model):
    """A branch a report can be about. Odoo/Wansoft naming differs per system,
    so `clave` is this project's own stable key (e.g. "Puebla")."""

    clave = models.SlugField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "sucursales"

    def __str__(self):
        return self.nombre


class PerfilUsuario(models.Model):
    """Extra data for a user. The user's *role* is a Django Group (Director,
    Administrador general, Gerente, Usuario) so what each role may do stays
    configurable from the admin/web; this model only adds branch scope."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil"
    )
    todas_las_sucursales = models.BooleanField(
        default=False, help_text="Sees every branch (e.g. Director, Administrador general)."
    )
    sucursales = models.ManyToManyField(Sucursal, blank=True, related_name="usuarios")

    class Meta:
        permissions = [
            ("ver_reportes", "Puede ver reportes"),
            ("generar_reportes", "Puede generar reportes"),
            ("gestionar_envios", "Puede gestionar envios programados"),
            ("gestionar_usuarios", "Puede gestionar usuarios y perfiles"),
        ]

    def __str__(self):
        return f"Perfil de {self.usuario}"

    def sucursales_visibles(self):
        if self.todas_las_sucursales:
            return Sucursal.objects.filter(activa=True)
        return self.sucursales.filter(activa=True)
