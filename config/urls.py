from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

from core import views

admin.site.site_header = "Sanjeev Power Controls — Django administration"
admin.site.site_title = "Sanjeev Power Controls"
admin.site.index_title = "Database administration"

urlpatterns = [
    path("", include("core.urls")),
    path("products/", include("products.urls")),
    path("enquiries/", include("enquiries.urls")),
    path("blog/", include("cms.urls_public")),
    path("admin-panel/", include("core.urls_dashboard")),
    path("django-admin/", admin.site.urls),
    # Generic managed-page route. Kept last so products, blog, dashboard and
    # the dedicated core routes always win.
    path("<slug:slug>/", views.page_detail, name="page"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    # `static()` is a no-op outside debug mode, so add the media route
    # explicitly for preview deployments without object storage configured.
    urlpatterns += [
        path(
            f"{settings.MEDIA_URL.lstrip('/')}<path:path>",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]
