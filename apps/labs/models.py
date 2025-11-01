from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from apps.tenants.models import Vendor
import uuid
from django.db.models import Max
from django.utils.text import slugify
from .utils import get_next_sequence

# Create your models here.
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
class GlobalTest(models.Model):
    """
    Platform-level test definitions (e.g., Hemoglobin).
    """
    RESULT_TYPE_CHOICES = [
        ('QNT', 'Quantitative (Numeric)'),
        ('QLT', 'Qualitative (Text/Descriptive)'),
    ]

    code = models.CharField(max_length=64, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='global_tests',help_text="Standard department responsible for this test."
    )
    name = models.CharField(max_length=150)
    specimen_type = models.CharField(max_length=100, help_text="Blood, Urine, Tissue, etc.")
    default_units = models.CharField(max_length=50, blank=True)
    
    # Tracks the basic text reference range
    default_reference_text = models.CharField(max_length=255, blank=True)
    
    default_turnaround = models.DurationField(null=True, blank=True, help_text="the expected time it takes to complete the test.")

    """Added field for result improvement"""
    # quantitative or qualitative 
    result_type = models.CharField(
        max_length=3,
        choices=RESULT_TYPE_CHOICES,
        default='QNT',
        help_text="Defines the format for data entry and display."
    )
    # Predefined text for the General Comment section of the report
    general_comment_template = models.TextField(
        blank=True,
        help_text="Constant interpretive text or template for the report."
    )
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
    assigned_department = models.ForeignKey(Department, 
        on_delete=models.CASCADE, related_name="vendor_assignments", help_text="The department in this lab responsible for running the test.")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    turnaround_override = models.DurationField(null=True, blank=True, help_text="the expected time it takes to complete the test.")
    enabled = models.BooleanField(default=True)
    slug = models.SlugField(max_length=150, blank=True, null=True, help_text="Name to be used on the url bar.")
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        unique_together = ("vendor", "test")

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.test.name, allow_unicode=True)
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            self.slug = f"{base_slug}-{timestamp}"
        super().save(*args, **kwargs)
        
    def effective_tat(self):
        return self.turnaround_override or self.test.default_turnaround

    def __str__(self):
        return f"{self.vendor.name} - {self.test.code}"


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

    requested_tests = models.ManyToManyField(VendorTest, related_name="test_requests")

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
            self.request_id = get_next_sequence(prefix, vendor=self.vendor)
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

