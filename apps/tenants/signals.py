# apps/tenants/signals.py 
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

