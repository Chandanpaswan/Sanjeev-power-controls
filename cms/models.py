from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.text import slugify

from core.utils import sanitize_html


def media_upload_to(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"library/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{suffix}"


def image_upload_to(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"cms/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{suffix}"


class MediaAsset(models.Model):
    TYPE_IMAGE = "image"
    TYPE_DOCUMENT = "document"
    TYPE_CHOICES = [(TYPE_IMAGE, "Image"), (TYPE_DOCUMENT, "Document")]

    file = models.FileField(upload_to=media_upload_to)
    title = models.CharField(max_length=160, blank=True)
    alt_text = models.CharField(max_length=240, blank=True)
    caption = models.CharField(max_length=240, blank=True)
    file_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_IMAGE)
    file_size = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_media",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "media file"
        verbose_name_plural = "media library"

    def __str__(self):
        return self.title or Path(self.file.name).name

    @property
    def filename(self):
        return Path(self.file.name).name

    @property
    def extension(self):
        return Path(self.file.name).suffix.lower().lstrip(".")

    @property
    def is_image(self):
        return self.file_type == self.TYPE_IMAGE

    @property
    def usage(self):
        """Return a list of human-readable references to this asset."""
        references = []
        try:
            from products.models import Product, ProductImage

            for product in Product.objects.filter(image_asset=self):
                references.append(f"Product: {product.name}")
            for image in ProductImage.objects.filter(asset=self).select_related("product"):
                references.append(f"Product gallery: {image.product.name}")
        except Exception:
            pass
        try:
            for page in Page.objects.filter(image_asset=self):
                references.append(f"Page: {page.title}")
            for section in PageSection.objects.filter(image_asset=self):
                references.append(f"Page section: {section.page.title}")
            for post in BlogPost.objects.filter(featured_asset=self):
                references.append(f"Blog post: {post.title}")
            for banner in Banner.objects.filter(
                models.Q(desktop_asset=self) | models.Q(mobile_asset=self)
            ):
                references.append(f"Banner: {banner.title}")
            for testimonial in Testimonial.objects.filter(photo_asset=self):
                references.append(f"Testimonial: {testimonial.customer_name}")
        except Exception:
            pass
        return references

    @property
    def is_in_use(self):
        return bool(self.usage)


class Page(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_PUBLISHED, "Published")]

    slug = models.SlugField(max_length=120, unique=True, help_text="Fixed key such as home, about, quality or contact.")
    title = models.CharField(max_length=160)
    hero_eyebrow = models.CharField(max_length=120, blank=True)
    hero_heading = models.CharField(max_length=180, blank=True)
    hero_description = models.TextField(blank=True)
    body = models.TextField(blank=True, help_text="Safe rich text. Scripts and event handlers are removed.")
    image = models.ImageField(upload_to=image_upload_to, blank=True)
    image_asset = models.ForeignKey(
        MediaAsset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pages", help_text="Select an image from the media library, or upload one above.",
    )
    image_alt = models.CharField(max_length=240, blank=True)
    cta_label = models.CharField(max_length=80, blank=True)
    cta_url = models.CharField(
        max_length=255, blank=True,
        help_text="Relative path (/contact/) or a full https:// URL.",
    )
    seo_title = models.CharField(max_length=160, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    canonical_url = models.URLField(blank=True)
    og_image = models.ImageField(upload_to="cms/seo/", blank=True)
    noindex = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PUBLISHED)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="updated_pages",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:120]
        self.body = sanitize_html(self.body)
        super().save(*args, **kwargs)

    @property
    def body_html(self):
        return sanitize_html(self.body)

    @property
    def display_image_url(self):
        if self.image_asset and self.image_asset.file:
            return self.image_asset.file.url
        if self.image:
            return self.image.url
        return ""

    @property
    def display_alt(self):
        return self.image_alt or (self.image_asset.alt_text if self.image_asset else "") or self.title

    def get_absolute_url(self):
        mapping = {
            "home": reverse("core:home"),
            "about": reverse("core:about"),
            "quality": reverse("core:quality"),
            "contact": reverse("core:contact"),
            "privacy": reverse("core:privacy"),
            "terms": reverse("core:terms"),
        }
        return mapping.get(
            self.slug, reverse("page", kwargs={"slug": self.slug})
        )


class PageSection(models.Model):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="sections")
    heading = models.CharField(max_length=180)
    body = models.TextField(blank=True)
    image = models.ImageField(upload_to=image_upload_to, blank=True)
    image_asset = models.ForeignKey(
        MediaAsset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="page_sections",
    )
    image_alt = models.CharField(max_length=240, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return f"{self.page.title} — {self.heading}"

    def save(self, *args, **kwargs):
        self.body = sanitize_html(self.body)
        super().save(*args, **kwargs)

    @property
    def body_html(self):
        return sanitize_html(self.body)

    @property
    def display_image_url(self):
        if self.image_asset and self.image_asset.file:
            return self.image_asset.file.url
        if self.image:
            return self.image.url
        return ""

    @property
    def display_alt(self):
        return self.image_alt or (self.image_asset.alt_text if self.image_asset else "") or self.heading


class BlogCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "blog categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:110] or "category"
            slug, counter = base, 2
            while BlogCategory.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class BlogPost(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_PUBLISHED, "Published")]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    excerpt = models.TextField(max_length=500, blank=True)
    content = models.TextField(help_text="Safe rich text article content.")
    featured_image = models.ImageField(upload_to="blog/", blank=True)
    featured_asset = models.ForeignKey(
        MediaAsset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blog_posts",
    )
    featured_image_alt = models.CharField(max_length=240, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blog_posts",
    )
    category = models.ForeignKey(
        BlogCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="posts",
    )
    tags = models.CharField(max_length=240, blank=True, help_text="Comma-separated tags.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    seo_title = models.CharField(max_length=160, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    canonical_url = models.URLField(blank=True)
    og_image = models.ImageField(upload_to="blog/seo/", blank=True)
    noindex = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [models.Index(fields=["status", "-published_at"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200] or "post"
            slug, counter = base, 2
            while BlogPost.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        self.content = sanitize_html(self.content)
        super().save(*args, **kwargs)

    @property
    def content_html(self):
        return sanitize_html(self.content)

    @property
    def is_public(self):
        return (
            self.status == self.STATUS_PUBLISHED
            and self.published_at is not None
            and self.published_at <= timezone.now()
        )

    @property
    def display_image_url(self):
        if self.featured_asset and self.featured_asset.file:
            return self.featured_asset.file.url
        if self.featured_image:
            return self.featured_image.url
        return ""

    @property
    def display_alt(self):
        return (
            self.featured_image_alt
            or (self.featured_asset.alt_text if self.featured_asset else "")
            or self.title
        )

    @property
    def reading_minutes(self):
        words = len((self.content or "").split())
        return max(1, round(words / 220))

    @property
    def tag_list(self):
        return [tag.strip() for tag in (self.tags or "").split(",") if tag.strip()]

    def get_absolute_url(self):
        return reverse("blog:detail", kwargs={"slug": self.slug})

    def related_posts(self, limit=3):
        queryset = BlogPost.objects.filter(
            status=self.STATUS_PUBLISHED, published_at__lte=timezone.now()
        ).exclude(pk=self.pk)
        if self.category_id:
            queryset = queryset.filter(category_id=self.category_id)
        return queryset.order_by("-published_at")[:limit]


class Testimonial(models.Model):
    customer_name = models.CharField(max_length=120)
    designation = models.CharField(max_length=120, blank=True)
    company = models.CharField(max_length=140, blank=True)
    quote = models.TextField()
    photo = models.ImageField(upload_to="testimonials/", blank=True)
    photo_asset = models.ForeignKey(
        MediaAsset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="testimonials",
    )
    rating = models.PositiveSmallIntegerField(null=True, blank=True, choices=[(i, str(i)) for i in range(1, 6)])
    is_approved = models.BooleanField(default=False, help_text="Only approved testimonials may be published.")
    is_published = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return f"{self.customer_name} — {self.quote[:40]}"

    @property
    def is_public(self):
        return self.is_approved and self.is_published

    @property
    def photo_url(self):
        if self.photo_asset and self.photo_asset.file:
            return self.photo_asset.file.url
        if self.photo:
            return self.photo.url
        return ""


class FAQ(models.Model):
    question = models.CharField(max_length=240)
    answer = models.TextField(help_text="Safe rich text is allowed.")
    category = models.CharField(max_length=80, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question

    def save(self, *args, **kwargs):
        self.answer = sanitize_html(self.answer)
        super().save(*args, **kwargs)

    @property
    def answer_html(self):
        return sanitize_html(self.answer)


class Banner(models.Model):
    title = models.CharField(max_length=160)
    heading = models.CharField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    desktop_image = models.ImageField(upload_to="banners/", blank=True)
    mobile_image = models.ImageField(upload_to="banners/", blank=True)
    desktop_asset = models.ForeignKey(
        MediaAsset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="banner_desktop",
    )
    mobile_asset = models.ForeignKey(
        MediaAsset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="banner_mobile",
    )
    cta_text = models.CharField(max_length=80, blank=True)
    cta_url = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.title

    @property
    def desktop_url(self):
        if self.desktop_asset and self.desktop_asset.file:
            return self.desktop_asset.file.url
        return self.desktop_image.url if self.desktop_image else ""

    @property
    def mobile_url(self):
        if self.mobile_asset and self.mobile_asset.file:
            return self.mobile_asset.file.url
        return self.mobile_image.url if self.mobile_image else ""


ALLOWED_MENU_ROUTES = [
    ("core:home", "Home"),
    ("core:about", "About Us"),
    ("products:list", "Products"),
    ("core:quality", "Quality & Applications"),
    ("core:contact", "Contact Us"),
    ("blog:list", "Blog"),
    ("core:privacy", "Privacy"),
    ("core:terms", "Terms"),
]


class MenuItem(models.Model):
    LOCATION_HEADER = "header"
    LOCATION_FOOTER = "footer"
    LOCATION_CHOICES = [(LOCATION_HEADER, "Primary navigation"), (LOCATION_FOOTER, "Footer quick links")]

    label = models.CharField(max_length=80)
    url_name = models.CharField(
        max_length=80, blank=True, choices=ALLOWED_MENU_ROUTES,
        help_text="Choose a managed page, or leave blank and enter a custom URL.",
    )
    url = models.CharField(
        max_length=255, blank=True,
        help_text="Only relative paths (/about/) or https:// URLs are allowed.",
    )
    location = models.CharField(max_length=20, choices=LOCATION_CHOICES, default=LOCATION_HEADER)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    open_in_new_tab = models.BooleanField(default=False)

    class Meta:
        ordering = ["location", "order", "pk"]

    def __str__(self):
        return f"{self.label} ({self.get_location_display()})"

    @property
    def resolved_url(self):
        if self.url_name:
            try:
                return reverse(self.url_name)
            except NoReverseMatch:
                return "#"
        return self.url or "#"

    def is_current(self, request):
        path = self.resolved_url
        if path in ("", "#"):
            return False
        return request.path == path or (path != "/" and request.path.startswith(path))


class RedirectRule(models.Model):
    STATUS_CHOICES = [(301, "301 — Permanent"), (302, "302 — Temporary")]

    old_path = models.CharField(max_length=255, unique=True, help_text="Example: /old-page/")
    new_path = models.CharField(max_length=255, help_text="Relative path or full https:// URL.")
    status_code = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, default=301)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["old_path"]

    def __str__(self):
        return f"{self.old_path} → {self.new_path}"

    def clean(self):
        from django.core.exceptions import ValidationError

        for value, label in ((self.old_path, "Old path"), (self.new_path, "New path")):
            if value and not value.startswith(("/", "http://", "https://")):
                raise ValidationError({("old_path" if label == "Old path" else "new_path"): "Enter a path beginning with / or a full URL."})
        if self.old_path.startswith(("/admin-panel", "/django-admin")):
            raise ValidationError({"old_path": "Administration paths cannot be redirected."})
