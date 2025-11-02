# apps/tenants/forms.py
from django import forms
from .models import PLAN_CHOICES
from django import forms
from django.core.exceptions import ValidationError
from .models import Vendor 
from apps.accounts.models import User
from phonenumber_field.formfields import PhoneNumberField
# from phonenumber_field.widgets import PhoneNumberPrefixWidget


class VendorOnboardingForm(forms.Form):
    # Business Information
    name = forms.CharField(
        max_length=255,
        label="Business / Lab Name",
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your lab name",
            "class": "form-control"
        })
    )
    
    # Admin User Information
    admin_email = forms.EmailField(
        label="Admin Email",
        widget=forms.EmailInput(attrs={
            "placeholder": "yourmail@example.com",
            "class": "form-control"
        })
    )
    admin_first_name = forms.CharField(
        label="First Name", 
        widget=forms.TextInput(attrs={
            "placeholder": "First Name",
            "class": "form-control"
        })
    )
    admin_last_name = forms.CharField(
        label="Last Name",
        widget=forms.TextInput(attrs={
            "placeholder": "Last Name", 
            "class": "form-control"
        })
    )
    # Contact Information
    contact_number = PhoneNumberField(required=False)
    
    admin_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="Password"
    )
    admin_password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="Confirm Password"
    )
    
    # Plan Selection
    plan_type = forms.ChoiceField(
        choices=PLAN_CHOICES, 
        label="Subscription Plan",
        initial="1",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    
    # Address Information
    office_street_address = forms.CharField(
        label="Street Address",
        widget=forms.TextInput(attrs={
            'placeholder': 'Street or Road Address',
            'class': 'form-control'
        })
    )
    office_city_state = forms.CharField(
        label="City & State",
        widget=forms.TextInput(attrs={
            'placeholder': 'City and State',
            'class': 'form-control'
        })
    )
    office_country = forms.CharField(  # Fixed field name from office_county
        label="Country",
        widget=forms.TextInput(attrs={
            'placeholder': 'Country',
            'class': 'form-control'
        })
    )
    office_zipcode = forms.CharField(
        label="Zipcode",
        widget=forms.TextInput(attrs={
            'placeholder': 'Zipcode',
            'class': 'form-control'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contact_number'].widget.attrs.update({'class': 'form-control'})


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
    

    # domain_name = forms.CharField(
    #     max_length=255,
    #     label="Preferred Domain (optional)",
    #     required=False,
    #     widget=forms.TextInput(attrs={"placeholder": "example.lis.com"})
    # )

