import hashlib
import hmac
import json
import time
import uuid

from django.test import TestCase, override_settings
from django.urls import reverse

from codes.models import AssignedEmail, CodeBotClient


@override_settings(WHATSAPP_CODES_BRIDGE_SECRET="test-bridge-secret", WHATSAPP_CODES_ADMIN_NUMBERS="51978640413")
class WhatsAppBridgeTests(TestCase):
    def post(self, phone, text, name="Cliente", **extra):
        body = json.dumps({"phone": phone, "text": text, "name": name, "timestamp":time.time(), "request_id":str(uuid.uuid4()), **extra}).encode()
        signature = hmac.new(b"test-bridge-secret", body, hashlib.sha256).hexdigest()
        return self.client.post(reverse("whatsapp_codes_bridge"), body, content_type="application/json", HTTP_X_CODES_SIGNATURE=signature)

    def test_rejects_unsigned_call(self):
        response = self.client.post(reverse("whatsapp_codes_bridge"), b"{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_export_only_whatsapp_assignments(self):
        c = CodeBotClient.objects.create(telegram_chat_id='wa:51911111111', is_active=True)
        AssignedEmail.objects.create(client=c, email='owned@example.test')
        CodeBotClient.objects.create(telegram_chat_id='123456789')
        result = self.post('', '', action='export_assignments').json()
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(result['records'][0]['phone'], '51911111111')
        self.assertEqual(result['records'][0]['email'], 'owned@example.test')
        self.assertEqual(result['records'][0]['status'], 'Activo')
        self.assertNotIn('password', result['records'][0])

    def test_start_is_pending_and_admin_can_activate_and_assign(self):
        response = self.post("51911111111", "/start")
        self.assertEqual(response.status_code, 200)
        client = CodeBotClient.objects.get(telegram_chat_id="wa:51911111111")
        self.assertFalse(client.is_active)
        self.assertIn("pendiente", response.json()["messages"][0]["text"])
        self.post("51978640413", "/activar 51911111111")
        self.post("51978640413", "/asignar 51911111111 cliente@example.test")
        client.refresh_from_db()
        self.assertTrue(client.is_active)
        self.assertTrue(AssignedEmail.objects.filter(client=client, email="cliente@example.test").exists())

    def test_customer_cannot_access_admin_commands(self):
        self.post("51911111111", "/start")
        self.post("51978640413", "/activar 51911111111")
        response = self.post("51911111111", "/clientes")
        self.assertIn("/cmds", response.json()["messages"][0]["text"])
