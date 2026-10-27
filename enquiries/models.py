import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse

from products.models import Product


class Customer(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    name = models.CharField(max_length=160, help_text="Customer or company name.")
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    company_address = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_customers",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name"]), models.Index(fields=["email"])]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("dashboard:customer_detail", kwargs={"pk": self.pk})

    @property
    def enquiry_count(self):
        return self.enquiries.count()

    @property
    def status_css(self):
        return {
            self.STATUS_ACTIVE: "active",
            self.STATUS_INACTIVE: "closed",
            self.STATUS_ARCHIVED: "lost",
        }.get(self.status, "new")


class Enquiry(models.Model):
    STATUS_NEW = "new"
    STATUS_CONTACTED = "contacted"
    STATUS_QUALIFIED = "qualified"
    STATUS_QUOTATION_SENT = "quotation_sent"
    STATUS_FOLLOW_UP = "follow_up"
    STATUS_CONVERTED = "converted"
    STATUS_CLOSED = "closed"
    STATUS_LOST = "lost"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_QUALIFIED, "Qualified"),
        (STATUS_QUOTATION_SENT, "Quotation Sent"),
        (STATUS_FOLLOW_UP, "Follow-up Required"),
        (STATUS_CONVERTED, "Converted"),
        (STATUS_CLOSED, "Closed"),
        (STATUS_LOST, "Lost"),
    ]
    OPEN_STATUSES = [STATUS_NEW, STATUS_CONTACTED, STATUS_QUALIFIED, STATUS_QUOTATION_SENT, STATUS_FOLLOW_UP]

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    reference = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enquiries_submitted",
    )
    name = models.CharField(max_length=120)
    company = models.CharField(max_length=140, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enquiries",
    )
    message = models.TextField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True
    )
    priority = models.CharField(
        max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL, db_index=True
    )
    source = models.CharField(max_length=60, default="Website", blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_enquiries",
    )
    assigned_seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_enquiries_seller",
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="enquiries",
    )
    quantity = models.CharField(max_length=100, blank=True)
    follow_up_date = models.DateField(null=True, blank=True, db_index=True)
    internal_notes = models.TextField(
        blank=True,
        help_text="Private notes for staff only. Never shown on the public website.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "enquiries"
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["email"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["assigned_to", "status"]),
        ]

    def __str__(self):
        return f"{self.reference} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            for _ in range(10):
                candidate = f"SPC-{secrets.token_hex(3).upper()}"
                if not Enquiry.objects.filter(reference=candidate).exists():
                    self.reference = candidate
                    break
            else:
                raise RuntimeError("Could not generate a unique enquiry reference.")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("dashboard:enquiry_detail", kwargs={"pk": self.pk})

    @property
    def product_label(self):
        return self.product.name if self.product else "General enquiry"

    @property
    def status_css(self):
        return {
            self.STATUS_NEW: "new",
            self.STATUS_CONTACTED: "contacted",
            self.STATUS_QUALIFIED: "qualified",
            self.STATUS_QUOTATION_SENT: "quotation",
            self.STATUS_FOLLOW_UP: "followup",
            self.STATUS_CONVERTED: "converted",
            self.STATUS_CLOSED: "closed",
            self.STATUS_LOST: "lost",
        }.get(self.status, "new")

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_follow_up_due(self):
        from django.utils import timezone

        return bool(self.follow_up_date and self.is_open and self.follow_up_date <= timezone.localdate())


class EnquiryNote(models.Model):
    enquiry = models.ForeignKey(Enquiry, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="enquiry_notes",
    )
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note on {self.enquiry.reference}"
