from django.db import models

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
    And there are different tests under each category. From the front end , patient details with clinical & sample information and specific test requests are logged in.
    If you have the know of how lims work, can you break things down, for execution...
"""


class Department(models.Model):
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ('vendor', 'name')


class TestType(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='tests')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, blank=True)
    specimen_type = models.CharField(max_length=100, help_text="Blood, Urine, Tissue, etc.")
    normal_range = models.CharField(max_length=255, blank=True)
    units = models.CharField(max_length=50, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    turnaround_time = models.DurationField(null=True, blank=True)


class Patient(models.Model):
    vendor = models.ForeignKey('tenants.Vendor', on_delete=models.CASCADE, related_name='patients')
    patient_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10)
    date_of_birth = models.DateField()
    contact_number = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)


class Sample(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='samples')
    sample_id = models.CharField(max_length=30, unique=True)
    sample_type = models.CharField(max_length=50)
    collected_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='collected_samples')
    collected_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='Collected')  # e.g., Collected, Received, Processed


class TestRequest(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='test_requests')
    sample = models.ForeignKey(Sample, on_delete=models.SET_NULL, null=True, blank=True)
    test = models.ForeignKey(TestType, on_delete=models.CASCADE)
    requested_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    clinical_info = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('in_progress', 'In Progress'),
                 ('completed', 'Completed'), ('verified', 'Verified')],
        default='pending'
    )
    requested_at = models.DateTimeField(auto_now_add=True)


class TestResult(models.Model):
    test_request = models.OneToOneField(TestRequest, on_delete=models.CASCADE, related_name='result')
    result_value = models.CharField(max_length=255)
    remarks = models.TextField(blank=True)
    entered_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='entered_results')
    verified_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='verified_results')
    entered_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

