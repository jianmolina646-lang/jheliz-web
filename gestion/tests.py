"""Tests de Jheliz Control: modelos (utilidad, semáforo, contador, renovar),
vistas (render + acciones) y reporte PDF."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Client,
    ControlSettings,
    Service,
    ServiceCategory,
    Subscription,
    Transaction,
)


class ModelLogicTests(TestCase):
    def setUp(self):
        self.cat = ServiceCategory.objects.create(name="TV", slug="tv")
        self.svc = Service.objects.create(name="Disney+", category=self.cat)
        self.cli = Client.objects.create(name="Juan", telegram="juan", whatsapp="+51 987 654 321")

    def _sub(self, **kw):
        defaults = dict(
            client=self.cli, service=self.svc, account_email="a@b.com",
            cost=Decimal("15.00"), investment=Decimal("5.00"),
            expires_at=timezone.now() + timedelta(days=10),
        )
        defaults.update(kw)
        return Subscription.objects.create(**defaults)

    def test_profit(self):
        self.assertEqual(self._sub().profit, Decimal("10.00"))

    def test_status_green(self):
        self.assertEqual(self._sub(expires_at=timezone.now() + timedelta(days=5)).status_color, "green")

    def test_status_yellow(self):
        self.assertEqual(self._sub(expires_at=timezone.now() + timedelta(days=2)).status_color, "yellow")

    def test_status_red(self):
        self.assertEqual(self._sub(expires_at=timezone.now() + timedelta(hours=3)).status_color, "red")

    def test_status_expired(self):
        s = self._sub(expires_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(s.status_color, "expired")
        self.assertTrue(s.is_expired)
        self.assertEqual(s.time_left_label, "Vencida")

    def test_renew_accumulates(self):
        s = self._sub(expires_at=timezone.now() + timedelta(days=5))
        before = s.expires_at
        s.renew(30)
        self.assertAlmostEqual((s.expires_at - before).days, 30, delta=1)

    def test_renew_from_now_when_expired(self):
        s = self._sub(expires_at=timezone.now() - timedelta(days=2))
        s.renew(30)
        self.assertGreater(s.seconds_left, 28 * 86400)

    def test_telegram_normalized(self):
        c = Client.objects.create(name="X", telegram="pepe")
        self.assertEqual(c.telegram, "@pepe")
        self.assertEqual(c.telegram_handle, "pepe")

    def test_whatsapp_digits(self):
        self.assertEqual(self.cli.whatsapp_digits, "51987654321")

    def test_settings_singleton(self):
        a = ControlSettings.load()
        b = ControlSettings.load()
        self.assertEqual(a.pk, b.pk)


class ViewTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.user = U.objects.create_user("admin", password="pw", is_staff=True, is_superuser=True)
        self.client.force_login(self.user)
        self.cat = ServiceCategory.objects.create(name="TV", slug="tv")
        self.svc = Service.objects.create(name="Disney+", category=self.cat, owner=self.user)
        self.cli = Client.objects.create(
            name="Juan", telegram="juan", whatsapp="+51987654321", owner=self.user,
        )
        self.sub = Subscription.objects.create(
            client=self.cli, service=self.svc, account_email="a@b.com",
            account_password="secret", cost=Decimal("15"), investment=Decimal("5"),
            expires_at=timezone.now() + timedelta(days=2), owner=self.user,
        )

    def test_pages_render(self):
        for name, args in [
            ("gestion_dashboard", []),
            ("gestion_services", []),
            ("gestion_service_detail", [self.svc.pk]),
            ("gestion_clients", []),
            ("gestion_search", []),
        ]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_search_finds_by_email(self):
        r = self.client.get(reverse("gestion_search"), {"q": "a@b.com"})
        self.assertContains(r, "Juan")

    def test_notifications_json(self):
        r = self.client.get(reverse("gestion_notifications"))
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 1)

    def test_add_client(self):
        r = self.client.post(reverse("gestion_client_add"),
                             {"name": "Maria", "telegram": "maria"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Client.objects.filter(name="Maria").exists())

    def test_add_subscription_creates_transactions(self):
        r = self.client.post(reverse("gestion_subscription_add"), {
            "service": self.svc.pk, "client": self.cli.pk, "account_email": "x@y.com",
            "plan": "perfil", "profiles": "2", "cost": "20", "investment": "8",
            "duration_days": "30",
        })
        self.assertEqual(r.status_code, 302)
        s = Subscription.objects.get(account_email="x@y.com")
        self.assertTrue(s.transactions.filter(kind="income").exists())
        self.assertTrue(s.transactions.filter(kind="expense").exists())

    def test_renew_view(self):
        before = self.sub.expires_at
        self.client.post(reverse("gestion_subscription_renew", args=[self.sub.pk]), {"days": "30"})
        self.sub.refresh_from_db()
        self.assertGreater(self.sub.expires_at, before)

    def test_edit_preserves_expiry(self):
        before = self.sub.expires_at
        self.client.post(reverse("gestion_subscription_edit", args=[self.sub.pk]), {
            "service": self.svc.pk, "client": self.cli.pk, "account_email": "new@y.com",
            "plan": "completa", "profiles": "1", "cost": "30", "investment": "5",
        })
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.account_email, "new@y.com")
        self.assertAlmostEqual((self.sub.expires_at - before).total_seconds(), 0, delta=5)

    def test_client_report_pdf(self):
        r = self.client.get(reverse("gestion_client_report", args=[self.cli.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_requires_staff(self):
        self.client.logout()
        r = self.client.get(reverse("gestion_dashboard"))
        self.assertIn(r.status_code, (301, 302))


@override_settings(
    ALLOWED_HOSTS=["jheliztv.xyz", "www.jheliztv.xyz", "ecormecejhelizstore.com", "testserver"],
    JHELIZTV_HOSTS=["jheliztv.xyz", "www.jheliztv.xyz"],
)
class TenantSaasTests(TestCase):
    """Producto SaaS jheliztv.xyz: ruteo por dominio, login propio,
    aislamiento de datos por inquilino y cobro Yape con aprobación manual."""

    HOST = "jheliztv.xyz"
    # Rutas literales del producto (el ROOT_URLCONF por defecto no las resuelve;
    # el middleware de dominio las activa en cada request por HTTP_HOST).
    REGISTER = "/registro/"
    DASHBOARD = "/app/"
    BILLING = "/suscripcion/"
    BILLING_UPLOAD = "/suscripcion/pagar/"
    SERVICE_ADD = "/app/servicios/agregar/"
    CLIENT_ADD = "/app/clientes/agregar/"
    CLIENTS = "/app/clientes/"

    def setUp(self):
        from .models import SaasSettings, Tenant

        SaasSettings.load()
        self.Tenant = Tenant

    def _register(self, username, business="Negocio"):
        return self.client.post(
            self.REGISTER,
            {
                "username": username, "business_name": business,
                "password": "clave123", "password2": "clave123",
            },
            HTTP_HOST=self.HOST,
        )

    def test_domain_routing_isolated_from_store(self):
        # En el dominio del producto sí existe /registro/.
        self.assertEqual(self.client.get(self.REGISTER, HTTP_HOST=self.HOST).status_code, 200)
        # En el dominio de la tienda NO se exponen las URLs del producto.
        self.assertEqual(self.client.get(self.REGISTER, HTTP_HOST="ecormecejhelizstore.com").status_code, 404)

    def test_register_grants_free_trial(self):
        r = self._register("inq1")
        self.assertEqual(r.status_code, 302)
        tenant = self.Tenant.objects.get(user__username="inq1")
        # Al registrarse arranca con la prueba gratis: acceso activo sin pagar.
        self.assertTrue(tenant.subscription_active)
        self.assertGreaterEqual(tenant.days_left, self.Tenant.TRIAL_DAYS - 1)
        # Con la prueba vigente, el panel responde 200 (no redirige a cobro).
        self.assertEqual(
            self.client.get(self.DASHBOARD, HTTP_HOST=self.HOST).status_code, 200
        )

    def test_expired_trial_blocks_until_paid(self):
        from datetime import timedelta

        from django.utils import timezone

        self._register("inq1b")
        tenant = self.Tenant.objects.get(user__username="inq1b")
        # Simula prueba vencida: sin pago, el panel redirige a "Mi suscripción".
        tenant.plan_expires_at = timezone.now() - timedelta(days=1)
        tenant.save(update_fields=["plan_expires_at"])
        self.assertFalse(tenant.subscription_active)
        r = self.client.get(self.DASHBOARD, HTTP_HOST=self.HOST)
        self.assertRedirects(r, self.BILLING, fetch_redirect_response=False)

    def test_payment_approval_activates_account(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .models import TenantPayment

        self._register("inq2")
        tenant = self.Tenant.objects.get(user__username="inq2")
        proof = SimpleUploadedFile("p.png", b"\x89PNG\r\n\x1a\n" + b"0" * 40, content_type="image/png")
        self.client.post(self.BILLING_UPLOAD, {"proof": proof}, HTTP_HOST=self.HOST)
        pay = TenantPayment.objects.get(tenant=tenant)
        self.assertEqual(pay.status, TenantPayment.Status.PENDING)
        pay.approve()
        tenant.refresh_from_db()
        self.assertTrue(tenant.subscription_active)
        self.assertEqual(pay.status, TenantPayment.Status.APPROVED)
        # Ya activo: el panel responde 200.
        self.assertEqual(self.client.get(self.DASHBOARD, HTTP_HOST=self.HOST).status_code, 200)

    def test_data_isolation_between_tenants(self):
        # Inquilino A crea un servicio y un cliente.
        self._register("alice")
        ta = self.Tenant.objects.get(user__username="alice")
        ta.extend(30)
        self.client.post(self.SERVICE_ADD, {"name": "Netflix"}, HTTP_HOST=self.HOST)
        self.client.post(self.CLIENT_ADD, {"name": "Cliente A"}, HTTP_HOST=self.HOST)
        self.assertEqual(Service.objects.filter(owner=ta.user).count(), 1)

        # Inquilino B, recién logueado, no ve nada de A.
        self.client.logout()
        self._register("bob")
        tb = self.Tenant.objects.get(user__username="bob")
        tb.extend(30)
        self.assertEqual(Service.objects.filter(owner=tb.user).count(), 0)
        self.assertEqual(Client.objects.filter(owner=tb.user).count(), 0)
        r = self.client.get(self.CLIENTS, HTTP_HOST=self.HOST)
        self.assertNotContains(r, "Cliente A")

    def test_service_edit_updates_name_and_logo(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        self._register("carol")
        tc = self.Tenant.objects.get(user__username="carol")
        tc.extend(30)
        self.client.post(self.SERVICE_ADD, {"name": "Netflix"}, HTTP_HOST=self.HOST)
        svc = Service.objects.get(owner=tc.user, name="Netflix")

        buf = io.BytesIO()
        Image.new("RGB", (8, 8), "#e50914").save(buf, format="PNG")
        logo = SimpleUploadedFile("logo.png", buf.getvalue(), content_type="image/png")
        r = self.client.post(
            f"/app/servicios/{svc.pk}/editar/",
            {"name": "Netflix Premium", "icon": "live_tv", "color": "#e50914", "image": logo},
            HTTP_HOST=self.HOST,
        )
        self.assertRedirects(
            r, f"/app/servicios/{svc.pk}/", fetch_redirect_response=False
        )
        svc.refresh_from_db()
        self.assertEqual(svc.name, "Netflix Premium")
        self.assertEqual(svc.color, "#e50914")
        self.assertTrue(svc.image)

    def test_service_edit_blocked_for_other_owner(self):
        # Inquilino dueño crea el servicio.
        self._register("owner1")
        to = self.Tenant.objects.get(user__username="owner1")
        to.extend(30)
        self.client.post(self.SERVICE_ADD, {"name": "HBO"}, HTTP_HOST=self.HOST)
        svc = Service.objects.get(owner=to.user, name="HBO")

        # Otro inquilino no puede editar el servicio ajeno (404).
        self.client.logout()
        self._register("intruder")
        ti = self.Tenant.objects.get(user__username="intruder")
        ti.extend(30)
        r = self.client.post(
            f"/app/servicios/{svc.pk}/editar/",
            {"name": "Hackeado"}, HTTP_HOST=self.HOST,
        )
        self.assertEqual(r.status_code, 404)
        svc.refresh_from_db()
        self.assertEqual(svc.name, "HBO")

    SUB_ADD = "/app/suscripciones/agregar/"

    def _new_service(self, username="seller", name="Netflix"):
        self._register(username)
        t = self.Tenant.objects.get(user__username=username)
        t.extend(30)
        self.client.post(self.SERVICE_ADD, {"name": name}, HTTP_HOST=self.HOST)
        return t, Service.objects.get(owner=t.user, name=name)

    def test_subscription_add_multiple_emails_splits_totals(self):
        t, svc = self._new_service("seller1")
        cli = Client.objects.create(owner=t.user, name="Juan")
        r = self.client.post(
            self.SUB_ADD,
            {
                "service": svc.pk, "client": cli.pk,
                "account_emails": "a@x.com, b@x.com, c@x.com",
                "account_password": "Pass123",
                "plan": "perfil", "profiles": "2",
                "plan_label": "Premium", "duration_days": "30",
                "cost": "30", "investment": "12",
            },
            HTTP_HOST=self.HOST,
        )
        self.assertRedirects(r, f"/app/servicios/{svc.pk}/", fetch_redirect_response=False)
        subs = Subscription.objects.filter(owner=t.user, service=svc).order_by("account_email")
        self.assertEqual(subs.count(), 3)
        # El total (30/12) se reparte en partes iguales entre los 3 correos.
        for s in subs:
            self.assertEqual(s.cost, Decimal("10.00"))
            self.assertEqual(s.investment, Decimal("4.00"))
            self.assertEqual(s.account_password, "Pass123")
            self.assertEqual(s.plan_label, "Premium")
            self.assertEqual(s.profiles, 2)
        self.assertEqual({s.account_email for s in subs}, {"a@x.com", "b@x.com", "c@x.com"})

    def test_service_detail_renders_new_subscription_modal(self):
        t, svc = self._new_service("seller_render")
        Client.objects.create(owner=t.user, name="Pepe", telegram="@pepe")
        r = self.client.get(f"/app/servicios/{svc.pk}/", HTTP_HOST=self.HOST)
        self.assertEqual(r.status_code, 200)
        for token in (
            "Selección rápida de cliente", "Agregar Suscripción",
            "cuenta completa", "¿Cuánto vendiste en total?",
            "account_emails", "data-jc-csearch",
        ):
            self.assertContains(r, token)

    def test_subscription_add_cuenta_completa_forces_one_profile(self):
        t, svc = self._new_service("seller2")
        cli = Client.objects.create(owner=t.user, name="Ana")
        self.client.post(
            self.SUB_ADD,
            {
                "service": svc.pk, "client": cli.pk,
                "account_emails": "full@x.com",
                "plan": "completa", "profiles": "5", "duration_days": "30",
            },
            HTTP_HOST=self.HOST,
        )
        s = Subscription.objects.get(account_email="full@x.com")
        self.assertEqual(s.plan, "completa")
        self.assertEqual(s.profiles, 1)

    def test_subscription_add_creates_inline_client(self):
        t, svc = self._new_service("seller3")
        self.client.post(
            self.SUB_ADD,
            {
                "service": svc.pk, "client": "",
                "new_client_name": "Cliente Nuevo",
                "new_client_whatsapp": "+51987654321",
                "account_emails": "n@x.com", "duration_days": "30",
            },
            HTTP_HOST=self.HOST,
        )
        cli = Client.objects.get(owner=t.user, name="Cliente Nuevo")
        self.assertEqual(cli.whatsapp, "+51987654321")
        self.assertTrue(Subscription.objects.filter(client=cli, account_email="n@x.com").exists())


@override_settings(
    ALLOWED_HOSTS=["jheliztv.xyz", "www.jheliztv.xyz", "ecormecejhelizstore.com", "testserver"],
    JHELIZTV_HOSTS=["jheliztv.xyz", "www.jheliztv.xyz"],
)
class OwnerControlPanelTests(TestCase):
    """Panel del dueño en jheliztv.xyz/control/: solo staff, ve inquilinos,
    aprueba pagos Yape y suma días — separado de la web del inquilino."""

    HOST = "jheliztv.xyz"
    CONTROL = "/control/"
    CONTROL_LOGIN = "/control/ingresar/"

    def setUp(self):
        from .models import SaasSettings, Tenant

        SaasSettings.load()
        self.Tenant = Tenant
        U = get_user_model()
        self.owner = U.objects.create_user("dueno", password="pw", is_staff=True, is_superuser=True)
        self.tenant_user = U.objects.create_user("inq", password="pw")
        self.tenant = Tenant.objects.create(user=self.tenant_user, business_name="Negocio Inq", whatsapp="+51987111222")
        self.tenant.start_trial()

    def test_control_only_on_jheliztv_host(self):
        # En el dominio de la tienda no existe /control/.
        self.assertEqual(
            self.client.get(self.CONTROL_LOGIN, HTTP_HOST="ecormecejhelizstore.com").status_code, 404
        )

    def test_control_requires_login(self):
        r = self.client.get(self.CONTROL, HTTP_HOST=self.HOST)
        self.assertRedirects(r, self.CONTROL_LOGIN, fetch_redirect_response=False)

    def test_non_staff_cannot_login(self):
        r = self.client.post(
            self.CONTROL_LOGIN, {"username": "inq", "password": "pw"}, HTTP_HOST=self.HOST
        )
        # Sigue en la página de login (no entra al panel).
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Acceso solo para el administrador")

    def test_staff_sees_registered_tenants(self):
        self.client.post(self.CONTROL_LOGIN, {"username": "dueno", "password": "pw"}, HTTP_HOST=self.HOST)
        r = self.client.get(self.CONTROL, HTTP_HOST=self.HOST)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Negocio Inq")
        self.assertContains(r, "Clientes registrados")

    def test_approve_payment_activates_tenant(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import TenantPayment

        # Inquilino con prueba vencida + un pago pendiente.
        self.tenant.plan_expires_at = timezone.now() - timedelta(days=1)
        self.tenant.save(update_fields=["plan_expires_at"])
        pay = TenantPayment.objects.create(tenant=self.tenant, amount=30, days=30)

        self.client.post(self.CONTROL_LOGIN, {"username": "dueno", "password": "pw"}, HTTP_HOST=self.HOST)
        self.client.post(f"/control/pagos/{pay.pk}/aprobar/", HTTP_HOST=self.HOST)

        pay.refresh_from_db()
        self.tenant.refresh_from_db()
        self.assertEqual(pay.status, TenantPayment.Status.APPROVED)
        self.assertTrue(self.tenant.subscription_active)

    def test_extend_tenant_adds_days(self):
        self.client.post(self.CONTROL_LOGIN, {"username": "dueno", "password": "pw"}, HTTP_HOST=self.HOST)
        before = self.tenant.days_left
        self.client.post(f"/control/inquilinos/{self.tenant.pk}/extender/", {"days": "30"}, HTTP_HOST=self.HOST)
        self.tenant.refresh_from_db()
        self.assertGreater(self.tenant.days_left, before)

    def test_block_and_unblock_tenant(self):
        self.client.post(self.CONTROL_LOGIN, {"username": "dueno", "password": "pw"}, HTTP_HOST=self.HOST)
        # Bloquear: el inquilino queda sin acceso aunque tenga alquiler vigente.
        self.client.post(f"/control/inquilinos/{self.tenant.pk}/bloquear/", HTTP_HOST=self.HOST)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_blocked)
        self.assertFalse(self.tenant.subscription_active)
        # Desbloquear: vuelve a tener acceso.
        self.client.post(f"/control/inquilinos/{self.tenant.pk}/bloquear/", HTTP_HOST=self.HOST)
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.is_blocked)
