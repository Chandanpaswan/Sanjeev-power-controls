"""Load safe, clearly labelled demonstration data.

The command is idempotent: running it again updates the demo records instead
of duplicating them. It never deletes enquiries and never overwrites a product
image that staff have uploaded through the dashboard.

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --reset-settings
"""
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from cms.models import MenuItem, Page
from core.models import SiteSettings
from products.models import Category, Product

from .setup_roles import apply_roles

DEMO_IMAGE_DIR = Path(settings.BASE_DIR) / "static" / "images" / "products" / "demo"

CATEGORIES = [
    {
        "name": "Filtration",
        "description": (
            "Air, lubricant and fuel filtration components used during routine "
            "diesel generator maintenance. Demonstration category."
        ),
    },
    {
        "name": "Engine Spares",
        "description": (
            "Engine service kits and spare components. Demonstration category — "
            "contents are confirmed per enquiry."
        ),
    },
    {
        "name": "Electrical Components",
        "description": (
            "Alternator-related and electrical parts for generator applications. "
            "Demonstration category."
        ),
    },
    {
        "name": "Gaskets & Seals",
        "description": (
            "Empty demonstration category, included so the safe-deletion rule can "
            "be demonstrated in the dashboard."
        ),
    },
]

PRODUCTS = [
    {
        "name": "DG Set Air Filter",
        "sku": "DEMO-AF-001",
        "category": "Filtration",
        "featured": True,
        "short_description": (
            "Illustrative air intake filter element for diesel generator sets. "
            "Part number and dimensions to be confirmed."
        ),
        "description": (
            "A demonstration record for an air intake filter element used during "
            "DG set servicing. The public listing shows how a filtration product "
            "is presented: category, reference, description and a structured "
            "specification table.\n\n"
            "No dimensions, engine compatibility, efficiency rating or brand "
            "cross-reference is claimed. Every specification must be confirmed "
            "against the actual requirement before a quotation is issued."
        ),
        "specifications": (
            "Element type: Pleated cylindrical (illustrative)\n"
            "Application: DG set intake filtration (demo)\n"
            "Dimensions: To be confirmed\n"
            "Part number: To be confirmed\n"
            "Operating environment: Industrial / dusty (illustrative)\n"
            "Note: Demonstration specification — verify before ordering"
        ),
        "image": "demo-air-filter.png",
    },
    {
        "name": "Diesel Engine Oil Filter",
        "sku": "DEMO-OF-002",
        "category": "Filtration",
        "featured": True,
        "short_description": (
            "Illustrative spin-on lubricant filter for diesel engine servicing. "
            "Thread size and bypass rating to be confirmed."
        ),
        "description": (
            "A demonstration record for a spin-on engine oil filter. It shows how "
            "a service item can be grouped under filtration and linked to an "
            "enquiry form from both the catalogue and the product page.\n\n"
            "Compatibility with a specific engine model is not stated. Confirm the "
            "thread, seal, bypass specification and service interval before use."
        ),
        "specifications": (
            "Element type: Spin-on lubricant filter (illustrative)\n"
            "Application: Diesel engine lubrication (demo)\n"
            "Thread size: To be confirmed\n"
            "Bypass rating: To be confirmed\n"
            "Part number: To be confirmed\n"
            "Note: Demonstration specification — verify before ordering"
        ),
        "image": "demo-oil-filter.png",
    },
    {
        "name": "Fuel Filter Assembly",
        "sku": "DEMO-FF-003",
        "category": "Filtration",
        "featured": False,
        "short_description": (
            "Illustrative fuel filtration assembly with a serviceable element. "
            "Housing, connections and filtration rating to be confirmed."
        ),
        "description": (
            "A demonstration record for a fuel filter assembly. The listing is "
            "intended to show how an assembly with multiple components can be "
            "described without inventing connection sizes or filtration figures.\n\n"
            "Confirm the housing type, inlet/outlet arrangement, water separation "
            "requirements and element part number with the business before "
            "ordering."
        ),
        "specifications": (
            "Assembly type: Fuel filter with serviceable element (illustrative)\n"
            "Application: Diesel fuel filtration (demo)\n"
            "Connections: To be confirmed\n"
            "Filtration rating: To be confirmed\n"
            "Element part number: To be confirmed\n"
            "Note: Demonstration specification — verify before ordering"
        ),
        "image": "demo-fuel-filter.png",
    },
    {
        "name": "Generator Alternator Component",
        "sku": "DEMO-ALT-004",
        "category": "Electrical Components",
        "featured": True,
        "short_description": (
            "Illustrative alternator-related component for generator applications. "
            "Electrical ratings and mounting details to be confirmed."
        ),
        "description": (
            "A demonstration record for an alternator-related component. It shows "
            "how an electrical part is presented separately from filtration and "
            "engine spares, with the enquiry path used to capture ratings and "
            "mounting details.\n\n"
            "No output rating, voltage, insulation class, mounting pattern or "
            "compatibility with a specific alternator is claimed. These details "
            "must be confirmed before supply."
        ),
        "specifications": (
            "Component type: Alternator-related part (illustrative)\n"
            "Application: Generator electrical system (demo)\n"
            "Electrical rating: To be confirmed\n"
            "Mounting details: To be confirmed\n"
            "Part number: To be confirmed\n"
            "Note: Demonstration specification — verify before ordering"
        ),
        "image": "demo-alternator.png",
    },
    {
        "name": "DG Set Engine Spare Parts Kit",
        "sku": "DEMO-KIT-005",
        "category": "Engine Spares",
        "featured": False,
        "short_description": (
            "Illustrative service kit grouping common engine spare items. Kit "
            "contents and quantities are confirmed per enquiry."
        ),
        "description": (
            "A demonstration record for a configurable engine spare parts kit. "
            "The listing illustrates how a kit can be presented while making clear "
            "that the contents are assembled against a specific requirement.\n\n"
            "The kit contents shown in this demo are examples only. Quantities, "
            "part numbers and included items must be agreed with the customer "
            "before a quotation is prepared."
        ),
        "specifications": (
            "Kit type: Configurable engine service kit (illustrative)\n"
            "Application: DG set engine maintenance (demo)\n"
            "Contents: Confirmed per enquiry\n"
            "Quantities: Confirmed per enquiry\n"
            "Part numbers: To be confirmed\n"
            "Note: Demonstration specification — verify before ordering"
        ),
        "image": "demo-parts-kit.png",
    },
]

SITE_DEFAULTS = {
    "company_name": "Sanjeev Power Controls",
    "tagline": "Powering Performance. Ensuring Reliability.",
    "business_type": "Diesel Generator (DG Set) Parts Manufacturing",
    "city": "Faridabad",
    "state": "Haryana",
    "country": "India",
    "whatsapp_number": "917015907650",
    "hero_heading": "Reliable DG Set Parts. Built for Performance.",
    "hero_description": (
        "Explore demonstration listings for filtration, engine and electrical "
        "components used in diesel generator sets. Share your part number and "
        "application, and the team can confirm the requirement before quoting."
    ),
    "footer_description": (
        "A demonstration website presenting DG set filtration, engine and "
        "electrical parts for enquiry-led supply. Contact details and technical "
        "claims await client verification."
    ),
}

# Managed pages mirror the built-in layouts. They are only created when missing,
# so content edited in the dashboard is never overwritten by re-running the seed.
PAGES = [
    {
        "slug": "home",
        "title": "Home",
        "hero_eyebrow": "DG set parts manufacturer",
        "hero_heading": "Reliable DG Set Parts. Built for Performance.",
        "hero_description": (
            "Explore demonstration listings for filtration, engine and electrical "
            "components used in diesel generator sets. Share your part number and "
            "application, and the team can confirm the requirement before quoting."
        ),
    },
    {
        "slug": "about",
        "title": "About Us",
        "hero_eyebrow": "Company profile",
        "hero_heading": "A parts business built around verification.",
        "hero_description": (
            "This page demonstrates the company story structure. Verified history, "
            "facility details and certifications have not been supplied, so they "
            "are deliberately shown as placeholders rather than invented."
        ),
    },
    {
        "slug": "quality",
        "title": "Quality & Applications",
        "hero_eyebrow": "Quality & applications",
        "hero_heading": "Check the part against the requirement.",
        "hero_description": (
            "A proposed workflow for capturing requirements, verifying components "
            "and recording the checks performed. Certification, testing capability "
            "and approvals remain unverified until the client supplies evidence."
        ),
    },
    {
        "slug": "contact",
        "title": "Contact Us",
        "hero_eyebrow": "Contact",
        "hero_heading": "Tell us what the generator needs.",
        "hero_description": (
            "Share the product interest, engine details and quantity. This demo "
            "saves the enquiry to a local database and records a reference number "
            "for follow-up."
        ),
    },
]

HEADER_MENU = [
    ("Home", "core:home"),
    ("About Us", "core:about"),
    ("Products", "products:list"),
    ("Quality & Applications", "core:quality"),
    ("Blog", "blog:list"),
    ("Contact Us", "core:contact"),
]

FOOTER_MENU = [
    ("Home", "core:home"),
    ("About Us", "core:about"),
    ("Products", "products:list"),
    ("Quality & Applications", "core:quality"),
    ("Contact Us", "core:contact"),
    ("Privacy", "core:privacy"),
    ("Terms", "core:terms"),
]


class Command(BaseCommand):
    help = "Load clearly labelled demonstration categories, products and groups."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-settings",
            action="store_true",
            help="Overwrite the editable website settings with the demo defaults.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        categories = self._seed_categories()
        products = self._seed_products(categories)
        self._seed_settings(reset=options["reset_settings"])
        pages = self._seed_pages()
        menu_count = self._seed_menu()
        roles = apply_roles(verbosity=1)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data loaded."))
        self.stdout.write(f"  Categories : {len(categories)}")
        self.stdout.write(f"  Products   : {len(products)}")
        self.stdout.write(f"  Pages      : {len(pages)}")
        self.stdout.write(f"  Menu items : {menu_count}")
        self.stdout.write(
            "  Settings   : "
            f"{'reset to demo defaults' if options['reset_settings'] else 'created if missing (existing values kept)'}"
        )
        self.stdout.write(f"  Roles      : {', '.join(role['name'] for role in roles)}")
        self.stdout.write("")
        self.stdout.write(
            "Create an admin account with: python manage.py createsuperuser"
        )
        self.stdout.write(
            "Then sign in at: http://127.0.0.1:8000/admin/login/"
        )

    # ------------------------------------------------------------------
    def _seed_categories(self):
        result = {}
        for row in CATEGORIES:
            category, created = Category.objects.update_or_create(
                name=row["name"],
                defaults={"description": row["description"]},
            )
            result[row["name"]] = category
            action = "created" if created else "updated"
            self.stdout.write(f"  category {action}: {category.name}")
        return result

    def _seed_products(self, categories):
        result = []
        for row in PRODUCTS:
            category = categories[row["category"]]
            defaults = {
                "name": row["name"],
                "slug": slugify(row["name"]),
                "category": category,
                "short_description": row["short_description"],
                "description": row["description"],
                "specifications": row["specifications"],
                "featured": row["featured"],
                "active": True,
            }
            product, created = Product.objects.update_or_create(
                sku=row["sku"],
                defaults=defaults,
            )
            self._attach_demo_image(product, row["image"])
            result.append(product)
            action = "created" if created else "updated"
            self.stdout.write(f"  product {action}: {product.sku} — {product.name}")
        return result

    def _attach_demo_image(self, product, filename):
        source = DEMO_IMAGE_DIR / filename
        if not source.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"  image missing, skipped: {source.relative_to(settings.BASE_DIR)}"
                )
            )
            return

        storage = product.image.storage
        target_name = f"products/{filename}"
        if product.image and storage.exists(product.image.name):
            return
        if storage.exists(target_name):
            product.image.name = target_name
            product.save(update_fields=["image", "updated_at"])
            return

        with source.open("rb") as handle:
            product.image.save(filename, ContentFile(handle.read()), save=True)

    def _seed_settings(self, reset=False):
        site = SiteSettings.load()
        # Older demo builds inserted placeholder contact details. Clear those
        # exact values so the public site shows its "not verified" placeholders
        # instead of presenting invented information as real.
        legacy_placeholders = {
            "contact_email": "seo.chandanpaswan@gmail.com",
            "contact_phone": "+91 701590750",
        }
        scrubbed = False
        for field, value in legacy_placeholders.items():
            if getattr(site, field, "") == value:
                setattr(site, field, "")
                scrubbed = True
        if site.whatsapp_number in {
            "91701590750",
            "+91 701590750",
            "070159 07650",
        }:
            site.whatsapp_number = "917015907650"
            scrubbed = True
        if scrubbed:
            site.save()
            self.stdout.write("  settings: corrected placeholder contact details")
        if reset or not site.updated_at:
            for field, value in SITE_DEFAULTS.items():
                setattr(site, field, value)
            site.save()
            self.stdout.write("  settings: demo defaults applied")
        elif not SiteSettings.objects.filter(pk=1).exists():
            site.save()
        else:
            changed = False
            for field, value in SITE_DEFAULTS.items():
                current = getattr(site, field, "")
                if not current:
                    setattr(site, field, value)
                    changed = True
            if changed:
                site.save()
                self.stdout.write("  settings: blank fields filled with demo defaults")
            else:
                self.stdout.write("  settings: existing values kept")

    def _seed_pages(self):
        pages = []
        for row in PAGES:
            page, created = Page.objects.get_or_create(
                slug=row["slug"],
                defaults={
                    "title": row["title"],
                    "hero_eyebrow": row["hero_eyebrow"],
                    "hero_heading": row["hero_heading"],
                    "hero_description": row["hero_description"],
                    "status": Page.STATUS_PUBLISHED,
                },
            )
            pages.append(page)
            action = "created" if created else "kept"
            self.stdout.write(f"  page {action}: /{page.slug}/ — {page.title}")
        return pages

    def _seed_menu(self):
        if MenuItem.objects.exists():
            count = MenuItem.objects.count()
            self.stdout.write(f"  menu: {count} item(s) already configured")
            return count

        created = 0
        for order, (label, url_name) in enumerate(HEADER_MENU, start=1):
            MenuItem.objects.create(
                label=label,
                url_name=url_name,
                location=MenuItem.LOCATION_HEADER,
                order=order * 10,
            )
            created += 1
        for order, (label, url_name) in enumerate(FOOTER_MENU, start=1):
            MenuItem.objects.create(
                label=label,
                url_name=url_name,
                location=MenuItem.LOCATION_FOOTER,
                order=order * 10,
            )
            created += 1
        self.stdout.write(f"  menu: {created} item(s) created")
        return created
