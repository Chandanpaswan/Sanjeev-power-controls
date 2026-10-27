"""Default templates, notification rules and idempotent seeding.

These templates intentionally use only the approved ``{{ placeholder }}``
syntax. They contain no Django template tags, so the restricted validator in
:mod:`email_manager.templating` accepts them.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

BRAND_NAVY = "#0B1F3A"
BRAND_BLUE = "#1F5FA8"
BRAND_RED = "#C8102E"
BRAND_STEEL = "#5B6B7D"
BRAND_BG = "#F4F7FA"


def _layout(inner: str) -> str:
    """Wrap email content in the shared brand shell.

    Inline styles are used because many email clients strip external CSS and
    the sanitiser removes ``<link>`` elements.
    """
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BRAND_BG};padding:24px 0;">
  <tr>
    <td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;color:#1F2937;">
        <tr>
          <td style="background:{BRAND_NAVY};padding:22px 28px;">
            <div style="font-size:20px;font-weight:bold;color:#ffffff;letter-spacing:.02em;">{{{{ site_name }}}}</div>
            <div style="font-size:12px;color:#C9D8E7;margin-top:4px;">Powering Performance. Ensuring Reliability.</div>
          </td>
        </tr>
        <tr>
          <td style="height:4px;background:{BRAND_RED};font-size:0;line-height:0;">&nbsp;</td>
        </tr>
        <tr>
          <td style="padding:28px;">
{inner}
          </td>
        </tr>
        <tr>
          <td style="padding:18px 28px;background:#F8FAFC;border-top:1px solid #E5EAF0;font-size:12px;line-height:1.6;color:{BRAND_STEEL};">
            <p style="margin:0 0 6px;">This message was sent by {{{{ site_name }}}}.</p>
            <p style="margin:0;">Questions? Reply to this email or contact <a href="mailto:{{{{ contact_email }}}}" style="color:{BRAND_BLUE};">{{{{ contact_email }}}}</a>.</p>
            <p style="margin:8px 0 0;">&copy; {{{{ current_year }}}} {{{{ site_name }}}}. All rights reserved.</p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""


def _detail_rows(rows: list[tuple[str, str]]) -> str:
    html = []
    for label, value in rows:
        html.append(
            f"""\
            <tr>
              <td style="padding:7px 0;width:160px;vertical-align:top;font-size:13px;color:{BRAND_STEEL};">{label}</td>
              <td style="padding:7px 0;vertical-align:top;font-size:14px;color:#1F2937;">{value}</td>
            </tr>"""
        )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;">'
        + "".join(html)
        + "</table>"
    )


def _button(label: str, url_expr: str) -> str:
    return f"""\
<p style="margin:22px 0 0;">
  <a href="{url_expr}" style="display:inline-block;background:{BRAND_BLUE};color:#ffffff;text-decoration:none;font-size:14px;font-weight:bold;padding:12px 22px;border-radius:8px;">{label}</a>
</p>"""


GENERAL_ACK_TEXT = """\
Hello {{ customer_name }},

Thank you for contacting {{ site_name }}. We have received your enquiry and
our team will review it shortly.

Enquiry reference: {{ enquiry_id }}
Product: {{ product_name }}
Submitted message:
{{ enquiry_message }}

If you need to add information, reply to this email or contact
{{ contact_email }}.

Kind regards,
{{ site_name }}
{{ current_year }}
"""

GENERAL_ACK_HTML = _layout(
    f"""\
<h1 style="margin:0 0 12px;font-size:22px;line-height:1.3;color:{BRAND_NAVY};">Thank you, {{{{ customer_name }}}}</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.6;">We have received your enquiry and our team will review it shortly. Keep the reference below for follow-up.</p>
<p style="margin:0 0 20px;font-size:16px;font-weight:bold;color:{BRAND_NAVY};">Reference: {{{{ enquiry_id }}}}</p>
{_detail_rows([
    ("Product", "{{ product_name }}"),
    ("Your message", "{{ enquiry_message }}"),
])}
<p style="margin:20px 0 0;font-size:14px;line-height:1.6;">If you need to add information, reply to this email or contact <a href="mailto:{{{{ contact_email }}}}" style="color:{BRAND_BLUE};">{{{{ contact_email }}}}</a>.</p>
<p style="margin:16px 0 0;font-size:14px;line-height:1.6;">Kind regards,<br><strong>{{{{ site_name }}}}</strong></p>"""
)

GENERAL_ADMIN_TEXT = """\
New customer enquiry {{ enquiry_id }}

Customer: {{ customer_name }}
Company: {{ company_name }}
Email: {{ customer_email }}
Phone: {{ customer_phone }}
Product: {{ product_name }}
Status: {{ enquiry_status }}

Message:
{{ enquiry_message }}

Open in the dashboard: {{ enquiry_url }}
"""

GENERAL_ADMIN_HTML = _layout(
    f"""\
<h1 style="margin:0 0 6px;font-size:21px;color:{BRAND_NAVY};">New customer enquiry</h1>
<p style="margin:0 0 18px;font-size:14px;color:{BRAND_STEEL};">Reference <strong style="color:{BRAND_NAVY};">{{{{ enquiry_id }}}}</strong> · {{{{ enquiry_status }}}}</p>
{_detail_rows([
    ("Customer", "{{ customer_name }}"),
    ("Company", "{{ company_name }}"),
    ("Email", '<a href="mailto:{{ customer_email }}" style="color:#1F5FA8;">{{ customer_email }}</a>'),
    ("Phone", "{{ customer_phone }}"),
    ("Product", "{{ product_name }}"),
])}
<div style="margin:20px 0 0;padding:16px;background:{BRAND_BG};border-left:4px solid {BRAND_BLUE};border-radius:6px;font-size:14px;line-height:1.6;white-space:pre-line;">{{{{ enquiry_message }}}}</div>
{_button("Open enquiry in dashboard", "{{ enquiry_url }}")}
<p style="margin:16px 0 0;font-size:12px;color:{BRAND_STEEL};">This notification contains customer data. Share it only with authorised staff.</p>"""
)

PRODUCT_ADMIN_TEXT = """\
Product enquiry {{ enquiry_id }} — {{ product_name }}

Customer: {{ customer_name }}
Company: {{ company_name }}
Email: {{ customer_email }}
Phone: {{ customer_phone }}
Status: {{ enquiry_status }}

Message:
{{ enquiry_message }}

Open in the dashboard: {{ enquiry_url }}
"""

PRODUCT_ADMIN_HTML = _layout(
    f"""\
<h1 style="margin:0 0 6px;font-size:21px;color:{BRAND_NAVY};">Product enquiry</h1>
<p style="margin:0 0 18px;font-size:14px;color:{BRAND_STEEL};">Reference <strong style="color:{BRAND_NAVY};">{{{{ enquiry_id }}}}</strong> · {{{{ enquiry_status }}}}</p>
<div style="margin:0 0 18px;padding:14px 16px;background:#EAF2FB;border-radius:8px;font-size:15px;font-weight:bold;color:{BRAND_NAVY};">{{{{ product_name }}}}</div>
{_detail_rows([
    ("Customer", "{{ customer_name }}"),
    ("Company", "{{ company_name }}"),
    ("Email", '<a href="mailto:{{ customer_email }}" style="color:#1F5FA8;">{{ customer_email }}</a>'),
    ("Phone", "{{ customer_phone }}"),
])}
<div style="margin:20px 0 0;padding:16px;background:{BRAND_BG};border-left:4px solid {BRAND_RED};border-radius:6px;font-size:14px;line-height:1.6;white-space:pre-line;">{{{{ enquiry_message }}}}</div>
{_button("Open product enquiry", "{{ enquiry_url }}")}"""
)

ADMIN_ALERT_TEXT = """\
New lead {{ enquiry_id }}: {{ customer_name }}

Product: {{ product_name }}
Email: {{ customer_email }}
Phone: {{ customer_phone }}

Open: {{ enquiry_url }}
"""

ADMIN_ALERT_HTML = _layout(
    f"""\
<h1 style="margin:0 0 10px;font-size:21px;color:{BRAND_NAVY};">New lead received</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.6;"><strong>{{{{ customer_name }}}}</strong> submitted enquiry <strong>{{{{ enquiry_id }}}}</strong> for <strong>{{{{ product_name }}}}</strong>.</p>
{_detail_rows([
    ("Email", '<a href="mailto:{{ customer_email }}" style="color:#1F5FA8;">{{ customer_email }}</a>'),
    ("Phone", "{{ customer_phone }}"),
    ("Company", "{{ company_name }}"),
])}
{_button("Review the lead", "{{ enquiry_url }}")}"""
)

CONTACT_TEXT = """\
Thank you for contacting {{ site_name }}

Hello {{ customer_name }},

We received your message and will respond as soon as possible.

Your reference is {{ enquiry_id }}.

Kind regards,
{{ site_name }}
{{ current_year }}
"""

CONTACT_HTML = _layout(
    f"""\
<h1 style="margin:0 0 12px;font-size:22px;color:{BRAND_NAVY};">Thank you for contacting us</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.6;">Hello {{{{ customer_name }}}}, we received your message and will respond as soon as possible.</p>
<p style="margin:0 0 18px;font-size:16px;font-weight:bold;color:{BRAND_NAVY};">Reference: {{{{ enquiry_id }}}}</p>
<p style="margin:0;font-size:14px;line-height:1.6;">For urgent requirements, call the number listed on our website or reply to this email.</p>
<p style="margin:16px 0 0;font-size:14px;line-height:1.6;">Kind regards,<br><strong>{{{{ site_name }}}}</strong></p>"""
)

PASSWORD_RESET_TEXT = """\
Reset your {{ site_name }} dashboard password

A password reset was requested for this email address. Open the secure link
below to choose a new password:

{{ reset_url }}

The link can be used once and expires automatically. If you did not request a
password reset, you can ignore this email — your current password stays active.

{{ site_name }}
{{ current_year }}
"""

PASSWORD_RESET_HTML = _layout(
    f"""\
<h1 style="margin:0 0 12px;font-size:22px;color:{BRAND_NAVY};">Reset your dashboard password</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.6;">A password reset was requested for this email address. Use the secure button below to choose a new password. The link can be used once and expires automatically.</p>
{_button("Choose a new password", "{{ reset_url }}")}
<p style="margin:18px 0 0;font-size:13px;line-height:1.6;color:{BRAND_STEEL};">If you did not request a reset, ignore this email. Your current password stays active.</p>
<p style="margin:16px 0 0;font-size:12px;line-height:1.6;color:{BRAND_STEEL};word-break:break-all;">If the button does not work, copy this link into your browser:<br>{{{{ reset_url }}}}</p>"""
)

ASSIGNED_TEXT = """\
Enquiry {{ enquiry_id }} assigned to {{ assigned_to }}

Customer: {{ customer_name }}
Product: {{ product_name }}
Status: {{ enquiry_status }}

Open: {{ enquiry_url }}
"""

ASSIGNED_HTML = _layout(
    f"""\
<h1 style="margin:0 0 10px;font-size:21px;color:{BRAND_NAVY};">Enquiry assigned</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.6;">Enquiry <strong>{{{{ enquiry_id }}}}</strong> has been assigned to <strong>{{{{ assigned_to }}}}</strong>.</p>
{_detail_rows([
    ("Customer", "{{ customer_name }}"),
    ("Product", "{{ product_name }}"),
    ("Status", "{{ enquiry_status }}"),
])}
{_button("Open the enquiry", "{{ enquiry_url }}")}"""
)

STATUS_TEXT = """\
Enquiry {{ enquiry_id }} status changed

{{ old_status }} → {{ new_status }}

Customer: {{ customer_name }}
Product: {{ product_name }}

Open: {{ enquiry_url }}
"""

STATUS_HTML = _layout(
    f"""\
<h1 style="margin:0 0 10px;font-size:21px;color:{BRAND_NAVY};">Enquiry status changed</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.6;">Enquiry <strong>{{{{ enquiry_id }}}}</strong> moved from <strong>{{{{ old_status }}}}</strong> to <strong>{{{{ new_status }}}}</strong>.</p>
{_detail_rows([
    ("Customer", "{{ customer_name }}"),
    ("Product", "{{ product_name }}"),
    ("Current status", "{{ enquiry_status }}"),
])}
{_button("Open the enquiry", "{{ enquiry_url }}")}"""
)

FOLLOW_UP_TEXT = """\
Follow-up due for enquiry {{ enquiry_id }}

Customer: {{ customer_name }}
Product: {{ product_name }}
Status: {{ enquiry_status }}

Open: {{ enquiry_url }}
"""

FOLLOW_UP_HTML = _layout(
    f"""\
<h1 style="margin:0 0 10px;font-size:21px;color:{BRAND_NAVY};">Follow-up due</h1>
<p style="margin:0 0 16px;font-size:15px;line-height:1.6;">The follow-up date for enquiry <strong>{{{{ enquiry_id }}}}</strong> has arrived. Contact the customer and update the status.</p>
{_detail_rows([
    ("Customer", "{{ customer_name }}"),
    ("Product", "{{ product_name }}"),
    ("Status", "{{ enquiry_status }}"),
])}
{_button("Open the enquiry", "{{ enquiry_url }}")}"""
)


DEFAULT_TEMPLATES = [
    {
        "key": "new_enquiry_notification",
        "name": "New Customer Enquiry Notification",
        "audience": "admin",
        "description": (
            "Internal notification with the full customer enquiry details. "
            "Used for general (non-product) enquiries."
        ),
        "subject": "New customer enquiry {{ enquiry_id }} — {{ customer_name }}",
        "html_body": GENERAL_ADMIN_HTML,
        "text_body": GENERAL_ADMIN_TEXT,
        "is_system": True,
    },
    {
        "key": "customer_enquiry_acknowledgement",
        "name": "Customer Enquiry Acknowledgement",
        "audience": "customer",
        "description": (
            "Automatic acknowledgement sent to the customer who submitted the "
            "public enquiry form."
        ),
        "subject": "We received your enquiry {{ enquiry_id }} — {{ site_name }}",
        "html_body": GENERAL_ACK_HTML,
        "text_body": GENERAL_ACK_TEXT,
        "is_system": True,
    },
    {
        "key": "product_enquiry_notification",
        "name": "Product Enquiry Notification",
        "audience": "admin",
        "description": (
            "Internal notification for enquiries linked to a specific product."
        ),
        "subject": "Product enquiry {{ enquiry_id }} — {{ product_name }}",
        "html_body": PRODUCT_ADMIN_HTML,
        "text_body": PRODUCT_ADMIN_TEXT,
        "is_system": True,
    },
    {
        "key": "admin_new_lead_alert",
        "name": "Admin New Lead Alert",
        "audience": "admin",
        "description": (
            "Short alert for the configured administrator. Disabled by default "
            "to avoid duplicating the detailed new-enquiry notification."
        ),
        "subject": "New lead {{ enquiry_id }}: {{ customer_name }}",
        "html_body": ADMIN_ALERT_HTML,
        "text_body": ADMIN_ALERT_TEXT,
        "is_system": True,
    },
    {
        "key": "contact_form_confirmation",
        "name": "Contact Form Confirmation",
        "audience": "customer",
        "description": (
            "Confirmation for the general contact form. Disabled by default so "
            "customers do not receive two acknowledgements."
        ),
        "subject": "Thank you for contacting {{ site_name }}",
        "html_body": CONTACT_HTML,
        "text_body": CONTACT_TEXT,
        "is_system": True,
    },
    {
        "key": "password_reset_email",
        "name": "Password Reset Email",
        "audience": "system",
        "description": (
            "Uses Django's secure, single-use password reset token workflow. "
            "The reset link is generated by Django and is never stored here."
        ),
        "subject": "Reset your {{ site_name }} dashboard password",
        "html_body": PASSWORD_RESET_HTML,
        "text_body": PASSWORD_RESET_TEXT,
        "is_system": True,
    },
    {
        "key": "lead_assigned_alert",
        "name": "Lead Assignment Alert",
        "audience": "admin",
        "description": (
            "Optional internal notification when an enquiry is assigned to a "
            "staff member. Disabled by default."
        ),
        "subject": "Enquiry {{ enquiry_id }} assigned to {{ assigned_to }}",
        "html_body": ASSIGNED_HTML,
        "text_body": ASSIGNED_TEXT,
        "is_system": True,
    },
    {
        "key": "enquiry_status_changed",
        "name": "Enquiry Status Changed",
        "audience": "admin",
        "description": (
            "Optional internal notification when an enquiry status changes. "
            "Disabled by default."
        ),
        "subject": "Enquiry {{ enquiry_id }}: {{ old_status }} → {{ new_status }}",
        "html_body": STATUS_HTML,
        "text_body": STATUS_TEXT,
        "is_system": True,
    },
    {
        "key": "follow_up_reminder",
        "name": "Follow-up Reminder",
        "audience": "admin",
        "description": (
            "Optional reminder for enquiries whose follow-up date is due. "
            "Send with the send_follow_up_reminders command or a scheduler. "
            "Disabled by default."
        ),
        "subject": "Follow-up due for enquiry {{ enquiry_id }}",
        "html_body": FOLLOW_UP_HTML,
        "text_body": FOLLOW_UP_TEXT,
        "is_system": True,
    },
]


DEFAULT_RULES = [
    {
        "event": "new_enquiry_customer",
        "template_key": "customer_enquiry_acknowledgement",
        "recipient": "customer",
        "is_enabled": True,
        "description": "Acknowledge every enquiry submitted through the website.",
    },
    {
        "event": "new_enquiry_admin",
        "template_key": "new_enquiry_notification",
        "recipient": "admin",
        "is_enabled": True,
        "description": "Notify the administrator about general enquiries.",
    },
    {
        "event": "product_enquiry_admin",
        "template_key": "product_enquiry_notification",
        "recipient": "admin",
        "is_enabled": True,
        "description": "Notify the administrator about product-specific enquiries.",
    },
    {
        "event": "admin_new_lead",
        "template_key": "admin_new_lead_alert",
        "recipient": "admin",
        "is_enabled": False,
        "description": (
            "Optional short alert in addition to the detailed notification."
        ),
    },
    {
        "event": "contact_confirmation",
        "template_key": "contact_form_confirmation",
        "recipient": "customer",
        "is_enabled": False,
        "description": (
            "Optional contact-form confirmation. Disabled to avoid a second "
            "acknowledgement."
        ),
    },
    {
        "event": "password_reset",
        "template_key": "password_reset_email",
        "recipient": "event_user",
        "is_enabled": True,
        "description": "Send the secure Django password reset link.",
    },
    {
        "event": "lead_assigned",
        "template_key": "lead_assigned_alert",
        "recipient": "assigned_staff",
        "is_enabled": False,
        "description": "Optional notification when an enquiry is assigned.",
    },
    {
        "event": "status_changed",
        "template_key": "enquiry_status_changed",
        "recipient": "admin",
        "is_enabled": False,
        "description": "Optional notification when an enquiry status changes.",
    },
    {
        "event": "follow_up_due",
        "template_key": "follow_up_reminder",
        "recipient": "admin",
        "is_enabled": False,
        "description": "Optional reminder for due follow-ups.",
    },
]


@transaction.atomic
def ensure_defaults(verbosity=0):
    """Create missing system templates and rules without overwriting edits.

    Returns a pair ``(created_templates, created_rules)``.
    """
    from .models import EmailTemplate, NotificationRule

    created_templates = 0
    templates = {}
    for item in DEFAULT_TEMPLATES:
        defaults = {key: value for key, value in item.items() if key != "key"}
        template, created = EmailTemplate.objects.get_or_create(
            key=item["key"], defaults=defaults
        )
        templates[item["key"]] = template
        if created:
            created_templates += 1

    created_rules = 0
    for item in DEFAULT_RULES:
        template = templates.get(item["template_key"])
        if not template:
            continue
        _, created = NotificationRule.objects.get_or_create(
            event=item["event"],
            defaults={
                "template": template,
                "recipient": item["recipient"],
                "is_enabled": item["is_enabled"],
                "description": item["description"],
            },
        )
        if created:
            created_rules += 1

    return created_templates, created_rules


def sample_context() -> dict:
    """Sample values used by template previews and test sends."""
    from django.conf import settings

    from core.models import SiteSettings

    try:
        site = SiteSettings.load()
        site_name = site.company_name
        contact_email = site.contact_email or "sales@example.com"
    except Exception:
        site_name = "Sanjeev Power Controls"
        contact_email = "sales@example.com"

    return {
        "customer_name": "Aarav Sharma",
        "customer_email": "aarav.sharma@example.com",
        "customer_phone": "+91 98765 43210",
        "company_name": "Sharma Engineering Works",
        "product_name": "DG Set Air Filter Element",
        "enquiry_id": "SPC-DEMO01",
        "enquiry_message": (
            "We need a quotation for two air filter elements for a 125 kVA "
            "DG set. Please confirm availability and lead time."
        ),
        "enquiry_status": "New",
        "enquiry_url": "http://localhost:8000/admin/enquiries/",
        "old_status": "New",
        "new_status": "Contacted",
        "assigned_to": "Sales Team",
        "site_name": site_name,
        "contact_email": contact_email,
        "admin_email": getattr(settings, "ADMIN_NOTIFICATION_EMAIL", "")
        or contact_email,
        "current_year": str(timezone.now().year),
        "reset_url": "http://localhost:8000/admin/password-reset/demo/demo-token/",
        "protocol": "http",
        "domain": "localhost:8000",
    }
