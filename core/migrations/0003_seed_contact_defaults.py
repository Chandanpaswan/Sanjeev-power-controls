"""Populate the supplied Sanjeev Power Controls contact details.

Only details explicitly supplied by the business are written: Faridabad,
Haryana, India and the WhatsApp enquiry number. Street address, PIN code and
email remain blank until they are verified.
"""
from django.db import migrations

WHATSAPP_NUMBER = "917015907650"
LEGACY_WHATSAPP_NUMBERS = {"91701590750", "+91 701590750", "070159 07650"}


def seed_contact_defaults(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    site = SiteSettings.objects.filter(pk=1).first()
    if site is None:
        SiteSettings.objects.create(
            pk=1,
            city="Faridabad",
            state="Haryana",
            country="India",
            business_type="Diesel Generator (DG Set) Parts Manufacturing",
            whatsapp_number=WHATSAPP_NUMBER,
        )
        return

    changed = []
    defaults = {
        "city": "Faridabad",
        "state": "Haryana",
        "country": "India",
        "business_type": "Diesel Generator (DG Set) Parts Manufacturing",
    }
    for field, value in defaults.items():
        if not (getattr(site, field) or "").strip():
            setattr(site, field, value)
            changed.append(field)

    current = (site.whatsapp_number or "").strip()
    if not current or current in LEGACY_WHATSAPP_NUMBERS:
        site.whatsapp_number = WHATSAPP_NUMBER
        changed.append("whatsapp_number")

    if changed:
        site.save(update_fields=changed)


def unseed_contact_defaults(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    site = SiteSettings.objects.filter(pk=1).first()
    if site is None:
        return
    changed = []
    if site.city == "Faridabad":
        site.city = ""
        changed.append("city")
    if site.state == "Haryana":
        site.state = ""
        changed.append("state")
    if site.country == "India":
        site.country = ""
        changed.append("country")
    if site.whatsapp_number == WHATSAPP_NUMBER:
        site.whatsapp_number = ""
        changed.append("whatsapp_number")
    if changed:
        site.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_sitesettings_business_type_sitesettings_city_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_contact_defaults, unseed_contact_defaults),
    ]
