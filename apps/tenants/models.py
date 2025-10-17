# apps/tenants/models.py
import uuid
from django.db import models


PLAN_CHOICES = [
    ("1", "BASIC"),
    ("2", "PREMIUM"),
    ("3", "DIAMOND"),
]

class Vendor(models.Model):
    # INTERNAL SYSTEM IDENTIFIER (used as PK for consistency and safety)
    internal_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)

    # HUMAN-READABLE TENANT IDENTIFIER (used for integration, communication)
    tenant_id = models.CharField(max_length=64, unique=True, help_text="Short, readable identifier (e.g., LAB001)")

    name = models.CharField(max_length=255)
    contact_email = models.EmailField(unique=True)

    # ACCESS & SUBSCRIPTION
    is_active = models.BooleanField(default=False, help_text="Set to False if subscription lapses or vendor is disabled.")
    plan_type = models.CharField(max_length=50,
        default='BASIC',
        help_text="Plan type for RBAC and feature gating."
    )

    # FLEXIBLE METADATA
    configuration = models.JSONField(default=dict, blank=True, help_text="LIS-specific settings (logo, timezone, features).")
    billing_metadata = models.JSONField( default=dict, blank=True, help_text="External IDs: Stripe Customer ID, Subscription ID, etc.")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.tenant_id})"


class VendorDomain(models.Model):
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name='domains'
    )
    domain_name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="The domain or subdomain used by this vendor."
    )
    is_primary = models.BooleanField(default=True)

    class Meta:
        # Only one domain can be marked as primary to a vendor
        unique_together = ('vendor', 'is_primary') 
        
    def __str__(self):
        return self.domain_name
