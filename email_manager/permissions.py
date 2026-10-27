"""Server-side access control for the Email Manager.

Hiding a sidebar link is never sufficient: every view is wrapped by one of
these decorators and Django's CSRF middleware protects every POST.
"""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse


def _authenticated_staff(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_active and user.is_staff)


def email_manager_access(*permissions: str):
    """Allow active staff who hold any one of the supplied permissions."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not _authenticated_staff(request):
                return redirect_to_login(
                    request.get_full_path(), reverse("dashboard:login")
                )
            user = request.user
            if permissions and not any(
                user.has_perm(permission) for permission in permissions
            ):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def smtp_admin_required(view):
    """Only superusers or holders of ``email_manager.manage_smtp``."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not _authenticated_staff(request):
            return redirect_to_login(request.get_full_path(), reverse("dashboard:login"))
        user = request.user
        if not (
            user.is_superuser
            or user.has_perm("email_manager.manage_smtp")
        ):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def can_manage_smtp(user) -> bool:
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return bool(
        user.is_superuser or user.has_perm("email_manager.manage_smtp")
    )


def can_view_email_manager(user) -> bool:
    if not user or not user.is_authenticated or not user.is_active or not user.is_staff:
        return False
    return bool(
        user.is_superuser
        or user.has_perm("email_manager.manage_smtp")
        or user.has_perm("email_manager.view_emaillog")
        or user.has_perm("email_manager.view_emailtemplate")
    )
