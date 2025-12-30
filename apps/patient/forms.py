# In patients/forms.py

from django import forms
from django.db import transaction
from django.utils import timezone
from .models import PatientUser
from apps.labs.models import Patient, TestRequest, VendorTest


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


from django.core.exceptions import ValidationError
from apps.labs.models import TestRequest, VendorTest

class PatientTestOrderForm(forms.ModelForm):
    """
    Simplified form for patients to order tests for themselves.
    Patients can only order tests marked as available_for_online_booking.
    """
    
    requested_tests = forms.ModelMultipleChoiceField(
        queryset=VendorTest.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Select Tests",
        help_text="Choose the tests you would like to request"
    )
    
    reason_for_testing = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional: Why are you requesting these tests? (e.g., routine checkup, symptoms you\'re experiencing)'
        }),
        label="Reason for Testing (Optional)"
    )
    
    class Meta:
        model = TestRequest
        fields = ['requested_tests', 'reason_for_testing', 'clinical_history', 'has_informed_consent']
        
        widgets = {
            'clinical_history': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Any relevant medical history, medications, or allergies we should know about'
            }),
            'has_informed_consent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
        labels = {
            'clinical_history': 'Medical History (Optional)',
            'has_informed_consent': 'I consent to these tests and understand the preparation requirements',
        }
    
    def __init__(self, *args, user=None, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.user = user
        self.vendor = vendor
        
        # DEBUG: Print to see what's happening
        print(f"DEBUG - PatientTestOrderForm init:")
        print(f"  User: {user}")
        print(f"  Vendor: {vendor}")
        
        # Only show tests available for patient self-ordering
        if vendor:
            available_tests = VendorTest.objects.filter(
                vendor=vendor,
                enabled=True,
                available_for_online_booking=True
            ).select_related('assigned_department').order_by('name')
            
            print(f"  Available tests count: {available_tests.count()}")
            
            self.fields['requested_tests'].queryset = available_tests
        else:
            print("  WARNING: No vendor provided!")
        
        # Make consent required
        self.fields['has_informed_consent'].required = True
    
    def clean_requested_tests(self):
        """Validate test selection and check patient eligibility."""
        tests = self.cleaned_data.get('requested_tests')
        
        if not tests or tests.count() == 0:
            raise ValidationError("Please select at least one test.")
        
        # Verify all tests are patient-accessible
        for test in tests:
            if not test.can_be_ordered_by_patient():
                raise ValidationError(
                    f"The test '{test.name}' requires clinician authorization and cannot be self-ordered."
                )
        
        return tests
    
    def clean(self):
        cleaned = super().clean()
        
        # Ensure consent is checked
        if not cleaned.get('has_informed_consent'):
            raise ValidationError({
                'has_informed_consent': 'You must consent to proceed with the test request.'
            })
        
        return cleaned
    
    @property
    def total_order_price(self):
        """Calculate total price of selected tests."""
        if hasattr(self, 'cleaned_data'):
            tests = self.cleaned_data.get('requested_tests', [])
            total = sum(test.price for test in tests)
            return total
        return 0
    
    def save(self, commit=True):
        """Create test request for patient self-order."""
        instance = super().save(commit=False)
        
        # Set vendor
        instance.vendor = self.vendor
        
        # Get patient from user's patient_profile
        try:
            patient_user = self.user.patient_profile
            instance.patient = patient_user.patient
        except AttributeError:
            raise ValueError("User does not have a patient profile.")
        
        # Set attribution (patient self-order)
        instance.requested_by = self.user
        instance.ordering_clinician = None  # No clinician for self-orders
        
        # Copy reason to clinical_indication
        instance.clinical_indication = self.cleaned_data.get('reason_for_testing', '')
        
        # Always routine priority for patient self-orders
        instance.priority = 'routine'
        
        if commit:
            with transaction.atomic():
                instance.save()
                
                # Add selected tests
                instance.requested_tests.set(self.cleaned_data['requested_tests'])
                
                # Check if any tests require approval
                instance.check_approval_requirement()
        
        return instance


# patients/forms.py

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Appointment, AppointmentSlot
from apps.labs.models import Patient

class AppointmentBookingForm(forms.ModelForm):
    """
    Form for booking appointments - handles both authenticated and unauthenticated users.
    """
    # Patient lookup (optional - for authenticated users)
    existing_patient = forms.ModelChoiceField(
        queryset=Patient.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Select if you're an existing patient"
    )
    
    # Visitor details (required if not authenticated or no existing patient)
    visitor_first_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'})
    )
    visitor_last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'})
    )
    visitor_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )
    visitor_phone = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'})
    )
    visitor_date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    visitor_gender = forms.ChoiceField(
        choices=[('', 'Select Gender'), ('M', 'Male'), ('F', 'Female')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Slot selection
    slot = forms.ModelChoiceField(
        queryset=AppointmentSlot.objects.none(),
        widget=forms.RadioSelect,
        error_messages={'required': 'Please select an available time slot'}
    )
    
    class Meta:
        model = Appointment
        fields = [
            'appointment_type',
            'reason_for_visit',
            'special_requirements',
        ]
        widgets = {
            'appointment_type': forms.Select(attrs={'class': 'form-control'}),
            'reason_for_visit': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Brief description of your visit (optional)'
            }),
            'special_requirements': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Any special needs? (wheelchair access, etc.)'
            }),
        }
    
    def __init__(self, *args, vendor=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor
        self.user = user
        
        if vendor:
            # Load available slots (next 30 days)
            today = timezone.now().date()
            future_date = today + timezone.timedelta(days=30)
            
            self.fields['slot'].queryset = AppointmentSlot.objects.filter(
                vendor=vendor,
                date__gte=today,
                date__lte=future_date,
                is_active=True
            ).exclude(
                current_bookings__gte=models.F('max_appointments')
            ).select_related('vendor')
            
            # If user is authenticated patient, load their existing patient record
            if user and user.is_authenticated and hasattr(user, 'patient_profile'):
                try:
                    patient = user.patient_profile.patient
                    self.fields['existing_patient'].queryset = Patient.objects.filter(
                        id=patient.id, vendor=vendor
                    )
                    self.fields['existing_patient'].initial = patient
                except Exception:
                    pass
    
    def clean(self):
        cleaned_data = super().clean()
        existing_patient = cleaned_data.get('existing_patient')
        
        # Check if we have patient data (either linked or visitor)
        if not existing_patient:
            # Validate visitor data
            required_visitor_fields = [
                'visitor_first_name',
                'visitor_last_name',
                'visitor_email',
                'visitor_phone',
            ]
            
            missing_fields = [
                field for field in required_visitor_fields
                if not cleaned_data.get(field)
            ]
            
            if missing_fields:
                raise ValidationError(
                    "Please provide your contact information: " +
                    ", ".join([f.replace('visitor_', '').replace('_', ' ').title() for f in missing_fields])
                )
            
            # Validate at least one contact method
            if not cleaned_data.get('visitor_email') and not cleaned_data.get('visitor_phone'):
                raise ValidationError("Please provide either email or phone number.")
        
        # Validate slot availability
        slot = cleaned_data.get('slot')
        if slot:
            if not slot.is_available:
                raise ValidationError("Sorry, this time slot is no longer available.")
            
            if slot.is_past:
                raise ValidationError("Cannot book appointments in the past.")
        
        return cleaned_data
    
    def save(self, commit=True):
        appointment = super().save(commit=False)
        appointment.vendor = self.vendor
        
        # Link to existing patient or use visitor data
        existing_patient = self.cleaned_data.get('existing_patient')
        if existing_patient:
            appointment.patient = existing_patient
        else:
            # Store visitor data
            appointment.visitor_first_name = self.cleaned_data['visitor_first_name']
            appointment.visitor_last_name = self.cleaned_data['visitor_last_name']
            appointment.visitor_email = self.cleaned_data.get('visitor_email', '')
            appointment.visitor_phone = self.cleaned_data.get('visitor_phone', '')
            appointment.visitor_date_of_birth = self.cleaned_data.get('visitor_date_of_birth')
            appointment.visitor_gender = self.cleaned_data.get('visitor_gender', '')
        
        if self.user and self.user.is_authenticated:
            appointment.booked_by_user = self.user
        
        if commit:
            appointment.save()
            
            # Increment slot booking count
            slot = appointment.slot
            slot.current_bookings += 1
            slot.save(update_fields=['current_bookings'])
        
        return appointment
    

# patients/forms.py - ADD THESE FORMS

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from .models import AppointmentSlot, AppointmentSlotTemplate

class AppointmentSlotTemplateForm(forms.ModelForm):
    """
    Form for creating recurring slot templates.
    """
    class Meta:
        model = AppointmentSlotTemplate
        fields = [
            'name',
            'start_time',
            'end_time',
            'duration_minutes',
            'recurrence_pattern',
            'monday', 'tuesday', 'wednesday', 'thursday', 
            'friday', 'saturday', 'sunday',
            'max_appointments',
            'slot_type',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Morning Sample Collection'
            }),
            'start_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'end_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'duration_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '15',
                'step': '15'
            }),
            'recurrence_pattern': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_recurrence_pattern'
            }),
            'max_appointments': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'slot_type': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        recurrence_pattern = cleaned_data.get('recurrence_pattern')
        
        # Validate time range
        if start_time and end_time:
            if end_time <= start_time:
                raise ValidationError("End time must be after start time.")
        
        # Validate specific days selection
        if recurrence_pattern == 'specific_days':
            days_selected = any([
                cleaned_data.get('monday'),
                cleaned_data.get('tuesday'),
                cleaned_data.get('wednesday'),
                cleaned_data.get('thursday'),
                cleaned_data.get('friday'),
                cleaned_data.get('saturday'),
                cleaned_data.get('sunday'),
            ])
            if not days_selected:
                raise ValidationError("Please select at least one day of the week.")
        
        return cleaned_data


class GenerateSlotsForm(forms.Form):
    """
    Form for generating slots from a template.
    """
    template = forms.ModelChoiceField(
        queryset=AppointmentSlotTemplate.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Slot Template"
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="Start Date",
        help_text="Generate slots starting from this date"
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label="End Date",
        help_text="Generate slots until this date"
    )
    
    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        if vendor:
            self.fields['template'].queryset = AppointmentSlotTemplate.objects.filter(
                vendor=vendor,
                is_active=True
            )
        
        # Set default dates (next 30 days)
        today = timezone.now().date()
        self.fields['start_date'].initial = today
        self.fields['end_date'].initial = today + timedelta(days=30)
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError("End date must be after start date.")
            
            # Prevent generating too many slots at once
            days_diff = (end_date - start_date).days
            if days_diff > 90:
                raise ValidationError("Cannot generate slots for more than 90 days at once.")
        
        return cleaned_data


class AppointmentSlotEditForm(forms.ModelForm):
    """
    Form for editing individual appointment slots.
    """
    class Meta:
        model = AppointmentSlot
        fields = [
            'date',
            'start_time',
            'end_time',
            'max_appointments',
            'slot_type',
            'is_active',
        ]
        widgets = {
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'start_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'end_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'max_appointments': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'slot_type': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def clean_max_appointments(self):
        """Prevent reducing capacity below current bookings."""
        max_appointments = self.cleaned_data.get('max_appointments')
        
        if self.instance and self.instance.pk:
            current_bookings = self.instance.current_bookings
            if max_appointments < current_bookings:
                raise ValidationError(
                    f"Cannot reduce capacity to {max_appointments}. "
                    f"This slot already has {current_bookings} booking(s)."
                )
        
        return max_appointments


class BulkSlotActionForm(forms.Form):
    """
    Form for bulk actions on appointment slots.
    """
    ACTION_CHOICES = [
        ('', 'Select Action'),
        ('activate', 'Activate Selected'),
        ('deactivate', 'Deactivate Selected'),
        ('delete', 'Delete Selected (if no bookings)'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Bulk Action"
    )
    
    slot_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    def clean_slot_ids(self):
        """Parse comma-separated slot IDs."""
        slot_ids_str = self.cleaned_data.get('slot_ids', '')
        
        try:
            slot_ids = [int(id.strip()) for id in slot_ids_str.split(',') if id.strip()]
            if not slot_ids:
                raise ValidationError("No slots selected.")
            return slot_ids
        except (ValueError, TypeError):
            raise ValidationError("Invalid slot IDs.")


            