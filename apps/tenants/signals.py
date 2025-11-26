from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
import logging
from .models import Vendor, VendorDomain

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Vendor)
def handle_vendor_domain(sender, instance, created, **kwargs):
    """
    Ensure VendorDomain exists for each Vendor:
    - Constructs domain: subdomain_prefix + PLATFORM_BASE_DOMAIN
    - Ensures only one primary domain per vendor
    - Updates domain_name if subdomain changes
    """

    if not instance.subdomain_prefix:
        # Fall back to tenant_id if no subdomain
        subdomain = instance.tenant_id.lower()
    else:
        subdomain = instance.subdomain_prefix.lower()

    base_domain = getattr(settings, 'PLATFORM_BASE_DOMAIN', 'localhost.test')
    full_domain = f"{subdomain}.{base_domain}"

    try:
        # Check if a primary domain exists
        domain_obj = VendorDomain.objects.filter(vendor=instance, is_primary=True).first()

        if domain_obj:
            # Update domain name if changed
            if domain_obj.domain_name != full_domain:
                domain_obj.domain_name = full_domain
                domain_obj.save(update_fields=['domain_name'])
                logger.info(f"Updated VendorDomain for {instance.tenant_id}: {full_domain}")
        else:
            # No primary domain exists → create one
            VendorDomain.objects.create(
                vendor=instance,
                domain_name=full_domain,
                is_primary=True
            )
            logger.info(f"Created VendorDomain for {instance.tenant_id}: {full_domain}")

    except Exception as e:
        logger.error(f"Error creating/updating VendorDomain for {instance.tenant_id}: {e}")

    # Optional: print for dev purposes
    print(f"✅ Vendor domain set: {full_domain}")


# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from django.conf import settings
# from .models import Vendor, VendorDomain


# @receiver(post_save, sender=Vendor)
# def handle_vendor_domain(sender, instance, created, **kwargs):
#     """
#     Constructs the full domain name and ensures a primary VendorDomain object exists
#     and is active when Vendor.is_active is set to True.
#     """
#     if not instance.is_active:
#         return

#     subdomain = (
#         instance.subdomain_prefix.lower()
#         if instance.subdomain_prefix
#         else instance.tenant_id.lower()
#     )
#     base_domain = getattr(settings, 'PLATFORM_BASE_DOMAIN', 'localhost.test')
#     full_domain = f"{subdomain}.{base_domain}"

#     domain_obj, created_domain = VendorDomain.objects.get_or_create(
#         vendor=instance,
#         defaults={'domain_name': full_domain, 'is_primary': True}
#     )

#     if not created_domain and domain_obj.domain_name != full_domain:
#         domain_obj.domain_name = full_domain
#         # domain_obj.acquired_domain = None
#         domain_obj.save()

#     print(f"✅ Vendor domain set: {full_domain}")

