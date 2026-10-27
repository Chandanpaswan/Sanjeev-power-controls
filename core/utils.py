"""Small shared helpers used by the dashboard and public site."""
from __future__ import annotations

import re

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


def client_ip(request):
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR") or ""


def log_activity(request, action, description, target=None, target_type="", target_id=""):
    """Record an audit entry without ever failing the calling view."""
    from .models import ActivityLog

    try:
        if target is not None:
            target_type = target_type or target._meta.label_lower
            target_id = target_id or str(getattr(target, "pk", ""))
        ActivityLog.objects.create(
            user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
            action=action,
            description=description[:255],
            target_type=target_type[:80],
            target_id=str(target_id)[:40],
            ip_address=client_ip(request) or None,
        )
    except Exception:  # Audit logging must never break a working action.
        pass


def notify_staff(title, message, url="", level="info", users=None):
    """Create one notification per active staff member (deduplicated)."""
    from django.contrib.auth import get_user_model

    from .models import Notification

    User = get_user_model()
    recipients = users
    if recipients is None:
        recipients = User.objects.filter(is_active=True, is_staff=True)
    seen = set()
    for user in recipients:
        if not user or not user.pk or user.pk in seen:
            continue
        seen.add(user.pk)
        Notification.objects.create(
            user=user, title=title[:160], message=message, url=url, level=level
        )


def login_key(username, ip):
    return f"spc-login-fail:{username.strip().lower()}:{ip}"


def login_is_locked(username, ip):
    limit = getattr(settings, "LOGIN_MAX_ATTEMPTS", 5)
    return int(cache.get(login_key(username, ip), 0)) >= limit


def login_record_failure(username, ip):
    key = login_key(username, ip)
    timeout = getattr(settings, "LOGIN_LOCKOUT_SECONDS", 900)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)


def login_clear_failures(username, ip):
    cache.delete(login_key(username, ip))


def today():
    return timezone.localdate()


def safe_next_url(value, fallback="/admin/"):
    """Only allow same-site relative redirects after authentication."""
    if not value:
        return fallback
    value = value.strip()
    if value.startswith("/") and not value.startswith("//") and not value.startswith("/\\"):
        return value
    return fallback


def human_size(size):
    size = int(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def slug_is_reserved(value):
    return value.strip("/").lower() in {
        "admin",
        "django-admin",
        "media",
        "static",
        "enquiries",
        "products",
        "blog",
        "sitemap.xml",
        "robots.txt",
    }


_SCRIPT_RE = re.compile(r"(?is)<\s*(script|iframe|object|embed|form|input|button)[^>]*>.*?<\s*/\s*\1\s*>")
_EVENT_RE = re.compile(r"(?i)\son\w+\s*=")
_JS_URL_RE = re.compile(r"(?i)javascript:")
_TAG_RE = re.compile(r"(?is)<\s*/?\s*([a-zA-Z0-9]+)([^>]*)>")
_ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "h2", "h3",
    "h4", "blockquote", "a", "hr", "table", "thead", "tbody", "tr", "th", "td",
}


def sanitize_html(value):
    """Allow a small, safe subset of HTML. No scripts, styles or event handlers."""
    if not value:
        return ""
    value = _SCRIPT_RE.sub("", str(value))
    value = _EVENT_RE.sub(" data-removed=", value)
    value = _JS_URL_RE.sub("#", value)

    def replace(match):
        tag = match.group(1).lower()
        if tag not in _ALLOWED_TAGS:
            return ""
        attrs = match.group(2) or ""
        if tag == "a":
            href = re.search(r'(?i)href\s*=\s*["\']([^"\']*)["\']', attrs)
            if not href:
                return "<a>"
            url = href.group(1).strip()
            if not re.match(r"(?i)^(https?://|mailto:|/|#)", url):
                return "<a>"
            return (
                f'<a href="{url.replace(chr(34), "&quot;")}" '
                'rel="noopener nofollow" target="_blank">'
            )
        return f"<{tag}>" if not match.group(0).startswith("</") else f"</{tag}>"

    return _TAG_RE.sub(replace, value)
