"""Dashboard views for administration, settings, access control and tooling.

Every view here is wired to :mod:`core.urls_dashboard`; there are no
placeholder actions. Permission checks run on the server so that hiding a
sidebar link is never the only protection.
"""
from __future__ import annotations

import csv
import re
import sqlite3
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import Group
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from enquiries.models import Customer, Enquiry
from products.models import Category, Product

from .forms import (
    CompanyInfoForm,
    ContactInfoForm,
    DashboardPasswordChangeForm,
    GeneralSettingsForm,
    NotificationCreateForm,
    ProfileForm,
    RoleForm,
    SeoSettingsForm,
    SocialMediaForm,
    StaffCreateForm,
    StaffLoginForm,
    StaffPasswordResetForm,
    StaffUpdateForm,
    search_users,
    staff_required,
    superuser_required,
)
from .models import ActivityLog, Notification, SiteSettings
from .utils import human_size, log_activity, safe_next_url

User = get_user_model()

SEARCH_GROUP_LIMIT = 6
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
BACKUP_NAME_RE = re.compile(r"^spc-backup-\d{8}-\d{6}\.(sqlite3|json)$")
REQUIRED_ROLES = (
    "Super Admin",
    "Content Manager",
    "Product Manager",
    "Sales Manager",
    "Viewer / Analyst",
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _csv_safe(value):
    """Prevent spreadsheet formula injection in exported CSV files."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(CSV_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _csv_response(filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    return response


def _percent(part, whole):
    if not whole:
        return 0
    return round(part / whole * 100, 1)


def _activity_url(log):
    """Best-effort dashboard link for an audit-log target."""
    mapping = {
        "products.product": "dashboard:product_edit",
        "products.category": "dashboard:category_edit",
        "enquiries.enquiry": "dashboard:enquiry_detail",
        "enquiries.customer": "dashboard:customer_detail",
        "cms.page": "dashboard:page_edit",
        "cms.blogpost": "dashboard:blog_edit",
        "cms.mediaasset": "dashboard:media_edit",
        "cms.testimonial": "dashboard:testimonial_edit",
        "cms.faq": "dashboard:faq_edit",
        "cms.banner": "dashboard:banner_edit",
        "cms.menuitem": "dashboard:menu_edit",
        "core.sitesettings": "dashboard:company_info",
    }
    route = mapping.get(log.target_type)
    if not route or not log.target_id:
        return ""
    try:
        return reverse(route, args=[int(log.target_id)])
    except Exception:
        return ""


def _settings_tabs(active):
    return [
        {
            "key": "company",
            "label": "Company information",
            "description": "Brand, logo and footer",
            "url": reverse("dashboard:company_info"),
            "active": active == "company",
        },
        {
            "key": "contact",
            "label": "Contact information",
            "description": "Phone, email, address and hours",
            "url": reverse("dashboard:contact_info"),
            "active": active == "contact",
        },
        {
            "key": "social",
            "label": "Social media",
            "description": "Verified profile links",
            "url": reverse("dashboard:social_media"),
            "active": active == "social",
        },
        {
            "key": "seo",
            "label": "SEO defaults",
            "description": "Metadata, indexing and robots.txt",
            "url": reverse("dashboard:seo_settings"),
            "active": active == "seo",
        },
        {
            "key": "general",
            "label": "General",
            "description": "Analytics and maintenance mode",
            "url": reverse("dashboard:general_settings"),
            "active": active == "general",
        },
    ]


def _backup_dir():
    directory = Path(getattr(settings, "BACKUP_DIR", settings.BASE_DIR / "backups"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _backup_files():
    directory = _backup_dir()
    items = []
    for path in directory.glob("spc-backup-*"):
        if not path.is_file() or not BACKUP_NAME_RE.match(path.name):
            continue
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "size": stat.st_size,
                "size_label": human_size(stat.st_size),
                "modified": timezone.datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.get_current_timezone()
                ),
                "kind": "Database" if path.suffix == ".sqlite3" else "JSON archive",
            }
        )
    items.sort(key=lambda item: item["modified"], reverse=True)
    return items


def _safe_backup_path(filename):
    if not BACKUP_NAME_RE.match(filename or ""):
        raise Http404("Backup not found.")
    path = (_backup_dir() / filename).resolve()
    if path.parent != _backup_dir().resolve() or not path.is_file():
        raise Http404("Backup not found.")
    return path


# ---------------------------------------------------------------------------
# Overview & global search
# ---------------------------------------------------------------------------
@staff_required
def overview(request):
    from cms.models import BlogPost, FAQ, MediaAsset, Page, Testimonial

    today = timezone.localdate()
    counts = {
        "products": Product.objects.count(),
        "active_products": Product.objects.filter(active=True).count(),
        "inactive_products": Product.objects.filter(active=False).count(),
        "featured_products": Product.objects.filter(featured=True).count(),
        "categories": Category.objects.count(),
        "enquiries": Enquiry.objects.count(),
        "new_enquiries": Enquiry.objects.filter(status=Enquiry.STATUS_NEW).count(),
        "open_enquiries": Enquiry.objects.filter(
            status__in=Enquiry.OPEN_STATUSES
        ).count(),
        "customers": Customer.objects.count(),
        "pages": Page.objects.count(),
        "published_pages": Page.objects.filter(status=Page.STATUS_PUBLISHED).count(),
        "blog_posts": BlogPost.objects.count(),
        "published_posts": BlogPost.objects.filter(
            status=BlogPost.STATUS_PUBLISHED, published_at__lte=timezone.now()
        ).count(),
        "draft_posts": BlogPost.objects.filter(status=BlogPost.STATUS_DRAFT).count(),
        "media": MediaAsset.objects.count(),
        "testimonials": Testimonial.objects.count(),
        "faqs": FAQ.objects.count(),
    }

    recent_enquiries = list(
        Enquiry.objects.select_related("product", "assigned_to").order_by(
            "-created_at"
        )[:6]
    )
    recent_products = list(
        Product.objects.select_related("category").order_by("-updated_at")[:5]
    )

    activity = []
    for log in ActivityLog.objects.select_related("user")[:10]:
        activity.append(
            {
                "kind": log.action,
                "title": log.description,
                "url": _activity_url(log),
                "meta": log.created_at,
                "user": log.user,
            }
        )
    if not activity:
        for enquiry in recent_enquiries[:4]:
            activity.append(
                {
                    "kind": "enquiry",
                    "title": f"Enquiry {enquiry.reference} from {enquiry.name}",
                    "url": reverse("dashboard:enquiry_detail", args=[enquiry.pk]),
                    "meta": enquiry.created_at,
                    "user": None,
                }
            )
        for product in recent_products[:4]:
            activity.append(
                {
                    "kind": "product",
                    "title": f"{product.name} updated",
                    "url": reverse("dashboard:product_edit", args=[product.pk]),
                    "meta": product.updated_at,
                    "user": None,
                }
            )
        activity.sort(key=lambda item: item["meta"], reverse=True)

    unread = Notification.objects.filter(
        Q(user=request.user) | Q(user__isnull=True), is_read=False
    )

    return render(
        request,
        "dashboard/overview.html",
        {
            "counts": counts,
            "recent_enquiries": recent_enquiries,
            "recent_products": recent_products,
            "activity": activity[:8],
            "followups_due": Enquiry.objects.filter(
                follow_up_date__lte=today, status__in=Enquiry.OPEN_STATUSES
            ).count(),
            "unread_notifications": unread.count(),
            "recent_notifications": list(unread[:4]),
            "today": today,
        },
    )


def _search_items(request, query):
    """Return grouped search results, filtered by the viewer's permissions."""
    from cms.models import (
        Banner,
        BlogPost,
        FAQ,
        MediaAsset,
        MenuItem,
        Page,
        Testimonial,
    )

    groups = []

    def add_group(label, icon, items, more_url):
        if items:
            groups.append(
                {
                    "label": label,
                    "icon": icon,
                    "items": items,
                    "more_url": more_url,
                }
            )

    user = request.user

    if user.has_perm("products.view_product"):
        qs = Product.objects.select_related("category").filter(
            Q(name__icontains=query) | Q(sku__icontains=query)
            | Q(short_description__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Products",
            "box",
            [
                {
                    "title": product.name,
                    "subtitle": f"{product.sku} · {product.category.name}",
                    "url": reverse("dashboard:product_edit", args=[product.pk]),
                }
                for product in qs
            ],
            f"{reverse('dashboard:product_list')}?q={query}",
        )

    if user.has_perm("products.view_category"):
        qs = Category.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Product categories",
            "layers",
            [
                {
                    "title": category.name,
                    "subtitle": f"{category.products.count()} product(s)",
                    "url": reverse("dashboard:category_edit", args=[category.pk]),
                }
                for category in qs
            ],
            f"{reverse('dashboard:category_list')}?q={query}",
        )

    if user.has_perm("enquiries.view_enquiry"):
        qs = Enquiry.objects.filter(
            Q(reference__icontains=query)
            | Q(name__icontains=query)
            | Q(company__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Enquiries",
            "inbox",
            [
                {
                    "title": f"{enquiry.reference} — {enquiry.name}",
                    "subtitle": f"{enquiry.get_status_display()} · {enquiry.get_priority_display()} priority",
                    "url": reverse("dashboard:enquiry_detail", args=[enquiry.pk]),
                }
                for enquiry in qs
            ],
            f"{reverse('dashboard:enquiry_list')}?q={query}",
        )

    if user.has_perm("enquiries.view_customer"):
        qs = Customer.objects.filter(
            Q(name__icontains=query)
            | Q(contact_person__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Customers",
            "users",
            [
                {
                    "title": customer.name,
                    "subtitle": customer.contact_person or customer.email or customer.get_status_display(),
                    "url": reverse("dashboard:customer_detail", args=[customer.pk]),
                }
                for customer in qs
            ],
            f"{reverse('dashboard:customer_list')}?q={query}",
        )

    if user.has_perm("cms.view_page"):
        qs = Page.objects.filter(
            Q(title__icontains=query) | Q(slug__icontains=query)
            | Q(body__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Website pages",
            "file",
            [
                {
                    "title": page.title,
                    "subtitle": f"/{page.slug}/ · {page.get_status_display()}",
                    "url": reverse("dashboard:page_edit", args=[page.pk]),
                }
                for page in qs
            ],
            f"{reverse('dashboard:page_list')}?q={query}",
        )

    if user.has_perm("cms.view_blogpost"):
        qs = BlogPost.objects.select_related("category").filter(
            Q(title__icontains=query) | Q(excerpt__icontains=query)
            | Q(content__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Blog posts",
            "pencil",
            [
                {
                    "title": post.title,
                    "subtitle": " · ".join(
                        filter(
                            None,
                            [
                                post.category.name if post.category else "",
                                post.get_status_display(),
                            ],
                        )
                    ),
                    "url": reverse("dashboard:blog_edit", args=[post.pk]),
                }
                for post in qs
            ],
            f"{reverse('dashboard:blog_list')}?q={query}",
        )

    if user.has_perm("cms.view_mediaasset"):
        qs = MediaAsset.objects.filter(
            Q(title__icontains=query) | Q(alt_text__icontains=query)
            | Q(file__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Media library",
            "image",
            [
                {
                    "title": asset.title or asset.filename,
                    "subtitle": f"{asset.get_file_type_display()} · {human_size(asset.file_size)}",
                    "url": reverse("dashboard:media_edit", args=[asset.pk]),
                }
                for asset in qs
            ],
            f"{reverse('dashboard:media_list')}?q={query}",
        )

    if user.has_perm("cms.view_testimonial"):
        qs = Testimonial.objects.filter(
            Q(customer_name__icontains=query) | Q(quote__icontains=query)
            | Q(company__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Testimonials",
            "star",
            [
                {
                    "title": testimonial.customer_name,
                    "subtitle": testimonial.quote[:90],
                    "url": reverse(
                        "dashboard:testimonial_edit", args=[testimonial.pk]
                    ),
                }
                for testimonial in qs
            ],
            f"{reverse('dashboard:testimonial_list')}?q={query}",
        )

    if user.has_perm("cms.view_faq"):
        qs = FAQ.objects.filter(
            Q(question__icontains=query) | Q(answer__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "FAQs",
            "info",
            [
                {
                    "title": faq.question,
                    "subtitle": faq.category or "General",
                    "url": reverse("dashboard:faq_edit", args=[faq.pk]),
                }
                for faq in qs
            ],
            f"{reverse('dashboard:faq_list')}?q={query}",
        )

    if user.has_perm("cms.view_banner"):
        qs = Banner.objects.filter(
            Q(title__icontains=query) | Q(heading__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Banners",
            "image",
            [
                {
                    "title": banner.title,
                    "subtitle": "Active" if banner.is_active else "Inactive",
                    "url": reverse("dashboard:banner_edit", args=[banner.pk]),
                }
                for banner in qs
            ],
            reverse("dashboard:banner_list"),
        )

    if user.has_perm("cms.view_menuitem"):
        qs = MenuItem.objects.filter(
            Q(label__icontains=query) | Q(url__icontains=query)
        )[:SEARCH_GROUP_LIMIT]
        add_group(
            "Navigation",
            "menu",
            [
                {
                    "title": item.label,
                    "subtitle": f"{item.get_location_display()} · {item.resolved_url}",
                    "url": reverse("dashboard:menu_edit", args=[item.pk]),
                }
                for item in qs
            ],
            reverse("dashboard:menu_list"),
        )

    if user.has_perm("auth.view_user"):
        qs = search_users(query)[:SEARCH_GROUP_LIMIT]
        add_group(
            "Staff accounts",
            "users",
            [
                {
                    "title": staff_user.get_full_name() or staff_user.username,
                    "subtitle": staff_user.email or staff_user.username,
                    "url": reverse("dashboard:staff_edit", args=[staff_user.pk]),
                }
                for staff_user in qs
            ],
            f"{reverse('dashboard:staff_list')}?q={query}",
        )

    return groups


@staff_required
def search(request):
    query = (request.GET.get("q") or "").strip()
    groups = []
    total = 0
    if len(query) >= 2:
        groups = _search_items(request, query)
        total = sum(len(group["items"]) for group in groups)
    return render(
        request,
        "dashboard/search.html",
        {
            "query": query,
            "groups": groups,
            "total": total,
            "searched": len(query) >= 2,
        },
    )


# ---------------------------------------------------------------------------
# Website settings
# ---------------------------------------------------------------------------
@staff_required
def settings_view(request):
    return redirect("dashboard:company_info")


def _settings_tab_view(
    request, form_class, *, tab, title, description, activity_label
):
    site = SiteSettings.load()
    form = form_class(request.POST or None, request.FILES or None, instance=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"{activity_label} updated",
            target=site,
        )
        messages.success(request, f"{activity_label} saved.")
        return redirect(request.path)
    if request.method == "POST":
        messages.error(request, "Please correct the highlighted fields.")

    return render(
        request,
        "dashboard/settings/form.html",
        {
            "form": form,
            "sections": form.section_fields(),
            "site": site,
            "title": title,
            "description": description,
            "eyebrow": "Website settings",
            "tabs": _settings_tabs(tab),
            "active_tab": tab,
            "submit_label": "Save settings",
            "cancel_url": reverse("dashboard:overview"),
        },
    )


@staff_required
@permission_required("core.change_sitesettings", raise_exception=True)
def company_info(request):
    return _settings_tab_view(
        request,
        CompanyInfoForm,
        tab="company",
        title="Company information",
        description=(
            "Brand identity, logo, footer summary and copyright. These values "
            "appear across the public website and in structured data."
        ),
        activity_label="Company information",
    )


@staff_required
@permission_required("core.change_sitesettings", raise_exception=True)
def contact_info(request):
    return _settings_tab_view(
        request,
        ContactInfoForm,
        tab="contact",
        title="Contact information",
        description=(
            "Only configured values are shown as clickable links on the public "
            "site. Blank fields display a clearly marked placeholder instead."
        ),
        activity_label="Contact information",
    )


@staff_required
@permission_required("core.change_sitesettings", raise_exception=True)
def social_media(request):
    return _settings_tab_view(
        request,
        SocialMediaForm,
        tab="social",
        title="Social media settings",
        description="Full https:// profile URLs. Blank profiles are hidden automatically.",
        activity_label="Social media settings",
    )


@staff_required
@permission_required("core.change_sitesettings", raise_exception=True)
def seo_settings(request):
    return _settings_tab_view(
        request,
        SeoSettingsForm,
        tab="seo",
        title="SEO management",
        description=(
            "Default metadata and indexing controls. Individual pages and "
            "products can override these values."
        ),
        activity_label="SEO settings",
    )


@staff_required
@permission_required("core.change_sitesettings", raise_exception=True)
def general_settings(request):
    return _settings_tab_view(
        request,
        GeneralSettingsForm,
        tab="general",
        title="General settings",
        description=(
            "Analytics is loaded only when a GA4 measurement ID is configured. "
            "Maintenance mode shows a 503 page to public visitors while staff "
            "continue working."
        ),
        activity_label="General settings",
    )


# ---------------------------------------------------------------------------
# Staff accounts
# ---------------------------------------------------------------------------
@superuser_required
def staff_list(request):
    query = (request.GET.get("q") or "").strip()
    staff_users = (
        search_users(query)
        .prefetch_related("groups")
        .annotate(activity_total=Count("activity_logs"))
        .order_by("username")
    )
    return render(
        request,
        "dashboard/staff/list.html",
        {
            "staff_users": staff_users,
            "query": query,
            "active_count": staff_users.filter(is_active=True).count(),
            "superuser_count": staff_users.filter(is_superuser=True).count(),
        },
    )


@superuser_required
def staff_create(request):
    form = StaffCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Staff account created: {user.username}",
            target=user,
        )
        messages.success(request, f"Staff account “{user.username}” created.")
        return redirect("dashboard:staff_list")

    return render(
        request,
        "dashboard/staff/form.html",
        {"form": form, "mode": "create"},
    )


@superuser_required
def staff_edit(request, pk):
    user = get_object_or_404(User, pk=pk, is_staff=True)
    form = StaffUpdateForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Staff account updated: {user.username}",
            target=user,
        )
        messages.success(request, f"Staff account “{user.username}” updated.")
        return redirect("dashboard:staff_list")

    return render(
        request,
        "dashboard/staff/form.html",
        {"form": form, "mode": "edit", "staff_user": user},
    )


@superuser_required
def staff_delete(request, pk):
    user = get_object_or_404(User, pk=pk, is_staff=True)

    if user.pk == request.user.pk:
        messages.error(request, "You cannot delete your own account.")
        return redirect("dashboard:staff_list")

    if user.is_superuser and User.objects.filter(
        is_superuser=True, is_active=True
    ).count() <= 1:
        messages.error(request, "The last active superuser account cannot be deleted.")
        return redirect("dashboard:staff_list")

    if request.method == "POST":
        username = user.username
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Staff account deleted: {username}",
            target_type="auth.user",
            target_id=user.pk,
        )
        user.delete()
        messages.success(request, f"Staff account “{username}” deleted.")
        return redirect("dashboard:staff_list")

    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete staff account",
            "object_label": (
                f"{user.get_full_name() or user.username} ({user.username})"
            ),
            "object_type": "staff account",
            "warning": (
                "The account will lose dashboard access immediately. Audit log "
                "entries are retained with the account name removed. This cannot "
                "be undone."
            ),
            "cancel_url": reverse("dashboard:staff_edit", args=[user.pk]),
        },
    )


# ---------------------------------------------------------------------------
# Roles & permissions
# ---------------------------------------------------------------------------
@superuser_required
def role_list(request):
    query = (request.GET.get("q") or "").strip()
    roles = Group.objects.annotate(
        user_total=Count("user", distinct=True),
        permission_total=Count("permissions", distinct=True),
    )
    if query:
        roles = roles.filter(name__icontains=query)
    roles = roles.order_by("name")
    role_names = list(roles.values_list("name", flat=True))
    return render(
        request,
        "dashboard/staff/roles.html",
        {
            "roles": roles,
            "query": query,
            "required_roles": REQUIRED_ROLES,
            "role_names": role_names,
            "role_total": roles.count(),
            "unassigned_staff": User.objects.filter(
                is_staff=True, groups__isnull=True
            ).count(),
        },
    )


@superuser_required
def role_create(request):
    form = RoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        role = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Role created: {role.name}",
            target=role,
        )
        messages.success(request, f"Role “{role.name}” created.")
        return redirect("dashboard:role_list")

    return render(
        request,
        "dashboard/staff/role_form.html",
        {
            "form": form,
            "permission_groups": form.grouped_permissions(),
            "mode": "create",
            "title": "Create role",
            "cancel_url": reverse("dashboard:role_list"),
        },
    )


@superuser_required
def role_edit(request, pk):
    role = get_object_or_404(Group, pk=pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        role = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Role updated: {role.name}",
            target=role,
        )
        messages.success(request, f"Role “{role.name}” updated.")
        return redirect("dashboard:role_list")

    return render(
        request,
        "dashboard/staff/role_form.html",
        {
            "form": form,
            "permission_groups": form.grouped_permissions(),
            "mode": "edit",
            "role": role,
            "title": f"Edit {role.name}",
            "cancel_url": reverse("dashboard:role_list"),
        },
    )


@superuser_required
def role_delete(request, pk):
    role = get_object_or_404(Group, pk=pk)
    member_count = role.user_set.count()

    if member_count:
        messages.error(
            request,
            f"“{role.name}” is assigned to {member_count} staff account(s). "
            "Reassign those accounts before deleting the role.",
        )
        return redirect("dashboard:role_list")

    if request.method == "POST":
        name = role.name
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Role deleted: {name}",
            target_type="auth.group",
            target_id=role.pk,
        )
        role.delete()
        messages.success(request, f"Role “{name}” deleted.")
        return redirect("dashboard:role_list")

    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete role",
            "object_label": role.name,
            "object_type": "role",
            "warning": (
                f"{role.permissions.count()} permission(s) will be removed from "
                "this role. Staff accounts are not affected because none are "
                "currently assigned. This cannot be undone."
            ),
            "cancel_url": reverse("dashboard:role_list"),
        },
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
def _notification_scope(user):
    return Notification.objects.filter(Q(user=user) | Q(user__isnull=True))


@staff_required
def notification_list(request):
    notifications = _notification_scope(request.user).select_related("user")
    status = (request.GET.get("status") or "").strip()
    level = (request.GET.get("level") or "").strip()
    if status == "unread":
        notifications = notifications.filter(is_read=False)
    elif status == "read":
        notifications = notifications.filter(is_read=True)
    if level in dict(Notification.LEVEL_CHOICES):
        notifications = notifications.filter(level=level)

    paginator = Paginator(notifications, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(
        request,
        "dashboard/notifications/list.html",
        {
            "notifications": page_obj.object_list,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "unread_count": _notification_scope(request.user)
            .filter(is_read=False)
            .count(),
            "status": status,
            "level": level,
            "level_choices": Notification.LEVEL_CHOICES,
            "querystring": params.urlencode(),
            "can_create": request.user.is_superuser
            or request.user.has_perm("core.add_notification"),
        },
    )


@staff_required
@permission_required("core.add_notification", raise_exception=True)
def notification_create(request):
    form = NotificationCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        notification = Notification.objects.create(
            user=None,
            title=form.cleaned_data["title"],
            message=form.cleaned_data["message"],
            url=form.cleaned_data["url"],
            level=form.cleaned_data["level"],
        )
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Staff notification sent: {notification.title}",
            target=notification,
        )
        messages.success(request, "Notification sent to all staff accounts.")
        return redirect("dashboard:notification_list")

    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Send a notification",
            "eyebrow": "Notifications",
            "description": (
                "Send a dashboard notification to every active staff account. "
                "Use a relative dashboard path to make the notification actionable."
            ),
            "submit_label": "Send notification",
            "cancel_url": reverse("dashboard:notification_list"),
            "sections": [],
        },
    )


@staff_required
def notification_open(request, pk):
    notification = get_object_or_404(_notification_scope(request.user), pk=pk)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect(safe_next_url(notification.url, reverse("dashboard:notification_list")))


@staff_required
def notification_delete(request, pk):
    notification = get_object_or_404(_notification_scope(request.user), pk=pk)
    if notification.user_id is None and not request.user.is_superuser:
        messages.error(
            request,
            "Only a superuser can delete a notification sent to all staff.",
        )
        return redirect("dashboard:notification_list")

    if request.method == "POST":
        notification.delete()
        messages.success(request, "Notification deleted.")
        return redirect("dashboard:notification_list")

    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete notification",
            "object_label": notification.title,
            "object_type": "notification",
            "warning": "This notification will be removed from your inbox.",
            "cancel_url": reverse("dashboard:notification_list"),
        },
    )


@staff_required
@require_POST
def notification_mark_all_read(request):
    updated = _notification_scope(request.user).filter(is_read=False).update(
        is_read=True
    )
    messages.success(
        request,
        f"{updated} notification{'s' if updated != 1 else ''} marked as read.",
    )
    return redirect("dashboard:notification_list")


# ---------------------------------------------------------------------------
# Reports & analytics
# ---------------------------------------------------------------------------
@staff_required
def reports_index(request):
    from cms.models import BlogPost, FAQ, MediaAsset, Page, Testimonial

    today = timezone.localdate()
    can_view_sales = request.user.has_perm(
        "enquiries.view_enquiry"
    ) or request.user.has_perm("enquiries.view_customer")

    total_enquiries = Enquiry.objects.count()
    converted = Enquiry.objects.filter(status=Enquiry.STATUS_CONVERTED).count()
    open_enquiries = Enquiry.objects.filter(
        status__in=Enquiry.OPEN_STATUSES
    ).count()

    status_counts = dict(
        Enquiry.objects.values_list("status").annotate(total=Count("id"))
    )
    status_summary = [
        {
            "value": value,
            "label": label,
            "count": status_counts.get(value, 0),
            "percent": _percent(status_counts.get(value, 0), total_enquiries),
            "css": value,
        }
        for value, label in Enquiry.STATUS_CHOICES
    ]

    # Six-month enquiry trend, oldest first.
    def month_start(base, offset):
        index = base.month - 1 + offset
        return date(base.year + index // 12, index % 12 + 1, 1)

    this_month = today.replace(day=1)
    start_month = month_start(this_month, -5)
    monthly_rows = (
        Enquiry.objects.filter(created_at__date__gte=start_month)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )
    monthly_lookup = {
        row["month"].strftime("%Y-%m"): row["total"]
        for row in monthly_rows
        if row["month"]
    }
    months = []
    for offset in range(6):
        cursor = month_start(this_month, offset - 5)
        key = cursor.strftime("%Y-%m")
        months.append(
            {
                "key": key,
                "label": cursor.strftime("%b"),
                "year": cursor.strftime("%Y"),
                "count": monthly_lookup.get(key, 0),
            }
        )
    max_month = max((item["count"] for item in months), default=0)
    for item in months:
        item["width"] = round(item["count"] / max_month * 100) if max_month else 0

    categories = (
        Category.objects.annotate(
            product_total=Count("products", distinct=True),
            enquiry_total=Count("products__enquiries", distinct=True),
        )
        .order_by("-enquiry_total", "name")[:8]
    )
    max_category = max((item.enquiry_total for item in categories), default=0)
    category_rows = [
        {
            "name": category.name,
            "products": category.product_total,
            "enquiries": category.enquiry_total,
            "width": round(category.enquiry_total / max_category * 100)
            if max_category
            else 0,
        }
        for category in categories
    ]

    top_products = (
        Product.objects.annotate(enquiry_total=Count("enquiries"))
        .filter(enquiry_total__gt=0)
        .order_by("-enquiry_total", "name")[:6]
        if can_view_sales
        else Product.objects.none()
    )

    content = {
        "pages": Page.objects.count(),
        "published_pages": Page.objects.filter(status=Page.STATUS_PUBLISHED).count(),
        "posts": BlogPost.objects.count(),
        "published_posts": BlogPost.objects.filter(
            status=BlogPost.STATUS_PUBLISHED, published_at__lte=timezone.now()
        ).count(),
        "media": MediaAsset.objects.count(),
        "testimonials": Testimonial.objects.count(),
        "approved_testimonials": Testimonial.objects.filter(
            is_approved=True, is_published=True
        ).count(),
        "faqs": FAQ.objects.count(),
        "published_faqs": FAQ.objects.filter(is_published=True).count(),
    }

    return render(
        request,
        "dashboard/reports/index.html",
        {
            "can_view_sales": can_view_sales,
            "total_enquiries": total_enquiries,
            "converted": converted,
            "open_enquiries": open_enquiries,
            "conversion_rate": _percent(converted, total_enquiries),
            "customer_total": Customer.objects.count() if can_view_sales else None,
            "product_total": Product.objects.count(),
            "active_products": Product.objects.filter(active=True).count(),
            "category_total": Category.objects.count(),
            "status_summary": status_summary,
            "months": months,
            "category_rows": category_rows,
            "top_products": top_products,
            "content": content,
            "followups_due": Enquiry.objects.filter(
                follow_up_date__lte=today, status__in=Enquiry.OPEN_STATUSES
            ).count(),
            "new_enquiries": Enquiry.objects.filter(
                status=Enquiry.STATUS_NEW
            ).count(),
            "today": today,
        },
    )


@staff_required
def reports_export(request):
    from cms.models import BlogPost, Page

    response = _csv_response(f"spc-report-{timezone.localdate():%Y%m%d}.csv")
    writer = csv.writer(response)
    writer.writerow(["Sanjeev Power Controls — dashboard report"])
    writer.writerow(["Generated", timezone.localtime().strftime("%Y-%m-%d %H:%M")])
    writer.writerow(["Generated by", request.user.get_username()])
    writer.writerow([])

    can_view_sales = request.user.has_perm(
        "enquiries.view_enquiry"
    ) or request.user.has_perm("enquiries.view_customer")

    if can_view_sales:
        writer.writerow(["Enquiry pipeline", "Count"])
        total = Enquiry.objects.count()
        writer.writerow(["Total enquiries", total])
        for value, label in Enquiry.STATUS_CHOICES:
            writer.writerow(
                [label, Enquiry.objects.filter(status=value).count()]
            )
        writer.writerow(
            ["Conversion rate (%)", _percent(Enquiry.objects.filter(status=Enquiry.STATUS_CONVERTED).count(), total)]
        )
        writer.writerow(["Customers", Customer.objects.count()])
        writer.writerow(["Follow-ups due", Enquiry.objects.filter(
            follow_up_date__lte=timezone.localdate(),
            status__in=Enquiry.OPEN_STATUSES,
        ).count()])
        writer.writerow([])

        writer.writerow(["Product", "SKU", "Status", "Enquiries"])
        for product in Product.objects.annotate(
            enquiry_total=Count("enquiries")
        ).order_by("-enquiry_total", "name"):
            writer.writerow(
                [
                    product.name,
                    product.sku,
                    "Active" if product.active else "Inactive",
                    product.enquiry_total,
                ]
            )
        writer.writerow([])

    writer.writerow(["Catalogue", "Count"])
    writer.writerow(["Products", Product.objects.count()])
    writer.writerow(["Active products", Product.objects.filter(active=True).count()])
    writer.writerow(["Categories", Category.objects.count()])
    writer.writerow([])

    writer.writerow(["Website content", "Count"])
    writer.writerow(["Pages", Page.objects.count()])
    writer.writerow(["Published pages", Page.objects.filter(status=Page.STATUS_PUBLISHED).count()])
    writer.writerow(["Blog posts", BlogPost.objects.count()])
    writer.writerow(["Published posts", BlogPost.objects.filter(status=BlogPost.STATUS_PUBLISHED).count()])

    log_activity(
        request,
        ActivityLog.ACTION_EXPORT,
        "Exported dashboard report",
    )
    return response


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------
def _filtered_activity(request):
    logs = ActivityLog.objects.select_related("user")
    query = (request.GET.get("q") or "").strip()
    action = (request.GET.get("action") or "").strip()
    user_id = (request.GET.get("user") or "").strip()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()

    if query:
        logs = logs.filter(
            Q(description__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
        )
    if action in dict(ActivityLog.ACTION_CHOICES):
        logs = logs.filter(action=action)
    if user_id.isdigit():
        logs = logs.filter(user_id=int(user_id))
    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)

    return logs, {
        "query": query,
        "action": action,
        "selected_user": user_id,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
    }


@staff_required
@permission_required("core.view_activitylog", raise_exception=True)
def activity_list(request):
    logs, filters = _filtered_activity(request)
    paginator = Paginator(logs, 30)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(
        request,
        "dashboard/activity/list.html",
        {
            "logs": page_obj.object_list,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "all_count": ActivityLog.objects.count(),
            "action_choices": ActivityLog.ACTION_CHOICES,
            "staff_users": User.objects.filter(is_staff=True).order_by("username"),
            "querystring": params.urlencode(),
            **filters,
        },
    )


@staff_required
@permission_required("core.view_activitylog", raise_exception=True)
def activity_export(request):
    logs, filters = _filtered_activity(request)
    response = _csv_response(f"spc-activity-{timezone.localdate():%Y%m%d}.csv")
    writer = csv.writer(response)
    writer.writerow(
        ["Timestamp", "User", "Action", "Description", "Target type", "Target ID", "IP address"]
    )
    for log in logs:
        writer.writerow(
            [
                timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                _csv_safe(log.user.get_username() if log.user else "System"),
                log.get_action_display(),
                _csv_safe(log.description),
                _csv_safe(log.target_type),
                _csv_safe(log.target_id),
                _csv_safe(log.ip_address or ""),
            ]
        )
    log_activity(
        request,
        ActivityLog.ACTION_EXPORT,
        f"Exported {logs.count()} activity log record(s)",
    )
    return response


# ---------------------------------------------------------------------------
# Backup & maintenance
# ---------------------------------------------------------------------------
@superuser_required
def backup_index(request):
    engine = settings.DATABASES["default"]["ENGINE"]
    db_path = settings.DATABASES["default"].get("NAME")
    db_size = None
    try:
        if engine == "django.db.backends.sqlite3" and db_path and Path(db_path).exists():
            db_size = human_size(Path(db_path).stat().st_size)
    except OSError:
        db_size = None

    media_root = Path(settings.MEDIA_ROOT)
    media_size = 0
    media_files = 0
    if media_root.exists():
        for path in media_root.rglob("*"):
            if path.is_file():
                media_files += 1
                media_size += path.stat().st_size

    return render(
        request,
        "dashboard/backup/index.html",
        {
            "backups": _backup_files(),
            "engine": engine.rsplit(".", 1)[-1],
            "db_size": db_size,
            "media_files": media_files,
            "media_size": human_size(media_size),
            "backup_dir": str(_backup_dir()),
            "maintenance_mode": SiteSettings.load().maintenance_mode,
            "last_backup": (_backup_files() or [None])[0],
        },
    )


@superuser_required
@require_POST
def backup_create(request):
    directory = _backup_dir()
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    engine = settings.DATABASES["default"]["ENGINE"]
    try:
        if engine == "django.db.backends.sqlite3":
            db_path = Path(settings.DATABASES["default"]["NAME"])
            if not db_path.exists():
                raise FileNotFoundError("The SQLite database file was not found.")
            target = directory / f"spc-backup-{stamp}.sqlite3"
            source = sqlite3.connect(db_path)
            destination = sqlite3.connect(target)
            try:
                with destination:
                    source.backup(destination)
            finally:
                source.close()
                destination.close()
        else:
            target = directory / f"spc-backup-{stamp}.json"
            with target.open("w", encoding="utf-8") as handle:
                call_command(
                    "dumpdata",
                    exclude=["sessions", "contenttypes"],
                    indent=2,
                    stdout=handle,
                )
    except Exception as exc:  # Report a clean error instead of a 500 page.
        messages.error(request, f"Backup could not be created: {exc}")
        return redirect("dashboard:backup_index")

    log_activity(
        request,
        ActivityLog.ACTION_BACKUP,
        f"Backup created: {target.name} ({human_size(target.stat().st_size)})",
    )
    messages.success(
        request,
        f"Backup “{target.name}” created ({human_size(target.stat().st_size)}).",
    )
    return redirect("dashboard:backup_index")


@superuser_required
def backup_download(request, filename):
    path = _safe_backup_path(filename)
    log_activity(
        request,
        ActivityLog.ACTION_BACKUP,
        f"Backup downloaded: {path.name}",
    )
    response = FileResponse(
        open(path, "rb"), as_attachment=True, filename=path.name
    )
    return response


@superuser_required
def backup_delete(request, filename):
    path = _safe_backup_path(filename)
    if request.method == "POST":
        name = path.name
        try:
            path.unlink()
        except OSError as exc:
            messages.error(request, f"The backup could not be deleted: {exc}")
            return redirect("dashboard:backup_index")
        log_activity(
            request, ActivityLog.ACTION_BACKUP, f"Backup deleted: {name}"
        )
        messages.success(request, f"Backup “{name}” deleted.")
        return redirect("dashboard:backup_index")

    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete backup",
            "object_label": path.name,
            "object_type": "backup file",
            "warning": (
                "The backup file will be permanently removed from the server. "
                "Download a copy first if it may be needed for recovery."
            ),
            "cancel_url": reverse("dashboard:backup_index"),
        },
    )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@staff_required
def profile(request):
    user = request.user
    profile_form = ProfileForm(
        request.POST if request.method == "POST" and request.POST.get("form") == "profile" else None,
        instance=user,
    )
    password_form = DashboardPasswordChangeForm(
        user,
        request.POST if request.method == "POST" and request.POST.get("form") == "password" else None,
    )

    if request.method == "POST":
        if request.POST.get("form") == "profile":
            if profile_form.is_valid():
                profile_form.save()
                log_activity(
                    request,
                    ActivityLog.ACTION_UPDATE,
                    "Profile details updated",
                    target=user,
                )
                messages.success(request, "Your profile has been updated.")
                return redirect("dashboard:profile")
            messages.error(request, "Please correct the highlighted profile fields.")
        elif request.POST.get("form") == "password":
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                log_activity(
                    request,
                    ActivityLog.ACTION_SECURITY,
                    "Dashboard password changed",
                    target=user,
                )
                messages.success(request, "Your password has been changed.")
                return redirect("dashboard:profile")
            messages.error(request, "Please correct the highlighted password fields.")
        else:
            messages.error(request, "Unrecognised form submission.")
            return redirect("dashboard:profile")

    return render(
        request,
        "dashboard/profile.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "activity": user.activity_logs.select_related("user")[:8],
            "groups": user.groups.order_by("name"),
            "is_superuser": user.is_superuser,
        },
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class StaffLoginView(LoginView):
    template_name = "dashboard/login.html"
    authentication_form = StaffLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return safe_next_url(
            self.get_redirect_url(), reverse("dashboard:overview")
        )

    def form_valid(self, form):
        if not form.get_user().is_staff:
            form.add_error(
                None,
                "This account does not have staff access to the dashboard.",
            )
            return self.form_invalid(form)
        response = super().form_valid(form)
        log_activity(
            self.request,
            ActivityLog.ACTION_LOGIN,
            f"Signed in: {self.request.user.username}",
            target=self.request.user,
        )
        return response


class StaffLogoutView(LogoutView):
    next_page = "/admin-panel/login/"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            log_activity(
                request,
                ActivityLog.ACTION_LOGOUT,
                f"Signed out: {request.user.username}",
                target=request.user,
            )
        return super().dispatch(request, *args, **kwargs)


class StaffPasswordResetView(PasswordResetView):
    template_name = "dashboard/auth/password_reset.html"
    email_template_name = "dashboard/auth/password_reset_email.txt"
    subject_template_name = "dashboard/auth/password_reset_subject.txt"
    form_class = StaffPasswordResetForm
    success_url = reverse_lazy("dashboard:password_reset_done")
    extra_email_context = {"brand_name": "Sanjeev Power Controls"}


class StaffPasswordResetDoneView(PasswordResetDoneView):
    template_name = "dashboard/auth/password_reset_done.html"


class StaffPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "dashboard/auth/password_reset_confirm.html"
    form_class = SetPasswordForm
    success_url = reverse_lazy("dashboard:password_reset_complete")
    post_reset_login = False


class StaffPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "dashboard/auth/password_reset_complete.html"
