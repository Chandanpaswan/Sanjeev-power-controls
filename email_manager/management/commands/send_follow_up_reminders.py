"""Management command: send reminders for due enquiry follow-ups.

Schedule this command (for example with cron or a platform scheduler) once the
follow-up reminder rule is enabled in the dashboard. Running it repeatedly on
the same day does not send duplicates because the email log dedupe key includes
the follow-up date.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from enquiries.models import Enquiry
from email_manager.notifications import notify_follow_up_due


class Command(BaseCommand):
    help = "Send follow-up reminders for open enquiries whose follow-up date is due."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List due enquiries without sending email.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        due = (
            Enquiry.objects.filter(
                follow_up_date__lte=today,
                status__in=Enquiry.OPEN_STATUSES,
            )
            .select_related("product", "assigned_to")
            .order_by("follow_up_date", "created_at")
        )
        sent = 0
        skipped = 0
        for enquiry in due:
            if options["dry_run"]:
                self.stdout.write(
                    f"Due: {enquiry.reference} - {enquiry.name} "
                    f"({enquiry.follow_up_date:%d %b %Y})"
                )
                continue
            result = notify_follow_up_due(enquiry)
            if result and result.is_successful:
                sent += 1
            else:
                skipped += 1
        if options["dry_run"]:
            self.stdout.write(f"{due.count()} due follow-up(s).")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Follow-up reminders: {sent} sent, {skipped} skipped or failed. "
                "Check Email Logs for details."
            )
        )
