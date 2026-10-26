from __future__ import annotations

from functools import wraps

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q

from .models import SiteSettings
from .uploads import validate_image_upload
from .utils import login_clear_failures, login_is_locked, login_record_failure

User = get_user_model()


class SectionedFormMixin:
    """Allow dashboard templates to render fields in logical groups."""

    sections: list[tuple] = []

    def section_fields(self):
        result = []
        for title, description, names in self.sections:
            result.append(
                {
                    "title": title,
                    "description": description,
                    "fields": [self[name] for name in names if name in self.fields],
                }
            )
        return result


class SiteSettingsForm(forms.ModelForm):
    """Only the fields actually rendered by ``dashboard/settings.html``.

    Limiting the form prevents unrendered values (logo, SEO defaults,
    maintenance controls) from being wiped when a staff member saves.
    """

    class Meta:
        model = SiteSettings
        fields = [
            "company_name", "tagline", "hero_heading", "hero_description",
            "contact_phone", "contact_email", "whatsapp_number", "hours",
            "business_address", "map_embed_url", "footer_description",
            "facebook_url", "instagram_url", "linkedin_url", "youtube_url",
        ]
        widgets = {
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "tagline": forms.TextInput(attrs={"class": "form-control"}),
            "hero_heading": forms.TextInput(attrs={"class": "form-control"}),
            "hero_description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control"}),
            "whatsapp_number": forms.TextInput(attrs={"class": "form-control"}),
            "hours": forms.TextInput(attrs={"class": "form-control"}),
            "business_address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "map_embed_url": forms.URLInput(attrs={"class": "form-control"}),
            "footer_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "facebook_url": forms.URLInput(attrs={"class": "form-control"}),
            "instagram_url": forms.URLInput(attrs={"class": "form-control"}),
            "linkedin_url": forms.URLInput(attrs={"class": "form-control"}),
            "youtube_url": forms.URLInput(attrs={"class": "form-control"}),
        }

    def clean_whatsapp_number(self):
        value = (self.cleaned_data.get("whatsapp_number") or "").strip()
        if not value:
            return ""
        digits = "".join(char for char in value if char.isdigit())
        if len(digits) < 8 or len(digits) > 15:
            raise ValidationError(
                "Enter the WhatsApp number in international format, including "
                "the country code (8–15 digits)."
            )
        return value

    def clean_business_address(self):
        return (self.cleaned_data.get("business_address") or "").strip()


class _SettingsSubForm(SectionedFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs.setdefault("class", "form-select")
            elif isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs.setdefault("class", "form-control")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean_image(self):
        return validate_image_upload(self.cleaned_data.get("image"))


class CompanyInfoForm(_SettingsSubForm):
    class Meta:
        model = SiteSettings
        fields = [
            "company_name", "tagline", "company_description", "logo", "favicon",
            "footer_description", "copyright_text",
        ]
        widgets = {
            "company_description": forms.Textarea(attrs={"rows": 4}),
            "footer_description": forms.Textarea(attrs={"rows": 3}),
        }
    sections = [
        ("Brand identity", "Shown in the site header, footer and structured data.", ["company_name", "tagline", "company_description"]),
        ("Logo & favicon", "Leave blank to use the built-in brand assets.", ["logo", "favicon"]),
        ("Footer and copyright", "", ["footer_description", "copyright_text"]),
    ]

    def clean_logo(self):
        return validate_image_upload(self.cleaned_data.get("logo"))

    def clean_favicon(self):
        return validate_image_upload(self.cleaned_data.get("favicon"))


class ContactInfoForm(_SettingsSubForm):
    class Meta:
        model = SiteSettings
        fields = [
            "contact_email", "contact_phone", "whatsapp_number", "business_address",
            "hours", "map_embed_url",
        ]
        widgets = {
            "business_address": forms.Textarea(attrs={"rows": 4}),
        }
    sections = [
        ("Contact channels", "Only configured values are shown as clickable links on the public site.", ["contact_email", "contact_phone", "whatsapp_number"]),
        ("Location & hours", "", ["business_address", "hours", "map_embed_url"]),
    ]

    def clean_whatsapp_number(self):
        return SiteSettingsForm.clean_whatsapp_number(self)


class SocialMediaForm(_SettingsSubForm):
    class Meta:
        model = SiteSettings
        fields = ["facebook_url", "instagram_url", "linkedin_url", "youtube_url"]
    sections = [
        ("Social profiles", "Full https:// profile URLs. Blank profiles are hidden automatically.", ["facebook_url", "instagram_url", "linkedin_url", "youtube_url"]),
    ]


class SeoSettingsForm(_SettingsSubForm):
    class Meta:
        model = SiteSettings
        fields = [
            "default_seo_title", "default_seo_description", "default_og_image",
            "allow_search_indexing", "robots_extra",
        ]
        widgets = {
            "default_seo_description": forms.Textarea(attrs={"rows": 3, "data-count": "160"}),
            "robots_extra": forms.Textarea(attrs={"rows": 4}),
        }
    sections = [
        ("Default metadata", "Used when a page or product does not provide its own metadata.", ["default_seo_title", "default_seo_description", "default_og_image"]),
        ("Indexing & robots.txt", "The sitemap location and administration disallow rules are added automatically.", ["allow_search_indexing", "robots_extra"]),
    ]

    def clean_default_og_image(self):
        return validate_image_upload(self.cleaned_data.get("default_og_image"))


class GeneralSettingsForm(_SettingsSubForm):
    class Meta:
        model = SiteSettings
        fields = ["google_analytics_id", "maintenance_mode", "maintenance_message"]
        widgets = {
            "maintenance_message": forms.Textarea(attrs={"rows": 3}),
        }
    sections = [
        ("Analytics", "Analytics is loaded only when a GA4 measurement ID is configured.", ["google_analytics_id"]),
        ("Maintenance mode", "Public visitors see a maintenance page; signed-in staff can continue working.", ["maintenance_mode", "maintenance_message"]),
    ]


class StaffCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"})
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}),
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "groups", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "groups": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["groups"].help_text = (
            "Groups control which dashboard sections this staff member can use. "
            "Superuser status is not granted here."
        )
        self.fields["groups"].queryset = Group.objects.order_by("name")

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("The two password fields did not match.")
        if password2:
            from django.contrib.auth.password_validation import validate_password

            validate_password(password2)
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class StaffUpdateForm(forms.ModelForm):
    new_password1 = forms.CharField(
        label="New password",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}),
        help_text="Leave blank to keep the current password.",
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}),
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "groups", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "groups": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["groups"].queryset = Group.objects.order_by("name")

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("new_password1")
        password2 = cleaned.get("new_password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("new_password2", "The two password fields did not match.")
            elif password1:
                from django.contrib.auth.password_validation import validate_password

                try:
                    validate_password(password1, self.instance)
                except ValidationError as exc:
                    self.add_error("new_password1", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        password = self.cleaned_data.get("new_password1")
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_m2m()
        return user


class RoleForm(SectionedFormMixin, forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name", "permissions"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "permissions": forms.CheckboxSelectMultiple(attrs={"class": "role-permissions"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = Permission.objects.select_related(
            "content_type"
        ).exclude(content_type__app_label__in=["sessions", "admin", "contenttypes"]).order_by(
            "content_type__app_label", "codename"
        )
        self.fields["permissions"].help_text = "Permissions are enforced on the server, not just hidden in the interface."

    def grouped_permissions(self):
        field = self["permissions"]
        widgets = list(field)
        queryset = {str(p.pk): p for p in self.fields["permissions"].queryset}
        groups = {}
        for widget in widgets:
            pk = str(widget.data.get("value", ""))
            permission = queryset.get(pk)
            if not permission:
                continue
            label = permission.content_type.app_label.replace("_", " ").title()
            if permission.content_type.app_label == "cms":
                label = "Website content"
            elif permission.content_type.app_label == "core":
                label = "Settings & administration"
            elif permission.content_type.app_label == "enquiries":
                label = "Enquiries & customers"
            elif permission.content_type.app_label == "products":
                label = "Products & categories"
            elif permission.content_type.app_label == "auth":
                label = "Users & groups"
            groups.setdefault(label, []).append(widget)
        return [{"label": label, "widgets": items} for label, items in groups.items()]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


class DashboardPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
            field.widget.attrs["autocomplete"] = "new-password"


class StaffPasswordResetForm(PasswordResetForm):
    """Only staff accounts can use the dashboard password reset flow."""

    def get_users(self, email):
        # ``PasswordResetForm.get_users`` returns a generator, so filter while
        # iterating rather than chaining a queryset method.
        for user in super().get_users(email):
            if user.is_staff:
                yield user


class NotificationCreateForm(forms.Form):
    title = forms.CharField(
        max_length=160,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    url = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "/admin-panel/enquiries/"}),
    )
    level = forms.ChoiceField(
        choices=[("info", "Information"), ("success", "Success"), ("warning", "Warning"), ("danger", "Urgent")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean_url(self):
        value = (self.cleaned_data.get("url") or "").strip()
        if value and not value.startswith("/"):
            raise ValidationError("Enter a relative dashboard path beginning with /.")
        return value


class StaffLoginForm(AuthenticationForm):
    """Authentication form with a cache-backed lockout after repeated failures."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "locked": "Too many failed sign-in attempts. Please wait before trying again.",
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": "form-control", "autocomplete": "username"})
        self.fields["password"].widget.attrs.update({"class": "form-control", "autocomplete": "current-password"})

    def clean(self):
        username = (self.cleaned_data.get("username") or "").strip()
        from .utils import client_ip

        ip = client_ip(self.request) if self.request else ""
        if login_is_locked(username, ip):
            raise ValidationError(self.error_messages["locked"], code="locked")
        try:
            cleaned = super().clean()
        except ValidationError:
            login_record_failure(username, ip)
            raise
        login_clear_failures(username, ip)
        return cleaned


def staff_required(view):
    return user_passes_test(
        lambda user: user.is_active and user.is_staff,
        login_url=settings.LOGIN_URL,
    )(view)


def superuser_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        if not (user.is_active and user.is_superuser):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def search_users(query):
    users = User.objects.filter(is_staff=True)
    if not query:
        return users
    return users.filter(
        Q(username__icontains=query)
        | Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(email__icontains=query)
    )


def flash_saved(request, label):
    from django.contrib import messages

    messages.success(request, f"{label} saved.")


SiteSettings = SiteSettings  # re-exported for convenient imports
