"""Restricted rendering and sanitising for administrator-edited email templates.

Django's template engine already prevents arbitrary Python execution, but the
dashboard only needs a small set of placeholders. We therefore reject template
tags (``{% ... %}``), unknown placeholders and unfamiliar filters. This keeps
administrator-edited content predictable and prevents someone from using
``{% include %}``/``{% load %}`` to read other files or enabled libraries.

All customer-supplied values are rendered with autoescaping enabled for HTML.
The rendered HTML is then passed through a conservative sanitiser that removes
scripts, embedded frames, form controls and event-handler attributes while
preserving normal email layout and inline styles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from django.template import Context, Engine
from django.utils.safestring import mark_safe

# The only context values an email template may reference.
APPROVED_PLACEHOLDERS: dict[str, str] = {
    "customer_name": "Name submitted with the enquiry, or the staff member's name.",
    "customer_email": "Email address submitted with the enquiry.",
    "customer_phone": "Phone number submitted with the enquiry.",
    "company_name": "Company supplied with the enquiry.",
    "product_name": "Product linked to the enquiry, or 'General enquiry'.",
    "enquiry_id": "Enquiry reference such as SPC-4A19C2.",
    "enquiry_message": "Message submitted by the customer.",
    "enquiry_status": "Current enquiry status label.",
    "enquiry_url": "Absolute dashboard link to the enquiry (staff templates).",
    "old_status": "Previous status label (status-change notifications).",
    "new_status": "New status label (status-change notifications).",
    "assigned_to": "Staff member assigned to the enquiry, if any.",
    "site_name": "Company name from website settings.",
    "contact_email": "Configured business contact email.",
    "admin_email": "Configured administrator notification email.",
    "current_year": "Current calendar year.",
    "reset_url": "Secure, single-use password reset link.",
    "protocol": "http or https for the current request.",
    "domain": "Request host name.",
}

# Filters that are safe for display. ``safe`` is deliberately excluded so
# customer values cannot bypass escaping.
ALLOWED_FILTERS = {
    "default",
    "upper",
    "lower",
    "title",
    "capfirst",
    "date",
    "time",
    "truncatechars",
    "truncatewords",
    "linebreaksbr",
    "linebreaks",
    "escape",
    "urlize",
    "yesno",
    "length",
    "pluralize",
}

_VARIABLE_RE = re.compile(r"{{\s*(.*?)\s*}}", re.S)
_TAG_RE = re.compile(r"{%.*?%}", re.S)
_SIMPLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Dangerous elements are removed with their contents. The second expression
# also removes stray opening/closing tags if the markup is malformed.
_BLOCK_ELEMENTS_RE = re.compile(
    r"(?is)<\s*(script|iframe|object|embed|form|input|button|select|textarea|meta|link)"
    r"\b[^>]*>.*?<\s*/\s*\1\s*>"
)
_ANY_DANGEROUS_TAG_RE = re.compile(
    r"(?is)</?\s*(script|iframe|object|embed|form|input|button|select|textarea|meta|link)"
    r"\b[^>]*>"
)
_EVENT_ATTRIBUTE_RE = re.compile(
    r"(?is)\s+on[a-z0-9_-]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)"
)
_SCRIPT_URL_RE = re.compile(r"(?is)(javascript|vbscript)\s*:")
_CSS_EXPRESSION_RE = re.compile(r"(?is)expression\s*\(")


class TemplateValidationError(ValueError):
    """Raised when administrator content uses unsupported template syntax."""


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html_body: str
    text_body: str


def validate_template_source(source: str, *, label: str = "Template") -> list[str]:
    """Return a list of human-readable validation errors for one source string."""
    source = source or ""
    errors: list[str] = []

    if _TAG_RE.search(source):
        errors.append(
            f"{label}: Django template tags ({{% ... %}}) are not allowed. "
            "Use the approved placeholders instead."
        )

    if source.count("{{") != len(_VARIABLE_RE.findall(source)):
        errors.append(f"{label}: a placeholder is missing its closing braces.")

    for raw_expression in _VARIABLE_RE.findall(source):
        expression = raw_expression.strip()
        if not expression:
            errors.append(f"{label}: an empty placeholder was found.")
            continue
        parts = [part.strip() for part in expression.split("|")]
        name = parts[0]
        if not _SIMPLE_NAME_RE.match(name) or name not in APPROVED_PLACEHOLDERS:
            errors.append(
                f"{label}: “{{{{ {name} }}}}” is not an approved placeholder. "
                "Choose one from the placeholder list."
            )
            continue
        for filter_expression in parts[1:]:
            filter_name = filter_expression.split(":", 1)[0].strip()
            if not _SIMPLE_NAME_RE.match(filter_name):
                errors.append(f"{label}: unsupported filter syntax in “{{{{ {expression} }}}}”.")
                break
            if filter_name not in ALLOWED_FILTERS:
                errors.append(
                    f"{label}: the “{filter_name}” filter is not allowed. "
                    "Use a plain placeholder or a simple formatting filter."
                )
                break

    return errors


def sanitize_email_html(value: str) -> str:
    """Remove active content from rendered HTML while preserving layout."""
    if not value:
        return ""
    cleaned = _BLOCK_ELEMENTS_RE.sub("", value)
    cleaned = _ANY_DANGEROUS_TAG_RE.sub("", cleaned)
    cleaned = _EVENT_ATTRIBUTE_RE.sub("", cleaned)
    cleaned = _SCRIPT_URL_RE.sub("#", cleaned)
    cleaned = _CSS_EXPRESSION_RE.sub("", cleaned)
    return cleaned


def _safe_context(context: dict) -> dict:
    return {
        key: "" if value is None else str(value)
        for key, value in (context or {}).items()
        if key in APPROVED_PLACEHOLDERS
    }


def _render(source: str, context: dict, *, autoescape: bool) -> str:
    engine = Engine(debug=False, autoescape=autoescape)
    template = engine.from_string(source or "")
    return template.render(Context(_safe_context(context), autoescape=autoescape))


def render_email_template(
    subject_source: str,
    html_source: str,
    text_source: str,
    context: dict,
) -> RenderedEmail:
    """Render and sanitise a validated email template."""
    errors = []
    errors.extend(validate_template_source(subject_source, label="Subject"))
    errors.extend(validate_template_source(html_source, label="HTML body"))
    errors.extend(validate_template_source(text_source, label="Plain-text body"))
    if errors:
        raise TemplateValidationError(" ".join(errors))

    subject = _render(subject_source, context, autoescape=False)
    subject = " ".join(subject.replace("\r", " ").replace("\n", " ").split())[:255]

    html_body = _render(html_source, context, autoescape=True)
    html_body = sanitize_email_html(html_body)

    text_body = _render(text_source, context, autoescape=False)
    return RenderedEmail(subject=subject, html_body=html_body, text_body=text_body)


def safe_rendered_html(value: str) -> str:
    """Mark already-sanitised HTML safe for dashboard previews."""
    return mark_safe(sanitize_email_html(value))
