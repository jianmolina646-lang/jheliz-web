"""Run against disposable PostgreSQL, never the production database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from django.contrib.auth import get_user_model
from django.db import connections, close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature, override_settings, Client as WebClient
from django.utils import timezone

from .control_operations import replace_account_credentials
from .models import Client, Service, Subscription, SupportContact, Tenant, RenewalRequest
from .support_operations import create_ticket


@skipUnlessDBFeature('has_select_for_update')
@override_settings(ALLOWED_HOSTS=['jheliztv.xyz','testserver'], SECURE_SSL_REDIRECT=False)
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('concurrent-a')
        self.other=get_user_model().objects.create_user('concurrent-b')
        for user in (self.owner,self.other):
            Tenant.objects.create(user=user,plan_expires_at=timezone.now()+timedelta(days=30))
        self.ca=Client.objects.create(owner=self.owner,name='A')
        self.cb=Client.objects.create(owner=self.owner,name='B')
        self.contact_a=SupportContact.objects.create(owner=self.owner,client=self.ca)
        self.contact_b=SupportContact.objects.create(owner=self.owner,client=self.cb)
        self.service=Service.objects.create(owner=self.owner,name='A')
        self.sub=Subscription.objects.create(owner=self.owner,client=self.ca,service=self.service,
            account_email='shared@example.invalid',expires_at=timezone.now()+timedelta(days=30))

    def parallel(self, functions):
        gate=Barrier(len(functions))
        def execute(fn):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                return fn()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(functions)) as executor:
            results=[executor.submit(execute,fn) for fn in functions]
            return [future.result(timeout=30) for future in results]

    def test_different_contacts_get_unique_sequential_ticket_numbers(self):
        def create(contact_id):
            contact=SupportContact.objects.get(pk=contact_id)
            return create_ticket(contact,'access','Concurrent').number
        functions=[lambda pk=pk:create(pk) for pk in [self.contact_a.pk,self.contact_b.pk]*3]
        self.assertEqual(sorted(self.parallel(functions)),list(range(1,7)))

    def test_simultaneous_approval_extends_only_once(self):
        renewal=RenewalRequest.objects.create(owner=self.owner,subscription=self.sub,
            expiry_date=self.sub.expires_at.date(),status='proof_sent')
        clients=[WebClient(),WebClient()]
        for client in clients:
            client.force_login(self.owner)
        before=self.sub.expires_at
        functions=[lambda client=client:client.post(f'/app/renovaciones/{renewal.pk}/revisar/',
            {'action':'approve','days':1},HTTP_HOST='jheliztv.xyz').status_code for client in clients]
        self.assertEqual(self.parallel(functions),[302,302])
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.expires_at,before+timedelta(days=1))

    def test_concurrent_credential_replacement_stays_in_its_tenant(self):
        client=Client.objects.create(owner=self.other,name='Foreign')
        service=Service.objects.create(owner=self.other,name='Foreign')
        foreign=Subscription.objects.create(owner=self.other,client=client,service=service,
            account_email=self.sub.account_email,account_password='unchanged',expires_at=self.sub.expires_at)
        before=self.sub.expires_at
        self.parallel([lambda:replace_account_credentials(self.owner,'shared@example.invalid','new-a','a-secret','concurrent-a'),
                       lambda:replace_account_credentials(self.owner,'shared@example.invalid','new-b','b-secret','concurrent-b')])
        foreign.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual(foreign.account_email,'shared@example.invalid')
        self.assertEqual(foreign.account_password,'unchanged')
        self.assertEqual(self.sub.expires_at,before)
        self.assertIn(self.sub.account_email,{'new-a','new-b'})
