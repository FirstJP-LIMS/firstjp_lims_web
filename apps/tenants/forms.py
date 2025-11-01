# apps/tenants/forms.py
from django import forms
from .models import PLAN_CHOICES
from django import forms
from django.core.exceptions import ValidationError
# from django.db import transaction
from .models import Vendor 
# from .models import PLAN_CHOICES, Vendor, VendorDomain
from apps.accounts.models import User # Import your Custom User Model


class VendorOnboardingForm(forms.Form):
    name = forms.CharField(
        max_length=255,
        label="Business / Lab Name",
        widget=forms.TextInput(attrs={"placeholder": "Enter your lab name"})
    )
    
    # tenant_id = forms.CharField(
    #     max_length=64,
    #     label="Tenant ID",
    #     help_text="A short, unique code (e.g., LAB001)",
    #     widget=forms.TextInput(attrs={"placeholder": "e.g., LAB001"})
    # )

    admin_email = forms.EmailField(
        label="Vendor Admin Email",
        help_text="Email for the vendor admin account",
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com"}))
    admin_first_name = forms.CharField(label="Admin First Name", widget=forms.TextInput(attrs={"placeholder": "First Name"}))
    admin_last_name = forms.CharField(label="Admin Last Name", widget=forms.TextInput(attrs={"placeholder": "Last Name"}))

    admin_password = forms.CharField(widget=forms.PasswordInput, label="Admin Password")
    admin_password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm Password") # Added for security
    plan_type = forms.ChoiceField(choices=PLAN_CHOICES, label="Subscription Plan", initial="1")

    domain_name = forms.CharField(
        max_length=255,
        label="Preferred Domain (optional)",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "example.lis.com"})
    )

    def clean_tenant_id(self):
        # Validate that the requested tenant_id slug is unique
        tenant_id = self.cleaned_data["tenant_id"].upper()
        if Vendor.objects.filter(tenant_id=tenant_id).exists():
            raise ValidationError("This Tenant ID is already taken.")
        return tenant_id

    def clean_admin_email(self):
        # Validate that the admin's email is unique across the *entire* platform
        email = self.cleaned_data["admin_email"]
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("admin_password")
        password_confirm = cleaned_data.get("admin_password_confirm")

        if password and password != password_confirm:
            self.add_error('admin_password_confirm', "Passwords do not match.")

        # Optional: Validate domain name format if required
        return cleaned_data