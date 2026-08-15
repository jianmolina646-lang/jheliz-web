from django.test import TestCase, override_settings


@override_settings(
    ALLOWED_HOSTS=["jheliztv.xyz", "www.jheliztv.xyz", "testserver"],
    JHELIZTV_HOSTS=["jheliztv.xyz", "www.jheliztv.xyz"],
    SECURE_SSL_REDIRECT=False,
)
class JheliztvSeoTests(TestCase):
    host = "jheliztv.xyz"

    def get(self, path):
        return self.client.get(path, HTTP_HOST=self.host, secure=True)

    def test_landing_has_complete_indexable_metadata(self):
        response = self.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>JHELIZCONTROLTV | Gestión de suscripciones</title>")
        self.assertContains(response, '<link rel="canonical" href="https://jheliztv.xyz/">')
        self.assertContains(response, '<meta property="og:url" content="https://jheliztv.xyz/">')
        self.assertContains(response, 'name="twitter:card" content="summary_large_image"')
        self.assertContains(response, 'type="application/ld+json"')
        self.assertContains(response, '"@type": "WebApplication"')
        self.assertNotIn("X-Robots-Tag", response.headers)
        self.assertEqual(response.content.count(b"<h1"), 1)

    def test_auth_pages_have_unique_metadata_and_are_noindex(self):
        cases = (
            ("/ingresar/", "Iniciar sesión | JHELIZCONTROLTV"),
            ("/registro/", "Crear cuenta | JHELIZCONTROLTV"),
        )
        for path, title in cases:
            with self.subTest(path=path):
                response = self.get(path)
                self.assertContains(response, f"<title>{title}</title>")
                self.assertContains(response, 'name="description"')
                self.assertContains(response, 'name="robots" content="noindex,nofollow,noarchive"')
                self.assertEqual(
                    response.headers["X-Robots-Tag"],
                    "noindex, nofollow, noarchive",
                )
                self.assertEqual(response.content.count(b"<h1"), 1)

    def test_private_and_api_like_routes_are_noindex(self):
        for path in ("/app/", "/control/", "/suscripcion/", "/meta/whatsapp/webhook/"):
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(
                    response.headers["X-Robots-Tag"],
                    "noindex, nofollow, noarchive",
                )

    def test_robots_blocks_private_areas_and_points_to_sitemap(self):
        response = self.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        for directive in (
            "Allow: /$",
            "Disallow: /ingresar/",
            "Disallow: /registro/",
            "Disallow: /control/",
            "Disallow: /app/",
            "Disallow: /api/",
            "Disallow: /media/",
            "Sitemap: https://jheliztv.xyz/sitemap.xml",
        ):
            self.assertContains(response, directive)

    def test_sitemap_contains_public_marketing_pages_only(self):
        response = self.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        for public_path in (
            "",
            "funciones/",
            "precios/",
            "como-funciona/",
            "preguntas-frecuentes/",
            "contacto/",
        ):
            self.assertContains(
                response,
                f"<loc>https://jheliztv.xyz/{public_path}</loc>",
            )
        self.assertEqual(response.content.count(b"<url>"), 6)
        for private_path in ("ingresar", "registro", "app", "control", "renovar"):
            self.assertNotContains(response, private_path)

    def test_www_redirects_to_single_canonical_host(self):
        response = self.client.get(
            "/registro/?source=test",
            HTTP_HOST="www.jheliztv.xyz",
            secure=True,
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://jheliztv.xyz/registro/?source=test",
        )

    @override_settings(DEBUG=False)
    def test_custom_404_is_accessible_and_noindex(self):
        response = self.get("/ruta-que-no-existe/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Página no encontrada", status_code=404)
        self.assertContains(response, "Página no encontrada | JHELIZCONTROLTV", status_code=404)
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow, noarchive")
