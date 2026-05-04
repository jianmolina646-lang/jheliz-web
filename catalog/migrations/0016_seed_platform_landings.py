"""Seed de landings SEO para las plataformas más comunes.

Crea landings publicadas con contenido SEO base para Netflix, Disney+, Spotify,
HBO Max, Prime Video y Crunchyroll. Si ya existen (por slug), se saltan.
"""
from django.db import migrations


SEED = [
    {
        "slug": "netflix",
        "name": "Netflix",
        "accent_color": "#e50914",
        "tagline": "Cuentas Netflix premium en perfiles, desde S/ 7 al mes",
        "seo_title": "Netflix Premium barato en Perú — Yape desde S/ 7 | Jheliz",
        "seo_description": "Compra Netflix Premium en Perú al mejor precio. Entrega en minutos, garantía 30 días, pago con Yape o Mercado Pago. Desde S/ 7 al mes.",
        "hero_description": (
            "<p>Disfruta Netflix Premium en UHD 4K, sin publicidad y con todos "
            "los estrenos exclusivos. Perfil propio con tu PIN, sin compartir "
            "con extraños y soporte real 7 días a la semana.</p>"
        ),
        "faq": [
            {"q": "¿La cuenta Netflix es original?", "a": "Sí, todas nuestras cuentas son 100% originales pagadas directamente con la plataforma oficial. Jamás usamos métodos gratuitos ni piratas."},
            {"q": "¿Cuántos dispositivos puedo usar?", "a": "Con Netflix Premium puedes ver simultáneamente hasta 4 dispositivos. Cada perfil es independiente con su propio historial y recomendaciones."},
            {"q": "¿Qué pasa si la cuenta deja de funcionar?", "a": "Reemplazamos tu cuenta gratis dentro de los primeros 30 días. Solo escríbenos por WhatsApp y en minutos te damos una nueva."},
            {"q": "¿Cómo pago?", "a": "Aceptamos Yape, Plin, Mercado Pago y tarjeta. La entrega es automática después del pago verificado."},
            {"q": "¿Puedo cambiar mi perfil y PIN después?", "a": "Sí, cuando te entreguemos el acceso puedes personalizar tu perfil (foto, idioma, controles parentales). El PIN puedes cambiarlo en cualquier momento."},
        ],
    },
    {
        "slug": "disney-plus",
        "name": "Disney+",
        "accent_color": "#0063e5",
        "tagline": "Disney+ Premium con Star+: más de 10 000 películas y series",
        "seo_title": "Disney Plus barato en Perú — desde S/ 5 con garantía | Jheliz",
        "seo_description": "Disney+ con Star+ al mejor precio de Perú. Pixar, Marvel, Star Wars, National Geographic y ESPN en un solo plan. Desde S/ 5 al mes.",
        "hero_description": (
            "<p>Disney+ combinado con Star+ te da acceso a todo el contenido "
            "de Disney, Pixar, Marvel, Star Wars, ESPN y series internacionales "
            "como The Bear, The Kardashians o Only Murders in the Building.</p>"
        ),
        "faq": [
            {"q": "¿Incluye Star+?", "a": "Sí, nuestros planes incluyen Disney+ Premium con Star+ para que veas todo el contenido sin limitaciones."},
            {"q": "¿Calidad 4K UHD?", "a": "Sí, transmitimos en 4K UHD con soporte Dolby Atmos en los dispositivos compatibles."},
            {"q": "¿Funciona en Smart TV y consolas?", "a": "Sí, en Smart TV (Samsung, LG, Android TV), PlayStation, Xbox, Chromecast, Firestick, celulares y laptops."},
            {"q": "¿Tiene garantía?", "a": "Garantía real de 30 días. Si algo no funciona reemplazamos tu cuenta gratis."},
        ],
    },
    {
        "slug": "spotify",
        "name": "Spotify Premium",
        "accent_color": "#1db954",
        "tagline": "Música sin anuncios, descarga offline y audio de alta calidad",
        "seo_title": "Spotify Premium barato en Perú — S/ 8/mes con garantía | Jheliz",
        "seo_description": "Spotify Premium individual al mejor precio de Perú. Sin publicidad, con descargas offline y audio de alta calidad. Desde S/ 8 al mes.",
        "hero_description": (
            "<p>Spotify Premium te da música ilimitada sin anuncios, descargas "
            "offline, audio de alta calidad y mezclas personalizadas. Compatible "
            "con celular, computadora, Alexa, Sonos, PlayStation y Xbox.</p>"
        ),
        "faq": [
            {"q": "¿Es Spotify Premium individual o familiar?", "a": "Ofrecemos ambos planes: individual (1 persona) y familiar (hasta 6 miembros). Elige el que más te convenga en la sección de planes."},
            {"q": "¿Funciona en CarPlay y Android Auto?", "a": "Sí, funciona perfectamente en CarPlay, Android Auto, Alexa, Google Home, Sonos y cualquier dispositivo donde tengas Spotify."},
            {"q": "¿Puedo descargar música para escuchar sin internet?", "a": "Sí, con Spotify Premium descargas hasta 10 000 canciones para escuchar offline desde 5 dispositivos distintos."},
        ],
    },
    {
        "slug": "hbo-max",
        "name": "HBO Max",
        "accent_color": "#9d4ed8",
        "tagline": "HBO, Warner, DC, Cartoon y Harry Potter en un solo plan",
        "seo_title": "HBO Max (Max) barato en Perú — Game of Thrones, DC y más | Jheliz",
        "seo_description": "HBO Max al mejor precio de Perú. Game of Thrones, House of the Dragon, DC, Harry Potter y todos los estrenos de Warner. Desde S/ 8 al mes.",
        "hero_description": (
            "<p>HBO Max (ahora Max) te da acceso a todo el universo HBO, Warner, "
            "DC Comics, Cartoon Network, Discovery y Harry Potter. Desde Game of "
            "Thrones hasta los estrenos recientes de Warner Bros en 4K UHD.</p>"
        ),
        "faq": [
            {"q": "¿Incluye los estrenos de Warner?", "a": "Sí, HBO Max incluye los estrenos de Warner Bros a los 45 días de su estreno en cines, además de las series originales de HBO."},
            {"q": "¿Qué calidad ofrecen?", "a": "Transmitimos en 4K UHD HDR10+ con Dolby Atmos en los dispositivos compatibles."},
        ],
    },
    {
        "slug": "prime-video",
        "name": "Amazon Prime Video",
        "accent_color": "#00a8e1",
        "tagline": "Series exclusivas de Amazon Studios + la mejor Champions League",
        "seo_title": "Prime Video barato en Perú — desde S/ 6 con garantía | Jheliz",
        "seo_description": "Amazon Prime Video al mejor precio de Perú. The Boys, Los Anillos de Poder, Champions League y más. Desde S/ 6 al mes con garantía.",
        "hero_description": (
            "<p>Amazon Prime Video te da acceso a las series más exclusivas como "
            "The Boys, Los Anillos de Poder, Reacher, The Wheel of Time, y además "
            "la Champions League en exclusiva para Perú.</p>"
        ),
        "faq": [
            {"q": "¿Incluye Champions League?", "a": "Sí, Prime Video tiene los derechos exclusivos de la UEFA Champions League en Perú."},
            {"q": "¿Calidad 4K?", "a": "Sí, la mayoría del contenido está en 4K UHD HDR. Algunos títulos están en Full HD según la producción."},
        ],
    },
    {
        "slug": "crunchyroll",
        "name": "Crunchyroll",
        "accent_color": "#f47521",
        "tagline": "Anime en simulcast con doblaje y sin publicidad",
        "seo_title": "Crunchyroll Premium barato en Perú — anime sin anuncios | Jheliz",
        "seo_description": "Crunchyroll Premium al mejor precio de Perú. Todo el anime en simulcast con Japón, sin publicidad, doblaje español latino. Desde S/ 7/mes.",
        "hero_description": (
            "<p>Crunchyroll Premium te da acceso a más de 1 000 series de anime "
            "con simulcast (se emite en Perú al mismo tiempo que en Japón), "
            "doblaje latino y sin publicidad. Incluye One Piece, Jujutsu Kaisen, "
            "Attack on Titan y todos los estrenos.</p>"
        ),
        "faq": [
            {"q": "¿Tiene doblaje al español latino?", "a": "Sí, Crunchyroll ofrece audios en español latino para la mayoría de sus animes populares, además de subtítulos."},
            {"q": "¿Qué es simulcast?", "a": "Simulcast significa que el episodio se emite en Crunchyroll el mismo día que en Japón, con subtítulos instantáneos."},
        ],
    },
]


def create_landings(apps, schema_editor):
    PlatformLanding = apps.get_model("catalog", "PlatformLanding")
    for i, data in enumerate(SEED):
        PlatformLanding.objects.get_or_create(
            slug=data["slug"],
            defaults={**data, "order": i, "is_published": True},
        )


def delete_landings(apps, schema_editor):
    PlatformLanding = apps.get_model("catalog", "PlatformLanding")
    PlatformLanding.objects.filter(
        slug__in=[d["slug"] for d in SEED]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0015_platformlanding"),
    ]

    operations = [
        migrations.RunPython(create_landings, delete_landings),
    ]
