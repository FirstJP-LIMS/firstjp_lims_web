
# apps/tenants/models.py 
"""
Tenants management: Models to be used for lab owners who wants to share our platform to analyze their samples.. 
Unique domain name attached to individual tenants.
"""
import uuid
from django.db import models, transaction
from django.conf import settings
from .utils import send_vendor_activation_email
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator


PLAN_CHOICES = [
    ("1", "BASIC"),
    ("2", "STANDARD"),
    ("2", "PREMIUM"),
    ("3", "PLATINUM"),
]

subdomain_validator = RegexValidator(
    regex=r'^[a-z0-9-]+$',
    message="Subdomain can only contain lowercase letters, numbers, and hyphens."
)


class Vendor(models.Model):
    internal_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    contact_email = models.EmailField(unique=True)
    subdomain_prefix = models.SlugField(max_length=64, 
                                        unique=True, 
                                        blank=True, null=True, 
                                        validators=[subdomain_validator],
                                        help_text="Subdomain prefix for this vendor (letters, numbers, hyphens only)"
                                        )

    is_active = models.BooleanField(default=False)
    activation_email_sent = models.BooleanField(default=False)

    plan_type = models.CharField(max_length=50, choices=PLAN_CHOICES, default="BASIC")
    billing_metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__original_is_active = self.is_active

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        if not self.tenant_id:
            with transaction.atomic():
                last_vendor = Vendor.objects.select_for_update().order_by("-created_at").first()
                current_number = 0
                if last_vendor and last_vendor.tenant_id.startswith("LAB"):
                    try:
                        current_number = int(last_vendor.tenant_id.replace("LAB", ""))
                    except ValueError:
                        pass
                self.tenant_id = f"LAB{current_number + 1:04d}"

        super().save(*args, **kwargs)

        # Send activation email synchronously (NO Celery)
        if (
            not is_new
            and self.is_active
            and not self.__original_is_active
            and not self.activation_email_sent
        ):
            send_vendor_activation_email(self)
            self.activation_email_sent = True
            super().save(update_fields=["activation_email_sent"])

        self.__original_is_active = self.is_active

    def get_primary_domain(self):
        return self.domains.filter(is_primary=True).first()

    def __str__(self):
        return f"{self.name} ({self.tenant_id})"


class VendorDomain(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="domains") # THe related name 'domains' can be used by Vendor instance to access VendorDomain objects and attributes. 
    domain_name = models.CharField(max_length=255, unique=True, db_index=True)
    is_primary = models.BooleanField(default=True)

    # def clean(self):
    #     if self.pk and self.vendor.is_active:
    #         raise ValidationError("Domain cannot be modified after vendor activation.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        # return f"{self.domain_name} ({'Primary' if self.is_primary else 'Secondary'})"
        return f"{self.domain_name} onwered by {self.vendor.name}"

