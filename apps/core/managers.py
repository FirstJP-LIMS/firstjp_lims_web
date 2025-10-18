# apps/core/managers.py
from django.db import models

class TenantAwareManager(models.Manager):
    """
    Custom manager that always requires a tenant object to scope the queryset.
    """
    def for_tenant(self, tenant):
        """Returns a queryset filtered by the provided Vendor/Tenant object."""
        if not tenant:
            # Prevent accidental querying without a tenant (good security measure)
            raise ValueError("Tenant object must be provided for a tenant-aware query.")
        return self.get_queryset().filter(tenant=tenant)
        
    def get_queryset(self):
        # Override to potentially add global filters, but for tenant models,
        # To resolve un-scoped for .for_tenant()
        return super().get_queryset()

