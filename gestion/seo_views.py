"""SEO público del producto SaaS servido en jheliztv.xyz."""

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_safe


CANONICAL_ORIGIN = "https://jheliztv.xyz"


@require_GET
def robots_txt(request):
    content = "\n".join(
        [
            "User-agent: *",
            "Allow: /$",
            "Disallow: /ingresar/",
            "Disallow: /registro/",
            "Disallow: /salir/",
            "Disallow: /control/",
            "Disallow: /app/",
            "Disallow: /suscripcion/",
            "Disallow: /renovar/",
            "Disallow: /meta/",
            "Disallow: /api/",
            "Disallow: /webhooks/",
            "Disallow: /i18n/",
            "Disallow: /media/",
            "Disallow: /*.json$",
            "Disallow: /*?*",
            f"Sitemap: {CANONICAL_ORIGIN}/sitemap.xml",
            "",
        ]
    )
    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_safe
def sitemap_xml(request):
    public_paths = (
        "",
        "funciones/",
        "precios/",
        "como-funciona/",
        "preguntas-frecuentes/",
        "contacto/",
    )
    urls = "\n".join(
        f'''  <url>
    <loc>{CANONICAL_ORIGIN}/{path}</loc>
    <changefreq>weekly</changefreq>
    <priority>{"1.0" if not path else "0.8"}</priority>
  </url>'''
        for path in public_paths
    )
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
'''
    response = HttpResponse(content, content_type="application/xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    return response


def page_not_found(request, exception):
    return render(request, "jheliztv/404.html", status=404)
