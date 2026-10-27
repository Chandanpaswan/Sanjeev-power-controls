"""Management command: seed or refresh the Email Manager defaults."""
from django.core.management.base import BaseCommand

from email_manager.defaults import ensure_defaults


class Command(BaseCommand):
    help = (
        "Create the default email templates and notification rules. Existing "
        "templates and rules are never overwritten."
    )

    def handle(self, *args, **options):
        templates, rules = ensure_defaults()
        self.stdout.write(
            self.style.SUCCESS(
                f"Email Manager ready: {templates} template(s) and "
                f"{rules} rule(s) created."
            )
        )
        self.stdout.write(
            "Existing content was left unchanged. Review rules under "
            "Admin panel > Email Manager > Notification Rules."
        )
