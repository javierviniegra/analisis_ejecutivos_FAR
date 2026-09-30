"""Create/update the base roles as Django Groups with default permissions.

Idempotent: safe to re-run. Permissions granted here are only the starting
point -- edit them afterwards from the admin (Groups) without touching code.
An existing group is never modified, so admin edits are not overwritten.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

PERFILES = {
    "Director": ["ver_reportes", "generar_reportes", "gestionar_envios", "gestionar_usuarios"],
    "Administrador general": ["ver_reportes", "generar_reportes", "gestionar_envios", "gestionar_usuarios"],
    "Gerente": ["ver_reportes", "generar_reportes"],
    "Usuario": ["ver_reportes"],
    # Payroll staff: only sees the reports assigned to this group (the payroll
    # reports), since report access is deny-by-default per group.
    "Nominista": ["ver_reportes", "generar_reportes"],
    # Area profiles, same idea: each only sees the reports assigned to it.
    "CEDIS": ["ver_reportes", "generar_reportes"],  # El Bodegón (central kitchen / distribution)
    "Contabilidad": ["ver_reportes", "generar_reportes"],
}


class Command(BaseCommand):
    help = "Create the base roles (Director, Administrador general, Gerente, Usuario, Nominista, CEDIS, Contabilidad)."

    def handle(self, *args, **options):
        for nombre, codenames in PERFILES.items():
            grupo, creado = Group.objects.get_or_create(name=nombre)
            if creado:
                grupo.permissions.set(Permission.objects.filter(codename__in=codenames))
            estado = "Creado" if creado else "Ya existia (sin cambios)"
            self.stdout.write(f"{estado}: {nombre}")
