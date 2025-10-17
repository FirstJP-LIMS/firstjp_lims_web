# apps/labs/models.py
from django.db import models
from apps.core.managers import TenantAwareManager
from apps.tenants.models import Vendor

class SampleRequest(models.Model):
    tenant = models.ForeignKey(Vendor, on_delete=models.CASCADE)  # The foreign key to your Tenant Registry.
    request_id = models.CharField(max_length=64)
    patient_name = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    received_at = models.DateTimeField(auto_now_add=True)
    raw_payload = models.JSONField()

    # Assign the custom manager to the 'objects' attribute
    objects = TenantAwareManager() 
    
    # Gives the admin access to all records regardless of tenant
    all_objects = models.Manager()

    