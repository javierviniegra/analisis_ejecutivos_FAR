"""Owner, 2026-09-30: "Comercial" becomes "Marca"; the executive, investors
and partners reports are a single category, "Inversionistas". Existing rows
are converted before the field's choices change."""

from django.db import migrations, models

CAMBIOS = {"comercial": "marca", "ejecutivo": "inversionistas", "socios": "inversionistas"}


def convertir(apps, schema_editor):
    Reporte = apps.get_model("central", "Reporte")
    for viejo, nuevo in CAMBIOS.items():
        Reporte.objects.filter(categoria=viejo).update(categoria=nuevo)


def revertir(apps, schema_editor):
    # "inversionistas" cannot be split back reliably; only "marca" is undone.
    Reporte = apps.get_model("central", "Reporte")
    Reporte.objects.filter(categoria="marca").update(categoria="comercial")


class Migration(migrations.Migration):

    dependencies = [
        ("central", "0004_alter_reporte_categoria"),
    ]

    operations = [
        migrations.RunPython(convertir, revertir),
        migrations.AlterField(
            model_name="reporte",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("marca", "Marca"),
                    ("sucursales", "Sucursales (gerentes)"),
                    ("operativo", "Operativo"),
                    ("inversionistas", "Inversionistas"),
                    ("cedis", "CEDIS (Bodegón)"),
                    ("nomina", "Nómina / RH"),
                    ("contabilidad", "Contabilidad"),
                    ("inventarios", "Inventarios"),
                    ("financiero", "Financiero"),
                    ("compras", "Compras"),
                ],
                max_length=20,
            ),
        ),
    ]
