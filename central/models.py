from django.contrib.auth.models import Group
from django.db import models


class Reporte(models.Model):
    """Definition of a report the system knows about (the catalog).

    This describes WHAT a report is; how it is generated (Phase 3), viewed
    (Phase 4) and sent (Phase 5) hangs off this definition. Which profiles
    may see it is data (`perfiles`), editable from the admin.
    """

    class Categoria(models.TextChoices):
        # Owner, 2026-09-30: "Comercial" is called "Marca"; executive,
        # investors and partners reports are one category, "Inversionistas";
        # operating reports are branch reports ("Sucursales"); financial
        # reports go to "Inversionistas" or "Contabilidad" by audience.
        MARCA = "marca", "Marca"
        SUCURSALES = "sucursales", "Sucursales (gerentes)"
        INVERSIONISTAS = "inversionistas", "Inversionistas"
        CEDIS = "cedis", "CEDIS (Bodegón)"
        NOMINA = "nomina", "Nómina / RH"
        CONTABILIDAD = "contabilidad", "Contabilidad"
        INVENTARIOS = "inventarios", "Inventarios"

    class Periodicidad(models.TextChoices):
        DIARIA = "diaria", "Diaria"
        SEMANAL = "semanal", "Semanal"
        QUINCENAL = "quincenal", "Quincenal"
        MENSUAL = "mensual", "Mensual"
        SEMESTRAL = "semestral", "Semestral"
        ANUAL = "anual", "Anual"

    class Plantilla(models.TextChoices):
        EJECUTIVA = "ejecutiva", "Ejecutiva (plantilla estandar Fonda)"
        FINANCIERA = "financiera", "Informe financiero (plantilla nueva)"
        TABULAR = "tabular", "Tabular / Excel"
        SEMAFOROS = "semaforos", "Tabla con semaforos"

    class Fuente(models.TextChoices):
        ODOO = "odoo", "Odoo"
        MYSQL_PROD = "mysql_prod", "MySQL productivo (Wansoft)"
        MIXTA = "mixta", "Mixta (Odoo + MySQL + Presupuestos AP)"
        BUK = "buk", "Buk (nómina, API)"

    class Alcance(models.TextChoices):
        POR_SUCURSAL = "por_sucursal", "Un reporte por sucursal"
        CONSOLIDADO = "consolidado", "Consolidado (todas las sucursales juntas)"
        AMBOS = "ambos", "Por sucursal y consolidado"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente_definicion", "Pendiente de definir"
        DEFINIDO = "definido", "Definido (aun sin generador en la web)"
        IMPLEMENTADO = "implementado", "Implementado"

    clave = models.SlugField(max_length=60, unique=True, help_text="Stable technical key; never reuse.")
    nombre = models.CharField(max_length=160)
    descripcion = models.TextField(blank=True)
    categoria = models.CharField(max_length=20, choices=Categoria.choices)
    periodicidad = models.CharField(max_length=20, choices=Periodicidad.choices)
    plantilla = models.CharField(max_length=20, choices=Plantilla.choices)
    fuente = models.CharField(max_length=20, choices=Fuente.choices)
    alcance = models.CharField(max_length=20, choices=Alcance.choices)
    admite_pdf = models.BooleanField(default=False)
    admite_excel = models.BooleanField(default=False)
    estado = models.CharField(max_length=24, choices=Estado.choices, default=Estado.PENDIENTE)
    notas = models.TextField(blank=True, help_text="Open questions / definition notes.")
    perfiles = models.ManyToManyField(
        Group,
        blank=True,
        related_name="reportes",
        help_text="Profiles allowed to see this report. Empty = nobody (except staff).",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["categoria", "nombre"]
        verbose_name_plural = "reportes"

    def __str__(self):
        return self.nombre

    @property
    def formatos(self):
        return [f for f, ok in (("PDF", self.admite_pdf), ("Excel", self.admite_excel)) if ok]

    @classmethod
    def visibles_para(cls, user):
        """Active reports this user may see. Staff/superusers see all active
        reports; everyone else only those assigned to one of their groups."""
        qs = cls.objects.filter(activo=True)
        if user.is_superuser or user.is_staff:
            return qs
        return qs.filter(perfiles__in=user.groups.all()).distinct()


class ClienteCedis(models.Model):
    """Who an Odoo customer (or delivery address) of El Bodegón / Las Empanadas
    is, for the CEDIS reports: a branch, a label for customers that are not
    one of our branches, or excluded. Data, not code: edit it in the admin
    when a customer or address changes. Seeded by `cargar_clientes_cedis`.

    The Odoo delivery address wins over the customer (e.g. customer
    "FONDA ARGENTINA AEROPUERTO" delivering to "... TAQUERIA VIADUCTO")."""

    odoo_partner_id = models.IntegerField(unique=True, help_text="res.partner id in Odoo (customer or delivery address).")
    nombre_odoo = models.CharField(max_length=200, help_text="Name in Odoo, for reference.")
    sucursal = models.ForeignKey("cuentas.Sucursal", null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="clientes_cedis")
    etiqueta = models.CharField(max_length=80, blank=True,
                                help_text="Name to show when it is not one of our branches (e.g. Perisur, León).")
    excluir = models.BooleanField(default=False, help_text="Left out of the reports (e.g. Público general, CEDIS to CEDIS).")
    nota = models.CharField(max_length=200, blank=True, help_text="Shown in the report's notes (e.g. internal delivery).")

    class Meta:
        ordering = ["nombre_odoo"]
        verbose_name = "cliente de CEDIS (Odoo)"
        verbose_name_plural = "clientes de CEDIS (Odoo)"

    def __str__(self):
        destino = "(excluido)" if self.excluir else (self.nombre_reporte or "(sin asignar)")
        return f"{self.nombre_odoo} -> {destino}"

    @property
    def nombre_reporte(self) -> str | None:
        if self.excluir:
            return None
        return self.sucursal.nombre if self.sucursal else (self.etiqueta or None)
