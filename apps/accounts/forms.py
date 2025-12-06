# apps/accounts/forms.py
from django import forms
from django.contrib.auth import get_user_model
from apps.tenants.models import Vendor
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm

User = get_user_model()

class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a strong password'
        }),
        label="Password",
        min_length=8,  # ✅ Add password strength
        help_text="Password must be at least 8 characters"
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password'
        }),
        label="Confirm Password"
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'contact_number')  # ✅ Add contact_number
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your@email.com'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First Name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Last Name'
            }),
            'contact_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+234 xxx xxx xxxx'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop('vendor', None)  # ✅ Store vendor for validation
        super().__init__(*args, **kwargs)
    
    def clean_email(self):
        """
        Validate email is unique within this tenant.
        """
        email = self.cleaned_data.get('email')
        
        if self.vendor:
            # Check if email already exists for this vendor
            if User.objects.filter(email=email, vendor=self.vendor).exists():
                raise forms.ValidationError(
                    f"An account with this email already exists at {self.vendor.name}. "
                    "Please login or use a different email."
                )
        
        return email

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match')
        
        # ✅ Add password strength validation
        if p1 and len(p1) < 8:
            raise forms.ValidationError('Password must be at least 8 characters long')
        
        return p2

    def save(self, commit=True, vendor=None, role='lab_staff'):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        
        if vendor:
            user.vendor = vendor
        elif self.vendor:
            user.vendor = self.vendor
        
        user.role = role
        
        if commit:
            user.save()
        
        return user

# class RegistrationForm(forms.ModelForm):
#     password1 = forms.CharField(
#         widget=forms.PasswordInput(attrs={
#             'class': 'form-control',
#             'placeholder': 'Create a strong password'
#         }),
#         label="Password"
#     )
#     password2 = forms.CharField(
#         widget=forms.PasswordInput(attrs={
#             'class': 'form-control',
#             'placeholder': 'Confirm your password'
#         }),
#         label="Confirm Password"
#     )

#     class Meta:
#         model = User
#         fields = ('email', 'first_name', 'last_name')
#         widgets = {
#             'email': forms.EmailInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'your@email.com'
#             }),
#             'first_name': forms.TextInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'First Name'
#             }),
#             'last_name': forms.TextInput(attrs={
#                 'class': 'form-control', 
#                 'placeholder': 'Last Name'
#             }),
#         }

#     def clean_password2(self):
#         p1 = self.cleaned_data.get('password1')
#         p2 = self.cleaned_data.get('password2')
#         if p1 and p2 and p1 != p2:
#             raise forms.ValidationError('Passwords do not match')
#         return p2

#     def save(self, commit=True, vendor=None, role='lab_staff'):
#         user = super().save(commit=False)
#         user.set_password(self.cleaned_data['password1'])
#         if vendor:
#             user.vendor = vendor
#         user.role = role
#         if commit:
#             user.save()
#         return user


class TenantAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter your email address',
                'autofocus': True,
            }
        ),
        label='Email Address',
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
                'placeholder': 'Enter your password',
            }
        ),
        label='Password',
    )


class TenantPasswordResetForm(PasswordResetForm):
    """
    Tenant-scoped password reset: only finds users belonging to the current tenant.
    """
    
    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)  # Pass tenant from view
        super().__init__(*args, **kwargs)
        
        # Update field styling
        self.fields['email'].widget.attrs.update({
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
            'placeholder': 'Enter your registered email'
        })
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        # Validate that user exists in THIS tenant
        if self.tenant:
            user_exists = User.objects.filter(
                email=email,
                vendor=self.tenant,
                is_active=True
            ).exists()
            
            if not user_exists:
                # Don't reveal if email exists (security)
                # But internally we know it's tenant-scoped
                pass
        
        return email
    
    def get_users(self, email):
        """
        Override to return only users from the current tenant.
        This is called by Django's password reset view.
        """
        if not self.tenant:
            return User.objects.none()  # No tenant = no users
        
        # Only return active users from THIS tenant
        active_users = User.objects.filter(
            email__iexact=email,
            vendor=self.tenant,
            is_active=True,
        )
        
        return (
            u for u in active_users
            if u.has_usable_password() and 
            u.email  # Ensure email is not empty
        )



from django import forms
from .models import VendorProfile

class VendorProfileForm(forms.ModelForm):
    class Meta:
        model = VendorProfile
        fields = [
            "logo",
            "registration_number",
            "contact_number",
            "office_address",
            "office_city_state",
            "office_country",
            "office_zipcode",
        ]

        widgets = {
            "office_address": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "office_city_state": forms.TextInput(attrs={"class": "form-control"}),
            "office_country": forms.TextInput(attrs={"class": "form-control"}),
            "office_zipcode": forms.TextInput(attrs={"class": "form-control"}),
            "contact_number": forms.TextInput(attrs={"class": "form-control"}),
            "registration_number": forms.TextInput(attrs={"class": "form-control"}),
        }


# app_name/forms.py
from django import forms
from apps.labs.models import Equipment, Department

class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [
            "name",
            "model",
            "serial_number",
            "department",
            "api_endpoint",
            "api_key",
            "supports_auto_fetch",
        ]
    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop("vendor", None)
        super().__init__(*args, **kwargs)

        # Filter departments based on vendor
        if vendor:
            self.fields["department"].queryset = Department.objects.filter(vendor=vendor)

    def clean_serial_number(self):
        serial = self.cleaned_data.get("serial_number")
        if Equipment.objects.filter(serial_number=serial).exists():
            raise forms.ValidationError("Equipment with this serial number already exists.")
        return serial



# # apps/accounts/forms.py
# from django import forms
# from django.contrib.auth import get_user_model
# from apps.tenants.models import Vendor
# from django.contrib.auth.forms import AuthenticationForm

# User = get_user_model()

# class RegistrationForm(forms.ModelForm):
#     password1 = forms.CharField(
#         widget=forms.PasswordInput(attrs={
#             'class': 'form-control',
#             'placeholder': 'Create a strong password'
#         }),
#         label="Password"
#     )
#     password2 = forms.CharField(
#         widget=forms.PasswordInput(attrs={
#             'class': 'form-control',
#             'placeholder': 'Confirm your password'
#         }),
#         label="Confirm Password"
#     )

#     class Meta:
#         model = User
#         fields = ('email', 'first_name', 'last_name')
#         widgets = {
#             'email': forms.EmailInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'your@email.com'
#             }),
#             'first_name': forms.TextInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'First Name'
#             }),
#             'last_name': forms.TextInput(attrs={
#                 'class': 'form-control', 
#                 'placeholder': 'Last Name'
#             }),
#         }

#     def clean_password2(self):
#         p1 = self.cleaned_data.get('password1')
#         p2 = self.cleaned_data.get('password2')
#         if p1 and p2 and p1 != p2:
#             raise forms.ValidationError('Passwords do not match')
#         return p2

#     def clean_email(self):
#         # email can exist across vendors — so check within vendor in save() instead if needed
#         return self.cleaned_data['email'].lower()

#     # def save(self, commit=True, vendor=None, role='lab_staff'):
#     #     user = super().save(commit=False)
#     #     user.set_password(self.cleaned_data['password1'])
#     #     user.role = role
#     #     if vendor:
#     #         user.vendor = vendor
#     #     else:
#     #         user.vendor = None
#     #     if role in ('platform_admin',):
#     #         user.is_staff = True
#     #     if commit:
#     #         user.save()
#     #     return user
    
#     def save(self, commit=True, vendor=None, role='lab_staff'):
#         """
#         Save a global user. Tenant-specific role/membership should be created separately.
#         """
#         user = super().save(commit=False)
#         user.set_password(self.cleaned_data['password1'])
#         user.role = role

#         # Platform-level admin gets staff access
#         if role in ('platform_admin',):
#             user.is_staff = True

#         if commit:
#             user.save()
#             # If tenant is provided, create membership here
#             if vendor:
#                 from .models import UserTenantMembership
#                 UserTenantMembership.objects.create(
#                     user=user,
#                     vendor=vendor,
#                     role=role
#                 )
#         return user


# class TenantAuthenticationForm(AuthenticationForm):
#     email = forms.EmailField(
#         widget=forms.EmailInput(attrs={
#             'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
#             'placeholder': 'Enter your email address',
#             'autofocus': True,
#         }),
#         label='Email Address',
#     )
#     password = forms.CharField(
#         widget=forms.PasswordInput(attrs={
#             'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
#             'placeholder': 'Enter your password',
#         }),
#         label='Password',
#     )

# # apps/accounts/forms.py (add)


# class TenantPasswordResetForm(PasswordResetForm):
#     """
#     Tenant-scoped password reset lookup.
#     """
#     def get_users(self, email):
#         tenant = getattr(self.request, 'tenant', None)
#         email = email.lower()
#         qs = User._default_manager.filter(email__iexact=email, is_active=True)

#         if tenant:
#             qs = qs.filter(memberships__vendor=tenant, memberships__is_active=True)
#         else:
#             qs = qs.filter(vendor__isnull=True)

#         return qs




# # class TenantPasswordResetForm(PasswordResetForm):
# #     """
# #     Override to perform tenant-scoped lookup.
# #     """
# #     def get_users(self, email):
# #         """Yield active users matching the email for the current tenant."""
# #         # request is available as self.request when using PasswordResetView; ensure you pass request.
# #         tenant = getattr(self.request, 'tenant', None)
# #         email = email.lower()
# #         qs = User._default_manager.filter(email__iexact=email, is_active=True)
# #         if tenant:
# #             qs = qs.filter(vendor=tenant)
# #         else:
# #             qs = qs.filter(vendor__isnull=True)
# #         return qs



# from django import forms
# from .models import VendorProfile

# class VendorProfileForm(forms.ModelForm):
#     class Meta:
#         model = VendorProfile
#         fields = [
#             "logo",
#             "registration_number",
#             "contact_number",
#             "office_address",
#             "office_city_state",
#             "office_country",
#             "office_zipcode",
#         ]

#         widgets = {
#             "office_address": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
#             "office_city_state": forms.TextInput(attrs={"class": "form-control"}),
#             "office_country": forms.TextInput(attrs={"class": "form-control"}),
#             "office_zipcode": forms.TextInput(attrs={"class": "form-control"}),
#             "contact_number": forms.TextInput(attrs={"class": "form-control"}),
#             "registration_number": forms.TextInput(attrs={"class": "form-control"}),
#         }


# # app_name/forms.py
# from django import forms
# from apps.labs.models import Equipment, Department

# class EquipmentForm(forms.ModelForm):
#     class Meta:
#         model = Equipment
#         fields = [
#             "name",
#             "model",
#             "serial_number",
#             "department",
#             "api_endpoint",
#             "api_key",
#             "supports_auto_fetch",
#         ]
#     def __init__(self, *args, **kwargs):
#         vendor = kwargs.pop("vendor", None)
#         super().__init__(*args, **kwargs)

#         # Filter departments based on vendor
#         if vendor:
#             self.fields["department"].queryset = Department.objects.filter(vendor=vendor)

#     def clean_serial_number(self):
#         serial = self.cleaned_data.get("serial_number")
#         if Equipment.objects.filter(serial_number=serial).exists():
#             raise forms.ValidationError("Equipment with this serial number already exists.")
#         return serial

