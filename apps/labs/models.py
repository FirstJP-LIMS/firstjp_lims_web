from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from apps.tenants.models import Vendor
import uuid
from django.db.models import Max
from django.utils.text import slugify
from .utils import get_next_sequence
from decimal import Decimal

# pdf 
# Generate barcode libraries           
import os
from io import BytesIO
from barcode import Code128
from barcode.writer import ImageWriter
from django.core.files.base import ContentFile


from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation


# ---------------------
# To customize id
# ---------------------
class SequenceCounter(models.Model):
    """
    Maintains atomic counters per vendor for generating IDs.
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True)  # ✅ Direct reference
    prefix = models.CharField(max_length=20)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("vendor", "prefix")

    def __str__(self):
        return f"{self.vendor or 'GLOBAL'} - {self.prefix} ({self.last_number})"


# ---------------------
# Per-vendor configuration
# ---------------------
class Department(models.Model):
    """
    Vendor-specific lab departments (e.g., Hematology, Serology).
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='departments')  # ✅ Direct reference
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Vendor Department"
        ordering = ["name"]
        unique_together = ('vendor', 'name') 

    def __str__(self):
        # return f"{self.vendor.name} - {self.name}"
        return f"{self.name}"


class VendorTest(models.Model):
    """
    Fully-featured test definition scoped to a Vendor (lab).
    Designed for modern LIMS: AMR/CRR, panic values, methods, specimen types, autoverification.
    """
    RESULT_TYPE_CHOICES = [
        ("QNT", "Quantitative"),
        ("QLT", "Qualitative"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="lab_tests")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, blank=True, null=True)

    # Lab mapping
    assigned_department = models.ForeignKey(
        "Department", on_delete=models.PROTECT, related_name="tests"
    )

    # Cost & availability
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    enabled = models.BooleanField(default=True)
    
    # 🆕 PATIENT SELF-ORDERING CONTROL
    available_for_online_booking = models.BooleanField(
        default=False,
        help_text="Can patients request this test online without clinician referral?"
    )
    
    requires_physician_approval = models.BooleanField(
        default=False,
        help_text="Patient orders require physician review before processing (used for complex/high-risk tests)"
    )

    # Specimen & method metadata
    specimen_type = models.CharField(max_length=100, blank=True, help_text="e.g. Serum, Plasma, Urine")
    method = models.CharField(max_length=120, blank=True, help_text="Analytical method / platform")
    platform = models.CharField(max_length=120, blank=True, help_text="Instrument/platform name (optional)")

    # Units & reporting
    default_units = models.CharField(max_length=50, blank=True, null=True)
    result_type = models.CharField(max_length=3, choices=RESULT_TYPE_CHOICES, default="QNT")

    # Analytical measuring/reportable ranges
    amr_low = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, help_text="Analytical Measuring Range (lower)")
    amr_high = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, help_text="Analytical Measuring Range (upper)")

    reportable_low = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, help_text="Reportable (clinical) low")
    reportable_high = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, help_text="Reportable (clinical) high")

    # Reference / clinical ranges (these can be vendor-default; patient-specific ranges may be applied at runtime)
    min_reference_value = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    max_reference_value = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)

    # Panic / critical values
    panic_low_value = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, help_text="Critical low (panic) threshold")
    panic_high_value = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, help_text="Critical high (panic) threshold")
    
    # 🆕 PATIENT PREPARATION & INFORMATION
    preparation_required = models.BooleanField(
        default=False, help_text="Does this test require special preparation? (fasting, medication hold, etc.)"
    )
    
    preparation_instructions = models.TextField(
        blank=True, help_text="Patient-facing instructions (e.g., 'Fast for 8-12 hours', 'Avoid alcohol 48hrs before')"
    )
    
    collection_instructions = models.TextField(
        blank=True,
        help_text="How the sample should be collected (e.g., 'First morning urine', 'Avoid recent exercise')"
    )
    
    patient_friendly_description = models.TextField(
        blank=True,
        help_text="Layman's explanation of what this test measures and why it's ordered"
    )
    
    typical_reasons = models.TextField(
        blank=True,
        help_text="Common clinical indications for this test (for patient education)"
    )

    # Misc
    turnaround_override = models.DurationField(null=True, blank=True)
    general_comment_template = models.TextField(blank=True)
    enabled_for_autoverify = models.BooleanField(default=False,
        help_text="Allow autoverification under configured rules (QC pass, instrument source, delta check, etc.)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lab Test"
        verbose_name_plural = "Lab Tests"
        unique_together = ("vendor", "code")
        indexes = [
            models.Index(fields=["vendor", "code"]),
            models.Index(fields=["result_type"]),
            models.Index(fields=["amr_low", "amr_high"]),
            models.Index(fields=["available_for_online_booking"]),  # 🆕 For patient queries
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True)
            self.slug = f"{self.vendor_id}-{self.code}-{base}"[:180]
        super().save(*args, **kwargs)

    # ---------------------
    # Helper methods
    # ---------------------
    def has_panic_low(self):
        return self.panic_low_value is not None

    def has_panic_high(self):
        return self.panic_high_value is not None

    def in_panic_low(self, value):
        if self.panic_low_value is None:
            return False
        return value <= self.panic_low_value

    def in_panic_high(self, value):
        if self.panic_high_value is None:
            return False
        return value >= self.panic_high_value

    def in_reference_range(self, value):
        """Return -1 if below, 0 if within, +1 if above, None if no refs"""
        if self.min_reference_value is None or self.max_reference_value is None:
            return None
        if value < self.min_reference_value:
            return -1
        if value > self.max_reference_value:
            return 1
        return 0

    def is_within_amr(self, value):
        """Check analytical measuring range if present"""
        if self.amr_low is None or self.amr_high is None:
            return True
        return self.amr_low <= value <= self.amr_high

    def qualitative_normal_values(self):
        """Return list of normalized normal qualitative strings"""
        return list(self.qlt_options.filter(is_normal=True).values_list("normalized", flat=True))

    def get_price_from_price_list(self, price_list):
        """
        Get test price from a specific price list.
        Returns default price if not found in price list.
        """
        from apps.billing.models import TestPrice
        
        if not price_list:
            return self.price
        
        try:
            test_price = TestPrice.objects.get(
                price_list=price_list,
                test=self
            )
            return test_price.price
        except TestPrice.DoesNotExist:
            return self.price
    
    # 🆕 ORDERING HELPERS
    def can_be_ordered_by_patient(self):
        """
        Check if this test is available for patient self-ordering.
        Simple check - no demographic restrictions.
        """
        return self.enabled and self.available_for_online_booking
    
    def get_estimated_turnaround(self):
        """
        Get estimated turnaround time for this test.
        Returns hours as integer.
        """
        if self.turnaround_override:
            return int(self.turnaround_override.total_seconds() / 3600)
        
        # Default based on department or test complexity
        if self.assigned_department:
            return getattr(self.assigned_department, 'default_turnaround_hours', 24)
        
        return 24  # Default 24 hours
    
    def get_display_price(self, price_list=None):
        """
        Get formatted price for display.
        """
        price = self.get_price_from_price_list(price_list)
        return f"₦{price:,.2f}"  # Adjust currency symbol as needed
        
    def __str__(self):
        return f"[{self.vendor.name}] {self.code} — {self.name}"


class QualitativeOption(models.Model):
    """
    Possible qualitative outcomes for a VendorTest (e.g. Negative, Positive, Indeterminate).
    One or more options can be flagged as "normal" so auto-flagging can compare against them.
    """
    test = models.ForeignKey(VendorTest, related_name="qlt_options", on_delete=models.CASCADE)
    value = models.CharField(max_length=120)
    normalized = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        help_text="Normalized lowercase value for fast comparisons (auto-filled on save)."
    )
    is_normal = models.BooleanField(default=False, help_text="Marks this option as clinically normal")
    order = models.PositiveSmallIntegerField(default=0, help_text="Sort order for display")

    class Meta:
        unique_together = ("test", "value")
        ordering = ("test", "order", "value")

    def save(self, *args, **kwargs):
        if not self.normalized:
            self.normalized = self.value.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.test.code} — {self.value}{' (normal)' if self.is_normal else ''}"


# ---------------------
# Tenant-scoped operational data
# ---------------------
class Patient(models.Model):
    GENDER_CHOICE = [
        ('M', 'Male'),
        ('F', 'Female')
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='patients')  # ✅ Direct reference
    patient_id = models.CharField(max_length=20, help_text="Auto-generated 6-digit patient ID.")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    # for Walk-in Patient.
    is_shadow = models.BooleanField(default=False,  help_text="True if created via a walk-in appointment without a full account.")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICE)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        unique_together = ("vendor", "patient_id")
        ordering = ("-id",)

    def save(self, *args, **kwargs):
        if not self.patient_id:
            self.patient_id = get_next_sequence("PAT", vendor=self.vendor)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient_id} — {self.first_name} {self.last_name}"


class Sample(models.Model):
    """
    Represents a specimen collected from a patient for one or more lab tests.
    """

    SAMPLE_STATUS = [
        ('AC', 'Accessioned'),   # Logged into LIMS
        ('RJ', 'Rejected'),      # Rejected during verification
        ('AP', 'Accepted'),      # Approved for analysis
        ('ST', 'Stored'),        # In cold storage after analysis
        ('CO', 'Consumed'),      # Fully used up in processing
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="samples")  # ✅ Direct reference
    test_request = models.ForeignKey('TestRequest', on_delete=models.CASCADE, related_name='samples')
    patient = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name="samples")

    sample_id = models.CharField(max_length=64, unique=True, help_text="Globally unique barcode/sample ID (auto-generated).")

    specimen_type = models.CharField(max_length=100, help_text="Specimen type e.g., Blood, Urine, Serum, Swab, etc.")
    specimen_description = models.TextField(blank=True, null=True)

    # --- Collection Information ---
    collected_by = models.CharField(max_length=150, blank=True, help_text="Phlebotomist or technician name/ID.")
    collection_method = models.CharField(max_length=100, blank=True, help_text="e.g., Venipuncture, Capillary, Finger prick.")
    collection_site = models.CharField(max_length=100, blank=True, help_text="e.g., Left arm, finger prick.")
    container_type = models.CharField(max_length=100, blank=True, help_text="e.g., EDTA tube, Serum separator, Plain bottle.")
    volume_collected_ml = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Volume in mL.")

    collected_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(choices=SAMPLE_STATUS, max_length=2, default='AC')
    location = models.CharField(max_length=200, blank=True, help_text="Storage location or rack ID.")

    # --- Verification / Examination Metadata ---
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_samples", help_text="Staff who verified this sample before analysis.")

    verified_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when verification occurred.")
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason for rejection if applicable.")

    FASTING_CHOICES = [
        ('fasting', 'Fasting (8-12 hours)'),
        ('non_fasting', 'Non-Fasting'),
        ('not_required', 'Not Required'),
        ('unknown', 'Unknown'),
    ]
    
    fasting_status = models.CharField(
        max_length=20, 
        choices=FASTING_CHOICES, 
        default='unknown',
        help_text="Patient's fasting state at time of collection."
    )
    
    class Meta:
        ordering = ['-collected_at']
        verbose_name = "Sample / Specimen"
        verbose_name_plural = "Samples / Specimens"

    def save(self, *args, **kwargs):
        """Auto-generate unique sample ID if not set."""
        if not self.sample_id:
            self.sample_id = get_next_sequence("SMP", vendor=self.vendor)
        super().save(*args, **kwargs)

    def verify_sample(self, user):
        """Mark this sample as verified by a lab staff."""
        self.verified_by = user
        self.verified_at = timezone.now()
        self.save(update_fields=['verified_by', 'verified_at'])

        AuditLog.objects.create(
            vendor=self.vendor,
            user=user,
            action=f"Sample {self.sample_id} verified for TestRequest {self.test_request.request_id}.",
        )

    def accept_sample(self, user):
        """Accept the sample and queue associated tests for analysis."""
        self.status = 'AP'
        self.verified_by = user
        self.verified_at = timezone.now()
        self.save(update_fields=['status', 'verified_by', 'verified_at'])

        # Move parent request to analysis phase
        test_request = self.test_request
        test_request.move_to_analysis()

        # Queue test assignments linked to this sample
        for assignment in test_request.assignments.filter(sample=self, status='P'):
            assignment.mark_queued()

        AuditLog.objects.create(
            vendor=self.vendor,
            user=user,
            action=f"Sample {self.sample_id} accepted and queued for analysis.",
        )

    def reject_sample(self, user, reason=None):
        """Reject this sample and optionally record reason."""
        self.status = 'RJ'
        self.rejection_reason = reason
        self.verified_by = user
        self.verified_at = timezone.now()
        self.save(update_fields=['status', 'verified_by', 'verified_at', 'rejection_reason'])

        # If all samples rejected, mark request as rejected
        test_request = self.test_request
        if all(s.status == 'RJ' for s in test_request.samples.all()):
            test_request.status = 'RJ'
            test_request.save(update_fields=['status'])

        AuditLog.objects.create(
            vendor=self.vendor,
            user=user,
            action=f"Sample {self.sample_id} rejected.",
        )

    def mark_stored(self, user):
        """Store sample after analysis completion."""
        self.status = 'ST'
        self.save(update_fields=['status'])

        AuditLog.objects.create(
            vendor=self.vendor,
            user=user,
            action=f"Sample {self.sample_id} stored post-analysis."
        )

    def mark_consumed(self, user):
        """Mark this sample as fully used in processing."""
        self.status = 'CO'
        self.save(update_fields=['status'])

        AuditLog.objects.create(
            vendor=self.vendor,
            user=user,
            action=f"Sample {self.sample_id} marked as consumed."
        )

    def __str__(self):
        return f"{self.sample_id} — {self.specimen_type}"


# ------------------------
# TEST REQUEST MODEL
# ------------------------
    
PRIORITY_STATUS = [
        ("urgent","URGENT"),
        ("routine","ROUTINE"),
    ]

class TestRequest(models.Model):
    """Represents a full lab order for a patient, possibly containing multiple tests."""

    ORDER_STATUS = [
        ('P', 'Pending'),           # Created, awaiting approval/sample
        ('W', 'Awaiting Approval'), # 🆕 Patient order needs physician review
        ('A', 'Approved'),          # 🆕 Physician approved patient order
        ('R', 'Received'),          # Sample received/accessioned
        ('N', 'Analysis'),          # Tests being analyzed (changed from 'A' to avoid conflict)
        ('C', 'Complete'),          # Results generated, awaiting verification
        ('V', 'Verified'),          # Final report verified and ready for release
        ('X', 'Rejected'),          # 🆕 Order rejected (insufficient info, contraindicated, etc.)
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="requests")
    patient = models.ForeignKey('Patient', on_delete=models.PROTECT, related_name="requests")
    
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="ordered_requests", help_text="User who created this order (clinician or patient)")
    
    ordering_clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clinical_orders",
        limit_choices_to={'role': 'clinician'},
        help_text="Clinician responsible for this order"
    )
    
    # 🆕 Approval workflow for patient orders
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_orders",
        help_text="Staff/clinician who approved patient self-order"
    )
    
    approved_at = models.DateTimeField(null=True, blank=True)
    
    rejection_reason = models.TextField(
        blank=True,
        help_text="Why was this order rejected?"
    )

    request_id = models.CharField(max_length=64, unique=True)
    requested_tests = models.ManyToManyField('VendorTest', related_name="test_requests")
    clinical_history = models.TextField(blank=True)
    clinical_indication = models.TextField(blank=True)
    urgency_reason = models.TextField(blank=True)
    
    priority = models.CharField(choices=PRIORITY_STATUS, max_length=45, default="routine",)
    
    status = models.CharField(choices=ORDER_STATUS, max_length=1, default="P")

    has_informed_consent = models.BooleanField(default=False)
    collection_notes = models.TextField(blank=True)
    external_referral = models.CharField(max_length=255, blank=True, null=True)

    barcode_image = models.ImageField(upload_to='barcodes/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    clinician_notified_at = models.DateTimeField(null=True, blank=True)
    clinician_acknowledged_at = models.DateTimeField(null=True, blank=True)

    # Request Result 

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Test Request"
        verbose_name_plural = "Test Requests"
        indexes = [
            models.Index(fields=['ordering_clinician', 'status']),
            models.Index(fields=['patient', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.request_id:
            self.request_id = get_next_sequence("REQ", vendor=self.vendor)
        
        # 🆕 Auto-determine initial status for patient orders
        if not self.pk and self.requested_by and self.requested_by.role == 'patient':
            # Check if any tests require approval
            if kwargs.get('_check_approval', True):
                # This will be checked after M2M save
                pass
        
        super().save(*args, **kwargs)
        
        if not self.barcode_image:
            self.generate_barcode()
            super().save(update_fields=["barcode_image"])
    
    def generate_barcode(self):
        """Generate a barcode image for this test request."""
        barcode_data = f"{self.vendor.tenant_id}-{self.patient.patient_id}-{self.request_id}"

        buffer = BytesIO()
        barcode = Code128(barcode_data, writer=ImageWriter())
        barcode.write(buffer)

        filename = f"barcode_{self.request_id}.png"
        self.barcode_image.save(filename, ContentFile(buffer.getvalue()), save=False)
        buffer.close()
        return self.barcode_image

    # 🆕 Status transition methods
    def check_approval_requirement(self):
        """
        Check if this order requires physician approval.
        Called after tests are added via M2M.
        """
        if self.ordering_clinician:
            # Clinician orders don't need approval
            return False
        
        # Check if any test requires approval
        requires_approval = self.requested_tests.filter(
            requires_physician_approval=True
        ).exists()
        
        if requires_approval and self.status == 'P':
            self.status = 'W'  # Move to "Awaiting Approval"
            self.save(update_fields=['status'])
        
        return requires_approval
    
    def approve_order(self, user):
        """Approve a patient order that requires review."""
        if self.status != 'W':
            raise ValueError("Only orders awaiting approval can be approved.")
        
        self.status = 'A'  # Approved
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save(update_fields=['status', 'approved_by', 'approved_at'])
        
        # TODO: Notify patient

    
    def reject_order(self, user, reason):
        """Reject a patient order."""
        if self.status not in ['P', 'W']:
            raise ValueError("Only pending/awaiting orders can be rejected.")
        
        self.status = 'X'  # Rejected
        self.rejection_reason = reason
        self.approved_by = user  # Track who rejected it
        self.approved_at = timezone.now()
        self.save(update_fields=['status', 'rejection_reason', 'approved_by', 'approved_at'])
        
        # TODO: Notify patient

    def move_to_analysis(self):
        """Sample received, start analysis."""
        if self.status in ['P', 'A', 'R']:
            self.status = 'R'  # Received
            self.save(update_fields=['status'])

    def complete_analysis(self):
        """All tests analyzed, pending verification."""
        self.status = 'C'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])
    
    @property
    def has_critical_results(self):
        return self.assignments.filter(
            result__flag='C',
            result__released=True
        ).exists()

    @property
    def all_results_released(self):
        return not self.assignments.filter(
            result__released=False
        ).exists()

    @property
    def requires_clinician_attention(self):
        return self.has_critical_results and not self.clinician_acknowledged_at()
    
    
    @property
    def requires_approval(self):
        """Check if order is awaiting approval."""
        return self.status == 'W'
    
    @property
    def is_patient_order(self):
        """Check if this was a patient self-order."""
        return self.ordering_clinician is None and self.requested_by and self.requested_by.role == 'patient'

    # Check Payment 
    @property
    def is_paid(self):
        """Check if billing is fully paid."""
        if hasattr(self, 'billing_info'):
            return self.billing_info.is_fully_paid()
        return False

    @property
    def can_verify_sample(self):
        """Sample can only be verified if payment is complete."""
        return self.is_paid and self.status in ['P', 'A']

    def __str__(self):
        return f"{self.request_id} ({self.patient})"

        
# Examination phase
class TestAssignment(models.Model):
    """The individual unit of work: one Test assigned to one Request."""
    ASSIGNMENT_STATUS = [
        ('P', 'Pending'),
        ('R', 'Rejected'),
        ('F', 'Freed'),
        ('Q', 'Queued'),
        ('I', 'In Progress'),
        ('A', 'Analysis Complete'),
        ('V', 'Result Verified'),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="assignments")  # ✅ Direct reference
    request = models.ForeignKey('TestRequest', on_delete=models.CASCADE, related_name="assignments")
    lab_test = models.ForeignKey('VendorTest', on_delete=models.PROTECT, related_name="assignments") 
    sample = models.ForeignKey('Sample', on_delete=models.PROTECT, related_name="assignments", help_text="The sample specimen required to run this test.")
    department = models.ForeignKey('Department', on_delete=models.PROTECT, related_name="assigned_work")
    
    status = models.CharField(choices=ASSIGNMENT_STATUS, max_length=1, default='P')
    
    instrument = models.ForeignKey('Equipment', null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments", help_text="The equipment used or scheduled to run this test.")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    queued_at = models.DateTimeField(null=True, blank=True, help_text="When test was sent to instrument")
    analyzed_at = models.DateTimeField(null=True, blank=True, help_text="When result was received")
    verified_at = models.DateTimeField(null=True, blank=True, help_text="When result was verified")
    released_at = models.DateTimeField(null=True, blank=True, help_text="When result was released")
    
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_tests", help_text="Lab technician assigned to this test")
    
    # Instrument integration
    external_id = models.CharField(max_length=100, blank=True, help_text="ID from Windows LIMS/instrument system")
    retry_count = models.IntegerField(default=0, help_text="Number of failed attempts to send to instrument")
    last_sync_attempt = models.DateTimeField(null=True, blank=True, help_text="Last time we tried to sync with instrument")
    
    class Meta:
        unique_together = ('request', 'lab_test')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'instrument']),
            models.Index(fields=['external_id']),
        ]

    def can_send_to_instrument(self):
        """Check if assignment can be sent to instrument"""
        return (
            self.status == 'P' and 
            self.instrument and 
            self.instrument.status == 'active' and
            bool(self.instrument.api_endpoint)
        )

    def mark_queued(self, external_id=None):
        self.status = 'Q'
        self.queued_at = timezone.now()
        if external_id:
            self.external_id = external_id
        self.save(update_fields=['status', 'queued_at', 'external_id'])

    def mark_in_progress(self):
        self.status = 'I'
        self.save(update_fields=['status'])

    def mark_analyzed(self):
        self.status = 'A'
        self.analyzed_at = timezone.now()
        self.save(update_fields=['status', 'analyzed_at'])

    def mark_verified(self):
        self.status = 'V'
        self.verified_at = timezone.now()
        self.save(update_fields=['status', 'verified_at'])
    
    def mark_released(self):
        self.status = 'F'
        self.released_at = timezone.now()
        self.save(update_fields=['status', 'released_at'])

    def mark_rejected(self, reason=""):
        self.status = 'R'
        self.save(update_fields=['status'])

    def __str__(self):
        return f"{self.request.request_id} - {self.lab_test.code}"


class TestResult(models.Model):
    """
    FINAL, GOVERNED Test Result model.

    Implements:
    - Explicit result state machine
    - Role-based lifecycle enforcement
    - Full audit trail
    - Quantitative & Qualitative support
    - QC, Delta checks, AMR, CRR, Panic values
    """

    # ======================================================
    # RELATIONSHIP
    # ======================================================

    assignment = models.OneToOneField(
        'TestAssignment',
        on_delete=models.CASCADE,
        related_name="result"
    )

    # ======================================================
    # RESULT STATE MACHINE
    # ======================================================

    RESULT_STATUS = [
        ('draft', 'Draft'),
        ('verified', 'Verified'),
        ('released', 'Released'),
        ('amended', 'Amended'),
    ]

    status = models.CharField(
        max_length=12,
        choices=RESULT_STATUS,
        default='draft'
    )

    # ======================================================
    # RESULT DATA
    # ======================================================

    result_value = models.TextField()
    units = models.CharField(max_length=50, blank=True)
    reference_range = models.CharField(max_length=80, blank=True)

    FLAG_CHOICES = [
        ('N', 'Normal'),
        ('H', 'High'),
        ('L', 'Low'),
        ('A', 'Abnormal'),
        ('C', 'Critical'),
        ('M', 'Unmeasurable (Outside AMR)'),
        ('R', 'Out of Reportable Range'),
        ('*', 'Corrected'),
    ]

    flag = models.CharField(max_length=1, choices=FLAG_CHOICES, default='N')

    remarks = models.TextField(blank=True)
    interpretation = models.TextField(blank=True)

    DATA_SOURCE = [
        ('manual', 'Manual Entry'),
        ('instrument', 'Instrument Generated'),
        ('imported', 'Imported'),
        ('calculated', 'Calculated'),
    ]

    data_source = models.CharField(max_length=20, choices=DATA_SOURCE, default='manual')
    instrument_name = models.CharField(max_length=150, blank=True)
    instrument_run_id = models.CharField(max_length=100, blank=True)

    # ======================================================
    # AUDIT FIELDS
    # ======================================================

    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='entered_results'
    )
    entered_at = models.DateTimeField(auto_now_add=True)

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='verified_results'
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='released_results'
    )
    released_at = models.DateTimeField(null=True, blank=True)

    # ======================================================
    # AMENDMENT CONTROL
    # ======================================================

    is_amended = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    previous_value = models.TextField(blank=True)
    amendment_reason = models.TextField(blank=True)

    # ======================================================
    # QUALITY CONTROL
    # ======================================================

    qc_passed = models.BooleanField(default=True)
    qc_comment = models.TextField(blank=True)

    delta_flag = models.BooleanField(default=False)
    delta_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # ======================================================
    # META
    # ======================================================

    class Meta:
        ordering = ['-entered_at']
        verbose_name = "Test Result"
        verbose_name_plural = "Test Results"

        permissions = [
            ("can_verify_results", "Can verify test results"),
            ("can_release_results", "Can release test results"),
            ("can_amend_results", "Can amend released results"),
        ]

        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['entered_at']),
            models.Index(fields=['verified_at']),
            models.Index(fields=['released_at']),
            models.Index(fields=['flag']),
            models.Index(fields=['flag', 'data_source']),
        ]

    # ======================================================
    # STATE TRANSITIONS (STRICT)
    # ======================================================

    def verify(self, user):
        """
        Transition: DRAFT → VERIFIED
        """
        if self.status != 'draft':
            raise ValidationError("Only draft results can be verified.")

        if not user.can_verify_results:
            raise ValidationError("User is not authorized to verify results.")

        if not self.qc_passed:
            raise ValidationError("QC must pass before verification.")

        self.status = 'verified'
        self.verified_by = user
        self.verified_at = timezone.now()
        self.save(update_fields=['status', 'verified_by', 'verified_at'])

        self.assignment.mark_verified()

    def release(self, user):
        """
        Transition: VERIFIED → RELEASED
        """
        if self.status != 'verified':
            raise ValidationError("Only verified results can be released.")

        if not user.can_release_results:
            raise ValidationError("User is not authorized to release results.")

        self.status = 'released'
        self.released_by = user
        self.released_at = timezone.now()
        self.save(update_fields=['status', 'released_by', 'released_at'])

        # Update the assignment status if it exists
        if hasattr(self.assignment, 'mark_released'):
            self.assignment.mark_released()

    def amend(self, new_value, user, reason):
        """
        Transition: RELEASED → AMENDED
        """
        if self.status != 'released':
            raise ValidationError("Only released results can be amended.")

        if not user.can_amend_results:
            raise ValidationError("User is not authorized to amend results.")

        self.previous_value = self.result_value
        self.result_value = new_value
        self.amendment_reason = reason
        self.is_amended = True
        self.version += 1
        self.status = 'amended'

        self.auto_flag_result()

        self.save()

    # ======================================================
    # SCIENTIFIC UTILITIES
    # ======================================================

    @property
    def test(self):
        return self.assignment.lab_test

    @property
    def is_quantitative(self):
        return self.test.result_type == 'QNT'

    @property
    def is_qualitative(self):
        return self.test.result_type == 'QLT'

    @property
    def is_critical(self):
        return self.flag == 'C'

    @property
    def formatted_result(self):
        if self.is_quantitative and self.units:
            return f"{self.result_value} {self.units}"
        return self.result_value

    # ======================================================
    # VALIDATION
    # ======================================================

    def clean(self):
        if self.is_quantitative:
            try:
                Decimal(str(self.result_value).strip())
            except (InvalidOperation, ValueError):
                raise ValidationError({"result_value": "Quantitative result must be numeric."})

    # ======================================================
    # AUTO FLAGGING (UNCHANGED LOGIC, GOVERNED SAVE)
    # ======================================================

    def auto_flag_result(self):
        """
        Single authoritative auto-flag engine.
        """
        test = self.test
        flag_to_set = 'N'

        if self.is_qualitative:
            value_norm = self.result_value.strip().lower()
            match = test.qlt_options.filter(normalized=value_norm).first()
            flag_to_set = 'N' if match and match.is_normal else 'A'

        else:
            try:
                value = Decimal(str(self.result_value).strip())
            except (InvalidOperation, ValueError):
                flag_to_set = 'A'
            else:
                if test.amr_low is not None and value < test.amr_low:
                    flag_to_set = 'M'
                elif test.amr_high is not None and value > test.amr_high:
                    flag_to_set = 'M'
                elif test.reportable_low is not None and value < test.reportable_low:
                    flag_to_set = 'R'
                elif test.reportable_high is not None and value > test.reportable_high:
                    flag_to_set = 'R'
                elif test.panic_low_value is not None and value <= test.panic_low_value:
                    flag_to_set = 'C'
                elif test.panic_high_value is not None and value >= test.panic_high_value:
                    flag_to_set = 'C'
                elif test.min_reference_value is not None and value < test.min_reference_value:
                    flag_to_set = 'L'
                elif test.max_reference_value is not None and value > test.max_reference_value:
                    flag_to_set = 'H'

        # if self.flag != flag_to_set:
        #     self.flag = flag_to_set
        #     self.save(update_fields=['flag'])
        self.flag = flag_to_set
        


    def __str__(self):
        return f"{self.assignment.lab_test.name} — {self.formatted_result}"

# For amend results 
class ResultAmendment(models.Model):
    result = models.ForeignKey(
        'TestResult', 
        on_delete=models.CASCADE, 
        related_name='amendment_history'
    )
    old_value = models.TextField()
    new_value = models.TextField()
    reason = models.TextField()
    amended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True
    )
    amended_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Result Amendment"
        ordering = ['-amended_at']

    def __str__(self):
        return f"Amendment for {self.result.id} on {self.amended_at.date()}"
    



class Equipment(models.Model):
    """Lab instruments/analyzers"""
    EQUIPMENT_STATUS = [
        ('active', 'Active'),
        ('maintenance', 'Under Maintenance'),
        ('inactive', 'Inactive'),
    ]
    
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="equipment_set")  # ✅ Direct reference
    name = models.CharField(max_length=150)
    model = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, unique=True)
    department = models.ForeignKey('Department', on_delete=models.PROTECT, related_name="equipment")
    
    api_endpoint = models.URLField(blank=True, help_text="Windows LIMS API endpoint for this instrument")
    api_key = models.CharField(max_length=255, blank=True, help_text="Authentication key")
    supports_auto_fetch = models.BooleanField(default=False, help_text="Can automatically fetch results")
    
    status = models.CharField(max_length=20, choices=EQUIPMENT_STATUS, default='active')
    last_calibrated = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.serial_number})"



class InstrumentLog(models.Model):
    """Log all communication with instruments"""
    LOG_TYPE = [
        ('send', 'Sent to Instrument'),
        ('receive', 'Received from Instrument'),
        ('error', 'Error'),
    ]
    
    assignment = models.ForeignKey(TestAssignment, on_delete=models.CASCADE, related_name="instrument_logs")
    instrument = models.ForeignKey(Equipment, on_delete=models.SET_NULL, null=True)
    
    log_type = models.CharField(max_length=10, choices=LOG_TYPE)
    payload = models.JSONField(help_text="Request/response payload")
    response_code = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['assignment', 'log_type']),
        ]
    
    def __str__(self):
        return f"{self.log_type} - {self.assignment.request.request_id} at {self.created_at}"


class AuditLog(models.Model):
    """System-wide audit log"""
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="audit_logs")  # ✅ Direct reference
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.action[:50]}"



"""
QUALITY CONTROL
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation

class QCLot(models.Model):
    """
    QC Material Lot - Like a batch of control material with known values.
    Each lot has a specific target value and acceptable range.
    """
    QC_LEVEL_CHOICES = [
        ('L1', 'Level 1 - Low'),
        ('L2', 'Level 2 - Normal'),
        ('L3', 'Level 3 - High'),
    ]

    UNIT_TYPE = [
        ('mg/dL', 'mg/dL'),
        ('mmol/L', 'mmol/L'),
        ('g/L', 'g/L'),
        ('g/dL', 'g/dL'),
        ('ng/mL', 'ng/mL'),
        ('µg/L', 'µg/L'),
        ('U/L', 'U/L'),
        ('IU/L', 'IU/L'),
        ('pg/mL', 'pg/mL'),
        ('mEq/L', 'mEq/L'),
        ('%','Percent (%)'),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='qc_lots')
    test = models.ForeignKey(VendorTest, on_delete=models.CASCADE, related_name='qc_lots', help_text="Which test this QC lot is for")
    
    # Lot Information
    lot_number = models.CharField(max_length=100, help_text="Manufacturer's lot/batch number")
    level = models.CharField(max_length=2, choices=QC_LEVEL_CHOICES, default='L2')
    manufacturer = models.CharField(max_length=200, blank=True, help_text="QC material manufacturer")
    
    # Target Values
    target_value = models.DecimalField(max_digits=10, decimal_places=3, 
                                       help_text="Expected/target value for this QC")
   
    # Acceptable Range (Standard Deviation based)
    sd = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, help_text="Standard deviation (optional if using explicit limits)")

    # Explicit range alternative (if lab prefers exact min/max)
    explicit_low = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    explicit_high = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    units = models.CharField(max_length=20, choices=UNIT_TYPE, default="mg/dL")
    # units = models.CharField(max_length=50, help_text="mg/dL, mmol/L, etc.")
     
    # Calculated limits (auto-calculated on save)
    mean = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, help_text="Mean value (same as target initially)")

    limit_1sd_low = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    limit_1sd_high = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    limit_2sd_low = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    limit_2sd_high = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    limit_3sd_low = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    limit_3sd_high = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    
    # Dates
    received_date = models.DateField(null=True, blank=True, help_text="Date QC lot was received")
    expiry_date = models.DateField(null=True, blank=True, help_text="Expiration date of QC material")
    opened_date = models.DateField(null=True, blank=True, help_text="Date vial was opened")
    closed_date = models.DateField(null=True, blank=True)

    # Status
    is_active = models.BooleanField(default=True, help_text="Currently in use")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('vendor', 'test', 'lot_number', 'level')
        ordering = ['-received_date', 'test__name', 'level']
        verbose_name = "QC Lot"
        verbose_name_plural = "QC Lots"
        
    def clean(self):
        # If explicit range is provided, ensure low < high
        if self.explicit_low is not None and self.explicit_high is not None:
            if self.explicit_low >= self.explicit_high:
                raise ValidationError('explicit_low must be less than explicit_high')

        # If using SD method, ensure target and sd are provided together
        if (self.target_value is None) ^ (self.sd is None):
            # one is set but not the other
            if self.target_value is None:
                raise ValidationError('sd provided but target_value is missing')
            if self.sd is None:
                raise ValidationError('target_value provided but sd is missing')

        # expiry_date must be after received_date if both present
        if self.received_date and self.expiry_date:
            if self.expiry_date <= self.received_date:
                raise ValidationError('expiry_date must be after received_date')

        # Prevent activating an expired lot
        if self.is_active and self.expiry_date and self.expiry_date < timezone.now().date():
            raise ValidationError('Cannot activate an expired QC lot')

        super().clean()

    def save(self, *args, **kwargs):
        """Auto-calculate control limits based on SD"""
        if self.target_value is not None and self.sd is not None:
            self.mean = self.target_value
            sd, target_value = Decimal(self.sd), Decimal(self.target_value)
            # target_value = Decimal(self.target_value)
            self.limit_1sd_low = target_value - sd
            self.limit_1sd_high = target_value + sd
            self.limit_2sd_low = target_value - (2 * sd)
            self.limit_2sd_high = target_value + (2 * sd)
            self.limit_3sd_low = target_value - (3 * sd)
            self.limit_3sd_high = target_value + (3 * sd)
            # self.limit_3sd_high = target_value + (3 * self.sd)
        else:
            # If explicit range provided, copy them into limit fields to simplify logic
            if self.explicit_low is not None and self.explicit_high is not None:
                self.limit_1sd_low = None
                self.limit_1sd_high = None
                self.limit_2sd_low = self.explicit_low
                self.limit_2sd_high = self.explicit_high
                # leave 3sd None

        super().save(*args, **kwargs)

        # Ensure only one active lot per vendor/test/level
        if self.is_active:
            QCLot.objects.filter(
                vendor=self.vendor,
                test=self.test,
                level=self.level,
            ).exclude(pk=self.pk).update(is_active=False)

    
    def is_expired(self):
        """Check if QC lot is expired"""
        if not self.expiry_date:
            return False
        return timezone.now().date() > self.expiry_date
    
    def days_until_expiry(self):
        """Days remaining until expiry"""
        delta = self.expiry_date - timezone.now().date()
        return delta.days
    
    def __str__(self):
        return f"{self.test.code} - {self.get_level_display()} - Lot {self.lot_number}"



def to_decimal(value):
    """Safely convert any value into Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


class QCResult(models.Model):
    QC_STATUS_CHOICES = [
        ('PASS', 'Pass - In Control'),
        ('WARNING', 'Warning - Near Limit'),
        ('FAIL', 'Fail - Out of Control'),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='qc_results')
    qc_lot = models.ForeignKey("QCLot", on_delete=models.CASCADE, related_name='results')

    result_value = models.DecimalField(max_digits=10, decimal_places=3)
    z_score = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)

    run_date = models.DateField(default=timezone.now, db_index=True)
    run_time = models.TimeField(default=timezone.now)
    run_number = models.IntegerField(default=1)

    instrument = models.ForeignKey(
        "Equipment",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='qc_results'
    )

    status = models.CharField(max_length=10, choices=QC_STATUS_CHOICES, default='PASS')
    rule_violations = models.JSONField(default=list, blank=True)

    comments = models.TextField(blank=True)
    corrective_action = models.TextField(blank=True)

    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='qc_entries'
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='qc_reviews'
    )

    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='qc_approvals'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-run_date', '-run_time']
        indexes = [
            models.Index(fields=['vendor', 'run_date']),
            models.Index(fields=['qc_lot', 'run_date']),
            models.Index(fields=['status', 'is_approved']),
        ]

    # ---------------------------
    # MAIN SAVE: ALWAYS SAFE
    # ---------------------------
    def save(self, *args, **kwargs):
        # Validate result_value
        result = to_decimal(self.result_value)
        if result is None:
            raise ValidationError("Invalid QC result value.")
        self.result_value = result

        # Calculate z-score
        mean = to_decimal(self.qc_lot.mean)
        sd = to_decimal(self.qc_lot.sd)

        if mean is not None and sd not in (None, 0):
            self.z_score = (result - mean) / sd
        else:
            self.z_score = None

        # Determine PASS / WARNING / FAIL
        self.status = self.determine_status(result)

        # Auto-approve PASS
        if self.status == 'PASS' and not self.is_approved:
            self.is_approved = True
            self.approved_at = timezone.now()

        # Save the QC result
        super().save(*args, **kwargs)

        # Only AFTER saving: apply Westgard rules
        self.apply_westgard()

    # ---------------------------
    # STATUS DECISION
    # ---------------------------
    def determine_status(self, result):
        l3_low = to_decimal(self.qc_lot.limit_3sd_low)
        l3_high = to_decimal(self.qc_lot.limit_3sd_high)
        l2_low = to_decimal(self.qc_lot.limit_2sd_low)
        l2_high = to_decimal(self.qc_lot.limit_2sd_high)

        if l3_low is not None and l3_high is not None:
            if result < l3_low or result > l3_high:
                return 'FAIL'
            if l2_low is not None and l2_high is not None:
                if result < l2_low or result > l2_high:
                    return 'WARNING'

        elif l2_low is not None and l2_high is not None:
            if result < l2_low or result > l2_high:
                return 'FAIL'

        return 'PASS'

    # ---------------------------
    # WESTGARD RULES
    # ---------------------------
    def apply_westgard(self):
        recent = QCResult.objects.filter(
            qc_lot=self.qc_lot
        ).order_by('-run_date', '-run_time')[:10]

        if len(recent) < 2:
            return

        values = [to_decimal(r.result_value) for r in recent if to_decimal(r.result_value) is not None]
        z = [to_decimal(r.z_score) or Decimal(0) for r in recent]

        v = []

        # 1-3s
        if abs(z[0]) > 3:
            v.append("1₃ₛ: |Z| > 3")

        # 2-2s
        if len(z) >= 2 and ((z[0] > 2 and z[1] > 2) or (z[0] < -2 and z[1] < -2)):
            v.append("2₂ₛ: Two values > ±2")

        # R-4s
        sd = to_decimal(self.qc_lot.sd)
        if len(values) >= 2 and sd:
            if abs(values[0] - values[1]) > 4 * sd:
                v.append("R₄ₛ: Range > 4SD")

        # 4-1s
        if len(z) >= 4:
            if all(x > 1 for x in z[:4]) or all(x < -1 for x in z[:4]):
                v.append("4₁ₛ: Four values > ±1 (same side)")

        # 10x
        if len(z) >= 10:
            if all(x > 0 for x in z[:10]) or all(x < 0 for x in z[:10]):
                v.append("10x: Ten on same side of mean")

        if v != self.rule_violations:
            self.rule_violations = v
            super().save(update_fields=['rule_violations'])

    def __str__(self):
        return f"{self.qc_lot} – {self.result_value}"

class QCAction(models.Model):
    """
    Corrective Actions taken when QC fails.
    Tracks what was done to fix the problem.
    To be used in the future --- (Corrective and Preventive Action)
    """
    ACTION_TYPE_CHOICES = [
        ('REPEAT', 'Repeat QC'),
        ('CALIBRATE', 'Recalibrate Instrument'),
        ('MAINTENANCE', 'Instrument Maintenance'),
        ('REAGENT', 'Replace Reagent'),
        ('NEW_LOT', 'Open New QC Lot'),
        ('SERVICE', 'Call Service Engineer'),
        ('OTHER', 'Other'),
    ]
    
    qc_result = models.ForeignKey(QCResult, on_delete=models.CASCADE, related_name='actions')
    action_type = models.CharField(max_length=20, choices=ACTION_TYPE_CHOICES)
    description = models.TextField(help_text="Detailed description of action taken")
    
    # Resolution
    resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True)
    
    # User tracking
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.performed_at.date()}"


class QCTestApproval(models.Model):
    """
    Daily approval status per test.
    Determines if patient testing is allowed for a specific test on a specific day.
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='qc_approvals')
    test = models.ForeignKey(VendorTest, on_delete=models.CASCADE, related_name='daily_qc_status')
    date = models.DateField(default=timezone.now, db_index=True)
    
    # Approval Status
    is_approved = models.BooleanField(default=False,
                                      help_text="Test approved for patient testing today")
    all_levels_passed = models.BooleanField(default=False,
                                            help_text="All QC levels passed")
    
    # Related QC Results
    qc_results = models.ManyToManyField(QCResult, related_name='test_approvals')
    
    # Comments
    notes = models.TextField(blank=True)
    
    # User tracking
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    approved_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('vendor', 'test', 'date')
        ordering = ['-date', 'test__name']
        verbose_name = "Daily QC Approval"
        verbose_name_plural = "Daily QC Approvals"
    
    def __str__(self):
        status = "✅ APPROVED" if self.is_approved else "❌ NOT APPROVED"
        return f"{self.test.code} - {self.date} - {status}"





# class TestResult(models.Model):
#     """
#     Stores the final result for a TestAssignment.
#     Fully supports:
#     - Quantitative (QNT)
#     - Qualitative (QLT via QualitativeOption)
#     - Critical values, AMR, clinical reportable range
#     - Audit trail (entered, verified, released)
#     - Amendments
#     """

#     assignment = models.OneToOneField(
#         'TestAssignment',
#         on_delete=models.CASCADE,
#         related_name="result"
#     )

#     # ===================
#     # RESULT FIELDS
#     # ===================
#     result_value = models.TextField(help_text="The measured value or observation")
#     units = models.CharField(max_length=50, blank=True)
#     reference_range = models.CharField(max_length=80, blank=True)

#     FLAG_CHOICES = [
#         ('N', 'Normal'),
#         ('H', 'High'),
#         ('L', 'Low'),
#         ('A', 'Abnormal'),
#         ('C', 'Critical'),
#         ('M', 'Unmeasurable (Outside AMR)'),
#         ('R', 'Out of Reportable Range'),
#         ('*', 'Corrected'),
#     ]

#     flag = models.CharField(max_length=1, choices=FLAG_CHOICES, default='N')

#     # CONTEXTUAL FIELDS
#     remarks = models.TextField(blank=True)
#     interpretation = models.TextField(blank=True)

#     DATA_SOURCE = [
#         ('manual', 'Manual Entry'),
#         ('instrument', 'Instrument Auto-Generated'),
#         ('imported', 'Imported from External System'),
#         ('calculated', 'Calculated Result'),
#     ]
#     data_source = models.CharField(max_length=20, choices=DATA_SOURCE, default='manual')

#     instrument_name = models.CharField(max_length=150, blank=True)
#     instrument_run_id = models.CharField(max_length=100, blank=True)

#     # ===================
#     # USER + AUDIT FIELDS
#     # ===================
#     entered_by = models.ForeignKey(settings.AUTH_USER_MODEL,null=True, on_delete=models.SET_NULL, related_name="entered_results")

#     verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_results")

#     released_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,
#         null=True, blank=True,
#         on_delete=models.SET_NULL,
#         related_name="released_results"
#     )

#     entered_at = models.DateTimeField(auto_now_add=True)
#     verified_at = models.DateTimeField(null=True, blank=True)
#     released_at = models.DateTimeField(null=True, blank=True)

#     released = models.BooleanField(default=False)
#     is_amended = models.BooleanField(default=False)

#     version = models.IntegerField(default=1)
#     previous_value = models.TextField(blank=True)
#     amendment_reason = models.TextField(blank=True)

#     # ===================
#     # QUALITY CONTROL
#     # ===================
#     qc_passed = models.BooleanField(default=True)
#     qc_comment = models.TextField(blank=True)

#     delta_flag = models.BooleanField(default=False)
#     delta_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

#     class Meta:
#         ordering = ['-entered_at']
#         verbose_name = "Test Result"
#         verbose_name_plural = "Test Results"
        
#         # ✅ CUSTOM PERMISSIONS DEFINED HERE
#         permissions = [
#             ("can_verify_results", "Can verify test results"),
#             ("can_release_results", "Can release test results"),
#             ("can_amend_results", "Can amend released results"),
#         ]
        
#         indexes = [
#             models.Index(fields=['assignment', 'entered_at']),
#             models.Index(fields=['entered_at']),
#             models.Index(fields=['verified_at']),
#             models.Index(fields=['released', 'verified_at']),
#             models.Index(fields=['flag']),
#             models.Index(fields=['flag', 'data_source']),
#             models.Index(fields=['data_source']),
#         ]

#     def __str__(self):
#         return f"Result for {self.assignment.lab_test.name} - {self.result_value}"

#     # ======================================================
#     #  M E T H O D S
#     # ======================================================
    
#     def update_result(self, new_value, user, reason=""):
#         """Update result value with audit trail"""
#         if self.verified_at:
#             raise ValidationError("Cannot modify verified result. Use amendment process.")
        
#         if str(self.result_value).strip() != str(new_value).strip():
#             self.previous_value = self.result_value
#             self.result_value = new_value
#             self.amendment_reason = reason
#             self.version += 1
#             self.is_amended = True
#             self.save()
            
#             # Re-run auto flagging after update
#             self.auto_flag_result()

#     def mark_verified(self, user):
#         """Mark result as verified"""
#         if self.verified_at:
#             raise ValidationError("Result already verified")
        
#         # if self.entered_by == user:
#         #     raise ValidationError("Self Verification is not allowed")
        
#         self.verified_by = user
#         self.verified_at = timezone.now()
#         self.save(update_fields=['verified_by', 'verified_at'])
        
#         # Update assignment status
#         self.assignment.mark_verified()

#     def release_result(self, user):
#         """Release verified result to patient/doctor"""
#         if not self.verified_at:
#             raise ValidationError("Result must be verified before release")
#         if self.released:
#             raise ValidationError("Result already released")
        
#         self.released = True
#         self.released_by = user
#         self.released_at = timezone.now()
#         self.save(update_fields=['released', 'released_by', 'released_at'])

#     def check_delta(self):
#         """Check delta against previous result"""
#         if not self.is_quantitative:
#             return
        
#         # Get previous result for same patient/test
#         previous = TestResult.objects.filter(
#             assignment__request__patient=self.assignment.request.patient,
#             assignment__lab_test=self.assignment.lab_test,
#             released=True
#         ).exclude(id=self.id).order_by('-entered_at').first()
        
#         if not previous:
#             return
        
#         try:
#             current_val = Decimal(str(self.result_value).strip())
#             previous_val = Decimal(str(previous.result_value).strip())
            
#             if previous_val != 0:
#                 delta = abs((current_val - previous_val) / previous_val * 100)
#                 self.delta_percent = delta
                
#                 # Flag if delta > 50% (configurable threshold)
#                 if delta > 50:
#                     self.delta_flag = True
                    
#                 self.save(update_fields=['delta_percent', 'delta_flag'])
#         except (InvalidOperation, ValueError, ZeroDivisionError):
#             # Silently skip delta check if calculation fails
#             pass

#     # ======================================================
#     #  P R O P E R T I E S
#     # ======================================================
    
#     @property
#     def can_be_verified(self):
#         """Check if result can be verified"""
#         return (
#             # not self.verified_at and 
#             # not self.released and
#             self.entered_at is not None and
#             self.verified_at is None and
#             self.released is False and
#             self.qc_passed
#         )

    
#     @property
#     def can_be_released(self):
#         """Check if result can be released"""
#         return (
#             self.verified_at and 
#             not self.released and
#             self.qc_passed
#         )
# # @property
# #     def can_be_released(self):
# #         return (
# #             self.verified_at is not None and
# #             self.released is False
# #         )
    
#     @property
#     def test(self):
#         return self.assignment.lab_test

#     @property
#     def is_quantitative(self):
#         return self.test.result_type == 'QNT'

#     @property
#     def is_qualitative(self):
#         return self.test.result_type == 'QLT'

#     @property
#     def is_critical(self):
#         return self.flag == 'C'

#     @property
#     def formatted_result(self):
#         if self.is_quantitative and self.units:
#             return f"{self.result_value} {self.units}"
#         return self.result_value

#     # ======================================================
#     #  V A L I D A T I O N
#     # ======================================================
    
#     def clean(self):
#         """Validate result data before save"""
#         # Only validate quantitative results as numeric
#         if self.is_quantitative:
#             try:
#                 Decimal(str(self.result_value).strip())
#             except (InvalidOperation, ValueError):
#                 raise ValidationError({"result_value": "Quantitative result must be numeric."})

#         # # Prevent self-verification
#         # if self.verified_by and self.verified_by == self.entered_by:
#         #     raise ValidationError("Cannot verify your own result.")

#     # ======================================================
#     #  A U T O  F L A G G I N G  (OPTIMIZED VERSION)
#     # ======================================================
    
#     def auto_flag_result(self):
#         """
#         FINAL and ONLY auto-flag engine.
#         Handles:
#         • Qualitative (via QualitativeOption)
#         • AMR (Analytical Measuring Range)
#         • CRR (Clinical Reportable Range)
#         • Panic/Critical Limits
#         • Reference Range
        
#         Optimized to save only once at the end.
#         """
#         test = self.test
#         flag_to_set = 'N'  # Default: Normal

#         # ---------------------
#         # QUALITATIVE LOGIC
#         # ---------------------
#         if self.is_qualitative:
#             value_norm = self.result_value.strip().lower()
#             match = test.qlt_options.filter(normalized=value_norm).first()
            
#             if match:
#                 flag_to_set = 'N' if match.is_normal else 'A'
#             else:
#                 flag_to_set = 'A'  # Unknown/unmatched value = Abnormal
        
#         # ---------------------
#         # QUANTITATIVE LOGIC
#         # ---------------------
#         else:
#             try:
#                 value = Decimal(str(self.result_value).strip())
#             except (InvalidOperation, ValueError):
#                 flag_to_set = 'A'  # Invalid numeric = Abnormal
#             else:
#                 # Check in PRIORITY order (most severe first)
                
#                 # 1. AMR checks (instrument measurement limits)
#                 if test.amr_low is not None and value < test.amr_low:
#                     flag_to_set = 'M'  # Unmeasurable
#                 elif test.amr_high is not None and value > test.amr_high:
#                     flag_to_set = 'M'  # Unmeasurable
                
#                 # 2. Reportable range (clinical reporting limits)
#                 elif test.reportable_low is not None and value < test.reportable_low:
#                     flag_to_set = 'R'  # Out of reportable range
#                 elif test.reportable_high is not None and value > test.reportable_high:
#                     flag_to_set = 'R'  # Out of reportable range
                
#                 # 3. Panic/Critical limits (immediate clinical action)
#                 elif test.panic_low_value is not None and value <= test.panic_low_value:
#                     flag_to_set = 'C'  # Critical
#                 elif test.panic_high_value is not None and value >= test.panic_high_value:
#                     flag_to_set = 'C'  # Critical
                
#                 # 4. Reference range (normal clinical interpretation)
#                 elif test.min_reference_value is not None and value < test.min_reference_value:
#                     flag_to_set = 'L'  # Low
#                 elif test.max_reference_value is not None and value > test.max_reference_value:
#                     flag_to_set = 'H'  # High
#                 # else: remains 'N' (Normal)

#         # ✅ Single save at end (only if flag changed)
#         if self.flag != flag_to_set:
#             self.flag = flag_to_set
#             self.save(update_fields=['flag'])

