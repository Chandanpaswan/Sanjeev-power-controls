from urllib.parse import quote

from django.conf import settings
from django.db import models

DEFAULT_WHATSAPP_MESSAGE = (
    "Hello Sanjeev Power Controls, I would like to enquire about DG set parts."
)

DEFAULT_MAINTENANCE_MESSAGE = (
    "The website is temporarily unavailable while scheduled maintenance is completed. "
    "Please try again shortly."
)


class SiteSettings(models.Model):
    """Editable, database-backed website content.

    A single row (pk=1) is used so that staff can update the public site
    without touching code. Contact fields stay blank until verified details
    are supplied — templates show a clearly marked placeholder instead.
    """

    company_name = models.CharField(max_length=120, default="Sanjeev Power Controls")
    tagline = models.CharField(
        max_length=160, default="Powering Performance. Ensuring Reliability."
    )
    company_description = models.TextField(
        blank=True,
        default=(
            "Sanjeev Power Controls supplies DG set filtration, engine and electrical "
            "components for enquiry-led industrial requirements."
        ),
    )
    hero_heading = models.CharField(
        max_length=160, default="Reliable DG Set Parts. Built for Performance."
    )
    hero_description = models.TextField(
        default=(
            "Explore demonstration listings for filtration, engine and electrical "
            "components used in diesel generator sets. Share your part number and "
            "application, and the team can confirm the requirement before quoting."
        )
    )
    logo = models.ImageField(
        upload_to="branding/", blank=True,
        help_text="Optional replacement logo. Leave blank to use the built-in brand mark.",
    )
    favicon = models.ImageField(upload_to="branding/", blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(
        max_length=40,
        blank=True,
        help_text="Displayed exactly as entered, e.g. +91 98765 43210.",
    )
    whatsapp_number = models.CharField(
        max_length=30,
        blank=True,
        help_text="Digits only, including country code (e.g. 919876543210).",
    )
    business_address = models.TextField(
        blank=True, help_text="One address line per line."
    )
    hours = models.CharField(max_length=120, blank=True)
    map_embed_url = models.URLField(
        blank=True, help_text="Google Maps embed URL. Leave blank to show a placeholder."
    )
    footer_description = models.TextField(
        blank=True,
        default=(
            "A demonstration website presenting DG set filtration, engine and "
            "electrical parts for enquiry-led supply."
        ),
    )
    copyright_text = models.CharField(
        max_length=200, blank=True,
        help_text="Leave blank to use the company name and current year.",
    )
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)

    # SEO and site controls
    default_seo_title = models.CharField(max_length=160, blank=True)
    default_seo_description = models.CharField(max_length=320, blank=True)
    default_og_image = models.ImageField(upload_to="seo/", blank=True)
    google_analytics_id = models.CharField(
        max_length=40, blank=True,
        help_text="Optional GA4 measurement ID (G-XXXXXXXXXX). Analytics is loaded only when configured.",
    )
    allow_search_indexing = models.BooleanField(
        default=True, help_text="When disabled, public pages send noindex and robots.txt blocks crawling."
    )
    robots_extra = models.TextField(
        blank=True,
        help_text="Optional extra robots.txt lines. The sitemap and admin disallow rules are added automatically.",
    )
    maintenance_mode = models.BooleanField(
        default=False, help_text="Show a maintenance page to public visitors. Staff can still sign in."
    )
    maintenance_message = models.TextField(blank=True, default=DEFAULT_MAINTENANCE_MESSAGE)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "website settings"
        verbose_name_plural = "website settings"

    def __str__(self):
        return "Website settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def has_phone(self):
        return bool(self.contact_phone.strip())

    @property
    def tel_href(self):
        number = "".join(
            char for char in self.contact_phone if char.isdigit() or char == "+"
        )
        return f"tel:{number}" if number else ""

    @property
    def whatsapp_digits(self):
        return "".join(char for char in self.whatsapp_number if char.isdigit())

    @property
    def has_whatsapp(self):
        return len(self.whatsapp_digits) >= 8

    @property
    def whatsapp_enquiry_link(self):
        if not self.has_whatsapp:
            return ""
        return (
            f"https://wa.me/{self.whatsapp_digits}"
            f"?text={quote(DEFAULT_WHATSAPP_MESSAGE)}"
        )

    @property
    def address_lines(self):
        return [line.strip() for line in self.business_address.splitlines() if line.strip()]

    @property
    def social_links(self):
        links = [
            ("Facebook", self.facebook_url),
            ("Instagram", self.instagram_url),
            ("LinkedIn", self.linkedin_url),
            ("YouTube", self.youtube_url),
        ]
        return [(name, url) for name, url in links if url]

    @property
    def display_logo_url(self):
        return self.logo.url if self.logo else ""

    @property
    def display_favicon_url(self):
        return self.favicon.url if self.favicon else ""

    @property
    def copyright_line(self):
        if self.copyright_text.strip():
            return self.copyright_text
        return f"© {self.company_name}. All rights reserved."


class ActivityLog(models.Model):
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_EXPORT = "export"
    ACTION_BACKUP = "backup"
    ACTION_SECURITY = "security"
    ACTION_CHOICES = [
        (ACTION_CREATE, "Created"),
        (ACTION_UPDATE, "Updated"),
        (ACTION_DELETE, "Deleted"),
        (ACTION_LOGIN, "Signed in"),
        (ACTION_LOGOUT, "Signed out"),
        (ACTION_EXPORT, "Exported"),
        (ACTION_BACKUP, "Backup"),
        (ACTION_SECURITY, "Security"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    description = models.CharField(max_length=255)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["action", "-created_at"])]

    def __str__(self):
        return f"{self.get_action_display()} — {self.description}"


class Notification(models.Model):
    LEVEL_INFO = "info"
    LEVEL_SUCCESS = "success"
    LEVEL_WARNING = "warning"
    LEVEL_DANGER = "danger"
    LEVEL_CHOICES = [
        (LEVEL_INFO, "Information"),
        (LEVEL_SUCCESS, "Success"),
        (LEVEL_WARNING, "Warning"),
        (LEVEL_DANGER, "Urgent"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name="dashboard_notifications",
    )
    title = models.CharField(max_length=160)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=255, blank=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default=LEVEL_INFO)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
