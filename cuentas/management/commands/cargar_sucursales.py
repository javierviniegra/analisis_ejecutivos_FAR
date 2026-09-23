"""Load the branches and their identifiers in each source system.

Idempotent and non-destructive: a branch is created if its `clave` is
missing; if it exists, only EMPTY mapping fields are filled (an admin's edits
are never overwritten). The identifiers come from the Wansoft warehouse
(getglobalcashclosing.subsidiary_id, order-detail branch name) and from
Odoo/ControlPresupuestos_AP (odoo_company_id). Taqueria San Fernando (closed
since 2025-06) is intentionally not included.
"""

from django.core.management.base import BaseCommand

from cuentas.models import Sucursal

# clave, nombre, wansoft_subsidiary_id, wansoft_ticket_nombre, odoo_company_id
SUCURSALES = [
    ("acoxpa", "Acoxpa", 5320, "Acoxpa", 7),
    ("aeropuerto", "Aeropuerto", 4959, "Aeropuerto", None),
    ("isabel-la-catolica", "Isabel La Católica", 4958, "Isabel La Católica", None),
    ("antenas", "Antenas", 4960, "Antenas", 9),
    ("taqueria-parroquia", "Taquería Parroquia", 5321, "Taquería parroquia", None),
    ("via-vallejo", "Vía Vallejo", 5318, "Vía Vallejo", None),
    ("viaducto", "Viaducto", 4961, "Viaducto", None),
    ("taqueria-viaducto", "Taquería Viaducto", 4962, "Taquería Viaducto", None),
    ("san-jeronimo", "San Jerónimo", 5319, "San Jeronimo", None),
    ("tepeyac", "Tepeyac", 6560, "Tepeyac", 10),
    ("playa-del-carmen", "Playa del Carmen", 6174, "Playa del Carmen", None),
    ("oceania", "Oceanía", 5943, "Oceanía", 11),
    ("cancun", "Cancún", 6175, "Cancun", None),
    ("napoles", "Nápoles", 4433, "Napoles", None),
    ("metepec", "Metepec", 4752, "Metepec", None),
    ("versalles", "Versalles (Taquería Exhibimex)", 5396, "Versalles", None),
    ("la-esquina-coyoacan", "La Esquina Coyoacán", 12057, "La Esquina Coyoacán", 36),
    ("centro-myj", "CentroMyJ (Mario y July)", 12802, "CentroMyJ", 35),
    ("puebla", "Puebla", 12806, "Puebla", 34),
]


class Command(BaseCommand):
    help = "Load the branches and their source-system identifiers (idempotent, never overwrites filled fields)."

    def handle(self, *args, **options):
        for clave, nombre, subs_id, ticket, odoo_id in SUCURSALES:
            suc, creada = Sucursal.objects.get_or_create(
                clave=clave,
                defaults=dict(nombre=nombre, wansoft_subsidiary_id=subs_id, wansoft_ticket_nombre=ticket, odoo_company_id=odoo_id),
            )
            if creada:
                self.stdout.write(f"Creada: {nombre}")
                continue
            llenados = []
            for campo, valor in (
                ("wansoft_subsidiary_id", subs_id),
                ("wansoft_ticket_nombre", ticket),
                ("odoo_company_id", odoo_id),
            ):
                if valor not in (None, "") and getattr(suc, campo) in (None, ""):
                    setattr(suc, campo, valor)
                    llenados.append(campo)
            if llenados:
                suc.save()
            self.stdout.write(f"Ya existia: {nombre}" + (f" (completado: {', '.join(llenados)})" if llenados else " (sin cambios)"))
