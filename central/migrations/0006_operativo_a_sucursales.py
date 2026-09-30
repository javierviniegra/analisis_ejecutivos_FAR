"""Owner, 2026-09-30: operating reports are branch reports, so the
"Operativo" category goes away and its reports move to "Sucursales"."""

from django.db import migrations, models


def convertir(apps, schema_editor):
    apps.get_model("central", "Reporte").objects.filter(categoria="operativo").update(categoria="sucursales")


class Migration(migrations.Migration):

    dependencies = [
        ("central", "0005_categorias_por_area"),
    ]

    operations = [
        migrations.RunPython(convertir, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="reporte",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("marca", "Marca"),
                    ("sucursales", "Sucursales (gerentes)"),
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
