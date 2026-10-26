from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

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
