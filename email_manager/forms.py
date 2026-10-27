"""Dashboard forms for SMTP settings, templates, tests and notification rules."""
from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .crypto import SecretStorageError, encryption_key_configured
from .models import EmailTemplate, NotificationRule, SMTPConfiguration


def _style_widgets(form):
    for name, field in form.fields.items():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs.setdefault("class", "form-select")
        elif isinstance(widget, forms.Textarea):
            widget.attrs.setdefault("class", "form-control")
            widget.attrs.setdefault("rows", 14)
        else:
            widget.attrs.setdefault("class", "form-control")


class SMTPConfigurationForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        label="SMTP password / app password",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "class": "form-control",
                "placeholder": "Leave blank to keep the saved password",
            },
            render_value=False,
        ),
        help_text=(
            "Saved passwords are encrypted and never shown again. Leave this "
            "blank to keep the current password."
        ),
    )
    clear_password = forms.BooleanField(
        required=False,
        label="Remove the saved password",
        help_text=(
            "Tick this only when replacing or removing credentials. It takes "
            "effect when you save the form."
        ),
    )

    class Meta:
        model = SMTPConfiguration
        fields = [
            "preset",
            "host",
            "port",
            "username",
            "sender_email",
            "sender_name",
            "use_tls",
            "use_ssl",
            "timeout",
            "reply_to",
            "admin_notification_email",
            "is_enabled",
            "log_retention_days",
        ]
        widgets = {
            "preset": forms.Select(attrs={"data-smtp-preset": "1"}),
            "host": forms.TextInput(
                attrs={"placeholder": "smtp.example.com", "autocomplete": "off"}
            ),
            "username": forms.TextInput(
                attrs={"placeholder": "you@example.com", "autocomplete": "off"}
            ),
            "sender_email": forms.EmailInput(
                attrs={"placeholder": "no-reply@example.com"}
            ),
            "sender_name": forms.TextInput(
                attrs={"placeholder": "Sanjeev Power Controls"}
            ),
            "reply_to": forms.EmailInput(
                attrs={"placeholder": "sales@example.com"}
            ),
            "admin_notification_email": forms.EmailInput(
                attrs={"placeholder": "admin@example.com"}
            ),
            "log_retention_days": forms.NumberInput(attrs={"min": 7, "max": 3650}),
            "timeout": forms.NumberInput(attrs={"min": 5, "max": 120}),
            "port": forms.NumberInput(attrs={"min": 1, "max": 65535}),
        }
        labels = {
            "preset": "Provider preset",
            "host": "SMTP host",
            "port": "SMTP port",
            "username": "SMTP username",
            "sender_email": "Sender email address",
            "sender_name": "Sender display name",
            "is_enabled": "Enable outgoing email",
            "log_retention_days": "Email log retention (days)",
        }
        help_texts = {
            "preset": (
                "Presets fill the fields as a starting point. Review every "
                "value with your email provider before saving."
            ),
            "is_enabled": (
                "When disabled, notification emails are recorded as skipped "
                "and nothing is sent. Test messages can still be sent."
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        _style_widgets(self)
        # Never render the ciphertext or the last test details as editable fields.
        self.fields["password"].initial = ""
        if self.instance and self.instance.has_password:
            self.fields["password"].help_text = (
                "A password is saved (••••••••). Leave this blank to keep it, "
                "or tick “Remove the saved password” below."
            )
        self.fields["clear_password"].initial = False

    def clean(self):
        cleaned = super().clean()
        use_tls = cleaned.get("use_tls")
        use_ssl = cleaned.get("use_ssl")
        if use_tls and use_ssl:
            self.add_error(
                "use_ssl",
                "Choose either STARTTLS or SSL/TLS, not both. Use STARTTLS on "
                "port 587 or SSL/TLS on port 465.",
            )
        if cleaned.get("is_enabled"):
            if not (cleaned.get("host") or "").strip():
                self.add_error(
                    "host", "Enter the SMTP host before enabling outgoing email."
                )
            if not (cleaned.get("sender_email") or "").strip():
                self.add_error(
                    "sender_email",
                    "Enter the sender email address before enabling outgoing email.",
                )
        password = cleaned.get("password") or ""
        clear_password = cleaned.get("clear_password")
        if password and not encryption_key_configured():
            self.add_error(
                "password",
                "EMAIL_ENCRYPTION_KEY is not configured on the server, so the "
                "password cannot be encrypted. Ask the operator to set it.",
            )
        if clear_password:
            if cleaned.get("is_enabled"):
                self.add_error(
                    "clear_password",
                    "Disable outgoing email or enter a new password before "
                    "removing the saved password.",
                )
            if cleaned.get("username"):
                self.add_error(
                    "clear_password",
                    "Remove the username as well, or enter a new password.",
                )
        elif (
            (cleaned.get("username") or "").strip()
            and not password
            and not (self.instance and self.instance.has_password)
        ):
            self.add_error(
                "password",
                "Enter the SMTP password or app password for this username.",
            )
        return cleaned

    def _post_clean(self):
        # Encrypt before the model's full_clean() runs so the model can see that
        # a password will be present. The plaintext value never leaves memory.
        password = self.cleaned_data.get("password")
        if password:
            try:
                self.instance.set_password(password)
            except SecretStorageError as exc:
                self.add_error("password", str(exc))
                return
        super()._post_clean()

    def save(self, commit=True):
        obj = super().save(commit=False)
        password = self.cleaned_data.get("password") or ""
        if password:
            obj.set_password(password)
        elif self.cleaned_data.get("clear_password"):
            obj.clear_password()
        if self.user is not None and getattr(self.user, "pk", None):
            obj.updated_by = self.user
        if commit:
            obj.save()
        return obj


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = [
            "key",
            "name",
            "audience",
            "description",
            "subject",
            "html_body",
            "text_body",
            "is_active",
        ]
        widgets = {
            "key": forms.TextInput(
                attrs={
                    "placeholder": "customer_enquiry_acknowledgement",
                    "autocomplete": "off",
                }
            ),
            "name": forms.TextInput(
                attrs={"placeholder": "Customer Enquiry Acknowledgement"}
            ),
            "description": forms.Textarea(attrs={"rows": 2}),
            "subject": forms.TextInput(
                attrs={"placeholder": "We received your enquiry {{ enquiry_id }}"}
            ),
            "html_body": forms.Textarea(
                attrs={
                    "rows": 16,
                    "class": "form-control code-field",
                    "spellcheck": "false",
                }
            ),
            "text_body": forms.Textarea(
                attrs={
                    "rows": 12,
                    "class": "form-control code-field",
                    "spellcheck": "false",
                }
            ),
        }
        help_texts = {
            "key": (
                "Lowercase identifier used by notification rules. System "
                "templates keep a fixed key."
            ),
            "subject": "Approved placeholders such as {{ enquiry_id }} are allowed.",
            "html_body": (
                "Only approved placeholders are allowed. Django tags such as "
                "{% if %} are rejected, and customer values are escaped."
            ),
            "text_body": "Plain-text fallback. Placeholders are allowed.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_widgets(self)
        if self.instance and self.instance.pk and self.instance.is_system:
            self.fields["key"].disabled = True
            self.fields["key"].help_text = (
                "System template keys are fixed so notification rules keep working."
            )

    def clean_key(self):
        key = (self.cleaned_data.get("key") or "").strip().lower()
        if self.instance and self.instance.pk and self.instance.is_system:
            return self.instance.key
        return key


class NotificationRuleForm(forms.ModelForm):
    class Meta:
        model = NotificationRule
        fields = ["template", "is_enabled"]
        widgets = {
            "template": forms.Select(),
        }
        labels = {
            "template": "Email template",
            "is_enabled": "Rule enabled",
        }
        help_texts = {
            "template": (
                "Only active templates are used for notifications. You can "
                "prepare an inactive template and enable it later."
            ),
            "is_enabled": (
                "Disabling a rule stops new emails for this event. Existing "
                "logs are kept."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_widgets(self)
        self.fields["template"].queryset = EmailTemplate.objects.order_by(
            "name"
        )


class TestEmailForm(forms.Form):
    recipient = forms.EmailField(
        label="Send test email to",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        ),
        help_text=(
            "This sends a real message using the saved SMTP configuration. "
            "Use an address you can check."
        ),
    )


class TemplateTestForm(forms.Form):
    recipient = forms.EmailField(
        label="Send preview to",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        ),
        help_text=(
            "The email is rendered with sample data and sent to this address."
        ),
    )
