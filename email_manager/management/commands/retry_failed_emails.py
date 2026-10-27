"""Management command: retry eligible failed email notifications."""
from django.core.management.base import BaseCommand

from email_manager.models import EmailLog
from email_manager.notifications import retry_email_log


class Command(BaseCommand):
    help = (
        "Retry failed enquiry notification emails that still have a template and "
        "related enquiry. Full bodies are not stored, so only rebuildable "
        "notifications are retried."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Maximum number of logs to process (default 25).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List eligible logs without retrying.",
        )

    def handle(self, *args, **options):
        limit = max(1, options["limit"])
        candidates = (
            EmailLog.objects.filter(
                status=EmailLog.STATUS_FAILED,
                template_key__gt="",
                enquiry__isnull=False,
            )
            .select_related("enquiry", "enquiry__product")
            .order_by("created_at")
        )
        processed = 0
        sent = 0
        failed = 0
        for email_log in candidates:
            if processed >= limit:
                break
            if not email_log.can_retry:
                continue
            processed += 1
            if options["dry_run"]:
                self.stdout.write(
                    f"Eligible: #{email_log.pk} {email_log.recipient} - "
                    f"{email_log.subject or email_log.template_key}"
                )
                continue
            result = retry_email_log(email_log)
            if result and result.is_successful:
                sent += 1
            else:
                failed += 1
        if options["dry_run"]:
            self.stdout.write(f"{processed} eligible log(s).")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Retried {processed} email(s): {sent} accepted, {failed} failed."
            )
        )
