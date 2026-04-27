from decimal import Decimal

from django.core.management.base import BaseCommand

from catalog.models import Category, Plan, Product, ProductMode, StockItem


class Command(BaseCommand):
    help = "Crea categor\u00edas y productos de ejemplo para Jheliz."

    def handle(self, *args, **options):
        streaming, _ = Category.objects.get_or_create(
            slug="streaming",
            defaults={
                "name": "Streaming",
                "emoji": "\U0001f3ac",
                "order": 1,
                "audience": Category.Audience.AMBOS,
                "description": "Cuentas de streaming por perfil o completas.",
            },
        )
        licencias, _ = Category.objects.get_or_create(
            slug="licencias",
            defaults={
                "name": "Licencias",
                "emoji": "\U0001f5a5\ufe0f",
                "order": 2,
                "audience": Category.Audience.AMBOS,
                "description": "Licencias originales de software.",
            },
        )

        catalog_data = [
            {
                "category": streaming, "mode": ProductMode.PERFIL, "icon": "\U0001f3ac",
                "name": "Netflix Premium \u2014 1 perfil",
                "short": "Perfil dedicado en cuenta premium 4K.",
                "desc": "Perfil con PIN. No cambies la foto ni el nombre. Compartido con otros clientes respetando las reglas de la cuenta.",
                "featured": True, "sold_badge": "+10K",
                "plans": [
                    ("1 mes", 30, "15.00", "11.00"),
                    ("3 meses", 90, "40.00", "30.00"),
                    ("6 meses", 180, "75.00", "60.00"),
                ],
            },
            {
                "category": streaming, "mode": ProductMode.PERFIL, "icon": "\U0001f3ed",
                "name": "Disney+ \u2014 1 perfil",
                "short": "Perfil dedicado en Disney+ premium.",
                "desc": "Incluye catalog completo Disney, Star+, Marvel y National Geographic.",
                "featured": True, "sold_badge": "+5K",
                "plans": [
                    ("1 mes", 30, "10.00", "7.00"),
                    ("3 meses", 90, "25.00", "18.00"),
                ],
            },
            {
                "category": streaming, "mode": ProductMode.PERFIL, "icon": "\U0001f4e6",
                "name": "Prime Video \u2014 1 perfil",
                "short": "Perfil dedicado en Amazon Prime Video.",
                "desc": "Acceso al cat\u00e1logo de Prime Video.",
                "featured": False, "sold_badge": "+2K",
                "plans": [
                    ("1 mes", 30, "8.00", "6.00"),
                    ("3 meses", 90, "21.00", "16.00"),
                ],
            },
            {
                "category": streaming, "mode": ProductMode.COMPLETA, "icon": "\U0001f451",
                "name": "Netflix Premium \u2014 Cuenta completa (distribuidor)",
                "short": "Cuenta completa Netflix Premium para distribuidor.",
                "desc": "Cuenta completa con 4 pantallas, lista para revender.",
                "featured": False, "sold_badge": "+500",
                "plans": [
                    ("1 mes", 30, "55.00", "45.00"),
                ],
            },
            {
                "category": licencias, "mode": ProductMode.LICENCIA, "icon": "\U0001f5a5\ufe0f",
                "name": "Windows 11 Pro \u2014 Licencia",
                "short": "Licencia Windows 11 Pro original de por vida.",
                "desc": "Clave de activaci\u00f3n digital para 1 PC. V\u00e1lida de por vida.",
                "featured": True, "sold_badge": "+1K",
                "plans": [
                    ("De por vida", 0, "25.00", "18.00"),
                ],
            },
            {
                "category": licencias, "mode": ProductMode.LICENCIA, "icon": "\U0001f4c4",
                "name": "Microsoft Office 2021 \u2014 Licencia",
                "short": "Licencia Office 2021 para 1 PC.",
                "desc": "Clave digital, Word, Excel, PowerPoint, Outlook.",
                "featured": True, "sold_badge": "+800",
                "plans": [
                    ("De por vida", 0, "20.00", "14.00"),
                ],
            },
            {
                "category": licencias, "mode": ProductMode.LICENCIA, "icon": "\U0001f3a8",
                "name": "Adobe Photoshop \u2014 1 mes",
                "short": "Acceso mensual a Photoshop original.",
                "desc": "Plan oficial de Adobe con facturaci\u00f3n mensual.",
                "featured": False, "sold_badge": "+300",
                "plans": [
                    ("1 mes", 30, "30.00", "22.00"),
                    ("3 meses", 90, "80.00", "60.00"),
                ],
            },
        ]

        for data in catalog_data:
            requires_profile = data["mode"] != ProductMode.LICENCIA
            product, created = Product.objects.get_or_create(
                name=data["name"],
                defaults={
                    "category": data["category"],
                    "mode": data["mode"],
                    "icon": data["icon"],
                    "short_description": data["short"],
                    "description": data["desc"],
                    "is_featured": data["featured"],
                    "sold_badge": data["sold_badge"],
                    "requires_customer_profile_data": requires_profile,
                    "delivery_is_instant": False,
                },
            )
            for idx, (name, days, pc, pd) in enumerate(data["plans"]):
                Plan.objects.get_or_create(
                    product=product, name=name,
                    defaults={
                        "duration_days": days,
                        "price_customer": Decimal(pc),
                        "price_distributor": Decimal(pd),
                        "order": idx,
                    },
                )
            # Seed 3 stock items per product so stock shows up
            if product.stock_items.count() == 0:
                for i in range(3):
                    StockItem.objects.create(
                        product=product,
                        credentials=(
                            f"Correo: demo{i}@jheliz.pe\n"
                            f"Contrase\u00f1a: demo-pass-{i}\n"
                            f"Perfil: Perfil {i + 1}\n"
                            f"PIN: {1000 + i}"
                        ),
                        label=f"demo-{i}",
                    )

        self.stdout.write(self.style.SUCCESS("Cat\u00e1logo sembrado correctamente."))
