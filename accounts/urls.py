from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.customer_register, name="register"),
    path("login/", views.customer_login, name="login"),
    path("logout/", views.customer_logout, name="logout"),
    path("seller/register/", views.seller_register, name="seller_register"),
    path("customer/dashboard/", views.customer_dashboard, name="customer_dashboard"),
    path("customer/profile/", views.customer_profile, name="customer_profile"),
    path("customer/enquiries/", views.customer_enquiries, name="customer_enquiries"),
    path("customer/enquiries/<int:pk>/", views.customer_enquiry_detail, name="customer_enquiry_detail"),
    path("customer/quotations/", views.customer_quotations, name="customer_quotations"),
    path("customer/settings/", views.customer_settings, name="customer_settings"),
    path("seller/dashboard/", views.seller_dashboard, name="seller_dashboard"),
    path("seller/products/", views.seller_products, name="seller_products"),
    path("seller/enquiries/", views.seller_enquiries, name="seller_enquiries"),
    path("seller/quotations/", views.seller_quotations, name="seller_quotations"),
    path("seller/profile/", views.seller_profile, name="seller_profile"),
    path("admin/users/", views.admin_users, name="admin_users"),
    path("admin/customers/", views.admin_customers, name="admin_customers"),
    path("admin/sellers/", views.admin_sellers, name="admin_sellers"),
    path("admin/sellers/<int:pk>/approve/", views.admin_approve_seller, name="admin_approve_seller"),
    path("admin/sellers/<int:pk>/reject/", views.admin_reject_seller, name="admin_reject_seller"),
    path("admin/enquiries/", views.admin_enquiries, name="admin_enquiries"),
    path("admin/quotations/", views.admin_quotations, name="admin_quotations"),
    path("admin/quotations/create/", views.admin_create_quotation, name="admin_create_quotation"),
    path("password-reset/", auth_views.PasswordResetView.as_view(template_name="accounts/password_reset.html"), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("password-reset-confirm/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html"), name="password_reset_confirm"),
    path("password-reset-complete/", auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
]
