"""Dashboard URL map.

The dashboard lives under ``/admin/`` and is intentionally separate from
Django's own administration site. Every public sidebar destination resolves to
a real view — there are no placeholder routes.
"""
from django.urls import path

from cms import dashboard_views as cms_views
from email_manager import dashboard_views as email_views
from enquiries import dashboard_views as enquiry_views
from products import dashboard_views as product_views

from . import dashboard_views

app_name = "dashboard"

urlpatterns = [
    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    path("login/", dashboard_views.StaffLoginView.as_view(), name="login"),
    path("logout/", dashboard_views.StaffLogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        dashboard_views.StaffPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        dashboard_views.StaffPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        dashboard_views.StaffPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        dashboard_views.StaffPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    # ------------------------------------------------------------------
    # Overview & search
    # ------------------------------------------------------------------
    path("", dashboard_views.overview, name="overview"),
    path("search/", dashboard_views.search, name="search"),
    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    path("products/", product_views.product_list, name="product_list"),
    path("products/new/", product_views.product_create, name="product_create"),
    path("products/<int:pk>/edit/", product_views.product_edit, name="product_edit"),
    path(
        "products/<int:pk>/delete/",
        product_views.product_delete,
        name="product_delete",
    ),
    path(
        "products/<int:pk>/toggle-active/",
        product_views.product_toggle_active,
        name="product_toggle_active",
    ),
    path(
        "products/<int:pk>/toggle-featured/",
        product_views.product_toggle_featured,
        name="product_toggle_featured",
    ),
    path(
        "products/<int:pk>/duplicate/",
        product_views.product_duplicate,
        name="product_duplicate",
    ),
    path(
        "products/<int:pk>/gallery/",
        product_views.product_gallery,
        name="product_gallery",
    ),
    path(
        "products/<int:pk>/gallery/<int:image_pk>/delete/",
        product_views.product_gallery_delete,
        name="product_gallery_delete",
    ),
    # Product categories
    path("categories/", product_views.category_list, name="category_list"),
    path("categories/new/", product_views.category_create, name="category_create"),
    path(
        "categories/<int:pk>/edit/",
        product_views.category_edit,
        name="category_edit",
    ),
    path(
        "categories/<int:pk>/delete/",
        product_views.category_delete,
        name="category_delete",
    ),
    # ------------------------------------------------------------------
    # Enquiries & customers
    # ------------------------------------------------------------------
    path("enquiries/", enquiry_views.enquiry_list, name="enquiry_list"),
    path("enquiries/export/", enquiry_views.enquiry_export, name="enquiry_export"),
    path("enquiries/<int:pk>/", enquiry_views.enquiry_detail, name="enquiry_detail"),
    path(
        "enquiries/<int:pk>/notes/",
        enquiry_views.enquiry_note_add,
        name="enquiry_note_add",
    ),
    path(
        "enquiries/<int:pk>/convert/",
        enquiry_views.enquiry_convert,
        name="enquiry_convert",
    ),
    path(
        "enquiries/<int:pk>/delete/",
        enquiry_views.enquiry_delete,
        name="enquiry_delete",
    ),
    path("customers/", enquiry_views.customer_list, name="customer_list"),
    path(
        "customers/export/", enquiry_views.customer_export, name="customer_export"
    ),
    path("customers/new/", enquiry_views.customer_create, name="customer_create"),
    path(
        "customers/<int:pk>/", enquiry_views.customer_detail, name="customer_detail"
    ),
    path(
        "customers/<int:pk>/edit/", enquiry_views.customer_edit, name="customer_edit"
    ),
    path(
        "customers/<int:pk>/delete/",
        enquiry_views.customer_delete,
        name="customer_delete",
    ),
    # ------------------------------------------------------------------
    # Website pages
    # ------------------------------------------------------------------
    path("pages/", cms_views.page_list, name="page_list"),
    path("pages/new/", cms_views.page_create, name="page_create"),
    path("pages/<int:pk>/edit/", cms_views.page_edit, name="page_edit"),
    path(
        "pages/<int:pk>/toggle-status/",
        cms_views.page_toggle_status,
        name="page_toggle_status",
    ),
    path("pages/<int:pk>/delete/", cms_views.page_delete, name="page_delete"),
    # ------------------------------------------------------------------
    # Blog
    # ------------------------------------------------------------------
    path("blog/", cms_views.blog_list, name="blog_list"),
    path("blog/new/", cms_views.blog_create, name="blog_create"),
    path("blog/<int:pk>/edit/", cms_views.blog_edit, name="blog_edit"),
    path(
        "blog/<int:pk>/toggle-status/",
        cms_views.blog_toggle_status,
        name="blog_toggle_status",
    ),
    path("blog/<int:pk>/delete/", cms_views.blog_delete, name="blog_delete"),
    path(
        "blog/categories/", cms_views.blog_category_list, name="blog_category_list"
    ),
    path(
        "blog/categories/new/",
        cms_views.blog_category_create,
        name="blog_category_create",
    ),
    path(
        "blog/categories/<int:pk>/edit/",
        cms_views.blog_category_edit,
        name="blog_category_edit",
    ),
    path(
        "blog/categories/<int:pk>/delete/",
        cms_views.blog_category_delete,
        name="blog_category_delete",
    ),
    # ------------------------------------------------------------------
    # Media library
    # ------------------------------------------------------------------
    path("media/", cms_views.media_list, name="media_list"),
    path("media/upload/", cms_views.media_upload, name="media_upload"),
    path("media/<int:pk>/edit/", cms_views.media_edit, name="media_edit"),
    path("media/<int:pk>/delete/", cms_views.media_delete, name="media_delete"),
    # ------------------------------------------------------------------
    # SEO
    # ------------------------------------------------------------------
    path("seo/", cms_views.seo_overview, name="seo_overview"),
    path("seo/redirects/new/", cms_views.redirect_create, name="redirect_create"),
    path(
        "seo/redirects/<int:pk>/edit/",
        cms_views.redirect_edit,
        name="redirect_edit",
    ),
    path(
        "seo/redirects/<int:pk>/delete/",
        cms_views.redirect_delete,
        name="redirect_delete",
    ),
    # ------------------------------------------------------------------
    # Testimonials, FAQs, banners, navigation
    # ------------------------------------------------------------------
    path("testimonials/", cms_views.testimonial_list, name="testimonial_list"),
    path(
        "testimonials/new/",
        cms_views.testimonial_create,
        name="testimonial_create",
    ),
    path(
        "testimonials/<int:pk>/edit/",
        cms_views.testimonial_edit,
        name="testimonial_edit",
    ),
    path(
        "testimonials/<int:pk>/toggle/",
        cms_views.testimonial_toggle,
        name="testimonial_toggle",
    ),
    path(
        "testimonials/<int:pk>/delete/",
        cms_views.testimonial_delete,
        name="testimonial_delete",
    ),
    path("faqs/", cms_views.faq_list, name="faq_list"),
    path("faqs/new/", cms_views.faq_create, name="faq_create"),
    path("faqs/<int:pk>/edit/", cms_views.faq_edit, name="faq_edit"),
    path("faqs/<int:pk>/delete/", cms_views.faq_delete, name="faq_delete"),
    path("banners/", cms_views.banner_list, name="banner_list"),
    path("banners/new/", cms_views.banner_create, name="banner_create"),
    path("banners/<int:pk>/edit/", cms_views.banner_edit, name="banner_edit"),
    path("banners/<int:pk>/delete/", cms_views.banner_delete, name="banner_delete"),
    path("navigation/", cms_views.menu_list, name="menu_list"),
    path("navigation/new/", cms_views.menu_create, name="menu_create"),
    path("navigation/<int:pk>/edit/", cms_views.menu_edit, name="menu_edit"),
    path("navigation/<int:pk>/delete/", cms_views.menu_delete, name="menu_delete"),
    path(
        "navigation/<int:pk>/move/<str:direction>/",
        cms_views.menu_move,
        name="menu_move",
    ),
    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    path("settings/", dashboard_views.settings_view, name="settings"),
    path("settings/company/", dashboard_views.company_info, name="company_info"),
    path("settings/contact/", dashboard_views.contact_info, name="contact_info"),
    path("settings/social/", dashboard_views.social_media, name="social_media"),
    path("settings/seo/", dashboard_views.seo_settings, name="seo_settings"),
    path("settings/general/", dashboard_views.general_settings, name="general_settings"),
    # ------------------------------------------------------------------
    # Staff, roles & access control
    # ------------------------------------------------------------------
    path("staff/", dashboard_views.staff_list, name="staff_list"),
    path("staff/new/", dashboard_views.staff_create, name="staff_create"),
    path("staff/<int:pk>/edit/", dashboard_views.staff_edit, name="staff_edit"),
    path("staff/<int:pk>/delete/", dashboard_views.staff_delete, name="staff_delete"),
    path("roles/", dashboard_views.role_list, name="role_list"),
    path("roles/new/", dashboard_views.role_create, name="role_create"),
    path("roles/<int:pk>/edit/", dashboard_views.role_edit, name="role_edit"),
    path("roles/<int:pk>/delete/", dashboard_views.role_delete, name="role_delete"),
    # ------------------------------------------------------------------
    # Email manager
    # ------------------------------------------------------------------
    path("email-manager/", email_views.overview, name="email_overview"),
    path(
        "email-manager/smtp/",
        email_views.smtp_settings,
        name="email_smtp_settings",
    ),
    path(
        "email-manager/smtp/test-connection/",
        email_views.smtp_test_connection,
        name="email_smtp_test_connection",
    ),
    path(
        "email-manager/test-email/",
        email_views.test_email,
        name="email_test",
    ),
    path(
        "email-manager/templates/",
        email_views.template_list,
        name="email_template_list",
    ),
    path(
        "email-manager/templates/new/",
        email_views.template_create,
        name="email_template_create",
    ),
    path(
        "email-manager/templates/<int:pk>/edit/",
        email_views.template_edit,
        name="email_template_edit",
    ),
    path(
        "email-manager/templates/<int:pk>/preview/",
        email_views.template_preview,
        name="email_template_preview",
    ),
    path(
        "email-manager/templates/<int:pk>/toggle/",
        email_views.template_toggle,
        name="email_template_toggle",
    ),
    path(
        "email-manager/templates/<int:pk>/test/",
        email_views.template_test,
        name="email_template_test",
    ),
    path(
        "email-manager/templates/<int:pk>/delete/",
        email_views.template_delete,
        name="email_template_delete",
    ),
    path(
        "email-manager/logs/",
        email_views.log_list,
        name="email_log_list",
    ),
    path(
        "email-manager/logs/prune/",
        email_views.log_prune,
        name="email_log_prune",
    ),
    path(
        "email-manager/logs/<int:pk>/",
        email_views.log_detail,
        name="email_log_detail",
    ),
    path(
        "email-manager/logs/<int:pk>/retry/",
        email_views.log_retry,
        name="email_log_retry",
    ),
    path(
        "email-manager/rules/",
        email_views.notification_rules,
        name="email_rules",
    ),
    path(
        "email-manager/rules/<int:pk>/update/",
        email_views.notification_rule_update,
        name="email_rule_update",
    ),
    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    path("notifications/", dashboard_views.notification_list, name="notification_list"),
    path(
        "notifications/new/",
        dashboard_views.notification_create,
        name="notification_create",
    ),
    path(
        "notifications/<int:pk>/open/",
        dashboard_views.notification_open,
        name="notification_open",
    ),
    path(
        "notifications/<int:pk>/delete/",
        dashboard_views.notification_delete,
        name="notification_delete",
    ),
    path(
        "notifications/read-all/",
        dashboard_views.notification_mark_all_read,
        name="notification_mark_all_read",
    ),
    # ------------------------------------------------------------------
    # Reports, activity, backup & profile
    # ------------------------------------------------------------------
    path("reports/", dashboard_views.reports_index, name="reports_index"),
    path("reports/export/", dashboard_views.reports_export, name="reports_export"),
    path("activity/", dashboard_views.activity_list, name="activity_list"),
    path("activity/export/", dashboard_views.activity_export, name="activity_export"),
    path("backup/", dashboard_views.backup_index, name="backup_index"),
    path("backup/create/", dashboard_views.backup_create, name="backup_create"),
    path(
        "backup/download/<str:filename>/",
        dashboard_views.backup_download,
        name="backup_download",
    ),
    path(
        "backup/delete/<str:filename>/",
        dashboard_views.backup_delete,
        name="backup_delete",
    ),
    path("profile/", dashboard_views.profile, name="profile"),
]
