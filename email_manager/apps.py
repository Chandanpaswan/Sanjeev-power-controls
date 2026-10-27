from django.apps import AppConfig


class EmailManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "email_manager"
    verbose_name = "Email manager"

    def ready(self):
        from . import checks  # noqa: F401  (registers system checks)
        from . import signals  # noqa: F401  (registers post_migrate seeding)
