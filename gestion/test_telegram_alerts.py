import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from gestion.control_operations import (
    create_client,
    create_subscription,
    delete_client,
    renew_subscription,
    search_clients,
    update_client,
)
from gestion.models import Client, Service, Subscription, TelegramConnection, Tenant
from gestion.telegram_alerts import (
    CONTROL_PREMIUM_EMOJI_IDS,
    _button,
    _parse_duration_or_date,
    _premium_text,
    _without_button_styling,
    link_chat,
    process_update,
    send_expiry_digests,
)


class TelegramAlertTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("revendedor", password="x")
        self.other = User.objects.create_user("otro", password="x")
        self.tenant = Tenant.objects.create(user=self.owner, business_name="Revendedor")
        self.tenant.start_trial()
        self.other_tenant = Tenant.objects.create(user=self.other, business_name="Otro")
        self.other_tenant.start_trial()

    def test_subscription_duration_accepts_days_with_label(self):
        parsed, error = _parse_duration_or_date("30 días")
        self.assertIsNone(error)
        self.assertEqual(parsed, {"duration_days": 30})

    def test_subscription_duration_accepts_short_exact_date(self):
        parsed, error = _parse_duration_or_date("12/08/27")
        self.assertIsNone(error)
        self.assertEqual(parsed["expires_on"], "2027-08-12")
        self.assertTrue(parsed["expires_at"].startswith("2027-08-12T23:59:59"))

    def test_one_time_token_links_only_its_owner(self):
        raw = "token-seguro"
        connection = TelegramConnection.objects.create(
            owner=self.owner,
            link_token_digest=hashlib.sha256(raw.encode()).hexdigest(),
            link_expires_at=timezone.now() + timedelta(minutes=10),
        )
        self.assertTrue(link_chat(raw, {"id": 123, "username": "revendedor"}))
        connection.refresh_from_db()
        self.assertEqual(connection.chat_id, "123")
        self.assertEqual(connection.link_token_digest, "")
        self.assertFalse(link_chat(raw, {"id": 999}))

    def test_control_buttons_use_premium_icons_and_semantic_colors(self):
        add = _button("➕ Nuevo cliente", "new")
        remove = _button("🗑 Eliminar", "delete_confirm:abc")
        menu = _button("👥 Mis clientes", "clients:0:all")

        self.assertEqual(add["style"], "success")
        self.assertEqual(remove["style"], "danger")
        self.assertEqual(menu["style"], "primary")
        self.assertTrue(add["icon_custom_emoji_id"])
        self.assertTrue(remove["icon_custom_emoji_id"])
        self.assertTrue(menu["icon_custom_emoji_id"])

    def test_control_button_fallback_preserves_callback(self):
        clean = _without_button_styling(
            {
                "inline_keyboard": [
                    [_button("➕ Nuevo cliente", "new")]
                ]
            }
        )
        button = clean["inline_keyboard"][0][0]
        self.assertEqual(button["callback_data"], "new")
        self.assertNotIn("style", button)
        self.assertNotIn("icon_custom_emoji_id", button)

    def test_summary_message_uses_configured_premium_emojis(self):
        rendered = _premium_text(
            "🤖 JHELIZ CONTROL\n📊 RESUMEN\n👥 Clientes\n🟢 Activas\n⏰ Por vencer\n🔴 Vencidas"
        )

        self.assertGreaterEqual(rendered.count("<tg-emoji"), 6)
        self.assertIn("JHELIZ CONTROL", rendered)
        self.assertIn("Clientes", rendered)

    def test_control_summary_uses_its_own_exact_premium_set(self):
        rendered = _premium_text(
            "🤖 JHELIZ CONTROL\n📊 RESUMEN\n👥 Clientes\n"
            "🟢 Activas\n⏰ Por vencer\n🔴 Vencidas"
        )

        for name in ("control", "summary", "clients", "active", "due", "expired"):
            self.assertIn(
                f'emoji-id="{CONTROL_PREMIUM_EMOJI_IDS[name]}"',
                rendered,
            )

    def test_control_buttons_use_exact_semantic_premium_ids(self):
        cases = {
            "➕ Nuevo cliente": "new_client",
            "⏰ Próximos vencimientos": "next_due",
            "📊 Estadísticas": "stats",
            "💰 Mi saldo": "balance",
            "🔔 Alertas": "alerts",
            "⚙️ Mi cuenta": "account",
            "🌐 Abrir Jheliz Control": "open_control",
            "Siguiente ➡️": "next",
            "🔎 Buscar": "search",
            "⬅️ Volver": "back",
        }
        for label, name in cases.items():
            with self.subTest(label=label):
                self.assertEqual(
                    _button(label, "test")["icon_custom_emoji_id"],
                    CONTROL_PREMIUM_EMOJI_IDS[name],
                )

    def test_account_and_finance_messages_use_exact_premium_ids(self):
        rendered = _premium_text(
            "⚙️ <b>MI CUENTA</b>\n"
            "👤 Revendedor\n🆔 ID interno\n🔗 Telegram\n📅 Vinculado desde\n"
            "💰 <b>MI SALDO</b>\n💳 Créditos disponibles\n"
            "📈 Ingresos registrados\n📉 Egresos registrados\n⚖️ Balance\n"
            "🆕 Clientes nuevos este mes"
        )

        expected = (
            "account",
            "reseller",
            "tenant_id",
            "telegram",
            "linked_since",
            "balance",
            "credits",
            "new_clients_month",
        )
        for name in expected:
            self.assertIn(
                f'emoji-id="{CONTROL_PREMIUM_EMOJI_IDS[name]}"',
                rendered,
            )

    def test_tomorrow_button_uses_its_specific_premium_id(self):
        self.assertEqual(
            _button("✅ Mañana", "alert_toggle:1")["icon_custom_emoji_id"],
            CONTROL_PREMIUM_EMOJI_IDS["tomorrow"],
        )

    def test_one_telegram_chat_cannot_stay_linked_to_two_resellers(self):
        first = TelegramConnection.objects.create(owner=self.owner, chat_id="123")
        raw = "token-otro"
        second = TelegramConnection.objects.create(
            owner=self.other,
            link_token_digest=hashlib.sha256(raw.encode()).hexdigest(),
            link_expires_at=timezone.now() + timedelta(minutes=10),
        )

        self.assertTrue(link_chat(raw, {"id": 123, "username": "mismo_chat"}))

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.chat_id)
        self.assertFalse(first.is_enabled)
        self.assertEqual(second.chat_id, "123")

    @patch("gestion.telegram_alerts.send_message")
    def test_unlinked_telegram_receives_no_private_data(self, send):
        Client.objects.create(owner=self.owner, name="Cliente privado")

        process_update({"message": {"text": "/menu", "chat": {"id": 999}}})

        message = send.call_args.args[1]
        self.assertIn("no vinculado", message)
        self.assertNotIn("Cliente privado", message)

    @patch("gestion.telegram_alerts.send_message")
    def test_status_identifies_connection_through_internal_owner(self, send):
        TelegramConnection.objects.create(
            owner=self.owner,
            chat_id="123",
            telegram_username="revendedor",
            notify_windows=[1, 0],
        )

        process_update({"message": {"text": "/estado", "chat": {"id": 123}}})

        message = send.call_args.args[1]
        self.assertIn(self.owner.username, message)
        self.assertIn("solo recibirás datos de tus propios clientes", message)

    def _subscription(self, owner, client_name):
        service = Service.objects.create(owner=owner, name=f"Netflix {owner.pk}")
        client = Client.objects.create(owner=owner, name=client_name)
        sub = Subscription.objects.create(
            owner=owner,
            client=client,
            service=service,
            account_email=f"{owner.pk}@example.com",
            starts_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=5),
        )
        return client, sub

    def test_other_owner_cannot_edit_delete_or_renew(self):
        foreign_client, foreign_sub = self._subscription(self.other, "Cliente ajeno")
        original_expiry = foreign_sub.expires_at

        updated, edit_error = update_client(
            self.owner,
            foreign_client.pk,
            {"name": "Hackeado"},
        )
        renewed, renew_error = renew_subscription(self.owner, foreign_sub.pk, 30)
        deleted, delete_error = delete_client(self.owner, foreign_client.pk)

        self.assertIsNone(updated)
        self.assertEqual(edit_error, "not_found")
        self.assertIsNone(renewed)
        self.assertEqual(renew_error, "not_found")
        self.assertFalse(deleted)
        self.assertEqual(delete_error, "not_found")
        foreign_client.refresh_from_db()
        foreign_sub.refresh_from_db()
        self.assertEqual(foreign_client.name, "Cliente ajeno")
        self.assertEqual(foreign_sub.expires_at, original_expiry)

    def test_renewal_idempotency_prevents_double_click(self):
        _, sub = self._subscription(self.owner, "Cliente propio")
        first, first_error = renew_subscription(self.owner, sub.pk, 30, "renew-once")
        first_expiry = first.expires_at
        second, second_error = renew_subscription(self.owner, sub.pk, 30, "renew-once")

        self.assertIsNone(first_error)
        self.assertIsNone(second)
        self.assertEqual(second_error, "duplicate")
        sub.refresh_from_db()
        self.assertEqual(sub.expires_at, first_expiry)

    def test_telegram_and_web_services_share_the_same_client_rows(self):
        created, error = create_client(
            self.owner,
            {
                "name": "Creado desde Telegram",
                "whatsapp": "+51999999999",
                "email": "cliente@example.com",
                "telegram": "@cliente",
                "notes": "",
            },
            "create-shared",
        )
        self.assertIsNone(error)
        self.assertTrue(
            Client.objects.filter(owner=self.owner, pk=created.pk).exists()
        )
        self.assertEqual(
            search_clients(self.owner.pk, "cliente@example.com").get().pk,
            created.pk,
        )

    def test_subscription_creation_uses_central_tables_and_is_idempotent(self):
        service = Service.objects.create(owner=self.owner, name="Netflix")
        client = Client.objects.create(owner=self.owner, name="Cliente")
        payload = {
            "client_id": client.pk,
            "service_id": service.pk,
            "account_email": "cuenta@example.com",
            "plan": "perfil",
            "profiles": 1,
            "duration_days": 30,
            "cost": "10.00",
            "investment": "5.00",
        }

        first, first_error = create_subscription(
            self.owner, payload, "subscription-once"
        )
        second, second_error = create_subscription(
            self.owner, payload, "subscription-once"
        )

        self.assertIsNone(first_error)
        self.assertEqual(first.owner_id, self.owner.pk)
        self.assertEqual(first.client_id, client.pk)
        self.assertIsNone(second)
        self.assertEqual(second_error, "duplicate")
        self.assertEqual(
            Subscription.objects.filter(owner=self.owner, client=client).count(),
            1,
        )

    def test_subscription_creation_rejects_foreign_client_and_service(self):
        foreign_service = Service.objects.create(owner=self.other, name="Prime")
        foreign_client = Client.objects.create(owner=self.other, name="Ajeno")

        sub, error = create_subscription(
            self.owner,
            {
                "client_id": foreign_client.pk,
                "service_id": foreign_service.pk,
                "account_email": "ajena@example.com",
            },
        )

        self.assertIsNone(sub)
        self.assertEqual(error, "not_found")

    @patch("gestion.telegram_alerts._render")
    @patch("gestion.telegram_alerts._ack")
    def test_callback_cannot_open_another_owners_client(self, ack, render):
        foreign_client, _ = self._subscription(self.other, "Cliente secreto")
        TelegramConnection.objects.create(owner=self.owner, chat_id="123")

        process_update(
            {
                "callback_query": {
                    "id": "callback-1",
                    "data": f"client:{foreign_client.pk}",
                    "message": {"message_id": 9, "chat": {"id": 123}},
                }
            }
        )

        text = render.call_args.args[1]
        self.assertIn("no existe o no tienes permiso", text)
        self.assertNotIn("Cliente secreto", text)

    @patch("gestion.telegram_alerts.send_message")
    def test_digest_never_includes_another_owners_clients(self, send):
        today = timezone.localdate()
        for owner, client_name in ((self.owner, "Cliente propio"), (self.other, "Cliente ajeno")):
            service = Service.objects.create(owner=owner, name=f"Netflix {owner.pk}")
            client = Client.objects.create(owner=owner, name=client_name)
            Subscription.objects.create(
                owner=owner,
                client=client,
                service=service,
                account_email=f"{owner.pk}@example.com",
                starts_at=timezone.now(),
                expires_at=timezone.now(),
            )
        TelegramConnection.objects.create(owner=self.owner, chat_id="123", notify_windows=[0])

        self.assertEqual(send_expiry_digests(today), 1)
        message = send.call_args.args[1]
        self.assertIn("Cliente propio", message)
        self.assertNotIn("Cliente ajeno", message)
        self.assertEqual(send_expiry_digests(today), 0)

    @patch("gestion.telegram_alerts.send_message")
    def test_digest_rejects_cross_owner_relations_even_if_row_is_corrupt(self, send):
        own_service = Service.objects.create(owner=self.owner, name="Netflix propio")
        foreign_service = Service.objects.create(owner=self.other, name="Netflix ajeno")
        own_client = Client.objects.create(owner=self.owner, name="Cliente propio")
        foreign_client = Client.objects.create(owner=self.other, name="Cliente ajeno")
        common = {
            "owner": self.owner,
            "account_email": "cuenta@example.com",
            "starts_at": timezone.now(),
            "expires_at": timezone.now(),
        }
        Subscription.objects.create(
            client=own_client,
            service=own_service,
            **common,
        )
        # Filas deliberadamente inconsistentes: owner=A, relación=B.
        Subscription.objects.create(
            client=foreign_client,
            service=own_service,
            **common,
        )
        Subscription.objects.create(
            client=own_client,
            service=foreign_service,
            **common,
        )
        TelegramConnection.objects.create(
            owner=self.owner,
            chat_id="123",
            notify_windows=[0],
        )

        self.assertEqual(send_expiry_digests(timezone.localdate()), 1)
        message = send.call_args.args[1]
        self.assertEqual(message.count("Cliente propio"), 1)
        self.assertNotIn("Cliente ajeno", message)
        self.assertNotIn("Netflix ajeno", message)
