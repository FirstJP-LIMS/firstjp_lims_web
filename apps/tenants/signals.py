# apps/tenants/signals.py (FIXED)
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Vendor, VendorDomain


# @receiver(post_save, sender=Vendor)
# def create_vendor_domain(sender, instance, created, **kwargs):
#     """
#     Automatically creates a full domain/subdomain for each vendor upon activation.
#     """
#     if instance.is_active:
#         BASE_DOMAIN = settings.GLOBAL_HOSTS[0] if settings.GLOBAL_HOSTS else "localhost"
#         subdomain = instance.subdomain_prefix.lower()
#         full_domain = f"{subdomain}.{BASE_DOMAIN}"

#         domain_obj, created_domain = VendorDomain.objects.get_or_create(
#             vendor=instance,
#             defaults={'domain_name': full_domain, 'is_primary': True}
#         )

#         if not created_domain and domain_obj.domain_name != full_domain:
#             domain_obj.domain_name = full_domain
#             domain_obj.save()

#         print(f"✅ Vendor domain set: {full_domain}")




# Define a fallback base domain setting (recommended)
# Ensure PLATFORM_BASE_DOMAIN is set in your settings.py (e.g., 'localhost.test' or 'firstjplims.com')
PLATFORM_BASE_DOMAIN = getattr(settings, 'PLATFORM_BASE_DOMAIN', 'localhost')


@receiver(post_save, sender=Vendor)
def activate_vendor_domain(sender, instance, created, **kwargs):
    """
    Constructs the full domain name and ensures a primary VendorDomain object exists
    and is active when Vendor.is_active is set to True.
    """
    if instance.is_active:
        
        # 1. Attempt to find the existing VendorDomain object (created during self-registration)
        domain_obj = VendorDomain.objects.filter(vendor=instance).first()
        
        subdomain_prefix = instance.tenant_id.lower() # Default fallback prefix
        
        if domain_obj:
            # Check if a specific prefix was acquired/provided during onboarding
            if domain_obj.acquired_domain:
                subdomain_prefix = domain_obj.acquired_domain.lower()
            
            # Use the dedicated setting, falling back to the default if not found
            BASE_DOMAIN = PLATFORM_BASE_DOMAIN
            full_domain = f"{subdomain_prefix}.{BASE_DOMAIN}"
            
            # 2. Update the existing object if the final domain is not yet set
            if domain_obj.domain_name != full_domain:
                domain_obj.domain_name = full_domain
                domain_obj.acquired_domain = None  # Clear the staging field
                domain_obj.save()
                print(f"✅ Domain ACTIVATED/UPDATED: {full_domain}")

        else:
            # 3. Handle case where Vendor was created directly by admin without a VendorDomain
            BASE_DOMAIN = PLATFORM_BASE_DOMAIN
            full_domain = f"{subdomain_prefix}.{BASE_DOMAIN}"
            
            VendorDomain.objects.create(
                vendor=instance,
                domain_name=full_domain, 
                is_primary=True
            )
            print(f"✅ Default Domain CREATED: {full_domain}")