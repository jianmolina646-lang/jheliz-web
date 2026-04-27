from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .markdown import render_markdown
from .models import BlogCategory, BlogPost


class BlogMarkdownTests(TestCase):
    def test_renders_headings_lists_bold(self):
        md = "# Título\n\nUn párrafo con **negrita** y *cursiva*.\n\n- uno\n- dos\n"
        html = render_markdown(md)
        self.assertIn("<h1>Título</h1>", html)
        self.assertIn("<strong>negrita</strong>", html)
        self.assertIn("<em>cursiva</em>", html)
        self.assertIn("<ul>", html)
        self.assertIn("<li>uno</li>", html)

    def test_escapes_html_input(self):
        html = render_markdown("<script>alert(1)</script>")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_links_open_external(self):
        html = render_markdown("[Google](https://google.com)")
        self.assertIn('href="https://google.com"', html)
        self.assertIn('target="_blank"', html)


class BlogViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cat = BlogCategory.objects.create(name="Streaming")
        self.published = BlogPost.objects.create(
            title="Cómo activar Netflix Premium",
            slug="netflix-premium",
            excerpt="Guía paso a paso",
            body="# Hola\n\nContenido.",
            status=BlogPost.Status.PUBLISHED,
            published_at=timezone.now(),
            category=self.cat,
        )
        self.draft = BlogPost.objects.create(
            title="Borrador",
            slug="borrador",
            excerpt="No visible",
            body="Privado",
            status=BlogPost.Status.DRAFT,
        )

    def test_list_only_shows_published(self):
        resp = self.client.get(reverse("blog:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Cómo activar Netflix Premium")
        self.assertNotContains(resp, "Borrador")

    def test_detail_increments_views(self):
        url = reverse("blog:detail", args=[self.published.slug])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Hola")
        self.published.refresh_from_db()
        self.assertEqual(self.published.views_count, 1)

    def test_draft_not_accessible(self):
        resp = self.client.get(reverse("blog:detail", args=[self.draft.slug]))
        self.assertEqual(resp.status_code, 404)

    def test_rss_feed(self):
        resp = self.client.get(reverse("blog:feed"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Cómo activar Netflix Premium".encode("utf-8"), resp.content)

    def test_category_filter(self):
        resp = self.client.get(reverse("blog:category", args=[self.cat.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.cat.name)
