"""SEO público del producto SaaS servido en jheliztv.xyz."""

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


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


@require_GET
def sitemap_xml(request):
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{CANONICAL_ORIGIN}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
'''
    response = HttpResponse(content, content_type="application/xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    return response


def page_not_found(request, exception):
    return render(request, "jheliztv/404.html", status=404)
