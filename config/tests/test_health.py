from unittest.mock import patch

from django.test import TestCase, override_settings


@override_settings(SECURE_SSL_REDIRECT=False)
class ReadinessTests(TestCase):
    def test_readiness_checks_database(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "max-age=0, no-cache, no-store, must-revalidate, private")

    @patch("config.health_views.connection.cursor", side_effect=RuntimeError("db down"))
    def test_readiness_fails_closed_without_leaking_details(self, _cursor):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
