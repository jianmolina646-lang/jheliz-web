from datetime import timedelta
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from .admin import ClientAdmin
from .models import Client, Service, Subscription, StockEmail, SupportContact, SupportTicket, RenewalRequest, ResellerPaymentMethod, Transaction
from .support_operations import create_ticket
from .testing import force_owner_login


@override_settings(ALLOWED_HOSTS=['jheliztv.xyz','testserver'], SECURE_SSL_REDIRECT=False)
class OwnerHardeningTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser('owner-hardening', password='test-password')

    def request(self, path, data=None):
        method = self.client.get if data is None else self.client.post
        return method(path, data, HTTP_HOST='jheliztv.xyz')

    def token(self, device):
        return str(totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits, drift=device.drift)).zfill(device.digits)

    def test_owner_without_otp_must_enroll_before_dashboard(self):
        response = self.request('/control/ingresar/', {'username':self.owner.username,'password':'test-password'})
        self.assertEqual(response['Location'], '/control/2fa/configurar/')
        self.assertEqual(self.request('/control/')['Location'], '/control/2fa/configurar/')
        self.assertEqual(self.request('/control/2fa/configurar/').status_code,200)
        self.request('/control/2fa/configurar/', {'action':'create'})
        device = TOTPDevice.objects.get(user=self.owner)
        self.assertFalse(device.confirmed)
        response = self.request('/control/2fa/configurar/', {'action':'verify','token':self.token(device)})
        self.assertEqual(response['Location'],'/control/')
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(self.request('/control/').status_code,200)

    def test_existing_devices_are_preserved_regardless_of_name(self):
        original = TOTPDevice.objects.create(user=self.owner, name='original-phone',confirmed=True)
        second = TOTPDevice.objects.create(user=self.owner, name='backup-phone',confirmed=True)
        original_keys = list(TOTPDevice.objects.values_list('pk','key'))
        self.request('/control/ingresar/', {'username':self.owner.username,'password':'test-password'})
        self.request('/control/2fa/verificar/', {'token':self.token(original)})
        response = self.request('/control/2fa/configurar/', {'action':'create'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(list(TOTPDevice.objects.values_list('pk','key')),original_keys)
        self.assertNotContains(response, original.key)
        self.assertNotContains(response, second.key)
        self.assertIn('no-store',response['Cache-Control'])

    def test_legacy_boolean_does_not_bypass_otp(self):
        TOTPDevice.objects.create(user=self.owner,confirmed=True)
        self.client.force_login(self.owner)
        session=self.client.session
        session['jheliz_control_otp_verified']=True
        session.save()
        self.assertEqual(self.request('/control/')['Location'],'/control/2fa/verificar/')

    def test_revoked_device_invalidates_verified_session(self):
        force_owner_login(self.client,self.owner)
        verified = TOTPDevice.objects.get(user=self.owner)
        TOTPDevice.objects.create(user=self.owner,name='remaining',confirmed=True)
        verified.delete()
        self.assertEqual(self.request('/control/')['Location'],'/control/2fa/verificar/')

    def test_limited_staff_model_permission_does_not_grant_global_clients(self):
        staff=get_user_model().objects.create_user('limited',is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_client',content_type__app_label='gestion'))
        request=RequestFactory().get('/')
        request.user=staff
        admin=ClientAdmin(Client,AdminSite())
        Client.objects.create(owner=self.owner,name='private')
        self.assertFalse(admin.has_view_permission(request))
        self.assertFalse(admin.get_queryset(request).exists())


class OwnershipInvariantTests(TestCase):
    def setUp(self):
        self.a=get_user_model().objects.create_user('invariant-a')
        self.b=get_user_model().objects.create_user('invariant-b')
        self.ca=Client.objects.create(owner=self.a,name='A')
        self.cb=Client.objects.create(owner=self.b,name='B')
        self.sa=Service.objects.create(owner=self.a,name='A')
        self.sb=Service.objects.create(owner=self.b,name='B')
        self.sub=Subscription.objects.create(owner=self.a,client=self.ca,service=self.sa,
            account_email='a@example.invalid',expires_at=timezone.now()+timedelta(days=30))

    def test_cross_owner_relations_rejected_on_save(self):
        invalid = [
            Subscription(owner=self.a,client=self.cb,service=self.sa,account_email='invalid'),
            Subscription(owner=self.a,client=self.ca,service=self.sb,account_email='invalid'),
            StockEmail(owner=self.a,service=self.sb,email='invalid'),
            SupportContact(owner=self.a,client=self.cb),
            SupportTicket(owner=self.b,client=self.cb,subscription=self.sub,number=1),
            RenewalRequest(owner=self.b,subscription=self.sub,expiry_date=timezone.localdate()),
            Transaction(owner=self.b,client=self.ca,amount=1,kind='income'),
        ]
        for item in invalid:
            with self.subTest(model=type(item).__name__), self.assertRaises(ValidationError):
                item.save()

    def test_existing_owner_cannot_be_reassigned(self):
        self.ca.owner=self.b
        with self.assertRaises(ValidationError):
            self.ca.save()
        self.ca.refresh_from_db()
        self.assertEqual(self.ca.owner_id,self.a.pk)

    def test_renewal_cannot_use_foreign_payment_method(self):
        method=ResellerPaymentMethod.objects.create(owner=self.b,kind='yape',label='B',details='B')
        with self.assertRaises(ValidationError):
            RenewalRequest.objects.create(owner=self.a,subscription=self.sub,payment_method=method,expiry_date=timezone.localdate())

    def test_support_operation_rejects_wrong_client_even_with_same_owner(self):
        other_client=Client.objects.create(owner=self.a,name='Other A')
        contact=SupportContact.objects.create(owner=self.a,client=other_client)
        with self.assertRaises(ValidationError):
            create_ticket(contact,'access','Test',subscription=self.sub)
        self.assertFalse(SupportTicket.objects.exists())
