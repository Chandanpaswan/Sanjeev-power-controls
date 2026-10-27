import secrets
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from products.models import Product


class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    company_information = models.TextField(blank=True)
    contact_preferences = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'accounts'

    def __str__(self):
        return f"Customer profile - {self.user}"


class SellerProfile(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_SUSPENDED = "suspended"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_SUSPENDED, "Suspended"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_profile")
    business_name = models.CharField(max_length=160)
    business_address = models.TextField()
    business_description = models.TextField(blank=True)
    product_categories_handled = models.CharField(max_length=200, blank=True)
    business_documentation = models.FileField(upload_to="seller_docs/", blank=True, null=True)
    approval_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_sellers",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'accounts'

    def __str__(self):
        return f"{self.business_name} - {self.approval_status}"


class SellerProductAssignment(models.Model):
    seller = models.ForeignKey('accounts.SellerProfile', on_delete=models.CASCADE, related_name="assignments")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="seller_assignments")
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        app_label = 'accounts'
        unique_together = [["seller", "product"]]

    def __str__(self):
        return f"{self.seller} -> {self.product}"


class Quotation(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED_FOR_APPROVAL = "submitted_for_approval"
    STATUS_APPROVED = "approved"
    STATUS_SENT = "sent"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED_FOR_APPROVAL, "Submitted for Approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_SENT, "Sent"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_EXPIRED, "Expired"),
    ]

    quotation_number = models.CharField(max_length=30, unique=True, editable=False)
    enquiry = models.ForeignKey("enquiries.Enquiry", on_delete=models.CASCADE, related_name="quotations")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_quotations")
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="prepared_quotations")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    taxes = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    validity_date = models.DateField(null=True, blank=True)
    terms_and_conditions = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'accounts'
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.quotation_number:
            for _ in range(10):
                candidate = f"QT-{secrets.token_hex(4).upper()}"
                if not Quotation.objects.filter(quotation_number=candidate).exists():
                    self.quotation_number = candidate
                    break
            else:
                raise RuntimeError("Could not generate a unique quotation number.")
        # Calculate total
        if self.unit_price and self.quantity:
            subtotal = self.unit_price * self.quantity
            self.total_amount = subtotal + self.taxes - self.discount
        super().save(*args, **kwargs)

    def __str__(self):
        return self.quotation_number


class QuotationLineItem(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="line_items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        app_label = 'accounts'

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)
