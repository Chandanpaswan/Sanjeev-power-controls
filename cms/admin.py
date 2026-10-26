from django.contrib import admin

from .models import (
    Banner,
    BlogCategory,
    BlogPost,
    FAQ,
    MediaAsset,
    MenuItem,
    Page,
    PageSection,
    RedirectRule,
    Testimonial,
)


class PageSectionInline(admin.TabularInline):
    model = PageSection
    extra = 0


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "slug", "hero_heading")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [PageSectionInline]


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("title", "file_type", "file_size", "created_at")
    list_filter = ("file_type",)
    search_fields = ("title", "alt_text", "caption", "file")


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author", "status", "published_at")
    list_filter = ("status", "category")
    search_fields = ("title", "excerpt", "content", "tags")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "company", "is_approved", "is_published", "order")
    list_filter = ("is_approved", "is_published")
    list_editable = ("order",)


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "order", "is_published")
    list_filter = ("is_published", "category")
    list_editable = ("order", "is_published")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "order")
    list_editable = ("is_active", "order")


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("label", "location", "order", "is_active")
    list_filter = ("location", "is_active")
    list_editable = ("order", "is_active")


@admin.register(RedirectRule)
class RedirectRuleAdmin(admin.ModelAdmin):
    list_display = ("old_path", "new_path", "status_code", "is_active")
    list_filter = ("is_active", "status_code")
