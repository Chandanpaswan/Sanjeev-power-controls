from pathlib import Path

from django.db import models
from django.templatetags.static import static
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    image_asset = models.ForeignKey(
        "cms.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="product_categories",
    )
    is_active = models.BooleanField(
        default=True, help_text="Inactive categories are hidden from the public catalogue."
    )
    seo_title = models.CharField(max_length=160, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:80] or "category"
            slug = base
            counter = 2
            while Category.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def image_url(self):
        if self.image_asset and self.image_asset.file:
            return self.image_asset.file.url
        return self.image.url if self.image else ""


class Product(models.Model):
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    sku = models.CharField(
        max_length=60,
        unique=True,
        help_text="Internal part or reference code. Demo values are clearly labelled.",
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    short_description = models.CharField(
        max_length=240,
        help_text="One or two lines shown on catalogue cards.",
    )
    description = models.TextField()
    features = models.TextField(
        blank=True, help_text="One product feature per line."
    )
    specifications = models.TextField(
        blank=True,
        help_text="One specification per line, in the format: Label: Value",
    )
    image = models.ImageField(upload_to="products/", blank=True)
    image_asset = models.ForeignKey(
        "cms.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="products",
        help_text="Select an existing image from the media library, or upload one above.",
    )
    image_alt = models.CharField(max_length=240, blank=True)
    featured = models.BooleanField(default=False)
    active = models.BooleanField(
        default=True, help_text="Inactive products are hidden from the public website."
    )

    # SEO
    seo_title = models.CharField(max_length=160, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    seo_keywords = models.CharField(max_length=240, blank=True)
    canonical_url = models.URLField(blank=True)
    og_image = models.ImageField(upload_to="products/seo/", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-featured", "name"]
        indexes = [
            models.Index(fields=["active", "featured"]),
            models.Index(fields=["active", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:140] or "product"
            slug = base
            counter = 2
            while Product.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("products:detail", kwargs={"slug": self.slug})

    def enquiry_url(self):
        return f"{reverse('core:contact')}?product={self.slug}"

    @property
    def display_image_url(self):
        if self.image_asset and self.image_asset.file:
            return self.image_asset.file.url
        if not self.image:
            return ""
        name = self.image.name
        # Demo fixtures also ship in static/, so preview deployments without
        # persistent upload storage still render the catalogue images.
        if name.startswith("products/demo-"):
            try:
                if not self.image.storage.exists(name):
                    return static(f"images/products/demo/{Path(name).name}")
            except Exception:
                return static(f"images/products/demo/{Path(name).name}")
        return self.image.url

    @property
    def display_alt(self):
        return (
            self.image_alt
            or (self.image_asset.alt_text if self.image_asset else "")
            or f"Illustrative image of {self.name}"
        )

    @property
    def specification_rows(self):
        rows = []
        for line in self.specifications.splitlines():
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                label, value = line.split(":", 1)
            else:
                label, value = "Specification", line
            rows.append((label.strip(), value.strip()))
        return rows

    @property
    def feature_list(self):
        return [line.strip() for line in (self.features or "").splitlines() if line.strip()]


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="gallery")
    image = models.ImageField(upload_to="products/gallery/", blank=True)
    asset = models.ForeignKey(
        "cms.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="product_gallery_images",
    )
    alt_text = models.CharField(max_length=240, blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return f"{self.product.name} — gallery image {self.pk}"

    @property
    def url(self):
        if self.asset and self.asset.file:
            return self.asset.file.url
        return self.image.url if self.image else ""

    @property
    def alt(self):
        return self.alt_text or (self.asset.alt_text if self.asset else "") or self.product.name
