"""Notification event integration for enquiries, staff actions and passwords.

The public enquiry flow must never fail because of email. Every function in
this module catches its own errors and returns a log (or ``None``) instead of
raising.
"""
from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from core.models import SiteSettings

from .mailer import send_template_email
from .models import (
    EmailLog,
    EmailTemplate,
    NotificationRule,
    SMTPConfiguration,
)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------
def _absolute_url(path: str, request=None) -> str:
    if request is not None:
        try:
            return request.build_absolute_uri(path)
        except Exception:
            pass
    base = (getattr(settings, "SITE_BASE_URL", "") or "").strip()
    if base:
        return urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    hosts = getattr(settings, "ALLOWED_HOSTS", []) or []
    host = next(
        (
            item
            for item in hosts
            if item and item not in {"*", "[::1]"} and not item.startswith(".")
        ),
        "localhost",
    )
    scheme = "http" if getattr(settings, "DEBUG", False) else "https"
    return f"{scheme}://{host}{path}"


def _site_details():
    try:
        site = SiteSettings.load()
        return {
            "site_name": site.company_name or "Sanjeev Power Controls",
            "contact_email": site.contact_email
            or getattr(settings, "DEFAULT_FROM_EMAIL", "")
            or "no-reply@example.com",
        }
    except Exception:
        return {
            "site_name": "Sanjeev Power Controls",
            "contact_email": getattr(settings, "DEFAULT_FROM_EMAIL", "")
            or "no-reply@example.com",
        }


def admin_recipient(config: SMTPConfiguration | None = None) -> str:
    """Resolve the internal notification address without exposing customer data."""
    config = config or SMTPConfiguration.load()
    site = _site_details()
    return (
        (config.admin_notification_email or "").strip()
        or (site.get("contact_email") or "").strip()
        or (getattr(settings, "ADMIN_NOTIFICATION_EMAIL", "") or "").strip()
    )


def enquiry_context(enquiry, request=None, extra: dict | None = None) -> dict:
    site = _site_details()
    config = SMTPConfiguration.load()
    assigned = ""
    if getattr(enquiry, "assigned_to", None):
        assigned = (
            enquiry.assigned_to.get_full_name()
            or enquiry.assigned_to.username
        )
    protocol = "https" if request is not None and request.is_secure() else "http"
    domain = request.get_host() if request is not None else ""
    context = {
        "customer_name": enquiry.name,
        "customer_email": enquiry.email,
        "customer_phone": enquiry.phone,
        "company_name": enquiry.company or "Not supplied",
        "product_name": enquiry.product_label,
        "enquiry_id": enquiry.reference,
        "enquiry_message": enquiry.message,
        "enquiry_status": enquiry.get_status_display(),
        "enquiry_url": _absolute_url(
            reverse("dashboard:enquiry_detail", args=[enquiry.pk]), request
        ),
        "old_status": "",
        "new_status": enquiry.get_status_display(),
        "assigned_to": assigned or "Unassigned",
        "site_name": site["site_name"],
        "contact_email": site["contact_email"],
        "admin_email": admin_recipient(config),
        "current_year": str(timezone.now().year),
        "protocol": protocol,
        "domain": domain,
        "reset_url": "",
    }
    if extra:
        context.update(
            {key: value for key, value in extra.items() if value is not None}
        )
    return context


# ---------------------------------------------------------------------------
# Recipient resolution
# ---------------------------------------------------------------------------
def _recipient_for(rule, enquiry, config, event_user=None) -> tuple[str, str]:
    if rule.recipient == NotificationRule.RECIPIENT_CUSTOMER:
        if not enquiry:
            return "", ""
        return enquiry.email, enquiry.name
    if rule.recipient == NotificationRule.RECIPIENT_ADMIN:
        return admin_recipient(config), ""
    if rule.recipient == NotificationRule.RECIPIENT_ASSIGNED_STAFF:
        user = getattr(enquiry, "assigned_to", None) if enquiry else None
        if not user or not user.is_active or not user.is_staff:
            return "", ""
        return user.email, user.get_full_name() or user.username
    if rule.recipient == NotificationRule.RECIPIENT_EVENT_USER:
        user = event_user
        if not user or not user.is_active:
            return "", ""
        return user.email, user.get_full_name() or user.username
    return "", ""


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
def dispatch_event(
    event: str,
    *,
    enquiry=None,
    request=None,
    event_user=None,
    triggered_by=None,
    extra_context: dict | None = None,
    dedupe_suffix: str = "",
    recipient_override: str = "",
) -> EmailLog | None:
    """Send the template configured for ``event``, if the rule is enabled."""
    try:
        rule = NotificationRule.for_event(event)
        if rule is None:
            return None
        config = SMTPConfiguration.load()
        if recipient_override:
            recipient, recipient_name = recipient_override, ""
        else:
            recipient, recipient_name = _recipient_for(
                rule, enquiry, config, event_user=event_user
            )
        if not recipient:
            return None

        context = (
            enquiry_context(enquiry, request, extra_context)
            if enquiry is not None
            else {
                **_site_details(),
                "admin_email": admin_recipient(config),
                "current_year": str(timezone.now().year),
                "protocol": "https"
                if request is not None and request.is_secure()
                else "http",
                "domain": request.get_host() if request is not None else "",
                "reset_url": "",
                **(extra_context or {}),
            }
        )

        dedupe_key = None
        if enquiry is not None:
            parts = [
                event,
                str(enquiry.pk),
                recipient,
                dedupe_suffix or "",
            ]
            dedupe_key = ":".join(part for part in parts if part)[:255]

        return send_template_email(
            template=rule.template,
            event=event,
            recipient=recipient,
            recipient_name=recipient_name,
            context=context,
            enquiry=enquiry,
            triggered_by=triggered_by,
            dedupe_key=dedupe_key,
        )
    except Exception:
        # Email is a side effect; never break the business transaction.
        return None


# ---------------------------------------------------------------------------
# Business events
# ---------------------------------------------------------------------------
def notify_new_enquiry(enquiry, request=None) -> list[EmailLog]:
    """Acknowledge the customer and notify the administrator.

    The enquiry has already been saved by the caller. Any failure here leaves
    the enquiry intact and is recorded in the email log where possible.
    """
    logs: list[EmailLog] = []
    if enquiry is None:
        return logs

    try:
        ack = dispatch_event(
            NotificationRule.EVENT_NEW_ENQUIRY_CUSTOMER,
            enquiry=enquiry,
            request=request,
            dedupe_suffix="ack",
        )
        if ack:
            logs.append(ack)
    except Exception:
        pass

    try:
        event = (
            NotificationRule.EVENT_PRODUCT_ENQUIRY_ADMIN
            if enquiry.product_id
            else NotificationRule.EVENT_NEW_ENQUIRY_ADMIN
        )
        admin_log = dispatch_event(
            event,
            enquiry=enquiry,
            request=request,
            dedupe_suffix="admin",
        )
        if admin_log:
            logs.append(admin_log)
    except Exception:
        pass

    # Optional short alert. Disabled by default; only one admin email by default.
    try:
        alert = dispatch_event(
            NotificationRule.EVENT_ADMIN_NEW_LEAD,
            enquiry=enquiry,
            request=request,
            dedupe_suffix="alert",
        )
        if alert:
            logs.append(alert)
    except Exception:
        pass

    return logs


def notify_status_change(
    enquiry, old_status: str, new_status: str, actor=None
) -> EmailLog | None:
    if enquiry is None or old_status == new_status:
        return None
    labels = dict(enquiry.STATUS_CHOICES)
    return dispatch_event(
        NotificationRule.EVENT_STATUS_CHANGED,
        enquiry=enquiry,
        triggered_by=actor,
        extra_context={
            "old_status": labels.get(old_status, old_status),
            "new_status": labels.get(new_status, new_status),
        },
        dedupe_suffix=f"{new_status}:{int(enquiry.updated_at.timestamp())}",
    )


def notify_assignment(enquiry, actor=None) -> EmailLog | None:
    if enquiry is None or not enquiry.assigned_to_id:
        return None
    user = enquiry.assigned_to
    if not user or not user.is_active or not user.is_staff:
        return None
    return dispatch_event(
        NotificationRule.EVENT_LEAD_ASSIGNED,
        enquiry=enquiry,
        triggered_by=actor,
        extra_context={
            "assigned_to": user.get_full_name() or user.username,
        },
        dedupe_suffix=f"assigned:{user.pk}",
    )


def notify_follow_up_due(enquiry, actor=None) -> EmailLog | None:
    if enquiry is None or not enquiry.follow_up_date:
        return None
    return dispatch_event(
        NotificationRule.EVENT_FOLLOW_UP_DUE,
        enquiry=enquiry,
        triggered_by=actor,
        dedupe_suffix=f"due:{enquiry.follow_up_date.isoformat()}",
    )


def send_password_reset_email(user, reset_url: str, request=None):
    """Send the dashboard password reset link through the Email Manager.

    Returns ``None`` when no enabled rule/template exists so the caller can fall
    back to Django's default reset email. Returns an ``EmailLog`` when the
    Email Manager handled (or deliberately skipped) the message.
    """
    if user is None or not user.email:
        return None
    try:
        rule = NotificationRule.for_event(NotificationRule.EVENT_PASSWORD_RESET)
        if rule is None:
            return None
        config = SMTPConfiguration.load()
        site = _site_details()
        context = {
            **site,
            "customer_name": user.get_full_name() or user.username,
            "reset_url": reset_url,
            "admin_email": admin_recipient(config),
            "current_year": str(timezone.now().year),
            "protocol": "https"
            if request is not None and request.is_secure()
            else "http",
            "domain": request.get_host() if request is not None else "",
        }
        return send_template_email(
            template=rule.template,
            event=NotificationRule.EVENT_PASSWORD_RESET,
            recipient=user.email,
            recipient_name=user.get_full_name() or user.username,
            context=context,
            triggered_by=None,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
def retry_email_log(log: EmailLog, actor=None) -> EmailLog | None:
    """Re-render and resend a failed enquiry notification.

    Only logs that carry a template key and a related enquiry are eligible,
    because full message bodies are intentionally not stored.
    """
    if log is None or not log.can_retry or not log.enquiry_id:
        return None
    template = EmailTemplate.objects.filter(key=log.template_key).first()
    if template is None:
        return None

    enquiry = log.enquiry
    context = enquiry_context(enquiry)
    if log.event == NotificationRule.EVENT_STATUS_CHANGED:
        context["new_status"] = enquiry.get_status_display()
    if log.event == NotificationRule.EVENT_LEAD_ASSIGNED:
        assigned = enquiry.assigned_to
        context["assigned_to"] = (
            (assigned.get_full_name() or assigned.username)
            if assigned
            else "Unassigned"
        )

    return send_template_email(
        template=template,
        event=log.event,
        recipient=log.recipient,
        recipient_name=log.recipient_name,
        context=context,
        enquiry=enquiry,
        triggered_by=actor,
        existing_log=log,
    )
