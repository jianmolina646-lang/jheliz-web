from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class BlogCategory(models.Model):
    name = models.CharField("Nombre", max_length=80, unique=True)
    slug = models.SlugField(unique=True, max_length=80)
    description = models.CharField("Descripción", max_length=160, blank=True)
    emoji = models.CharField("Emoji", max_length=4, blank=True, default="📝")

    class Meta:
        verbose_name = "Categoría de blog"
        verbose_name_plural = "Categorías de blog"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:80]
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog:category", args=[self.slug])


class BlogPost(models.Model):
    """Artículo del blog. Render con Markdown muy ligero (encabezados + listas + énfasis)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PUBLISHED = "published", "Publicado"

    title = models.CharField("Título", max_length=200)
    slug = models.SlugField("Slug", unique=True, max_length=220)
    category = models.ForeignKey(
        BlogCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="posts",
    )
    excerpt = models.CharField(
        "Extracto", max_length=300,
        help_text="Resumen corto que aparece en el listado y en la meta description.",
    )
    body = models.TextField(
        "Contenido (Markdown)",
        help_text="Acepta Markdown: # Título, ## Subtítulo, **negrita**, *cursiva*, listas con - o 1.",
    )
    cover_image = models.ImageField(
        "Imagen de portada", upload_to="blog/covers/", blank=True,
        help_text="Recomendado 1200x630 px (Open Graph). Aparece en la cabecera del post y en redes sociales.",
    )
    cover_alt = models.CharField("Texto alternativo", max_length=160, blank=True)
    seo_title = models.CharField(
        "Título SEO", max_length=70, blank=True,
        help_text="Si está vacío, usa el título normal. Máx 60-70 caracteres para Google.",
    )
    seo_description = models.CharField(
        "Meta description", max_length=160, blank=True,
        help_text="Si está vacío, usa el extracto. Máx 155-160 caracteres.",
    )
    seo_keywords = models.CharField("Keywords (separadas por coma)", max_length=300, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_featured = models.BooleanField(
        "Destacado", default=False,
        help_text="Si está marcado, aparece arriba del listado de blog.",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blog_posts",
    )
    related_products = models.ManyToManyField(
        "catalog.Product", blank=True, related_name="blog_posts",
        help_text="Se mostrarán como CTA al final del artículo.",
    )
    published_at = models.DateTimeField("Publicado el", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    views_count = models.PositiveIntegerField("Visitas", default=0, editable=False)

    class Meta:
        verbose_name = "Post de blog"
        verbose_name_plural = "Posts de blog"
        ordering = ("-published_at", "-created_at")
        indexes = [
            models.Index(fields=["status", "-published_at"], name="blog_status_pub_idx"),
            models.Index(fields=["slug"], name="blog_slug_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:220]
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog:detail", args=[self.slug])

    @property
    def effective_seo_title(self) -> str:
        return self.seo_title or self.title

    @property
    def effective_seo_description(self) -> str:
        return self.seo_description or self.excerpt

    def increment_views(self) -> None:
        type(self).objects.filter(pk=self.pk).update(
            views_count=models.F("views_count") + 1,
        )

    @property
    def read_time_minutes(self) -> int:
        """Tiempo estimado de lectura en minutos (~200 palabras/min)."""
        words = len((self.body or "").split())
        return max(1, round(words / 200))
