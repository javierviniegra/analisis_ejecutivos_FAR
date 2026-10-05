from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
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


class Automatizacion(models.Model):
    """A scheduled delivery of one report (Phase 5): which branches, what is
    sent (consolidated and/or one per branch), format, the report's options
    as rules, who receives it and when. Bound to ONE period kind; it always
    sends the last closed period of that kind, `dias_despues` days after it
    closes, at `hora` (see central/motor/programacion.py)."""

    class Tipo(models.TextChoices):
        # same values as motor.periodo.TipoPeriodo (a free range cannot be automated)
        SEMANA = "semana", "Semanal"
        MES = "mes", "Mensual"
        BIMESTRE = "bimestre", "Bimestral"
        TRIMESTRE = "trimestre", "Trimestral"
        SEMESTRE = "semestre", "Semestral"
        ANIO = "anio", "Anual"

    class Formato(models.TextChoices):
        PDF = "pdf", "PDF"
        EXCEL = "excel", "Excel"
        AMBOS = "ambos", "PDF y Excel"

    reporte = models.ForeignKey(Reporte, on_delete=models.CASCADE, related_name="automatizaciones")
    nombre = models.CharField(max_length=120)
    activa = models.BooleanField(default=True)
    tipo = models.CharField("frecuencia", max_length=12, choices=Tipo.choices, default=Tipo.SEMANA)
    dias_despues = models.PositiveSmallIntegerField(
        "días después del cierre", default=1,
        help_text="1 = el día siguiente al cierre (lunes para una semana, día 1 para un mes).")
    hora = models.TimeField(default="08:00")
    todas_las_sucursales = models.BooleanField(
        default=True, help_text="Todas las sucursales activas, también las que se abran después.")
    sucursales = models.ManyToManyField("cuentas.Sucursal", blank=True, related_name="automatizaciones")
    enviar_consolidado = models.BooleanField(default=False)
    enviar_particulares = models.BooleanField("enviar uno por sucursal", default=True)
    formato = models.CharField(max_length=8, choices=Formato.choices, default=Formato.PDF)
    opciones = models.JSONField(default=dict, blank=True, help_text="Reglas del reporte, p. ej. incluir_costos.")
    # Recipients, separate for each kind of file (owner, 2026-10-05):
    # - consolidated: specific people only;
    # - one per branch: each branch's default recipients (cuentas.Sucursal) get
    #   their branch's report, plus optional people who get the branches' reports
    #   (users only those of their profile, if so set; outside e-mails all).
    consolidado_destinatarios = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="automatizaciones_consolidado")
    consolidado_correos = models.TextField(blank=True, help_text="Correos fuera del sistema, uno por renglón.")
    particulares_a_sucursal = models.BooleanField(
        "a los destinatarios de cada sucursal", default=True,
        help_text="Cada sucursal recibe solo su reporte (destinatarios definidos en la sucursal).")
    particulares_destinatarios = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="automatizaciones_particulares")
    particulares_correos = models.TextField(blank=True, help_text="Correos fuera del sistema, uno por renglón.")
    particulares_solo_sus_sucursales = models.BooleanField(
        "cada quien solo sus sucursales", default=True,
        help_text="Los usuarios agregados reciben solo las sucursales de su perfil; los correos externos, todas.")
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["reporte", "nombre"]
        verbose_name = "automatización"
        verbose_name_plural = "automatizaciones"

    def __str__(self):
        return f"{self.reporte} · {self.nombre}"

    def clean(self):
        from .motor.periodo import TipoPeriodo
        from .motor.programacion import max_dias_despues

        errores = {}
        if not (self.enviar_consolidado or self.enviar_particulares):
            errores["enviar_particulares"] = "Elige consolidado, uno por sucursal o ambos."
        if self.reporte_id:
            alcance = self.reporte.alcance
            if self.enviar_consolidado and alcance == Reporte.Alcance.POR_SUCURSAL:
                errores["enviar_consolidado"] = "Este reporte no tiene versión consolidada."
            if self.enviar_particulares and alcance == Reporte.Alcance.CONSOLIDADO:
                errores["enviar_particulares"] = "Este reporte solo es consolidado."
            admitidos = {self.Formato.PDF: self.reporte.admite_pdf, self.Formato.EXCEL: self.reporte.admite_excel,
                         self.Formato.AMBOS: self.reporte.admite_pdf and self.reporte.admite_excel}
            if not admitidos.get(self.formato):
                errores["formato"] = "Este reporte no se genera en ese formato."
        tope = max_dias_despues(TipoPeriodo(self.tipo))
        if not 1 <= self.dias_despues <= tope:
            errores["dias_despues"] = f"Entre 1 y {tope} días después del cierre."
        if errores:
            raise ValidationError(errores)

    @property
    def correos_consolidado(self) -> list[str]:
        from cuentas.models import separar_correos
        return separar_correos(self.consolidado_correos)

    @property
    def correos_particulares(self) -> list[str]:
        from cuentas.models import separar_correos
        return separar_correos(self.particulares_correos)


class EnvioAutomatico(models.Model):
    """Send log: one row per automation and period (retries update it), so a
    period is never sent twice and every send can be audited."""

    class Estado(models.TextChoices):
        ENVIADO = "enviado", "Enviado"
        ERROR = "error", "Error"
        SIN_DESTINATARIOS = "sin_destinatarios", "Sin destinatarios"

    automatizacion = models.ForeignKey(Automatizacion, on_delete=models.CASCADE, related_name="envios")
    desde = models.DateField()
    hasta = models.DateField()
    programado_para = models.DateTimeField()
    enviado_en = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=Estado.choices)
    destinatarios = models.TextField(blank=True)
    archivos = models.TextField(blank=True)
    error = models.TextField(blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-programado_para"]
        constraints = [models.UniqueConstraint(fields=["automatizacion", "desde"], name="un_envio_por_periodo")]
        verbose_name = "envío automático"
        verbose_name_plural = "envíos automáticos"

    def __str__(self):
        return f"{self.automatizacion} · {self.desde:%d/%m/%Y} · {self.get_estado_display()}"
