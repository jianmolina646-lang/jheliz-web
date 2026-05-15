from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from accounts.admin_helpers import chip
from .models import BlogCategory, BlogPost


@admin.register(BlogCategory)
class BlogCategoryAdmin(ModelAdmin):
    list_display = ("category_cell", "slug", "post_count_chip")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    @display(description="Categor\u00eda", ordering="name")
    def category_cell(self, obj):
        emoji = obj.emoji or "\U0001F4DD"
        return format_html(
            '<div class="jh-product-cell">'
            '<span class="jh-product-cell__emoji">{}</span>'
            '<div class="jh-product-cell__txt">'
            '<div class="jh-product-cell__name">{}</div>'
            '</div></div>',
            emoji, obj.name,
        )

    @display(description="Posts")
    def post_count_chip(self, obj):
        n = obj.posts.count()
        tone = "success" if n > 0 else "neutral"
        return chip(f"{n} post{'s' if n != 1 else ''}", tone=tone, icon="article")


@admin.register(BlogPost)
class BlogPostAdmin(ModelAdmin):
    list_display = (
        "post_preview", "status_chip", "category", "featured_chip", "published_at",
        "views_chip",
    )
    list_filter = ("status", "is_featured", "category")
    search_fields = ("title", "excerpt", "body", "seo_keywords")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("author", "category", "related_products")
    readonly_fields = ("views_count", "created_at", "updated_at")
    date_hierarchy = "published_at"
    fieldsets = (
        ("Contenido", {
            "fields": ("title", "slug", "category", "is_featured",
                       "excerpt", "body", "cover_image", "cover_alt"),
        }),
        ("Publicación", {
            "fields": ("status", "published_at", "author"),
        }),
        ("SEO", {
            "fields": ("seo_title", "seo_description", "seo_keywords"),
            "description": "Si dejas estos campos vacíos, se autogeneran del título y extracto.",
        }),
        ("Relacionados", {
            "fields": ("related_products",),
            "description": "Productos sugeridos al final del artículo (máx 3).",
        }),
        ("Métricas", {
            "fields": ("views_count", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    actions = ("publish_posts", "unpublish_posts")

    @display(description="Post", ordering="title")
    def post_preview(self, obj):
        if obj.cover_image:
            return format_html(
                '<div class="jh-product-cell">'
                '<img class="jh-product-cell__img" src="{}" alt="" loading="lazy" />'
                '<div class="jh-product-cell__txt">'
                '<div class="jh-product-cell__name">{}</div>'
                '<div class="jh-product-cell__sub">{}</div>'
                '</div></div>',
                obj.cover_image.url, obj.title, obj.slug,
            )
        return format_html(
            '<div class="jh-product-cell">'
            '<span class="jh-product-cell__emoji">\U0001F4F0</span>'
            '<div class="jh-product-cell__txt">'
            '<div class="jh-product-cell__name">{}</div>'
            '<div class="jh-product-cell__sub">{}</div>'
            '</div></div>',
            obj.title, obj.slug,
        )

    @display(description="Estado", ordering="status")
    def status_chip(self, obj):
        tone = {
            BlogPost.Status.PUBLISHED: "success",
            BlogPost.Status.DRAFT: "warning",
        }.get(obj.status, "neutral")
        icon = "check_circle" if obj.status == BlogPost.Status.PUBLISHED else "edit_note"
        return chip(obj.get_status_display(), tone=tone, icon=icon)

    @display(description="Destacado", ordering="is_featured")
    def featured_chip(self, obj):
        if obj.is_featured:
            return chip("Destacado", tone="pink", icon="star")
        return chip("\u2014", tone="neutral")

    @display(description="Vistas", ordering="views_count")
    def views_chip(self, obj):
        v = obj.views_count or 0
        if v == 0:
            return chip("0", tone="neutral", icon="visibility_off")
        tone = "success" if v >= 100 else "info"
        return chip(f"{v:,}", tone=tone, icon="visibility")

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Publicar")
    def publish_posts(self, request, queryset):
        n = 0
        for post in queryset:
            post.status = BlogPost.Status.PUBLISHED
            post.save()
            n += 1
        self.message_user(request, f"{n} post(s) publicados.")

    @admin.action(description="Mover a borrador")
    def unpublish_posts(self, request, queryset):
        updated = queryset.update(status=BlogPost.Status.DRAFT)
        self.message_user(request, f"{updated} post(s) movidos a borrador.")
