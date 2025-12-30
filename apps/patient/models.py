# patients/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

class PatientUser(models.Model):
    """
    Links an authenticated user account to lab patient records.
    Created automatically during patient registration.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='patient_links'
    )
    patient = models.ForeignKey(
        'labs.Patient',
        on_delete=models.CASCADE,
        related_name='user_links'
    )

    # user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='patient_profile', help_text="Link to authenticated user account")
    
    # patient = models.OneToOneField('labs.Patient', on_delete=models.CASCADE, related_name='user_account', help_text="Link to lab operations patient record")
    
    # Portal preferences
    preferred_notification = models.CharField(max_length=20,
        choices=[
            ('email', 'Email Only'),
            ('sms', 'SMS Only'),
            ('both', 'Email & SMS'),
        ],
        default='email'
    )
    
    consent_to_digital_results = models.BooleanField(default=False, help_text="Patient consents to viewing results online")
    
    # Verification status
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    
    profile_completed = models.BooleanField(default=False, help_text="Has patient filled all required profile fields?")
    
    # Additional preferences
    language_preference = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Metadata
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    last_portal_login = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        unique_together = ('user', 'patient')
        verbose_name = "Patient User Profile"
        verbose_name_plural = "Patient User Profiles"
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['patient']),
        ]
        
    def __str__(self):
        return f"{self.user.email} → Patient {self.patient.patient_id}"
    
    @property
    def full_name(self):
        """Get patient full name."""
        return f"{self.patient.first_name} {self.patient.last_name}"
    
    @property
    def is_profile_complete(self):
        """Check if all critical profile fields are filled."""
        patient = self.patient
        required_fields = [
            patient.first_name,
            patient.last_name,
            patient.date_of_birth,
            patient.gender,
            patient.contact_phone or patient.contact_email,
        ]
        return all(required_fields) and self.consent_to_digital_results
    
    def save(self, *args, **kwargs):
        """Auto-update profile_completed status."""
        self.profile_completed = self.is_profile_complete
        super().save(*args, **kwargs)
    
    def update_last_login(self):
        """Track portal login time."""
        self.last_portal_login = timezone.now()
        self.save(update_fields=['last_portal_login'])


# patients/models.py
# Visitor/Walk-in Patient (Unauthenticated)

class AppointmentSlot(models.Model):
    """
    Defines available time slots for appointments at a laboratory.
    Staff configures these in advance.
    """
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='appointment_slots')
    
    # Time configuration
    date = models.DateField(help_text="Appointment date")
    start_time = models.TimeField(help_text="Slot start time")
    end_time = models.TimeField(help_text="Slot end time")
    
    # Capacity management
    max_appointments = models.PositiveIntegerField(default=1, help_text="How many patients can book this slot")
    current_bookings = models.PositiveIntegerField(default=0, help_text="Current number of bookings")
    
    # Availability
    is_active = models.BooleanField(default=True, help_text="Is this slot available for booking?")
    slot_type = models.CharField(
        max_length=20,
        choices=[
            ('sample_collection', 'Sample Collection'),
            ('consultation', 'Consultation'),
            ('result_discussion', 'Result Discussion'),
            ('general', 'General Visit'),
        ],
        default='sample_collection'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('vendor', 'date', 'start_time')
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['vendor', 'date', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.date} {self.start_time}-{self.end_time} ({self.current_bookings}/{self.max_appointments})"
    
    # CheckConstraint(
    # check=Q(current_bookings__lte=F('max_appointments')),
    # name='slot_capacity_not_exceeded'
    # )

    @property
    def is_available(self):
        """Check if slot has capacity."""
        return self.is_active and self.current_bookings < self.max_appointments
    
    @property
    def is_past(self):
        """Check if slot is in the past."""
        from django.utils import timezone
        slot_datetime = timezone.make_aware(
            timezone.datetime.combine(self.date, self.start_time)
        )
        return slot_datetime < timezone.now()


class Appointment(models.Model):
    """
    Patient appointment booking - can be made by authenticated or unauthenticated users.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Confirmation'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
    ]
    
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='appointments')
    appointment_id = models.CharField(max_length=20, unique=True, help_text="Auto-generated appointment ID")
    
    # Patient information (linked if registered, else standalone)
    patient = models.ForeignKey(
        'labs.Patient', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='appointments',
        help_text="Linked patient record (created if doesn't exist)"
    )
    
    # Walk-in patient data (if not registered)
    visitor_first_name = models.CharField(max_length=100, blank=True)
    visitor_last_name = models.CharField(max_length=100, blank=True)
    visitor_email = models.EmailField(blank=True)
    visitor_phone = models.CharField(max_length=15, blank=True)
    visitor_date_of_birth = models.DateField(null=True, blank=True)
    visitor_gender = models.CharField(max_length=1, choices=[('M', 'Male'), ('F', 'Female')], blank=True)
    
    # Appointment details
    slot = models.ForeignKey(AppointmentSlot, on_delete=models.PROTECT, related_name='appointments')
    appointment_type = models.CharField(
        max_length=20,
        choices=[
            ('sample_collection', 'Sample Collection'),
            ('consultation', 'Consultation'),
            ('result_discussion', 'Result Discussion'),
            ('test_request', 'New Test Request'),
        ],
        default='sample_collection'
    )
    
    # Optional: Link to test request if booking is for sample collection
    test_request = models.OneToOneField(
        'labs.TestRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointment',
        help_text="Link to test request if appointment is for sample collection"
    )
    
    # Additional info
    reason_for_visit = models.TextField(blank=True, help_text="Patient's notes about the visit")
    special_requirements = models.TextField(blank=True, help_text="Any special needs (wheelchair access, etc.)")
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_appointments'
    )
    
    cancellation_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_appointments'
    )
    
    # Notifications
    confirmation_sent = models.BooleanField(default=False)
    reminder_sent = models.BooleanField(default=False)
    
    # Metadata
    booked_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='booked_appointments',
        help_text="User who made the booking (if authenticated)"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['patient', 'status']),
            models.Index(fields=['appointment_id']),
        ]
    
    def __str__(self):
        name = self.get_patient_name()
        return f"{self.appointment_id} - {name} on {self.slot.date}"
    
    def save(self, *args, **kwargs):
        # Generate appointment ID
        if not self.appointment_id:
            from labs.utils import get_next_sequence
            self.appointment_id = get_next_sequence("APT", vendor=self.vendor)
        
        super().save(*args, **kwargs)
    
    def get_patient_name(self):
        """Get patient name from either linked patient or visitor data."""
        if self.patient:
            return f"{self.patient.first_name} {self.patient.last_name}"
        return f"{self.visitor_first_name} {self.visitor_last_name}"
    
    def get_contact_email(self):
        """Get contact email."""
        if self.patient and self.patient.contact_email:
            return self.patient.contact_email
        return self.visitor_email
    
    def get_contact_phone(self):
        """Get contact phone."""
        if self.patient and self.patient.contact_phone:
            return self.patient.contact_phone
        return self.visitor_phone
    
    def confirm(self, confirmed_by_user=None):
        """Confirm the appointment."""
        self.status = 'confirmed'
        self.confirmed_at = timezone.now()
        self.confirmed_by = confirmed_by_user
        self.save(update_fields=['status', 'confirmed_at', 'confirmed_by', 'updated_at'])
    
    def cancel(self, reason='', cancelled_by_user=None):
        """Cancel the appointment and free up the slot."""
        self.status = 'cancelled'
        self.cancellation_reason = reason
        self.cancelled_at = timezone.now()
        self.cancelled_by = cancelled_by_user
        self.save(update_fields=['status', 'cancellation_reason', 'cancelled_at', 'cancelled_by', 'updated_at'])
        
        # Decrement slot booking count
        if self.slot:
            self.slot.current_bookings = max(0, self.slot.current_bookings - 1)
            self.slot.save(update_fields=['current_bookings'])
    
    @property
    def can_be_cancelled(self):
        """Check if appointment can still be cancelled."""
        if self.status in ['cancelled', 'completed', 'no_show']:
            return False
        return not self.slot.is_past
    


# patients/models.py - ADD THIS MODEL

class AppointmentSlotTemplate(models.Model):
    """
    Templates for recurring appointment slots.
    Staff creates these once, then generates actual slots in bulk.
    """
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='slot_templates')
    
    name = models.CharField(max_length=100, help_text="Template name (e.g., 'Morning Sample Collection')")
    
    # Time configuration
    start_time = models.TimeField(help_text="Slot start time")
    end_time = models.TimeField(help_text="Slot end time")
    duration_minutes = models.PositiveIntegerField(default=30, help_text="Slot duration in minutes")
    
    # Recurrence pattern
    RECURRENCE_CHOICES = [
        ('weekdays', 'Weekdays (Mon-Fri)'),
        ('weekends', 'Weekends (Sat-Sun)'),
        ('daily', 'Daily'),
        ('specific_days', 'Specific Days of Week'),
    ]
    recurrence_pattern = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default='weekdays')
    
    # Specific days (if recurrence_pattern = 'specific_days')
    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    
    # Capacity
    max_appointments = models.PositiveIntegerField(default=1, help_text="Max bookings per slot")
    slot_type = models.CharField(
        max_length=20,
        choices=[
            ('sample_collection', 'Sample Collection'),
            ('consultation', 'Consultation'),
            ('result_discussion', 'Result Discussion'),
            ('general', 'General Visit'),
        ],
        default='sample_collection'
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_slot_templates'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['start_time']
        
    def __str__(self):
        return f"{self.name} ({self.start_time}-{self.end_time})"
    
    def get_active_days(self):
        """Return list of active weekday numbers (0=Monday, 6=Sunday)."""
        if self.recurrence_pattern == 'weekdays':
            return [0, 1, 2, 3, 4]  # Mon-Fri
        elif self.recurrence_pattern == 'weekends':
            return [5, 6]  # Sat-Sun
        elif self.recurrence_pattern == 'daily':
            return list(range(7))
        elif self.recurrence_pattern == 'specific_days':
            days = []
            day_map = [
                (self.monday, 0),
                (self.tuesday, 1),
                (self.wednesday, 2),
                (self.thursday, 3),
                (self.friday, 4),
                (self.saturday, 5),
                (self.sunday, 6),
            ]
            return [day_num for is_active, day_num in day_map if is_active]
        return []
    
    def generate_slots(self, start_date, end_date):
        """
        Generate actual AppointmentSlot instances from this template
        for the given date range.
        """
        from datetime import timedelta
        
        slots_created = 0
        current_date = start_date
        active_days = self.get_active_days()
        
        while current_date <= end_date:
            # Check if this day matches the recurrence pattern
            if current_date.weekday() in active_days:
                # Check if slot doesn't already exist
                existing = AppointmentSlot.objects.filter(
                    vendor=self.vendor,
                    date=current_date,
                    start_time=self.start_time,
                    end_time=self.end_time
                ).exists()
                
                if not existing:
                    AppointmentSlot.objects.create(
                        vendor=self.vendor,
                        date=current_date,
                        start_time=self.start_time,
                        end_time=self.end_time,
                        max_appointments=self.max_appointments,
                        slot_type=self.slot_type,
                        is_active=True
                    )
                    slots_created += 1
            
            current_date += timedelta(days=1)
        
        return slots_created


