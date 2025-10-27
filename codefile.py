from django.db import models
from django.utils import timezone
from django.conf import settings
from apps.tenants.models import Vendor


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


# apps/lis/models.py (Global Definitions)

from django.db import models
from django.utils.text import slugify

# global model
class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Department Catalog"
        ordering = ["name"]

    def __str__(self):
        return self.name


# global model
class TestType(models.Model):
    """
    Platform-level test definitions (global).
    Vendors do NOT modify these entries directly.
    """
    code = models.CharField(max_length=64, unique=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='tests')
    name = models.CharField(max_length=150)
    specimen_type = models.CharField(max_length=100, help_text="Blood, Urine, Tissue, etc.")
    default_units = models.CharField(max_length=50, blank=True)
    default_reference = models.CharField(max_length=255, blank=True)
    default_turnaround = models.DurationField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} under {self.department}"


# ---------------------
# Per-vendor configuration (enables/price/overrides)
# ---------------------
class VendorTest(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="vendor_tests")
    test = models.ForeignKey(TestType, on_delete=models.CASCADE, related_name="vendor_configs")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    turnaround_override = models.DurationField(null=True, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ("vendor", "test")

    def effective_tat(self):
        return self.turnaround_override or self.test.default_turnaround

    def __str__(self):
        return f"{self.vendor} - {self.test.code}"


# ---------------------
# Tenant-scoped operational data
# ---------------------
class Patient(models.Model):
    GENDER_CHOICE = [
        ('M', 'Male'),
        ('F', 'Female')
        ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='patients')
    """# can we work on the patient Id to be auto generated and be 6 -digits """
    patient_id = models.CharField(max_length=20, unique=True) 
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICE)
    contact_email = models.EmailField(blank=True)
    contact_number = models.CharField(max_length=15, blank=True)

    class Meta:
        unique_together = ("vendor", "patient_id")

    def __str__(self):
        return f"{self.patient_id} — {self.first_name} {self.last_name}"

# About the sample, there is a story about barcode generations for samples.
class Sample(models.Model):
    SAMPLE_STATUS = [
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
        ('Completed', 'Completed'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="samples")
    """# can we work on the sample Id to be auto generated and be 6 -digits """
    sample_id = models.CharField(max_length=64, unique=True)  # globally unique label
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="samples")
    specimen_type = models.CharField(max_length=100)
    collected_by = models.CharField(max_length=120, blank=True, null=True, help_text="Name of the staff who collected the sample")
    collected_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(choices=SAMPLE_STATUS, max_length=10, default='Accepted')
    
    location = models.CharField(max_length=200, blank=True)  # bench or fridge

    def __str__(self): 
        return f"{self.sample_id} - {self.specimen_type}"
    

class TestOrder(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="orders")
    order_id = models.CharField(max_length=64, unique=True)  # generate e.g., ORD-<vendor>-0001
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="orders")
    sample = models.ForeignKey(Sample, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    test = models.ForeignKey(TestType, on_delete=models.PROTECT, related_name="orders")
    vendor_test = models.ForeignKey(VendorTest, null=True, blank=True, on_delete=models.SET_NULL)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    clinical_history = models.TextField(blank=True)
    priority = models.CharField(max_length=32, default="routine")  # routine/urgent
    status = models.CharField(max_length=32, default="pending")  # pending, queued, sent, processing, completed, verified, released
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_to_lab_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_id


class TestResult(models.Model):
    order = models.OneToOneField(TestOrder, on_delete=models.CASCADE, related_name="result")
    result_value = models.TextField()
    units = models.CharField(max_length=50, blank=True)
    reference_range = models.CharField(max_length=80, blank=True)
    remarks = models.TextField(blank=True)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="entered_results")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_results")
    entered_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    released = models.BooleanField(default=False)

    def __str__(self):
        return f"Result {self.order.order_id}"


# Equipment & devices (Windows service registers)
class Equipment(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="equipment")
    name = models.CharField(max_length=200)
    manufacturer = models.CharField(max_length=200, blank=True)
    model = models.CharField(max_length=200, blank=True)
    serial_number = models.CharField(max_length=200, blank=True)
    device_key = models.CharField(max_length=64, unique=True)  # create API key per device
    last_heartbeat = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.vendor} - {self.name}"

# Audit log
class AuditLog(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="audit_logs", null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=255)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)













# apps/lis/models.py (Tenant Operational Data)

import uuid
from django.db import models, transaction
from django.utils import timezone
from django.db.models import Max

# ... Imports for Vendor and User models

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
        ordering = ("-id",) # Use ID for performance in save() lookup

    def save(self, *args, **kwargs):
        """Auto-generate sequential patient_id scoped to the vendor."""
        if not self.patient_id and self.vendor:
            prefix = "" # No prefix, just sequential number
            with transaction.atomic():
                # Find the highest ID for the current vendor
                max_id = Patient.objects.filter(vendor=self.vendor).aggregate(Max('patient_id'))['patient_id__max']
                
                current_number = 0
                if max_id:
                    try:
                        current_number = int(max_id)
                    except ValueError:
                        pass # Keep at 0 if non-numeric ID exists

                next_number = current_number + 1
                self.patient_id = f"{prefix}{next_number:06d}" # e.g., 000001
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient_id} — {self.first_name} {self.last_name}"


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
    specimen_type = models.CharField(max_length=100)
    
    # New Field: Link to the TestRequest that generated this sample
    test_request = models.ForeignKey('TestRequest', on_delete=models.CASCADE, related_name='samples') 
    
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="collected_samples")
    collected_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(choices=SAMPLE_STATUS, max_length=1, default='A')
    location = models.CharField(max_length=200, blank=True) 

    # Implement global sequential save logic here (similar to Vendor.save) 
    # if you want a guaranteed unique 6-digit ID across ALL labs (best for barcoding).
    
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
