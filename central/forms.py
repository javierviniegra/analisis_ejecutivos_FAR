"""Form for on-demand report generation."""

from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from cuentas.models import separar_correos

from .models import Automatizacion, Reporte
from .motor.periodo import Periodo, TipoPeriodo

TIPOS = [
    (TipoPeriodo.SEMANA.value, "Semana (lunes a domingo)"),
    (TipoPeriodo.MES.value, "Mes"),
    (TipoPeriodo.BIMESTRE.value, "Bimestre"),
    (TipoPeriodo.TRIMESTRE.value, "Trimestre"),
    (TipoPeriodo.SEMESTRE.value, "Semestre"),
    (TipoPeriodo.ANIO.value, "Año"),
    (TipoPeriodo.RANGO.value, "Rango libre de fechas"),
]
MAX_DIAS_RANGO = 366

POR_SUCURSAL, CONSOLIDADO = "por_sucursal", "consolidado"
UN_ARCHIVO, SEPARADOS = "un_archivo", "separados"
PDF, EXCEL, AMBOS = "pdf", "excel", "ambos"


class GenerarForm(forms.Form):
    sucursales = forms.ModelMultipleChoiceField(
        queryset=None, widget=forms.CheckboxSelectMultiple, error_messages={"required": "Elige al menos una sucursal."}
    )
    tipo = forms.ChoiceField(choices=TIPOS, initial=TipoPeriodo.SEMANA.value, label="Tipo de periodo")
    fecha = forms.DateField(required=False, label="Cualquier día del periodo",
                            widget=forms.DateInput(attrs={"type": "date"}))
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    modo = forms.ChoiceField(choices=[(POR_SUCURSAL, "Un reporte por sucursal"), (CONSOLIDADO, "Consolidado")],
                             widget=forms.RadioSelect, label="Presentación")
    # Rule (owner, 2026-09-24): several branches per branch -> always ask; no default.
    entrega = forms.ChoiceField(required=False, widget=forms.RadioSelect, label="Entrega",
                                choices=[(UN_ARCHIVO, "Todo en un archivo (una página u hoja por sucursal)"),
                                         (SEPARADOS, "Un archivo por sucursal (se descargan juntos en un .zip)")])
    formato = forms.ChoiceField(widget=forms.RadioSelect, label="Formato",
                                choices=[(PDF, "PDF"), (EXCEL, "Excel"), (AMBOS, "PDF y Excel (en un .zip)")])
    # Report options (generadores.OPCIONES); only the ones the report admits are kept.
    incluir_costos = forms.BooleanField(required=False, initial=True, label="Incluir costos")
    # "Enviar por correo" (owner, 2026-10-06): the same report, e-mailed to whom the user picks.
    destinatarios = forms.ModelMultipleChoiceField(queryset=None, required=False, widget=forms.CheckboxSelectMultiple,
                                                   label="Usuarios")
    correos = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Otros correos")
    mensaje = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}),
                              label="Mensaje (opcional)")
    titulo = forms.CharField(required=False, max_length=150, label="Título en el correo")

    def __init__(self, *args, reporte: Reporte, sucursales, opciones: dict | None = None, usuarios=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destinatarios"].queryset = usuarios if usuarios is not None else \
            self.fields["sucursales"].queryset.none()
        self.fields["destinatarios"].label_from_instance = lambda u: f"{u.get_full_name() or u.username} ({u.email})"
        self.fields["titulo"].widget.attrs.update(placeholder=reporte.nombre, size=60)
        self.opciones = opciones or {}
        for nombre in ("incluir_costos",):
            if nombre in self.opciones:
                self.fields[nombre].initial = self.opciones[nombre]
            else:
                del self.fields[nombre]
        # Only branches the user may see: validated here on the server, not
        # just hidden in the page.
        self.fields["sucursales"].queryset = sucursales
        # The report's scope decides whether per-branch, consolidated or both are offered.
        if reporte.alcance == Reporte.Alcance.POR_SUCURSAL:
            self.fields["modo"].choices = [(POR_SUCURSAL, "Un reporte por sucursal")]
        elif reporte.alcance == Reporte.Alcance.CONSOLIDADO:
            self.fields["modo"].choices = [(CONSOLIDADO, "Consolidado")]
        self.fields["modo"].initial = self.fields["modo"].choices[0][0]
        # Only the formats the report admits.
        formatos = [(PDF, "PDF")] * reporte.admite_pdf + [(EXCEL, "Excel")] * reporte.admite_excel
        if len(formatos) == 2:
            formatos.append((AMBOS, "PDF y Excel (en un .zip)"))
        self.fields["formato"].choices = formatos
        self.fields["formato"].initial = formatos[0][0] if formatos else None

    def clean(self):
        datos = super().clean()
        varias = len(datos.get("sucursales") or []) > 1 and datos.get("modo") == POR_SUCURSAL
        if varias and not datos.get("entrega"):
            self.add_error("entrega", "Elige si quieres todo en un archivo o un archivo por sucursal.")
        datos["separados"] = varias and datos.get("entrega") == SEPARADOS
        formato = datos.get("formato")
        datos["formatos"] = {PDF, EXCEL} if formato == AMBOS else {formato}
        if self.data.get("accion") == "correo":
            otros = separar_correos(datos.get("correos", ""))
            for correo in otros:
                try:
                    validate_email(correo)
                except ValidationError:
                    self.add_error("correos", f"Correo no válido: {correo}")
            para = [u.email for u in datos.get("destinatarios") or [] if u.email] + otros
            if not para:
                self.add_error("destinatarios", "Elige a quién enviarlo (usuarios u otros correos).")
            datos["para"] = list(dict.fromkeys(para))
            datos["otros_correos"] = otros
        datos["opciones"] = {nombre: bool(datos.get(nombre)) for nombre in self.opciones}
        tipo = datos.get("tipo")
        if not tipo:
            return datos
        tipo = TipoPeriodo(tipo)
        if tipo == TipoPeriodo.RANGO:
            desde, hasta = datos.get("desde"), datos.get("hasta")
            if not (desde and hasta):
                raise forms.ValidationError("Para un rango indica la fecha inicial y la final.")
            if desde > hasta:
                raise forms.ValidationError("La fecha inicial no puede ser posterior a la final.")
            if (hasta - desde).days + 1 > MAX_DIAS_RANGO:
                raise forms.ValidationError(f"El rango no puede pasar de {MAX_DIAS_RANGO} días.")
            periodo = Periodo.rango(desde, hasta)
        else:
            fecha = datos.get("fecha")
            if not fecha:
                raise forms.ValidationError("Indica una fecha dentro del periodo.")
            periodo = Periodo.de_fecha(tipo, fecha)
        if periodo.desde > date.today():
            raise forms.ValidationError("El periodo todavía no empieza.")
        datos["periodo"] = periodo
        return datos


class AutomatizacionForm(forms.ModelForm):
    """Create / edit an automation of one report. Only the choices the report
    admits are offered (scope, formats, its options); the model validates them
    again. The report's options are stored in `opciones` as rules."""

    incluir_costos = forms.BooleanField(required=False, initial=True, label="Incluir costos")

    class Meta:
        model = Automatizacion
        fields = ["nombre", "activa", "titulo", "tipo", "dias_despues", "hora", "todas_las_sucursales", "sucursales",
                  "enviar_consolidado", "enviar_particulares", "formato",
                  "consolidado_destinatarios", "consolidado_correos",
                  "particulares_a_sucursal", "particulares_destinatarios", "particulares_correos",
                  "particulares_solo_sus_sucursales"]
        widgets = {
            "sucursales": forms.CheckboxSelectMultiple,
            "consolidado_destinatarios": forms.CheckboxSelectMultiple,
            "particulares_destinatarios": forms.CheckboxSelectMultiple,
            "formato": forms.RadioSelect,
            "hora": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            # 1..28 = days after the close; the page relabels them per frequency
            # (a week: the weekday it goes out; a month: the day of the next month).
            "dias_despues": forms.Select(choices=[(i, str(i)) for i in range(1, 29)]),
            "consolidado_correos": forms.Textarea(attrs={"rows": 2}),
            "particulares_correos": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, reporte: Reporte, sucursales, usuarios, opciones: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.reporte = reporte
        self.fields["sucursales"].queryset = sucursales
        for campo in ("consolidado_destinatarios", "particulares_destinatarios"):
            self.fields[campo].queryset = usuarios
            self.fields[campo].label_from_instance = (
                lambda u: f"{u.get_full_name() or u.username} ({u.email or 'sin correo'})")
        formatos = [(Automatizacion.Formato.PDF, "PDF")] * reporte.admite_pdf + \
                   [(Automatizacion.Formato.EXCEL, "Excel")] * reporte.admite_excel
        if len(formatos) == 2:
            formatos.append((Automatizacion.Formato.AMBOS, "PDF y Excel"))
        self.fields["formato"].choices = formatos
        if not self.instance.pk and formatos:
            self.initial.setdefault("formato", formatos[0][0])
        # scope: drop what the report cannot send
        if reporte.alcance == Reporte.Alcance.POR_SUCURSAL:
            for campo in ("enviar_consolidado", "consolidado_destinatarios", "consolidado_correos"):
                del self.fields[campo]
        elif reporte.alcance == Reporte.Alcance.CONSOLIDADO:
            for campo in ("enviar_particulares", "particulares_a_sucursal", "particulares_destinatarios",
                          "particulares_correos", "particulares_solo_sus_sucursales"):
                del self.fields[campo]
            self.instance.enviar_particulares, self.instance.enviar_consolidado = False, True
        # the report's own options, as rules (default: the report's default, or what was saved)
        self.opciones = opciones or {}
        if "incluir_costos" in self.opciones:
            self.fields["incluir_costos"].initial = self.instance.opciones.get(
                "incluir_costos", self.opciones["incluir_costos"]) if self.instance.pk else self.opciones["incluir_costos"]
        else:
            del self.fields["incluir_costos"]

    def clean(self):
        datos = super().clean()
        if not datos.get("todas_las_sucursales") and not datos.get("sucursales"):
            self.add_error("sucursales", "Elige sucursales o marca «Todas las sucursales activas».")
        consolidado = datos.get("enviar_consolidado", self.instance.enviar_consolidado)
        if consolidado and not (datos.get("consolidado_destinatarios") or (datos.get("consolidado_correos") or "").strip()):
            self.add_error("consolidado_destinatarios" if "consolidado_destinatarios" in self.fields else None,
                           "Elige a quién se manda el consolidado.")
        if datos.get("enviar_particulares") and not (
                datos.get("particulares_a_sucursal") or datos.get("particulares_destinatarios")
                or (datos.get("particulares_correos") or "").strip()):
            self.add_error("particulares_destinatarios",
                           "Elige a quién se mandan los reportes por sucursal (sus destinatarios o personas).")
        return datos

    def save(self, commit=True):
        self.instance.opciones = {nombre: bool(self.cleaned_data.get(nombre)) for nombre in self.opciones}
        return super().save(commit)
