from django.contrib import admin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "product_count", "created_at")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "featured", "active", "updated_at")
    list_filter = ("active", "featured", "category")
    search_fields = ("name", "sku", "short_description", "description")
    list_editable = ("featured", "active")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Identity", {"fields": ("name", "slug", "sku", "category")}),
        ("Public content", {"fields": ("short_description", "description", "specifications")}),
        ("Media and visibility", {"fields": ("image", "featured", "active")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
