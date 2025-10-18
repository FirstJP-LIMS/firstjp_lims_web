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


# # Check the two
# class TenantAwareManager(models.Manager):
#     def for_tenant(self, tenant):
#         if tenant is None:
#             return self.get_queryset().none()
#         # tenant may be Vendor instance or UUID
#         tenant_obj = tenant if hasattr(tenant, 'internal_id') else None
#         if tenant_obj:
#             return self.get_queryset().filter(tenant=tenant_obj)
#         # fallback
#         return self.get_queryset().filter(tenant__internal_id=tenant)
