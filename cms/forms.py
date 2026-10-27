from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from core.forms import SectionedFormMixin
from core.uploads import image_asset_queryset, validate_image_upload, validate_media_upload

from .models import (
    ALLOWED_MENU_ROUTES,
    Banner,
    BlogCategory,
    BlogPost,
    FAQ,
    MediaAsset,
    MenuItem,
    Page,
    PageSection,
    RedirectRule,
    Testimonial,
)


class MediaAssetForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = ["file", "title", "alt_text", "caption"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif,application/pdf"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "alt_text": forms.TextInput(attrs={"class": "form-control"}),
            "caption": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_file(self):
        upload = self.cleaned_data.get("file")
        if upload:
            validate_media_upload(upload)
        return upload

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get("file")
        if not upload and not self.instance.pk:
            self.add_error("file", "Choose a file to upload.")
        if upload and not cleaned.get("title"):
            cleaned["title"] = upload.name[:160]
        return cleaned


class MediaAssetEditForm(forms.ModelForm):
    class Meta:
        model = MediaAsset
        fields = ["title", "alt_text", "caption"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "alt_text": forms.TextInput(attrs={"class": "form-control"}),
            "caption": forms.TextInput(attrs={"class": "form-control"}),
        }


class PageForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = [
            "title", "slug", "hero_eyebrow", "hero_heading", "hero_description",
            "image", "image_asset", "image_alt", "body", "cta_label", "cta_url",
            "status", "seo_title", "seo_description", "canonical_url", "og_image", "noindex",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "hero_eyebrow": forms.TextInput(attrs={"class": "form-control"}),
            "hero_heading": forms.TextInput(attrs={"class": "form-control"}),
            "hero_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
            "image_asset": forms.Select(attrs={"class": "form-select"}),
            "image_alt": forms.TextInput(attrs={"class": "form-control"}),
            "body": forms.Textarea(attrs={"class": "form-control rich-text", "rows": 10}),
            "cta_label": forms.TextInput(attrs={"class": "form-control"}),
            "cta_url": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "seo_title": forms.TextInput(attrs={"class": "form-control", "data-count": "60"}),
            "seo_description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "data-count": "160"}),
            "canonical_url": forms.URLInput(attrs={"class": "form-control"}),
            "og_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image_asset"].queryset = image_asset_queryset()
        self.fields["image_asset"].empty_label = "No library image"
        self.fields["slug"].help_text = "Used to identify the page. Home, about, quality and contact are wired into the public site."
        self.fields["body"].help_text = "Safe rich text: headings, lists, links, emphasis and paragraphs are allowed."
        self.fields["cta_url"].help_text = "Example: /contact/ or https://example.com/page"

    def clean_image(self):
        return validate_image_upload(self.cleaned_data.get("image"))

    def clean_og_image(self):
        return validate_image_upload(self.cleaned_data.get("og_image"))

    def clean_cta_url(self):
        value = (self.cleaned_data.get("cta_url") or "").strip()
        if value and not (value.startswith("/") or value.startswith("https://") or value.startswith("http://")):
            raise forms.ValidationError("Enter a relative path or a full http(s) URL.")
        return value


PageSectionFormSet = inlineformset_factory(
    Page,
    PageSection,
    fields=["heading", "body", "image", "image_asset", "image_alt", "order", "is_active"],
    extra=1,
    can_delete=True,
    widgets={
        "heading": forms.TextInput(attrs={"class": "form-control"}),
        "body": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
        "image_asset": forms.Select(attrs={"class": "form-select"}),
        "image_alt": forms.TextInput(attrs={"class": "form-control"}),
        "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    },
)


class BlogCategoryForm(forms.ModelForm):
    class Meta:
        model = BlogCategory
        fields = ["name", "slug", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class BlogPostForm(SectionedFormMixin, forms.ModelForm):
    sections = [
        (
            "Post details",
            "Draft posts stay private until the status is Published.",
            ["title", "slug", "excerpt", "content"],
        ),
        (
            "Featured image",
            "Upload a new image or choose one from the media library.",
            ["featured_image", "featured_asset", "featured_image_alt"],
        ),
        (
            "Publishing",
            "Published posts with a future date stay hidden until that date.",
            ["author", "category", "tags", "status", "published_at"],
        ),
        (
            "Search engine listing",
            "Optional overrides for the public page metadata.",
            ["seo_title", "seo_description", "canonical_url", "og_image", "noindex"],
        ),
    ]

    class Meta:
        model = BlogPost
        fields = [
            "title", "slug", "excerpt", "content", "featured_image", "featured_asset",
            "featured_image_alt", "author", "category", "tags", "status", "published_at",
            "seo_title", "seo_description", "canonical_url", "og_image", "noindex",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "excerpt": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "content": forms.Textarea(attrs={"class": "form-control rich-text", "rows": 14}),
            "featured_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
            "featured_asset": forms.Select(attrs={"class": "form-select"}),
            "featured_image_alt": forms.TextInput(attrs={"class": "form-control"}),
            "author": forms.Select(attrs={"class": "form-select"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "tags": forms.TextInput(attrs={"class": "form-control", "placeholder": "maintenance, filters, buying guide"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "published_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "seo_title": forms.TextInput(attrs={"class": "form-control", "data-count": "60"}),
            "seo_description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "data-count": "160"}),
            "canonical_url": forms.URLInput(attrs={"class": "form-control"}),
            "og_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["featured_asset"].queryset = image_asset_queryset()
        self.fields["featured_asset"].empty_label = "No library image"
        self.fields["author"].required = False
        self.fields["published_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["slug"].help_text = "Leave blank to generate from the title."
        self.fields["published_at"].help_text = "Leave blank to publish immediately when status is Published."

    def clean_featured_image(self):
        return validate_image_upload(self.cleaned_data.get("featured_image"))

    def clean_og_image(self):
        return validate_image_upload(self.cleaned_data.get("og_image"))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == BlogPost.STATUS_PUBLISHED and not cleaned.get("published_at"):
            from django.utils import timezone

            cleaned["published_at"] = timezone.now()
        return cleaned


class TestimonialForm(SectionedFormMixin, forms.ModelForm):
    sections = [
        (
            "Testimonial",
            "Use only real feedback with permission to publish.",
            [
                "customer_name", "designation", "company", "quote", "rating", "order",
            ],
        ),
        (
            "Image & visibility",
            "Approve the testimonial before publishing it.",
            ["photo", "photo_asset", "is_approved", "is_published"],
        ),
    ]

    class Meta:
        model = Testimonial
        fields = [
            "customer_name", "designation", "company", "quote", "photo", "photo_asset",
            "rating", "order", "is_approved", "is_published",
        ]
        widgets = {
            "customer_name": forms.TextInput(attrs={"class": "form-control"}),
            "designation": forms.TextInput(attrs={"class": "form-control"}),
            "company": forms.TextInput(attrs={"class": "form-control"}),
            "quote": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
            "photo_asset": forms.Select(attrs={"class": "form-select"}),
            "rating": forms.Select(attrs={"class": "form-select"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["photo_asset"].queryset = image_asset_queryset()
        self.fields["photo_asset"].empty_label = "No library image"

    def clean_photo(self):
        return validate_image_upload(self.cleaned_data.get("photo"))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_published") and not cleaned.get("is_approved"):
            self.add_error("is_published", "Approve this testimonial before publishing it.")
        return cleaned


class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ["question", "answer", "category", "order", "is_published"]
        widgets = {
            "question": forms.TextInput(attrs={"class": "form-control"}),
            "answer": forms.Textarea(attrs={"class": "form-control rich-text", "rows": 6}),
            "category": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ordering, Products, Support…"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }


class BannerForm(forms.ModelForm):
    class Meta:
        model = Banner
        fields = [
            "title", "heading", "description", "desktop_image", "mobile_image",
            "desktop_asset", "mobile_asset", "cta_text", "cta_url", "is_active", "order",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "heading": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "desktop_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
            "mobile_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
            "desktop_asset": forms.Select(attrs={"class": "form-select"}),
            "mobile_asset": forms.Select(attrs={"class": "form-select"}),
            "cta_text": forms.TextInput(attrs={"class": "form-control"}),
            "cta_url": forms.TextInput(attrs={"class": "form-control"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assets = image_asset_queryset()
        self.fields["desktop_asset"].queryset = assets
        self.fields["mobile_asset"].queryset = assets
        self.fields["desktop_asset"].empty_label = "No library image"
        self.fields["mobile_asset"].empty_label = "No library image"

    def clean_desktop_image(self):
        return validate_image_upload(self.cleaned_data.get("desktop_image"))

    def clean_mobile_image(self):
        return validate_image_upload(self.cleaned_data.get("mobile_image"))

    def clean_cta_url(self):
        value = (self.cleaned_data.get("cta_url") or "").strip()
        if value and not (value.startswith("/") or value.startswith("https://") or value.startswith("http://")):
            raise forms.ValidationError("Enter a relative path or a full http(s) URL.")
        return value


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ["label", "url_name", "url", "location", "order", "is_active", "open_in_new_tab"]
        widgets = {
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "url_name": forms.Select(attrs={"class": "form-select"}),
            "url": forms.TextInput(attrs={"class": "form-control", "placeholder": "/about/ or https://example.com"}),
            "location": forms.Select(attrs={"class": "form-select"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("url_name") and not cleaned.get("url"):
            self.add_error("url", "Choose a managed page or enter a custom destination.")
        if cleaned.get("url") and cleaned.get("url_name"):
            self.add_error("url", "Use either a managed page or a custom URL, not both.")
        value = (cleaned.get("url") or "").strip()
        if value and not (value.startswith("/") or value.startswith("https://") or value.startswith("http://")):
            self.add_error("url", "Enter a relative path or a full http(s) URL.")
        if value.startswith(("/admin/", "/django-admin")):
            self.add_error("url", "Administration pages cannot be added to the public menu.")
        return cleaned


class RedirectRuleForm(forms.ModelForm):
    class Meta:
        model = RedirectRule
        fields = ["old_path", "new_path", "status_code", "is_active"]
        widgets = {
            "old_path": forms.TextInput(attrs={"class": "form-control", "placeholder": "/old-page/"}),
            "new_path": forms.TextInput(attrs={"class": "form-control", "placeholder": "/new-page/"}),
            "status_code": forms.Select(attrs={"class": "form-select"}),
        }
