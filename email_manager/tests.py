"""Tests for the dashboard Email Manager.

Coverage required by the module specification:

* SMTP configuration validation (TLS/SSL, required fields, password handling)
* Server-side authorisation for every SMTP/test route
* A successful test email using Django's in-memory backend
* Delivery failure handling with sanitised errors
* Enquiry persistence when sending fails
* Restricted placeholder rendering and HTML escaping
* Secret masking in the database and in the dashboard
* Email log creation, retry eligibility and duplicate protection
"""
from __future__ import annotations

import smtplib
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from enquiries.models import Enquiry

from .crypto import (
    SecretStorageError,
    decrypt_secret,
    encrypt_secret,
    mask_secret,
)
from .defaults import DEFAULT_TEMPLATES, ensure_defaults, sample_context
from .forms import SMTPConfigurationForm
from .mailer import (
    sanitize_smtp_error,
    send_template_email,
    send_test_email,
)
from .models import EmailLog, EmailTemplate, NotificationRule, SMTPConfiguration
from .notifications import dispatch_event, notify_new_enquiry
from .templating import (
    TemplateValidationError,
    render_email_template,
    sanitize_email_html,
    validate_template_source,
)

User = get_user_model()

TEST_KEY = "unit-test-encryption-key-that-is-long-enough"
STRONG_PASSWORD = "Correct-Horse-Battery-Staple-42"


def make_user(*, username="staff", email="staff@example.com", superuser=False):
    user = User.objects.create(
        username=username,
        email=email,
        is_staff=True,
        is_superuser=superuser,
        is_active=True,
    )
    user.set_password("Test-pass-12345")
    user.save()
    return user


def grant(user, *codenames):
    permissions = Permission.objects.filter(
        content_type__app_label="email_manager", codename__in=codenames
    )
    user.user_permissions.add(*permissions)
    return user


def configure_smtp(**overrides):
    config = SMTPConfiguration.load()
    config.host = overrides.pop("host", "smtp.example.com")
    config.port = overrides.pop("port", 587)
    config.username = overrides.pop("username", "")
    config.sender_email = overrides.pop("sender_email", "no-reply@example.com")
    config.sender_name = overrides.pop("sender_name", "Sanjeev Power Controls")
    config.admin_notification_email = overrides.pop(
        "admin_notification_email", "admin@example.com"
    )
    config.use_tls = overrides.pop("use_tls", True)
    config.use_ssl = overrides.pop("use_ssl", False)
    config.is_enabled = overrides.pop("is_enabled", True)
    for key, value in overrides.items():
        setattr(config, key, value)
    config.save()
    return config


# ---------------------------------------------------------------------------
# Encryption and masking
# ---------------------------------------------------------------------------
@override_settings(EMAIL_ENCRYPTION_KEY=TEST_KEY, DEBUG=True)
class CryptoTests(SimpleTestCase):
    def test_secret_round_trip(self):
        ciphertext = encrypt_secret(STRONG_PASSWORD)
        self.assertNotIn(STRONG_PASSWORD, ciphertext)
        self.assertEqual(decrypt_secret(ciphertext), STRONG_PASSWORD)
        self.assertNotEqual(ciphertext, encrypt_secret(STRONG_PASSWORD))

    def test_empty_secret(self):
        self.assertEqual(encrypt_secret(""), "")
        self.assertEqual(decrypt_secret(""), "")

    def test_mask_never_reveals_characters(self):
        self.assertEqual(mask_secret(encrypt_secret(STRONG_PASSWORD)), "••••••••")
        self.assertEqual(mask_secret(""), "Not set")

    @override_settings(EMAIL_ENCRYPTION_KEY="")
    def test_production_requires_a_key(self):
        # The DEBUG fallback is intentionally refused when DEBUG is off.
        with override_settings(DEBUG=False):
            with self.assertRaises(SecretStorageError):
                encrypt_secret("secret")

    def test_passphrase_is_accepted(self):
        with override_settings(EMAIL_ENCRYPTION_KEY="a long passphrase not base64"):
            self.assertEqual(decrypt_secret(encrypt_secret("value")), "value")


# ---------------------------------------------------------------------------
# Template validation and rendering
# ---------------------------------------------------------------------------
class TemplateValidationTests(SimpleTestCase):
    def test_approved_placeholders_are_allowed(self):
        self.assertEqual(
            validate_template_source("Hello {{ customer_name }}", label="Body"), []
        )

    def test_unknown_placeholder_is_rejected(self):
        errors = validate_template_source("Hello {{ secret_token }}", label="Body")
        self.assertTrue(any("not an approved placeholder" in error for error in errors))

    def test_template_tags_are_rejected(self):
        errors = validate_template_source(
            "{% include 'secrets.html' %}", label="Body"
        )
        self.assertTrue(any("template tags" in error for error in errors))

    def test_safe_filter_is_rejected(self):
        errors = validate_template_source("{{ enquiry_message|safe }}", label="Body")
        self.assertTrue(any("not allowed" in error for error in errors))

    def test_approved_filter_is_allowed(self):
        self.assertEqual(
            validate_template_source("{{ customer_name|upper }}", label="Body"), []
        )

    def test_unclosed_placeholder_is_rejected(self):
        errors = validate_template_source("{{ customer_name", label="Body")
        self.assertTrue(any("closing braces" in error for error in errors))

    def test_every_default_template_validates(self):
        for item in DEFAULT_TEMPLATES:
            for field in ("subject", "html_body", "text_body"):
                self.assertEqual(
                    validate_template_source(item[field], label=item["key"]),
                    [],
                    f"{item['key']} has an invalid {field}",
                )

    def test_rendering_substitutes_escapes_and_sanitises(self):
        rendered = render_email_template(
            "Enquiry {{ enquiry_id }}",
            "<p>Hello {{ customer_name }}</p><script>alert(1)</script>",
            "Hello {{ customer_name }}",
            {
                "enquiry_id": "SPC-1",
                "customer_name": '<script>alert("x")</script>',
            },
        )
        self.assertEqual(rendered.subject, "Enquiry SPC-1")
        self.assertNotIn("<script>", rendered.html_body)
        self.assertIn("&lt;script&gt;", rendered.html_body)
        self.assertIn('<script>alert("x")</script>', rendered.text_body)

    def test_sanitiser_removes_active_content(self):
        cleaned = sanitize_email_html(
            '<p onclick="steal()">Hi</p>'
            '<iframe src="https://evil.example"></iframe>'
            '<a href="javascript:alert(1)">x</a>'
        )
        self.assertNotIn("onclick", cleaned)
        self.assertNotIn("<iframe", cleaned)
        self.assertNotIn("javascript:", cleaned)

    def test_unknown_placeholder_raises_on_render(self):
        with self.assertRaises(TemplateValidationError):
            render_email_template("Hi", "{{ not_allowed }}", "", {})


# ---------------------------------------------------------------------------
# SMTP form validation
# ---------------------------------------------------------------------------
@override_settings(EMAIL_ENCRYPTION_KEY=TEST_KEY, DEBUG=True)
class SMTPFormTests(TestCase):
    def form_data(self, **overrides):
        data = {
            "preset": SMTPConfiguration.PRESET_CUSTOM,
            "host": "smtp.example.com",
            "port": "587",
            "username": "mailer@example.com",
            "sender_email": "no-reply@example.com",
            "sender_name": "Sanjeev Power Controls",
            "use_tls": "on",
            "timeout": "20",
            "reply_to": "",
            "admin_notification_email": "admin@example.com",
            "is_enabled": "on",
            "log_retention_days": "180",
            "password": STRONG_PASSWORD,
        }
        data.update(overrides)
        return data

    def test_rejects_both_tls_and_ssl(self):
        form = SMTPConfigurationForm(
            data=self.form_data(use_ssl="on"),
            instance=SMTPConfiguration.load(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("use_ssl", form.errors)

    def test_requires_host_when_enabled(self):
        form = SMTPConfigurationForm(
            data=self.form_data(host=""),
            instance=SMTPConfiguration.load(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("host", form.errors)

    def test_requires_sender_when_enabled(self):
        form = SMTPConfigurationForm(
            data=self.form_data(sender_email=""),
            instance=SMTPConfiguration.load(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("sender_email", form.errors)

    def test_requires_password_for_username(self):
        form = SMTPConfigurationForm(
            data=self.form_data(password=""),
            instance=SMTPConfiguration.load(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password", form.errors)

    def test_password_is_encrypted_on_save(self):
        form = SMTPConfigurationForm(
            data=self.form_data(), instance=SMTPConfiguration.load()
        )
        self.assertTrue(form.is_valid(), form.errors)
        config = form.save()
        self.assertNotIn(STRONG_PASSWORD, config.password_ciphertext)
        self.assertEqual(config.decrypt_password(), STRONG_PASSWORD)
        self.assertEqual(config.masked_password, "••••••••")

    def test_blank_password_keeps_saved_password(self):
        config = configure_smtp(username="mailer@example.com")
        config.set_password(STRONG_PASSWORD)
        config.save()
        original = config.password_ciphertext

        form = SMTPConfigurationForm(
            data=self.form_data(password=""), instance=config
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.password_ciphertext, original)
        self.assertEqual(saved.decrypt_password(), STRONG_PASSWORD)

    def test_clear_password_removes_it(self):
        config = configure_smtp(username="", is_enabled=False)
        config.set_password(STRONG_PASSWORD)
        config.save()

        form = SMTPConfigurationForm(
            data=self.form_data(
                username="",
                is_enabled="",
                password="",
                clear_password="on",
            ),
            instance=config,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertFalse(saved.has_password)

    def test_clear_password_blocked_while_enabled(self):
        config = configure_smtp(username="mailer@example.com")
        config.set_password(STRONG_PASSWORD)
        config.save()

        form = SMTPConfigurationForm(
            data=self.form_data(
                password="", clear_password="on", username=""
            ),
            instance=config,
        )
        # Username removed, but outgoing email is still enabled.
        self.assertFalse(form.is_valid())
        self.assertIn("clear_password", form.errors)


# ---------------------------------------------------------------------------
# Mailer
# ---------------------------------------------------------------------------
@override_settings(
    EMAIL_ENCRYPTION_KEY=TEST_KEY,
    EMAIL_MANAGER_TRANSPORT="django",
    EMAIL_MANAGER_AUTO_RETRIES=0,
    EMAIL_MANAGER_RETRY_DELAY=0,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="no-reply@example.com",
)
class MailerTests(TestCase):
    def setUp(self):
        configure_smtp()

    def test_successful_test_email_uses_in_memory_backend(self):
        log = send_test_email("recipient@example.com")
        self.assertEqual(log.status, EmailLog.STATUS_SENT)
        self.assertEqual(log.event, "test_email")
        self.assertTrue(log.message_id)
        self.assertEqual(log.attempts, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["recipient@example.com"])

    def test_failed_test_email_records_sanitised_error(self):
        config = SMTPConfiguration.load()
        config.set_password(STRONG_PASSWORD)
        config.username = "mailer@example.com"
        config.save()

        error = smtplib.SMTPAuthenticationError(535, b"bad credentials")
        with patch("email_manager.mailer._deliver", side_effect=error):
            log = send_test_email("recipient@example.com")

        self.assertEqual(log.status, EmailLog.STATUS_FAILED)
        self.assertIn("rejected the username", log.error_summary)
        self.assertNotIn(STRONG_PASSWORD, log.error_summary)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_template_email_creates_log_and_message(self):
        template = EmailTemplate.objects.get(key="customer_enquiry_acknowledgement")
        log = send_template_email(
            template=template,
            event="new_enquiry_customer",
            recipient="customer@example.com",
            recipient_name="Customer",
            context=sample_context(),
        )
        self.assertEqual(log.status, EmailLog.STATUS_SENT)
        self.assertEqual(log.template_key, template.key)
        self.assertEqual(log.template_name, template.name)
        self.assertIn("SPC-DEMO01", log.subject)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("text/html", [part[1] for part in mail.outbox[0].alternatives])
        self.assertTrue(
            any("Aarav Sharma" in body for body in (mail.outbox[0].body,))
        )

    def test_template_is_skipped_when_outgoing_email_disabled(self):
        config = configure_smtp(is_enabled=False)
        template = EmailTemplate.objects.get(key="customer_enquiry_acknowledgement")
        log = send_template_email(
            template=template,
            event="new_enquiry_customer",
            recipient="customer@example.com",
            context=sample_context(),
        )
        self.assertEqual(log.status, EmailLog.STATUS_SKIPPED)
        self.assertIn("disabled", log.error_summary)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(
            EmailLog.objects.filter(recipient="customer@example.com").count(), 1
        )

    def test_inactive_template_is_skipped(self):
        template = EmailTemplate.objects.get(key="customer_enquiry_acknowledgement")
        template.is_active = False
        template.save(update_fields=["is_active", "updated_at"])
        log = send_template_email(
            template=template,
            event="new_enquiry_customer",
            recipient="customer@example.com",
            context=sample_context(),
        )
        self.assertEqual(log.status, EmailLog.STATUS_SKIPPED)
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_recipient_creates_failed_log(self):
        log = send_template_email(
            template=None,
            event="test_email",
            recipient="not-an-email",
            context={},
        )
        self.assertEqual(log.status, EmailLog.STATUS_FAILED)
        self.assertIn("not valid", log.error_summary)

    def test_dedupe_key_prevents_duplicate_sends(self):
        template = EmailTemplate.objects.get(key="customer_enquiry_acknowledgement")
        first = send_template_email(
            template=template,
            event="new_enquiry_customer",
            recipient="customer@example.com",
            context=sample_context(),
            dedupe_key="event:1:customer@example.com",
        )
        second = send_template_email(
            template=template,
            event="new_enquiry_customer",
            recipient="customer@example.com",
            context=sample_context(),
            dedupe_key="event:1:customer@example.com",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(len(mail.outbox), 1)

    def test_retry_increments_attempts_and_uses_same_log(self):
        template = EmailTemplate.objects.get(key="customer_enquiry_acknowledgement")
        enquiry = Enquiry.objects.create(
            name="Retry Customer",
            email="customer@example.com",
            phone="+91 98765 43210",
            message="Please send a quote for a control panel.",
        )
        error = smtplib.SMTPServerDisconnected("gone")
        with patch("email_manager.mailer._deliver", side_effect=error):
            log = send_template_email(
                template=template,
                event="new_enquiry_customer",
                recipient="customer@example.com",
                context=sample_context(),
                enquiry=enquiry,
            )
        self.assertEqual(log.status, EmailLog.STATUS_FAILED)
        self.assertEqual(log.attempts, 1)

        with patch("email_manager.mailer._deliver", return_value=1) as deliver:
            from .notifications import retry_email_log

            retried = retry_email_log(log)
        self.assertEqual(retried.pk, log.pk)
        self.assertEqual(retried.status, EmailLog.STATUS_SENT)
        self.assertEqual(retried.attempts, 2)
        deliver.assert_called_once()
        self.assertEqual(EmailLog.objects.count(), 1)

    def test_error_sanitiser_maps_common_failures(self):
        self.assertIn(
            "rejected the username",
            sanitize_smtp_error(smtplib.SMTPAuthenticationError(535, b"x")),
        )
        self.assertIn(
            "timeout", sanitize_smtp_error(TimeoutError()).lower()
        )
        self.assertIn(
            "secure connection",
            sanitize_smtp_error(__import__("ssl").SSLError("bad")).lower(),
        )
        self.assertEqual(
            sanitize_smtp_error(ValueError("Bad configuration")),
            "Bad configuration",
        )


# ---------------------------------------------------------------------------
# Notification integration
# ---------------------------------------------------------------------------
@override_settings(
    EMAIL_ENCRYPTION_KEY=TEST_KEY,
    EMAIL_MANAGER_TRANSPORT="django",
    EMAIL_MANAGER_AUTO_RETRIES=0,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="no-reply@example.com",
)
class NotificationTests(TestCase):
    def setUp(self):
        configure_smtp()
        self.enquiry = Enquiry.objects.create(
            name="Test Customer",
            company="Test Co",
            email="customer@example.com",
            phone="+91 98765 43210",
            message="Please quote for two air filters.",
        )

    def test_new_enquiry_sends_acknowledgement_and_admin_alert(self):
        logs = notify_new_enquiry(self.enquiry)
        self.assertEqual(len(logs), 2)
        self.assertEqual(len(mail.outbox), 2)
        recipients = {log.recipient for log in logs}
        self.assertEqual(
            recipients,
            {"customer@example.com", "admin@example.com"},
        )
        self.assertTrue(
            all(log.status == EmailLog.STATUS_SENT for log in logs)
        )

    def test_duplicate_notification_is_not_sent_twice(self):
        notify_new_enquiry(self.enquiry)
        notify_new_enquiry(self.enquiry)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(EmailLog.objects.count(), 2)

    def test_product_enquiry_uses_product_template(self):
        from products.models import Category, Product

        category = Category.objects.create(name="Filters")
        product = Product.objects.create(
            name="Air Filter",
            category=category,
            sku="AF-1",
        )
        self.enquiry.product = product
        self.enquiry.save(update_fields=["product", "updated_at"])

        logs = notify_new_enquiry(self.enquiry)
        status_log = next(
            log for log in logs if log.template_key == "product_enquiry_notification"
        )
        self.assertIsNotNone(status_log)
        self.enquiry.refresh_from_db()
        self.assertIn("Air Filter", self.enquiry.product_label)

    def test_disabled_rule_sends_nothing(self):
        rule = NotificationRule.objects.get(event="new_enquiry_customer")
        rule.is_enabled = False
        rule.save(update_fields=["is_enabled", "updated_at"])
        logs = notify_new_enquiry(self.enquiry)
        self.assertEqual(len(logs), 1)  # Admin rule still enabled.
        self.assertEqual({log.recipient for log in logs}, {"admin@example.com"})

    def test_dispatch_returns_none_when_recipient_is_missing(self):
        config = SMTPConfiguration.load()
        config.admin_notification_email = ""
        config.save()
        with patch(
            "email_manager.notifications._site_details",
            return_value={"site_name": "SPC", "contact_email": ""},
        ):
            log = dispatch_event(
                NotificationRule.EVENT_NEW_ENQUIRY_ADMIN,
                enquiry=self.enquiry,
            )
        self.assertIsNone(log)

    def test_enquiry_is_kept_when_email_raises(self):
        with patch(
            "email_manager.notifications.send_template_email",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            response = self.client.post(
                reverse("enquiries:create"),
                {
                    "name": "Website Visitor",
                    "company": "Visitor Co",
                    "email": "visitor@example.com",
                    "phone": "+91 90000 00000",
                    "product": "",
                    "message": "We need a quotation for a control panel.",
                    "consent": "on",
                    "website": "",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Enquiry.objects.count(), 2)
        self.assertTrue(
            Enquiry.objects.filter(email="visitor@example.com").exists()
        )

    def test_enquiry_is_kept_when_dispatch_raises(self):
        with patch(
            "email_manager.notifications.dispatch_event",
            side_effect=RuntimeError("boom"),
        ):
            response = self.client.post(
                reverse("enquiries:create"),
                {
                    "name": "Second Visitor",
                    "company": "",
                    "email": "second@example.com",
                    "phone": "+91 90000 00001",
                    "product": "",
                    "message": "Please share your product catalogue.",
                    "consent": "on",
                    "website": "",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Enquiry.objects.filter(email="second@example.com").exists())


# ---------------------------------------------------------------------------
# Dashboard permissions, masking and CSRF
# ---------------------------------------------------------------------------
@override_settings(EMAIL_ENCRYPTION_KEY=TEST_KEY, DEBUG=True)
class DashboardPermissionTests(TestCase):
    def setUp(self):
        self.superuser = make_user(username="root", superuser=True)
        self.no_perm_staff = make_user(username="plain", email="plain@example.com")
        self.log_viewer = grant(
            make_user(username="logs", email="logs@example.com"), "view_emaillog"
        )
        self.smtp_manager = grant(
            make_user(username="smtp", email="smtp@example.com"), "manage_smtp"
        )

    def test_anonymous_is_redirected_to_login(self):
        from django.conf import settings

        response = self.client.get(reverse("dashboard:email_smtp_settings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(settings.LOGIN_URL, response["Location"])

    def test_staff_without_permission_is_forbidden(self):
        self.client.force_login(self.no_perm_staff)
        response = self.client.get(reverse("dashboard:email_smtp_settings"))
        self.assertEqual(response.status_code, 403)

    def test_log_viewer_cannot_open_smtp_settings(self):
        self.client.force_login(self.log_viewer)
        self.assertEqual(
            self.client.get(reverse("dashboard:email_smtp_settings")).status_code,
            403,
        )

    def test_smtp_permission_allows_settings_page(self):
        self.client.force_login(self.smtp_manager)
        response = self.client.get(reverse("dashboard:email_smtp_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SMTP settings")

    def test_log_viewer_cannot_send_test_email(self):
        self.client.force_login(self.log_viewer)
        self.assertEqual(
            self.client.get(reverse("dashboard:email_test")).status_code, 403
        )

    def test_log_viewer_can_read_logs(self):
        self.client.force_login(self.log_viewer)
        response = self.client.get(reverse("dashboard:email_log_list"))
        self.assertEqual(response.status_code, 200)

    def test_smtp_manager_can_see_overview(self):
        self.client.force_login(self.smtp_manager)
        response = self.client.get(reverse("dashboard:email_overview"))
        self.assertEqual(response.status_code, 200)

    def test_csrf_is_enforced_on_post(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.smtp_manager)
        response = client.post(reverse("dashboard:email_test"), {"recipient": "a@b.com"})
        self.assertEqual(response.status_code, 403)

    def test_saved_password_is_not_rendered(self):
        config = configure_smtp(username="mailer@example.com")
        config.set_password(STRONG_PASSWORD)
        config.save()

        self.client.force_login(self.superuser)
        response = self.client.get(reverse("dashboard:email_smtp_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, STRONG_PASSWORD)
        self.assertNotContains(response, config.password_ciphertext)
        self.assertContains(response, "••••••••")

    def test_superuser_can_update_settings(self):
        config = configure_smtp(is_enabled=False)
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("dashboard:email_smtp_settings"),
            {
                "preset": "custom",
                "host": "smtp.example.org",
                "port": "465",
                "username": "mailer@example.org",
                "sender_email": "no-reply@example.org",
                "sender_name": "SPC",
                "use_ssl": "on",
                "timeout": "30",
                "reply_to": "",
                "admin_notification_email": "admin@example.org",
                "log_retention_days": "90",
                "password": STRONG_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 302)
        config.refresh_from_db()
        self.assertEqual(config.host, "smtp.example.org")
        self.assertEqual(config.port, 465)
        self.assertTrue(config.use_ssl)
        self.assertFalse(config.use_tls)
        self.assertNotIn(STRONG_PASSWORD, config.password_ciphertext)
        self.assertEqual(config.decrypt_password(), STRONG_PASSWORD)

    def test_superuser_can_open_every_email_manager_page(self):
        self.client.force_login(self.superuser)
        template = EmailTemplate.objects.get(key="customer_enquiry_acknowledgement")
        log = EmailLog.objects.create(
            recipient="customer@example.com",
            sender="no-reply@example.com",
            subject="Test",
            status=EmailLog.STATUS_SENT,
        )
        names = [
            reverse("dashboard:email_overview"),
            reverse("dashboard:email_smtp_settings"),
            reverse("dashboard:email_test"),
            reverse("dashboard:email_template_list"),
            reverse("dashboard:email_template_create"),
            reverse("dashboard:email_template_preview", args=[template.pk]),
            reverse("dashboard:email_log_list"),
            reverse("dashboard:email_log_detail", args=[log.pk]),
            reverse("dashboard:email_rules"),
        ]
        for url in names:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_template_used_by_a_rule_cannot_be_deleted(self):
        template = EmailTemplate.objects.get(key="customer_enquiry_acknowledgement")
        template.is_system = False
        template.save(update_fields=["is_system", "updated_at"])
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("dashboard:email_template_delete", args=[template.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EmailTemplate.objects.filter(pk=template.pk).exists())


# ---------------------------------------------------------------------------
# Seeding and email log behaviour
# ---------------------------------------------------------------------------
class SeedingTests(TestCase):
    def test_defaults_are_idempotent(self):
        # Rules protect their templates, so remove the rules first.
        NotificationRule.objects.all().delete()
        EmailTemplate.objects.all().delete()
        created_templates, created_rules = ensure_defaults()
        self.assertEqual(created_templates, len(DEFAULT_TEMPLATES))
        self.assertEqual(created_rules, 9)
        again = ensure_defaults()
        self.assertEqual(again, (0, 0))
        self.assertEqual(EmailTemplate.objects.count(), len(DEFAULT_TEMPLATES))
        self.assertEqual(NotificationRule.objects.count(), 9)
        self.assertEqual(
            EmailTemplate.objects.filter(is_system=True).count(),
            len(DEFAULT_TEMPLATES),
        )

    def test_required_templates_exist(self):
        keys = set(EmailTemplate.objects.values_list("key", flat=True))
        for key in {
            "new_enquiry_notification",
            "customer_enquiry_acknowledgement",
            "product_enquiry_notification",
            "admin_new_lead_alert",
            "contact_form_confirmation",
            "password_reset_email",
        }:
            self.assertIn(key, keys)


class EmailLogBehaviourTests(TestCase):
    def test_status_helpers(self):
        log = EmailLog.objects.create(
            recipient="person@example.com",
            status=EmailLog.STATUS_SENT,
        )
        self.assertTrue(log.is_successful)
        self.assertEqual(log.status_css, "sent")
        self.assertIn("accepted", log.status_explanation.lower())
        log.status = EmailLog.STATUS_FAILED
        self.assertFalse(log.is_successful)
        self.assertEqual(log.status_css, "failed")

    def test_only_rebuildable_failures_can_be_retried(self):
        log = EmailLog.objects.create(
            recipient="person@example.com",
            status=EmailLog.STATUS_FAILED,
            attempts=1,
            template_key="customer_enquiry_acknowledgement",
        )
        self.assertFalse(log.can_retry)  # No linked enquiry.
        enquiry = Enquiry.objects.create(
            name="Retry Customer",
            email="retry@example.com",
            message="Please send a quote for a control panel.",
        )
        log.enquiry = enquiry
        log.save(update_fields=["enquiry", "updated_at"])
        self.assertTrue(log.can_retry)

        log.attempts = 3
        log.save(update_fields=["attempts", "updated_at"])
        self.assertFalse(log.can_retry)

    def test_prune_respects_retention(self):
        from .mailer import prune_email_logs

        old = EmailLog.objects.create(
            recipient="old@example.com", status=EmailLog.STATUS_SENT
        )
        EmailLog.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=400)
        )
        EmailLog.objects.create(
            recipient="new@example.com", status=EmailLog.STATUS_SENT
        )
        deleted = prune_email_logs(180)
        self.assertEqual(deleted, 1)
        self.assertTrue(EmailLog.objects.filter(recipient="new@example.com").exists())


# ---------------------------------------------------------------------------
# Password reset routing
# ---------------------------------------------------------------------------
@override_settings(
    EMAIL_ENCRYPTION_KEY=TEST_KEY,
    EMAIL_MANAGER_TRANSPORT="django",
    EMAIL_MANAGER_AUTO_RETRIES=0,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PasswordResetTests(TestCase):
    def test_reset_uses_email_manager_template_when_available(self):
        configure_smtp()
        user = make_user(username="reset", email="reset@example.com")
        reset_url = "https://example.com/admin/password-reset/abc/def/"
        from .notifications import send_password_reset_email

        log = send_password_reset_email(user, reset_url)
        self.assertIsNotNone(log)
        self.assertEqual(log.status, EmailLog.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reset@example.com"])
        combined = mail.outbox[0].body + str(mail.outbox[0].alternatives)
        self.assertIn(reset_url, combined)

    def test_reset_falls_back_when_rule_is_disabled(self):
        configure_smtp()
        rule = NotificationRule.objects.get(event="password_reset")
        rule.is_enabled = False
        rule.save(update_fields=["is_enabled", "updated_at"])
        user = make_user(username="reset2", email="reset2@example.com")
        from .notifications import send_password_reset_email

        self.assertIsNone(
            send_password_reset_email(
                user, "https://example.com/admin/password-reset/abc/def/"
            )
        )
        self.assertEqual(len(mail.outbox), 0)
