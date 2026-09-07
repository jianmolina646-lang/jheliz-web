from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from PIL import Image
from unittest.mock import patch
from django.test import TestCase, override_settings, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from gestion.models import Tenant, Client, Service, Subscription, RenewalRequest, ResellerPaymentMethod
from gestion import views, telegram_alerts

@override_settings(ALLOWED_HOSTS=['testserver', 'jheliztv.xyz'])
class TenantSecurityTests(TestCase):
    def setUp(self):
        self.a = get_user_model().objects.create_user('audit_a', is_staff=True)
        self.b = get_user_model().objects.create_user('audit_b')
        for u in (self.a, self.b):
            Tenant.objects.create(user=u, plan_expires_at=timezone.now()+timedelta(days=30))
        self.ca = Client.objects.create(owner=self.a, name='A')
        self.cb = Client.objects.create(owner=self.b, name='B')
        self.sa = Service.objects.create(owner=self.a, name='A')
        self.sb = Service.objects.create(owner=self.b, name='B')
        self.sub = Subscription.objects.create(owner=self.a, client=self.ca, service=self.sa,
            account_email='audit@example.invalid', expires_at=timezone.now()+timedelta(days=30))
        self.client.force_login(self.a)

    def post(self, path, data):
        return self.client.post(path, data, HTTP_HOST='jheliztv.xyz')

    def test_legacy_cross_owner_assignment_denied(self):
        request = RequestFactory().post('/', {'client': self.cb.pk, 'service': self.sb.pk,
            'account_email':'audit@example.invalid', 'plan':'perfil', 'profiles':1})
        request.user = self.a
        request.session = {}
        request._messages = FallbackStorage(request)
        response = views.subscription_edit(request, self.sub.pk)
        self.sub.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.sub.client_id, self.ca.pk)
        self.assertEqual(self.sub.service_id, self.sa.pk)
        self.assertEqual(self.sub.owner_id, self.a.pk)

    def test_html_qr_upload_rejected(self):
        response = self.post('/app/renovaciones/metodos/agregar/', {'kind':'yape', 'label':'Audit',
            'details':'Audit', 'qr_image':SimpleUploadedFile('audit.html', b'<html>AUDIT</html>', content_type='text/html')})
        self.assertEqual(response.status_code,302)
        self.assertFalse(ResellerPaymentMethod.objects.filter(owner=self.a).exists())

    def test_double_approval_is_idempotent(self):
        renewal = RenewalRequest.objects.create(owner=self.a, subscription=self.sub,
            expiry_date=self.sub.expires_at.date(), status='proof_sent')
        path = f'/app/renovaciones/{renewal.pk}/revisar/'
        self.post(path, {'action':'approve','days':30})
        self.sub.refresh_from_db()
        first = self.sub.expires_at
        renewal.refresh_from_db()
        self.assertEqual(renewal.status, 'approved')
        self.post(path, {'action':'approve','days':30})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.expires_at,first)

    def test_approved_renewal_cannot_be_reopened(self):
        renewal = RenewalRequest.objects.create(owner=self.a, subscription=self.sub,
            expiry_date=self.sub.expires_at.date(), status='approved')
        self.post(f'/renovar/{renewal.token}/', {'action':'renew'})
        renewal.refresh_from_db()
        self.assertEqual(renewal.status, 'approved')

    def test_valid_qr_is_recoded_as_png(self):
        raw = BytesIO()
        Image.new('RGB', (20, 20), 'white').save(raw, format='JPEG')
        with TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            self.post('/app/renovaciones/metodos/agregar/', {'kind':'yape', 'label':'QR',
                'details':'Audit', 'qr_image':SimpleUploadedFile('qr.jpg',raw.getvalue())})
            method = ResellerPaymentMethod.objects.get(owner=self.a)
            self.assertTrue(method.qr_image.name.endswith('.png'))
            with method.qr_image.open('rb') as uploaded:
                self.assertEqual(uploaded.read(8), b'\x89PNG\r\n\x1a\n')

    def test_group_cannot_consume_link_token(self):
        self.assertFalse(telegram_alerts.link_chat('unused', {'id':-123,'type':'group'}))

    def test_private_chat_with_different_sender_is_rejected(self):
        with patch.object(telegram_alerts, '_linked_connection') as lookup:
            telegram_alerts.process_update({'message':{'chat':{'id':123,'type':'private'},
                'from':{'id':999},'text':'/menu'}})
            lookup.assert_not_called()

    def test_foreign_ids_denied(self):
        self.client.force_login(self.b)
        for path in (f'/app/suscripciones/{self.sub.pk}/credenciales.json',
                     f'/app/clientes/{self.ca.pk}/reporte.pdf'):
            self.assertEqual(self.client.get(path,HTTP_HOST='jheliztv.xyz').status_code,404)
        for path in (f'/app/clientes/{self.ca.pk}/eliminar/',
                     f'/app/suscripciones/{self.sub.pk}/eliminar/',
                     f'/app/servicios/{self.sa.pk}/eliminar/'):
            self.assertEqual(self.post(path,{}).status_code,404)
        self.assertTrue(Subscription.objects.filter(pk=self.sub.pk).exists())

    def test_group_actor_is_rejected(self):
        with patch.object(telegram_alerts,'_linked_connection',return_value=object()), \
             patch.object(telegram_alerts,'_has_active_access',return_value=True), \
             patch.object(telegram_alerts,'_main_menu') as menu:
            telegram_alerts.process_update({'message':{'chat':{'id':-123,'type':'group'},
                'from':{'id':999},'text':'/menu'}})
            menu.assert_not_called()
