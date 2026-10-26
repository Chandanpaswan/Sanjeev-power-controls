from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator

from core.forms import SectionedFormMixin
from products.models import Product

from .models import Customer, Enquiry, EnquiryNote

User = get_user_model()

phone_validator = RegexValidator(
    regex=r"^[0-9+\-()\s]{7,30}$",
    message="Enter a valid phone number using digits, spaces, +, - or brackets.",
)


class EnquiryForm(forms.ModelForm):
    consent = forms.BooleanField(
        required=True,
        label="I agree to be contacted about this enquiry.",
        error_messages={
            "required": "Please confirm that you agree to be contacted about this enquiry."
        },
    )
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Enquiry
        fields = ["name", "company", "email", "phone", "product", "message"]
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Your full name", "autocomplete": "name"}
            ),
            "company": forms.TextInput(
                attrs={"placeholder": "Company (optional)", "autocomplete": "organization"}
            ),
            "email": forms.EmailInput(
                attrs={"placeholder": "you@company.com", "autocomplete": "email"}
            ),
            "phone": forms.TextInput(
                attrs={"placeholder": "+91 98765 43210", "autocomplete": "tel"}
            ),
            "message": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Part number, engine model, quantity and any other details…",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(
            active=True, category__is_active=True
        ).order_by("name")
        self.fields["product"].required = False
        self.fields["product"].empty_label = "General enquiry / not sure"
        self.fields["product"].label = "Product interest"
        self.fields["company"].required = False
        self.fields["phone"].validators = [phone_validator]
        self.fields["name"].min_length = 2
        self.fields["message"].min_length = 10

    def clean_website(self):
        value = self.cleaned_data.get("website")
        if value:
            raise forms.ValidationError("Spam protection triggered.")
        return value

    def clean_name(self):
        return (self.cleaned_data.get("name") or "").strip()

    def clean_company(self):
        return (self.cleaned_data.get("company") or "").strip()

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean_phone(self):
        return (self.cleaned_data.get("phone") or "").strip()

    def clean_message(self):
        message = (self.cleaned_data.get("message") or "").strip()
        if len(message) < 10:
            raise forms.ValidationError("Please add a little more detail (at least 10 characters).")
        return message


class EnquiryUpdateForm(SectionedFormMixin, forms.ModelForm):
    class Meta:
        model = Enquiry
        fields = ["status", "internal_notes"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "internal_notes": forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Private notes visible only to staff…"}),
        }
    sections = [
        ("Follow-up", "Status changes are recorded in the audit log.", ["status"]),
        ("Private notes", "Never shown on the public website.", ["internal_notes"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["internal_notes"].help_text = ""


class EnquiryNoteForm(forms.ModelForm):
    class Meta:
        model = EnquiryNote
        fields = ["note"]
        widgets = {
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Add a private follow-up note…"}),
        }

    def clean_note(self):
        note = (self.cleaned_data.get("note") or "").strip()
        if len(note) < 2:
            raise forms.ValidationError("Enter a note.")
        return note


class CustomerForm(SectionedFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "contact_person", "email", "phone", "company_address", "status", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "company_address": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }
    sections = [
        ("Customer details", "", ["name", "contact_person", "email", "phone", "company_address"]),
        ("Status & notes", "Internal only. Customers are created manually from qualified enquiries.", ["status", "notes"]),
    ]

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean_phone(self):
        value = (self.cleaned_data.get("phone") or "").strip()
        if value:
            phone_validator(value)
        return value

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        duplicate = Customer.objects.exclude(pk=self.instance.pk).filter(name__iexact=name)
        if duplicate.exists():
            raise forms.ValidationError("A customer with this name already exists. Open the existing record instead.")
        return name
