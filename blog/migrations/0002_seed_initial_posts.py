"""Seed inicial: 2 categorías + 3 posts publicados de ejemplo."""

from django.db import migrations
from django.utils import timezone
from django.utils.text import slugify


def seed(apps, schema_editor):
    BlogCategory = apps.get_model("blog", "BlogCategory")
    BlogPost = apps.get_model("blog", "BlogPost")

    cats = {}
    for name, emoji, desc in [
        ("Streaming", "🎬", "Cómo activar y aprovechar tus cuentas de Netflix, Disney+, HBO, Prime y más."),
        ("Software", "💻", "Office, antivirus y licencias originales: tips y comparativas."),
        ("Guías", "📘", "Guías paso a paso para problemas comunes."),
    ]:
        cats[name] = BlogCategory.objects.create(
            name=name, slug=slugify(name), emoji=emoji, description=desc,
        )

    now = timezone.now()
    posts = [
        {
            "title": "Cómo activar Netflix Premium 2026 paso a paso",
            "slug": "como-activar-netflix-premium-2026",
            "excerpt": "Guía visual para activar tu cuenta de Netflix Premium en menos de 2 minutos: ingreso, perfil, PIN y verificación en TV o celular.",
            "category": cats["Streaming"],
            "is_featured": True,
            "seo_keywords": "netflix premium 2026, activar netflix, cuenta netflix, netflix peru",
            "body": (
                "# Cómo activar Netflix Premium 2026 paso a paso\n\n"
                "Recibiste tu cuenta de Netflix Premium. Sigue estos pasos para activarla "
                "correctamente y evitar bloqueos.\n\n"
                "## 1. Abre Netflix en tu dispositivo\n\n"
                "Entra a **netflix.com** desde un navegador o abre la app oficial. Importante: "
                "no inicies sesión en TV antes de hacerlo en el celular o PC.\n\n"
                "## 2. Inicia sesión con las credenciales que recibiste\n\n"
                "Encuentras correo y contraseña en tu pedido en **Mi cuenta**. Cópialas tal cual, "
                "respetando mayúsculas y caracteres especiales.\n\n"
                "## 3. Selecciona tu perfil\n\n"
                "Vas a ver varios perfiles. **Solo entras al que tiene tu nombre y PIN**. "
                "No edites otros perfiles ni cambies la contraseña.\n\n"
                "## 4. ¿Te pide verificar dispositivo?\n\n"
                "A veces Netflix manda un código al correo del dueño. Si te pasa, abre un ticket "
                "desde **Mi cuenta** y te enviamos el código en menos de 5 minutos.\n\n"
                "## 5. Tips para que tu cuenta dure los 30 días\n\n"
                "- No cambies la contraseña ni el correo de la cuenta.\n"
                "- No edites otros perfiles.\n"
                "- Conecta tu Smart TV solo después de iniciar en el celular.\n"
                "- Si Netflix te pide verificación, escríbenos por WhatsApp.\n\n"
                "> Nuestra garantía de 30 días aplica solo si sigues estos pasos.\n"
            ),
        },
        {
            "title": "Cuenta completa vs perfil de Netflix: ¿cuál te conviene?",
            "slug": "cuenta-completa-vs-perfil-netflix",
            "excerpt": "Diferencias clave entre comprar la cuenta completa y comprar solo un perfil. Te explicamos qué pierdes y qué ganas con cada opción.",
            "category": cats["Streaming"],
            "seo_keywords": "cuenta completa netflix, perfil netflix, netflix peru, comprar netflix",
            "body": (
                "# Cuenta completa vs perfil de Netflix\n\n"
                "Si vas a comprar Netflix premium en Perú, te van a ofrecer dos opciones: "
                "**cuenta completa** o **perfil compartido**. Te explicamos cuál te conviene "
                "según tu uso real.\n\n"
                "## Perfil compartido — la opción más popular\n\n"
                "- Compras un perfil dentro de una cuenta de 4 perfiles.\n"
                "- Tienes tu propio perfil con tu PIN.\n"
                "- **No** tienes acceso a la configuración de la cuenta.\n"
                "- **Más barato** (entre S/ 12 y S/ 18 al mes).\n"
                "- Funciona en hasta 2 dispositivos a la vez.\n\n"
                "## Cuenta completa — para uso intensivo o reventa\n\n"
                "- Tú eres el dueño de los 4 perfiles.\n"
                "- Acceso total: cambias el plan, agregas nuevos perfiles.\n"
                "- **Más cara** (entre S/ 45 y S/ 60 al mes).\n"
                "- Pensada para distribuidores que la subdividen, o familias grandes.\n\n"
                "## ¿Cuál elegir?\n\n"
                "**Para una persona o pareja**: perfil compartido. Te ahorras 70% del precio "
                "y la experiencia es exactamente la misma.\n\n"
                "**Si revendes**: cuenta completa. Compras una y la subdivides en 4 perfiles.\n\n"
                "**Familia de 3-4 personas**: depende. Si todos van a usar Netflix al mismo tiempo, "
                "considera 2 perfiles compartidos en lugar de 1 cuenta completa (sale más barato).\n"
            ),
        },
        {
            "title": "Office 365 original vs pirata: por qué no vale la pena ahorrar",
            "slug": "office-365-original-vs-pirata",
            "excerpt": "Por qué los KMS y activadores piratas terminan saliendo más caros. Comparativa real de riesgos, soporte y rendimiento.",
            "category": cats["Software"],
            "seo_keywords": "office 365 original, office pirata, licencia office, kms office",
            "body": (
                "# Office 365 original vs pirata\n\n"
                "El típico debate: ¿pago por una licencia de Office o uso un activador KMS? "
                "Te explicamos los riesgos reales que **no se ven en YouTube**.\n\n"
                "## Lo que pierdes con un Office pirata\n\n"
                "- **Sin actualizaciones de seguridad**: cada vulnerabilidad nueva queda abierta.\n"
                "- **Antivirus lo bloquea**: Windows Defender lo detecta como amenaza.\n"
                "- **Sin OneDrive**: te quedas sin los 1 TB de almacenamiento incluido.\n"
                "- **No funciona en Mac ni iPad**: solo Windows.\n"
                "- **Banneo de cuenta Microsoft**: si activas con KMS y luego inicias sesión con "
                "tu cuenta personal, Microsoft puede suspendértela.\n\n"
                "## Lo que ganas con Office original\n\n"
                "- 6 dispositivos: PC, Mac, iPad, Android.\n"
                "- 1 TB en OneDrive por cuenta.\n"
                "- Outlook, Word, Excel, PowerPoint, Access, Publisher.\n"
                "- Soporte directo de Microsoft.\n"
                "- Actualizaciones automáticas para siempre.\n\n"
                "## ¿Cuánto cuesta realmente?\n\n"
                "Una licencia original Microsoft 365 Family cuesta alrededor de **S/ 280 al año** "
                "para 6 personas. Eso es **S/ 47 por persona al año**.\n\n"
                "Comparado con el riesgo de perder tus archivos en OneDrive o que tu antivirus "
                "te bloquee Word un día antes de entregar tu tesis... no vale la pena.\n\n"
                "> Si tienes presupuesto justo, mejor usa **LibreOffice gratis** que un Office "
                "pirata. Es legal, se actualiza y funciona en Windows, Mac y Linux.\n"
            ),
        },
    ]

    for p in posts:
        BlogPost.objects.create(
            status="published",
            published_at=now,
            **p,
        )


def unseed(apps, schema_editor):
    apps.get_model("blog", "BlogPost").objects.all().delete()
    apps.get_model("blog", "BlogCategory").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("blog", "0001_initial"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
