"""Form for on-demand report generation."""

from datetime import date

from django import forms

from .models import Reporte
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

    def __init__(self, *args, reporte: Reporte, sucursales, **kwargs):
        super().__init__(*args, **kwargs)
        # Only branches the user may see: validated here on the server, not
        # just hidden in the page.
        self.fields["sucursales"].queryset = sucursales
        # The report's scope decides whether per-branch, consolidated or both are offered.
        if reporte.alcance == Reporte.Alcance.POR_SUCURSAL:
            self.fields["modo"].choices = [(POR_SUCURSAL, "Un reporte por sucursal")]
        elif reporte.alcance == Reporte.Alcance.CONSOLIDADO:
            self.fields["modo"].choices = [(CONSOLIDADO, "Consolidado")]
        self.fields["modo"].initial = self.fields["modo"].choices[0][0]

    def clean(self):
        datos = super().clean()
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
