"""Site-level SEO / PWA / utility endpoints."""
import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import cache_control


@cache_control(public=True, max_age=86400)
def robots_txt(request):
    """Plain-text robots.txt — disallow admin/auth/orders, link sitemap."""
    sitemap_url = request.build_absolute_uri(reverse("django.contrib.sitemaps.views.sitemap"))
    body = "\n".join([
        "User-agent: *",
        "Disallow: /jheliz-admin/",
        "Disallow: /cuenta/",
        "Disallow: /pedidos/",
        "Disallow: /soporte/",
        "Allow: /",
        "",
        f"Sitemap: {sitemap_url}",
        "",
    ])
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


_GOOGLE_VERIFICATION_TOKENS = {
    # Google Search Console verification tokens (one per property).
    "google47b175ffc31eb10e": "google-site-verification: google47b175ffc31eb10e.html",
}


def google_site_verification(request, token):
    """Serve Google Search Console verification HTML files.

    Each token is a property registered in Search Console. Anyone with the
    token in the URL gets the matching response body — Google uses this to
    verify domain ownership.
    """
    body = _GOOGLE_VERIFICATION_TOKENS.get(token)
    if body is None:
        return HttpResponse(status=404)
    return HttpResponse(body, content_type="text/html; charset=utf-8")


@cache_control(public=True, max_age=86400)
def manifest_json(request):
    """PWA manifest — makes the site installable on mobile."""
    icon192 = request.build_absolute_uri("/static/img/icon-192.png")
    icon512 = request.build_absolute_uri("/static/img/icon-512.png")
    return JsonResponse({
        "id": "/?source=pwa",
        "name": "Jheliz Services TV",
        "short_name": "Jheliz",
        "description": "Streaming y licencias al instante en Per\u00fa.",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "background_color": "#07060b",
        "theme_color": "#07060b",
        "orientation": "portrait",
        "lang": "es-PE",
        "icons": [
            {"src": icon192, "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": icon512, "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": icon512, "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "categories": ["shopping", "entertainment"],
        "shortcuts": [
            {
                "name": "Cat\u00e1logo",
                "short_name": "Cat\u00e1logo",
                "url": "/productos/",
                "icons": [{"src": icon192, "sizes": "192x192"}],
            },
            {
                "name": "Mis pedidos",
                "short_name": "Pedidos",
                "url": "/cuenta/",
                "icons": [{"src": icon192, "sizes": "192x192"}],
            },
            {
                "name": "Armar combo",
                "short_name": "Combo",
                "url": "/combos/",
                "icons": [{"src": icon192, "sizes": "192x192"}],
            },
        ],
    })


_SERVICE_WORKER_JS = """// Jheliz PWA service worker
const VERSION = 'jheliz-v2';
const STATIC_CACHE = `static-${VERSION}`;
const RUNTIME_CACHE = `runtime-${VERSION}`;

// Assets that should always work offline (the app shell).
const APP_SHELL = [
  '/',
  '/productos/',
  '/manifest.webmanifest',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(APP_SHELL).catch(() => null))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => ![STATIC_CACHE, RUNTIME_CACHE].includes(k))
            .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// Network-first for documents, cache-first for static assets.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // Don't cache admin, auth, checkout or anything POST-sensitive.
  if (url.pathname.startsWith('/jheliz-admin') ||
      url.pathname.startsWith('/cuenta') ||
      url.pathname.startsWith('/pedidos') ||
      url.pathname.startsWith('/soporte') ||
      url.pathname.startsWith('/distribuidor/panel')) {
    return;
  }
  const isStatic = url.pathname.startsWith('/static/') ||
                   url.pathname.startsWith('/media/') ||
                   /\\.(css|js|png|jpg|jpeg|svg|webp|woff2?|ico)$/i.test(url.pathname);
  if (isStatic) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res && res.ok) {
          const clone = res.clone();
          caches.open(RUNTIME_CACHE).then((c) => c.put(req, clone));
        }
        return res;
      }).catch(() => hit))
    );
    return;
  }
  // Document requests: network first, fallback to cache, fallback to offline page.
  if (req.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(req).then((res) => {
        if (res && res.ok) {
          const clone = res.clone();
          caches.open(RUNTIME_CACHE).then((c) => c.put(req, clone));
        }
        return res;
      }).catch(() =>
        caches.match(req).then((hit) => hit || caches.match('/'))
      )
    );
  }
});
"""


@cache_control(public=True, max_age=3600)
def service_worker(request):
    """PWA service worker served from the site root so its scope covers the whole app."""
    response = HttpResponse(_SERVICE_WORKER_JS, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


def faq(request):
    """Frequently asked questions — also rendered as schema.org FAQPage."""
    items = [
        {
            "q": "\u00bfC\u00f3mo recibo mi cuenta despu\u00e9s de pagar?",
            "a": (
                "Apenas confirmamos tu pago, te enviamos los datos por correo y tambi\u00e9n los ves en"
                " tu panel \u201cMi cuenta\u201d. Si pagaste con Mercado Pago la entrega es autom\u00e1tica;"
                " con Yape, validamos el comprobante en pocos minutos."
            ),
        },
        {
            "q": "\u00bfQu\u00e9 pasa si la cuenta deja de funcionar?",
            "a": (
                "Tienes garant\u00eda durante todo el periodo del plan. Si la cuenta falla, abre un ticket"
                " desde tu panel o escr\u00edbenos al WhatsApp y te reponemos sin preguntas."
            ),
        },
        {
            "q": "\u00bfPuedo cambiar la contrase\u00f1a de la cuenta?",
            "a": (
                "No \u2014 las cuentas son administradas por Jheliz para garantizar el servicio a todos"
                " los perfiles. Si cambias la contrase\u00f1a, se invalida la garant\u00eda."
            ),
        },
        {
            "q": "\u00bfPuedo elegir el nombre y PIN de mi perfil?",
            "a": (
                "Claro. En productos por perfil (Netflix, Disney+, Prime) te pedimos el nombre y un"
                " PIN de 4 d\u00edgitos antes de pagar para crearte el perfil exclusivo."
            ),
        },
        {
            "q": "\u00bfTrabajan con distribuidores / revendedores?",
            "a": (
                "S\u00ed. Reg\u00edstrate como distribuidor en /distribuidor y, una vez aprobado, ver\u00e1s"
                " precios mayoristas y un panel exclusivo con stock en tiempo real."
            ),
        },
        {
            "q": "\u00bfQu\u00e9 m\u00e9todos de pago aceptan?",
            "a": (
                "Mercado Pago (tarjetas, Yape, PagoEfectivo) y Yape directo con QR. Toda la pasarela"
                " es PCI-DSS y nunca vemos los datos de tu tarjeta."
            ),
        },
        {
            "q": "\u00bfMe avisan cuando se vence mi plan?",
            "a": (
                "S\u00ed \u2014 enviamos un correo 3 d\u00edas antes y otro un d\u00eda antes del vencimiento,"
                " con un bot\u00f3n para renovar al toque."
            ),
        },
        {
            "q": "\u00bfPuedo comprar varios planes en un solo pedido?",
            "a": (
                "Por supuesto. Agrega cuantos productos quieras al carrito y los pagas todos juntos."
                " Si un producto se entrega manualmente, te avisamos cuando est\u00e9 listo."
            ),
        },
    ]
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
            }
            for item in items
        ],
    }
    return render(
        request,
        "catalog/faq.html",
        {"faq_items": items, "faq_schema": json.dumps(schema, ensure_ascii=False)},
    )


def status_page(request):
    """Public status page — shows availability of each platform."""
    # Estos estados son editables a futuro desde el admin; por ahora
    # mantenemos la lista en c\u00f3digo para no introducir un modelo nuevo.
    services = [
        {"name": "Netflix", "emoji": "\U0001f3ac", "status": "operational"},
        {"name": "Disney+", "emoji": "\u2728", "status": "operational"},
        {"name": "Prime Video", "emoji": "\U0001f4e6", "status": "operational"},
        {"name": "Spotify", "emoji": "\U0001f3b5", "status": "operational"},
        {"name": "Microsoft Office", "emoji": "\U0001f4be", "status": "operational"},
        {"name": "Windows", "emoji": "\U0001f5a5\ufe0f", "status": "operational"},
        {"name": "Adobe Photoshop", "emoji": "\U0001f3a8", "status": "operational"},
        {"name": "Mercado Pago (pagos)", "emoji": "\U0001f4b3", "status": "operational"},
        {"name": "Yape (pagos)", "emoji": "\U0001f4f1", "status": "operational"},
    ]
    overall_ok = all(s["status"] == "operational" for s in services)
    return render(
        request,
        "catalog/status.html",
        {"services": services, "overall_ok": overall_ok},
    )
