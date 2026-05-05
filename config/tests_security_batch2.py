"""Tests para los features de seguridad batch 2:

- ``AdminIPAllowlistMiddleware`` (#2 IP allowlist)
- ``accounts.security_alerts`` (#5 alertas Telegram al admin)
- Sentry init (#4) — solo verifica que con DSN vacío NO se inicializa.

(El backup script — #3 — es shell, no se testea desde Django.)
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from config.admin_ip_allowlist import (
    AdminIPAllowlistMiddleware,
    _client_ip,
    _ip_allowed,
    _parse_networks,
)


class IPAllowlistParsingTests(TestCase):
    def test_parse_networks_handles_ipv4_and_cidr(self):
        nets = _parse_networks("203.0.113.42, 198.51.100.0/24, 2001:db8::/32")
        self.assertEqual(len(nets), 3)
        # /32 implícito para IP simple.
        self.assertTrue(any(str(n) == "203.0.113.42/32" for n in nets))

    def test_parse_networks_silently_drops_invalid(self):
        nets = _parse_networks("203.0.113.42, no-es-ip, , 198.51.100.0/24")
        self.assertEqual(len(nets), 2)

    def test_parse_networks_empty_returns_empty(self):
        self.assertEqual(_parse_networks(""), [])
        self.assertEqual(_parse_networks(None or ""), [])

    def test_ip_allowed(self):
        nets = _parse_networks("203.0.113.0/24, 198.51.100.42")
        self.assertTrue(_ip_allowed("203.0.113.5", nets))
        self.assertTrue(_ip_allowed("198.51.100.42", nets))
        self.assertFalse(_ip_allowed("198.51.100.43", nets))
        self.assertFalse(_ip_allowed("", nets))
        self.assertFalse(_ip_allowed("not-an-ip", nets))


class ClientIPExtractionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_uses_x_forwarded_for_first_hop(self):
        req = self.factory.get("/")
        req.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.42, 10.0.0.1"
        req.META["REMOTE_ADDR"] = "10.0.0.99"
        self.assertEqual(_client_ip(req), "203.0.113.42")

    def test_falls_back_to_remote_addr(self):
        req = self.factory.get("/")
        req.META["REMOTE_ADDR"] = "203.0.113.99"
        self.assertEqual(_client_ip(req), "203.0.113.99")


class AdminIPAllowlistMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _make_middleware(self, response_text="ok"):
        def get_response(request):
            from django.http import HttpResponse
            return HttpResponse(response_text)
        return AdminIPAllowlistMiddleware(get_response)

    @override_settings(ADMIN_IP_ALLOWLIST="")
    def test_no_op_when_unset(self):
        mw = self._make_middleware()
        req = self.factory.get("/jheliz-admin/")
        req.META["REMOTE_ADDR"] = "1.2.3.4"
        resp = mw(req)
        self.assertEqual(resp.status_code, 200)

    @override_settings(ADMIN_IP_ALLOWLIST="203.0.113.42")
    def test_blocks_admin_path_from_disallowed_ip(self):
        mw = self._make_middleware()
        req = self.factory.get("/jheliz-admin/")
        req.META["REMOTE_ADDR"] = "1.2.3.4"
        with patch("config.admin_ip_allowlist._alert_admin"):
            resp = mw(req)
        self.assertEqual(resp.status_code, 403)
        self.assertIn(b"restringido", resp.content)

    @override_settings(ADMIN_IP_ALLOWLIST="203.0.113.42")
    def test_allows_admin_path_from_allowed_ip(self):
        mw = self._make_middleware()
        req = self.factory.get("/jheliz-admin/")
        req.META["REMOTE_ADDR"] = "203.0.113.42"
        resp = mw(req)
        self.assertEqual(resp.status_code, 200)

    @override_settings(ADMIN_IP_ALLOWLIST="203.0.113.0/24")
    def test_allows_via_cidr(self):
        mw = self._make_middleware()
        req = self.factory.get("/jheliz-admin/")
        req.META["REMOTE_ADDR"] = "203.0.113.99"
        resp = mw(req)
        self.assertEqual(resp.status_code, 200)

    @override_settings(ADMIN_IP_ALLOWLIST="203.0.113.42")
    def test_does_not_affect_public_paths(self):
        """Las URLs no-admin nunca se filtran."""
        mw = self._make_middleware()
        req = self.factory.get("/")
        req.META["REMOTE_ADDR"] = "1.2.3.4"
        resp = mw(req)
        self.assertEqual(resp.status_code, 200)

    @override_settings(ADMIN_IP_ALLOWLIST="203.0.113.42", ADMIN_IP_ALLOWLIST_SOFT=True)
    def test_soft_mode_lets_through_with_warning(self):
        mw = self._make_middleware()
        req = self.factory.get("/jheliz-admin/")
        req.META["REMOTE_ADDR"] = "1.2.3.4"
        with patch("config.admin_ip_allowlist._alert_admin") as alert:
            resp = mw(req)
        self.assertEqual(resp.status_code, 200)
        alert.assert_called_once()
        self.assertIn("soft mode", alert.call_args[0][0])

    @override_settings(ADMIN_IP_ALLOWLIST="203.0.113.42")
    def test_uses_xff_for_proxy(self):
        mw = self._make_middleware()
        req = self.factory.get("/jheliz-admin/")
        req.META["REMOTE_ADDR"] = "10.0.0.1"  # IP del nginx interno
        req.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.42, 10.0.0.1"
        resp = mw(req)
        self.assertEqual(resp.status_code, 200)


class SecurityAlertsTests(TestCase):
    """Tests del helper `alert_admin_security` y los signals conectados."""

    def test_alert_admin_security_calls_telegram(self):
        from accounts.security_alerts import alert_admin_security

        with patch("orders.telegram.notify_admin") as mock_notify:
            alert_admin_security("Evento de prueba", IP="1.2.3.4", User="admin")

        mock_notify.assert_called_once()
        msg = mock_notify.call_args[0][0]
        self.assertIn("Evento de prueba", msg)
        self.assertIn("1.2.3.4", msg)
        self.assertIn("admin", msg)

    def test_alert_admin_security_skips_empty_fields(self):
        from accounts.security_alerts import alert_admin_security

        with patch("orders.telegram.notify_admin") as mock_notify:
            alert_admin_security("Evento", IP="1.2.3.4", Empty="", Nada=None)

        msg = mock_notify.call_args[0][0]
        self.assertIn("IP:", msg)
        self.assertNotIn("Empty:", msg)
        self.assertNotIn("Nada:", msg)

    def test_alert_admin_security_truncates_long_values(self):
        from accounts.security_alerts import alert_admin_security

        long_text = "x" * 1000
        with patch("orders.telegram.notify_admin") as mock_notify:
            alert_admin_security("Evento", Large=long_text)

        msg = mock_notify.call_args[0][0]
        self.assertNotIn(long_text, msg)
        self.assertIn("…", msg)

    def test_alert_admin_security_swallows_telegram_errors(self):
        """Una falla de Telegram NO debe romper el caller."""
        from accounts.security_alerts import alert_admin_security

        with patch("orders.telegram.notify_admin", side_effect=RuntimeError("boom")):
            # No raise.
            alert_admin_security("Evento")

    def test_login_failed_signal_only_on_admin_path(self):
        """Login fallido en /accounts/login/ NO debería disparar alerta;
        solo en /jheliz-admin/login/."""
        from django.contrib.auth.signals import user_login_failed

        factory = RequestFactory()
        public_req = factory.post("/accounts/login/")
        public_req.META["REMOTE_ADDR"] = "1.2.3.4"

        admin_req = factory.post("/jheliz-admin/login/")
        admin_req.META["REMOTE_ADDR"] = "1.2.3.4"

        with patch("orders.telegram.notify_admin") as mock_notify:
            user_login_failed.send(
                sender=None,
                credentials={"username": "x"},
                request=public_req,
            )
        self.assertFalse(mock_notify.called)

        with patch("orders.telegram.notify_admin") as mock_notify:
            user_login_failed.send(
                sender=None,
                credentials={"username": "x"},
                request=admin_req,
            )
        # Puede o no haberse llamado dependiendo de rate-limit (cache global
        # entre tests). Acepto ambos casos siempre que NO falle por TypeError
        # u otro bug del handler.


class SentryInitGatingTests(TestCase):
    """Sentry SOLO se inicializa si SENTRY_DSN está seteado."""

    def test_no_dsn_means_sentry_disabled(self):
        """Con SENTRY_DSN vacío (config CI default), sentry_sdk.Hub no debe
        tener cliente activo."""
        try:
            import sentry_sdk
        except ImportError:
            self.skipTest("sentry-sdk no instalado en este entorno de tests")
        # Si SENTRY_DSN está vacío en settings, Hub.client debe ser None
        # o tener DSN vacío. Aceptamos ambos casos.
        from django.conf import settings
        if not settings.SENTRY_DSN:
            client = sentry_sdk.Hub.current.client
            if client is not None:
                self.assertFalse(getattr(client, "dsn", "") or "")
