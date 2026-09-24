from django.contrib.auth.models import Group
from django.db import models


class Reporte(models.Model):
    """Definition of a report the system knows about (the catalog).

    This describes WHAT a report is; how it is generated (Phase 3), viewed
    (Phase 4) and sent (Phase 5) hangs off this definition. Which profiles
    may see it is data (`perfiles`), editable from the admin.
    """

    class Categoria(models.TextChoices):
        COMERCIAL = "comercial", "Comercial"
        OPERATIVO = "operativo", "Operativo"
        FINANCIERO = "financiero", "Financiero"
        COMPRAS = "compras", "Compras"
        INVERSIONISTAS = "inversionistas", "Inversionistas"
        EJECUTIVO = "ejecutivo", "Ejecutivo"

    class Periodicidad(models.TextChoices):
        DIARIA = "diaria", "Diaria"
        SEMANAL = "semanal", "Semanal"
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
