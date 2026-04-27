from django.db import migrations


SEED = [
    ("Carla M.", "Lima", 5,
     "Compré Netflix Premium y la cuenta llegó en menos de 5 minutos. Soporte por WhatsApp súper rápido."),
    ("Diego R.", "Arequipa", 5,
     "Llevo 6 meses comprando aquí mes a mes. Cero problemas, precios mucho mejores que otras páginas."),
    ("Andrea L.", "Trujillo", 5,
     "Pagué con Yape y todo perfecto. La cuenta de Disney+ funciona sin fallar."),
    ("Martín T.", "Cusco", 5,
     "Compré Office 2021 — llegó la licencia, la activé y a trabajar. Recomendado."),
    ("Lucia P.", "Piura", 5,
     "Soy distribuidora desde hace 3 meses, los precios mayoristas y el panel automatizado me hacen la vida fácil."),
    ("Jorge A.", "Chiclayo", 5,
     "Tuve un problema con Prime Video y me repusieron la cuenta sin preguntar. Garantía real."),
]


def seed(apps, schema_editor):
    Testimonial = apps.get_model("catalog", "Testimonial")
    if Testimonial.objects.exists():
        return
    for i, (author, city, rating, text) in enumerate(SEED):
        Testimonial.objects.create(
            author=author, city=city, rating=rating, text=text, order=i,
        )


def unseed(apps, schema_editor):
    Testimonial = apps.get_model("catalog", "Testimonial")
    Testimonial.objects.filter(author__in=[s[0] for s in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_testimonial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
