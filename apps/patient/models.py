# patients/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
import logging
import uuid 


logger = logging.getLogger(__name__)


class PatientUser(models.Model):
    """
    Links an authenticated user account to lab patient records.
    Created automatically during patient registration.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='patient_profile', help_text="Link to authenticated user account")
    
    patient = models.OneToOneField('labs.Patient', on_delete=models.CASCADE, related_name='user_account', help_text="Link to lab operations patient record")
    
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

