from django import forms
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError

# Authenticatied User
from apps.labs.models import Patient, TestRequest, VendorTest


# For slot creation 
from datetime import timedelta
from .models import Appointment, AppointmentSlot
from .models import AppointmentSlot, AppointmentSlotTemplate

class AppointmentSlotTemplateForm(forms.ModelForm):
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
            'instructions',
            'is_active',
        ]

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get('recurrence_pattern') == 'specific_days':
            if not any(
                cleaned_data.get(day)
                for day in [
                    'monday', 'tuesday', 'wednesday',
                    'thursday', 'friday', 'saturday', 'sunday'
                ]
            ):
                raise ValidationError("Select at least one weekday.")

        return cleaned_data

class GenerateSlotsForm(forms.Form):
    template = forms.ModelChoiceField(
        queryset=AppointmentSlotTemplate.objects.none()
    )
    start_date = forms.DateField()
    end_date = forms.DateField()

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)

        if vendor:
            self.fields['template'].queryset = AppointmentSlotTemplate.objects.filter(
                vendor=vendor,
                is_active=True
            )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')

        if start and end:
            if end < start:
                raise ValidationError("End date must be after start date.")
            if (end - start).days > 90:
                raise ValidationError("Maximum range is 90 days.")

        return cleaned_data

class AppointmentSlotEditForm(forms.ModelForm):
    class Meta:
        model = AppointmentSlot
        fields = [
            'date',
            'start_time',
            'end_time',
            'max_appointments',
            'slot_type',
            'instructions',
            'is_active',
        ]

    def clean_max_appointments(self):
        max_appointments = self.cleaned_data['max_appointments']

        if self.instance.pk and max_appointments < self.instance.current_bookings:
            raise ValidationError(
                "Cannot reduce capacity below existing bookings."
            )

        return max_appointments


class BulkSlotActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=[
            ('activate', 'Activate'),
            ('deactivate', 'Deactivate'),
            ('delete', 'Delete (no bookings)'),
        ]
    )
    slot_ids = forms.CharField()

    def clean_slot_ids(self):
        try:
            ids = [int(pk) for pk in self.cleaned_data['slot_ids'].split(',')]
        except ValueError:
            raise ValidationError("Invalid slot IDs.")

        if not ids:
            raise ValidationError("No slots selected.")

        return ids



# API READY BOOKING FORM
class AppointmentBookingForm(forms.ModelForm):
    existing_patient = forms.ModelChoiceField(
        queryset=Patient.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    visitor_first_name = forms.CharField(max_length=100, required=False)
    visitor_last_name = forms.CharField(max_length=100, required=False)
    visitor_email = forms.EmailField(required=False)
    visitor_phone = forms.CharField(max_length=15, required=False)
    visitor_date_of_birth = forms.DateField(required=False)
    visitor_gender = forms.ChoiceField(
        choices=[('', 'Select Gender'), ('M', 'Male'), ('F', 'Female')],
        required=False
    )

    slot = forms.ModelChoiceField(
        queryset=AppointmentSlot.objects.none(),
        widget=forms.RadioSelect
    )

    class Meta:
        model = Appointment
        fields = ['appointment_type', 'reason_for_visit', 'special_requirements']

    def __init__(self, *args, vendor=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor
        self.user = user

        if vendor:
            today = timezone.now().date()
            self.fields['slot'].queryset = AppointmentSlot.objects.available_for_vendor(
                vendor=vendor,
                start_date=today,
                days=30
            )

        if user and user.is_authenticated and hasattr(user, 'patient_profile'):
            patient = user.patient_profile.patient
            self.fields['existing_patient'].queryset = Patient.objects.filter(
                id=patient.id,
                vendor=vendor
            )
            self.fields['existing_patient'].initial = patient

    def clean(self):
        cleaned_data = super().clean()
        slot = cleaned_data.get('slot')

        if not slot:
            return cleaned_data

        if slot.vendor_id != self.vendor.id:
            raise ValidationError("Invalid slot selected.")

        if not slot.is_available:
            raise ValidationError("This time slot is no longer available.")

        existing_patient = cleaned_data.get('existing_patient')

        if not existing_patient:
            required_fields = [
                'visitor_first_name',
                'visitor_last_name',
                'visitor_email',
                'visitor_phone',
            ]

            missing = [f for f in required_fields if not cleaned_data.get(f)]
            if missing:
                raise ValidationError("Please complete your contact details.")

        return cleaned_data





# class AppointmentBookingForm(forms.ModelForm):
#     existing_patient = forms.ModelChoiceField(
#         queryset=Patient.objects.none(),
#         required=False
#     )

#     slot = forms.ModelChoiceField(
#         queryset=AppointmentSlot.objects.none(),
#         widget=forms.RadioSelect
#     )

#     class Meta:
#         model = Appointment
#         fields = [
#             'appointment_type',
#             'reason_for_visit',
#             'special_requirements',
#         ]

#     def __init__(self, *args, vendor=None, user=None, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.vendor = vendor
#         self.user = user

#         today = timezone.now().date()

#         self.fields['slot'].queryset = AppointmentSlot.objects.filter(
#             vendor=vendor,
#             date__gte=today,
#             is_active=True
#         )

#         if user and user.is_authenticated and hasattr(user, 'patient_profile'):
#             patient = user.patient_profile.patient
#             self.fields['existing_patient'].queryset = Patient.objects.filter(
#                 pk=patient.pk
#             )
#             self.fields['existing_patient'].initial = patient

#     def clean(self):
#         cleaned_data = super().clean()

#         if not cleaned_data.get('existing_patient'):
#             required = ['visitor_first_name', 'visitor_last_name', 'visitor_email']
#             missing = [f for f in required if not cleaned_data.get(f)]

#             if missing:
#                 raise ValidationError("Please provide your contact details.")

#         slot = cleaned_data.get('slot')
#         if slot and not slot.is_available:
#             raise ValidationError("This slot is no longer available.")

#         return cleaned_data

#     def save(self, commit=True):
#         appointment = super().save(commit=False)
#         appointment.vendor = self.vendor
#         appointment.slot = self.cleaned_data['slot']

#         if self.user and self.user.is_authenticated:
#             appointment.booked_by_user = self.user

#         with transaction.atomic():
#             slot = AppointmentSlot.objects.select_for_update().get(
#                 pk=appointment.slot.pk
#             )

#             if not slot.is_available:
#                 raise ValidationError("Slot just filled up.")

#             appointment.save()
#             slot.current_bookings += 1
#             slot.save(update_fields=['current_bookings'])

#         return appointment





# class AppointmentSlotTemplateForm(forms.ModelForm):
#     """
#     Form for creating recurring slot templates.
#     """
#     class Meta:
#         model = AppointmentSlotTemplate
#         fields = [
#             'name',
#             'start_time',
#             'end_time',
#             'duration_minutes',
#             'recurrence_pattern',
#             'monday', 'tuesday', 'wednesday', 'thursday', 
#             'friday', 'saturday', 'sunday',
#             'max_appointments',
#             'slot_type',
#             'instructions',
#             'is_active',
#         ]
#         widgets = {
#             'name': forms.TextInput(attrs={
#                 'class': 'form-control',
#                 'placeholder': 'e.g., Consultation'
#             }),
#             'start_time': forms.TimeInput(attrs={
#                 'class': 'form-control',
#                 'type': 'time'
#             }),
#             'end_time': forms.TimeInput(attrs={
#                 'class': 'form-control',
#                 'type': 'time'
#             }),
#             'duration_minutes': forms.NumberInput(attrs={
#                 'class': 'form-control',
#                 'min': '15',
#                 'step': '15'
#             }),
#             'recurrence_pattern': forms.Select(attrs={
#                 'class': 'form-control',
#                 'id': 'id_recurrence_pattern'
#             }),
#             'max_appointments': forms.NumberInput(attrs={
#                 'class': 'form-control',
#                 'min': '1'
#             }),
#             'slot_type': forms.Select(attrs={'class': 'form-control'}),
            
#             'instructions': forms.Textarea(attrs={'class': 'form-control'}),

#             'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
#         }
    
#     def clean(self):
#         cleaned_data = super().clean()
#         start_time = cleaned_data.get('start_time')
#         end_time = cleaned_data.get('end_time')
#         recurrence_pattern = cleaned_data.get('recurrence_pattern')
        
#         # Validate time range
#         if start_time and end_time:
#             if end_time <= start_time:
#                 raise ValidationError("End time must be after start time.")
        
#         # Validate specific days selection
#         if recurrence_pattern == 'specific_days':
#             days_selected = any([
#                 cleaned_data.get('monday'),
#                 cleaned_data.get('tuesday'),
#                 cleaned_data.get('wednesday'),
#                 cleaned_data.get('thursday'),
#                 cleaned_data.get('friday'),
#                 cleaned_data.get('saturday'),
#                 cleaned_data.get('sunday'),
#             ])
#             if not days_selected:
#                 raise ValidationError("Please select at least one day of the week.")
        
#         return cleaned_data



# class GenerateSlotsForm(forms.Form):
#     """
#     Form for generating slots from a template.
#     """
#     template = forms.ModelChoiceField(
#         queryset=AppointmentSlotTemplate.objects.none(),
#         widget=forms.Select(attrs={'class': 'form-control'}),
#         label="Slot Template"
#     )
    
#     start_date = forms.DateField(
#         widget=forms.DateInput(attrs={
#             'class': 'form-control',
#             'type': 'date'
#         }),
#         label="Start Date",
#         help_text="Generate slots starting from this date"
#     )
    
#     end_date = forms.DateField(
#         widget=forms.DateInput(attrs={
#             'class': 'form-control',
#             'type': 'date'
#         }),
#         label="End Date",
#         help_text="Generate slots until this date"
#     )
    
#     def __init__(self, *args, vendor=None, **kwargs):
#         super().__init__(*args, **kwargs)
        
#         if vendor:
#             self.fields['template'].queryset = AppointmentSlotTemplate.objects.filter(
#                 vendor=vendor,
#                 is_active=True
#             )
        
#         # Set default dates (next 30 days)
#         today = timezone.now().date()
#         self.fields['start_date'].initial = today
#         self.fields['end_date'].initial = today + timedelta(days=30)
    
#     def clean(self):
#         cleaned_data = super().clean()
#         start_date = cleaned_data.get('start_date')
#         end_date = cleaned_data.get('end_date')
        
#         if start_date and end_date:
#             if end_date < start_date:
#                 raise ValidationError("End date must be after start date.")
            
#             # Prevent generating too many slots at once
#             days_diff = (end_date - start_date).days
#             if days_diff > 90:
#                 raise ValidationError("Cannot generate slots for more than 90 days at once.")
        
#         return cleaned_data




# class AppointmentSlotEditForm(forms.ModelForm):
#     """
#     Form for editing individual appointment slots.
#     """
#     class Meta:
#         model = AppointmentSlot
#         fields = [
#             'date',
#             'start_time',
#             'end_time',
#             'max_appointments',
#             'slot_type',
#             'instructions',
#             'is_active',
#         ]
#         widgets = {
#             'date': forms.DateInput(attrs={
#                 'class': 'form-control',
#                 'type': 'date'
#             }),
#             'start_time': forms.TimeInput(attrs={
#                 'class': 'form-control',
#                 'type': 'time'
#             }),
#             'end_time': forms.TimeInput(attrs={
#                 'class': 'form-control',
#                 'type': 'time'
#             }),
#             'max_appointments': forms.NumberInput(attrs={
#                 'class': 'form-control',
#                 'min': '1'
#             }),
#             'slot_type': forms.Select(attrs={'class': 'form-control'}),
#             'instructions': forms.Textarea(attrs={'class': 'form-control'}),
#             'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
#         }
    
#     def clean(self):
#         overlapping = AppointmentSlot.objects.filter(
#             vendor=self.vendor,
#             date=self.date,
#             start_time__lt=self.end_time,
#             end_time__gt=self.start_time
#         ).exclude(pk=self.pk)

#         if overlapping.exists():
#             raise ValidationError("This slot overlaps with an existing slot.")

#     def clean_max_appointments(self):
#         """Prevent reducing capacity below current bookings."""
#         max_appointments = self.cleaned_data.get('max_appointments')
        
#         if self.instance and self.instance.pk:
#             current_bookings = self.instance.current_bookings
#             if max_appointments < current_bookings:
#                 raise ValidationError(
#                     f"Cannot reduce capacity to {max_appointments}. "
#                     f"This slot already has {current_bookings} booking(s)."
#                 )
        
#         return max_appointments



# class BulkSlotActionForm(forms.Form):
#     """
#     Form for bulk actions on appointment slots.
#     """
#     ACTION_CHOICES = [
#         ('', 'Select Action'),
#         ('activate', 'Activate Selected'),
#         ('deactivate', 'Deactivate Selected'),
#         ('delete', 'Delete Selected (if no bookings)'),
#     ]
    
#     action = forms.ChoiceField(
#         choices=ACTION_CHOICES,
#         widget=forms.Select(attrs={'class': 'form-control'}),
#         label="Bulk Action"
#     )
    
#     slot_ids = forms.CharField(
#         widget=forms.HiddenInput(),
#         required=True
#     )
    
#     def clean_slot_ids(self):
#         """Parse comma-separated slot IDs."""
#         slot_ids_str = self.cleaned_data.get('slot_ids', '')
        
#         try:
#             slot_ids = [int(id.strip()) for id in slot_ids_str.split(',') if id.strip()]
#             if not slot_ids:
#                 raise ValidationError("No slots selected.")
#             return slot_ids
#         except (ValueError, TypeError):
#             raise ValidationError("Invalid slot IDs.")



# class AppointmentBookingForm(forms.ModelForm):
#     """
#     Form for booking appointments - handles both authenticated and unauthenticated users.
#     """
#     # Patient lookup (optional - for authenticated users)
#     existing_patient = forms.ModelChoiceField(
#         queryset=Patient.objects.none(),
#         required=False,
#         widget=forms.Select(attrs={'class': 'form-control'}),
#         help_text="Select if you're an existing patient"
#     )
    
#     # Visitor details (required if not authenticated or no existing patient)
#     visitor_first_name = forms.CharField(
#         max_length=100,
#         required=False,
#         widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'})
#     )
#     visitor_last_name = forms.CharField(
#         max_length=100,
#         required=False,
#         widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'})
#     )
#     visitor_email = forms.EmailField(
#         required=False,
#         widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
#     )
#     visitor_phone = forms.CharField(
#         max_length=15,
#         required=False,
#         widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'})
#     )
#     visitor_date_of_birth = forms.DateField(
#         required=False,
#         widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
#     )
#     visitor_gender = forms.ChoiceField(
#         choices=[('', 'Select Gender'), ('M', 'Male'), ('F', 'Female')],
#         required=False,
#         widget=forms.Select(attrs={'class': 'form-control'})
#     )
    
#     # Slot selection
#     slot = forms.ModelChoiceField(
#         queryset=AppointmentSlot.objects.none(),
#         widget=forms.RadioSelect,
#         error_messages={'required': 'Please select an available time slot'}
#     )
    
#     class Meta:
#         model = Appointment
#         fields = [
#             'appointment_type',
#             'reason_for_visit',
#             'special_requirements',
#         ]
#         widgets = {
#             'appointment_type': forms.Select(attrs={'class': 'form-control'}),
#             'reason_for_visit': forms.Textarea(attrs={
#                 'class': 'form-control',
#                 'rows': 3,
#                 'placeholder': 'Brief description of your visit (optional)'
#             }),
#             'special_requirements': forms.Textarea(attrs={
#                 'class': 'form-control',
#                 'rows': 2,
#                 'placeholder': 'Any special needs? (wheelchair access, etc.)'
#             }),
#         }
    
#     def __init__(self, *args, vendor=None, user=None, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.vendor = vendor
#         self.user = user
#         # self.fields['slot'].empty_label = None

#         if vendor:
#             # Load available slots (next 30 days)
#             today = timezone.now().date()
#             future_date = today + timezone.timedelta(days=30)
            
#             self.fields['slot'].queryset = AppointmentSlot.objects.filter(
#                 vendor=vendor,
#                 date__gte=today,
#                 date__lte=future_date,
#                 is_active=True
#             ).exclude(
#                 current_bookings__gte=models.F('max_appointments')
#             ).select_related('vendor')
            
#             # If user is authenticated patient, load their existing patient record
#             if user and user.is_authenticated and hasattr(user, 'patient_profile'):
#                 try:
#                     patient = user.patient_profile.patient
#                     self.fields['existing_patient'].queryset = Patient.objects.filter(
#                         id=patient.id, vendor=vendor
#                     )
#                     self.fields['existing_patient'].initial = patient
#                 except Exception:
#                     pass
    
#     def clean(self):
#         if self.slot.vendor_id != self.vendor_id:
#             raise ValidationError("Slot does not belong to this laboratory.")

#         cleaned_data = super().clean()
#         existing_patient = cleaned_data.get('existing_patient')
        
#         # Check if we have patient data (either linked or visitor)
#         if not existing_patient:
#             # Validate visitor data
#             required_visitor_fields = [
#                 'visitor_first_name',
#                 'visitor_last_name',
#                 'visitor_email',
#                 'visitor_phone',
#             ]
            
#             missing_fields = [
#                 field for field in required_visitor_fields
#                 if not cleaned_data.get(field)
#             ]
            
#             if missing_fields:
#                 raise ValidationError(
#                     "Please provide your contact information: " +
#                     ", ".join([f.replace('visitor_', '').replace('_', ' ').title() for f in missing_fields])
#                 )
            
#             # Validate at least one contact method
#             if not cleaned_data.get('visitor_email') and not cleaned_data.get('visitor_phone'):
#                 raise ValidationError("Please provide either email or phone number.")
        
#         # Validate slot availability
#         slot = cleaned_data.get('slot')
#         if slot:
#             if not slot.is_available:
#                 raise ValidationError("Sorry, this time slot is no longer available.")
            
#             if slot.is_past:
#                 raise ValidationError("Cannot book appointments in the past.")
#             import pytz
#         return cleaned_data
    
#     def save(self, commit=True):
#         from django.db import transaction
#         from django.core.exceptions import ValidationError
#         from django.db.models import F
#         from apps.labs.models import Patient  # Ensure correct import path

#         appointment = super().save(commit=False)
#         appointment.vendor = self.vendor
#         appointment.slot = self.cleaned_data.get('slot')

#         if self.user and self.user.is_authenticated:
#             appointment.booked_by_user = self.user

#         if commit:
#             with transaction.atomic():
#                 # 1. HANDLE PATIENT LOGIC (Shadow Patient Strategy)
#                 existing_patient = self.cleaned_data.get('existing_patient')
                
#                 if existing_patient:
#                     appointment.patient = existing_patient
#                 else:
#                     # Use visitor data to find or create a 'Shadow' Patient
#                     email = self.cleaned_data.get('visitor_email')
#                     # We use get_or_create to ensure we don't duplicate records 
#                     # for the same visitor email at the same lab.
#                     patient, created = Patient.objects.get_or_create(
#                         vendor=self.vendor,
#                         contact_email=email,
#                         defaults={
#                             'first_name': self.cleaned_data.get('visitor_first_name'),
#                             'last_name': self.cleaned_data.get('visitor_last_name'),
#                             'contact_phone': self.cleaned_data.get('visitor_phone'),
#                             'date_of_birth': self.cleaned_data.get('visitor_date_of_birth'),
#                             'gender': self.cleaned_data.get('visitor_gender'),
#                             'is_shadow': True,
#                         }
#                     )
#                     appointment.patient = patient

#                 # 2. SLOT LOCKING & CAPACITY CHECK
#                 # select_for_update() locks the row until the transaction ends
#                 slot = AppointmentSlot.objects.select_for_update().get(
#                     pk=appointment.slot.pk
#                 )
                
#                 if slot.current_bookings >= slot.max_appointments:
#                     raise ValidationError("This slot just filled up. Please select another time.")
                
#                 # 3. ATOMIC UPDATES
#                 appointment.save()
                
#                 # Increment using F expression to prevent race condition updates
#                 AppointmentSlot.objects.filter(pk=slot.pk).update(
#                     current_bookings=F('current_bookings') + 1
#                 )
                
#         return appointment
    


