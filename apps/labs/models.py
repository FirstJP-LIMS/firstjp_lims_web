from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from apps.tenants.models import Vendor
import uuid
from django.db.models import Max
from django.utils.text import slugify
from .utils import get_next_sequence

# Create your models here.
"""
Departments:
1. Hematology & Immunology 
2. Chemical Pathology 
3. Medical Microbiology 
4. Histopathology 
5. Cytology
6. Molecular Diagnostics 
7. Radiology
    And there are different tests under each category. From the front end, patient details with clinical & sample information and specific test requests are logged in.
    If you have the know of how lims work, can you break things down, for execution...

Department and Test type to be controlled by the platform admin. i.e the LIMS, has all department available to all tenants..
Vendor, controls, their lab assistants, patients, samples, test requests and results.


Ask Scientist - If Each tenant can choose which department and test types they want to enable for their lab, or all tenants have access to all departments and test types by default.


# ---------------------
# Tenant-Scoped Models (Vendor Managed)
# Patient	TENANT	Patient records specific to the vendor/lab.
# TestRequest	TENANT	The patient's order for a list of tests.
# Sample	TENANT	The physical specimen received by the vendor/lab.
# TestAssignment	TENANT	Tracks the execution of a GlobalTest within this vendor's workflow.
# Result	TENANT	The final measured value for a TestAssignment.
# Equipment	TENANT	Tracks the vendor's specific lab instruments.
# ---------------------

"""

# Global Model: Department Catalog
class Department(models.Model):
    """Platform-level standard lab departments (e.g., Hematology)."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Department Catalog"
        ordering = ["name"]

    def __str__(self):
        return self.name

# Global Model: Test Definitions
# Renamed from TestType for clarity
class GlobalTest(models.Model):
    """
    Platform-level test definitions (e.g., Hemoglobin).
    """
    code = models.CharField(max_length=64, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='global_tests',help_text="Standard department responsible for this test."
    )
    name = models.CharField(max_length=150)
    specimen_type = models.CharField(max_length=100, help_text="Blood, Urine, Tissue, etc.")
    default_units = models.CharField(max_length=50, blank=True)
    
    # Tracks the basic text reference range
    default_reference_text = models.CharField(max_length=255, blank=True)
    
    default_turnaround = models.DurationField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.code}: {self.name}"

# NOTE: TestReferenceRange model is still needed for advanced ranges (age/gender/etc.) 
# but is omitted here for brevity. It would link to GlobalTest.

# ---------------------
# Per-vendor configuration (enables/price/overrides)
# ---------------------
class VendorTest(models.Model):
    """Vendor-specific configuration (pricing, TAT override) for a GlobalTest."""
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="vendor_tests")
    test = models.ForeignKey(GlobalTest, on_delete=models.CASCADE, related_name="vendor_configs")    
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    turnaround_override = models.DurationField(null=True, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ("vendor", "test")

    def effective_tat(self):
        return self.turnaround_override or self.test.default_turnaround

    def __str__(self):
        return f"{self.vendor.name} - {self.test.code}"



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


# ---------------------
# Tenant-scoped operational data
# ---------------------
class Patient(models.Model):
    GENDER_CHOICE = [
        ('M', 'Male'),
        ('F', 'Female')
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='patients')
    
    # Auto-generated per-vendor ID
    patient_id = models.CharField(max_length=20, help_text="Auto-generated 6-digit patient ID.") 
    
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICE)
    contact_email = models.EmailField(blank=True)
    contact_number = models.CharField(max_length=15, blank=True)

    class Meta:
        unique_together = ("vendor", "patient_id")
        ordering = ("-id",)

    def save(self, *args, **kwargs):
        if not self.patient_id:
            self.patient_id = get_next_sequence("PAT")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient_id} — {self.first_name} {self.last_name}"


class Sample(models.Model):
    SAMPLE_STATUS = [
        ('A', 'Accepted'), # Sample has been logged and assigned an ID
        ('R', 'Rejected'),
        ('C', 'Consumed'),
        ('I', 'In Storage'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="samples")
    
    # Global unique sample/barcode ID (recommended for barcoding)
    sample_id = models.CharField(max_length=64, unique=True, help_text="Globally unique ID for barcoding.") 
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="samples")
    specimen_type = models.CharField(max_length=100)
    
    # New Field: Link to the TestRequest that generated this sample
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


class TestRequest(models.Model):
    """Represents the entire patient order/request for multiple tests."""
    ORDER_STATUS = [
        ('P', 'Pending'),
        ('R', 'Received'),
        ('A', 'Analysis'),
        ('C', 'Complete'),
        ('V', 'Verified'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="requests")
    
    # Request ID generated sequentially per-vendor (e.g., REQ-0001)
    request_id = models.CharField(max_length=64, unique=True) 
    
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="requests")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="ordered_requests")
    clinical_history = models.TextField(blank=True)
    priority = models.CharField(max_length=32, default="routine") 
    status = models.CharField(choices=ORDER_STATUS, max_length=1, default="P")
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        # Implement sequential save logic here for request_id (REQ-0001)

    def save(self, *args, **kwargs):
        if not self.request_id:
            prefix = f"ORD-{self.vendor.tenant_id}-"
            seq = get_next_sequence(prefix, vendor=self.vendor)
            self.request_id = seq
        super().save(*args, **kwargs)

    def __str__(self):
        return self.request_id


class TestAssignment(models.Model):
    """The individual unit of work: one Test assigned to one Request."""
    ASSIGNMENT_STATUS = [
        ('P', 'Pending'),
        ('Q', 'Queued on Instrument'),
        ('A', 'Analysis Complete'),
        ('V', 'Result Verified'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="assignments")
    request = models.ForeignKey(TestRequest, on_delete=models.CASCADE, related_name="assignments")
    
    # Links to the Global Test Definition and the Vendor's config
    global_test = models.ForeignKey(GlobalTest, on_delete=models.PROTECT, related_name="assignments")
    vendor_config = models.ForeignKey(VendorTest, null=True, on_delete=models.SET_NULL)
    
    # Inherit routing from VendorTest, or use the global default
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="assigned_work") 
    
    status = models.CharField(choices=ASSIGNMENT_STATUS, max_length=1, default='P')
    instrument = models.ForeignKey('Equipment', null=True, blank=True, on_delete=models.SET_NULL)
    
    class Meta:
        # Ensures a vendor doesn't accidentally assign the same test twice to one request
        unique_together = ('request', 'global_test')

    def __str__(self):
        return f"{self.request.request_id} - {self.global_test.code}"


class TestResult(models.Model):
    """The final measured value for a single TestAssignment."""
    # One-to-One link to the unit of work
    assignment = models.OneToOneField(TestAssignment, on_delete=models.CASCADE, related_name="result")
    
    result_value = models.TextField(help_text="The measured value.")
    units = models.CharField(max_length=50, blank=True)
    reference_range = models.CharField(max_length=80, blank=True)
    
    # New Field: Flag to indicate high/low/normal (H, L, N)
    NORMAL_FLAG_CHOICES = [('N', 'Normal'), ('H', 'High'), ('L', 'Low'), ('A', 'Abnormal')]
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

