"""Focused tests for contact settings and WhatsApp enquiry links."""
import re
from urllib.parse import parse_qs, unquote, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from products.models import Category, Product

from .forms import ContactInfoForm
from .models import (
    SiteSettings,
    format_whatsapp_number,
    normalize_whatsapp_number,
    whatsapp_url,
)

User = get_user_model()


class WhatsAppNumberTests(TestCase):
    def test_normalises_common_indian_formats(self):
        for value in (
            "917015907650",
            "+91 70159 07650",
            "+91-70159-07650",
            "070159 07650",
            "70159 07650",
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_whatsapp_number(value), "917015907650")

    def test_readable_display_format(self):
        self.assertEqual(
            format_whatsapp_number("917015907650"), "+91 70159 07650"
        )
        self.assertEqual(format_whatsapp_number(""), "")

    def test_url_encodes_message_and_omits_empty_number(self):
        url = whatsapp_url("917015907650", "Hello & welcome")
        self.assertTrue(url.startswith("https://wa.me/917015907650?text="))
        parsed = urlparse(url)
        self.assertEqual(
            parse_qs(parsed.query)["text"], ["Hello & welcome"]
        )
        self.assertNotIn(" ", url)
        self.assertEqual(whatsapp_url("", "Hello"), "")


class SiteSettingsContactTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.load()
        self.site.company_name = "Sanjeev Power Controls"
        self.site.business_type = "Diesel Generator (DG Set) Parts Manufacturing"
        self.site.whatsapp_number = "917015907650"
        self.site.business_address = ""
        self.site.city = "Faridabad"
        self.site.state = "Haryana"
        self.site.country = "India"
        self.site.pin_code = ""
        self.site.map_embed_url = ""
        self.site.save()

    def test_locality_address_does_not_invent_street_or_pin(self):
        self.assertEqual(self.site.locality_line, "Faridabad, Haryana, India")
        self.assertEqual(
            self.site.address_lines, ["Faridabad, Haryana, India"]
        )
        self.assertNotIn("Map", self.site.address_lines)
        self.assertTrue(self.site.has_address)

    def test_address_lines_avoid_duplicating_locality(self):
        self.site.business_address = "Plot 1\nFaridabad, Haryana, India"
        self.site.save()
        self.assertEqual(
            self.site.address_lines, ["Plot 1", "Faridabad, Haryana, India"]
        )

    def test_verified_pin_code_is_appended_once(self):
        self.site.pin_code = "121001"
        self.site.save()
        self.assertEqual(
            self.site.address_lines,
            ["Faridabad, Haryana, India - 121001"],
        )

        self.site.business_address = "Plot 1, 121001"
        self.site.save()
        self.assertEqual(
            self.site.address_lines,
            ["Plot 1, 121001", "Faridabad, Haryana, India"],
        )

    def test_general_and_contact_links_use_readable_number(self):
        self.assertTrue(
            self.site.whatsapp_enquiry_link.startswith(
                "https://wa.me/917015907650?text="
            )
        )
        self.assertTrue(
            self.site.contact_whatsapp_link.startswith(
                "https://wa.me/917015907650?text="
            )
        )
        self.assertEqual(self.site.whatsapp_display, "+91 70159 07650")


class ContactFormTests(TestCase):
    def test_form_normalises_whatsapp_number_and_locality(self):
        site = SiteSettings.load()
        form = ContactInfoForm(
            data={
                "company_name": "Sanjeev Power Controls",
                "business_type": "Diesel Generator (DG Set) Parts Manufacturing",
                "contact_email": "",
                "contact_phone": "",
                "whatsapp_number": "+91 70159 07650",
                "business_address": "  ",
                "city": " Faridabad ",
                "state": " Haryana ",
                "country": " India ",
                "pin_code": " ",
                "hours": "",
                "map_embed_url": "",
            },
            instance=site,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.whatsapp_number, "917015907650")
        self.assertEqual(saved.city, "Faridabad")
        self.assertEqual(saved.state, "Haryana")
        self.assertEqual(saved.country, "India")
        self.assertEqual(saved.pin_code, "")

    def test_form_rejects_invalid_whatsapp_number(self):
        form = ContactInfoForm(
            data={
                "company_name": "Sanjeev Power Controls",
                "whatsapp_number": "123",
            },
            instance=SiteSettings.load(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("whatsapp_number", form.errors)


class PublicWhatsAppRenderTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.load()
        self.site.company_name = "Sanjeev Power Controls"
        self.site.whatsapp_number = "917015907650"
        self.site.business_address = ""
        self.site.city = "Faridabad"
        self.site.state = "Haryana"
        self.site.country = "India"
        self.site.pin_code = ""
        self.site.map_embed_url = ""
        self.site.save()

        self.category = Category.objects.create(
            name="Filtration", description="Demo category"
        )
        self.product = Product.objects.create(
            name="Demo Air Filter",
            sku="SPC-AF-001",
            category=self.category,
            short_description="Demonstration air filter listing.",
            description="Demonstration product used by the test suite.",
            active=True,
        )

    def _whatsapp_hrefs(self, response):
        html = response.content.decode()
        return [
            href.replace("&amp;", "&")
            for href in re.findall(r'href="(https://wa\.me/[^"]+)"', html)
        ]

    def test_header_footer_and_floating_button_on_home(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        hrefs = self._whatsapp_hrefs(response)
        self.assertTrue(hrefs)
        self.assertIn("+91 70159 07650", response.content.decode())
        self.assertIn("Faridabad, Haryana, India", response.content.decode())
        self.assertIn("Diesel Generator (DG Set) Parts Manufacturing", response.content.decode())

    def test_product_card_message_includes_sku_and_product_url(self):
        response = self.client.get(reverse("products:list"))
        self.assertEqual(response.status_code, 200)
        hrefs = self._whatsapp_hrefs(response)
        product_href = next(
            href for href in hrefs if "SPC-AF-001" in unquote(href)
        )
        message = parse_qs(urlparse(product_href).query)["text"][0]
        self.assertIn("Sanjeev Power Controls", message)
        self.assertIn("Demo Air Filter", message)
        self.assertIn("SKU: SPC-AF-001", message)
        self.assertIn(
            f"http://testserver{self.product.get_absolute_url()}", message
        )
        self.assertIn("specifications", message)
        self.assertIn("pricing", message)

    def test_product_detail_and_contact_page_links(self):
        detail = self.client.get(self.product.get_absolute_url())
        self.assertEqual(detail.status_code, 200)
        detail_hrefs = self._whatsapp_hrefs(detail)
        self.assertTrue(any("SPC-AF-001" in unquote(h) for h in detail_hrefs))

        contact = self.client.get(reverse("core:contact"))
        self.assertEqual(contact.status_code, 200)
        contact_hrefs = self._whatsapp_hrefs(contact)
        self.assertTrue(contact_hrefs)
        messages = [
            parse_qs(urlparse(href).query)["text"][0]
            for href in contact_hrefs
        ]
        self.assertTrue(
            any("DG Set parts requirements" in message for message in messages)
        )
        html = contact.content.decode()
        self.assertIn("Faridabad, Haryana, India", html)
        self.assertIn("confirmed locality only", html)
        self.assertNotIn("<iframe", html)


class DashboardContactSettingsTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.client.force_login(self.superuser)

    def test_admin_can_update_contact_details_and_public_site_reflects_them(self):
        response = self.client.post(
            reverse("dashboard:contact_info"),
            {
                "company_name": "Sanjeev Power Controls",
                "business_type": "Diesel Generator (DG Set) Parts Manufacturing",
                "contact_email": "",
                "contact_phone": "",
                "whatsapp_number": "+91 70159 07650",
                "business_address": "",
                "city": "Faridabad",
                "state": "Haryana",
                "country": "India",
                "pin_code": "",
                "hours": "",
                "map_embed_url": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        site = SiteSettings.load()
        self.assertEqual(site.whatsapp_number, "917015907650")
        self.assertEqual(site.locality_line, "Faridabad, Haryana, India")

        public = self.client.get(reverse("core:contact"))
        html = public.content.decode()
        self.assertIn("+91 70159 07650", html)
        self.assertIn("Faridabad, Haryana, India", html)
