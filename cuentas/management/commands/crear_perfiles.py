"""Create/update the four base roles as Django Groups with default permissions.

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
}


class Command(BaseCommand):
    help = "Create the base roles (Director, Administrador general, Gerente, Usuario)."

    def handle(self, *args, **options):
        for nombre, codenames in PERFILES.items():
            grupo, creado = Group.objects.get_or_create(name=nombre)
            if creado:
                grupo.permissions.set(Permission.objects.filter(codename__in=codenames))
            estado = "Creado" if creado else "Ya existia (sin cambios)"
            self.stdout.write(f"{estado}: {nombre}")
