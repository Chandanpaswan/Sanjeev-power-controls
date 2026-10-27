"""Signal handlers for Email Manager."""
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def seed_email_defaults(sender, **kwargs):
    """Create the default templates and notification rules after migrations."""
    if getattr(sender, "name", "") != "email_manager":
        return
    try:
        from .defaults import ensure_defaults

        created_templates, created_rules = ensure_defaults()
    except Exception:
        # A failed seed must not prevent migrations from completing. The
        # seed_email_manager command can be run manually afterwards.
        return
    verbosity = kwargs.get("verbosity", 0)
    if verbosity >= 1 and (created_templates or created_rules):
        stdout = kwargs.get("stdout")
        if stdout:
            stdout.write(
                f"  email manager: seeded {created_templates} template(s) and "
                f"{created_rules} notification rule(s)"
            )
