
# apps/tenants/forms.py
from django import forms
from .models import PLAN_CHOICES
from django import forms
from django.core.exceptions import ValidationError
from .models import Vendor 
from apps.accounts.models import User
from phonenumber_field.formfields import PhoneNumberField
# from phonenumber_field.widgets import PhoneNumberPrefixWidget

BASE_INPUT = "w-full px-4 py-2 rounded-md border border-gray-300 focus:outline-none focus:ring-2 focus:ring-nav-blue"
BASE_SELECT = "w-full px-4 py-2 rounded-md border border-gray-300 bg-white focus:outline-none focus:ring-2 focus:ring-nav-blue"


class VendorOnboardingForm(forms.Form):
    # Business Information
    name = forms.CharField(
        max_length=255,
        label="Business / Lab Name",
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your lab name",
            "class": BASE_INPUT
        })
    )
    
    # Admin User Information
    admin_email = forms.EmailField(
        label="Admin Email",
        widget=forms.EmailInput(attrs={
            "placeholder": "yourmail@example.com",
            "class": BASE_INPUT
        })
    )
    admin_first_name = forms.CharField(
        label="First Name", 
        widget=forms.TextInput(attrs={
            "placeholder": "First Name",
            "class": BASE_INPUT
        })
    )
    admin_last_name = forms.CharField(
        label="Last Name",
        widget=forms.TextInput(attrs={
            "placeholder": "Last Name", 
            "class": BASE_INPUT
        })
    )
    # Contact Information
    contact_number = PhoneNumberField(required=False)
    
    admin_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": BASE_INPUT}),
        label="Password"
    )
    admin_password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": BASE_INPUT}),
        label="Confirm Password"
    )
    
    # Address Information
    office_street_address = forms.CharField(
        label="Street Address",
        widget=forms.TextInput(attrs={
            'placeholder': 'Street or Road Address',
            'class': BASE_INPUT
        })
    )
    office_city_state = forms.CharField(
        label="City & State",
        widget=forms.TextInput(attrs={
            'placeholder': 'City and State',
            'class': BASE_INPUT
        })
    )
    office_country = forms.CharField(  # Fixed field name from office_county
        label="Country",
        widget=forms.TextInput(attrs={
            'placeholder': 'Country',
            'class': BASE_INPUT
        })
    )
    office_zipcode = forms.CharField(
        label="Zipcode",
        widget=forms.TextInput(attrs={
            'placeholder': 'Zipcode',
            'class': BASE_INPUT
        })
    )
      
    # Plan Selection
    plan_type = forms.ChoiceField(
        choices=PLAN_CHOICES, 
        label="Subscription Plan",
        initial="1",
        widget=forms.Select(attrs={"class": BASE_SELECT})
    ) 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contact_number'].widget.attrs.update({'class': BASE_INPUT})


    # def clean_tenant_id(self):
    #     # Validate that the requested tenant_id slug is unique
    #     tenant_id = self.cleaned_data["tenant_id"].upper()
    #     if Vendor.objects.filter(tenant_id=tenant_id).exists():
    #         raise ValidationError("This Tenant ID is already taken.")
    #     return tenant_id

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

# # apps/tenants/forms.py
# from django import forms
# from .models import PLAN_CHOICES
# from django import forms
# from django.core.exceptions import ValidationError
# # from .models import Vendor 
# from apps.accounts.models import User
# from phonenumber_field.formfields import PhoneNumberField
# from phonenumber_field.widgets import PhoneNumberPrefixWidget


# BASE_INPUT = "w-full px-4 py-2 rounded-md border border-gray-300 focus:outline-none focus:ring-2 focus:ring-nav-blue"
# BASE_SELECT = "w-full px-4 py-2 rounded-md border border-gray-300 bg-white focus:outline-none focus:ring-2 focus:ring-nav-blue"


# class VendorOnboardingForm(forms.Form):
#     # Business Information
#     name = forms.CharField(max_length=255, label="Business / Lab Name", widget=forms.TextInput(attrs={"placeholder": "Enter your lab name. Please note: it will used to setup you domain", "class": BASE_INPUT}))
    
#     # Admin User Information
#     admin_email = forms.EmailField(label="Admin Email",
#         widget=forms.EmailInput(attrs={
#             "placeholder": "yourmail@example.com",
#             "class": BASE_INPUT
#         })
#     )
#     admin_first_name = forms.CharField(
#         label="First Name", 
#         widget=forms.TextInput(attrs={
#             "placeholder": "First Name",
#             "class": BASE_INPUT
#         })
#     )
#     admin_last_name = forms.CharField(
#         label="Last Name",
#         widget=forms.TextInput(attrs={
#             "placeholder": "Last Name", 
#             "class": BASE_INPUT
#         })
#     )

#     contact_number = PhoneNumberField(required=False)
#     # contact_number = PhoneNumberField(
#     #     required=False,
#     #     error_messages={
#     #         'invalid': 'Please enter a valid international phone number.',
#     #     },
#     #     widget=forms.TextInput(attrs={
#     #         "class": BASE_INPUT,
#     #         "id": "id_contact_number",
#     #         "placeholder": "Country code(+234)",
#     #         "autocomplete": "tel"
#     #     })
#     # )


#     admin_password = forms.CharField(
#         widget=forms.PasswordInput(attrs={"class": BASE_INPUT}),
#         label="Password"
#     )
#     admin_password_confirm = forms.CharField(
#         widget=forms.PasswordInput(attrs={"class": BASE_INPUT}),
#         label="Confirm Password"
#     )
    
#     # Address Information
#     office_street_address = forms.CharField(
#         label="Street Address",
#         widget=forms.TextInput(attrs={
#             'placeholder': 'Street or Road Address',
#             'class': BASE_INPUT
#         })
#     )
#     office_city_state = forms.CharField(
#         label="City & State",
#         widget=forms.TextInput(attrs={
#             'placeholder': 'City and State',
#             'class': BASE_INPUT
#         })
#     )
#     office_country = forms.CharField(  # Fixed field name from office_county
#         label="Country",
#         widget=forms.TextInput(attrs={
#             'placeholder': 'Country',
#             'class': BASE_INPUT
#         })
#     )
#     office_zipcode = forms.CharField(
#         label="Zipcode",
#         widget=forms.TextInput(attrs={
#             'placeholder': 'Zipcode',
#             'class': BASE_INPUT
#         })
#     )
      
#     # Plan Selection
#     plan_type = forms.ChoiceField(
#         choices=PLAN_CHOICES, 
#         label="Subscription Plan",
#         initial="1",
#         widget=forms.Select(attrs={"class": BASE_SELECT})
#     ) 

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
    
#         # self.fields['contact_number'].widget.widgets[0].attrs.update({
#         #     'class': BASE_SELECT,
#         #     'style': 'width: 28%; display: inline-block; margin-right: 2%;'
#         # })
#         # self.fields['contact_number'].widget.widgets[1].attrs.update({
#         #     'class': BASE_INPUT,
#         #     'style': 'width: 70%; display: inline-block;'
#         # })

#     def clean_admin_email(self):
#         # Validate that the admin's email is unique across the *entire* platform
#         email = self.cleaned_data["admin_email"]
#         if User.objects.filter(email=email).exists():
#             raise ValidationError("A user with this email already exists.")
#         return email

#     def clean(self):
#         cleaned_data = super().clean()
#         password = cleaned_data.get("admin_password")
#         password_confirm = cleaned_data.get("admin_password_confirm")

#         if password and password != password_confirm:
#             self.add_error('admin_password_confirm', "Passwords do not match.")

#         # Optional: Validate domain name format if required
#         return cleaned_data
