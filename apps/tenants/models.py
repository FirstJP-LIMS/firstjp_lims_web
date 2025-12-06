"""
Tenants management: Models to be used for lab owners who wants to share our platform to analyze their samples.. Unique domain name attached to individual tenants.
"""
import uuid
from django.db import models
from django.db import transaction
# from django.db.models import Max

PLAN_CHOICES = [
    ("1", "BASIC"), # 1 - 20 users
    ("2", "STANDARD"), # 21 - 50 users
    ("2", "PREMIUM"), # 51 - 100 users
    ("3", "PLATINUM"), # 100+ users
]

# Set up profile     
class Vendor(models.Model):
    internal_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    tenant_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    contact_email = models.EmailField(unique=True)
    subdomain_prefix = models.SlugField(
        max_length=64,
        unique=True,
        blank=True,
        null=True,
        help_text="Subdomain prefix for this vendor (e.g., carbonilab)."
    )
    # ACCESS & SUBSCRIPTION
    is_active = models.BooleanField(default=False, help_text="Set to False if subscription lapses or vendor is disabled.")
    
    plan_type = models.CharField(max_length=50,
        choices=PLAN_CHOICES,
        default='BASIC',
        help_text="Plan type for this vendor.",
    )

    # FLEXIBLE METADATA
    # configuration = models.JSONField(default=dict, blank=True, help_text="LIS-specific settings (logo, timezone, features).")
    billing_metadata = models.JSONField( default=dict, blank=True, help_text="External IDs: Stripe Customer ID, Subscription ID, etc.")

    created_at = models.DateTimeField(auto_now_add=True)

    # generate vendor id  
    def save(self, *args, **kwargs):
        if not self.tenant_id:
            with transaction.atomic():
                last_vendor = Vendor.objects.select_for_update().order_by('-created_at').first()
                if last_vendor and last_vendor.tenant_id.startswith('LAB'):
                    try:
                        current_number = int(last_vendor.tenant_id.replace('LAB', ''))
                    except ValueError:
                        current_number = 0
                else:
                    current_number = 0
                next_number = current_number + 1
                self.tenant_id = f"LAB{next_number:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.tenant_id})"


class VendorDomain(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='domains')
    domain_name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="The full domain/subdomain used by this vendor."
    )
    is_primary = models.BooleanField(default=True)

    class Meta:
        # Only one domain can be marked as primary to a vendor
        unique_together = ('vendor', 'is_primary')

    def __str__(self):
        return self.domain_name

