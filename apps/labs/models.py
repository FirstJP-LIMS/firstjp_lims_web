from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from apps.tenants.models import Vendor
import uuid
from django.db.models import Max
from django.utils.text import slugify
from .utils import get_next_sequence



# ---------------------
# To customize id
# ---------------------
class SequenceCounter(models.Model):
    """
    Maintains atomic counters per vendor for generating IDs.
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True)
    prefix = models.CharField(max_length=20)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("vendor", "prefix")

    def __str__(self):
        return f"{self.vendor or 'GLOBAL'} - {self.prefix} ({self.last_number})"


# # Create your models here.
# # Global Model: Department Catalog and Test Definitions Deleted

# # NOTE: TestReferenceRange model is still needed for advanced ranges (age/gender/etc.) 

# ---------------------
# Per-vendor configuration
# ---------------------
class Department(models.Model):
    """
        Vendor-specific lab departments (e.g., Hematology, Serology).
        CRITICAL CHANGE: Added vendor FK.
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Vendor Department"
        ordering = ["name"]
        unique_together = ('vendor', 'name') 

    def __str__(self):
        return f"{self.vendor.name} - {self.name}"


class VendorTest(models.Model):
    """
    The primary test definition, completely scoped to a specific vendor/lab.
    
    This model combines the function of the old GlobalTest and VendorTest.
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="lab_tests")    
    code = models.CharField(max_length=64) 
    name = models.CharField(max_length=150)
    assigned_department = models.ForeignKey(
        Department, 
        on_delete=models.PROTECT, 
        related_name='tests',
        help_text="The department in this lab responsible for running the test."
    )    
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    turnaround_override = models.DurationField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    specimen_type = models.CharField(max_length=100, help_text="Blood, Urine, Tissue, etc.")
    default_units = models.CharField(max_length=50, blank=True)
    default_reference_text = models.CharField(max_length=255, blank=True)
    # Required for the Quantitative/Qualitative requirement
    RESULT_TYPE_CHOICES = [('QNT', 'Quantitative'), ('QLT', 'Qualitative')]
    result_type = models.CharField(max_length=3, choices=RESULT_TYPE_CHOICES, default='QNT')
    general_comment_template = models.TextField(blank=True) # For constant report comments
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        verbose_name = "Lab Test"
        unique_together = ("vendor", "code") 
    
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.test.name, allow_unicode=True)
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            self.slug = f"{base_slug}-{timestamp}"
        super().save(*args, **kwargs)
        
    def effective_tat(self):
        return self.turnaround_override or self.test.default_turnaround

    def __str__(self):
        return f"[{self.vendor.name}] {self.code}: {self.name}"

# ---------------------
# Tenant-scoped operational data
# ---------------------
class Patient(models.Model):
    GENDER_CHOICE = [
        ('M', 'Male'),
        ('F', 'Female')
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='patients')    
    patient_id = models.CharField(max_length=20, help_text="Auto-generated 6-digit patient ID.")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICE)
    contact_email = models.EmailField(blank=True)
    contact_number = models.CharField(max_length=15, blank=True)
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


# Test Request and Assignment
class Sample(models.Model):
    SAMPLE_STATUS = [
        ('A', 'Accessioned'), # Sample has been logged and assigned an ID
        ('R', 'Rejected'),
        ('C', 'Consumed'),
        ('I', 'In Storage'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="samples")
    
    # Global unique sample/barcode ID (recommended for barcoding)
    sample_id = models.CharField(max_length=64, unique=True, help_text="Globally unique ID for barcoding.") 
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="samples")
    
    # Specimen type is synced with VendorTest or GlobalTest
    specimen_type = models.CharField(max_length=100, help_text="Specimen type e.g. Blood, Urine, Serum, etc.")

    # Link to the TestRequest that generated this sample
    test_request = models.ForeignKey('TestRequest', on_delete=models.CASCADE, related_name='samples') 
    
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="collected_samples")
    collected_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(choices=SAMPLE_STATUS, max_length=1, default='A')
    location = models.CharField(max_length=200, blank=True) 
    
    # if you want a guaranteed unique 6-digit ID across ALL labs (best for barcoding).
    # Save Uniques Id     
    def save(self, *args, **kwargs):
        if not self.sample_id:
            self.sample_id = get_next_sequence("SMP")
        super().save(*args, **kwargs)

    def __str__(self): 
        return f"{self.sample_id} - {self.specimen_type}"

# Assuming all necessary imports (Vendor, settings.AUTH_USER_MODEL, etc.) are present

# --- Minor cleanup to TestRequest save method ---
class TestRequest(models.Model):
    """Represents the entire patient order/request for multiple tests."""
    ORDER_STATUS = [
        ('P', 'Pending'), # Created, waiting for sample accessioning
        ('R', 'Received'), # Sample accessioned, tests assigned
        ('A', 'Analysis'), # Work is being done on tests
        ('C', 'Complete'), # All tests analyzed, waiting for verification
        ('V', 'Verified'), # Final report ready for release
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="requests")
    
    # Request ID generated sequentially per-vendor (e.g., REQ-0001)
    request_id = models.CharField(max_length=64, unique=True) # Unique globally for simplicity
    
    patient = models.ForeignKey('Patient', on_delete=models.PROTECT, related_name="requests")

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="ordered_requests")

    requested_tests = models.ManyToManyField('VendorTest', related_name="test_requests")

    clinical_history = models.TextField(blank=True)
    
    priority = models.CharField(max_length=32, default="routine") # e.g., routine, stat
    
    status = models.CharField(choices=ORDER_STATUS, max_length=1, default="P")
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Simplified ID generation logic, assuming get_next_sequence handles prefixing
        if not self.request_id:
            # Using 'REQ' prefix for Request ID
            self.request_id = get_next_sequence("REQ", vendor=self.vendor) 
        super().save(*args, **kwargs)

    def __str__(self):
        return self.request_id


# --- Critical cleanup and simplification to TestAssignment ---
class TestAssignment(models.Model):
    """The individual unit of work: one Test assigned to one Request."""
    ASSIGNMENT_STATUS = [
        ('P', 'Pending'), # Created, waiting for instrument assignment
        ('Q', 'Queued'), # Queued on Instrument
        ('A', 'Analysis Complete'), # Result is back from instrument/manually entered
        ('V', 'Result Verified'), # Result is verified by a staff member
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="assignments")
    request = models.ForeignKey(TestRequest, on_delete=models.CASCADE, related_name="assignments")
    # Links directly to the LabTest definition
    lab_test = models.ForeignKey('VendorTest', on_delete=models.PROTECT, related_name="assignments") 
    # The sample containing the material needed for this test
    sample = models.ForeignKey('Sample', on_delete=models.PROTECT, related_name="assignments", 
                               help_text="The sample specimen required to run this test.")
    # Department is copied from VendorTest definition at creation time for performance/routing
    department = models.ForeignKey('Department', on_delete=models.PROTECT, related_name="assigned_work")
    status = models.CharField(choices=ASSIGNMENT_STATUS, max_length=1, default='P')
    instrument = models.ForeignKey('Equipment', null=True, blank=True, on_delete=models.SET_NULL,
                                   help_text="The equipment used or scheduled to run this test.")
    
    class Meta:
        # Ensures no two Assignments for the SAME test exist within one request
        unique_together = ('request', 'lab_test') 

    def __str__(self):
        return f"{self.request.request_id} - {self.lab_test.code}"


class TestResult(models.Model):
    """The final measured value for a single TestAssignment."""
    # One-to-One link to the unit of work
    assignment = models.OneToOneField(TestAssignment, on_delete=models.CASCADE, related_name="result")
    
    result_value = models.TextField(help_text="The measured value.")
    units = models.CharField(max_length=50, blank=True)
    reference_range = models.CharField(max_length=80, blank=True)
    
    # New Field: Flag to indicate high/low/normal (H, L, N)
    NORMAL_FLAG_CHOICES = [
        ('N', 'Normal'), 
        ('H', 'High'), 
        ('L', 'Low'), 
        ('A', 'Abnormal')
        ]
    flag = models.CharField(max_length=1, choices=NORMAL_FLAG_CHOICES, default='N')
    remarks = models.TextField(blank=True)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="entered_results")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_results")
    entered_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    released = models.BooleanField(default=False)

    def __str__(self):
        return f"Result for {self.assignment.global_test.code}"


# Equipment & AuditLog Models (mostly unchanged, except for AuditLog FK clarification)
class Equipment(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="equipment")
    name = models.CharField(max_length=200)
    manufacturer = models.CharField(max_length=200, blank=True)
    model = models.CharField(max_length=200, blank=True)
    serial_number = models.CharField(max_length=200, blank=True)
    
    # API key per device for local Windows service communication
    device_key = models.CharField(max_length=64, unique=True, default=uuid.uuid4) 
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    
    # NOTE: You'll also need a VendorInterface model to manage the connection settings.

    def __str__(self):
        return f"{self.vendor.name} - {self.name}"

class AuditLog(models.Model):
    # Nullable vendor to allow platform admin actions to be logged without a specific tenant
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="audit_logs", null=True, blank=True) 
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=255)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.action} by {self.user}"
