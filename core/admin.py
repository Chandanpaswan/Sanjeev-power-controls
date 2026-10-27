from django.contrib import admin

from .models import ActivityLog, Notification, SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "company_name",
        "whatsapp_number",
        "city",
        "state",
        "country",
        "updated_at",
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "description", "user", "ip_address")
    list_filter = ("action", "created_at")
    search_fields = ("description", "target_type", "target_id", "user__username")
    readonly_fields = (
        "user", "action", "description", "target_type", "target_id",
        "ip_address", "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "level", "is_read", "created_at")
    list_filter = ("level", "is_read", "created_at")
    search_fields = ("title", "message", "user__username")
    date_hierarchy = "created_at"
