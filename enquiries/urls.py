from django.urls import path

from . import views

app_name = "enquiries"

urlpatterns = [
    path("submit/", views.create_enquiry, name="create"),
]
