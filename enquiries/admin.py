from django.contrib import admin

from .models import Enquiry


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("reference", "name", "company", "product", "status", "created_at")
    list_filter = ("status", "created_at", "product__category")
    search_fields = ("reference", "name", "company", "email", "phone", "message")
    readonly_fields = ("reference", "name", "company", "email", "phone", "product", "message", "created_at", "updated_at")
    fieldsets = (
        ("Enquirer", {"fields": ("reference", "name", "company", "email", "phone", "product", "message")}),
        ("Follow-up", {"fields": ("status", "internal_notes")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        return False
