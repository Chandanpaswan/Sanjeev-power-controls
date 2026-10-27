"""Management command: prune old email logs."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from email_manager.models import EmailLog, SMTPConfiguration


class Command(BaseCommand):
    help = "Delete email logs older than the configured retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=0,
            help="Override the retention period (defaults to SMTP settings).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting it.",
        )

    def handle(self, *args, **options):
        config = SMTPConfiguration.load()
        days = options["days"] or config.log_retention_days or 180
        cutoff = timezone.now() - timedelta(days=int(days))
        queryset = EmailLog.objects.filter(created_at__lt=cutoff)
        count = queryset.count()
        if options["dry_run"]:
            self.stdout.write(
                f"{count} email log(s) older than {days} day(s) would be deleted."
            )
            return
        queryset.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} email log(s) older than {days} day(s)."
            )
        )
