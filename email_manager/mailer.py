"""Email delivery service.

All outgoing email goes through this module so that status handling, logging,
duplicate protection and error sanitisation stay consistent.

Two transports are supported:

``EMAIL_MANAGER_TRANSPORT=database`` (default)
    Use the SMTP settings saved in the dashboard. This is the production path.

``EMAIL_MANAGER_TRANSPORT=django``
    Use ``settings.EMAIL_BACKEND``. Automated tests use this with Django's
    in-memory backend, and operators can use it to defer to environment-only
    email configuration.
"""
from __future__ import annotations

import smtplib
import socket
import ssl
import time
from datetime import timedelta
from email.utils import make_msgid

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.smtp import EmailBackend
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone

from .crypto import SecretStorageError
from .models import EmailLog, EmailTemplate, SMTPConfiguration
from .templating import TemplateValidationError, render_email_template


class EmailDeliveryError(Exception):
    """Raised for configuration problems detected before sending."""


# ---------------------------------------------------------------------------
# Error sanitisation
# ---------------------------------------------------------------------------
def sanitize_smtp_error(exc: Exception) -> str:
    """Return a friendly message that never contains credentials or raw output."""
    if isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPNotSupportedError)):
        return (
            "The SMTP server rejected the username or app password. Confirm "
            "that SMTP AUTH is enabled and that the credential is valid."
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return (
            "The SMTP server rejected the recipient address. Check the address "
            "and try again."
        )
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return (
            "The SMTP server rejected the sender address. Confirm the sender "
            "email address is authorised by the provider."
        )
    if isinstance(exc, smtplib.SMTPDataError):
        return (
            "The SMTP server rejected the message. Check the sender address, "
            "message size and provider sending limits."
        )
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (
            "The SMTP server closed the connection unexpectedly. Check the "
            "host, port and TLS/SSL mode, then try again."
        )
    if isinstance(exc, smtplib.SMTPConnectError):
        return (
            "The SMTP server refused the connection. Check the host and port "
            "with your email provider."
        )
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return (
            "The SMTP server did not respond before the timeout. Check the "
            "host, port, security mode and network access."
        )
    if isinstance(exc, ssl.SSLError):
        return (
            "A secure connection could not be established. Check whether the "
            "provider expects STARTTLS or SSL/TLS and use the matching port."
        )
    if isinstance(exc, (ConnectionRefusedError, ConnectionResetError, OSError)):
        return (
            "The SMTP server could not be reached. Check the host, port and "
            "network access, including any firewall rules."
        )
    if isinstance(exc, SecretStorageError):
        return (
            "The saved SMTP password could not be decrypted. Check "
            "EMAIL_ENCRYPTION_KEY, or enter the password again."
        )
    if isinstance(exc, (ValueError, EmailDeliveryError)):
        return str(exc)[:500] if str(exc) else "The SMTP configuration is invalid."
    if isinstance(exc, smtplib.SMTPException):
        return "The SMTP server reported an error. Check the SMTP settings and try again."
    return "The email could not be sent. Check the SMTP configuration and try again."


_TRANSIENT_EXCEPTIONS = (
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    socket.timeout,
    TimeoutError,
    ConnectionResetError,
    ConnectionRefusedError,
)


def _is_transient(exc: Exception) -> bool:
    return isinstance(exc, _TRANSIENT_EXCEPTIONS)


def _transport() -> str:
    mode = str(getattr(settings, "EMAIL_MANAGER_TRANSPORT", "database")).lower()
    return "django" if mode == "django" else "database"


def _retry_delay() -> float:
    try:
        return max(0.0, float(getattr(settings, "EMAIL_MANAGER_RETRY_DELAY", 2)))
    except (TypeError, ValueError):
        return 2.0


def _auto_retries() -> int:
    try:
        return max(0, int(getattr(settings, "EMAIL_MANAGER_AUTO_RETRIES", 1)))
    except (TypeError, ValueError):
        return 1


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
def _build_smtp_backend(config: SMTPConfiguration) -> EmailBackend:
    if not config.is_configured:
        raise EmailDeliveryError(
            "SMTP is not fully configured. Add a host, sender email and any "
            "required credentials."
        )
    try:
        password = config.decrypt_password()
    except SecretStorageError:
        raise
    return EmailBackend(
        host=config.host,
        port=config.port,
        username=config.username,
        password=password,
        use_tls=config.use_tls,
        use_ssl=config.use_ssl,
        timeout=config.timeout,
        fail_silently=False,
    )


def test_connection(config: SMTPConfiguration | None = None) -> dict:
    """Open, authenticate and close a real SMTP connection.

    This always uses SMTP directly, even when the transport setting is
    ``django``, because the purpose of the action is to verify the saved SMTP
    credentials.
    """
    config = config or SMTPConfiguration.load()
    if not config.is_configured:
        message = (
            "SMTP is not fully configured. Add a host, sender email and any "
            "required credentials before testing."
        )
        config.record_test_result(success=False, message=message)
        return {"ok": False, "message": message}

    backend = None
    try:
        backend = _build_smtp_backend(config)
        backend.open()
        connection = getattr(backend, "connection", None)
        if connection is not None and hasattr(connection, "noop"):
            connection.noop()
        message = (
            "Connected and authenticated with the SMTP server successfully. "
            "This confirms the connection; it does not send an email."
        )
        config.record_test_result(success=True, message=message)
        return {"ok": True, "message": message}
    except Exception as exc:  # Deliberately converted to a safe message.
        message = sanitize_smtp_error(exc)
        config.record_test_result(success=False, message=message)
        return {"ok": False, "message": message}
    finally:
        if backend is not None:
            try:
                backend.close()
            except Exception:
                pass


def _apply_transport(message: EmailMultiAlternatives, config: SMTPConfiguration):
    if _transport() == "django":
        message.connection = get_connection(fail_silently=False)
    else:
        message.connection = _build_smtp_backend(config)


def _sender_for(config: SMTPConfiguration) -> str:
    if _transport() == "django":
        return (
            config.from_email
            or getattr(settings, "DEFAULT_FROM_EMAIL", "")
            or "no-reply@example.com"
        )
    return config.from_email


def _deliver(message: EmailMultiAlternatives, config: SMTPConfiguration) -> int:
    _apply_transport(message, config)
    return message.send(fail_silently=False)


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
def _base_log_fields(
    *,
    template: EmailTemplate | None,
    event: str,
    recipient: str,
    recipient_name: str,
    sender: str,
    enquiry,
    triggered_by,
    dedupe_key: str | None,
) -> dict:
    return {
        "recipient": recipient,
        "recipient_name": (recipient_name or "")[:160],
        "sender": sender or "",
        "template_key": template.key if template else "",
        "template_name": template.name if template else "",
        "event": (event or "")[:40],
        "enquiry": enquiry,
        "status": EmailLog.STATUS_QUEUED,
        "attempts": 0,
        "dedupe_key": dedupe_key,
        "triggered_by": triggered_by if getattr(triggered_by, "pk", None) else None,
    }


def _finish(
    log: EmailLog,
    *,
    status: str,
    error_summary: str = "",
    message_id: str = "",
) -> EmailLog:
    log.status = status
    log.error_summary = (error_summary or "")[:500]
    log.message_id = (message_id or "")[:255]
    if status in {EmailLog.STATUS_SENT, EmailLog.STATUS_DELIVERY_CONFIRMED}:
        log.sent_at = timezone.now()
    if log.pk is None:
        # An unsaved log has no row to update. Persist it in full.
        log.save()
        return log
    log.save(
        update_fields=[
            "recipient",
            "recipient_name",
            "sender",
            "subject",
            "template_key",
            "template_name",
            "event",
            "enquiry",
            "status",
            "attempts",
            "error_summary",
            "message_id",
            "dedupe_key",
            "sent_at",
            "updated_at",
        ]
    )
    return log


def _valid_recipient(value: str) -> bool:
    try:
        validate_email(value)
        return True
    except ValidationError:
        return False


def send_template_email(
    *,
    template: EmailTemplate | None,
    event: str,
    recipient: str,
    context: dict,
    enquiry=None,
    triggered_by=None,
    dedupe_key: str | None = None,
    recipient_name: str = "",
    existing_log: EmailLog | None = None,
    allow_when_disabled: bool = False,
) -> EmailLog:
    """Render and send one template email, recording every outcome.

    The function never raises for delivery or configuration failures. It returns
    an :class:`EmailLog` whose status describes exactly what happened.
    """
    recipient = (recipient or "").strip()
    config = SMTPConfiguration.load()
    sender = _sender_for(config)

    if not _valid_recipient(recipient):
        log = existing_log or EmailLog(
            **_base_log_fields(
                template=template,
                event=event,
                recipient=recipient[:254] or "invalid",
                recipient_name=recipient_name,
                sender=sender,
                enquiry=enquiry,
                triggered_by=triggered_by,
                dedupe_key=dedupe_key,
            )
        )
        log.attempts += 1
        log.subject = (template.name if template else "")[:255]
        return _finish(
            log,
            status=EmailLog.STATUS_FAILED,
            error_summary="The recipient email address is not valid.",
        )

    # Duplicate protection: reuse an existing attempt instead of sending twice.
    if dedupe_key and existing_log is None:
        existing = EmailLog.objects.filter(dedupe_key=dedupe_key).first()
        if existing:
            return existing

    if existing_log is not None:
        log = existing_log
        log.status = EmailLog.STATUS_QUEUED
        log.error_summary = ""
        log.sent_at = None
    else:
        log = EmailLog(
            **_base_log_fields(
                template=template,
                event=event,
                recipient=recipient,
                recipient_name=recipient_name,
                sender=sender,
                enquiry=enquiry,
                triggered_by=triggered_by,
                dedupe_key=dedupe_key,
            )
        )
        try:
            log.save()
        except Exception:
            # A concurrent request may have created the same dedupe key.
            if dedupe_key:
                existing = EmailLog.objects.filter(dedupe_key=dedupe_key).first()
                if existing:
                    return existing
            raise

    # Gate checks. These are logged as skipped so the reason is visible.
    if template is None:
        log.attempts += 1
        return _finish(
            log,
            status=EmailLog.STATUS_FAILED,
            error_summary="The email template could not be found.",
        )
    if not template.is_active:
        log.attempts += 1
        return _finish(
            log,
            status=EmailLog.STATUS_SKIPPED,
            error_summary="The email template is inactive.",
        )
    if not allow_when_disabled and not config.is_enabled:
        log.attempts += 1
        return _finish(
            log,
            status=EmailLog.STATUS_SKIPPED,
            error_summary=(
                "Outgoing email is disabled in SMTP settings, so nothing was sent."
            ),
        )
    if _transport() == "database" and not config.is_configured:
        log.attempts += 1
        return _finish(
            log,
            status=EmailLog.STATUS_SKIPPED,
            error_summary=(
                "SMTP is not fully configured, so nothing was sent."
            ),
        )

    try:
        rendered = render_email_template(
            template.subject,
            template.html_body,
            template.text_body,
            context,
        )
    except TemplateValidationError:
        log.attempts += 1
        return _finish(
            log,
            status=EmailLog.STATUS_FAILED,
            error_summary=(
                "The email template contains unsupported placeholders or syntax."
            ),
        )

    log.subject = rendered.subject[:255]

    message = EmailMultiAlternatives(
        subject=rendered.subject,
        body=rendered.text_body or "Please view this email in an HTML client.",
        from_email=sender,
        to=[recipient],
    )
    if rendered.html_body:
        message.attach_alternative(rendered.html_body, "text/html")
    reply_to = config.effective_reply_to
    if reply_to:
        message.reply_to = [reply_to]

    message_id = make_msgid()
    message.extra_headers["Message-ID"] = message_id
    message.encoding = "utf-8"

    attempts_allowed = 1 + _auto_retries()
    last_error = ""
    for index in range(attempts_allowed):
        log.attempts += 1
        try:
            _deliver(message, config)
            log.error_summary = ""
            return _finish(
                log,
                status=EmailLog.STATUS_SENT,
                message_id=message_id,
            )
        except Exception as exc:
            last_error = sanitize_smtp_error(exc)
            if index + 1 < attempts_allowed and _is_transient(exc):
                delay = _retry_delay()
                if delay:
                    time.sleep(delay)
                continue
            break

    return _finish(
        log,
        status=EmailLog.STATUS_FAILED,
        error_summary=last_error or "The email could not be sent.",
    )


def send_test_email(to_email: str, *, actor=None) -> EmailLog:
    """Send a real test message and log the result.

    The test is allowed while outgoing notifications are disabled so an
    administrator can verify credentials before enabling the service.
    """
    from core.models import SiteSettings

    config = SMTPConfiguration.load()
    try:
        site_name = SiteSettings.load().company_name
    except Exception:
        site_name = "Sanjeev Power Controls"

    subject = f"SMTP test from {site_name}"
    text_body = (
        f"This is a test email from the {site_name} dashboard.\n\n"
        "If you received it, the saved SMTP configuration accepted the "
        "message. Acceptance by the SMTP server does not guarantee inbox "
        "delivery, but it confirms the connection and authentication path.\n"
    )
    html_body = (
        "<div style=\"font-family:Arial,Helvetica,sans-serif;color:#1F2937;"
        "max-width:560px;\">"
        f"<h1 style=\"font-size:20px;color:#0B1F3A;\">SMTP test successful</h1>"
        f"<p>This is a test email from the <strong>{site_name}</strong> dashboard.</p>"
        "<p>If you received it, the saved SMTP configuration accepted the "
        "message. Acceptance by the SMTP server does not guarantee inbox "
        "delivery, but it confirms the connection and authentication path.</p>"
        "</div>"
    )

    log = EmailLog(
        recipient=to_email,
        sender=_sender_for(config),
        subject=subject,
        template_key="",
        template_name="Test email",
        event="test_email",
        status=EmailLog.STATUS_QUEUED,
        attempts=0,
        triggered_by=actor if getattr(actor, "pk", None) else None,
    )
    log.save()

    if _transport() == "database" and not config.is_configured:
        log.attempts = 1
        return _finish(
            log,
            status=EmailLog.STATUS_FAILED,
            error_summary=(
                "SMTP is not fully configured. Add a host, sender email and "
                "any required credentials."
            ),
        )

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=_sender_for(config),
        to=[to_email],
    )
    message.attach_alternative(html_body, "text/html")
    reply_to = config.effective_reply_to
    if reply_to:
        message.reply_to = [reply_to]
    message_id = make_msgid()
    message.extra_headers["Message-ID"] = message_id
    message.encoding = "utf-8"

    last_error = ""
    for index in range(1 + _auto_retries()):
        log.attempts += 1
        try:
            _deliver(message, config)
            return _finish(
                log, status=EmailLog.STATUS_SENT, message_id=message_id
            )
        except Exception as exc:
            last_error = sanitize_smtp_error(exc)
            if index + 1 < 1 + _auto_retries() and _is_transient(exc):
                delay = _retry_delay()
                if delay:
                    time.sleep(delay)
                continue
            break

    return _finish(
        log,
        status=EmailLog.STATUS_FAILED,
        error_summary=last_error or "The test email could not be sent.",
    )


def prune_email_logs(days: int | None = None) -> int:
    """Delete logs older than the retention window. Returns the row count."""
    config = SMTPConfiguration.load()
    retention = days or config.log_retention_days or 180
    cutoff = timezone.now() - timedelta(days=int(retention))
    queryset = EmailLog.objects.filter(created_at__lt=cutoff)
    count = queryset.count()
    queryset.delete()
    return count
