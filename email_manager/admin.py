from django.contrib import admin

from .models import EmailLog, EmailTemplate, NotificationRule, SMTPConfiguration


@admin.register(SMTPConfiguration)
class SMTPConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "host",
        "port",
        "sender_email",
        "is_enabled",
        "last_test_status",
        "updated_at",
    )
    readonly_fields = (
        "password_ciphertext",
        "last_test_status",
        "last_test_message",
        "last_test_at",
        "updated_by",
        "updated_at",
    )
    exclude = ("password_ciphertext",)
    fieldsets = (
        (
            "Server",
            {
                "fields": (
                    "preset",
                    "host",
                    "port",
                    "username",
                    "use_tls",
                    "use_ssl",
                    "timeout",
                    "is_enabled",
                )
            },
        ),
        (
            "Sender",
            {
                "fields": (
                    "sender_email",
                    "sender_name",
                    "reply_to",
                    "admin_notification_email",
                    "log_retention_days",
                )
            },
        ),
        (
            "Last connection test",
            {
                "fields": (
                    "last_test_status",
                    "last_test_message",
                    "last_test_at",
                )
            },
        ),
        ("Audit", {"fields": ("updated_by", "updated_at")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "audience", "is_active", "is_system", "updated_at")
    list_filter = ("audience", "is_active", "is_system")
    search_fields = ("name", "key", "subject")
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "key",
        "name",
        "audience",
        "description",
        "subject",
        "html_body",
        "text_body",
        "is_active",
        "is_system",
        "created_at",
        "updated_at",
    )


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "recipient",
        "subject",
        "status",
        "attempts",
        "event",
    )
    list_filter = ("status", "event")
    search_fields = ("recipient", "subject", "message_id", "enquiry__reference")
    readonly_fields = [field.name for field in EmailLog._meta.fields]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(NotificationRule)
class NotificationRuleAdmin(admin.ModelAdmin):
    list_display = ("event", "template", "recipient", "is_enabled", "updated_at")
    list_filter = ("is_enabled", "recipient")
    readonly_fields = ("updated_at",)
