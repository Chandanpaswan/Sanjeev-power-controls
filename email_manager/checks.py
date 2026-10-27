"""System checks for Email Manager configuration."""
from django.conf import settings
from django.core.checks import Warning, register


@register()
def email_manager_configuration(app_configs, **kwargs):
    warnings = []
    if not (getattr(settings, "EMAIL_ENCRYPTION_KEY", "") or "").strip():
        if getattr(settings, "DEBUG", False):
            warnings.append(
                Warning(
                    "EMAIL_ENCRYPTION_KEY is not set. A development-only key "
                    "derived from DJANGO_SECRET_KEY is being used for SMTP "
                    "credential encryption. Set a dedicated key before "
                    "production.",
                    id="email_manager.W001",
                )
            )
        else:
            warnings.append(
                Warning(
                    "EMAIL_ENCRYPTION_KEY is not set. SMTP passwords cannot be "
                    "saved until a dedicated encryption key is provided in the "
                    "server environment.",
                    id="email_manager.W002",
                )
            )
    return warnings
