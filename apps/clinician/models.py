from django.db import models
from django.conf import settings
from django.utils import timezone


class ClinicianProfile(models.Model):
    """
    Extended profile for clinicians with professional credentials and specializations.
    """
    
    SPECIALIZATION_CHOICES = [
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
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='clinician_profile')
    
    # Professional Information
    license_number = models.CharField(max_length=100, blank=True, help_text="Medical license number")
    
    specialization = models.CharField(max_length=50, choices=SPECIALIZATION_CHOICES, default='general_practice')
    
    organization = models.CharField(max_length=255, blank=True, help_text="Hospital/Clinic name")
    
    department = models.CharField(max_length=100, blank=True, help_text="Department within organization")
    
    # Credentials
    qualifications = models.CharField(max_length=250, blank=True, help_text="Degrees and certifications (e.g., MD, MBBS, DO)")
    
    # Preferences
    default_test_priority = models.CharField(max_length=20, choices=[('routine', 'Routine'), ('urgent', 'Urgent')], default='routine')
    
    enable_critical_alerts = models.BooleanField(default=True, help_text="Receive notifications for critical/panic values")
    
    preferred_contact_method = models.CharField(max_length=20, choices=[
            ('email', 'Email'),
            ('sms', 'SMS'),
            ('both', 'Both'),
        ],
        default='email'
    )
    
    # Statistics (for dashboard)
    total_orders_placed = models.IntegerField(default=0)
    last_order_date = models.DateTimeField(null=True, blank=True)
    
    # Status
    is_verified = models.BooleanField(default=False, help_text="Has admin verified clinician credentials?")
    
    verification_notes = models.TextField(
        blank=True,
        help_text="Admin notes on verification"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Can this clinician place orders?"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Clinician Profile"
        verbose_name_plural = "Clinician Profiles"
        
    def __str__(self):
        return f"Dr. {self.user.get_full_name()} - {self.get_specialization_display()}"
    
    @property
    def full_title(self):
        """Return clinician's full professional title."""
        name = self.user.get_full_name()
        quals = f", {self.qualifications}" if self.qualifications else ""
        return f"Dr. {name}{quals}"
    
    def increment_order_count(self):
        """Update order statistics."""
        self.total_orders_placed += 1
        self.last_order_date = timezone.now()
        self.save(update_fields=['total_orders_placed', 'last_order_date'])


class ClinicianPatientRelationship(models.Model):
    """
    Tracks which clinicians have authorization to view which patients.
    Created automatically when a clinician orders a test for a patient.
    """
    
    RELATIONSHIP_TYPE = [
        ('primary', 'Primary Care Physician'),
        ('specialist', 'Specialist'),
        ('consulting', 'Consulting Physician'),
        ('covering', 'Covering Physician'),
    ]
    
    clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='patient_relationships',
        limit_choices_to={'role': 'clinician'}
    )
    
    patient = models.ForeignKey(
        'labs.Patient',
        on_delete=models.CASCADE,
        related_name='clinician_relationships'
    )
    
    relationship_type = models.CharField(
        max_length=20,
        choices=RELATIONSHIP_TYPE,
        default='primary'
    )
    
    # Access control
    can_order_tests = models.BooleanField(default=True)
    can_view_results = models.BooleanField(default=True)
    can_view_history = models.BooleanField(default=True)
    
    # Audit
    established_date = models.DateTimeField(auto_now_add=True)
    established_via = models.CharField(
        max_length=100,
        blank=True,
        help_text="How was relationship established? (e.g., 'First test order')"
    )
    
    last_interaction = models.DateTimeField(auto_now=True)
    
    is_active = models.BooleanField(default=True, help_text="Is this relationship currently active?")
    
    class Meta:
        verbose_name = "Clinician-Patient Relationship"
        verbose_name_plural = "Clinician-Patient Relationships"
        unique_together = ('clinician', 'patient')
        indexes = [
            models.Index(fields=['clinician', 'is_active']),
            models.Index(fields=['patient', 'is_active']),
        ]
    
    def __str__(self):
        # return f"{self.clinician.get_full_name()} → {self.patient.patient_id}"
        return f"{self.clinician.first_name} → {self.patient.patient_id}"
    

