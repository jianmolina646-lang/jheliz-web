"""Tests para el PR B — cabeceras de seguridad y endpoint del bell de notificaciones."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


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

    def test_x_robots_tag_on_admin_paths(self):
        """Las URLs del admin nunca deben ser indexables por buscadores."""
        # Aunque el admin redirige a login (no autenticado), el middleware
        # ya añadió la cabecera. Eso es defense-in-depth: incluso un 302
        # accidentalmente filtrado en logs no se indexa.
        resp = self.client.get("/panel-jheliz-2026/")
        self.assertEqual(
            resp.headers.get("X-Robots-Tag"), "noindex, nofollow, noarchive"
        )

    def test_x_robots_tag_absent_on_public_pages(self):
        """Las páginas públicas SÍ son indexables (no deben tener noindex)."""
        resp = self.client.get("/")
        self.assertNotIn("X-Robots-Tag", resp.headers)

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


class NotificationsBellEndpointTests(TestCase):
    """Tests del endpoint que alimenta el bell del admin (lista de pendientes)."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="admin", email="admin@example.com", password="x"
        )
        self.staff.is_staff = True
        self.staff.save()
        self.client.force_login(self.staff)
        self.url = reverse("admin_notifications_count")

    def _create_yape_order(self, *, total: str = "49.90", email: str = "buyer@example.com"):
        from orders.models import Order

        return Order.objects.create(
            email=email,
            phone="+51999000111",
            status=Order.Status.VERIFYING,
            total=Decimal(total),
            currency="PEN",
            payment_provider="yape",
        )

    def test_requires_staff(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)  # redirect a login

    def test_empty_state_returns_zero_counts_and_empty_items(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["verifying"], 0)
        self.assertEqual(data["preparing"], 0)
        self.assertEqual(data["open_tickets"], 0)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["items"], [])
        # Compat con el JS viejo del dashboard.
        self.assertEqual(data["counts"]["total"], 0)

    def test_verifying_yape_order_appears_in_items(self):
        order = self._create_yape_order(email="comprador@example.com")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verifying"], 1)
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["items"]), 1)

        item = data["items"][0]
        self.assertEqual(item["id"], f"order-verifying-{order.pk}")
        self.assertEqual(item["kind"], "yape_proof")
        # Título contiene short uuid + monto.
        self.assertIn(order.short_uuid, item["title"])
        self.assertIn("49.90", item["title"])
        # Subtítulo lleva el correo del cliente para identificarlo de un vistazo.
        self.assertIn("comprador@example.com", item["subtitle"])
        # URL apunta al detalle del pedido en el admin.
        self.assertEqual(
            item["url"],
            reverse("admin:orders_order_change", args=[order.pk]),
        )
        # `relative` es un string corto en español.
        self.assertTrue(item["relative"].startswith("hace"))

    def test_items_sorted_most_recent_first(self):
        from orders.models import Order
        from django.utils import timezone
        from datetime import timedelta

        old = self._create_yape_order(email="viejo@x.com")
        new = self._create_yape_order(email="nuevo@x.com")
        # Forzamos timestamps de subida del comprobante: `old` antes, `new` después.
        Order.objects.filter(pk=old.pk).update(
            payment_proof_uploaded_at=timezone.now() - timedelta(hours=2)
        )
        Order.objects.filter(pk=new.pk).update(
            payment_proof_uploaded_at=timezone.now() - timedelta(minutes=5)
        )

        resp = self.client.get(self.url)
        data = resp.json()
        ids = [it["id"] for it in data["items"]]
        self.assertEqual(
            ids,
            [f"order-verifying-{new.pk}", f"order-verifying-{old.pk}"],
        )

    def test_preparing_orders_also_listed(self):
        from orders.models import Order

        order = Order.objects.create(
            email="x@x.com",
            status=Order.Status.PREPARING,
            total=Decimal("100.00"),
            currency="PEN",
            payment_provider="mercadopago",
        )
        resp = self.client.get(self.url)
        data = resp.json()
        self.assertEqual(data["preparing"], 1)
        kinds = {it["kind"] for it in data["items"]}
        self.assertIn("preparing", kinds)
        # El título lleva la palabra "preparación" (con tilde, como aparece en UI).
        prep = [it for it in data["items"] if it["id"] == f"order-preparing-{order.pk}"][0]
        self.assertIn("preparación", prep["title"])

    def test_resolved_tickets_excluded_from_items(self):
        from support.models import Ticket

        Ticket.objects.create(
            user=self.staff,
            subject="Ya estaba resuelto",
            status=Ticket.Status.RESOLVED,
        )
        Ticket.objects.create(
            user=self.staff,
            subject="Tengo problemas con mi cuenta de Netflix",
            status=Ticket.Status.OPEN,
        )
        resp = self.client.get(self.url)
        data = resp.json()
        self.assertEqual(data["open_tickets"], 1)
        ticket_items = [it for it in data["items"] if it["kind"] == "ticket"]
        self.assertEqual(len(ticket_items), 1)
        self.assertIn("Netflix", ticket_items[0]["title"])


class AuditLogViewerTests(TestCase):
    """Tests del visor de auditoría (`/panel-jheliz-2026/auditoria/`)."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="x",
            is_staff=True,
        )
        self.list_url = reverse("admin_auditlog")

    def _create_log_entry(self, *, action, changes=None, object_repr="Pedido #1"):
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType
        from orders.models import Order

        ct = ContentType.objects.get_for_model(Order)
        return LogEntry.objects.create(
            content_type=ct,
            object_pk="1",
            object_id=1,
            object_repr=object_repr,
            action=action,
            changes=changes or {},
            actor=self.staff,
            remote_addr="10.0.0.1",
        )

    def test_requires_staff(self):
        self.client.logout()
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 302)  # redirect a login

    def test_list_page_renders_for_staff(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Auditoría")

    def test_list_shows_entry(self):
        from auditlog.models import LogEntry

        entry = self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            changes={"status": ["pending", "paid"]},
            object_repr="Pedido #1234",
        )
        self.client.force_login(self.staff)
        resp = self.client.get(self.list_url)
        self.assertContains(resp, "Pedido #1234")
        self.assertContains(resp, "Editó")
        # El diff aparece en el preview.
        self.assertContains(resp, "status")

    def test_filter_by_action(self):
        from auditlog.models import LogEntry

        self._create_log_entry(
            action=LogEntry.Action.CREATE, object_repr="Crear A",
        )
        self._create_log_entry(
            action=LogEntry.Action.UPDATE, object_repr="Editar B",
        )
        self.client.force_login(self.staff)
        resp = self.client.get(self.list_url + "?action=create")
        self.assertContains(resp, "Crear A")
        self.assertNotContains(resp, "Editar B")

    def test_filter_by_search(self):
        from auditlog.models import LogEntry

        self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            object_repr="Pedido único X",
        )
        self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            object_repr="Otro objeto Y",
        )
        self.client.force_login(self.staff)
        resp = self.client.get(self.list_url + "?q=único")
        self.assertContains(resp, "Pedido único X")
        self.assertNotContains(resp, "Otro objeto Y")

    def test_detail_page(self):
        from auditlog.models import LogEntry

        entry = self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            changes={"status": ["pending", "paid"], "total": ["10.00", "20.00"]},
            object_repr="Pedido #999",
        )
        self.client.force_login(self.staff)
        url = reverse("admin_auditlog_detail", args=[entry.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pedido #999")
        # El diff aparece en la tabla.
        self.assertContains(resp, "status")
        self.assertContains(resp, "total")
        self.assertContains(resp, "10.00")
        self.assertContains(resp, "20.00")

    def test_detail_404_for_unknown_entry(self):
        self.client.force_login(self.staff)
        url = reverse("admin_auditlog_detail", args=[999999])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_truncation_of_long_values(self):
        """Valores muy largos en `changes` se truncan al renderizar para no romper el layout."""
        from auditlog.models import LogEntry

        long_value = "a" * 500
        entry = self._create_log_entry(
            action=LogEntry.Action.UPDATE,
            changes={"notes": ["", long_value]},
        )
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_auditlog_detail", args=[entry.pk]))
        self.assertEqual(resp.status_code, 200)
        # El truncado del helper limita a 200 chars + elipsis.
        body = resp.content.decode()
        self.assertNotIn(long_value, body)


# -----------------------------------------------------------------------------
# i18n + multi-país
# -----------------------------------------------------------------------------

from django.urls import reverse
from django.test import override_settings


class CountryMiddlewareTests(TestCase):
    """Verifica que el middleware resuelve country desde cookie/header/default."""

    def test_default_country_when_no_cookie(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        # Por default debería ser PE.
        self.assertContains(resp, "🇵🇪")

    def test_country_from_cookie(self):
        self.client.cookies["jheliz_country"] = "BR"
        resp = self.client.get("/")
        # El selector del footer renderiza la bandera del país activo.
        self.assertContains(resp, "🇧🇷")

    def test_country_from_geo_header(self):
        # Sin cookie pero con header CF-IPCountry → debería resolver MX.
        resp = self.client.get("/", HTTP_CF_IPCOUNTRY="MX")
        self.assertContains(resp, "🇲🇽")

    def test_set_country_persists_cookie(self):
        resp = self.client.post(
            reverse("set_country"),
            {"code": "CO", "next": "/"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.cookies.get("jheliz_country").value, "CO")

    def test_set_country_rejects_unsupported(self):
        resp = self.client.post(
            reverse("set_country"),
            {"code": "ZZ", "next": "/"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_set_country_blocks_open_redirect(self):
        resp = self.client.post(
            reverse("set_country"),
            {"code": "CO", "next": "https://evil.example/"},
        )
        # Redirige pero a "/", no a la URL externa.
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/")


class LanguageSwitcherTests(TestCase):
    """La vista built-in de Django para set_language sigue funcionando."""

    def test_can_switch_to_english(self):
        resp = self.client.post(
            reverse("set_language"),
            {"language": "en", "next": "/"},
        )
        self.assertEqual(resp.status_code, 302)
        # La cookie de idioma se setea.
        self.assertEqual(resp.cookies.get("django_language").value, "en")

    def test_translates_navbar_in_english(self):
        # Activar inglés via cookie y verificar que el header lo refleja.
        self.client.cookies["django_language"] = "en"
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Products", body)
        self.assertIn("Log in", body)

    def test_translates_navbar_in_portuguese(self):
        self.client.cookies["django_language"] = "pt"
        resp = self.client.get("/")
        body = resp.content.decode()
        self.assertIn("Produtos", body)


class FooterPickerRenderTests(TestCase):
    """El footer renderiza los selectores con todos los países."""

    def test_footer_lists_all_countries(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # Que aparezca al menos un país de cada continente (sanity).
        self.assertIn("Perú", body)
        self.assertIn("Brasil", body)
        self.assertIn("Argentina", body)


class AdminDesignSystem2026Tests(TestCase):
    """PR1 del rediseño 2026: verifica que los assets nuevos del sistema
    de diseño se cargan en el admin y que los componentes reusables
    renderizan."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="staff-design",
            password="x",
            email="staff-design@example.com",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.staff)

    def test_admin_loads_jheliz_2026_css(self):
        # Usamos /panel-jheliz-2026/ (la home del admin) para verificar que
        # Unfold inyecta nuestra capa CSS 2026. Manifest static storage le
        # añade un hash al filename, por eso buscamos el prefijo.
        resp = self.client.get("/panel-jheliz-2026/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "jheliz_2026")

    def test_pill_component_renders(self):
        from django.template import Context, Template

        tpl = Template(
            "{% include 'admin/components/_pill.html' "
            "with text='Pagado' variant='success' %}"
        )
        out = tpl.render(Context({}))
        self.assertIn("jh2-pill", out)
        self.assertIn("jh2-pill--success", out)
        self.assertIn("Pagado", out)

    def test_stat_component_renders_with_link(self):
        from django.template import Context, Template

        tpl = Template(
            "{% include 'admin/components/_stat.html' with "
            "label='Pedidos hoy' value='42' icon='shopping_cart' "
            "variant='info' href='/foo/' %}"
        )
        out = tpl.render(Context({}))
        self.assertIn("jh2-stat", out)
        self.assertIn("jh2-stat--info", out)
        self.assertIn('href="/foo/"', out)
        self.assertIn("42", out)
        self.assertIn("Pedidos hoy", out)
        self.assertIn("shopping_cart", out)

    def test_empty_component_renders_with_cta(self):
        from django.template import Context, Template

        tpl = Template(
            "{% include 'admin/components/_empty.html' with "
            "icon='inbox' title='Sin pedidos' "
            "desc='Cuando llegue uno aparece acá.' "
            "cta_label='Crear' cta_href='/x/' %}"
        )
        out = tpl.render(Context({}))
        self.assertIn("jh2-empty", out)
        self.assertIn("Sin pedidos", out)
        self.assertIn("Cuando llegue uno aparece acá.", out)
        self.assertIn('href="/x/"', out)
        self.assertIn(">Crear<", out)


class ReportsViewDesignTests(TestCase):
    """Verifica que la vista /panel-jheliz-2026/reports/ renderiza el nuevo
    diseño basado en chips, KPIs con delta y sparkline.
    """

    def setUp(self) -> None:
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="reptester", password="x", is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_reports_view_renders_new_design_with_no_data(self):
        """Sin ventas: la página renderiza OK con los placeholders."""
        resp = self.client.get(reverse("admin_reports"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # 4 tarjetas KPI con el chip de delta.
        self.assertIn("jh-rep-kpi", body)
        self.assertIn("jh-rep-kpi--today", body)
        self.assertIn("jh-rep-kpi--week", body)
        self.assertIn("jh-rep-kpi--month", body)
        self.assertIn("jh-rep-kpi--year", body)
        # Sparkline siempre presente (con 30 barras incluso si todas son 0).
        self.assertIn("jh-rep-spark", body)
        # Secciones de las dos tablas redesigned.
        self.assertIn("Top 10 productos", body)
        self.assertIn("Ingresos por método", body)
        # Botones de export.
        self.assertIn("CSV últimos 7 días", body)

    def test_reports_view_renders_chips_with_real_data(self):
        """Con un pedido pagado: se ve el ícono del método y la barra del producto."""
        from datetime import timedelta
        from django.utils import timezone
        from catalog.models import Category, Plan, Product
        from orders.models import Order, OrderItem

        cat, _ = Category.objects.get_or_create(
            slug="streaming-rep-test",
            defaults={"name": "Streaming Reports Test"},
        )
        prod = Product.objects.create(
            name="Netflix Premium",
            slug="netflix-premium-rep-test",
            category=cat,
        )
        plan = Plan.objects.create(
            product=prod, name="1 mes",
            duration_days=30, price_customer=Decimal("15.00"),
        )
        order = Order.objects.create(
            email="cliente@example.com",
            phone="+51999111222",
            total=Decimal("15.00"),
            status=Order.Status.PAID,
            paid_at=timezone.now() - timedelta(hours=2),
            payment_provider="yape",
        )
        OrderItem.objects.create(
            order=order,
            product=prod,
            plan=plan,
            product_name=prod.name,
            unit_price=Decimal("15.00"),
            quantity=1,
        )

        resp = self.client.get(reverse("admin_reports"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # El producto aparece en top productos con barra.
        self.assertIn("Netflix Premium", body)
        self.assertIn("jh-rep-row__bar", body)
        # El método yape aparece con su label visible.
        self.assertIn("Yape", body)
        # La barra del método yape lleva la clase violet.
        self.assertIn("jh-rep-row__bar--violet", body)


class RenewalsViewDesignTests(TestCase):
    """Verifica que `/panel-jheliz-2026/renewals/` renderiza con chips,
    conteo por ventana y empty state cuando no hay items."""

    def setUp(self) -> None:
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="rentester", password="x", is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_renewals_empty_renders_celebration_empty_state(self):
        """Sin items y sin pendientes: empty state 'No hay nada por renovar'."""
        resp = self.client.get(reverse("admin_renewals"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # Tabs/chips con conteo.
        self.assertIn("jh-ren-tab", body)
        self.assertIn("jh-ren-tab__count", body)
        # 5 filtros visibles con sus labels.
        for label in ("Vencidos", "Vencen hoy", "Próx. 3 días", "Próx. 7 días", "Próx. 30 días"):
            self.assertIn(label, body)
        # Empty state happy path.
        self.assertIn("jh2-empty", body)
        self.assertIn("No hay nada por renovar", body)

    def test_renewals_with_item_renders_chips(self):
        """Con un item por vencer: aparecen chips de cliente, plan y días."""
        from datetime import timedelta
        from django.utils import timezone
        from catalog.models import Category, Plan, Product
        from orders.models import Order, OrderItem

        cat, _ = Category.objects.get_or_create(
            slug="ren-test-cat", defaults={"name": "Cat renewals test"},
        )
        prod = Product.objects.create(
            name="Netflix Premium",
            slug="netflix-ren-test",
            category=cat,
        )
        plan = Plan.objects.create(
            product=prod, name="1 mes",
            duration_days=30, price_customer=Decimal("15.00"),
        )
        order = Order.objects.create(
            email="cliente@example.com",
            phone="51999111222",
            total=Decimal("15.00"),
            status=Order.Status.DELIVERED,
            paid_at=timezone.now() - timedelta(days=20),
            payment_provider="yape",
        )
        OrderItem.objects.create(
            order=order, product=prod, plan=plan,
            product_name=prod.name, plan_name=plan.name,
            unit_price=Decimal("15.00"), quantity=1,
            expires_at=timezone.now() + timedelta(days=5),  # cae en 7d
        )

        resp = self.client.get(reverse("admin_renewals") + "?w=7d")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # Item visible.
        self.assertIn("cliente@example.com", body)
        self.assertIn("Netflix Premium", body)
        # Chip de días con tono info (entre 4 y 7 días).
        self.assertIn("jh-ren-chip--info", body)
        # Botón de renovar y de WhatsApp.
        self.assertIn("jh-ren-btn--renew", body)
        self.assertIn("jh-ren-btn--wa", body)
        # El chip de filtro "Próx. 7 días" muestra count=1 (cabe en ventana).
        self.assertIn('jh-ren-tab--has-items', body)


class LockedLoginsAdminTests(TestCase):
    """Tests para la pantalla del admin que desbloquea logins (django-axes)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="locks_admin", email="locks@ex.com", password="pw12345!",
        )

    def test_locked_logins_page_renders_empty(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_locked_logins"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Logins bloqueados", body)
        self.assertIn("No hay intentos fallidos", body)

    def test_locked_logins_page_lists_attempts(self):
        from axes.models import AccessAttempt

        AccessAttempt.objects.create(
            username="cliente@x.com",
            ip_address="10.0.0.1",
            user_agent="curl/8",
            failures_since_start=12,
            get_data="", post_data="", http_accept="", path_info="/admin/login/",
        )
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_locked_logins"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("cliente@x.com", body)
        self.assertIn("10.0.0.1", body)
        # 12 fallos contra threshold 10 → bloqueado
        self.assertIn("Bloqueado", body)

    def test_unlock_login_deletes_one_attempt(self):
        from axes.models import AccessAttempt

        a = AccessAttempt.objects.create(
            username="a@x.com", ip_address="1.1.1.1",
            failures_since_start=15,
            get_data="", post_data="", http_accept="", path_info="/",
        )
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("admin_unlock_login", args=[a.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(AccessAttempt.objects.filter(pk=a.pk).exists())

    def test_unlock_all_deletes_everything(self):
        from axes.models import AccessAttempt

        for i in range(3):
            AccessAttempt.objects.create(
                username=f"u{i}@x.com", ip_address=f"1.1.1.{i}",
                failures_since_start=11,
                get_data="", post_data="", http_accept="", path_info="/",
            )
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("admin_unlock_all_logins"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AccessAttempt.objects.count(), 0)

    def test_unlock_requires_staff(self):
        # Anónimo se redirige a login admin.
        from axes.models import AccessAttempt
        a = AccessAttempt.objects.create(
            username="x@x.com", ip_address="2.2.2.2",
            failures_since_start=11,
            get_data="", post_data="", http_accept="", path_info="/",
        )
        resp = self.client.post(reverse("admin_unlock_login", args=[a.pk]))
        self.assertIn(resp.status_code, (302, 403))
        # No se borró.
        self.assertTrue(AccessAttempt.objects.filter(pk=a.pk).exists())


class MPDiagnoseAdminTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="mp_admin", email="mp@x.com", password="pw12345!",
        )

    def test_page_renders_for_staff(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_mp_diagnose"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Diagn", body)  # "Diagnóstico"
        self.assertIn("Probar Mercado Pago", body)

    def test_anon_blocked(self):
        resp = self.client.get(reverse("admin_mp_diagnose"))
        self.assertIn(resp.status_code, (302, 403))

    @override_settings(MERCADOPAGO_ACCESS_TOKEN="")
    def test_post_without_token_shows_error(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("admin_mp_diagnose"), {"action": "test_preference"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Mercado Pago fall", body)
        self.assertIn("no est", body.lower())  # "no está configurado"


class UserAdminUnlockActionTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="adm_ul", email="adm_ul@x.com", password="pw12345!",
        )
        self.client.force_login(self.admin)
        self.target = User.objects.create_user(
            username="locked_user", email="locked@x.com", password="pw12345!",
        )
        from axes.models import AccessAttempt
        AccessAttempt.objects.create(
            username="locked_user", ip_address="1.1.1.1",
            failures_since_start=20, user_agent="ua",
        )
        AccessAttempt.objects.create(
            username="locked@x.com", ip_address="2.2.2.2",
            failures_since_start=20, user_agent="ua",
        )

    def test_action_clears_attempts_by_username_and_email(self):
        from axes.models import AccessAttempt

        url = reverse("admin:accounts_user_changelist")
        resp = self.client.post(url, {
            "action": "unlock_login_action",
            "_selected_action": [str(self.target.pk)],
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            AccessAttempt.objects.filter(
                username__in=["locked_user", "locked@x.com"]
            ).count(),
            0,
        )
