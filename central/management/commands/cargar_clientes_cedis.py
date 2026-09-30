"""Seed the Odoo customer -> branch table of the CEDIS reports (read-only on Odoo).

Finds the customers and delivery addresses that actually appear on El
Bodegón / Las Empanadas sales orders and applies the owner's mapping
(2026-09-30). Never overwrites a row that exists (admin edits win); a
customer that is not in the mapping is created unassigned, and the reports
list it in their notes until someone assigns it in the admin.

    python manage.py cargar_clientes_cedis
"""

from django.core.management.base import BaseCommand

from central.models import ClienteCedis
from central.motor.fuentes import odoo
from cuentas.models import Sucursal

# Odoo display name -> (branch key | None, label, exclude, note). Owner, 2026-09-30.
ASIGNACION = {
    "FONDA ARGENTINA": ("isabel-la-catolica", "", False, ""),
    "FONDA ARGENTINA AEROPUERTO": ("aeropuerto", "", False, ""),
    "FONDA ARGENTINA AEROPUERTO, TAQUERIA VIADUCTO": ("taqueria-viaducto", "", False, ""),
    "FONDA ARGENTINA COYOACAN": ("la-esquina-coyoacan", "", False, ""),
    "FONDA ARGENTINA ENCUENTRO OCEANIA": ("oceania", "", False, ""),
    "FONDA ARGENTINA MAQ": ("tepeyac", "", False, ""),
    "FONDA ARGENTINA POLYFORUM, FONDA ARGENTINA POLYFORUM": ("napoles", "", False, ""),
    "FONDA ARGENTINA PUEBLA": ("puebla", "", False, ""),
    "FONDA ARGENTINA SAN JERONIMO": ("san-jeronimo", "", False, ""),
    "FONDA ARGENTINA TOLLOCAN": ("metepec", "", False, ""),
    "FONDA ARGENTINA VALLEJO": ("via-vallejo", "", False, ""),
    "FONDA ARGENTINA VIADUCTO": ("viaducto", "", False, ""),
    "FONDA COSTA NERA": ("acoxpa", "", False, ""),
    "Fonda Argentina las Antenas, FONDA ARGENTINA LAS ANTENAS": ("antenas", "", False, ""),
    "MARIO Y JULY": ("centro-myj", "", False, ""),
    "PERALTA Y LEON": ("taqueria-parroquia", "", False,
                       "Peralta y León: compra Taquería Parroquia y entrega internamente a Versalles (Exhibimex)."),
    "LA PARRILLADA ORIGINAL DEL SUR": ("cancun", "", False,
                                       "La Parrillada Original del Sur: compra Cancún; Playa del Carmen se abastece por entrega interna."),
    "GASTRONOMIA MUNDO E": (None, "Perisur", False, ""),
    "GASTRONOMIA MUNDO E, Fonda Argentina Lindavista": (None, "Lindavista", False, ""),
    "AMIGO DEL CHEF": (None, "León", False, ""),
    "PUBLICO GENERAL": (None, "", True, ""),
    "EL BODEGON DE FITO": (None, "", True, ""),
    "LAS EMPANADAS DE MARIA EVA": (None, "", True, ""),
}


class Command(BaseCommand):
    help = "Seed the Odoo customer -> branch table of the CEDIS reports (never overwrites existing rows)."

    def handle(self, *args, **options):
        cli = odoo.abrir_odoo()
        proveedores = list(odoo.proveedores_internos(cli))
        companias = odoo.companias_de(cli, proveedores)
        pedidos = cli.leer_todo("sale.order", [["company_id", "in", companias], ["state", "in", ["sale", "done"]]],
                                ["partner_id", "partner_shipping_id"])
        socios = {}
        for p in pedidos:
            for campo in ("partner_id", "partner_shipping_id"):
                if p[campo]:
                    socios[p[campo][0]] = p[campo][1]
        sucursales = {s.clave: s for s in Sucursal.objects.all()}
        for pid, nombre in sorted(socios.items(), key=lambda x: x[1]):
            clave, etiqueta, excluir, nota = ASIGNACION.get(nombre, (None, "", False, ""))
            fila, creada = ClienteCedis.objects.get_or_create(
                odoo_partner_id=pid,
                defaults=dict(nombre_odoo=nombre, sucursal=sucursales.get(clave) if clave else None,
                              etiqueta=etiqueta, excluir=excluir, nota=nota))
            estado = "Creado" if creada else "Ya existia (sin cambios)"
            aviso = "" if nombre in ASIGNACION else "  <- SIN ASIGNAR: asignalo en el admin"
            self.stdout.write(f"{estado}: {fila}{aviso}")
