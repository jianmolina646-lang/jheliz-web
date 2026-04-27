from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import BlogCategory, BlogPost


@admin.register(BlogCategory)
class BlogCategoryAdmin(ModelAdmin):
    list_display = ("name", "slug", "emoji", "post_count")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    @display(description="Posts")
    def post_count(self, obj):
        return obj.posts.count()


@admin.register(BlogPost)
class BlogPostAdmin(ModelAdmin):
    list_display = (
        "title", "status", "category", "is_featured", "published_at",
        "views_count",
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
