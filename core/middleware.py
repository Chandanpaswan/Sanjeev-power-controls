from __future__ import annotations

from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse


class AdminRedirectMiddleware:
    """Apply SEO redirects to public paths only."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ("GET", "HEAD"):
            path = request.path
            exempt = (
                path.startswith("/admin-panel/")
                or path.startswith("/django-admin/")
                or path.startswith("/static/")
                or path.startswith("/media/")
            )
            if not exempt:
                try:
                    from cms.models import RedirectRule

                    rule = RedirectRule.objects.filter(old_path=path, is_active=True).first()
                except Exception:
                    rule = None
                if rule:
                    redirect_class = (
                        HttpResponsePermanentRedirect
                        if rule.status_code == 301
                        else HttpResponseRedirect
                    )
                    return redirect_class(rule.new_path)
        return self.get_response(request)


class MaintenanceModeMiddleware:
    """Show a clear 503 page while maintenance mode is enabled."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        exempt = (
            path.startswith("/admin-panel/")
            or path.startswith("/django-admin/")
            or path.startswith("/static/")
            or path.startswith("/media/")
        )
        user = getattr(request, "user", None)
        if not exempt and not (user and user.is_authenticated and user.is_staff):
            try:
                from core.models import SiteSettings

                site = SiteSettings.load()
            except Exception:
                site = None
            if site and site.maintenance_mode:
                return render(
                    request,
                    "maintenance.html",
                    {"site_profile": site, "maintenance_message": site.maintenance_message},
                    status=503,
                )
        return self.get_response(request)
