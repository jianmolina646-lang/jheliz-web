"""Smoke tests para las mejoras de seguridad del PR A.

- Cifrado transparente de OrderItem.delivered_credentials.
- Compatibilidad backwards con datos en texto plano.
- Auth requerido en /media/payments/proofs/.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Plan, Product
from orders.encryption import EncryptedTextField, decrypt_text, encrypt_text
from orders.models import Order, OrderItem


"""Tests para PR D — features de negocio."""


from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from catalog.models import Category, Plan, Product, StockItem


def _make_order_item(creds: str = "") -> OrderItem:
    cat = Category.objects.create(name="Streaming", slug="streaming")
    product = Product.objects.create(
        name="Netflix Premium", slug="netflix-premium", category=cat
    )
    plan = Plan.objects.create(
        product=product, name="1 mes", duration_days=30,
        price_customer=Decimal("15.00"), price_distributor=Decimal("12.00"),
    )
    order = Order.objects.create(email="cliente@ejemplo.com", total=Decimal("15.00"))
    return OrderItem.objects.create(
        order=order,
        product=product,
        plan=plan,
        product_name=product.name,
        plan_name=plan.name,
        unit_price=plan.price_customer,
        quantity=1,
        delivered_credentials=creds,
    )


class EncryptedFieldTests(TestCase):
    def test_roundtrip(self):
        secret = "email: foo@bar.com\nclave: SuperSecreta123"
        token = encrypt_text(secret)
        self.assertNotEqual(token, secret)
        self.assertTrue(token.startswith("gAAAAA"))
        self.assertEqual(decrypt_text(token), secret)

    def test_field_stores_ciphertext_in_db(self):
        item = _make_order_item("email: foo@bar.com\nclave: secret")
        with connection.cursor() as cur:
            cur.execute(
                "SELECT delivered_credentials FROM orders_orderitem WHERE id = %s",
                [item.pk],
            )
            raw = cur.fetchone()[0]
        # Lo que está en la BD NO es texto plano:
        self.assertNotIn("clave: secret", raw)
        self.assertTrue(raw.startswith("gAAAAA"))

    def test_field_decrypts_on_read(self):
        item = _make_order_item("PIN: 1234")
        item.refresh_from_db()
        self.assertEqual(item.delivered_credentials, "PIN: 1234")

    def test_legacy_plaintext_is_returned_as_is(self):
        item = _make_order_item("placeholder")
        # Sobrescribimos directamente con SQL para simular fila legacy en plano:
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE orders_orderitem SET delivered_credentials = %s WHERE id = %s",
                ["TEXTO_PLANO_LEGACY", item.pk],
            )
        item.refresh_from_db()
        self.assertEqual(item.delivered_credentials, "TEXTO_PLANO_LEGACY")

    def test_field_is_subclass_of_textfield(self):
        from django.db import models
        self.assertTrue(issubclass(EncryptedTextField, models.TextField))


@override_settings(MEDIA_ROOT="/tmp/jheliz-test-media")
class PaymentProofAuthTests(TestCase):
    def setUp(self):
        import os
        path = os.path.join(settings.MEDIA_ROOT, "payments", "proofs")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "test.txt"), "wb") as f:
            f.write(b"comprobante secreto")
        self.url = "/media/payments/proofs/test.txt"

    def test_anonymous_redirected_to_login(self):
        c = Client()
        resp = c.get(self.url)
        self.assertEqual(resp.status_code, 302)
        # LOGIN_URL es "accounts:login" → resuelve a /cuenta/ingresar/.
        self.assertIn("/cuenta/", resp["Location"])
        self.assertIn("next=", resp["Location"])

    def test_non_staff_user_forbidden(self):
        User = get_user_model()
        u = User.objects.create_user(username="cliente", password="x" * 12)
        c = Client()
        c.force_login(u)
        resp = c.get(self.url)
        # user_passes_test redirige al login si falla la condición:
        self.assertEqual(resp.status_code, 302)

    def test_staff_user_can_read(self):
        User = get_user_model()
        u = User.objects.create_user(username="staff", password="x" * 12, is_staff=True)
        c = Client()
        c.force_login(u)
        resp = c.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), b"comprobante secreto")


@override_settings(MEDIA_ROOT="/tmp/jheliz-test-media")
class YapeQrPublicAccessTests(TestCase):
    """El QR del comerciante debe ser visible a compradores invitados.

    El checkout permite pagar sin cuenta, así que servir el QR detrás de
    @login_required hace que el <img> se rompa en celulares sin sesión.
    """

    def setUp(self):
        import os
        path = os.path.join(settings.MEDIA_ROOT, "payments", "yape")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "qr.png"), "wb") as f:
            f.write(b"\x89PNG-fake-qr")
        with open(os.path.join(path, "qr.heic"), "wb") as f:
            f.write(b"fake-heic-bytes")
        with open(os.path.join(path, "qr.weird"), "wb") as f:
            f.write(b"fake-bytes")
        self.url = "/media/payments/yape/qr.png"

    def test_anonymous_user_can_read_qr(self):
        c = Client()
        resp = c.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), b"\x89PNG-fake-qr")

    def test_path_traversal_rejected(self):
        c = Client()
        resp = c.get("/media/payments/yape/../proofs/secret.txt")
        self.assertEqual(resp.status_code, 404)

    def test_png_returns_image_content_type_inline(self):
        """Mobile browsers refuse to render application/octet-stream as image.

        Regression: the QR was served without an explicit Content-Type and
        with no Content-Disposition, which broke rendering on mobile when
        ``X-Content-Type-Options: nosniff`` was set.
        """
        c = Client()
        resp = c.get("/media/payments/yape/qr.png")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")
        self.assertIn("inline", resp["Content-Disposition"])

    def test_heic_returns_image_content_type_for_iphone_uploads(self):
        """iPhone uploads can be HEIC; must serve as image/heic, not octet-stream."""
        c = Client()
        resp = c.get("/media/payments/yape/qr.heic")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/heic")

    def test_unknown_extension_falls_back_to_png(self):
        c = Client()
        resp = c.get("/media/payments/yape/qr.weird")
        self.assertEqual(resp.status_code, 200)
        # Never application/octet-stream — mobile browser with nosniff would refuse.
        self.assertNotEqual(resp["Content-Type"], "application/octet-stream")


# ---------------------------------------------------------------------------
# Verificación de firma del webhook de Mercado Pago.
# ---------------------------------------------------------------------------

import hashlib  # noqa: E402
import hmac as _hmac  # noqa: E402

from unittest.mock import patch as _patch  # noqa: E402

from orders import mercadopago_client  # noqa: E402


def _mp_sign(secret: str, data_id: str, request_id: str, ts: str = "1700000000") -> str:
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    digest = _hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={digest}"


class MercadoPagoSignatureUnitTests(TestCase):
    """Tests unitarios de :func:`mercadopago_client.verify_webhook_signature`."""

    SECRET = "testsecret123"
    DATA_ID = "PAY-42"
    REQ_ID = "abc-req-1"

    def test_valid_signature(self):
        sig = _mp_sign(self.SECRET, self.DATA_ID, self.REQ_ID)
        self.assertTrue(mercadopago_client.verify_webhook_signature(
            signature_header=sig,
            request_id=self.REQ_ID,
            data_id=self.DATA_ID,
            secret=self.SECRET,
        ))

    def test_wrong_secret_rejected(self):
        sig = _mp_sign(self.SECRET, self.DATA_ID, self.REQ_ID)
        self.assertFalse(mercadopago_client.verify_webhook_signature(
            signature_header=sig,
            request_id=self.REQ_ID,
            data_id=self.DATA_ID,
            secret="otro-secreto",
        ))

    def test_tampered_data_id_rejected(self):
        sig = _mp_sign(self.SECRET, self.DATA_ID, self.REQ_ID)
        self.assertFalse(mercadopago_client.verify_webhook_signature(
            signature_header=sig,
            request_id=self.REQ_ID,
            data_id="OTRO-PAYMENT",  # el atacante cambió el id en la URL
            secret=self.SECRET,
        ))

    def test_tampered_request_id_rejected(self):
        sig = _mp_sign(self.SECRET, self.DATA_ID, self.REQ_ID)
        self.assertFalse(mercadopago_client.verify_webhook_signature(
            signature_header=sig,
            request_id="otro-req",
            data_id=self.DATA_ID,
            secret=self.SECRET,
        ))

    def test_missing_secret_returns_false(self):
        sig = _mp_sign(self.SECRET, self.DATA_ID, self.REQ_ID)
        self.assertFalse(mercadopago_client.verify_webhook_signature(
            signature_header=sig,
            request_id=self.REQ_ID,
            data_id=self.DATA_ID,
            secret="",
        ))

    def test_malformed_header_returns_false(self):
        for bad in ("", "garbage", "ts=", "v1=foo", "ts=1,v1="):
            self.assertFalse(mercadopago_client.verify_webhook_signature(
                signature_header=bad,
                request_id=self.REQ_ID,
                data_id=self.DATA_ID,
                secret=self.SECRET,
            ))


@override_settings(MERCADOPAGO_WEBHOOK_SECRET="testsecret123")
class MercadoPagoWebhookViewTests(TestCase):
    """Tests del view :func:`orders.views.mercadopago_webhook`."""

    SECRET = "testsecret123"
    DATA_ID = "PAY-99"
    REQ_ID = "req-xyz"
    URL = f"/pedidos/webhooks/mercadopago/?data.id={DATA_ID}"

    def _post(self, **headers):
        # ``Client`` traduce kwargs HTTP_FOO a header Foo (formato Django).
        return self.client.post(
            self.URL,
            data='{"data": {"id": "%s"}}' % self.DATA_ID,
            content_type="application/json",
            **headers,
        )

    def test_unsigned_request_rejected(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 401)

    def test_invalid_signature_rejected(self):
        resp = self._post(
            HTTP_X_SIGNATURE="ts=1700000000,v1=deadbeef",
            HTTP_X_REQUEST_ID=self.REQ_ID,
        )
        self.assertEqual(resp.status_code, 401)

    def test_valid_signature_accepted(self):
        sig = _mp_sign(self.SECRET, self.DATA_ID, self.REQ_ID)
        # Mockeamos fetch_payment para no llamar a la API real.
        with _patch.object(
            mercadopago_client, "fetch_payment",
            return_value={"status": "pending", "external_reference": ""},
        ) as mocked:
            resp = self._post(
                HTTP_X_SIGNATURE=sig,
                HTTP_X_REQUEST_ID=self.REQ_ID,
            )
        self.assertEqual(resp.status_code, 200)
        mocked.assert_called_once_with(self.DATA_ID)

    def test_attacker_cannot_replay_with_different_data_id(self):
        """Replay clásico: atacante toma una firma legítima de otro pago y
        la usa contra ``data.id=OTRO`` — debe rechazarse.
        """
        sig = _mp_sign(self.SECRET, self.DATA_ID, self.REQ_ID)
        url = "/pedidos/webhooks/mercadopago/?data.id=OTRO_PAGO"
        resp = self.client.post(
            url,
            data='{"data": {"id": "OTRO_PAGO"}}',
            content_type="application/json",
            HTTP_X_SIGNATURE=sig,
            HTTP_X_REQUEST_ID=self.REQ_ID,
        )
        self.assertEqual(resp.status_code, 401)


@override_settings(MERCADOPAGO_WEBHOOK_SECRET="")
class MercadoPagoWebhookFallbackTests(TestCase):
    """Si el secreto no está configurado, el webhook acepta sin verificar
    pero loguea un warning. Ese fallback existe para no romper el flujo de
    pagos durante el rollout — el operador completa el setup del secreto y
    en el próximo deploy se activa la verificación automáticamente.
    """

    def test_unsigned_request_passes_through_when_secret_missing(self):
        with _patch.object(
            mercadopago_client, "fetch_payment",
            return_value={"status": "pending", "external_reference": ""},
        ) as mocked:
            resp = self.client.post(
                "/pedidos/webhooks/mercadopago/?data.id=PAY-1",
                data='{"data": {"id": "PAY-1"}}',
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        mocked.assert_called_once_with("PAY-1")


# ----- PR D -----

def _make_setup():
    cat = Category.objects.create(name="Streaming", slug="streaming")
    product = Product.objects.create(
        name="Netflix Premium", slug="netflix-premium", category=cat
    )
    plan = Plan.objects.create(
        product=product, name="1 mes", duration_days=30,
        price_customer=Decimal("15.00"), price_distributor=Decimal("12.00"),
        low_stock_threshold=3,
    )
    return product, plan


def _make_delivered_item(*, days_until_expiry: int, email: str = "cliente@ejemplo.com"):
    product, plan = _make_setup()
    order = Order.objects.create(
        email=email, total=Decimal("15.00"), status=Order.Status.DELIVERED,
    )
    return OrderItem.objects.create(
        order=order,
        product=product,
        plan=plan,
        product_name=product.name,
        plan_name=plan.name,
        unit_price=plan.price_customer,
        quantity=1,
        expires_at=timezone.now() + timedelta(days=days_until_expiry),
    )


class ExpiryReminderTests(TestCase):
    def test_sends_3d_reminder(self):
        item = _make_delivered_item(days_until_expiry=3)
        out = StringIO()
        call_command("send_expiry_reminders", stdout=out)
        item.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("3 días", mail.outbox[0].subject)
        self.assertIsNotNone(item.expiry_reminder_3d_sent_at)

    def test_sends_1d_reminder(self):
        item = _make_delivered_item(days_until_expiry=1)
        call_command("send_expiry_reminders", stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("mañana", mail.outbox[0].subject)
        self.assertIsNotNone(item.expiry_reminder_1d_sent_at)

    def test_does_not_resend(self):
        _make_delivered_item(days_until_expiry=3)
        call_command("send_expiry_reminders", stdout=StringIO())
        call_command("send_expiry_reminders", stdout=StringIO())
        # Sólo una vez:
        self.assertEqual(len(mail.outbox), 1)

    def test_dry_run_does_not_send(self):
        item = _make_delivered_item(days_until_expiry=3)
        call_command("send_expiry_reminders", "--dry-run", stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(item.expiry_reminder_3d_sent_at)

    def test_skips_orders_without_email(self):
        _make_delivered_item(days_until_expiry=3, email="")
        call_command("send_expiry_reminders", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_skips_non_delivered_orders(self):
        item = _make_delivered_item(days_until_expiry=3)
        item.order.status = Order.Status.PENDING
        item.order.save()
        call_command("send_expiry_reminders", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)


class LowStockAlertTests(TestCase):
    def setUp(self):
        self.product, self.plan = _make_setup()

    def _add_stock(self, n: int):
        for i in range(n):
            StockItem.objects.create(
                product=self.product, plan=self.plan,
                credentials=f"creds-{i}",
            )

    @patch("orders.telegram.notify_admin")
    def test_alert_when_below_threshold(self, mock_notify):
        self._add_stock(2)  # umbral es 3
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
        mock_notify.assert_called_once()
        msg = mock_notify.call_args[0][0]
        self.assertIn("Netflix Premium", msg)
        self.assertIn("2/3", msg)
        self.plan.refresh_from_db()
        self.assertIsNotNone(self.plan.low_stock_alert_sent_at)

    @patch("orders.telegram.notify_admin")
    def test_no_alert_when_at_threshold(self, mock_notify):
        self._add_stock(3)
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
        mock_notify.assert_not_called()

    @patch("orders.telegram.notify_admin")
    def test_does_not_realert_within_cooldown(self, mock_notify):
        self._add_stock(1)
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
            call_command("check_low_stock", stdout=StringIO())
        self.assertEqual(mock_notify.call_count, 1)

    @patch("orders.telegram.notify_admin")
    def test_clears_flag_when_stock_recovers(self, mock_notify):
        self._add_stock(1)
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
        self.plan.refresh_from_db()
        self.assertIsNotNone(self.plan.low_stock_alert_sent_at)

        # Repón stock
        self._add_stock(5)
        with patch("orders.telegram.is_configured", return_value=True):
            call_command("check_low_stock", stdout=StringIO())
        self.plan.refresh_from_db()
        self.assertIsNone(self.plan.low_stock_alert_sent_at)


class AuditLogTests(TestCase):
    def test_orderitem_changes_create_log_entries(self):
        from auditlog.models import LogEntry

        item = _make_delivered_item(days_until_expiry=10)
        # La creación ya generó una entrada:
        self.assertGreaterEqual(
            LogEntry.objects.get_for_object(item).count(), 1
        )
        item.delivered_credentials = "secreto"
        item.save()
        # El cambio en delivered_credentials NO se guarda en el log
        # (configurado en orders.apps.OrdersConfig.ready):
        latest = LogEntry.objects.get_for_object(item).order_by("-timestamp").first()
        if latest and latest.changes_dict:
            self.assertNotIn("delivered_credentials", latest.changes_dict)


# --------------------------------------------------------------------------
# Tests para Cupones
# --------------------------------------------------------------------------

from orders.models import Coupon  # noqa: E402


class CouponTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Streaming", slug="streaming")
        self.product = Product.objects.create(
            name="Netflix Premium", slug="netflix-premium", category=self.cat,
            is_active=True, requires_customer_profile_data=False,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes",
            price_customer=Decimal("20.00"),
            is_active=True,
        )

    def test_percent_discount_calculation(self):
        c = Coupon.objects.create(code="OFF10", discount_type="percent", discount_value=Decimal("10"))
        self.assertEqual(c.compute_discount(Decimal("100")), Decimal("10.00"))

    def test_fixed_discount_does_not_exceed_subtotal(self):
        c = Coupon.objects.create(code="OFF50", discount_type="fixed", discount_value=Decimal("50"))
        self.assertEqual(c.compute_discount(Decimal("30")), Decimal("30"))

    def test_inactive_coupon_not_eligible(self):
        c = Coupon.objects.create(
            code="DISABLED", discount_type="percent",
            discount_value=Decimal("10"), is_active=False,
        )
        ok, _ = c.is_eligible_for(None, Decimal("100"))
        self.assertFalse(ok)

    def test_min_order_total_enforced(self):
        c = Coupon.objects.create(
            code="MIN50", discount_type="percent",
            discount_value=Decimal("10"), min_order_total=Decimal("50"),
        )
        ok, msg = c.is_eligible_for(None, Decimal("30"))
        self.assertFalse(ok)
        self.assertIn("mínimo", msg.lower())

    def test_max_uses_global_cap(self):
        c = Coupon.objects.create(
            code="LIMITED", discount_type="percent",
            discount_value=Decimal("10"), max_uses=1, times_used=1,
        )
        self.assertFalse(c.is_currently_valid())

    def test_code_normalized_to_uppercase(self):
        c = Coupon.objects.create(
            code="  hola amigos  ", discount_type="percent",
            discount_value=Decimal("5"),
        )
        self.assertEqual(c.code, "HOLAAMIGOS")

    def test_apply_and_remove_coupon_via_views(self):
        c = Coupon.objects.create(code="WELCOME10", discount_type="percent", discount_value=Decimal("10"))
        client = Client()
        # Add an item to the cart
        client.post(reverse("orders:add_to_cart"), data={
            "plan_id": self.plan.id, "quantity": 1,
        })
        # Apply coupon
        resp = client.post(reverse("orders:cart_apply_coupon"), data={"code": "WELCOME10"})
        self.assertEqual(resp.status_code, 302)
        # Cart total should reflect the 10% discount
        resp = client.get(reverse("orders:cart"))
        # subtotal 20.00, discount 2.00, total 18.00
        self.assertContains(resp, "WELCOME10")
        # Format may use locale-specific comma (S/ 18,00) or period (18.00).
        body = resp.content.decode("utf-8")
        self.assertTrue("18,00" in body or "18.00" in body, "Total con descuento no encontrado en la respuesta.")
        # Remove coupon
        resp = client.post(reverse("orders:cart_remove_coupon"))
        self.assertEqual(resp.status_code, 302)
        resp = client.get(reverse("orders:cart"))
        self.assertNotContains(resp, "WELCOME10")

    def test_unknown_coupon_rejected(self):
        client = Client()
        client.post(reverse("orders:add_to_cart"), data={
            "plan_id": self.plan.id, "quantity": 1,
        })
        resp = client.post(reverse("orders:cart_apply_coupon"), data={"code": "NOPE"})
        self.assertEqual(resp.status_code, 302)
        # Following the redirect should show an error message
        resp = client.get(reverse("orders:cart"))
        self.assertContains(resp, "no existe")


class OrderTimelineTests(TestCase):
    """Validación de Order.get_timeline() — bitácora combinando fuentes."""

    def setUp(self):
        cat = Category.objects.create(name="Streaming", slug="streaming-t")
        product = Product.objects.create(
            name="Netflix", slug="netflix-timeline", category=cat,
        )
        plan = Plan.objects.create(
            product=product, name="1 mes", duration_days=30,
            price_customer=Decimal("15.00"), price_distributor=Decimal("12.00"),
        )
        self.order = Order.objects.create(
            email="t@ejemplo.com", total=Decimal("15.00"), currency="PEN",
        )
        OrderItem.objects.create(
            order=self.order, product=product, plan=plan,
            product_name=product.name, plan_name=plan.name,
            unit_price=Decimal("15.00"), quantity=1,
        )

    def test_created_event_always_present(self):
        events = self.order.get_timeline()
        kinds = [e["kind"] for e in events]
        self.assertIn("order_created", kinds)

    def test_emails_appear_in_timeline(self):
        from orders.models import EmailLog
        EmailLog.objects.create(
            kind=EmailLog.Kind.ORDER_RECEIVED,
            status=EmailLog.Status.SENT,
            to_email=self.order.email,
            subject="Recibimos tu pedido",
            order=self.order,
        )
        events = self.order.get_timeline()
        email_events = [e for e in events if e["kind"].startswith("email_")]
        self.assertEqual(len(email_events), 1)
        self.assertIn("Recibimos tu pedido", email_events[0]["title"])

    def test_status_change_via_auditlog_appears(self):
        # Cambiar status => auditlog capta el cambio.
        self.order.status = Order.Status.PAID
        self.order.save(update_fields=["status"])
        events = self.order.get_timeline()
        kinds = [e["kind"] for e in events]
        self.assertTrue(any(k.startswith("status_") for k in kinds),
                        f"No se encontró evento status_* en: {kinds}")

    def test_timeline_sorted_desc(self):
        from orders.models import EmailLog
        now = timezone.now()
        # Forzamos timestamps controlados: paid_at = ahora + 1h
        self.order.paid_at = now + timedelta(hours=1)
        self.order.delivered_at = now + timedelta(hours=2)
        self.order.save(update_fields=["paid_at", "delivered_at"])
        EmailLog.objects.create(
            kind=EmailLog.Kind.ORDER_DELIVERED,
            status=EmailLog.Status.SENT,
            to_email=self.order.email, subject="Entregado",
            order=self.order,
        )
        events = self.order.get_timeline()
        # más reciente primero
        for prev, nxt in zip(events, events[1:]):
            self.assertGreaterEqual(prev["timestamp"], nxt["timestamp"])

    def test_failed_email_shown_as_error(self):
        from orders.models import EmailLog
        EmailLog.objects.create(
            kind=EmailLog.Kind.ORDER_DELIVERED,
            status=EmailLog.Status.FAILED,
            to_email=self.order.email, subject="Entregado",
            order=self.order, error="SMTP timeout",
        )
        events = self.order.get_timeline()
        failed = [e for e in events if "Falló envío" in e["title"]]
        self.assertEqual(len(failed), 1)
        self.assertIn("SMTP", failed[0]["description"])


class YapeInboxTests(TestCase):
    """Bandeja de verificación Yape en el admin."""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="staff-inbox", password="x", is_staff=True, is_superuser=True,
        )
        cat = Category.objects.create(name="Streaming", slug="streaming-inbox")
        self.product = Product.objects.create(
            name="Netflix", slug="netflix-inbox", category=cat,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("15.00"), price_distributor=Decimal("12.00"),
        )

    def _make_yape_order(self, **overrides):
        defaults = dict(
            email="x@ejemplo.com",
            total=Decimal("15.00"),
            currency="PEN",
            payment_provider="yape",
            status=Order.Status.VERIFYING,
            payment_proof="payments/proofs/test.jpg",
            payment_proof_uploaded_at=timezone.now(),
        )
        defaults.update(overrides)
        order = Order.objects.create(**defaults)
        OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=Decimal("15.00"), quantity=1,
        )
        return order

    def test_inbox_renders_only_verifying_yape_with_proof(self):
        ok = self._make_yape_order()
        # Estos NO deberían aparecer:
        self._make_yape_order(status=Order.Status.PAID)  # ya pagado
        self._make_yape_order(payment_proof="")  # sin comprobante
        self._make_yape_order(payment_provider="mercadopago")  # no es Yape

        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin:orders_order_yape_inbox"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, ok.short_uuid)
        # Etiqueta de "1 pendiente" (len(orders)==1)
        self.assertContains(resp, "1 pendiente")

    def test_inbox_empty_state(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin:orders_order_yape_inbox"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bandeja vacía")

    def test_inbox_requires_staff(self):
        User = get_user_model()
        cliente = User.objects.create_user(
            username="cliente-inbox", password="x", is_staff=False,
        )
        self.client.force_login(cliente)
        resp = self.client.get(reverse("admin:orders_order_yape_inbox"))
        # admin_view redirige a login si no sos staff
        self.assertIn(resp.status_code, (302, 403))

    def test_reject_from_inbox_redirects_back(self):
        order = self._make_yape_order()
        self.client.force_login(self.admin)
        url = reverse("admin:orders_order_reject_yape", args=[order.pk])
        # Simular referer desde la bandeja
        resp = self.client.post(
            url, data={"reason": "prueba"},
            HTTP_REFERER="http://testserver" + reverse("admin:orders_order_yape_inbox"),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("yape-inbox", resp["Location"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_rejection_reason, "prueba")


class OrdersKanbanTests(TestCase):
    """Vista Kanban del admin."""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="staff-kanban", password="x", is_staff=True, is_superuser=True,
        )

    def _order(self, status, created_at=None):
        o = Order.objects.create(
            email="k@ejemplo.com", total=Decimal("10.00"),
            currency="PEN", status=status, payment_provider="yape",
        )
        if created_at:
            Order.objects.filter(pk=o.pk).update(created_at=created_at)
        return o

    def test_kanban_renders_all_columns(self):
        self._order(Order.Status.PENDING)
        self._order(Order.Status.VERIFYING)
        self._order(Order.Status.PAID)
        self._order(Order.Status.DELIVERED)
        self._order(Order.Status.CANCELED)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin:orders_order_kanban"))
        self.assertEqual(resp.status_code, 200)
        for label in ["Pendiente de pago", "Verificando", "En preparación",
                      "Entregado", "Cerrados"]:
            self.assertContains(resp, label)

    def test_kanban_filters_by_days(self):
        old = self._order(Order.Status.DELIVERED, created_at=timezone.now() - timedelta(days=45))
        recent = self._order(Order.Status.DELIVERED)
        self.client.force_login(self.admin)
        # default 30 días: el viejo no aparece
        resp = self.client.get(reverse("admin:orders_order_kanban"))
        self.assertNotContains(resp, f"#{old.short_uuid}")
        self.assertContains(resp, f"#{recent.short_uuid}")
        # 90 días: aparecen ambos
        resp = self.client.get(reverse("admin:orders_order_kanban") + "?days=90")
        self.assertContains(resp, f"#{old.short_uuid}")

    def test_kanban_invalid_days_falls_back_to_default(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin:orders_order_kanban") + "?days=abc")
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse("admin:orders_order_kanban") + "?days=-1")
        self.assertEqual(resp.status_code, 200)
        # 99999 clamp a 365
        resp = self.client.get(reverse("admin:orders_order_kanban") + "?days=99999")
        self.assertEqual(resp.status_code, 200)

    def test_kanban_requires_staff(self):
        User = get_user_model()
        cliente = User.objects.create_user(
            username="cliente-kanban", password="x", is_staff=False,
        )
        self.client.force_login(cliente)
        resp = self.client.get(reverse("admin:orders_order_kanban"))
        self.assertIn(resp.status_code, (302, 403))

    def test_kanban_merges_paid_and_preparing_into_one_column(self):
        a = self._order(Order.Status.PAID)
        b = self._order(Order.Status.PREPARING)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin:orders_order_kanban"))
        self.assertContains(resp, f"#{a.short_uuid}")
        self.assertContains(resp, f"#{b.short_uuid}")


class GlobalSearchTests(TestCase):
    """Endpoint /jheliz-admin/search/ con y sin ?full=1."""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="staff-search", password="x", is_staff=True, is_superuser=True,
        )
        cat = Category.objects.create(name="Streaming", slug="streaming-search")
        self.product = Product.objects.create(
            name="Netflix Premium Buscable", slug="netflix-buscable", category=cat,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("15.00"), price_distributor=Decimal("12.00"),
        )

    def test_json_search_by_email(self):
        Order.objects.create(
            email="buscable@ejemplo.com", total=Decimal("15.00"), currency="PEN",
        )
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_global_search") + "?q=buscable")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["orders"]), 1)
        self.assertIn("buscable", data["orders"][0]["label"].lower())

    def test_json_search_by_telegram_username(self):
        Order.objects.create(
            telegram_username="@pepito", total=Decimal("15.00"),
            phone="999", currency="PEN",
        )
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_global_search") + "?q=pepito")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["orders"]), 1)

    def test_json_search_by_uuid_partial(self):
        order = Order.objects.create(
            email="x@e.com", total=Decimal("10"), currency="PEN",
        )
        partial = str(order.uuid)[:6]
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_global_search") + f"?q={partial}")
        data = resp.json()
        self.assertEqual(len(data["orders"]), 1)

    def test_json_short_query_returns_empty(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_global_search") + "?q=a")
        data = resp.json()
        self.assertEqual(data, {"orders": [], "customers": [], "products": [], "plans": [], "tickets": []})

    def test_full_results_page(self):
        Order.objects.create(email="buscable@ejemplo.com", total=Decimal("15.00"))
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_global_search") + "?q=buscable&full=1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Búsqueda global")
        self.assertContains(resp, "buscable@ejemplo.com")

    def test_full_results_page_empty_query(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_global_search") + "?full=1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "al menos 2 caracteres")

    def test_search_requires_staff(self):
        User = get_user_model()
        u = User.objects.create_user(username="cliente-s", password="x", is_staff=False)
        self.client.force_login(u)
        resp = self.client.get(reverse("admin_global_search") + "?q=test")
        self.assertIn(resp.status_code, (302, 403))

    def test_search_customers_by_phone(self):
        User = get_user_model()
        User.objects.create_user(
            username="tel-client", password="x", phone="987654321",
        )
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_global_search") + "?q=987654321")
        data = resp.json()
        self.assertGreaterEqual(len(data["customers"]), 1)

    def test_search_products(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_global_search") + "?q=Buscable")
        data = resp.json()
        self.assertGreaterEqual(len(data["products"]), 1)


class ReplaceAccountCredentialsTests(TestCase):
    """Reemplazo seguro de correo/contraseña en items ya entregados."""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="staff-rep", password="x",
            is_staff=True, is_superuser=True,
        )
        self.cliente = User.objects.create_user(
            username="cliente-rep", password="x", email="c@ejemplo.com",
        )
        # distribuidor aprobado (según User.is_distributor)
        self.distri = User.objects.create_user(
            username="distri-rep", password="x", email="d@ejemplo.com",
        )
        self.distri.role = "distribuidor"
        self.distri.distributor_approved = True
        self.distri.save()

        cat = Category.objects.create(name="Streaming", slug="streaming-rep")
        self.product = Product.objects.create(
            name="Amazon", slug="amazon-rep", category=cat,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("20.00"), price_distributor=Decimal("15.00"),
        )

    def _make_item(self, *, user=None, creds="", profile="Juan", pin="1234"):
        order = Order.objects.create(
            user=user, email=(user.email if user else "guest@ejemplo.com"),
            total=Decimal("20.00"), currency="PEN",
            status=Order.Status.DELIVERED,
        )
        return OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=Decimal("20.00"), quantity=1,
            requested_profile_name=profile, requested_pin=pin,
            delivered_credentials=creds,
        )

    def test_parse_credentials(self):
        from orders import credentials as c
        parsed = c.parse(
            "Correo: old@amazon.com\nContraseña: oldpass\nPerfil: Juan\nPIN: 1234"
        )
        self.assertEqual(parsed.email, "old@amazon.com")
        self.assertEqual(parsed.password, "oldpass")
        self.assertTrue(parsed.has_email_line)
        self.assertTrue(parsed.has_password_line)

    def test_replace_keeps_profile_and_pin(self):
        from orders import credentials as c
        original = (
            "Correo: old@amazon.com\n"
            "Contraseña: oldpass\n"
            "Perfil: Juan\n"
            "PIN: 1234\n"
        )
        new = c.replace_account(original, "new@amazon.com", "newpass")
        self.assertIn("Correo: new@amazon.com", new)
        self.assertIn("Contraseña: newpass", new)
        self.assertIn("Perfil: Juan", new)
        self.assertIn("PIN: 1234", new)
        self.assertNotIn("old@amazon.com", new)
        self.assertNotIn("oldpass", new)

    def test_replace_preserves_label_style(self):
        from orders import credentials as c
        # admin usó "Email:" en lugar de "Correo:"
        new = c.replace_account(
            "Email: a@a.com\nPassword: p\nPerfil: X",
            "b@b.com", "q",
        )
        self.assertIn("Email: b@b.com", new)
        self.assertIn("Password: q", new)

    def test_preview_shows_old_email_and_role(self):
        item_c = self._make_item(
            user=self.cliente,
            creds="Correo: old@amazon.com\nContraseña: oldpass\nPerfil: Juan\nPIN: 1234",
        )
        item_d = self._make_item(
            user=self.distri,
            creds="Correo: old@amazon.com\nContraseña: oldpass\nPerfil: Full",
        )
        self.client.force_login(self.admin)
        url = reverse("admin:orders_orderitem_replace_account")
        resp = self.client.get(f"{url}?ids={item_c.pk}&ids={item_d.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "old@amazon.com")
        self.assertContains(resp, "oldpass")
        self.assertContains(resp, "Cliente")
        self.assertContains(resp, "Distribuidor")

    def test_submit_updates_credentials_and_snapshot(self):
        item = self._make_item(
            user=self.cliente,
            creds="Correo: old@amazon.com\nContraseña: oldpass\nPerfil: Juan\nPIN: 1234",
        )
        self.client.force_login(self.admin)
        url = reverse("admin:orders_orderitem_replace_account")
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(url, data={
                "confirm": "1",
                "ids": str(item.pk),
                "apply": str(item.pk),
                "new_email": "new@amazon.com",
                "new_password": "newpass",
                "confirm_email": "new@amazon.com",
                "notify": "on",
            })
        self.assertEqual(resp.status_code, 302)
        item.refresh_from_db()
        self.assertIn("Correo: new@amazon.com", item.delivered_credentials)
        self.assertIn("Contraseña: newpass", item.delivered_credentials)
        self.assertIn("Perfil: Juan", item.delivered_credentials)
        self.assertIn("old@amazon.com", item.previous_delivered_credentials)
        self.assertIsNotNone(item.credentials_replaced_at)
        # Email enviado
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Actualizamos tu cuenta", mail.outbox[0].subject)

    def test_submit_rejects_when_emails_dont_match(self):
        item = self._make_item(
            user=self.cliente,
            creds="Correo: old@amazon.com\nContraseña: x\nPerfil: Y",
        )
        self.client.force_login(self.admin)
        url = reverse("admin:orders_orderitem_replace_account")
        resp = self.client.post(url, data={
            "confirm": "1",
            "ids": str(item.pk),
            "apply": str(item.pk),
            "new_email": "new@amazon.com",
            "new_password": "np",
            "confirm_email": "otro@amazon.com",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "confirmación no coincide")
        item.refresh_from_db()
        # Sin cambios
        self.assertIn("old@amazon.com", item.delivered_credentials)
        self.assertEqual(item.previous_delivered_credentials, "")

    def test_distributor_gets_distributor_email(self):
        item = self._make_item(
            user=self.distri,
            creds="Correo: old@amazon.com\nContraseña: x\nPerfil: Full",
        )
        self.client.force_login(self.admin)
        url = reverse("admin:orders_orderitem_replace_account")
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(url, data={
                "confirm": "1",
                "ids": str(item.pk),
                "apply": str(item.pk),
                "new_email": "new@amazon.com",
                "new_password": "np",
                "confirm_email": "new@amazon.com",
                "notify": "on",
            })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        # Distribuidor tiene la mención de reenviar a sus clientes finales.
        self.assertIn("clientes finales", body)

    def test_rollback_restores_previous_credentials(self):
        from orders import credentials as c
        item = self._make_item(
            user=self.cliente,
            creds="Correo: old@amazon.com\nContraseña: oldpass\nPerfil: Juan\nPIN: 1234",
        )
        # Aplicar reemplazo simulado
        item.previous_delivered_credentials = item.delivered_credentials
        item.delivered_credentials = c.replace_account(
            item.delivered_credentials, "new@amazon.com", "newpass",
        )
        item.credentials_replaced_at = timezone.now()
        item.save()

        # Usar la action de rollback
        self.client.force_login(self.admin)
        from django.contrib.admin.sites import site
        from orders.admin import OrderItemAdmin
        admin_instance = site._registry[OrderItem]
        from django.test import RequestFactory
        rf = RequestFactory()
        req = rf.post("/")
        req.user = self.admin
        # Emular messages framework
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, "session", self.client.session)
        setattr(req, "_messages", FallbackStorage(req))
        qs = OrderItem.objects.filter(pk=item.pk)
        admin_instance.action_rollback_replacement(req, qs)
        item.refresh_from_db()
        self.assertIn("old@amazon.com", item.delivered_credentials)
        self.assertIn("oldpass", item.delivered_credentials)
        self.assertEqual(item.previous_delivered_credentials, "")
        self.assertIsNone(item.credentials_replaced_at)

    def test_view_requires_staff(self):
        self.client.force_login(self.cliente)
        url = reverse("admin:orders_orderitem_replace_account")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (302, 403))





class CartBulkTests(TestCase):
    """Cubre flujo de carrito con cantidad > 1 para distribuidores."""

    def setUp(self):
        User = get_user_model()
        self.client = Client()
        self.distri = User.objects.create_user(
            username="cart_distri", password="x",
            email="cart_distri@example.com",
            role="distribuidor", distributor_approved=True,
        )
        self.cliente = User.objects.create_user(
            username="cart_cli", password="x", email="cli@example.com", role="cliente",
        )
        self.cat = Category.objects.create(name="Streaming", slug="streaming-bulk")
        self.prod = Product.objects.create(
            category=self.cat, name="Netflix", slug="netflix-bulk",
            is_active=True, requires_customer_profile_data=True,
        )
        self.plan = Plan.objects.create(
            product=self.prod, name="1 mes", duration_days=30,
            price_customer=Decimal("20.00"), price_distributor=Decimal("12.00"),
            available_for_distributor=True, is_active=True, order=1,
        )

    def test_distributor_qty_gt_1_creates_n_lines(self):
        self.client.force_login(self.distri)
        resp = self.client.post(reverse("orders:add_to_cart"), {
            "plan_id": self.plan.pk,
            "quantity": 5,
            "profile_name": "",
            "pin": "",
            "notes": "",
        })
        self.assertEqual(resp.status_code, 302)
        cart = self.client.session.get("cart")
        self.assertEqual(len(cart), 5)
        for it in cart:
            self.assertEqual(it["quantity"], 1)
            self.assertEqual(it["profile_name"], "")
            self.assertEqual(it["pin"], "")

    def test_customer_qty_gt_1_keeps_single_line_with_qty(self):
        # Cliente normal con quantity > 1 → carrito mantiene 1 línea con quantity = N.
        # Necesita perfil/PIN obligatorio.
        self.client.force_login(self.cliente)
        resp = self.client.post(reverse("orders:add_to_cart"), {
            "plan_id": self.plan.pk,
            "quantity": 3,
            "profile_name": "Cli1",
            "pin": "1234",
            "notes": "",
        })
        self.assertEqual(resp.status_code, 302)
        cart = self.client.session.get("cart")
        self.assertEqual(len(cart), 1)
        self.assertEqual(cart[0]["quantity"], 3)

    def test_customer_qty_1_requires_profile(self):
        self.client.force_login(self.cliente)
        resp = self.client.post(reverse("orders:add_to_cart"), {
            "plan_id": self.plan.pk,
            "quantity": 1,
            "profile_name": "",
            "pin": "",
            "notes": "",
        })
        self.assertEqual(resp.status_code, 302)
        # No agrega nada al carrito
        self.assertEqual(self.client.session.get("cart"), None)

    def test_distributor_qty_1_still_requires_profile(self):
        self.client.force_login(self.distri)
        resp = self.client.post(reverse("orders:add_to_cart"), {
            "plan_id": self.plan.pk,
            "quantity": 1,
            "profile_name": "",
            "pin": "",
            "notes": "",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.session.get("cart"), None)

    def test_update_line(self):
        self.client.force_login(self.distri)
        # Agrega una línea
        self.client.post(reverse("orders:add_to_cart"), {
            "plan_id": self.plan.pk, "quantity": 2,
            "profile_name": "", "pin": "", "notes": "",
        })
        # Edita la primera
        resp = self.client.post(reverse("orders:cart_update_line", args=[0]), {
            "profile_name": "Juan",
            "pin": "1111",
            "notes": "VIP",
        })
        self.assertEqual(resp.status_code, 302)
        cart = self.client.session.get("cart")
        self.assertEqual(cart[0]["profile_name"], "Juan")
        self.assertEqual(cart[0]["pin"], "1111")
        self.assertEqual(cart[0]["notes"], "VIP")
        # La segunda línea no debe haber cambiado
        self.assertEqual(cart[1]["profile_name"], "")

    def test_duplicate_line(self):
        self.client.force_login(self.distri)
        self.client.post(reverse("orders:add_to_cart"), {
            "plan_id": self.plan.pk, "quantity": 2,
            "profile_name": "", "pin": "", "notes": "",
        })
        # Llena la primera
        self.client.post(reverse("orders:cart_update_line", args=[0]), {
            "profile_name": "Juan", "pin": "1111", "notes": "",
        })
        # Duplicarla
        resp = self.client.post(reverse("orders:cart_duplicate_line", args=[0]))
        self.assertEqual(resp.status_code, 302)
        cart = self.client.session.get("cart")
        self.assertEqual(len(cart), 3)
        # La copia debe estar inmediatamente después y con perfil/pin vacíos
        self.assertEqual(cart[1]["profile_name"], "")
        self.assertEqual(cart[1]["pin"], "")
        self.assertEqual(cart[1]["plan_id"], self.plan.pk)


class DistributorExpiryReminderTests(TestCase):
    """Cubre el flujo de recordatorios específico para distribuidores."""

    def setUp(self):
        User = get_user_model()
        self.product, self.plan = _make_setup()
        self.distri = User.objects.create_user(
            username="rem_distri", password="x",
            email="rem_distri@example.com",
            role="distribuidor", distributor_approved=True,
        )
        self.cliente = User.objects.create_user(
            username="rem_cli", password="x", email="rem_cli@example.com", role="cliente",
        )

    def _make_item(self, *, owner, days_until_expiry):
        order = Order.objects.create(
            user=owner, email=owner.email, total=Decimal("15.00"),
            status=Order.Status.DELIVERED,
        )
        return OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
            expires_at=timezone.now() + timedelta(days=days_until_expiry),
        )

    def test_distributor_gets_7d_reminder(self):
        item = self._make_item(owner=self.distri, days_until_expiry=7)
        call_command("send_expiry_reminders", stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("7 días", mail.outbox[0].subject)
        self.assertIsNotNone(item.distri_reminder_7d_sent_at)

    def test_distributor_uses_distributor_template(self):
        self._make_item(owner=self.distri, days_until_expiry=7)
        call_command("send_expiry_reminders", stdout=StringIO())
        body = mail.outbox[0].body
        self.assertIn("clientes finales", body)
        self.assertIn("/distribuidor/panel/", body)

    def test_customer_does_not_get_distributor_template(self):
        self._make_item(owner=self.cliente, days_until_expiry=3)
        call_command("send_expiry_reminders", stdout=StringIO())
        body = mail.outbox[0].body
        self.assertNotIn("clientes finales", body)

    def test_customer_does_not_get_7d_window(self):
        # A los clientes finales no les llega la ventana de 7 días, sólo a distri.
        self._make_item(owner=self.cliente, days_until_expiry=7)
        call_command("send_expiry_reminders", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_distributor_independent_idempotency(self):
        # 7d + 3d + 1d marcas son independientes; cada una se manda 1 sola vez.
        item = self._make_item(owner=self.distri, days_until_expiry=3)
        call_command("send_expiry_reminders", stdout=StringIO())
        call_command("send_expiry_reminders", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        item.refresh_from_db()
        self.assertIsNotNone(item.distri_reminder_3d_sent_at)
        self.assertIsNone(item.distri_reminder_1d_sent_at)

    def test_skip_distributors_flag(self):
        self._make_item(owner=self.distri, days_until_expiry=7)
        call_command("send_expiry_reminders", "--skip-distributors", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_skip_customers_flag(self):
        self._make_item(owner=self.cliente, days_until_expiry=3)
        call_command("send_expiry_reminders", "--skip-customers", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)


class ProductWhatsappPitchTests(TestCase):
    def setUp(self):
        cat = Category.objects.create(name="Streaming", slug="streaming-pitch")
        self.product = Product.objects.create(
            category=cat, name="Netflix", slug="netflix-pitch",
            short_description="Plan Premium 4K compartido", icon="🎬",
            is_active=True,
        )
        Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("15.00"), price_distributor=Decimal("10.00"),
            available_for_customer=True, is_active=True, order=1,
        )

    def test_default_pitch_uses_product_data(self):
        pitch = self.product.whatsapp_pitch_for(None)
        self.assertIn("Netflix", pitch)
        self.assertIn("1 mes", pitch)
        self.assertIn("15.00", pitch)
        self.assertIn("Garantía", pitch)
        # Distribuidor NO debería ver su propio precio mayorista en el copy
        # (es lo que ofrece a su cliente final, no lo que él compra).
        self.assertNotIn("10.00", pitch)

    def test_custom_pitch_overrides_default(self):
        self.product.whatsapp_sales_copy = "Mi copy especial 🎉"
        self.product.save()
        self.assertEqual(self.product.whatsapp_pitch_for(None), "Mi copy especial 🎉")


class ReminderRunLogTests(TestCase):
    """Cubre el log de runs del comando send_expiry_reminders."""

    def setUp(self):
        from orders.models import ReminderRunLog
        self.RRL = ReminderRunLog

    def test_run_creates_log_entry(self):
        _make_delivered_item(days_until_expiry=3)
        call_command("send_expiry_reminders", stdout=StringIO())
        log = self.RRL.objects.get()
        self.assertFalse(log.dry_run)
        self.assertEqual(log.customer_count, 1)
        self.assertEqual(log.distri_count, 0)
        self.assertEqual(log.by_window.get("cliente_3d"), 1)
        self.assertIsNotNone(log.finished_at)
        self.assertEqual(log.error, "")

    def test_dry_run_creates_log_entry_with_zero_counts(self):
        _make_delivered_item(days_until_expiry=3)
        call_command("send_expiry_reminders", "--dry-run", stdout=StringIO())
        log = self.RRL.objects.get()
        self.assertTrue(log.dry_run)
        self.assertEqual(log.customer_count, 0)
        self.assertEqual(log.distri_count, 0)
        self.assertEqual(log.by_window.get("cliente_3d"), 0)

    def test_distri_run_logged_in_correct_bucket(self):
        User = get_user_model()
        product, plan = _make_setup()
        distri = User.objects.create_user(
            username="rrl_distri", password="x", email="rrl_distri@example.com",
            role="distribuidor", distributor_approved=True,
        )
        order = Order.objects.create(
            user=distri, email=distri.email,
            total=Decimal("15.00"), status=Order.Status.DELIVERED,
        )
        OrderItem.objects.create(
            order=order, product=product, plan=plan,
            product_name=product.name, plan_name=plan.name,
            unit_price=plan.price_customer, quantity=1,
            expires_at=timezone.now() + timedelta(days=7),
        )
        call_command("send_expiry_reminders", stdout=StringIO())
        log = self.RRL.objects.get()
        self.assertEqual(log.distri_count, 1)
        self.assertEqual(log.customer_count, 0)
        self.assertEqual(log.by_window.get("distri_7d"), 1)

    def test_reminder_status_helper_handles_no_runs(self):
        from config.admin_dashboard import _reminder_status
        rs = _reminder_status(self.RRL, timezone.now())
        self.assertFalse(rs["has_runs"])
        self.assertEqual(rs["tone"], "amber")

    def test_reminder_status_helper_with_recent_run(self):
        from config.admin_dashboard import _reminder_status
        _make_delivered_item(days_until_expiry=3)
        call_command("send_expiry_reminders", stdout=StringIO())
        rs = _reminder_status(self.RRL, timezone.now())
        self.assertTrue(rs["has_runs"])
        self.assertEqual(rs["tone"], "emerald")
        self.assertIn("1 aviso", rs["label"])

    def test_reminder_status_helper_with_stale_run_is_red(self):
        from config.admin_dashboard import _reminder_status
        log = self.RRL.objects.create()
        # Forzamos un started_at de 30 horas atrás (más que el umbral de 25h).
        self.RRL.objects.filter(pk=log.pk).update(
            started_at=timezone.now() - timedelta(hours=30),
            finished_at=timezone.now() - timedelta(hours=30),
        )
        rs = _reminder_status(self.RRL, timezone.now())
        self.assertEqual(rs["tone"], "red")
        self.assertIn("podría estar caído", rs["label"])

    def test_reminder_status_helper_skips_dry_runs(self):
        from config.admin_dashboard import _reminder_status
        _make_delivered_item(days_until_expiry=3)
        call_command("send_expiry_reminders", "--dry-run", stdout=StringIO())
        # Sólo hay un run dry-run → tratamos el panel como "sin runs reales".
        rs = _reminder_status(self.RRL, timezone.now())
        self.assertFalse(rs["has_runs"])


# --- Auto-entrega para distribuidores ----------------------------------------


class AutoDeliverDistributorTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.distri = User.objects.create_user(
            username="auto-distri",
            password="x",
            email="auto-distri@example.com",
            role="distribuidor",
            distributor_approved=True,
        )
        self.cliente = User.objects.create_user(
            username="auto-cli",
            password="x",
            email="auto-cli@example.com",
            role="cliente",
        )
        self.cat = Category.objects.create(name="Streaming-Auto", slug="streaming-auto")
        self.product_max = Product.objects.create(
            name="Max", slug="max-auto", category=self.cat,
        )
        self.plan_max = Plan.objects.create(
            product=self.product_max, name="1 mes (mayorista)",
            duration_days=30,
            price_customer=Decimal("15.00"),
            price_distributor=Decimal("10.00"),
        )
        self.product_prime = Product.objects.create(
            name="Prime", slug="prime-auto", category=self.cat,
        )
        self.plan_prime = Plan.objects.create(
            product=self.product_prime, name="1 mes (mayorista)",
            duration_days=30,
            price_customer=Decimal("12.00"),
            price_distributor=Decimal("8.00"),
        )

    def _make_distributor_order(self):
        order = Order.objects.create(
            user=self.distri, email=self.distri.email,
            total=Decimal("18.00"), status=Order.Status.VERIFYING,
        )
        OrderItem.objects.create(
            order=order, product=self.product_max, plan=self.plan_max,
            product_name=self.product_max.name, plan_name=self.plan_max.name,
            unit_price=self.plan_max.price_distributor, quantity=1,
        )
        OrderItem.objects.create(
            order=order, product=self.product_prime, plan=self.plan_prime,
            product_name=self.product_prime.name, plan_name=self.plan_prime.name,
            unit_price=self.plan_prime.price_distributor, quantity=1,
        )
        return order

    def test_auto_delivers_when_stock_available(self):
        from orders.auto_delivery import auto_deliver_distributor_order

        StockItem.objects.create(
            product=self.product_max, plan=self.plan_max,
            credentials="Correo: max@x.com\nContraseña: maxpass",
        )
        StockItem.objects.create(
            product=self.product_prime, plan=self.plan_prime,
            credentials="Correo: prime@x.com\nContraseña: primepass",
        )
        order = self._make_distributor_order()

        delivered, missing = auto_deliver_distributor_order(order)

        self.assertTrue(delivered)
        self.assertEqual(missing, [])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertIsNotNone(order.delivered_at)
        for item in order.items.all():
            self.assertIsNotNone(item.stock_item_id)
            item.stock_item.refresh_from_db()
            self.assertEqual(item.stock_item.status, StockItem.Status.SOLD)
            self.assertIsNotNone(item.stock_item.sold_at)
            self.assertIn("Correo:", item.delivered_credentials)

    def test_no_op_when_user_is_customer(self):
        from orders.auto_delivery import auto_deliver_distributor_order

        StockItem.objects.create(
            product=self.product_max, plan=self.plan_max,
            credentials="Correo: max@x.com\nContraseña: maxpass",
        )
        order = Order.objects.create(
            user=self.cliente, email=self.cliente.email,
            total=Decimal("15.00"), status=Order.Status.PREPARING,
        )
        OrderItem.objects.create(
            order=order, product=self.product_max, plan=self.plan_max,
            product_name=self.product_max.name, plan_name=self.plan_max.name,
            unit_price=self.plan_max.price_customer, quantity=1,
        )

        delivered, missing = auto_deliver_distributor_order(order)

        self.assertFalse(delivered)
        self.assertEqual(missing, [])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PREPARING)
        # El stock fue reservado al crear el OrderItem (por el signal
        # post_save) — auto_deliver no toca nada porque no es distri.
        # El stock queda RESERVED hasta que se entregue manual o se
        # cancele el pedido.
        stock = StockItem.objects.filter(product=self.product_max).get()
        self.assertEqual(stock.status, StockItem.Status.RESERVED)

    def test_leaves_order_pending_when_one_item_lacks_stock(self):
        from orders.auto_delivery import auto_deliver_distributor_order

        # Solo carga stock para Max — Prime queda sin stock.
        StockItem.objects.create(
            product=self.product_max, plan=self.plan_max,
            credentials="Correo: max@x.com\nContraseña: maxpass",
        )
        order = self._make_distributor_order()
        order.status = Order.Status.PREPARING
        order.save(update_fields=["status"])

        with patch("orders.auto_delivery.telegram.notify_admin") as notify:
            delivered, missing = auto_deliver_distributor_order(order)

        self.assertFalse(delivered)
        self.assertEqual(len(missing), 1)
        self.assertIn("Prime", missing[0])
        order.refresh_from_db()
        # No se entregó: el pedido sigue en PREPARING y el stock de Max
        # NO debe haberse marcado como SOLD (atomicidad). Queda RESERVED
        # porque el signal post_save lo reservó al crear el OrderItem;
        # eso es consistente con el invariante "cada pedido reserva su
        # stock hasta entregar o cancelar".
        self.assertEqual(order.status, Order.Status.PREPARING)
        max_stock = StockItem.objects.get(product=self.product_max)
        self.assertIn(
            max_stock.status,
            {StockItem.Status.AVAILABLE, StockItem.Status.RESERVED},
        )
        self.assertNotEqual(max_stock.status, StockItem.Status.SOLD)
        notify.assert_called_once()

    def test_picks_distinct_stock_for_two_items_of_same_product(self):
        from orders.auto_delivery import auto_deliver_distributor_order

        StockItem.objects.create(
            product=self.product_max, plan=self.plan_max,
            credentials="Correo: a@x.com\nContraseña: a",
        )
        StockItem.objects.create(
            product=self.product_max, plan=self.plan_max,
            credentials="Correo: b@x.com\nContraseña: b",
        )
        order = Order.objects.create(
            user=self.distri, email=self.distri.email,
            total=Decimal("20.00"), status=Order.Status.PREPARING,
        )
        OrderItem.objects.create(
            order=order, product=self.product_max, plan=self.plan_max,
            product_name=self.product_max.name, plan_name=self.plan_max.name,
            unit_price=self.plan_max.price_distributor, quantity=1,
        )
        OrderItem.objects.create(
            order=order, product=self.product_max, plan=self.plan_max,
            product_name=self.product_max.name, plan_name=self.plan_max.name,
            unit_price=self.plan_max.price_distributor, quantity=1,
        )

        delivered, missing = auto_deliver_distributor_order(order)

        self.assertTrue(delivered)
        ids = list(order.items.values_list("stock_item_id", flat=True))
        self.assertEqual(len(set(ids)), 2, "Cada item debe tener un stock distinto")


class ReconcileSoldStockTests(TestCase):
    def setUp(self):
        cat = Category.objects.create(name="Streaming-R", slug="streaming-r")
        self.product = Product.objects.create(
            name="Disney", slug="disney-r", category=cat,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("10.00"), price_distributor=Decimal("8.00"),
        )

    def _delivered_order_with_stock(self, stock_status, link=True, creds="X: 1"):
        stock = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials=creds, status=stock_status,
        )
        order = Order.objects.create(
            email="x@y.com", total=Decimal("10.00"),
            status=Order.Status.DELIVERED,
            delivered_at=timezone.now(),
        )
        item = OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
            delivered_credentials=creds,
            stock_item=stock if link else None,
        )
        return order, item, stock

    def test_marks_linked_stock_as_sold(self):
        _, _, stock = self._delivered_order_with_stock(
            StockItem.Status.AVAILABLE, link=True,
        )
        out = StringIO()
        call_command("reconcile_sold_stock", stdout=out)
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.SOLD)
        self.assertIsNotNone(stock.sold_at)

    def test_dry_run_does_not_write(self):
        _, _, stock = self._delivered_order_with_stock(
            StockItem.Status.AVAILABLE, link=True,
        )
        call_command("reconcile_sold_stock", "--dry-run", stdout=StringIO())
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.AVAILABLE)

    def test_match_by_credentials_links_orphan_item(self):
        # OrderItem sin stock_item, pero las credenciales coinciden con
        # un StockItem AVAILABLE del mismo producto.
        order = Order.objects.create(
            email="x@y.com", total=Decimal("10.00"),
            status=Order.Status.DELIVERED,
            delivered_at=timezone.now(),
        )
        creds = "Correo: foo@bar.com\nContraseña: bar"
        OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
            delivered_credentials=creds,
        )
        stock = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials=creds, status=StockItem.Status.AVAILABLE,
        )

        call_command("reconcile_sold_stock", "--match-by-credentials", stdout=StringIO())

        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.SOLD)
        item = order.items.get()
        self.assertEqual(item.stock_item_id, stock.pk)


class AutoDeliverNoDoubleEmailTests(TestCase):
    """Verifies the doble-email fix: when a distributor's order is
    auto-delivered, only the 'order_delivered' email is sent — no
    'order_preparing' email leaks through the PREPARING transition.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.distri = User.objects.create_user(
            username="d2",
            password="x",
            email="d2@example.com",
            role="distribuidor",
            distributor_approved=True,
        )
        self.cliente = User.objects.create_user(
            username="c2",
            password="x",
            email="c2@example.com",
            role="cliente",
        )
        self.cat = Category.objects.create(name="Streaming-D2", slug="streaming-d2")
        self.product = Product.objects.create(
            name="HBO Max-D2", slug="max-d2", category=self.cat,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes (mayorista)",
            duration_days=30,
            price_customer=Decimal("15.00"),
            price_distributor=Decimal("10.00"),
        )

    def _make_order(self, *, user, status, with_proof=False):
        order = Order.objects.create(
            user=user, email=user.email,
            total=Decimal("10.00"), status=status,
            payment_provider="yape" if with_proof else "",
            payment_proof="proofs/x.jpg" if with_proof else "",
        )
        OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_distributor, quantity=1,
        )
        return order

    def test_distributor_with_stock_only_gets_delivered_email(self):
        from orders.auto_delivery import auto_deliver_distributor_order

        StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: a@x.com\nContraseña: a",
        )
        order = self._make_order(user=self.distri, status=Order.Status.VERIFYING)
        mail.outbox = []
        delivered, missing = auto_deliver_distributor_order(order)
        self.assertTrue(delivered)
        self.assertEqual(missing, [])
        # Ningún correo "Estamos preparando" debe haberse enviado.
        subjects = [m.subject for m in mail.outbox]
        self.assertFalse(
            any("preparando" in s.lower() for s in subjects),
            f"Se filtró un email de PREPARING: {subjects}",
        )
        # Pero sí debe haber un correo de entrega.
        self.assertTrue(
            any("listo" in s.lower() or "entregado" in s.lower() for s in subjects),
            f"No se envió email de entrega: {subjects}",
        )

    def test_paid_at_argument_is_set_when_provided(self):
        from orders.auto_delivery import auto_deliver_distributor_order
        from django.utils import timezone as tz
        from datetime import timedelta

        StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: a@x.com\nContraseña: a",
        )
        order = self._make_order(user=self.distri, status=Order.Status.VERIFYING)
        before = tz.now() - timedelta(hours=1)
        delivered, _ = auto_deliver_distributor_order(order, paid_at=before)
        self.assertTrue(delivered)
        order.refresh_from_db()
        self.assertEqual(order.paid_at, before)

    def test_confirm_yape_view_distributor_only_one_email(self):
        StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: a@x.com\nContraseña: a",
        )
        order = self._make_order(
            user=self.distri, status=Order.Status.VERIFYING, with_proof=True,
        )
        # Login as superuser to access the admin view.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            username="admin-test", password="x", email="admin@x.com",
        )
        self.client.force_login(admin_user)
        mail.outbox = []
        url = reverse("admin:orders_order_confirm_yape", args=[order.pk])
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (302, 303))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        # Verifica: 1 email (entrega), 0 emails de "preparando".
        preparing_count = sum(
            1 for m in mail.outbox if "preparando" in m.subject.lower()
        )
        self.assertEqual(
            preparing_count, 0,
            f"No debe enviarse email de PREPARING. Subjects: {[m.subject for m in mail.outbox]}",
        )

    def test_confirm_yape_view_customer_one_email_only(self):
        # Cliente final: NO se descuenta stock automático, va a PREPARING,
        # signal manda 1 solo email de "preparando" (no se duplicó).
        order = self._make_order(
            user=self.cliente, status=Order.Status.VERIFYING, with_proof=True,
        )
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            username="admin-test2", password="x", email="admin2@x.com",
        )
        self.client.force_login(admin_user)
        mail.outbox = []
        url = reverse("admin:orders_order_confirm_yape", args=[order.pk])
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (302, 303))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PREPARING)
        preparing_count = sum(
            1 for m in mail.outbox if "preparando" in m.subject.lower()
        )
        self.assertEqual(
            preparing_count, 1,
            f"Cliente final debe recibir exactamente 1 email PREPARING. "
            f"Subjects: {[m.subject for m in mail.outbox]}",
        )


class CredentialsParseProfilePinTests(TestCase):
    def test_parses_perfil_and_pin_lines(self):
        from orders.credentials import parse_profile_pin, split_account_extras

        text = (
            "Correo: foo@bar.com\n"
            "Contraseña: secret\n"
            "Perfil: Saldoya\n"
            "PIN: 1234\n"
        )
        profile, pin = parse_profile_pin(text)
        self.assertEqual(profile, "Saldoya")
        self.assertEqual(pin, "1234")

        account, profile, pin = split_account_extras(text)
        self.assertIn("Correo:", account)
        self.assertIn("Contraseña:", account)
        self.assertNotIn("Perfil:", account)
        self.assertNotIn("PIN:", account)
        self.assertEqual(profile, "Saldoya")
        self.assertEqual(pin, "1234")

    def test_missing_perfil_pin_returns_empty(self):
        from orders.credentials import parse_profile_pin

        profile, pin = parse_profile_pin("Correo: x@y.com\nContraseña: pass")
        self.assertEqual(profile, "")
        self.assertEqual(pin, "")


class StockItemAdminSoldAtTests(TestCase):
    """Cuando el admin marca un stock como Vendida desde el form, si
    `sold_at` estaba vacío, debe setearse automáticamente al timestamp
    actual. Esto cubre el caso de reconciliación manual de ventas
    históricas."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.admin_user = User.objects.create_superuser(
            username="admin-stock", password="x", email="adm@x.com",
        )
        self.cat = Category.objects.create(name="C-S", slug="c-s")
        self.product = Product.objects.create(
            name="P", slug="p", category=self.cat,
        )

    def test_sold_at_auto_set_when_marking_sold(self):
        stock = StockItem.objects.create(
            product=self.product, status=StockItem.Status.AVAILABLE,
            credentials="x",
        )
        self.assertIsNone(stock.sold_at)
        self.client.force_login(self.admin_user)
        url = reverse("admin:catalog_stockitem_change", args=[stock.pk])
        resp = self.client.post(url, {
            "product": str(self.product.pk),
            "status": StockItem.Status.SOLD,
            "credentials": "x",
            "label": "",
            "_save": "Save",
        })
        self.assertIn(resp.status_code, (200, 302, 303))
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.SOLD)
        self.assertIsNotNone(stock.sold_at)



class StockReservationOnOrderItemCreateTests(TestCase):
    """Reserva automática de stock al crear un OrderItem."""

    def setUp(self):
        self.cat = Category.objects.create(name="C-R", slug="c-r")
        self.product = Product.objects.create(
            name="Disney-R", slug="disney-r", category=self.cat,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("10.00"), price_distributor=Decimal("8.00"),
        )

    def _make_order(self):
        return Order.objects.create(
            email="x@y.com", total=Decimal("10.00"),
            status=Order.Status.PENDING,
        )

    def test_reserves_first_available_stock_on_create(self):
        stock = StockItem.objects.create(
            product=self.product, plan=self.plan,
            credentials="Correo: a@x.com\nContraseña: a",
        )
        order = self._make_order()
        item = OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
        )
        item.refresh_from_db()
        stock.refresh_from_db()
        self.assertEqual(item.stock_item_id, stock.pk)
        self.assertEqual(stock.status, StockItem.Status.RESERVED)

    def test_two_items_pick_distinct_stocks(self):
        s1 = StockItem.objects.create(
            product=self.product, plan=self.plan, credentials="x1",
        )
        s2 = StockItem.objects.create(
            product=self.product, plan=self.plan, credentials="x2",
        )
        order = self._make_order()
        i1 = OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
        )
        i2 = OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
        )
        i1.refresh_from_db()
        i2.refresh_from_db()
        self.assertNotEqual(i1.stock_item_id, i2.stock_item_id)
        self.assertEqual({i1.stock_item_id, i2.stock_item_id}, {s1.pk, s2.pk})

    def test_no_stock_means_item_left_unreserved(self):
        order = self._make_order()
        item = OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
        )
        item.refresh_from_db()
        self.assertIsNone(item.stock_item_id)

    def test_canceling_order_releases_reservation(self):
        stock = StockItem.objects.create(
            product=self.product, plan=self.plan, credentials="x",
        )
        order = self._make_order()
        OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
        )
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.RESERVED)
        # Cancelar el pedido debe liberar la reserva.
        order.status = Order.Status.CANCELED
        order.save(update_fields=["status"])
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.AVAILABLE)
        item = order.items.get()
        self.assertIsNone(item.stock_item_id)

    def test_does_not_release_sold_stock_on_refund(self):
        # Si el pedido pasó por DELIVERED (stock SOLD) y luego se
        # refunda, el stock NO se restaura — la cuenta ya se entregó.
        stock = StockItem.objects.create(
            product=self.product, plan=self.plan, credentials="x",
        )
        order = self._make_order()
        item = OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
        )
        # Simular entrega: stock SOLD vinculado al item.
        item.refresh_from_db()
        stock.refresh_from_db()
        stock.status = StockItem.Status.SOLD
        stock.save(update_fields=["status"])
        # Refundar.
        order.status = Order.Status.REFUNDED
        order.save(update_fields=["status"])
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.SOLD)


class ReleaseStaleReservationsCommandTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="C-S", slug="c-stale")
        self.product = Product.objects.create(
            name="Stale", slug="stale", category=self.cat,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("10.00"), price_distributor=Decimal("8.00"),
        )

    def _stale_pending_order(self, hours=48):
        from datetime import timedelta

        stock = StockItem.objects.create(
            product=self.product, plan=self.plan, credentials="x",
        )
        order = Order.objects.create(
            email="z@y.com", total=Decimal("10.00"),
            status=Order.Status.PENDING,
        )
        OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
        )
        # Backdate por SQL para simular pedido viejo (auto_now_add).
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(hours=hours),
        )
        return order, stock

    def test_releases_reservations_of_stale_pending_order(self):
        _, stock = self._stale_pending_order(hours=48)
        out = StringIO()
        call_command("release_stale_reservations", "--hours", "24", stdout=out)
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.AVAILABLE)

    def test_does_not_release_recent_pending_order(self):
        _, stock = self._stale_pending_order(hours=2)
        call_command(
            "release_stale_reservations", "--hours", "24",
            stdout=StringIO(),
        )
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.RESERVED)

    def test_dry_run_does_not_write(self):
        _, stock = self._stale_pending_order(hours=48)
        call_command(
            "release_stale_reservations", "--hours", "24", "--dry-run",
            stdout=StringIO(),
        )
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.RESERVED)


class StockBulkActionsTests(TestCase):
    """Las acciones masivas Marcar Caída / Reactivar del admin de
    StockItem deben preservar invariantes (limpiar sold_at al
    reactivar, desvincular OrderItems al caer)."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.admin_user = User.objects.create_superuser(
            username="admin-bulk", password="x", email="bulk@x.com",
        )
        self.cat = Category.objects.create(name="C-B", slug="c-b")
        self.product = Product.objects.create(
            name="Bulk", slug="bulk", category=self.cat,
        )
        self.plan = Plan.objects.create(
            product=self.product, name="1 mes", duration_days=30,
            price_customer=Decimal("10.00"), price_distributor=Decimal("8.00"),
        )

    def _post_action(self, action: str, ids: list[int]):
        self.client.force_login(self.admin_user)
        return self.client.post(
            reverse("admin:catalog_stockitem_changelist"),
            data={
                "action": action,
                "_selected_action": [str(pk) for pk in ids],
            },
        )

    def test_mark_available_clears_sold_at(self):
        stock = StockItem.objects.create(
            product=self.product, plan=self.plan, credentials="x",
            status=StockItem.Status.SOLD, sold_at=timezone.now(),
        )
        resp = self._post_action("action_mark_available", [stock.pk])
        self.assertEqual(resp.status_code, 302)
        stock.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.AVAILABLE)
        self.assertIsNone(stock.sold_at)

    def test_mark_defective_unlinks_orderitems(self):
        # OrderItem con stock vinculado → al marcar el stock como
        # caído, el OrderItem queda con stock_item=None para que
        # pueda recibir un reemplazo.
        stock = StockItem.objects.create(
            product=self.product, plan=self.plan, credentials="x",
        )
        order = Order.objects.create(
            email="z@y.com", total=Decimal("10.00"),
            status=Order.Status.PENDING,
        )
        item = OrderItem.objects.create(
            order=order, product=self.product, plan=self.plan,
            product_name=self.product.name, plan_name=self.plan.name,
            unit_price=self.plan.price_customer, quantity=1,
            stock_item=stock,
        )
        # Marcar como caída.
        resp = self._post_action("action_mark_defective", [stock.pk])
        self.assertEqual(resp.status_code, 302)
        stock.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(stock.status, StockItem.Status.DEFECTIVE)
        self.assertIsNone(item.stock_item_id)


class NotifyProviderExpiryCommandTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="C-NP", slug="c-np")
        self.product = Product.objects.create(
            name="Provider-Exp", slug="provider-exp", category=self.cat,
        )

    def test_notifies_3d_window_once(self):
        from datetime import timedelta

        stock = StockItem.objects.create(
            product=self.product, credentials="x",
            provider_expires_at=timezone.now() + timedelta(days=2),
        )
        with patch(
            "catalog.management.commands.notify_provider_expiry.telegram.notify_admin"
        ) as notify:
            call_command("notify_provider_expiry", stdout=StringIO())
            self.assertEqual(notify.call_count, 1)
            stock.refresh_from_db()
            self.assertIsNotNone(stock.provider_expiry_3d_notified_at)
            # Segunda corrida: NO vuelve a alertar (idempotente).
            call_command("notify_provider_expiry", stdout=StringIO())
            self.assertEqual(notify.call_count, 1)

    def test_notifies_1d_window_after_3d(self):
        from datetime import timedelta

        stock = StockItem.objects.create(
            product=self.product, credentials="x",
            provider_expires_at=timezone.now() + timedelta(hours=12),
            provider_expiry_3d_notified_at=timezone.now() - timedelta(days=2),
        )
        with patch(
            "catalog.management.commands.notify_provider_expiry.telegram.notify_admin"
        ) as notify:
            call_command("notify_provider_expiry", stdout=StringIO())
            self.assertEqual(notify.call_count, 1)
            stock.refresh_from_db()
            self.assertIsNotNone(stock.provider_expiry_1d_notified_at)

    def test_dry_run_does_not_send(self):
        from datetime import timedelta

        StockItem.objects.create(
            product=self.product, credentials="x",
            provider_expires_at=timezone.now() + timedelta(days=2),
        )
        with patch(
            "catalog.management.commands.notify_provider_expiry.telegram.notify_admin"
        ) as notify:
            call_command(
                "notify_provider_expiry", "--dry-run",
                stdout=StringIO(),
            )
            notify.assert_not_called()

    def test_skips_sold_and_defective(self):
        from datetime import timedelta

        StockItem.objects.create(
            product=self.product, credentials="x", status=StockItem.Status.SOLD,
            provider_expires_at=timezone.now() + timedelta(days=2),
        )
        StockItem.objects.create(
            product=self.product, credentials="y", status=StockItem.Status.DEFECTIVE,
            provider_expires_at=timezone.now() + timedelta(days=2),
        )
        with patch(
            "catalog.management.commands.notify_provider_expiry.telegram.notify_admin"
        ) as notify:
            call_command("notify_provider_expiry", stdout=StringIO())
            notify.assert_not_called()


# --------------------------------------------------------------
# Telegram webhook + comandos admin (PR #77)
# --------------------------------------------------------------

from django.test import override_settings as _override_settings  # noqa: E402

from orders import telegram as _telegram  # noqa: E402


@_override_settings(
    TELEGRAM_BOT_TOKEN="dummy-token",
    TELEGRAM_ADMIN_CHAT_ID="999",
    TELEGRAM_WEBHOOK_SECRET="abc-secret",
)
class TelegramWebhookTests(TestCase):
    def setUp(self):
        self.url = reverse("orders:telegram_webhook", args=["abc-secret"])
        self.client = Client()

    def test_rejects_without_header(self):
        resp = self.client.post(self.url, data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_rejects_with_wrong_secret_in_path(self):
        url = reverse("orders:telegram_webhook", args=["wrong"])
        resp = self.client.post(
            url, data="{}", content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="abc-secret",
        )
        self.assertEqual(resp.status_code, 403)

    def test_accepts_valid_secret(self):
        with patch("orders.telegram.process_update") as proc:
            resp = self.client.post(
                self.url,
                data='{"update_id":1,"message":{"chat":{"id":999},"text":"/start"}}',
                content_type="application/json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="abc-secret",
            )
        self.assertEqual(resp.status_code, 200)
        proc.assert_called_once()


@_override_settings(
    TELEGRAM_BOT_TOKEN="dummy-token",
    TELEGRAM_ADMIN_CHAT_ID="999",
)
class TelegramAdminCommandsTests(TestCase):
    def test_admin_command_only_runs_for_admin_chat(self):
        with patch("orders.telegram.send_message") as send:
            _telegram.process_update({
                "update_id": 1,
                "message": {"chat": {"id": 999}, "text": "/yape"},
            })
        send.assert_called()  # corre /yape

    def test_admin_command_falls_back_to_help_for_others(self):
        with patch("orders.telegram.send_message") as send:
            _telegram.process_update({
                "update_id": 2,
                "message": {"chat": {"id": 12345}, "text": "/yape"},
            })
        # Para chat no-admin, devuelve PUBLIC_HELP
        args, kwargs = send.call_args
        self.assertIn("Comandos", args[1])

    def test_daily_summary_text_runs(self):
        text = _telegram.daily_summary_text()
        self.assertIn("Resumen diario", text)


@_override_settings(
    TELEGRAM_BOT_TOKEN="dummy-token",
    TELEGRAM_ADMIN_CHAT_ID="999",
)
class TelegramYapeCallbackTests(TestCase):
    def test_callback_rejects_non_admin(self):
        with patch("orders.telegram.answer_callback_query") as ack:
            _telegram._handle_callback_query({
                "callback_query": {
                    "id": "cb1",
                    "data": "yape:confirm:1",
                    "message": {"chat": {"id": 12345}, "message_id": 1, "text": ""},
                },
            })
        ack.assert_called_once()
        args, kwargs = ack.call_args
        self.assertEqual(args[0], "cb1")
