from django.db import DatabaseError

from products.models import Category

from .models import SiteSettings


def site_context(request):
    """Expose editable site content and footer categories to every template."""
    try:
        site_profile = SiteSettings.load()
    except DatabaseError:
        site_profile = None

    try:
        footer_categories = (
            Category.objects.filter(is_active=True, products__active=True)
            .distinct()
            .order_by("name")
        )
    except DatabaseError:
        footer_categories = []

    return {
        "site_profile": site_profile,
        "footer_categories": footer_categories,
    }


def dashboard_context(request):
    """Badge counts, notifications and follow-up reminders for the dashboard."""
    user = getattr(request, "user", None)
    if (
        not request.path.startswith("/admin-panel/")
        or not user
        or not user.is_authenticated
        or not user.is_staff
    ):
        return {}

    try:
        from django.utils import timezone

        from enquiries.models import Enquiry

        unread = user.dashboard_notifications.filter(is_read=False)
        return {
            "new_enquiry_count": Enquiry.objects.filter(status=Enquiry.STATUS_NEW).count(),
            "unread_notifications": unread.count(),
            "recent_notifications": list(unread.select_related("user")[:5]),
            "followups_due_count": Enquiry.objects.filter(
                follow_up_date__lte=timezone.localdate(),
                status__in=Enquiry.OPEN_STATUSES,
            ).count(),
        }
    except Exception:
        return {}
