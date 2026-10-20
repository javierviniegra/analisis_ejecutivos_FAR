from django.db import migrations, models

# Owner, 2026-10-19: taquerías and La Esquina; every other branch is a fonda (the default).
FORMATOS = {"taqueria-parroquia": "taqueria", "taqueria-viaducto": "taqueria", "versalles": "taqueria",
            "la-esquina-coyoacan": "esquina"}


def asignar(apps, schema_editor):
    Sucursal = apps.get_model("cuentas", "Sucursal")
    for clave, formato in FORMATOS.items():
        Sucursal.objects.filter(clave=clave).update(formato=formato)


class Migration(migrations.Migration):
    dependencies = [("cuentas", "0004_considerar_costo")]

    operations = [
        migrations.AddField(
            model_name="sucursal",
            name="formato",
            field=models.CharField(
                choices=[("fonda", "Fonda"), ("taqueria", "Taquería"), ("esquina", "La Esquina")], default="fonda",
                help_text="Tipo de restaurante: el consolidado separa ticket y cheque por formato.", max_length=10),
        ),
        migrations.RunPython(asignar, migrations.RunPython.noop),
    ]
