"""Permission-protected dashboard views for the Email Manager."""
from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core.models import ActivityLog
from core.utils import log_activity

from . import mailer
from .defaults import sample_context
from .forms import (
    EmailTemplateForm,
    NotificationRuleForm,
    SMTPConfigurationForm,
    TemplateTestForm,
    TestEmailForm,
)
from .models import EmailLog, EmailTemplate, NotificationRule, SMTPConfiguration
from .notifications import retry_email_log
from .permissions import (
    can_manage_smtp,
    email_manager_access,
    smtp_admin_required,
)
from .templating import (
    APPROVED_PLACEHOLDERS,
    TemplateValidationError,
    render_email_template,
)


def _tabs_context(active: str) -> dict:
    return {"active_tab": active}


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
@email_manager_access(
    "email_manager.view_emaillog",
    "email_manager.view_emailtemplate",
    "email_manager.manage_smtp",
)
def overview(request):
    logs = EmailLog.objects.all()
    successful_statuses = [
        EmailLog.STATUS_SENT,
        EmailLog.STATUS_DELIVERY_CONFIRMED,
    ]
    since = timezone.now() - timedelta(hours=24)

    total = logs.count()
    accepted = logs.filter(status__in=successful_statuses).count()
    failed = logs.filter(status=EmailLog.STATUS_FAILED).count()
    queued = logs.filter(status=EmailLog.STATUS_QUEUED).count()
    skipped = logs.filter(status=EmailLog.STATUS_SKIPPED).count()
    confirmed = logs.filter(
        status=EmailLog.STATUS_DELIVERY_CONFIRMED
    ).count()
    last_success = (
        logs.filter(status__in=successful_statuses, sent_at__isnull=False)
        .order_by("-sent_at")
        .first()
    )
    last_failure = (
        logs.filter(status=EmailLog.STATUS_FAILED)
        .order_by("-created_at")
        .first()
    )
    last_24h = logs.filter(created_at__gte=since).count()
    success_rate = round(accepted / total * 100, 1) if total else 0

    config = SMTPConfiguration.load()
    recent_logs = (
        logs.select_related("enquiry").order_by("-created_at")[:8]
    )
    template_count = EmailTemplate.objects.count()
    active_template_count = EmailTemplate.objects.filter(is_active=True).count()
    enabled_rule_count = NotificationRule.objects.filter(
        is_enabled=True
    ).count()
    rule_count = NotificationRule.objects.count()

    return render(
        request,
        "dashboard/email_manager/overview.html",
        {
            **_tabs_context("overview"),
            "config": config,
            "smtp_status": config.connection_status,
            "stats": {
                "total": total,
                "accepted": accepted,
                "failed": failed,
                "queued": queued,
                "skipped": skipped,
                "confirmed": confirmed,
                "last_24h": last_24h,
                "success_rate": success_rate,
            },
            "last_success": last_success,
            "last_failure": last_failure,
            "recent_logs": recent_logs,
            "template_count": template_count,
            "active_template_count": active_template_count,
            "rule_count": rule_count,
            "enabled_rule_count": enabled_rule_count,
            "can_manage_smtp": can_manage_smtp(request.user),
        },
    )


# ---------------------------------------------------------------------------
# SMTP settings and tests
# ---------------------------------------------------------------------------
@smtp_admin_required
def smtp_settings(request):
    config = SMTPConfiguration.load()
    form = SMTPConfigurationForm(
        request.POST if request.method == "POST" else None,
        instance=config,
        user=request.user,
    )
    if request.method == "POST":
        if form.is_valid():
            config = form.save()
            log_activity(
                request,
                ActivityLog.ACTION_UPDATE,
                "SMTP settings updated"
                + (" (outgoing email enabled)" if config.is_enabled else ""),
                target_type="email_manager.smtpconfiguration",
                target_id=config.pk,
            )
            messages.success(
                request,
                "SMTP settings saved. Run a connection test to confirm the "
                "credentials before relying on automatic notifications.",
            )
            return redirect("dashboard:email_smtp_settings")
        messages.error(request, "Please correct the highlighted settings.")

    return render(
        request,
        "dashboard/email_manager/smtp_settings.html",
        {
            **_tabs_context("smtp"),
            "config": config,
            "form": form,
            "smtp_status": config.connection_status,
            "can_manage_smtp": True,
        },
    )


@smtp_admin_required
@require_POST
def smtp_test_connection(request):
    config = SMTPConfiguration.load()
    result = mailer.test_connection(config)
    log_activity(
        request,
        ActivityLog.ACTION_UPDATE,
        "SMTP connection test "
        + ("succeeded" if result["ok"] else "failed"),
        target_type="email_manager.smtpconfiguration",
        target_id=config.pk,
    )
    if result["ok"]:
        messages.success(request, result["message"])
    else:
        messages.error(request, result["message"])
    return redirect("dashboard:email_smtp_settings")


@email_manager_access("email_manager.manage_smtp")
def test_email(request):
    form = TestEmailForm(
        request.POST if request.method == "POST" else None,
        initial={"recipient": request.user.email},
    )
    if request.method == "POST" and form.is_valid():
        recipient = form.cleaned_data["recipient"]
        email_log = mailer.send_test_email(recipient, actor=request.user)
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Test email to {recipient} finished with status "
            f"{email_log.get_status_display().lower()}",
            target_type="email_manager.emaillog",
            target_id=email_log.pk,
        )
        if email_log.is_successful:
            messages.success(
                request,
                "Test email accepted by the email backend. Check the recipient "
                "inbox; acceptance does not guarantee inbox delivery.",
            )
        elif email_log.status == EmailLog.STATUS_SKIPPED:
            messages.warning(
                request,
                f"Test email was not sent: {email_log.error_summary}",
            )
        else:
            messages.error(
                request,
                f"Test email failed: {email_log.error_summary}",
            )
        return redirect("dashboard:email_test")

    config = SMTPConfiguration.load()
    recent_tests = EmailLog.objects.filter(event="test_email")[:10]
    return render(
        request,
        "dashboard/email_manager/test_email.html",
        {
            **_tabs_context("test"),
            "form": form,
            "config": config,
            "smtp_status": config.connection_status,
            "recent_tests": recent_tests,
        },
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
@email_manager_access("email_manager.view_emailtemplate")
def template_list(request):
    templates = EmailTemplate.objects.annotate(rule_count=Count("rules"))
    query = (request.GET.get("q") or "").strip()
    audience = (request.GET.get("audience") or "").strip()
    state = (request.GET.get("state") or "").strip()

    if query:
        templates = templates.filter(
            Q(name__icontains=query)
            | Q(key__icontains=query)
            | Q(subject__icontains=query)
        )
    if audience:
        templates = templates.filter(audience=audience)
    if state == "active":
        templates = templates.filter(is_active=True)
    elif state == "inactive":
        templates = templates.filter(is_active=False)

    templates = templates.order_by("name")
    total_count = templates.count()

    return render(
        request,
        "dashboard/email_manager/templates/list.html",
        {
            **_tabs_context("templates"),
            "templates": templates,
            "total_count": total_count,
            "all_count": EmailTemplate.objects.count(),
            "query": query,
            "audience": audience,
            "state": state,
            "audience_choices": EmailTemplate.AUDIENCE_CHOICES,
        },
    )


@email_manager_access("email_manager.add_emailtemplate")
def template_create(request):
    form = EmailTemplateForm(
        request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        template = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Email template created: {template.name}",
            target=template,
        )
        messages.success(request, "Email template created.")
        return redirect("dashboard:email_template_list")

    return render(
        request,
        "dashboard/email_manager/templates/form.html",
        {
            **_tabs_context("templates"),
            "form": form,
            "template": None,
            "placeholders": APPROVED_PLACEHOLDERS,
            "title": "New email template",
            "submit_label": "Create template",
        },
    )


@email_manager_access("email_manager.change_emailtemplate")
def template_edit(request, pk):
    template = get_object_or_404(EmailTemplate, pk=pk)
    form = EmailTemplateForm(
        request.POST if request.method == "POST" else None,
        instance=template,
    )
    if request.method == "POST" and form.is_valid():
        template = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Email template updated: {template.name}",
            target=template,
        )
        messages.success(request, "Email template saved.")
        return redirect("dashboard:email_template_list")

    return render(
        request,
        "dashboard/email_manager/templates/form.html",
        {
            **_tabs_context("templates"),
            "form": form,
            "template": template,
            "placeholders": APPROVED_PLACEHOLDERS,
            "title": f"Edit {template.name}",
            "submit_label": "Save template",
        },
    )


@email_manager_access("email_manager.view_emailtemplate")
def template_preview(request, pk):
    template = get_object_or_404(EmailTemplate, pk=pk)
    context = sample_context()
    rendered = None
    preview_error = ""
    try:
        rendered = render_email_template(
            template.subject,
            template.html_body,
            template.text_body,
            context,
        )
    except TemplateValidationError as exc:
        preview_error = str(exc)

    return render(
        request,
        "dashboard/email_manager/templates/preview.html",
        {
            **_tabs_context("templates"),
            "template": template,
            "preview_subject": rendered.subject if rendered else "",
            "preview_html": rendered.html_body if rendered else "",
            "preview_text": rendered.text_body if rendered else "",
            "preview_error": preview_error,
            "test_form": TemplateTestForm(
                initial={"recipient": request.user.email}
            ),
        },
    )


@email_manager_access("email_manager.change_emailtemplate")
@require_POST
def template_toggle(request, pk):
    template = get_object_or_404(EmailTemplate, pk=pk)
    template.is_active = not template.is_active
    template.save(update_fields=["is_active", "updated_at"])
    log_activity(
        request,
        ActivityLog.ACTION_UPDATE,
        f"Email template {'activated' if template.is_active else 'deactivated'}: "
        f"{template.name}",
        target=template,
    )
    messages.success(
        request,
        f"“{template.name}” is now "
        f"{'active' if template.is_active else 'inactive'}.",
    )
    return redirect("dashboard:email_template_list")


@email_manager_access("email_manager.delete_emailtemplate")
def template_delete(request, pk):
    template = get_object_or_404(EmailTemplate, pk=pk)
    if template.is_system:
        messages.error(
            request,
            "System templates cannot be deleted. Deactivate the template "
            "instead, or edit its content.",
        )
        return redirect("dashboard:email_template_list")

    if request.method == "POST":
        name = template.name
        template_pk = template.pk
        try:
            template.delete()
        except ProtectedError:
            messages.error(
                request,
                "This template is used by a notification rule. Point the rule "
                "at another template before deleting it.",
            )
            return redirect("dashboard:email_template_list")
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Email template deleted: {name}",
            target_type="email_manager.emailtemplate",
            target_id=template_pk,
        )
        messages.success(request, f"“{name}” deleted.")
        return redirect("dashboard:email_template_list")

    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete email template",
            "object_label": template.name,
            "object_type": "email template",
            "warning": (
                "This permanently removes the template. Notification rules "
                "that still reference it must be changed first."
            ),
            "cancel_url": reverse("dashboard:email_template_list"),
        },
    )


@email_manager_access("email_manager.change_emailtemplate")
@require_POST
def template_test(request, pk):
    template = get_object_or_404(EmailTemplate, pk=pk)
    form = TemplateTestForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid recipient email address.")
        return redirect("dashboard:email_template_preview", pk=template.pk)

    recipient = form.cleaned_data["recipient"]
    email_log = mailer.send_template_email(
        template=template,
        event="template_test",
        recipient=recipient,
        recipient_name="Template preview",
        context=sample_context(),
        triggered_by=request.user,
        allow_when_disabled=True,
    )
    log_activity(
        request,
        ActivityLog.ACTION_UPDATE,
        f"Template test for “{template.name}” finished with status "
        f"{email_log.get_status_display().lower()}",
        target=template,
    )
    if email_log.is_successful:
        messages.success(
            request,
            f"Preview of “{template.name}” accepted by the email backend for "
            f"{recipient}.",
        )
    elif email_log.status == EmailLog.STATUS_SKIPPED:
        messages.warning(
            request, f"Preview not sent: {email_log.error_summary}"
        )
    else:
        messages.error(
            request, f"Preview failed: {email_log.error_summary}"
        )
    return redirect("dashboard:email_template_preview", pk=template.pk)


# ---------------------------------------------------------------------------
# Email logs
# ---------------------------------------------------------------------------
@email_manager_access("email_manager.view_emaillog")
def log_list(request):
    logs = EmailLog.objects.select_related("enquiry")
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    event = (request.GET.get("event") or "").strip()
    template_key = (request.GET.get("template") or "").strip()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()

    if query:
        logs = logs.filter(
            Q(recipient__icontains=query)
            | Q(subject__icontains=query)
            | Q(recipient_name__icontains=query)
            | Q(enquiry__reference__icontains=query)
        )
    if status:
        logs = logs.filter(status=status)
    if event:
        logs = logs.filter(event=event)
    if template_key:
        logs = logs.filter(template_key=template_key)
    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)

    paginator = Paginator(logs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(
        request,
        "dashboard/email_manager/logs/list.html",
        {
            **_tabs_context("logs"),
            "page_obj": page_obj,
            "logs": page_obj.object_list,
            "total_count": paginator.count,
            "all_count": EmailLog.objects.count(),
            "query": query,
            "status": status,
            "event": event,
            "template_key": template_key,
            "date_from": date_from_raw,
            "date_to": date_to_raw,
            "status_choices": EmailLog.STATUS_CHOICES,
            "event_choices": NotificationRule.EVENT_CHOICES,
            "template_choices": EmailTemplate.objects.order_by("name").values_list(
                "key", "name"
            ),
            "querystring": params.urlencode(),
            "retention_days": SMTPConfiguration.load().log_retention_days,
            "can_prune": request.user.has_perm("email_manager.delete_emaillog"),
        },
    )


@email_manager_access("email_manager.view_emaillog")
def log_detail(request, pk):
    email_log = get_object_or_404(
        EmailLog.objects.select_related("enquiry", "triggered_by"), pk=pk
    )
    return render(
        request,
        "dashboard/email_manager/logs/detail.html",
        {
            **_tabs_context("logs"),
            "email_log": email_log,
            "can_retry": email_log.can_retry
            and request.user.has_perm("email_manager.change_emaillog"),
            "can_view_enquiry": request.user.has_perm(
                "enquiries.view_enquiry"
            ),
        },
    )


@email_manager_access("email_manager.change_emaillog")
@require_POST
def log_retry(request, pk):
    email_log = get_object_or_404(EmailLog, pk=pk)
    if not email_log.can_retry:
        messages.error(
            request,
            "This email is not eligible for a retry. Only failed enquiry "
            "notifications under the attempt limit can be rebuilt.",
        )
        return redirect("dashboard:email_log_detail", pk=email_log.pk)

    previous_attempts = email_log.attempts
    result = retry_email_log(email_log, actor=request.user)
    if result is None:
        messages.error(request, "The email could not be rebuilt for a retry.")
    elif result.is_successful:
        messages.success(
            request,
            "Retry accepted by the SMTP server. The email log has been updated.",
        )
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Email log #{email_log.pk} retried successfully",
            target_type="email_manager.emaillog",
            target_id=email_log.pk,
        )
    elif result.status == EmailLog.STATUS_SKIPPED:
        messages.warning(
            request, f"Retry not sent: {result.error_summary}"
        )
    else:
        messages.error(
            request,
            f"Retry failed after {max(result.attempts - previous_attempts, 1)} "
            f"attempt(s): {result.error_summary}",
        )
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Email log #{email_log.pk} retry failed",
            target_type="email_manager.emaillog",
            target_id=email_log.pk,
        )
    return redirect("dashboard:email_log_detail", pk=email_log.pk)


@email_manager_access("email_manager.delete_emaillog")
@require_POST
def log_prune(request):
    config = SMTPConfiguration.load()
    count = mailer.prune_email_logs(config.log_retention_days)
    log_activity(
        request,
        ActivityLog.ACTION_DELETE,
        f"Pruned {count} email log(s) older than "
        f"{config.log_retention_days} days",
    )
    messages.success(
        request,
        f"Removed {count} email log(s) older than "
        f"{config.log_retention_days} days.",
    )
    return redirect("dashboard:email_log_list")


# ---------------------------------------------------------------------------
# Notification rules
# ---------------------------------------------------------------------------
@email_manager_access("email_manager.view_notificationrule")
def notification_rules(request):
    rules = NotificationRule.objects.select_related("template").order_by(
        "event"
    )
    rows = [
        {
            "rule": rule,
            "form": NotificationRuleForm(
                instance=rule, prefix=f"rule{rule.pk}-"
            ),
        }
        for rule in rules
    ]
    return render(
        request,
        "dashboard/email_manager/rules.html",
        {
            **_tabs_context("rules"),
            "rows": rows,
            "rule_count": len(rows),
            "enabled_count": sum(1 for row in rows if row["rule"].is_enabled),
        },
    )


@email_manager_access("email_manager.change_notificationrule")
@require_POST
def notification_rule_update(request, pk):
    rule = get_object_or_404(
        NotificationRule.objects.select_related("template"), pk=pk
    )
    form = NotificationRuleForm(
        request.POST, instance=rule, prefix=f"rule{rule.pk}-"
    )
    if form.is_valid():
        form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Notification rule updated: {rule.get_event_display()} "
            f"({'enabled' if rule.is_enabled else 'disabled'})",
            target=rule,
        )
        messages.success(
            request, f"Notification rule “{rule.get_event_display()}” saved."
        )
    else:
        messages.error(
            request,
            f"The rule “{rule.get_event_display()}” could not be saved. "
            "Choose a template and try again.",
        )
    return redirect("dashboard:email_rules")
