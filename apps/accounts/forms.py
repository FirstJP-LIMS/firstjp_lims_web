# apps/accounts/forms.py
from django import forms
from django.contrib.auth import get_user_model
from apps.tenants.models import Vendor
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.db import transaction
from django.utils import timezone
from apps.labs.models import Patient 
from apps.patient.models import PatientUser
from apps.clinician.models import ClinicianProfile
from .models import VendorProfile
# app_name/forms.py
from django import forms
from apps.labs.models import Equipment, Department


User = get_user_model()

# TENANT_ALLOWED = {'vendor_admin', 'lab_staff', 'clinician', 'patient'}
LEARN_ALLOWED = {'learner', 'facilitator'}
TENANT_ALLOWED = {'lab_staff', 'clinician', 'patient'}


class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="Password",
        min_length=8,
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="Confirm Password"
    )
    
    # PATIENT-SPECIFIC FIELDS (only shown when role='patient')
    date_of_birth = forms.DateField(
        required=False,  # Will be required conditionally
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Date of Birth",
        help_text="Required for accurate test results"
    )
    
    gender = forms.ChoiceField(
        required=False,  # Will be required conditionally
        choices=[('', 'Select Gender'), ('M', 'Male'), ('F', 'Female')],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Gender"
    )
    
    preferred_notification = forms.ChoiceField(
        required=False,
        choices=[
            ('email', 'Email Only'),
            ('sms', 'SMS Only'),
            ('both', 'Email & SMS'),
        ],
        initial='email',
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Notification Preference"
    )
    
    consent_digital_results = forms.BooleanField(
        required=False,  # Will be required conditionally
        label="I consent to viewing my lab results online",
        help_text="Required to access test results through the patient portal",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    terms_and_conditions = forms.BooleanField(
        required=False,  # Will be required conditionally
        label="I agree to the Terms of Service and Privacy Policy",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    # ===== CLINICIAN-SPECIFIC FIELDS ===== Only seen when role == 'clinician'
    license_number = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Medical License Number",
        help_text="Required for verification"
    )
    
    specialization = forms.ChoiceField(
        required=False,
        choices=[('', 'Select Specialization')] + [
            ('general_practice', 'General Practice'),
            ('internal_medicine', 'Internal Medicine'),
            ('pediatrics', 'Pediatrics'),
            ('cardiology', 'Cardiology'),
            ('endocrinology', 'Endocrinology'),
            ('hematology', 'Hematology'),
            ('oncology', 'Oncology'),
            ('infectious_disease', 'Infectious Disease'),
            ('pathology', 'Pathology'),
            ('other', 'Other'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Specialization"
    )

        
    organization = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label="Hospital/Clinic Name"
    )
    
    qualifications = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'rows': 3}),
        label="Qualifications",
        help_text="e.g., MD, MBBS, DO, PhD"
    )

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name',
            'contact_number', 'password1', 'password2'
        ]
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, vendor=None, forced_role=None, is_learning_portal=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor
        self.forced_role = forced_role
        self.is_learning_portal = is_learning_portal
        
        # Make patient-specific fields required only for patient role
        if forced_role == 'patient':
            self.fields['date_of_birth'].required = True
            self.fields['gender'].required = True
            self.fields['consent_digital_results'].required = True
            self.fields['terms_and_conditions'].required = True
            # Remove clinician fields
            del self.fields['license_number']
            del self.fields['specialization']
            del self.fields['organization']
            del self.fields['qualifications']
        
        elif forced_role == 'clinician':
            # Make clinician fields required
            self.fields['license_number'].required = True
            self.fields['specialization'].required = True
            self.fields['organization'].required = True
            # Remove patient fields
            del self.fields['date_of_birth']
            del self.fields['gender']
            del self.fields['preferred_notification']
            del self.fields['consent_digital_results']
            del self.fields['terms_and_conditions']
        else:
            # Lab staff, vendor admin - remove both patient and clinician fields
            for field in ['date_of_birth', 'gender', 'preferred_notification', 'consent_digital_results', 'terms_and_conditions', 'license_number', 'specialization', 'organization', 'qualifications']:
                if field in self.fields:
                    del self.fields[field]

    def clean(self):
        cleaned = super().clean()
        role = self.forced_role

        if not role:
            raise forms.ValidationError("Registration role not supplied.")

        # Validate roles
        if self.is_learning_portal:
            if role not in LEARN_ALLOWED:
                raise forms.ValidationError("Invalid role for learning portal.")

        elif self.vendor:
            if role not in TENANT_ALLOWED:
                raise forms.ValidationError("Invalid role for tenant registration.")

        else:
            if role != 'platform_admin':
                raise forms.ValidationError("Invalid platform role.")
        
        # Patient-specific validation
        if role == 'patient':
            if not cleaned.get('consent_digital_results'):
                raise forms.ValidationError(
                    "You must consent to viewing digital results to create a patient account."
                )
            if not cleaned.get('terms_and_conditions'):
                raise forms.ValidationError(
                    "You must accept the terms and conditions."
                )

        return cleaned

    def clean_email(self):
        email = self.cleaned_data.get('email')

        if self.vendor and User.objects.filter(email=email, vendor=self.vendor).exists():
            raise forms.ValidationError(
                f"An account with this email already exists at {self.vendor.name}."
            )
        return email

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match')
        return p2
    
    def clean_date_of_birth(self):
        """Validate date of birth for patients."""
        dob = self.cleaned_data.get('date_of_birth')
        if dob and self.forced_role == 'patient':
            from datetime import date
            age = (date.today() - dob).days // 365
            if age < 0:
                raise forms.ValidationError("Date of birth cannot be in the future.")
            if age < 18:
                raise forms.ValidationError(
                    "You must be 18 or older to create a patient account."
                )
        return dob

    def save(self, commit=True, vendor=None):
        """
        Save user and create role specific profiles.
        """
        data = self.cleaned_data
        pwd = data['password1']
        role = self.forced_role

        vendor_to_use = vendor if vendor else self.vendor
        if self.is_learning_portal:
            vendor_to_use = None

        user = User(
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            contact_number=data.get('contact_number'),
            vendor=vendor_to_use,
            role=role,
        )
        user.set_password(pwd)

        if commit:
            with transaction.atomic():
                user.save()
                
                # Create Patient and PatientUser records if role is 'patient'
                if role == 'patient' and vendor_to_use:
                    # Create Patient record (for lab operations)
                    patient = Patient.objects.create(
                        vendor=vendor_to_use,
                        first_name=data['first_name'],
                        last_name=data['last_name'],
                        date_of_birth=data.get('date_of_birth'),
                        gender=data.get('gender'),
                        contact_email=data['email'],
                        contact_phone=data.get('contact_number', ''),
                    )
                    # patient_id is auto-generated via Patient.save()
                    
                    # Create PatientUser record (portal access bridge)
                    PatientUser.objects.create(
                        user=user,
                        patient=patient,
                        preferred_notification=data.get('preferred_notification', 'email'),
                        consent_to_digital_results=data.get('consent_digital_results', False),
                        terms_accepted_at=timezone.now(),
                        # email_verified=False,  # Will be verified later
                        # phone_verified=False,
                        email_verified=True,  # Will be verified later
                        phone_verified=True,
                    )

                # Create ClinicianProfile if role is 'clinician'
                elif role == 'clinician' and vendor_to_use:
                    ClinicianProfile.objects.create(
                        user=user,
                        license_number=data.get('license_number', ''),
                        specialization=data.get('specialization', 'general_practice'),
                        organization=data.get('organization', ''),
                        qualifications=data.get('qualifications', ''),
                        is_verified=False,  # Requires admin verification
                        is_active=True,
                    )
        
        return user
    

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

