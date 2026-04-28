"""Tests para el PR B — cabeceras de seguridad."""

from __future__ import annotations

from django.test import TestCase, override_settings


class SecurityHeadersTests(TestCase):
    def test_csp_header_present(self):
        resp = self.client.get("/")
        self.assertIn("Content-Security-Policy", resp.headers)
        csp = resp.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)

    def test_permissions_policy_present(self):
        resp = self.client.get("/")
        self.assertIn("Permissions-Policy", resp.headers)
        pp = resp.headers["Permissions-Policy"]
        self.assertIn("camera=()", pp)
        self.assertIn("microphone=()", pp)
        self.assertIn("geolocation=()", pp)

    def test_referrer_policy(self):
        resp = self.client.get("/")
        self.assertEqual(
            resp.headers.get("Referrer-Policy"),
            "strict-origin-when-cross-origin",
        )

    def test_x_frame_options_deny(self):
        resp = self.client.get("/")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")

    def test_x_content_type_options_nosniff(self):
        resp = self.client.get("/")
        self.assertEqual(
            resp.headers.get("X-Content-Type-Options"), "nosniff"
        )

    def test_coop_corp_set(self):
        resp = self.client.get("/")
        self.assertEqual(
            resp.headers.get("Cross-Origin-Opener-Policy"), "same-origin"
        )
        self.assertEqual(
            resp.headers.get("Cross-Origin-Resource-Policy"), "same-origin"
        )

    @override_settings(DEBUG=False, SECURE_HSTS_SECONDS=31536000, SECURE_HSTS_PRELOAD=True, SECURE_HSTS_INCLUDE_SUBDOMAINS=True)
    def test_hsts_preload_in_prod(self):
        # SecurityMiddleware sólo escribe HSTS sobre HTTPS; simulamos:
        resp = self.client.get("/", secure=True)
        sts = resp.headers.get("Strict-Transport-Security", "")
        self.assertIn("max-age=31536000", sts)
        self.assertIn("includeSubDomains", sts)
        self.assertIn("preload", sts)
