# In patients/forms.py

from django import forms
from apps.labs.models import Patient
from .models import PatientUser

class PatientProfileForm(forms.Form):
    """
    Combined form for editing Patient and PatientUser information.
    Email is read-only for security.
    """
    
    # ===== Patient Model Fields (labs.Patient) =====
    first_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    last_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    date_of_birth = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        help_text="Cannot be changed after initial registration for security reasons"
    )
    
    gender = forms.ChoiceField(
        required=True,
        choices=[('M', 'Male'), ('F', 'Female')],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    contact_phone = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 XXX XXX XXXX'}),
        help_text="For appointment reminders and critical result notifications"
    )
    
    # ===== PatientUser Model Fields (patients.PatientUser) =====
    preferred_notification = forms.ChoiceField(
        required=False,
        choices=[
            ('email', 'Email Only'),
            ('sms', 'SMS Only'),
            ('both', 'Email & SMS'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Notification Preference"
    )
    
    language_preference = forms.ChoiceField(
        required=False,
        choices=[
            ('en', 'English'),
            ('fr', 'French'),
            ('es', 'Spanish'),
            # Add more languages as needed
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Language"
    )
    
    timezone = forms.ChoiceField(
        required=False,
        choices=[
            ('Africa/Lagos', 'Lagos (WAT)'),
            ('Africa/Accra', 'Accra (GMT)'),
            ('Africa/Cairo', 'Cairo (EET)'),
            ('UTC', 'UTC'),
            # Add more timezones as needed
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Timezone"
    )
    
    def __init__(self, *args, patient=None, patient_user=None, **kwargs):
        """
        Initialize form with existing patient data.
        
        Args:
            patient: labs.Patient instance
            patient_user: patients.PatientUser instance
        """
        self.patient = patient
        self.patient_user = patient_user
        
        # Pre-populate form with existing data
        if patient and patient_user and not kwargs.get('data'):
            kwargs['initial'] = {
                # Patient fields
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'date_of_birth': patient.date_of_birth,
                'gender': patient.gender,
                'contact_phone': patient.contact_phone,
                # PatientUser fields
                'preferred_notification': patient_user.preferred_notification,
                'language_preference': patient_user.language_preference,
                'timezone': patient_user.timezone,
            }
        
        super().__init__(*args, **kwargs)
        
        # Make date_of_birth read-only after initial registration
        if patient and patient.date_of_birth:
            self.fields['date_of_birth'].widget.attrs['readonly'] = True
            self.fields['date_of_birth'].help_text = "Date of birth cannot be changed for security reasons. Contact support if incorrect."
    
    def clean_date_of_birth(self):
        """
        Prevent changing date of birth after initial registration.
        Allow only if it was previously empty.
        """
        dob = self.cleaned_data.get('date_of_birth')
        
        if self.patient and self.patient.date_of_birth:
            # Don't allow changing existing DOB
            if dob != self.patient.date_of_birth:
                raise forms.ValidationError(
                    "Date of birth cannot be changed. Please contact support if this information is incorrect."
                )
        
        # Validate age
        if dob:
            from datetime import date
            age = (date.today() - dob).days // 365
            if age < 0:
                raise forms.ValidationError("Date of birth cannot be in the future.")
            if age < 18:
                raise forms.ValidationError("Patient must be 18 or older.")
            if age > 120:
                raise forms.ValidationError("Please enter a valid date of birth.")
        
        return dob
    
    def clean_contact_phone(self):
        """Validate phone number format."""
        phone = self.cleaned_data.get('contact_phone')
        if phone:
            # Remove spaces and common separators
            cleaned = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            
            # Basic validation (adjust based on your region)
            if not cleaned.replace('+', '').isdigit():
                raise forms.ValidationError("Please enter a valid phone number.")
            
            if len(cleaned) < 10:
                raise forms.ValidationError("Phone number is too short.")
        
        return phone
    
    def save(self):
        """
        Save changes to both Patient and PatientUser models.
        Returns tuple: (patient, patient_user)
        """
        if not self.patient or not self.patient_user:
            raise ValueError("Patient and PatientUser instances required to save.")
        
        from django.db import transaction
        
        with transaction.atomic():
            # Update Patient model
            self.patient.first_name = self.cleaned_data['first_name']
            self.patient.last_name = self.cleaned_data['last_name']
            self.patient.date_of_birth = self.cleaned_data['date_of_birth']
            self.patient.gender = self.cleaned_data['gender']
            self.patient.contact_phone = self.cleaned_data['contact_phone']
            self.patient.save()
            
            # Update PatientUser model
            self.patient_user.preferred_notification = self.cleaned_data['preferred_notification']
            self.patient_user.language_preference = self.cleaned_data['language_preference']
            self.patient_user.timezone = self.cleaned_data['timezone']
            self.patient_user.save()
        
        return self.patient, self.patient_user


# class ChangeEmailRequestForm(forms.Form):
#     """
#     Separate form for requesting email change (requires verification).
#     """
#     new_email = forms.EmailField(
#         required=True,
#         widget=forms.EmailInput(attrs={'class': 'form-control'}),
#         label="New Email Address"
#     )
    
#     confirm_email = forms.EmailField(
#         required=True,
#         widget=forms.EmailInput(attrs={'class': 'form-control'}),
#         label="Confirm New Email"
#     )
    
#     password = forms.CharField(
#         required=True,
#         widget=forms.PasswordInput(attrs={'class': 'form-control'}),
#         label="Current Password",
#         help_text="For security verification"
#     )
    
#     def __init__(self, *args, user=None, **kwargs):
#         self.user = user
#         super().__init__(*args, **kwargs)
    
#     def clean_confirm_email(self):
#         """Ensure emails match."""
#         email1 = self.cleaned_data.get('new_email')
#         email2 = self.cleaned_data.get('confirm_email')
        
#         if email1 and email2 and email1 != email2:
#             raise forms.ValidationError("Email addresses do not match.")
        
#         return email2
    
#     def clean_new_email(self):
#         """Check if email is already in use."""
#         email = self.cleaned_data.get('new_email')
        
#         if self.user and email == self.user.email:
#             raise forms.ValidationError("This is already your current email address.")
        
#         # Check if email exists for this vendor
#         if self.user and self.user.vendor:
#             from django.contrib.auth import get_user_model
#             User = get_user_model()
            
#             if User.objects.filter(email=email, vendor=self.user.vendor).exists():
#                 raise forms.ValidationError("This email is already registered.")
        
#         return email
    
#     def clean_password(self):
#         """Verify current password."""
#         password = self.cleaned_data.get('password')
        
#         if self.user and not self.user.check_password(password):
#             raise forms.ValidationError("Incorrect password.")
        
#         return password


# class PasswordChangeForm(forms.Form):
#     """
#     Custom password change form for patients.
#     """
#     current_password = forms.CharField(
#         required=True,
#         widget=forms.PasswordInput(attrs={'class': 'form-control'}),
#         label="Current Password"
#     )
    
#     new_password1 = forms.CharField(
#         required=True,
#         widget=forms.PasswordInput(attrs={'class': 'form-control'}),
#         label="New Password",
#         min_length=8,
#         help_text="Password must be at least 8 characters"
#     )
    
#     new_password2 = forms.CharField(
#         required=True,
#         widget=forms.PasswordInput(attrs={'class': 'form-control'}),
#         label="Confirm New Password"
#     )
    
#     def __init__(self, *args, user=None, **kwargs):
#         self.user = user
#         super().__init__(*args, **kwargs)
    
#     def clean_current_password(self):
#         """Verify current password."""
#         password = self.cleaned_data.get('current_password')
        
#         if self.user and not self.user.check_password(password):
#             raise forms.ValidationError("Current password is incorrect.")
        
#         return password
    
#     def clean_new_password2(self):
#         """Ensure new passwords match."""
#         pwd1 = self.cleaned_data.get('new_password1')
#         pwd2 = self.cleaned_data.get('new_password2')
        
#         if pwd1 and pwd2 and pwd1 != pwd2:
#             raise forms.ValidationError("New passwords do not match.")
        
#         return pwd2
    
#     def save(self):
#         """Update user password."""
#         if not self.user:
#             raise ValueError("User instance required.")
        
#         self.user.set_password(self.cleaned_data['new_password1'])
#         self.user.save()
#         return self.user

