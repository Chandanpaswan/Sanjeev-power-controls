from __future__ import annotations

from django import forms
from django.utils.text import slugify

from core.forms import SectionedFormMixin
from core.uploads import image_asset_queryset, validate_image_upload

from .models import Category, Product, ProductImage

IMAGE_MAX_BYTES = 3 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class ProductForm(SectionedFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "slug", "sku", "category", "short_description", "description",
            "features", "specifications", "image", "image_asset", "image_alt",
            "featured", "active", "seo_title", "seo_description", "seo_keywords",
            "canonical_url", "og_image",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "sku": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "short_description": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "features": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "One feature per line"}),
            "specifications": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 7,
                    "placeholder": "Element type: Pleated cylindrical (demo)\nDimensions: To be confirmed",
                }
            ),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
            "image_asset": forms.Select(attrs={"class": "form-select"}),
            "image_alt": forms.TextInput(attrs={"class": "form-control"}),
            "featured": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "seo_title": forms.TextInput(attrs={"class": "form-control", "data-count": "60"}),
            "seo_description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "data-count": "160"}),
            "seo_keywords": forms.TextInput(attrs={"class": "form-control"}),
            "canonical_url": forms.URLInput(attrs={"class": "form-control"}),
            "og_image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
        }

    sections = [
        ("Product identity", "The SKU must be unique. Published products appear immediately on the public catalogue.", ["name", "slug", "sku", "category"]),
        ("Public content", "", ["short_description", "description", "features", "specifications"]),
        ("Images", "Upload a new image or select one from the media library. The library selection takes priority.", ["image", "image_asset", "image_alt"]),
        ("Visibility", "", ["featured", "active"]),
        ("Search engine metadata", "Optional. Defaults from the website settings are used when these are blank.", ["seo_title", "seo_description", "seo_keywords", "canonical_url", "og_image"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].help_text = "JPG, PNG, WebP or GIF, up to 3 MB. Recommended size 1000 × 750 px."
        self.fields["slug"].help_text = "Leave blank to generate from the product name."
        self.fields["slug"].required = False
        self.fields["image_asset"].queryset = image_asset_queryset()
        self.fields["image_asset"].empty_label = "Use the uploaded image"
        self.fields["image_asset"].help_text = (
            "Select a cleared image from the media library, or upload a new file above."
        )
        self.fields["og_image"].help_text = "Optional social sharing image. JPG, PNG, WebP or GIF up to 3 MB."

    def clean_image(self):
        return validate_image_upload(self.cleaned_data.get("image"))

    def clean_og_image(self):
        return validate_image_upload(self.cleaned_data.get("og_image"))

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip()
        if not slug:
            return ""
        slug = slugify(slug)
        if not slug:
            raise forms.ValidationError("Enter a valid URL slug.")
        if Product.objects.exclude(pk=self.instance.pk).filter(slug=slug).exists():
            raise forms.ValidationError("That slug is already used by another product.")
        return slug

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip()
        if not sku:
            raise forms.ValidationError("A SKU is required.")
        sku = sku.upper()
        if Product.objects.exclude(pk=self.instance.pk).filter(sku__iexact=sku).exists():
            raise forms.ValidationError("That SKU is already used by another product.")
        return sku

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("slug") and cleaned.get("name"):
            cleaned["slug"] = slugify(cleaned["name"])[:140]
        return cleaned


class CategoryForm(SectionedFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = [
            "name", "slug", "description", "image", "image_asset", "is_active",
            "seo_title", "seo_description",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
            "image_asset": forms.Select(attrs={"class": "form-select"}),
            "seo_title": forms.TextInput(attrs={"class": "form-control", "data-count": "60"}),
            "seo_description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "data-count": "160"}),
        }
    sections = [
        ("Category", "", ["name", "slug", "description"]),
        ("Image", "", ["image", "image_asset"]),
        ("Visibility & SEO", "", ["is_active", "seo_title", "seo_description"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Leave blank to generate from the name."
        self.fields["image_asset"].queryset = image_asset_queryset()
        self.fields["image_asset"].empty_label = "Use the uploaded image"
        self.fields["image_asset"].help_text = (
            "Select a cleared image from the media library, or upload a new file above."
        )
        self.fields["is_active"].help_text = (
            "Inactive categories and their products are hidden from the public catalogue."
        )

    def clean_image(self):
        return validate_image_upload(self.cleaned_data.get("image"))

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip()
        if not slug:
            return ""
        slug = slugify(slug)
        if Category.objects.exclude(pk=self.instance.pk).filter(slug=slug).exists():
            raise forms.ValidationError("That slug is already used by another category.")
        return slug

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if Category.objects.exclude(pk=self.instance.pk).filter(name__iexact=name).exists():
            raise forms.ValidationError("A category with this name already exists.")
        return name


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "asset", "alt_text", "order"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}),
            "asset": forms.Select(attrs={"class": "form-select"}),
            "alt_text": forms.TextInput(attrs={"class": "form-control"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["asset"].queryset = image_asset_queryset()
        self.fields["asset"].empty_label = "No library image"
        self.fields["image"].required = False
        self.fields["asset"].required = False

    def clean_image(self):
        return validate_image_upload(self.cleaned_data.get("image"))

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("image") and not cleaned.get("asset") and not self.instance.pk:
            raise forms.ValidationError("Upload an image or select one from the media library.")
        return cleaned
