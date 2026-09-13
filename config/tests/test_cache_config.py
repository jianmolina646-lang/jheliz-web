from django.test import SimpleTestCase, override_settings


class CacheConfigurationTests(SimpleTestCase):
    def test_development_cache_is_available(self):
        from django.core.cache import cache

        cache.set("configuration-probe", "ok", timeout=5)
        self.assertEqual(cache.get("configuration-probe"), "ok")
