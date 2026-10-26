"""Create or refresh the five standard dashboard roles.

The roles map to Django groups and model permissions, so every check is
enforced on the server. Run this after migrations and whenever a new model is
added:

    python manage.py setup_roles

Existing groups with the same names have their permissions refreshed. Staff
assignments are never changed.
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

ALL_PERMISSION_APPS = ("cms", "core", "enquiries", "products", "auth")

ROLE_RULES = {
    "Super Admin": {
        "all_apps": ALL_PERMISSION_APPS,
        "description": "Complete dashboard access, including staff, roles and reports.",
    },
    "Content Manager": {
        "all_apps": ("cms",),
        "extra": (
            "core.view_sitesettings",
            "core.change_sitesettings",
            "core.view_activitylog",
            "core.view_notification",
            "products.view_product",
            "products.view_category",
        ),
        "description": "Pages, blog, media, testimonials, FAQs, banners, menus and site content.",
    },
    "Product Manager": {
        "all_apps": ("products",),
        "extra": (
            "cms.view_mediaasset",
            "cms.add_mediaasset",
            "cms.change_mediaasset",
            "core.view_sitesettings",
            "core.view_activitylog",
        ),
        "description": "Products, categories, gallery images and catalogue media.",
    },
    "Sales Manager": {
        "all_apps": ("enquiries",),
        "extra": (
            "cms.view_page",
            "cms.view_blogpost",
            "products.view_product",
            "products.view_category",
            "core.view_activitylog",
            "core.view_notification",
        ),
        "description": "Enquiries, customers, follow-up, conversion and sales reports.",
    },
    "Viewer / Analyst": {
        "view_only_apps": ("cms", "core", "enquiries", "products"),
        "description": "Read-only access to content, catalogue, enquiries and reports.",
    },
}


def _permission_queryset(rule):
    queryset = Permission.objects.none()
    if rule.get("all_apps"):
        queryset = queryset | Permission.objects.filter(
            content_type__app_label__in=rule["all_apps"]
        )
    if rule.get("view_only_apps"):
        queryset = queryset | Permission.objects.filter(
            content_type__app_label__in=rule["view_only_apps"],
            codename__startswith="view_",
        )
    extra = list(rule.get("extra", ()))
    if extra:
        labels = [entry.split(".", 1) for entry in extra]
        from django.db.models import Q

        query = Q()
        for app_label, codename in labels:
            query |= Q(
                content_type__app_label=app_label, codename=codename
            )
        queryset = queryset | Permission.objects.filter(query)
    return queryset.distinct()


@transaction.atomic
def apply_roles(verbosity=1, stdout=None):
    """Create/refresh the standard roles. Returns a list of result dicts."""
    results = []
    for name, rule in ROLE_RULES.items():
        group, _created = Group.objects.get_or_create(name=name)
        permissions = list(_permission_queryset(rule))
        group.permissions.set(permissions)
        results.append({"name": name, "count": len(permissions), "rule": rule})
        if stdout:
            stdout.write(
                f"  role: {name} ({len(permissions)} permissions)"
            )
    return results


class Command(BaseCommand):
    help = "Create or refresh the standard dashboard roles."

    @transaction.atomic
    def handle(self, *args, **options):
        results = apply_roles(verbosity=1, stdout=self.stdout)
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Roles ready: {len(results)} standard role(s).")
        )
        for result in results:
            self.stdout.write(
                f"  {result['name']}: {result['rule']['description']}"
            )
        self.stdout.write("")
        self.stdout.write(
            "Assign roles to staff accounts under Staff & Roles in the dashboard."
        )
