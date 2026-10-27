from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError

from .models import CustomerProfile, SellerProfile

User = get_user_model()


class CustomerRegistrationForm(UserCreationForm):
    full_name = forms.CharField(max_length=160, required=True, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Full name"}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email address"}))
    phone = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Mobile number"}))
    company_name = forms.CharField(max_length=160, required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Company name (optional)"}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))
    accept_terms = forms.BooleanField(required=True, label="Accept Terms and Privacy Policy")

    class Meta:
        model = User
        fields = ("full_name", "email", "phone", "company_name", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data.get("email").lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].lower().strip()
        user.username = user.email
        user.full_name = self.cleaned_data["full_name"]
        user.phone = self.cleaned_data["phone"]
        user.company_name = self.cleaned_data.get("company_name", "")
        if commit:
            user.save()
            CustomerProfile.objects.create(user=user)
        return user


class CustomerLoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "current-password"}))
    remember_me = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"


class SellerRegistrationForm(forms.ModelForm):
    full_name = forms.CharField(max_length=160, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=30, required=True)
    password1 = forms.CharField(widget=forms.PasswordInput())
    password2 = forms.CharField(widget=forms.PasswordInput())

    class Meta:
        model = SellerProfile
        fields = ("business_name", "business_address", "business_description", "product_categories_handled", "business_documentation")

    def clean_email(self):
        email = self.cleaned_data.get("email").lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            raise ValidationError("Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = User.objects.create_user(
            username=self.cleaned_data["email"].lower().strip(),
            email=self.cleaned_data["email"].lower().strip(),
            password=self.cleaned_data["password1"],
            full_name=self.cleaned_data["full_name"],
            phone=self.cleaned_data["phone"],
        )
        user.is_staff = False
        user.save()
        profile.user = user
        profile.approval_status = SellerProfile.STATUS_PENDING
        if commit:
            profile.save()
        return profile
