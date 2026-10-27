"""Database models for the dashboard Email Manager.

The password is never stored in plaintext. Only a Fernet ciphertext produced by
:mod:`email_manager.crypto` is persisted, and it is never included in model
``__str__`` output, admin listings or template contexts.
"""
from __future__ import annotations

import re
from email.utils import formataddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .crypto import (
    SecretStorageError,
    decrypt_secret,
    encrypt_secret,
    mask_secret,
)
from .templating import validate_template_source


class SMTPConfiguration(models.Model):
    """Singleton SMTP configuration (always ``pk=1``)."""

    PRESET_GMAIL = "gmail"
    PRESET_MICROSOFT365 = "microsoft365"
    PRESET_CUSTOM = "custom"
    PRESET_CHOICES = [
        (PRESET_GMAIL, "Gmail"),
        (PRESET_MICROSOFT365, "Microsoft 365"),
        (PRESET_CUSTOM, "Custom SMTP"),
    ]

    TEST_PENDING = ""
    TEST_SUCCESS = "success"
    TEST_FAILED = "failed"
    TEST_STATUS_CHOICES = [
        (TEST_PENDING, "Not tested"),
        (TEST_SUCCESS, "Connection succeeded"),
        (TEST_FAILED, "Connection failed"),
    ]

    preset = models.CharField(
        max_length=20, choices=PRESET_CHOICES, default=PRESET_CUSTOM
    )
    host = models.CharField(max_length=255, blank=True)
    port = models.PositiveIntegerField(
        default=587, validators=[MinValueValidator(1), MaxValueValidator(65535)]
    )
    username = models.CharField(max_length=255, blank=True)
    # Fernet ciphertext only. Plaintext must never be written to this field.
    password_ciphertext = models.TextField(blank=True)
    sender_email = models.EmailField(blank=True)
    sender_name = models.CharField(
        max_length=120, default="Sanjeev Power Controls"
    )
    use_tls = models.BooleanField(
        default=True, verbose_name="Use STARTTLS",
        help_text="Usually port 587. Upgrades a plain connection to TLS.",
    )
    use_ssl = models.BooleanField(
        default=False, verbose_name="Use SSL/TLS",
        help_text="Usually port 465. Encrypts the connection from the start.",
    )
    timeout = models.PositiveIntegerField(
        default=20,
        validators=[MinValueValidator(5), MaxValueValidator(120)],
        help_text="Connection timeout in seconds (5–120).",
    )
    reply_to = models.EmailField(
        blank=True, help_text="Optional Reply-To address for outgoing mail."
    )
    admin_notification_email = models.EmailField(
        blank=True,
        help_text=(
            "Receives internal lead alerts. Falls back to the website contact "
            "email, then ADMIN_NOTIFICATION_EMAIL."
        ),
    )
    is_enabled = models.BooleanField(
        default=False,
        verbose_name="Enable outgoing email",
        help_text=(
            "When disabled, notification emails are recorded as skipped and "
            "nothing is sent. Connection tests still work."
        ),
    )
    log_retention_days = models.PositiveIntegerField(
        default=180,
        validators=[MinValueValidator(7), MaxValueValidator(3650)],
        help_text="Email logs older than this may be pruned. Default 180 days.",
    )
    last_test_status = models.CharField(
        max_length=20, choices=TEST_STATUS_CHOICES, blank=True
    )
    last_test_message = models.CharField(max_length=500, blank=True)
    last_test_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="smtp_configurations_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SMTP configuration"
        verbose_name_plural = "SMTP configuration"
        permissions = [
            (
                "manage_smtp",
                "Can manage SMTP settings and send test email",
            ),
        ]

    def __str__(self):
        return "SMTP configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------
    @property
    def has_password(self) -> bool:
        return bool(self.password_ciphertext)

    @property
    def masked_password(self) -> str:
        return mask_secret(self.password_ciphertext)

    def set_password(self, raw_password: str) -> None:
        """Encrypt and store a new password. Never stores plaintext."""
        self.password_ciphertext = encrypt_secret(raw_password or "")

    def clear_password(self) -> None:
        self.password_ciphertext = ""

    def decrypt_password(self) -> str:
        """Return the plaintext password for an SMTP connection only."""
        return decrypt_secret(self.password_ciphertext)

    # ------------------------------------------------------------------
    # Derived state
    # ------------------------------------------------------------------
    @property
    def is_configured(self) -> bool:
        """Enough information exists to attempt a real SMTP connection."""
        if not self.host.strip() or not self.sender_email.strip():
            return False
        if self.username.strip() and not self.password_ciphertext:
            return False
        return True

    @property
    def from_email(self) -> str:
        sender = (self.sender_email or "").strip()
        name = (self.sender_name or "").strip()
        if sender and name:
            return formataddr((name, sender))
        return sender

    @property
    def effective_reply_to(self) -> str:
        return (self.reply_to or self.sender_email or "").strip()

    @property
    def connection_status(self) -> dict:
        """Display-safe status for the dashboard. Contains no secrets."""
        if not self.is_enabled:
            return {
                "label": "Outgoing email disabled",
                "css": "disabled",
                "detail": "Notifications are recorded as skipped.",
            }
        if not self.is_configured:
            return {
                "label": "Not configured",
                "css": "warning",
                "detail": "Add a host, sender address and credentials.",
            }
        if self.last_test_status == self.TEST_SUCCESS:
            return {
                "label": "Connected",
                "css": "success",
                "detail": self.last_test_message
                or "The last connection test succeeded.",
            }
        if self.last_test_status == self.TEST_FAILED:
            return {
                "label": "Connection test failed",
                "css": "failed",
                "detail": self.last_test_message
                or "Review the SMTP settings and test again.",
            }
        return {
            "label": "Configured, not tested",
            "css": "configured",
            "detail": "Run a connection test to confirm the credentials.",
        }

    @property
    def from_address(self) -> str:
        return self.from_email

    def clean(self):
        errors = {}
        if self.use_tls and self.use_ssl:
            errors["use_ssl"] = (
                "Choose either STARTTLS or SSL/TLS, not both. "
                "Use STARTTLS on port 587 or SSL/TLS on port 465."
            )
        if self.is_enabled and not self.host.strip():
            errors["host"] = "Enter the SMTP host before enabling outgoing email."
        if self.is_enabled and not self.sender_email.strip():
            errors["sender_email"] = (
                "Enter the sender email address before enabling outgoing email."
            )
        if self.username.strip() and not self.password_ciphertext:
            errors["username"] = (
                "A username is set but no password is saved. Enter the SMTP "
                "password or app password."
            )
        if errors:
            raise ValidationError(errors)
        return super().clean()

    def record_test_result(self, *, success: bool, message: str) -> None:
        self.last_test_status = (
            self.TEST_SUCCESS if success else self.TEST_FAILED
        )
        self.last_test_message = (message or "")[:500]
        self.last_test_at = timezone.now()
        self.save(
            update_fields=[
                "last_test_status",
                "last_test_message",
                "last_test_at",
                "updated_at",
            ]
        )


class EmailTemplate(models.Model):
    """Administrator-editable email content using a restricted placeholder set."""

    AUDIENCE_CUSTOMER = "customer"
    AUDIENCE_ADMIN = "admin"
    AUDIENCE_SYSTEM = "system"
    AUDIENCE_CHOICES = [
        (AUDIENCE_CUSTOMER, "Customer"),
        (AUDIENCE_ADMIN, "Internal / administrator"),
        (AUDIENCE_SYSTEM, "System"),
    ]

    key = models.SlugField(
        max_length=80,
        unique=True,
        help_text=(
            "Stable identifier used by notification rules, e.g. "
            "customer_enquiry_acknowledgement."
        ),
    )
    name = models.CharField(max_length=160)
    description = models.TextField(
        blank=True, help_text="Optional note for dashboard staff."
    )
    audience = models.CharField(
        max_length=20, choices=AUDIENCE_CHOICES, default=AUDIENCE_ADMIN
    )
    subject = models.CharField(
        max_length=255,
        help_text="Approved placeholders are allowed. Line breaks are removed.",
    )
    html_body = models.TextField(
        blank=True,
        help_text=(
            "HTML email body. Django template tags are not allowed; use the "
            "approved placeholders only."
        ),
    )
    text_body = models.TextField(
        blank=True,
        help_text="Plain-text alternative for email clients that block HTML.",
    )
    is_active = models.BooleanField(
        default=True, help_text="Inactive templates are not used for notifications."
    )
    is_system = models.BooleanField(
        default=False,
        help_text=(
            "System templates are seeded by the application. Their key cannot "
            "be changed and they cannot be deleted."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "email template"
        verbose_name_plural = "email templates"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse(
            "dashboard:email_template_edit", kwargs={"pk": self.pk}
        )

    def clean(self):
        errors: dict[str, list[str]] = {}

        subject_errors = validate_template_source(
            self.subject, label="Subject"
        )
        if subject_errors:
            errors.setdefault("subject", []).extend(subject_errors)
        html_errors = validate_template_source(
            self.html_body, label="HTML body"
        )
        if html_errors:
            errors.setdefault("html_body", []).extend(html_errors)
        text_errors = validate_template_source(
            self.text_body, label="Plain-text body"
        )
        if text_errors:
            errors.setdefault("text_body", []).extend(text_errors)

        if not (self.html_body or "").strip() and not (
            self.text_body or ""
        ).strip():
            errors.setdefault("html_body", []).append(
                "Add an HTML body, a plain-text body, or both."
            )
        if not (self.subject or "").strip():
            errors.setdefault("subject", []).append("Enter an email subject.")
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", self.key or ""):
            errors.setdefault("key", []).append(
                "The template key must use lowercase letters, numbers, "
                "hyphens or underscores."
            )
        if errors:
            raise ValidationError(errors)
        return super().clean()

    def body_for_preview(self) -> str:
        return self.html_body or self.text_body


class EmailLog(models.Model):
    """One attempt to deliver one email. Message bodies are never stored."""

    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_DELIVERY_CONFIRMED = "delivery_confirmed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Accepted by SMTP"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
        (STATUS_DELIVERY_CONFIRMED, "Delivery confirmed"),
    ]

    recipient = models.EmailField()
    recipient_name = models.CharField(max_length=160, blank=True)
    sender = models.EmailField(blank=True)
    subject = models.CharField(max_length=255, blank=True)
    template_key = models.SlugField(max_length=80, blank=True)
    template_name = models.CharField(max_length=160, blank=True)
    event = models.CharField(max_length=40, blank=True, db_index=True)
    enquiry = models.ForeignKey(
        "enquiries.Enquiry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED, db_index=True
    )
    attempts = models.PositiveIntegerField(default=0)
    error_summary = models.CharField(max_length=500, blank=True)
    message_id = models.CharField(max_length=255, blank=True)
    dedupe_key = models.CharField(
        max_length=255, unique=True, null=True, blank=True
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs_triggered",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "email log"
        verbose_name_plural = "email logs"
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["event", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.recipient} — {self.get_status_display()}"

    @property
    def status_css(self) -> str:
        return {
            self.STATUS_QUEUED: "queued",
            self.STATUS_SENT: "sent",
            self.STATUS_FAILED: "failed",
            self.STATUS_SKIPPED: "skipped",
            self.STATUS_DELIVERY_CONFIRMED: "confirmed",
        }.get(self.status, "neutral")

    @property
    def event_label(self) -> str:
        """Human-readable event name, including non-rule events."""
        extra = {
            "test_email": "Test email",
            "template_test": "Template preview",
        }
        if self.event in extra:
            return extra[self.event]
        return dict(NotificationRule.EVENT_CHOICES).get(self.event, self.event)

    @property
    def is_successful(self) -> bool:
        return self.status in {
            self.STATUS_SENT,
            self.STATUS_DELIVERY_CONFIRMED,
        }

    @property
    def max_attempts(self) -> int:
        return int(getattr(settings, "EMAIL_MANAGER_MAX_ATTEMPTS", 3))

    @property
    def can_retry(self) -> bool:
        """Only failed template emails linked to an enquiry can be rebuilt.

        Full message bodies are deliberately not stored, so an arbitrary failed
        email cannot be replayed. Enquiry notifications can be reconstructed
        safely from the stored enquiry and template.
        """
        return bool(
            self.status == self.STATUS_FAILED
            and self.attempts < self.max_attempts
            and self.template_key
            and self.enquiry_id
        )

    @property
    def status_explanation(self) -> str:
        return {
            self.STATUS_QUEUED: (
                "The message is waiting to be sent. Synchronous local sending "
                "normally moves out of this state immediately."
            ),
            self.STATUS_SENT: (
                "The SMTP server accepted the message. This does not prove it "
                "reached the recipient's inbox."
            ),
            self.STATUS_FAILED: (
                "The message could not be accepted by the SMTP server. Review "
                "the sanitised error summary."
            ),
            self.STATUS_SKIPPED: (
                "No message was sent because outgoing email is disabled, the "
                "template is inactive, or the SMTP configuration is incomplete."
            ),
            self.STATUS_DELIVERY_CONFIRMED: (
                "A provider delivery receipt confirmed delivery. This status is "
                "only used when a provider actually supplies confirmation."
            ),
        }.get(self.status, "")


class NotificationRule(models.Model):
    """Maps a business event to a template and recipient type."""

    EVENT_NEW_ENQUIRY_CUSTOMER = "new_enquiry_customer"
    EVENT_NEW_ENQUIRY_ADMIN = "new_enquiry_admin"
    EVENT_PRODUCT_ENQUIRY_ADMIN = "product_enquiry_admin"
    EVENT_ADMIN_NEW_LEAD = "admin_new_lead"
    EVENT_CONTACT_CONFIRMATION = "contact_confirmation"
    EVENT_PASSWORD_RESET = "password_reset"
    EVENT_LEAD_ASSIGNED = "lead_assigned"
    EVENT_STATUS_CHANGED = "status_changed"
    EVENT_FOLLOW_UP_DUE = "follow_up_due"
    EVENT_CHOICES = [
        (
            EVENT_NEW_ENQUIRY_CUSTOMER,
            "New enquiry — customer acknowledgement",
        ),
        (EVENT_NEW_ENQUIRY_ADMIN, "New enquiry — internal notification"),
        (
            EVENT_PRODUCT_ENQUIRY_ADMIN,
            "Product enquiry — internal notification",
        ),
        (EVENT_ADMIN_NEW_LEAD, "New lead — short administrator alert"),
        (
            EVENT_CONTACT_CONFIRMATION,
            "Contact form — customer confirmation",
        ),
        (EVENT_PASSWORD_RESET, "Password reset requested"),
        (EVENT_LEAD_ASSIGNED, "Lead assigned to a staff member"),
        (EVENT_STATUS_CHANGED, "Enquiry status changed"),
        (EVENT_FOLLOW_UP_DUE, "Follow-up due"),
    ]

    RECIPIENT_CUSTOMER = "customer"
    RECIPIENT_ADMIN = "admin"
    RECIPIENT_ASSIGNED_STAFF = "assigned_staff"
    RECIPIENT_EVENT_USER = "event_user"
    RECIPIENT_CHOICES = [
        (RECIPIENT_CUSTOMER, "Enquiry customer"),
        (RECIPIENT_ADMIN, "Configured administrator"),
        (RECIPIENT_ASSIGNED_STAFF, "Assigned staff member"),
        (RECIPIENT_EVENT_USER, "Affected user account"),
    ]

    event = models.CharField(
        max_length=40, choices=EVENT_CHOICES, unique=True
    )
    template = models.ForeignKey(
        EmailTemplate, on_delete=models.PROTECT, related_name="rules"
    )
    recipient = models.CharField(
        max_length=20,
        choices=RECIPIENT_CHOICES,
        default=RECIPIENT_ADMIN,
        help_text=(
            "Fixed by the event so customer data is never sent to an "
            "unexpected recipient."
        ),
    )
    is_enabled = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event"]
        verbose_name = "notification rule"
        verbose_name_plural = "notification rules"

    def __str__(self):
        return self.get_event_display()

    @classmethod
    def for_event(cls, event):
        return (
            cls.objects.select_related("template")
            .filter(event=event, is_enabled=True, template__is_active=True)
            .first()
        )
