from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("quality/", views.quality, name="quality"),
    path("contact/", views.contact, name="contact"),
    path("contact/thank-you/", views.contact_success, name="contact_success"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("credits/", views.credits, name="credits"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
    path("robots.txt", views.robots_txt, name="robots"),
]
