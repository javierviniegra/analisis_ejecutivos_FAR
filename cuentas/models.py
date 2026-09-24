from django.conf import settings
from django.db import models


class Sucursal(models.Model):
    """A branch a report can be about. Odoo/Wansoft naming differs per system,
    so `clave` is this project's own stable key (e.g. "Puebla")."""

    clave = models.SlugField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    activa = models.BooleanField(default=True)

    # Identifiers of the same branch in each source system. None of the
    # names match across systems, so queries go by these stable keys.
    wansoft_subsidiary_id = models.IntegerField(
        null=True, blank=True, unique=True, help_text="getglobalcashclosing.subsidiary_id (Wansoft)."
    )
    wansoft_ticket_nombre = models.CharField(
        max_length=120, blank=True, help_text="Sucursal name in getallordenesbyday_* (blank = no ticket detail)."
    )
    odoo_company_id = models.IntegerField(
        null=True, blank=True, unique=True, help_text="Odoo res.company id (also ControlPresupuestos_AP's key)."
    )

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


def sucursales_de(user):
    """Active branches a user may run reports on: superusers and staff see
    all; everyone else what their profile allows (none without a profile)."""
    if user.is_superuser or user.is_staff:
        return Sucursal.objects.filter(activa=True)
    perfil = getattr(user, "perfil", None)
    return perfil.sucursales_visibles() if perfil else Sucursal.objects.none()


def puede_generar(user) -> bool:
    return user.is_superuser or user.has_perm("cuentas.generar_reportes")
