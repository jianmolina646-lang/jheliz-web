from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase

from catalog.admin import CategoryAdmin, ProductAdmin
from catalog.models import Category, Product


class MarketingAdminFieldTests(SimpleTestCase):
    def test_marketing_choices_reject_profiles(self):
        request = RequestFactory().get('/')
        request.is_marketing = True
        for model, admin_class, field_name, allowed, rejected in [
            (Category, CategoryAdmin, 'audience', 'cliente', 'distribuidor'),
            (Product, ProductAdmin, 'mode', 'completa', 'perfil'),
        ]:
            field = admin_class(model, AdminSite()).formfield_for_choice_field(
                model._meta.get_field(field_name), request,
            )
            self.assertEqual(field.clean(allowed), allowed)
            with self.assertRaises(ValidationError):
                field.clean(rejected)

    def test_other_domain_preserves_choices(self):
        request = RequestFactory().get('/')
        request.is_marketing = False
        field = CategoryAdmin(Category, AdminSite()).formfield_for_choice_field(
            Category._meta.get_field('audience'), request,
        )
        self.assertEqual(field.clean('cliente'), 'cliente')
